"""Scrape ~200 Manhattan restaurants per cuisine from the Yelp Fusion API.

Usage: .venv/bin/python other-scripts/scrape_yelp.py
Reads YELP_API_KEY from .env, writes other-scripts/restaurants.json (git-ignored cache).
Yelp's free tier allows 300 calls/day, so results are cached; re-run only to refresh.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "scripts", "restaurants.json")

# cuisine -> Yelp category alias. Must match the Lex CuisineType slot values.
CUISINES = {
    "chinese": "chinese",
    "japanese": "japanese",
    "italian": "italian",
    "mexican": "mexican",
    "indian": "indpak",
    "thai": "thai",
}
TARGET_PER_CUISINE = 200
PAGE = 50            # Yelp max per call
MAX_CALLS = 250      # stay under the 300/day quota
LOCATIONS = [        # broad query first, then neighborhoods to get past Yelp's per-query ranking
    ("Manhattan, NY", 4),
    ("Upper East Side, Manhattan, NY", 2), ("Upper West Side, Manhattan, NY", 2),
    ("Harlem, Manhattan, NY", 2), ("Midtown, Manhattan, NY", 2), ("Chelsea, Manhattan, NY", 2),
    ("Greenwich Village, Manhattan, NY", 2), ("East Village, Manhattan, NY", 2),
    ("SoHo, Manhattan, NY", 2), ("Financial District, Manhattan, NY", 2),
    ("Chinatown, Manhattan, NY", 2), ("Lower East Side, Manhattan, NY", 2),
    ("Hell's Kitchen, Manhattan, NY", 2), ("Washington Heights, Manhattan, NY", 2),
    ("Murray Hill, Manhattan, NY", 2), ("Tribeca, Manhattan, NY", 2), ("Gramercy, Manhattan, NY", 2),
]


def load_key():
    with open(os.path.join(ROOT, ".env")) as f:
        for line in f:
            if line.startswith("YELP_API_KEY="):
                return line.split("=", 1)[1].strip()
    sys.exit("YELP_API_KEY missing from .env")


KEY = load_key()
calls = 0


def search(cuisine, category, location, offset):
    global calls
    if calls >= MAX_CALLS:
        sys.exit(f"Stopping: reached {MAX_CALLS} API calls (daily quota guard).")
    params = urllib.parse.urlencode({
        "location": location, "term": f"{cuisine} restaurants", "categories": category,
        "limit": PAGE, "offset": offset, "sort_by": "best_match",
    })
    req = urllib.request.Request("https://api.yelp.com/v3/businesses/search?" + params,
                                 headers={"Authorization": f"Bearer {KEY}"})
    calls += 1
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r).get("businesses", [])
    except urllib.error.HTTPError as e:
        if e.code == 400:  # e.g. offset beyond available results
            return []
        sys.exit(f"Yelp error {e.code}: {e.read().decode()[:200]}")


def in_manhattan(biz):
    zip_code = (biz.get("location") or {}).get("zip_code") or ""
    return zip_code[:3] in ("100", "101", "102")


def to_item(biz, cuisine):
    loc = biz["location"]
    return {
        "BusinessID": biz["id"],
        "Name": biz["name"],
        "Address": ", ".join(loc.get("display_address") or [loc.get("address1", "")]),
        "Coordinates": {"latitude": biz["coordinates"]["latitude"], "longitude": biz["coordinates"]["longitude"]},
        "NumberOfReviews": biz.get("review_count", 0),
        "Rating": biz.get("rating"),
        "ZipCode": loc.get("zip_code"),
        "Cuisine": cuisine,
    }


seen = {}                       # BusinessID -> item (global de-dup)
seen_listings = set()           # (name, address): Yelp sometimes has duplicate listings with different ids
by_cuisine = {c: 0 for c in CUISINES}

for cuisine, category in CUISINES.items():
    for location, pages in LOCATIONS:
        if by_cuisine[cuisine] >= TARGET_PER_CUISINE:
            break
        for p in range(pages):
            if by_cuisine[cuisine] >= TARGET_PER_CUISINE:
                break
            results = search(cuisine, category, location, p * PAGE)
            for biz in results:
                if (biz["id"] in seen or not in_manhattan(biz) or not biz.get("coordinates", {}).get("latitude")
                        or by_cuisine[cuisine] >= TARGET_PER_CUISINE):
                    continue
                item = to_item(biz, cuisine)
                listing = (item["Name"], item["Address"])
                if listing in seen_listings:
                    continue
                seen_listings.add(listing)
                seen[biz["id"]] = item
                by_cuisine[cuisine] += 1
            time.sleep(0.2)
            if len(results) < PAGE:
                break
    print(f"{cuisine:9s} {by_cuisine[cuisine]:4d} restaurants   (API calls so far: {calls})", flush=True)

with open(OUT, "w") as f:
    json.dump(list(seen.values()), f, indent=1)
print(f"\nSaved {len(seen)} unique restaurants to {OUT}  ({calls} API calls)")
