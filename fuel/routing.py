"""The one external call: a driving route from OSRM.

OSRM's public servers need no key. They are run by volunteers with no uptime
promise, so if the first server fails the request is tried once on the next.
A normal request makes exactly one call, and a repeat of the same trip makes
none: routes are cached by their resolved start and finish. Only the route is
cached, not the fuel plan, so reloading station prices never serves a stale plan.
"""

from dataclasses import dataclass, replace

import requests
from django.conf import settings
from django.core.cache import cache

METERS_PER_MILE = 1609.344
USER_AGENT = 'spotter-fuel-route-api'


class RouteNotFound(Exception):
    """OSRM answered, but there is no road route between the two points."""


class RoutingUnavailable(Exception):
    """No routing server could be reached."""


@dataclass(frozen=True)
class Route:
    points: list  # [(latitude, longitude), ...] along the road
    distance_miles: float
    duration_hours: float
    provider: str
    calls: int
    cached: bool = False


def get_route(start, finish):
    """Route between two Locations, from the cache if this trip was routed recently."""
    key = (f'route:{start.latitude:.5f},{start.longitude:.5f}:'
           f'{finish.latitude:.5f},{finish.longitude:.5f}')
    route = cache.get(key)
    if route is not None:
        return replace(route, calls=0, cached=True)
    route = _fetch_route(start, finish)
    cache.set(key, route, settings.ROUTE_CACHE_SECONDS)
    return route


def _fetch_route(start, finish):
    """Ask OSRM, trying each server in OSRM_SERVERS until one answers."""
    path = f'route/v1/driving/{start.longitude},{start.latitude};{finish.longitude},{finish.latitude}'
    params = {'overview': 'full', 'geometries': 'polyline6', 'steps': 'false'}
    failures = []
    for calls, server in enumerate(settings.OSRM_SERVERS, start=1):
        try:
            response = requests.get(f'{server.rstrip("/")}/{path}', params=params,
                                    headers={'User-Agent': USER_AGENT}, timeout=(5, 20))
            body = response.json()
        except (requests.RequestException, ValueError) as error:
            failures.append(f'{server}: {error.__class__.__name__}')
            continue
        if body.get('code') == 'Ok':
            route = body['routes'][0]
            return Route(points=decode_polyline(route['geometry']),
                         distance_miles=route['distance'] / METERS_PER_MILE,
                         duration_hours=route['duration'] / 3600,
                         provider=server, calls=calls)
        if body.get('code') in ('NoRoute', 'NoSegment'):
            # A real answer, not an outage: another server would say the same.
            raise RouteNotFound('There is no driving route between these two places.')
        failures.append(f'{server}: {body.get("code") or response.status_code}')
    raise RoutingUnavailable('The routing service is unavailable. Tried: ' + '; '.join(failures))


def decode_polyline(encoded, precision=6):
    """Decode Google's encoded polyline format, which OSRM uses to send the route compactly."""
    points, index, latitude, longitude = [], 0, 0, 0
    factor = 10 ** precision
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        latitude += deltas[0]
        longitude += deltas[1]
        points.append((latitude / factor, longitude / factor))
    return points
