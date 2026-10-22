"""Build data/us_places.csv.gz, the offline list of US places.

One-time step. Downloads the GeoNames US dump (about 70 MB), keeps populated
places only, and writes one row per (name, state), keeping the most populous
place when a state has several with the same name. Cities of 50,000+ people are
also listed under their common alternate names ("New York" for New York City),
but never in place of a town that really has that name. The output is committed, so
running the app never needs GeoNames.

    python scripts/build_places.py

GeoNames data is CC BY 4.0, https://www.geonames.org/
"""

import csv
import gzip
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fuel.places import normalize  # noqa: E402

GEONAMES_URL = 'https://download.geonames.org/export/dump/US.zip'
CACHE = ROOT / 'data' / 'cache' / 'US.zip'
OUTPUT = ROOT / 'data' / 'us_places.csv.gz'

# Columns in the GeoNames dump, see https://download.geonames.org/export/dump/readme.txt
NAME, ASCII_NAME, ALTERNATE_NAMES, LAT, LON, FEATURE_CLASS, STATE, POPULATION = 1, 2, 3, 4, 5, 6, 10, 14
ALIAS_MIN_POPULATION = 50_000


def download():
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        print(f'Downloading {GEONAMES_URL}')
        urllib.request.urlretrieve(GEONAMES_URL, CACHE)
    with zipfile.ZipFile(CACHE) as archive:
        return io.TextIOWrapper(archive.open('US.txt'), encoding='utf-8')


def main():
    places, aliases = {}, {}
    for line in download():
        row = line.rstrip('\n').split('\t')
        if row[FEATURE_CLASS] != 'P':  # P = populated place: city, town, village
            continue
        population = int(row[POPULATION] or 0)
        place = (row[NAME], float(row[LAT]), float(row[LON]), population)
        for name in {row[NAME], row[ASCII_NAME]}:
            key = (normalize(name), row[STATE])
            if key not in places or population > places[key][3]:
                places[key] = place
        if population >= ALIAS_MIN_POPULATION:
            for name in row[ALTERNATE_NAMES].split(','):
                if name.isascii() and name.strip():
                    key = (normalize(name), row[STATE])
                    if key not in aliases or population > aliases[key][3]:
                        aliases[key] = place
    for key, place in aliases.items():
        places.setdefault(key, place)

    with gzip.open(OUTPUT, 'wt', newline='', encoding='utf-8') as out:
        writer = csv.writer(out)
        writer.writerow(['key', 'state', 'name', 'latitude', 'longitude', 'population'])
        for (key, state), (name, lat, lon, population) in sorted(places.items()):
            writer.writerow([key, state, name, f'{lat:.5f}', f'{lon:.5f}', population])
    print(f'Wrote {len(places)} places to {OUTPUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
