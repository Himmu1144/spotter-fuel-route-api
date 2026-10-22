"""Turning US place names into coordinates without calling an API.

The place list (data/us_places.csv.gz) is built once from GeoNames by
scripts/build_places.py. It is used offline to place the fuel stations, and at
request time to resolve the user's start and finish.
"""

import re
import unicodedata

# Spelled-out forms, so "St. Louis", "Saint Louis" and "ST LOUIS" all match.
_PREFIXES = {
    'st': 'saint', 'ste': 'sainte', 'ft': 'fort', 'mt': 'mount',
    'n': 'north', 's': 'south', 'e': 'east', 'w': 'west',
}


def normalize(name):
    """Reduce a place name to a key that survives case, accents and punctuation."""
    text = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()
    text = text.replace("'", '')
    words = re.sub(r'[^a-z0-9]+', ' ', text).split()
    if words and words[0] in _PREFIXES:
        words[0] = _PREFIXES[words[0]]
    # "Mc Calla" and "McCalla", "De Forest" and "DeForest" are the same town.
    if len(words) > 1 and words[0] in ('mc', 'de', 'la', 'du'):
        words[:2] = [words[0] + words[1]]
    return ' '.join(words)
