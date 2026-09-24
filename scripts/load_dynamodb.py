"""Load scripts/restaurants.json into the DynamoDB table `yelp-restaurants`.

Usage: .venv/bin/python scripts/load_dynamodb.py
Adds `insertedAtTimestamp` (UTC ISO-8601) to every item. Safe to re-run: items are keyed
by BusinessID, so a re-run overwrites rather than duplicates.
"""
import json
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLE = "yelp-restaurants"

# DynamoDB has no float type: parse JSON numbers as Decimal
with open(os.path.join(ROOT, "scripts", "restaurants.json")) as f:
    items = json.load(f, parse_float=Decimal)

table = boto3.resource("dynamodb", region_name="us-east-1").Table(TABLE)
with table.batch_writer(overwrite_by_pkeys=["BusinessID"]) as batch:
    for item in items:
        item["insertedAtTimestamp"] = datetime.now(timezone.utc).isoformat()
        batch.put_item(Item=item)

print(f"Wrote {len(items)} items to {TABLE}")
