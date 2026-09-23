import json
import os
import re

import boto3

sqs = boto3.client("sqs")
QUEUE_URL = os.environ["QUEUE_URL"]

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


def elicit_slot(intent, slot_name, text):
    intent["slots"][slot_name] = None  # clear the rejected value so Lex re-asks
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


def dining_suggestions(event, intent):
    source = event.get("invocationSource")
    slots = intent.get("slots") or {}

    if source == "DialogCodeHook":
        problem = validate_dining_slots(slots)
        if problem:
            return elicit_slot(intent, *problem)
        return delegate(intent)

    # FulfillmentCodeHook: every slot is filled and valid
    request = {
        "location": slot_value(slots, "Location"),
        "cuisine": slot_value(slots, "Cuisine").lower(),
        "diningTime": slot_value(slots, "DiningTime"),
        "numberOfPeople": int(float(slot_value(slots, "NumberOfPeople"))),
        "email": slot_value(slots, "Email").strip(),
    }
    sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(request))
    return close(
        intent,
        "You're all set. I've received your request and will email my "
        f"{request['cuisine'].title()} restaurant suggestions to {request['email']} shortly. Have a good day!",
    )


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
