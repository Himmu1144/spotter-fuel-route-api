import math

import numpy as np

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


def simplify(points, tolerance_degrees=0.0005):
    """Drop points that barely change the line's shape (Douglas-Peucker).

    0.0005 degrees is about 50 metres: invisible on a map, but it cuts a
    coast-to-coast route from ~35,000 points to a few thousand.
    """
    if len(points) < 3:
        return list(points)
    line = np.asarray(points, dtype=float)
    keep = np.zeros(len(line), dtype=bool)
    keep[[0, -1]] = True
    stack = [(0, len(line) - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        start, end = line[first], line[last]
        segment = end - start
        between = line[first + 1:last] - start
        length = np.hypot(*segment)
        if length == 0:
            distances = np.hypot(between[:, 0], between[:, 1])
        else:
            distances = np.abs(segment[0] * between[:, 1] - segment[1] * between[:, 0]) / length
        farthest = int(np.argmax(distances))
        if distances[farthest] > tolerance_degrees:
            middle = first + 1 + farthest
            keep[middle] = True
            stack += [(first, middle), (middle, last)]
    return [tuple(point) for point in line[keep]]
