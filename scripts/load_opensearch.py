"""Create the `restaurants` index and load RestaurantID/Cuisine docs into OpenSearch.

Usage: .venv/bin/python scripts/load_opensearch.py
Reads OPENSEARCH_ENDPOINT/USER/PASSWORD from .env and restaurant data from
data/yelp-restaurants.json (fall back to scripts/restaurants.json). Idempotent:
re-running overwrites documents (indexed by BusinessID) rather than duplicating them.

Note: modern OpenSearch dropped mapping "types" (one index = one implicit type).
The PDF's "create a type called Restaurant" is represented here as a `type: "Restaurant"`
field on every document, with the index itself named `restaurants` as required.
"""
import json
import os
import sys

import requests
from requests.auth import HTTPBasicAuth

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = "restaurants"


def load_env():
    env = {}
    with open(os.path.join(ROOT, ".env")) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


env = load_env()
ENDPOINT = env.get("OPENSEARCH_ENDPOINT", "").rstrip("/")
USER = env.get("OPENSEARCH_USER", "")
PASSWORD = env.get("OPENSEARCH_PASSWORD", "")
if not (ENDPOINT and USER and PASSWORD):
    sys.exit("Set OPENSEARCH_ENDPOINT, OPENSEARCH_USER, OPENSEARCH_PASSWORD in .env first.")
AUTH = HTTPBasicAuth(USER, PASSWORD)


def load_restaurants():
    for rel in ("data/yelp-restaurants.json", "scripts/restaurants.json"):
        path = os.path.join(ROOT, rel)
        if os.path.exists(path):
            print(f"Reading {rel}")
            with open(path) as f:
                return json.load(f)
    sys.exit("No restaurant data found (data/yelp-restaurants.json or scripts/restaurants.json).")


def create_index():
    mapping = {
        "mappings": {"properties": {
            "RestaurantID": {"type": "keyword"},
            "Cuisine": {"type": "keyword"},
            "type": {"type": "keyword"},
        }}
    }
    r = requests.head(f"{ENDPOINT}/{INDEX}", auth=AUTH, timeout=15)
    if r.status_code == 200:
        print(f"Index '{INDEX}' already exists; skipping create.")
        return
    r = requests.put(f"{ENDPOINT}/{INDEX}", json=mapping, auth=AUTH, timeout=15)
    r.raise_for_status()
    print(f"Created index '{INDEX}'.")


def bulk_load(items):
    lines = []
    for item in items:
        doc_id = item.get("BusinessID") or item.get("Business ID")
        cuisine = item.get("Cuisine")
        if not doc_id or not cuisine:
            continue
        lines.append(json.dumps({"index": {"_index": INDEX, "_id": doc_id}}))
        lines.append(json.dumps({"RestaurantID": doc_id, "Cuisine": cuisine, "type": "Restaurant"}))
    body = "\n".join(lines) + "\n"

    sent = errors = 0
    batch_size = 1000  # lines, i.e. 500 docs per request
    for i in range(0, len(lines), batch_size):
        chunk = "\n".join(lines[i:i + batch_size]) + "\n"
        r = requests.post(f"{ENDPOINT}/_bulk", data=chunk, auth=AUTH,
                          headers={"Content-Type": "application/x-ndjson"}, timeout=60)
        r.raise_for_status()
        resp = r.json()
        for item in resp["items"]:
            sent += 1
            if item["index"].get("error"):
                errors += 1
                print("  error:", item["index"]["error"])
    return sent, errors


if __name__ == "__main__":
    restaurants = load_restaurants()
    print(f"Loaded {len(restaurants)} restaurants from local file")
    create_index()
    sent, errors = bulk_load(restaurants)
    print(f"Indexed {sent} documents, {errors} errors")

    r = requests.get(f"{ENDPOINT}/{INDEX}/_count", auth=AUTH, timeout=15)
    print("Index doc count:", r.json().get("count"))
