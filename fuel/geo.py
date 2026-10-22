import math

EARTH_RADIUS_MILES = 3958.8
MILES_PER_DEGREE_LATITUDE = 69.0


def miles_between(a, b):
    """Great-circle distance in miles between two (latitude, longitude) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(h))


def degrees_for_miles(miles, latitude):
    """How many degrees of (latitude, longitude) cover this many miles, near this latitude."""
    lat_degrees = miles / MILES_PER_DEGREE_LATITUDE
    return lat_degrees, lat_degrees / max(math.cos(math.radians(latitude)), 0.01)
