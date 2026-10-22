"""Build data/stations.csv: the price file cleaned and placed on the map.

One-time step, run after build_places.py. Reads the price file as provided and:
  1. trims stray spaces and drops rows outside the 50 states and DC,
  2. keeps one row per OPIS station ID, at its lowest listed price,
  3. places each station at its town's centre using the offline place list,
     or a hand-checked fix from data/place_fixes.csv for towns the list lacks.
The output is committed and loaded with `python manage.py load_stations`.

    python scripts/build_stations.py
"""

import csv
import gzip
import sys
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
OUTPUT = DATA / 'stations.csv'

US_STATES = set(
    'AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV '
    'NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split()
)
FIELDS = ['opis_id', 'name', 'address', 'city', 'state', 'rack_id', 'price_per_gallon',
          'latitude', 'longitude', 'placement']


def read_prices(path=PRICE_FILE, report=print):
    """One cleaned row per station ID, at the lowest price the file lists for it."""
    stations, rows, foreign = {}, 0, Counter()
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
            kept = stations.get(station['opis_id'])
            if kept is None or station['price_per_gallon'] < kept['price_per_gallon']:
                stations[station['opis_id']] = station
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


def main():
    stations = read_prices()
    places, fixes = read_places(), read_fixes()
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
