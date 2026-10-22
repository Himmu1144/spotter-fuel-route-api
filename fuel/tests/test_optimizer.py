import itertools
import random

from django.test import SimpleTestCase

from fuel.optimizer import RouteNotFeasible, plan_fuel

TANK, MPG = 500, 10.0


def cost_with_stops_at(stops, total):
    """Cost of a trip that buys fuel at exactly these (mile, price) stops, buying the least it can.

    At each stop: buy just enough to reach the next cheaper stop (or the end), otherwise fill up.
    Returns None if the stops can't cover the trip, or if a stop would buy nothing.
    """
    points = [0, *(mile for mile, _ in stops), total]
    if any(b - a > TANK for a, b in zip(points, points[1:])):
        return None
    fuel, here, cost = TANK, 0, 0.0
    for i, (mile, price) in enumerate(stops):
        fuel -= mile - here
        here = mile
        target = TANK
        for later, later_price in [*stops[i + 1:], (total, 0.0)]:
            if later - mile > TANK:
                break
            if later_price < price:
                target = later - mile
                break
        bought = target - fuel
        if bought <= 0:
            return None
        cost += bought / MPG * price
        fuel += bought
    return cost


def brute_force(miles, prices, total):
    """Cheapest cost for every number of stops, by trying every set of stops."""
    stations = list(zip(miles, prices))
    best = {}
    for count in range(len(stations) + 1):
        for chosen in itertools.combinations(stations, count):
            cost = cost_with_stops_at(list(chosen), total)
            if cost is not None:
                best[count] = min(cost, best.get(count, cost))
    return best


class PlanFuelTests(SimpleTestCase):
    def test_short_trip_needs_no_stop(self):
        plan = plan_fuel([100, 300], [3.0, 3.0], 480)
        self.assertEqual((plan.purchases, plan.fuel_cost), ([], 0.0))

    def test_waits_for_the_cheaper_station(self):
        # Full tank reaches mile 500. Buying at the $3 station covers the rest more cheaply.
        plan = plan_fuel([100, 400], [4.0, 3.0], 900)
        self.assertEqual([(p.index, p.gallons) for p in plan.purchases], [(1, 40.0)])
        self.assertAlmostEqual(plan.fuel_cost, 120.0)

    def test_balanced_takes_one_stop_when_two_save_under_one_percent(self):
        # Cheapest: 10 gal at $3.00 then 40 gal at $2.99 = $149.60 over two stops.
        # One stop: 50 gal at $3.00 = $150.00, 0.27% more.
        miles, prices = [500, 600], [3.00, 2.99]
        cheapest = plan_fuel(miles, prices, 1000, mode='cheapest')
        balanced = plan_fuel(miles, prices, 1000)
        self.assertEqual((len(cheapest.purchases), round(cheapest.fuel_cost, 2)), (2, 149.60))
        self.assertEqual((len(balanced.purchases), round(balanced.fuel_cost, 2)), (1, 150.00))
        self.assertEqual((balanced.cheapest_stops, round(balanced.cheapest_cost, 2)), (2, 149.60))

    def test_gap_wider_than_a_tank(self):
        with self.assertRaises(RouteNotFeasible) as raised:
            plan_fuel([100, 700], [3.0, 3.0], 900)
        self.assertEqual((raised.exception.from_mile, raised.exception.to_mile), (100, 700))

    def test_matches_brute_force_on_random_trips(self):
        random.seed(7)
        for trial in range(300):
            total = random.randint(501, 1600)
            miles = sorted(random.sample(range(1, total), random.randint(1, 7)))
            prices = [round(random.uniform(3.0, 4.0), 3) for _ in miles]
            with self.subTest(trial=trial, miles=miles, prices=prices, total=total):
                best = brute_force(miles, prices, total)
                if not best:
                    with self.assertRaises(RouteNotFeasible):
                        plan_fuel(miles, prices, total)
                    continue
                cheapest = min(best.values())
                plan = plan_fuel(miles, prices, total, mode='cheapest')
                self.assertAlmostEqual(plan.fuel_cost, cheapest, places=6)
                fewest = min(k for k, cost in best.items() if cost <= cheapest * 1.01 + 1e-9)
                balanced = plan_fuel(miles, prices, total)
                self.assertEqual(len(balanced.purchases), fewest)
                self.assertAlmostEqual(balanced.fuel_cost, best[fewest], places=6)
                self.assertAlmostEqual(sum(p.cost for p in balanced.purchases), balanced.fuel_cost, places=6)
