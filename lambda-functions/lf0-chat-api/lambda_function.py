import json
import os
import re
import uuid
from datetime import datetime, timezone

import boto3

lex = boto3.client("lexv2-runtime")

BOT_ID = os.environ["LEX_BOT_ID"]
BOT_ALIAS_ID = os.environ["LEX_BOT_ALIAS_ID"]
LOCALE_ID = os.environ.get("LEX_LOCALE_ID", "en_US")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,POST",
    "Content-Type": "application/json",
}

FALLBACK_TEXT = "Sorry, I didn't catch that. Could you rephrase?"


def _response(status, body):
    return {"statusCode": status, "headers": CORS_HEADERS, "body": json.dumps(body)}


def _error(status, message):
    return _response(status, {"code": status, "message": message})


def _bot_message(text):
    return {
        "type": "unstructured",
        "unstructured": {
            "id": str(uuid.uuid4()),
            "text": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


def _session_id(message):
    """The frontend sends its browser-stored session id in unstructured.id."""
    raw = (message.get("unstructured") or {}).get("id") or ""
    # Lex sessionId: 2-100 chars of [0-9a-zA-Z._:-]
    cleaned = re.sub(r"[^0-9a-zA-Z._:-]", "", raw)[:100]
    return cleaned if len(cleaned) >= 2 else str(uuid.uuid4())


def lambda_handler(event, context):
    # i) extract the text message from the API request
    try:
        body = json.loads(event.get("body") or "{}")
        message = body["messages"][0]
        text = message["unstructured"]["text"]
    except (ValueError, KeyError, TypeError, IndexError):
        return _error(400, "Invalid request body")
    if not isinstance(text, str) or not text.strip():
        return _error(400, "Message text is empty")

    # ii) send it to Lex, iii) wait for the response
    try:
        result = lex.recognize_text(
            botId=BOT_ID,
            botAliasId=BOT_ALIAS_ID,
            localeId=LOCALE_ID,
            sessionId=_session_id(message),
            text=text,
        )
    except Exception as exc:  # surface a clean 500 instead of an opaque proxy error
        print(f"Lex call failed: {exc!r}")
        return _error(500, "The chatbot is unavailable right now. Please try again.")

    # iv) send back Lex's response as the API response
    lex_messages = [m["content"] for m in result.get("messages", []) if m.get("content")]
    if not lex_messages:
        lex_messages = [FALLBACK_TEXT]
    return _response(200, {"messages": [_bot_message(t) for t in lex_messages]})
