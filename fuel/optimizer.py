"""Choosing where to buy fuel along a fixed route. Pure computation: no Django, no I/O.

The question it answers: for every possible number of stops, what is the
cheapest way to finish the trip? It walks the route station by station, keeping
a table of the cheapest way to be at that station for every fuel level and
every number of stops made so far. At each station there are only two choices:
drive past, or buy some fuel (any amount, which counts as a stop). This is
dynamic programming, done on whole numpy arrays so a coast-to-coast route with
~450 stations takes tens of milliseconds.

Fuel is counted in miles of driving (one unit = 1/mpg gallons) and station
positions are rounded to the nearest mile. Rounding positions, rather than the
gaps between them, keeps the error from adding up along the route.

From the cost-by-stops table it picks a plan:
  cheapest  the lowest cost, however many stops that takes,
  balanced  the fewest stops whose cost is within TOLERANCE of the cheapest.
"""

from dataclasses import dataclass

import numpy as np

TOLERANCE = 0.01
MAX_STOPS = 30


class RouteNotFeasible(Exception):
    """Some stretch of the route is longer than one tank and has no station in it."""

    def __init__(self, from_mile, to_mile):
        self.from_mile, self.to_mile = from_mile, to_mile
        super().__init__(f'No fuel station between mile {from_mile:.0f} and mile {to_mile:.0f}.')


@dataclass(frozen=True)
class Purchase:
    index: int      # which of the input stations
    gallons: float
    cost: float


@dataclass(frozen=True)
class FuelPlan:
    purchases: list
    fuel_cost: float
    cheapest_cost: float
    cheapest_stops: int


def plan_fuel(miles, prices, total_miles, *, range_miles=500, mpg=10.0,
              mode='balanced', tolerance=TOLERANCE, max_stops=MAX_STOPS):
    """Plan the stops for a trip that starts with a full tank.

    miles: each station's position along the route, in increasing order.
    prices: each station's price per gallon.
    """
    tank = int(range_miles)
    positions = [round(m) for m in miles]
    end = round(total_miles)
    if end <= tank:
        return FuelPlan([], 0.0, 0.0, 0)
    _check_gaps([0, *positions, end], [0.0, *miles, total_miles], tank)

    stops = min(max_stops, len(positions))
    fuel = np.arange(tank + 1)
    # cost[k, g]: cheapest way to be here having made k stops, with g miles of fuel in the tank.
    cost = np.full((stops + 1, tank + 1), np.inf)
    cost[0, tank] = 0.0
    previous, choices = 0, []
    for position, price in zip(positions, prices):
        cost = _drive(cost, position - previous)
        previous = position
        # Buying up to g from h < g costs (g - h) * per_mile, and adds a stop.
        # min over h < g of cost[k-1, h] + (g - h) * per_mile
        #   = g * per_mile + (running minimum of cost[k-1, h] - h * per_mile).
        per_mile = price / mpg
        shifted = cost - fuel * per_mile
        running_min = np.minimum.accumulate(shifted, axis=1)
        where_min = np.maximum.accumulate(np.where(shifted == running_min, fuel, 0), axis=1)
        bought = np.full_like(cost, np.inf)
        bought[1:, 1:] = running_min[:-1, :-1] + fuel[1:] * per_mile
        buy = bought < cost
        # For each state reached by buying, remember the fuel level it was bought from.
        came_from = np.full(cost.shape, -1, dtype=np.int16)
        came_from[1:, 1:] = np.where(buy[1:, 1:], where_min[:-1, :-1], -1)
        choices.append(came_from)
        cost = np.minimum(cost, bought)

    last_leg = end - previous
    by_stops = cost[:, last_leg:].min(axis=1)
    cheapest = float(by_stops.min())
    if mode == 'cheapest':
        chosen = int(np.argmin(by_stops))
    else:
        chosen = int(np.argmax(by_stops <= cheapest * (1 + tolerance) + 1e-9))

    purchases = _trace_back(choices, positions, cost, chosen, last_leg, prices, mpg)
    return FuelPlan(purchases, float(by_stops[chosen]), cheapest, int(np.argmin(by_stops)))


def _check_gaps(rounded, exact, tank):
    for i in range(len(rounded) - 1):
        if rounded[i + 1] - rounded[i] > tank:
            raise RouteNotFeasible(exact[i], exact[i + 1])


def _drive(cost, miles):
    """Every fuel level drops by the miles driven; levels that can't make it disappear."""
    if miles == 0:
        return cost
    moved = np.full_like(cost, np.inf)
    moved[:, :-miles] = cost[:, miles:]
    return moved


def _trace_back(choices, positions, final_cost, stops, last_leg, prices, mpg):
    """Walk backwards from the destination to recover where fuel was bought, and how much."""
    fuel = last_leg + int(np.argmin(final_cost[stops, last_leg:]))
    purchases = []
    for index in range(len(positions) - 1, -1, -1):
        bought_from = choices[index][stops, fuel]
        if bought_from >= 0:
            gallons = (fuel - bought_from) / mpg
            purchases.append(Purchase(index, gallons, gallons * prices[index]))
            fuel, stops = int(bought_from), stops - 1
        if index:
            fuel += positions[index] - positions[index - 1]
    return purchases[::-1]
