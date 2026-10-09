import json
import os
import re
from datetime import datetime, timezone

import boto3

sqs = boto3.client("sqs")
QUEUE_URL = os.environ["QUEUE_URL"]
state_table = boto3.resource("dynamodb").Table(os.environ.get("STATE_TABLE", "user-search-state"))

SUPPORTED_LOCATIONS = {"manhattan", "new york", "new york city", "nyc", "new york, ny", "midtown", "downtown"}
SUPPORTED_CUISINES = {"chinese", "japanese", "italian", "mexican", "indian", "thai"}
MAX_PARTY = 20
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------- Lex V2 helpers ----------

def slot_value(slots, name):
    slot = (slots or {}).get(name)
    if not slot or not slot.get("value"):
        return None
    return slot["value"].get("interpretedValue") or slot["value"].get("originalValue")


def _messages(text):
    return [{"contentType": "PlainText", "content": text}]


def close(intent, text):
    intent["state"] = "Fulfilled"
    return {
        "sessionState": {"dialogAction": {"type": "Close"}, "intent": intent},
        "messages": _messages(text),
    }


def delegate(intent):
    return {"sessionState": {"dialogAction": {"type": "Delegate"}, "intent": intent}}


def elicit_slot(intent, slot_name, text, clear=True):
    if clear:
        intent["slots"][slot_name] = None  # clear a rejected value so Lex re-asks
    return {
        "sessionState": {
            "dialogAction": {"type": "ElicitSlot", "slotToElicit": slot_name},
            "intent": intent,
        },
        "messages": _messages(text),
    }


# ---------- Intent handlers ----------

def greeting(intent):
    return close(intent, "Hi there, how can I help?")


def thank_you(intent):
    return close(intent, "You're welcome!")


def validate_dining_slots(slots):
    """Return (slot_name, message) for the first invalid slot, else None."""
    location = slot_value(slots, "Location")
    if location and location.strip().lower() not in SUPPORTED_LOCATIONS:
        return "Location", f"Sorry, I can't fulfill requests for {location}. Please enter a valid location (I currently cover Manhattan)."

    cuisine = slot_value(slots, "Cuisine")
    if cuisine and cuisine.strip().lower() not in SUPPORTED_CUISINES:
        return "Cuisine", f"Sorry, I don't have {cuisine} restaurants. Try one of: {', '.join(c.title() for c in sorted(SUPPORTED_CUISINES))}."

    people = slot_value(slots, "NumberOfPeople")
    if people:
        try:
            n = int(float(people))
        except ValueError:
            n = 0
        if not 1 <= n <= MAX_PARTY:
            return "NumberOfPeople", f"I can book for between 1 and {MAX_PARTY} people. How many people are in your party?"

    email = slot_value(slots, "Email")
    if email and not EMAIL_RE.match(email.strip()):
        return "Email", "That doesn't look like a valid email address. Could you re-enter it?"

    return None


# ---------- Extra credit: remember the last search per session ----------

def get_last_search(session_id):
    try:
        resp = state_table.get_item(Key={"SessionId": session_id})
    except Exception as exc:  # don't let a state-table hiccup break the main flow
        print(f"get_last_search failed: {exc!r}")
        return None
    return resp.get("Item")


def save_last_search(session_id, location, cuisine):
    """LF1 owns Location/Cuisine freshness; RestaurantIds is written by LF2 once it knows
    which restaurants were actually sent (fresh pick or reused), so it is left untouched here."""
    try:
        state_table.update_item(
            Key={"SessionId": session_id},
            UpdateExpression="SET #loc = :l, Cuisine = :c, UpdatedAt = :u",
            ExpressionAttributeNames={"#loc": "Location"},  # Location is a DynamoDB reserved word
            ExpressionAttributeValues={
                ":l": location, ":c": cuisine, ":u": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        print(f"save_last_search failed: {exc!r}")


def dining_suggestions(event, intent):
    source = event.get("invocationSource")
    slots = intent.get("slots") or {}
    session_id = event.get("sessionId", "")

    if source == "DialogCodeHook":
        problem = validate_dining_slots(slots)
        if problem:
            return elicit_slot(intent, *problem)

        # Once Location & Cuisine are both valid, and before we've asked, check whether this
        # session searched the same location+cuisine before; if so, offer to repeat it.
        location = slot_value(slots, "Location")
        cuisine = slot_value(slots, "Cuisine")
        same_as_last = slot_value(slots, "SameAsLastTime")
        if location and cuisine and not same_as_last:
            last = get_last_search(session_id)
            if (last and last.get("Location", "").strip().lower() == location.strip().lower()
                    and last.get("Cuisine", "").strip().lower() == cuisine.strip().lower()):
                return elicit_slot(
                    intent, "SameAsLastTime",
                    f"Looks like you searched for {cuisine} food in {location} last time too! "
                    "Would you like the same recommendations as last time?",
                    clear=False,
                )
        return delegate(intent)

    # FulfillmentCodeHook: every required slot is filled and valid
    location = slot_value(slots, "Location")
    cuisine = slot_value(slots, "Cuisine").lower()
    same_as_last = (slot_value(slots, "SameAsLastTime") or "").strip().lower()
    reuse = same_as_last in ("yes", "yeah", "yep", "sure")

    request = {
        "sessionId": session_id,
        "location": location,
        "cuisine": cuisine,
        "diningTime": slot_value(slots, "DiningTime"),
        "numberOfPeople": int(float(slot_value(slots, "NumberOfPeople"))),
        "email": slot_value(slots, "Email").strip(),
    }
    if reuse:
        last = get_last_search(session_id)
        if last and last.get("RestaurantIds"):
            request["restaurantIds"] = list(last["RestaurantIds"])

    save_last_search(session_id, location, cuisine)
    sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(request))

    confirmation = (
        "You're all set. Sending you the same recommendations as last time, "
        if request.get("restaurantIds") else
        f"You're all set. I've received your request and will email my {cuisine.title()} restaurant suggestions "
    )
    return close(intent, confirmation + f"to {request['email']} shortly. Have a good day!")


HANDLERS = {"GreetingIntent": greeting, "ThankYouIntent": thank_you}


def lambda_handler(event, context):
    print(json.dumps(event))
    intent = event["sessionState"]["intent"]
    name = intent["name"]

    if name == "DiningSuggestionsIntent":
        return dining_suggestions(event, intent)
    if name in HANDLERS:
        return HANDLERS[name](intent)
    return close(intent, "Sorry, I didn't understand that.")
