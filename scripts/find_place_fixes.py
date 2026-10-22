"""Look up the towns the place list lacks, once, and save them to data/place_fixes.csv.

One-time step, run when build_stations.py reports stations it could not place.
Asks OpenStreetMap's Nominatim geocoder, one request per second as its usage
policy requires. Every result should be checked by eye before committing.

    python scripts/find_place_fixes.py
"""

import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fuel.places import normalize  # noqa: E402
from scripts.build_stations import FIXES, read_fixes, read_places, read_prices  # noqa: E402

NOMINATIM = 'https://nominatim.openstreetmap.org/search'
USER_AGENT = 'spotter-fuel-route-api (one-time data build)'


def lookup(city, state):
    query = urllib.parse.urlencode(
        {'city': city, 'state': state, 'country': 'US', 'format': 'json', 'limit': 1})
    request = urllib.request.Request(f'{NOMINATIM}?{query}', headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        results = json.load(response)
    return (float(results[0]['lat']), float(results[0]['lon']), results[0]['display_name']) if results else None


def main():
    places, fixes = read_places(), read_fixes()
    towns = sorted({(s['city'], s['state']) for s in read_prices().values()
                    if (normalize(s['city']), s['state']) not in places | fixes.keys()})
    rows = []
    if FIXES.exists():
        with open(FIXES, encoding='utf-8', newline='') as f:
            rows = list(csv.DictReader(f))
    for city, state in towns:
        found = lookup(city, state)
        print(f'{city}, {state}: {found if found else "NOT FOUND"}')
        if found:
            rows.append({'city': city, 'state': state, 'latitude': f'{found[0]:.5f}',
                         'longitude': f'{found[1]:.5f}', 'source': f'Nominatim: {found[2]}'})
        time.sleep(1)
    with open(FIXES, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['city', 'state', 'latitude', 'longitude', 'source'])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == '__main__':
    main()
