"""Add the SameAsLastTime slot (extra credit) to the existing DiningConcierge bot,
rebuild the DRAFT locale, publish a new version, and repoint the `prod` alias at it.

Usage: .venv/bin/python scripts/update_lex_add_state_slot.py
Safe to re-run: skips the slot type / slot if they already exist, but always publishes
a fresh version and repoints the alias (cheap, and keeps the alias on the latest DRAFT).
"""
import sys
import time

import boto3

REGION = "us-east-1"
ACCOUNT = "088850687383"
BOT_NAME = "DiningConcierge"
LOCALE = "en_US"
LF1_ARN = f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:LF1"
ALIAS_NAME = "prod"

lex = boto3.client("lexv2-models", region_name=REGION)


def msg(text):
    return {"messageGroups": [{"message": {"plainTextMessage": {"value": text}}}],
            "maxRetries": 3, "allowInterrupt": True}


def wait(fetch, status_key, ok, label):
    while True:
        try:
            status = fetch()[status_key]
        except lex.exceptions.ResourceNotFoundException:
            status = "NotVisibleYet"
        print(f"  {label}: {status}")
        if status in ok:
            return
        if status in ("Failed", "ReadyExpressTesting_Failed"):
            sys.exit(f"{label} failed")
        time.sleep(4)


def find_bot_id():
    kwargs = {}
    while True:
        page = lex.list_bots(**kwargs)
        for b in page["botSummaries"]:
            if b["botName"] == BOT_NAME:
                return b["botId"]
        if "nextToken" not in page:
            sys.exit(f"Bot {BOT_NAME} not found.")
        kwargs["nextToken"] = page["nextToken"]


bot_id = find_bot_id()
print(f"bot: {bot_id}")
common = dict(botId=bot_id, botVersion="DRAFT", localeId=LOCALE)


def find_intent_id(name):
    kwargs = {**common}
    while True:
        page = lex.list_intents(**kwargs)
        for i in page["intentSummaries"]:
            if i["intentName"] == name:
                return i["intentId"]
        if "nextToken" not in page:
            sys.exit(f"Intent {name} not found.")
        kwargs["nextToken"] = page["nextToken"]


def find_slot_type_id(name):
    kwargs = {**common}
    while True:
        page = lex.list_slot_types(**kwargs)
        for s in page["slotTypeSummaries"]:
            if s["slotTypeName"] == name:
                return s["slotTypeId"]
        if "nextToken" not in page:
            return None
        kwargs["nextToken"] = page["nextToken"]


def find_slot_id(intent_id, name):
    kwargs = {**common, "intentId": intent_id}
    while True:
        page = lex.list_slots(**kwargs)
        for s in page["slotSummaries"]:
            if s["slotName"] == name:
                return s["slotId"]
        if "nextToken" not in page:
            return None
        kwargs["nextToken"] = page["nextToken"]


dining_id = find_intent_id("DiningSuggestionsIntent")
print(f"DiningSuggestionsIntent: {dining_id}")

yesno_type_id = find_slot_type_id("YesNoType")
if yesno_type_id:
    print(f"YesNoType already exists: {yesno_type_id}")
else:
    yesno_type_id = lex.create_slot_type(
        slotTypeName="YesNoType", **common,
        slotTypeValues=[
            {"sampleValue": {"value": "Yes"}, "synonyms": [{"value": v} for v in
             ["Yeah", "Yep", "Sure", "Of course", "Please do", "Yes please"]]},
            {"sampleValue": {"value": "No"}, "synonyms": [{"value": v} for v in
             ["Nope", "No thanks", "Not this time", "Nah"]]},
        ],
        valueSelectionSetting={"resolutionStrategy": "TopResolution"},
    )["slotTypeId"]
    print(f"Created YesNoType: {yesno_type_id}")

existing_slot_id = find_slot_id(dining_id, "SameAsLastTime")
if existing_slot_id:
    print(f"SameAsLastTime slot already exists: {existing_slot_id}")
    same_slot_id = existing_slot_id
else:
    same_slot_id = lex.create_slot(
        slotName="SameAsLastTime", slotTypeId=yesno_type_id, intentId=dining_id, **common,
        valueElicitationSetting={
            "slotConstraint": "Optional",  # only elicited explicitly by LF1's code hook
            "promptSpecification": msg("Would you like the same recommendation as last time?"),
        },
    )["slotId"]
    print(f"Created SameAsLastTime slot: {same_slot_id}")

# Re-fetch the other slot ids (unchanged) to rebuild full slot priority order:
# Location, Cuisine, SameAsLastTime, NumberOfPeople, DiningTime, Email
order = ["Location", "Cuisine", "SameAsLastTime", "NumberOfPeople", "DiningTime", "Email"]
slot_ids = {"SameAsLastTime": same_slot_id}
for name in order:
    if name not in slot_ids:
        sid = find_slot_id(dining_id, name)
        if not sid:
            sys.exit(f"Expected slot {name} not found on DiningSuggestionsIntent.")
        slot_ids[name] = sid

lex.update_intent(
    intentId=dining_id, intentName="DiningSuggestionsIntent", **common,
    dialogCodeHook={"enabled": True}, fulfillmentCodeHook={"enabled": True},
    sampleUtterances=[{"utterance": u} for u in [
        "I need some restaurant suggestions", "I need restaurant suggestions", "Give me dining suggestions",
        "I'm hungry", "I want to find a restaurant", "Suggest a restaurant", "Where should I eat",
        "Can you recommend a place to eat", "Dining suggestions please",
        "I want {Cuisine} food", "Find me {Cuisine} restaurants in {Location}"]],
    slotPriorities=[{"priority": i + 1, "slotId": slot_ids[name]} for i, name in enumerate(order)],
)
print("Updated DiningSuggestionsIntent slot priorities")

print("Building locale")
lex.build_bot_locale(botId=bot_id, botVersion="DRAFT", localeId=LOCALE)
wait(lambda: lex.describe_bot_locale(botId=bot_id, botVersion="DRAFT", localeId=LOCALE),
     "botLocaleStatus", ("Built",), "locale")

print("Publishing new version")
version = lex.create_bot_version(
    botId=bot_id, botVersionLocaleSpecification={LOCALE: {"sourceBotVersion": "DRAFT"}})["botVersion"]
wait(lambda: lex.describe_bot_version(botId=bot_id, botVersion=version), "botStatus", ("Available",), "version")

hook = {LOCALE: {"enabled": True, "codeHookSpecification": {
    "lambdaCodeHook": {"lambdaARN": LF1_ARN, "codeHookInterfaceVersion": "1.0"}}}}
alias_id = None
kwargs = {"botId": bot_id}
while True:
    page = lex.list_bot_aliases(**kwargs)
    for a in page["botAliasSummaries"]:
        if a["botAliasName"] == ALIAS_NAME:
            alias_id = a["botAliasId"]
    if alias_id or "nextToken" not in page:
        break
    kwargs["nextToken"] = page["nextToken"]
if not alias_id:
    sys.exit(f"Alias {ALIAS_NAME} not found.")

lex.update_bot_alias(botId=bot_id, botAliasId=alias_id, botAliasName=ALIAS_NAME,
                     botVersion=version, botAliasLocaleSettings=hook)
print(f"\nDONE\n  version={version}\n  prod alias ({alias_id}) now points at version {version}")
