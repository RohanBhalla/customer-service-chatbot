"""Create the DiningConcierge Lex V2 bot (intents, slots, alias with LF1 code hook).

Usage: .venv/bin/python other-scripts/setup_lex_bot.py
Re-running exits if the bot already exists; delete it in the Lex console first.
"""
import sys
import time

import boto3

REGION = "us-east-1"
ACCOUNT = "088850687383"
BOT_NAME = "DiningConcierge"
LOCALE = "en_US"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/lex-hw1-bot-role"
LF1_ARN = f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:LF1"
ALIAS_NAME = "prod"

CUISINES = ["Chinese", "Japanese", "Italian", "Mexican", "Indian", "Thai"]
LOCATIONS = ["Manhattan", "New York", "New York City", "NYC", "Midtown", "Downtown"]

lex = boto3.client("lexv2-models", region_name=REGION)
lam = boto3.client("lambda", region_name=REGION)


def msg(text):
    return {"messageGroups": [{"message": {"plainTextMessage": {"value": text}}}],
            "maxRetries": 3, "allowInterrupt": True}


def wait(fetch, status_key, ok, label):
    while True:
        try:
            status = fetch()[status_key]
        except lex.exceptions.ResourceNotFoundException:  # eventual consistency right after create
            status = "NotVisibleYet"
        print(f"  {label}: {status}")
        if status in ok:
            return
        if status in ("Failed", "ReadyExpressTesting_Failed"):
            sys.exit(f"{label} failed")
        time.sleep(4)


def existing_bot():
    kwargs = {}
    while True:
        page = lex.list_bots(**kwargs)
        for b in page["botSummaries"]:
            if b["botName"] == BOT_NAME:
                return b["botId"]
        if "nextToken" not in page:
            return None
        kwargs["nextToken"] = page["nextToken"]


if existing_bot():
    sys.exit(f"Bot {BOT_NAME} already exists ({existing_bot()}). Delete it first to recreate.")

print("Creating bot")
bot_id = lex.create_bot(
    botName=BOT_NAME, roleArn=ROLE_ARN, dataPrivacy={"childDirected": False},
    idleSessionTTLInSeconds=300, description="Dining Concierge chatbot (HW1)",
)["botId"]
wait(lambda: lex.describe_bot(botId=bot_id), "botStatus", ("Available",), "bot")

lex.create_bot_locale(botId=bot_id, botVersion="DRAFT", localeId=LOCALE, nluIntentConfidenceThreshold=0.4)
wait(lambda: lex.describe_bot_locale(botId=bot_id, botVersion="DRAFT", localeId=LOCALE),
     "botLocaleStatus", ("NotBuilt",), "locale create")
common = dict(botId=bot_id, botVersion="DRAFT", localeId=LOCALE)

print("Creating slot types")
cuisine_type = lex.create_slot_type(
    slotTypeName="CuisineType", **common,
    slotTypeValues=[{"sampleValue": {"value": c}} for c in CUISINES],
    valueSelectionSetting={"resolutionStrategy": "TopResolution"},
)["slotTypeId"]
# OriginalValue lets unknown cities through so LF1 can reject them with a friendly message.
location_type = lex.create_slot_type(
    slotTypeName="LocationType", **common,
    slotTypeValues=[{"sampleValue": {"value": v}} for v in LOCATIONS],
    valueSelectionSetting={"resolutionStrategy": "OriginalValue"},
)["slotTypeId"]

print("Creating intents")
greeting = lex.create_intent(
    intentName="GreetingIntent", **common, fulfillmentCodeHook={"enabled": True},
    sampleUtterances=[{"utterance": u} for u in ["Hello", "Hi", "Hey", "Hi there", "Hey there", "Good morning", "Good evening"]],
)["intentId"]
thanks = lex.create_intent(
    intentName="ThankYouIntent", **common, fulfillmentCodeHook={"enabled": True},
    sampleUtterances=[{"utterance": u} for u in ["Thanks", "Thank you", "Thanks a lot", "Thank you so much", "Thx", "Appreciate it"]],
)["intentId"]
dining = lex.create_intent(
    intentName="DiningSuggestionsIntent", **common,
    dialogCodeHook={"enabled": True}, fulfillmentCodeHook={"enabled": True},
    sampleUtterances=[{"utterance": u} for u in [
        "I need some restaurant suggestions", "I need restaurant suggestions", "Give me dining suggestions",
        "I'm hungry", "I want to find a restaurant", "Suggest a restaurant", "Where should I eat",
        "Can you recommend a place to eat", "Dining suggestions please"]],
)["intentId"]

print("Creating DiningSuggestionsIntent slots")
slot_defs = [  # (name, type id, prompt), in the order they are asked
    ("Location", location_type, "Great. I can help you with that. What city or city area are you looking to dine in?"),
    ("Cuisine", cuisine_type, "Got it. What cuisine would you like to try? (Chinese, Japanese, Italian, Mexican, Indian or Thai)"),
    ("NumberOfPeople", "AMAZON.Number", "Ok, how many people are in your party?"),
    ("DiningTime", "AMAZON.Time", "What time would you like to dine?"),
    ("Email", "AMAZON.EmailAddress", "Great. Lastly, what email address should I send my findings to?"),
]
slot_ids = []
for name, type_id, prompt in slot_defs:
    slot_ids.append(lex.create_slot(
        slotName=name, slotTypeId=type_id, intentId=dining, **common,
        valueElicitationSetting={"slotConstraint": "Required", "promptSpecification": msg(prompt)},
    )["slotId"])

lex.update_intent(
    intentId=dining, intentName="DiningSuggestionsIntent", **common,
    dialogCodeHook={"enabled": True}, fulfillmentCodeHook={"enabled": True},
    sampleUtterances=[{"utterance": u} for u in [
        "I need some restaurant suggestions", "I need restaurant suggestions", "Give me dining suggestions",
        "I'm hungry", "I want to find a restaurant", "Suggest a restaurant", "Where should I eat",
        "Can you recommend a place to eat", "Dining suggestions please",
        "I want {Cuisine} food", "Find me {Cuisine} restaurants in {Location}"]],
    slotPriorities=[{"priority": i + 1, "slotId": s} for i, s in enumerate(slot_ids)],
)

print("Building locale")
lex.build_bot_locale(botId=bot_id, botVersion="DRAFT", localeId=LOCALE)
wait(lambda: lex.describe_bot_locale(botId=bot_id, botVersion="DRAFT", localeId=LOCALE),
     "botLocaleStatus", ("Built",), "locale")

print("Publishing version")
version = lex.create_bot_version(
    botId=bot_id, botVersionLocaleSpecification={LOCALE: {"sourceBotVersion": "DRAFT"}})["botVersion"]
wait(lambda: lex.describe_bot_version(botId=bot_id, botVersion=version), "botStatus", ("Available",), "version")

hook = {LOCALE: {"enabled": True, "codeHookSpecification": {
    "lambdaCodeHook": {"lambdaARN": LF1_ARN, "codeHookInterfaceVersion": "1.0"}}}}
alias_id = lex.create_bot_alias(
    botAliasName=ALIAS_NAME, botId=bot_id, botVersion=version, botAliasLocaleSettings=hook)["botAliasId"]
# Also attach LF1 to the built-in TestBotAlias so the Lex console "Test" pane uses the code hook.
lex.update_bot_alias(botId=bot_id, botAliasId="TSTALIASID", botAliasName="TestBotAlias",
                     botVersion="DRAFT", botAliasLocaleSettings=hook)

lam.add_permission(
    FunctionName="LF1", StatementId="lex-invoke-dining-concierge", Action="lambda:InvokeFunction",
    Principal="lexv2.amazonaws.com", SourceArn=f"arn:aws:lex:{REGION}:{ACCOUNT}:bot-alias/{bot_id}/*")

print(f"\nDONE\n  LEX_BOT_ID={bot_id}\n  LEX_BOT_ALIAS_ID={alias_id}\n  version={version}")
