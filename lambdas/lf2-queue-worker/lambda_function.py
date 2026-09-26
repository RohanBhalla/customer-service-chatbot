import base64
import json
import os
import random
import urllib.request
from datetime import datetime

import boto3
from boto3.dynamodb.conditions import Attr

QUEUE_URL = os.environ["QUEUE_URL"]
TABLE_NAME = os.environ.get("TABLE_NAME", "yelp-restaurants")
SENDER = os.environ["SENDER_EMAIL"]
OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT", "").rstrip("/")
OPENSEARCH_USER = os.environ.get("OPENSEARCH_USER", "")
OPENSEARCH_PASSWORD = os.environ.get("OPENSEARCH_PASSWORD", "")
NUM_SUGGESTIONS = 3
MAX_RECEIVES = 3  # give up on a message that has failed this many times

sqs = boto3.client("sqs")
ses = boto3.client("sesv2")
table = boto3.resource("dynamodb").Table(TABLE_NAME)


# ---------- restaurant lookup ----------

def ids_from_opensearch(cuisine, n):
    """Random restaurant IDs for a cuisine from the OpenSearch `restaurants` index."""
    query = {
        "size": n,
        "_source": ["RestaurantID", "Cuisine"],
        "query": {"function_score": {
            "query": {"match": {"Cuisine": cuisine}},
            "random_score": {},
        }},
    }
    req = urllib.request.Request(
        f"{OPENSEARCH_ENDPOINT}/restaurants/_search",
        data=json.dumps(query).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Basic " + base64.b64encode(f"{OPENSEARCH_USER}:{OPENSEARCH_PASSWORD}".encode()).decode(),
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        hits = json.load(resp)["hits"]["hits"]
    return [h["_source"]["RestaurantID"] for h in hits]


def ids_from_dynamodb(cuisine, n):
    """Fallback used until OpenSearch exists: filter the DynamoDB table by cuisine."""
    items, kwargs = [], {"FilterExpression": Attr("Cuisine").eq(cuisine), "ProjectionExpression": "BusinessID"}
    while True:
        page = table.scan(**kwargs)
        items += page["Items"]
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    return [i["BusinessID"] for i in random.sample(items, min(n, len(items)))]


def get_restaurant_ids(cuisine, n):
    if OPENSEARCH_ENDPOINT:
        return ids_from_opensearch(cuisine, n)
    print("OPENSEARCH_ENDPOINT not set: using DynamoDB fallback")
    return ids_from_dynamodb(cuisine, n)


def get_restaurant_details(ids):
    """Name, address etc. for each ID from the yelp-restaurants table."""
    if not ids:
        return []
    resp = boto3.resource("dynamodb").batch_get_item(
        RequestItems={TABLE_NAME: {"Keys": [{"BusinessID": i} for i in ids]}}
    )
    by_id = {r["BusinessID"]: r for r in resp["Responses"][TABLE_NAME]}
    return [by_id[i] for i in ids if i in by_id]  # keep the random order


# ---------- email ----------

def pretty_time(hhmm):
    try:
        return datetime.strptime(hhmm, "%H:%M").strftime("%-I:%M %p")
    except (ValueError, TypeError):
        return hhmm


def format_email(req, restaurants):
    cuisine = req["cuisine"].title()
    people = req["numberOfPeople"]
    lines = [f"Hello! Here are my {cuisine} restaurant suggestions for {people} "
             f"{'person' if int(people) == 1 else 'people'}, at {pretty_time(req.get('diningTime'))}:", ""]
    for i, r in enumerate(restaurants, 1):
        lines.append(f"{i}. {r['Name']}, located at {r['Address']} (rating {float(r['Rating']):.1f}, {int(r['NumberOfReviews'])} reviews)")
    lines += ["", "Enjoy your meal!"]
    return "\n".join(lines)


def send_email(to_addr, body):
    ses.send_email(
        FromEmailAddress=SENDER,
        Destination={"ToAddresses": [to_addr]},
        Content={"Simple": {
            "Subject": {"Data": "Your Dining Concierge suggestions"},
            "Body": {"Text": {"Data": body}},
        }},
    )


# ---------- worker ----------

def process(message):
    req = json.loads(message["Body"])
    ids = get_restaurant_ids(req["cuisine"], NUM_SUGGESTIONS)
    restaurants = get_restaurant_details(ids)
    if not restaurants:
        raise RuntimeError(f"no restaurants found for cuisine {req['cuisine']!r}")
    send_email(req["email"], format_email(req, restaurants))


def lambda_handler(event, context):
    resp = sqs.receive_message(
        QueueUrl=QUEUE_URL, MaxNumberOfMessages=10, WaitTimeSeconds=2,
        AttributeNames=["ApproximateReceiveCount"],
    )
    messages = resp.get("Messages", [])
    done = failed = 0
    for m in messages:
        try:
            process(m)
            sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=m["ReceiptHandle"])
            done += 1
        except Exception as exc:
            failed += 1
            print(f"Failed to process {m['MessageId']}: {exc!r}")
            if int(m["Attributes"]["ApproximateReceiveCount"]) >= MAX_RECEIVES:
                print(f"Dropping {m['MessageId']} after {MAX_RECEIVES} attempts")
                sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=m["ReceiptHandle"])
            # otherwise leave it: it becomes visible again after the visibility timeout
    print(f"processed={done} failed={failed} received={len(messages)}")
    return {"processed": done, "failed": failed}
