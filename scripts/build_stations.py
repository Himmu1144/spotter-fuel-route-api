"""Build data/stations.csv: the price file cleaned and placed on the map.

One-time step, run after build_places.py. Reads the price file as provided and:
  1. trims stray spaces and drops rows outside the 50 states and DC,
  2. keeps one row per OPIS station ID, at the median of its listed prices,
  3. places each station at its town's centre using the offline place list,
     or a hand-checked fix from data/place_fixes.csv for towns the list lacks,
  4. moves it to the real highway exit when the address names one ("I-44, EXIT
     283") and OpenStreetMap has that exit number near the town (see
     fetch_exits.py). Town centres can be several miles off the highway.
The output is committed and loaded with `python manage.py load_stations`.

    python scripts/build_stations.py
"""

import csv
import statistics
import gzip
import math
import re
import sys
from collections import defaultdict
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fuel.places import normalize  # noqa: E402

DATA = ROOT / 'data'
PRICE_FILE = DATA / 'raw' / 'fuel-prices-for-be-assessment.csv'
PLACES = DATA / 'us_places.csv.gz'
FIXES = DATA / 'place_fixes.csv'
EXITS = DATA / 'osm_exits.csv'
OUTPUT = DATA / 'stations.csv'

# An exit further than this from the station's town is taken to be a different exit
# with the same number, so the station stays at the town centre.
MAX_EXIT_MILES = 15
EXIT_IN_ADDRESS = re.compile(r'\bEX(?:IT|T)?\.?[\s,#]*(\d+\s*-?\s*[A-Z]?)\b', re.IGNORECASE)

US_STATES = set(
    'AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV '
    'NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split()
)
FIELDS = ['opis_id', 'name', 'address', 'city', 'state', 'rack_id', 'price_per_gallon',
          'listed_prices', 'lowest_price', 'highest_price', 'latitude', 'longitude', 'placement']


def read_prices(path=PRICE_FILE, report=print):
    """One cleaned row per station ID, priced at the median of the prices the file lists for it.

    Some stations appear several times with different prices and no dates. The lowest
    would favour stations listed more often (more chances to look cheap); the median
    treats every station the same and ignores a single odd value.
    """
    stations, prices, rows, foreign = {}, {}, 0, Counter()
    with open(path, encoding='utf-8-sig', newline='') as f:
        for raw in csv.DictReader(f):
            rows += 1
            row = {key: value.strip() for key, value in raw.items()}
            if row['State'] not in US_STATES:
                foreign[row['State']] += 1
                continue
            station = {
                'opis_id': int(row['OPIS Truckstop ID']),
                'name': row['Truckstop Name'],
                'address': row['Address'],
                'city': row['City'],
                'state': row['State'],
                'rack_id': int(row['Rack ID']),
                'price_per_gallon': Decimal(row['Retail Price']),
            }
            stations.setdefault(station['opis_id'], station)
            prices.setdefault(station['opis_id'], []).append(station['price_per_gallon'])
    for opis_id, station in stations.items():
        station['price_per_gallon'] = statistics.median(prices[opis_id])
        station['listed_prices'] = len(prices[opis_id])
        station['lowest_price'], station['highest_price'] = min(prices[opis_id]), max(prices[opis_id])
    report(f'{rows} rows read; {sum(foreign.values())} outside the US dropped ({", ".join(sorted(foreign))})')
    report(f'{len(stations)} US stations after keeping one row per ID')
    return stations


def read_places():
    with gzip.open(PLACES, 'rt', encoding='utf-8') as f:
        return {(r['key'], r['state']): (float(r['latitude']), float(r['longitude']))
                for r in csv.DictReader(f)}


def read_fixes():
    if not FIXES.exists():
        return {}
    with open(FIXES, encoding='utf-8', newline='') as f:
        return {(normalize(r['city']), r['state']): (float(r['latitude']), float(r['longitude']))
                for r in csv.DictReader(f)}


def exit_key(ref):
    """'144-B', '144 B' and '144b' are the same exit."""
    return re.sub(r'[^0-9A-Z]', '', ref.upper())


def read_exits():
    """Exits by state and exit number. Some OSM exits carry several numbers, e.g. '283;284'."""
    exits = defaultdict(list)
    if not EXITS.exists():
        return exits
    with open(EXITS, encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            for ref in re.split(r'[;/]', row['ref']):
                exits[(row['state'], exit_key(ref))].append(
                    (float(row['latitude']), float(row['longitude'])))
    return exits


def miles_between(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def find_exit(station, exits):
    """The named exit closest to the station's town, if it is close enough to be the right one."""
    match = EXIT_IN_ADDRESS.search(station['address'])
    if not match:
        return None
    key = exit_key(match.group(1))
    candidates = exits.get((station['state'], key)) or exits.get((station['state'], key.rstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZ')), [])
    town = (station['latitude'], station['longitude'])
    nearby = [(miles_between(town, point), point) for point in candidates]
    nearby = [item for item in nearby if item[0] <= MAX_EXIT_MILES]
    return min(nearby)[1] if nearby else None


def main():
    stations = read_prices()
    places, fixes, exits = read_places(), read_fixes(), read_exits()
    placed, missing = [], Counter()
    for station in stations.values():
        key = (normalize(station['city']), station['state'])
        if key in places:
            station['latitude'], station['longitude'] = places[key]
            station['placement'] = 'town'
        elif key in fixes:
            station['latitude'], station['longitude'] = fixes[key]
            station['placement'] = 'manual'
        else:
            missing[(station['city'], station['state'])] += 1
            continue
        exit_point = find_exit(station, exits)
        if exit_point:
            station['latitude'], station['longitude'] = exit_point
            station['placement'] = 'exit'
        placed.append(station)

    placed.sort(key=lambda s: s['opis_id'])
    with open(OUTPUT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(placed)

    print(f'Placed {len(placed)}: {dict(Counter(s["placement"] for s in placed))}')
    if missing:
        print(f'Not placed, {sum(missing.values())} stations in {len(missing)} towns:')
        for (city, state), count in sorted(missing.items()):
            print(f'  {city}, {state} ({count})')


if __name__ == '__main__':
    main()
