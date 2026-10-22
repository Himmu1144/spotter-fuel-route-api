"""Turning US place names into coordinates without calling an API.

The place list (data/us_places.csv.gz) is built once from GeoNames by
scripts/build_places.py. It is used offline to place the fuel stations, and at
request time to resolve the user's start and finish.
"""

import csv
import difflib
import gzip
import re
import unicodedata
from dataclasses import dataclass
from collections import defaultdict
from functools import cache
from pathlib import Path

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


STATES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California',
    'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware', 'DC': 'District of Columbia',
    'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois',
    'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana',
    'ME': 'Maine', 'MD': 'Maryland', 'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota',
    'MS': 'Mississippi', 'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
    'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
    'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma', 'OR': 'Oregon',
    'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina', 'SD': 'South Dakota',
    'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont', 'VA': 'Virginia',
    'WA': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming',
}
_STATE_CODES = {**{code.lower(): code for code in STATES},
                **{name.lower(): code for code, name in STATES.items()}}

# Rough boxes around the lower 48, Alaska and Hawaii, to reject coordinates outside the USA.
_US_BOXES = [(24.3, 49.5, -125.0, -66.8), (51.0, 71.5, -180.0, -129.0), (18.8, 22.4, -160.4, -154.7)]
_COORDINATES = re.compile(r'^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$')

PLACES_FILE = Path(__file__).resolve().parent.parent / 'data' / 'us_places.csv.gz'
FORMAT_HELP = 'Use a city and state, e.g. "Chicago, IL" or "Chicago, Illinois", or coordinates, e.g. "41.88,-87.63".'


class PlaceNotFound(ValueError):
    """The input isn't a US place we can resolve. The message says why and what to send instead."""


# How alike a misspelt name must be to a real one (0 to 1) to be corrected automatically.
TYPO_CUTOFF = 0.85


@dataclass(frozen=True)
class Location:
    name: str
    latitude: float
    longitude: float
    # Set when the input was read with a guess (a typo fixed, a missing state filled
    # in), so the caller can always see how it was read.
    note: str | None = None


@cache
def _places():
    """Load the place list once per process: {(normalized name, state): (name, lat, lon, population)}."""
    with gzip.open(PLACES_FILE, 'rt', encoding='utf-8') as f:
        return {(row['key'], row['state']): (row['name'], float(row['latitude']),
                                             float(row['longitude']), int(row['population']))
                for row in csv.DictReader(f)}


@cache
def _states_by_name():
    states = defaultdict(list)
    for key, state in _places():
        states[key].append(state)
    return states


@cache
def _names_by_state():
    names = defaultdict(list)
    for key, state in _places():
        names[state].append(key)
    return names


def _closest(key, code):
    """Names in the state that look like a misspelling of key, most alike (then most populous) first."""
    places = _places()
    matches = difflib.get_close_matches(key, _names_by_state()[code], n=5, cutoff=0.7)
    return sorted(matches, key=lambda m: (-difflib.SequenceMatcher(None, key, m).ratio(),
                                          -places[(m, code)][3]))


def in_usa(latitude, longitude):
    return any(south <= latitude <= north and west <= longitude <= east
               for south, north, west, east in _US_BOXES)


def resolve(text):
    """Turn "City, ST", "City, State name" or "lat,lon" into a Location in the USA."""
    text = (text or '').strip()
    if not text:
        raise PlaceNotFound(f'Location is empty. {FORMAT_HELP}')

    match = _COORDINATES.match(text)
    if match:
        latitude, longitude = float(match[1]), float(match[2])
        if not in_usa(latitude, longitude):
            hint = ' Latitude comes first.' if in_usa(longitude, latitude) else ''
            raise PlaceNotFound(f'"{text}" is not in the USA.{hint}')
        return Location(f'{latitude:.5f},{longitude:.5f}', latitude, longitude)

    city, comma, state = text.rpartition(',')
    if not comma:
        return _resolve_without_state(text)
    if not city.strip():
        raise PlaceNotFound(f'"{text}" has no city. {FORMAT_HELP}')
    state_text = ' '.join(state.split()).lower()
    code = _STATE_CODES.get(state_text)
    corrected = False
    if code is None and len(state_text) > 2:
        close = difflib.get_close_matches(state_text, _STATE_CODES, n=1, cutoff=TYPO_CUTOFF)
        code, corrected = (_STATE_CODES[close[0]], True) if close else (None, False)
    if code is None:
        raise PlaceNotFound(f'"{state.strip()}" is not a US state. {FORMAT_HELP}')
    key = normalize(city)
    place = _places().get((key, code))
    if place:
        name = f'{place[0]}, {code}'
        return Location(name, place[1], place[2], note=f'Read "{text}" as "{name}".' if corrected else None)

    candidates = _closest(key, code)
    if candidates and difflib.SequenceMatcher(None, key, candidates[0]).ratio() >= TYPO_CUTOFF:
        name, latitude, longitude, _ = _places()[(candidates[0], code)]
        return Location(f'{name}, {code}', latitude, longitude, note=f'Read "{text}" as "{name}, {code}".')
    names = dict.fromkeys(f'"{_places()[(c, code)][0]}, {code}"' for c in candidates)
    suggestions = ', '.join(list(names)[:3])
    hint = f' Did you mean {suggestions}?' if suggestions else ''
    raise PlaceNotFound(f'Could not find "{city.strip()}" in {STATES[code]}.{hint} {FORMAT_HELP}')


# A city named without its state is accepted only if it is far bigger than every other
# US place with that name: "Chicago" is Chicago, IL, but "Portland" could be OR or ME.
DOMINANT_RATIO = 20


def _resolve_without_state(text):
    """The format asks for a state; this is a convenience on top of it, never a guess."""
    key = normalize(text)
    states = _states_by_name().get(key, [])
    if not states:
        raise PlaceNotFound(f'"{text}" has no state. {FORMAT_HELP}')
    places = sorted(((_places()[(key, state)], state) for state in states), key=lambda p: -p[0][3])
    (name, latitude, longitude, population), code = places[0]
    runner_up = places[1][0][3] if len(places) > 1 else 0
    if population > 0 and population >= DOMINANT_RATIO * runner_up:
        return Location(f'{name}, {code}', latitude, longitude,
                        note=f'No state given; read "{text}" as "{name}, {code}".')
    options = '; '.join(f'{p[0]}, {state}' for p, state in places[:4])
    more = f' and {len(places) - 4} more' if len(places) > 4 else ''
    raise PlaceNotFound(f'There are several places called "{text}": {options}{more}. '
                        f'Add the state, e.g. "{places[0][0][0]}, {places[0][1]}". {FORMAT_HELP}')
