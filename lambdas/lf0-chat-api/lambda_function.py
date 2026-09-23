import json
import uuid
from datetime import datetime, timezone

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,POST",
    "Content-Type": "application/json",
}

BOILERPLATE = "I'm still under development. Please come back later."


def _response(status, body):
    return {"statusCode": status, "headers": CORS_HEADERS, "body": json.dumps(body)}


def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        messages = body.get("messages") or []
        # Request shape (swagger BotRequest): messages[].unstructured.text
        _ = messages[0]["unstructured"]["text"] if messages else ""
    except (ValueError, KeyError, TypeError, IndexError):
        return _response(400, {"code": 400, "message": "Invalid request body"})

    return _response(200, {
        "messages": [{
            "type": "unstructured",
            "unstructured": {
                "id": str(uuid.uuid4()),
                "text": BOILERPLATE,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }]
    })
