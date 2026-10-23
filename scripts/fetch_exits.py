"""Fetch every numbered motorway exit in the US from OpenStreetMap.

One-time step, run before build_stations.py. Asks the Overpass API for each
state's exits (nodes tagged highway=motorway_junction with a ref, the exit
number) and writes data/osm_exits.csv. Public Overpass servers are often busy,
so each state is retried with a growing wait, and states already fetched are
kept in data/cache/ and skipped on the next run.

    python scripts/fetch_exits.py

OpenStreetMap data is ODbL, https://www.openstreetmap.org/copyright
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

from scripts.build_stations import US_STATES  # noqa: E402

SERVERS = ['https://overpass-api.de/api/interpreter',
           'https://overpass.private.coffee/api/interpreter']
USER_AGENT = 'spotter-fuel-route-api (one-time data build)'
CACHE = ROOT / 'data' / 'cache' / 'osm_exits'
OUTPUT = ROOT / 'data' / 'osm_exits.csv'
QUERY = '''[out:json][timeout:120];
area["ISO3166-2"="US-{state}"][admin_level=4]->.state;
node(area.state)[highway=motorway_junction][ref];
out;'''


def fetch(state):
    body = urllib.parse.urlencode({'data': QUERY.format(state=state)}).encode()
    for attempt in range(8):
        server = SERVERS[attempt % len(SERVERS)]
        try:
            request = urllib.request.Request(server, data=body, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.load(response)['elements']
        except Exception as error:  # busy servers answer 429/502/504, or time out
            wait = 10 * (attempt + 1)
            print(f'  {state}: {error}; retrying in {wait}s')
            time.sleep(wait)
    raise RuntimeError(f'Could not fetch exits for {state}')


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    rows = []
    for state in sorted(US_STATES - {'AK', 'HI'}):
        cached = CACHE / f'{state}.json'
        if not cached.exists():
            cached.write_text(json.dumps(fetch(state)))
            time.sleep(2)
        nodes = json.loads(cached.read_text())
        rows += [[state, n['tags']['ref'], f"{n['lat']:.5f}", f"{n['lon']:.5f}"] for n in nodes]
        print(f'{state}: {len(nodes)} exits')
    with open(OUTPUT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['state', 'ref', 'latitude', 'longitude'])
        writer.writerows(sorted(rows))
    print(f'Wrote {len(rows)} exits to {OUTPUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
