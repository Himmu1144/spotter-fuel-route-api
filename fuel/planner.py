"""One trip plan, start to finish: places, route, stations along it, fuel stops.

The view only checks input and turns errors into status codes; everything else
happens here.
"""

import time

from django.conf import settings

from .corridor import stations_along
from .geo import simplify
from .optimizer import MAX_STOPS, RouteNotFeasible, plan_fuel
from .places import resolve
from .routing import get_route


class TripNotFeasible(Exception):
    """There is a stretch of the route longer than one tank with no station in it."""

    def __init__(self, message, gap):
        super().__init__(message)
        self.gap = gap


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
        raise TripNotFeasible(*_describe_gap(gap, along, start, finish)) from gap
    lap('fuel_plan')

    stops = []
    fuel_miles, here = float(settings.VEHICLE_RANGE_MILES), 0.0
    for order, purchase in enumerate(plan.purchases, start=1):
        found = along[purchase.index]
        station = found.station
        fuel_miles -= found.mile - here
        here = found.mile
        fuel_miles += purchase.gallons * settings.VEHICLE_MPG
        stops.append({
            'order': order,
            'name': station.name,
            'address': station.address,
            'city': station.city,
            'state': station.state,
            'mile': round(found.mile, 1),
            'off_route_miles': round(found.off_route_miles, 1),
            'price_per_gallon': round(float(station.price_per_gallon), 3),
            'price_basis': _price_basis(station),
            'gallons': round(purchase.gallons, 2),
            'cost_usd': round(purchase.cost, 2),
            'why': _why(order, plan.purchases, along, fuel_miles),
            'location_basis': _location_basis(station),
            'latitude': station.latitude,
            'longitude': station.longitude,
        })
    line = simplify(route.points)
    gallons_bought = sum(p.gallons for p in plan.purchases)
    gallons_used = route.distance_miles / settings.VEHICLE_MPG
    tank_price, tank_priced_at = _starting_tank_price(along)
    starting_tank_cost = max(gallons_used - gallons_bought, 0) * tank_price
    lap('response')

    summary_warning = ({'warning': f'The cheapest plan used all {MAX_STOPS} allowed stops; '
                                   f'a plan with more stops might cost slightly less.'}
                       if plan.stop_limit_reached else {})
    return {
        'start': _place(start_text, start),
        'finish': _place(finish_text, finish),
        'summary': {
            'distance_miles': round(route.distance_miles, 1),
            'drive_hours': round(route.duration_hours, 1),
            'mode': mode,
            'stops': len(stops),
            'plan': _plan_explanation(mode, plan, len(stops)),
            'stop_limit': MAX_STOPS,
            'fuel_bought_usd': round(plan.fuel_cost, 2),
            'trip_fuel_cost_usd': round(plan.fuel_cost + starting_tank_cost, 2),
            'gallons_bought': round(gallons_bought, 2),
            'gallons_used': round(gallons_used, 2),
            'assumptions': (
                f'{settings.VEHICLE_MPG:g} mpg and a {settings.VEHICLE_RANGE_MILES:.0f}-mile range. The vehicle '
                f'starts with a full tank: fuel_bought_usd is the fuel bought on the way; trip_fuel_cost_usd '
                f'also counts the starting tank, priced at {tank_priced_at}. Mileage is along the route; '
                f'off_route_miles is the straight-line distance from a station to the route; the road detour is not added.'),
            **summary_warning,
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
            'route_cached': route.cached,
            'route_points': {'from_router': len(route.points), 'returned': len(line)},
            'stations_considered': len(along),
            'timing_ms': timings,
        },
    }


def _place(text, location):
    place = {'input': text, 'resolved': location.name,
             'latitude': location.latitude, 'longitude': location.longitude}
    if location.note:
        place['note'] = location.note
    return place


def _price_basis(station):
    if station.listed_prices == 1:
        return 'the one price listed for this station'
    return (f'median of {station.listed_prices} prices listed for this station '
            f'(${station.lowest_price:.3f} to ${station.highest_price:.3f})')


def _why(order, purchases, along, fuel_after_miles):
    """One line on why this stop buys the amount it does."""
    if order == len(purchases):
        return 'Enough to reach the destination.'
    if fuel_after_miles >= settings.VEHICLE_RANGE_MILES - 1:
        return 'Filled the tank.'
    this = along[purchases[order - 1].index].station
    following = along[purchases[order].index]
    if following.station.price_per_gallon < this.price_per_gallon:
        return (f'Just enough to reach stop {order + 1}, {following.mile - along[purchases[order - 1].index].mile:.0f} '
                f'miles on, where fuel is cheaper (${following.station.price_per_gallon:.3f}).')
    return f'Enough to reach stop {order + 1}.'


def _location_basis(station):
    if station.placement == 'exit':
        return f'the highway exit named in its address ({station.address})'
    if station.placement == 'manual':
        return f'approximate: {station.city}, {station.state}, looked up by hand (the price list gives no exact location)'
    return f'approximate: the centre of {station.city}, {station.state} (the price list gives no exact location)'


def _starting_tank_price(along):
    """What the fuel already in the tank is worth: the price at the first listed station on the route."""
    if along:
        first = along[0].station
        return float(first.price_per_gallon), f'${first.price_per_gallon:.3f}, the first listed station on the route ({first.name}, {first.city}, {first.state})'
    median = float(settings.FALLBACK_PRICE_PER_GALLON)
    return median, f'${median:.3f}, the median price in the price list (no listed station on this route)'


def _plan_explanation(mode, plan, stops):
    if mode == 'cheapest':
        return f'cheapest: the lowest fuel cost with up to {MAX_STOPS} stops.'
    if stops == plan.cheapest_stops:
        return 'balanced: the fewest stops within 1% of the cheapest plan. Here that is also the cheapest plan.'
    return (f'balanced: the fewest stops within 1% of the cheapest plan. The cheapest plan costs '
            f'${plan.fuel_cost - plan.cheapest_cost:.2f} less but needs {plan.cheapest_stops} stops '
            f'(add mode=cheapest to get it).')


def _describe_gap(gap, along, start, finish):
    """A one-line explanation of the stretch with no listed station, and the same as data."""
    def name_at(mile):
        if mile == 0:
            return start.name
        for found in along:
            if abs(found.mile - mile) < 1e-6:
                s = found.station
                return f'{s.name} in {s.city}, {s.state} (mile {found.mile:.0f})'
        return f'{finish.name} (mile {mile:.0f})'

    miles = gap.to_mile - gap.from_mile
    message = (f'No fuel station in the price list between {name_at(gap.from_mile)} and '
               f'{name_at(gap.to_mile)}: {miles:.0f} miles, more than one '
               f'{settings.VEHICLE_RANGE_MILES:.0f}-mile tank. This trip can\'t be planned from this price list.')
    return message, {'from': name_at(gap.from_mile), 'to': name_at(gap.to_mile),
                     'from_mile': round(gap.from_mile, 1), 'to_mile': round(gap.to_mile, 1),
                     'miles': round(miles, 1)}
