"""One trip plan, start to finish: places, route, stations along it, fuel stops.

The view only checks input and turns errors into status codes; everything else
happens here.
"""

import time

from django.conf import settings

from .corridor import stations_along
from .geo import simplify
from .optimizer import RouteNotFeasible, plan_fuel
from .places import resolve
from .routing import get_route


class TripNotFeasible(Exception):
    """There is a stretch of the route longer than one tank with no station in it."""


def plan_trip(start_text, finish_text, mode='balanced'):
    timings, clock = {}, time.perf_counter()

    def lap(name):
        nonlocal clock
        now = time.perf_counter()
        timings[name] = round((now - clock) * 1000, 1)
        clock = now

    start, finish = resolve(start_text), resolve(finish_text)
    lap('places')
    route = get_route(start, finish)
    lap('routing')
    along = stations_along(route.points)
    lap('stations')
    try:
        plan = plan_fuel([s.mile for s in along], [float(s.station.price_per_gallon) for s in along],
                         route.distance_miles, range_miles=settings.VEHICLE_RANGE_MILES,
                         mpg=settings.VEHICLE_MPG, mode=mode)
    except RouteNotFeasible as gap:
        raise TripNotFeasible(_describe_gap(gap, along, start, finish)) from gap
    lap('fuel_plan')

    stops = []
    for order, purchase in enumerate(plan.purchases, start=1):
        found = along[purchase.index]
        station = found.station
        stops.append({
            'order': order,
            'name': station.name,
            'address': station.address,
            'city': station.city,
            'state': station.state,
            'mile': round(found.mile, 1),
            'off_route_miles': round(found.off_route_miles, 1),
            'price_per_gallon': round(float(station.price_per_gallon), 3),
            'gallons': round(purchase.gallons, 2),
            'cost_usd': round(purchase.cost, 2),
            'latitude': station.latitude,
            'longitude': station.longitude,
        })
    line = simplify(route.points)
    lap('response')

    return {
        'start': _place(start_text, start),
        'finish': _place(finish_text, finish),
        'summary': {
            'distance_miles': round(route.distance_miles, 1),
            'drive_hours': round(route.duration_hours, 1),
            'mode': mode,
            'stops': len(stops),
            'fuel_cost_usd': round(plan.fuel_cost, 2),
            'gallons_bought': round(sum(p.gallons for p in plan.purchases), 2),
            'gallons_used': round(route.distance_miles / settings.VEHICLE_MPG, 2),
            'assumptions': (f'Starts with a full tank ({settings.VEHICLE_RANGE_MILES:.0f}-mile range) '
                            f'at {settings.VEHICLE_MPG:g} mpg; fuel_cost_usd is the fuel bought on the way.'),
        },
        'compared_to_cheapest': {
            'cheapest_cost_usd': round(plan.cheapest_cost, 2),
            'cheapest_stops': plan.cheapest_stops,
            'extra_cost_usd': round(plan.fuel_cost - plan.cheapest_cost, 2),
        },
        'stops': stops,
        'map': {
            'type': 'FeatureCollection',
            'features': [
                {'type': 'Feature', 'properties': {'kind': 'route'},
                 'geometry': {'type': 'LineString',
                              'coordinates': [[round(lon, 5), round(lat, 5)] for lat, lon in line]}},
                *({'type': 'Feature',
                   'properties': {'kind': 'fuel_stop', 'order': s['order'], 'name': s['name'],
                                  'price_per_gallon': s['price_per_gallon'], 'gallons': s['gallons']},
                   'geometry': {'type': 'Point', 'coordinates': [s['longitude'], s['latitude']]}}
                  for s in stops),
            ],
        },
        'meta': {
            'routing_provider': route.provider,
            'external_calls': route.calls,
            'route_points': {'from_router': len(route.points), 'returned': len(line)},
            'stations_considered': len(along),
            'timing_ms': timings,
        },
    }


def _place(text, location):
    place = {'input': text, 'resolved': location.name,
             'latitude': location.latitude, 'longitude': location.longitude}
    if location.corrected_from:
        place['note'] = f'Read "{location.corrected_from}" as "{location.name}".'
    return place


def _describe_gap(gap, along, start, finish):
    def name_at(mile):
        if mile == 0:
            return f'the start ({start.name})'
        for found in along:
            if abs(found.mile - mile) < 1e-6:
                s = found.station
                return f'{s.name} in {s.city}, {s.state} (mile {found.mile:.0f})'
        return f'the destination ({finish.name}, mile {mile:.0f})'

    return (f'This trip needs a fuel stop the price list can\'t provide: there is no station between '
            f'{name_at(gap.from_mile)} and {name_at(gap.to_mile)}, which is more than '
            f'{settings.VEHICLE_RANGE_MILES:.0f} miles.')
