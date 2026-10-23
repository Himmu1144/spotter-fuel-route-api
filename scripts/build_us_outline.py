"""Build data/us_outline.json.gz, the US border used to check coordinates are in the USA.

One-time step. Downloads the US Census Bureau's nation boundary (cartographic
boundary file, 1:5,000,000) and keeps each polygon's outer ring and holes as
(longitude, latitude) lists. The output is committed. Public domain data.

    python scripts/build_us_outline.py
"""

import gzip
import io
import json
import urllib.request
import xml.etree.ElementTree as ElementTree
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = 'https://www2.census.gov/geo/tiger/GENZ2024/kml/cb_2024_us_nation_5m.zip'
OUTPUT = ROOT / 'data' / 'us_outline.json.gz'
KML = '{http://www.opengis.net/kml/2.2}'


def ring(element):
    text = element.find(f'.//{KML}coordinates').text
    return [[round(float(lon), 5), round(float(lat), 5)]
            for lon, lat, *_ in (point.split(',') for point in text.split())]


def main():
    with urllib.request.urlopen(SOURCE, timeout=60) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    kml_name = next(name for name in archive.namelist() if name.endswith('.kml'))
    root = ElementTree.fromstring(archive.read(kml_name))
    polygons = [
        {'outer': ring(polygon.find(f'{KML}outerBoundaryIs')),
         'holes': [ring(hole) for hole in polygon.findall(f'{KML}innerBoundaryIs')]}
        for polygon in root.iter(f'{KML}Polygon')
    ]
    with gzip.open(OUTPUT, 'wt', encoding='utf-8') as f:
        json.dump(polygons, f, separators=(',', ':'))
    points = sum(len(p['outer']) + sum(map(len, p['holes'])) for p in polygons)
    print(f'Wrote {len(polygons)} polygons, {points} points, to {OUTPUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
