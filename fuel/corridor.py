"""Finding the fuel stations along a route, and how far along it each one is.

Two passes. First a cheap one in the database: the route is cut into stretches
of about BOX_MILES, each stretch gets a box padded by the corridor width, and
one query returns the stations inside any box (it uses the latitude/longitude
index). Then an exact one in Python on those candidates only: the distance from
each station to the route, and its mile marker, the route mile it sits beside.
"""

from collections import defaultdict
from dataclasses import dataclass
from functools import reduce
from operator import or_

from django.conf import settings
from django.db.models import Q

from .geo import degrees_for_miles, miles_between
from .models import FuelStation

# The route is thinned to a point about every half mile, so the nearest point is
# never more than a quarter mile from the true nearest spot on the road.
SAMPLE_MILES = 0.5
BOX_MILES = 50
# Grid cell for the exact pass. Wider than any corridor, so checking a station's
# own cell and the eight around it always finds its nearest route point.
CELL_DEGREES = 0.5


@dataclass(frozen=True)
class RouteStation:
    station: FuelStation
    mile: float             # where along the route the station sits
    off_route_miles: float  # straight-line distance from the station to the road


def sample(points):
    """Thin the route to a point about every SAMPLE_MILES, keeping the end. Returns [(point, mile)]."""
    kept, mile, next_mile = [], 0.0, 0.0
    for i, point in enumerate(points):
        if i:
            mile += miles_between(points[i - 1], point)
        if mile >= next_mile or i == len(points) - 1:
            kept.append((point, mile))
            next_mile = mile + SAMPLE_MILES
    return kept


def corridor_width(station):
    widths = settings.CORRIDOR_MILES
    return widths.get(station.placement, widths['town'])


def boxes(samples, pad_miles):
    """One box per stretch of about BOX_MILES, padded on every side."""
    stretch, start_mile = [], 0.0
    for point, mile in samples:
        stretch.append(point)
        if mile - start_mile >= BOX_MILES or (point, mile) == samples[-1]:
            lats, lons = [p[0] for p in stretch], [p[1] for p in stretch]
            lat_pad, lon_pad = degrees_for_miles(pad_miles, max(map(abs, lats)))
            yield (min(lats) - lat_pad, max(lats) + lat_pad, min(lons) - lon_pad, max(lons) + lon_pad)
            stretch, start_mile = [point], mile


def stations_along(route_points):
    """Stations within their corridor width of the route, ordered by mile marker."""
    samples = sample(route_points)
    pad = max(settings.CORRIDOR_MILES.values())
    in_boxes = reduce(or_, (Q(latitude__range=(s, n), longitude__range=(w, e))
                            for s, n, w, e in boxes(samples, pad)))
    candidates = FuelStation.objects.filter(in_boxes)

    grid = defaultdict(list)
    for point, mile in samples:
        grid[(int(point[0] // CELL_DEGREES), int(point[1] // CELL_DEGREES))].append((point, mile))

    found = []
    for station in candidates:
        position = (station.latitude, station.longitude)
        row, col = int(position[0] // CELL_DEGREES), int(position[1] // CELL_DEGREES)
        nearest = min(((miles_between(position, point), mile)
                       for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                       for point, mile in grid.get((row + dr, col + dc), ())), default=None)
        if nearest and nearest[0] <= corridor_width(station):
            found.append(RouteStation(station, mile=nearest[1], off_route_miles=nearest[0]))
    return sorted(found, key=lambda s: s.mile)
