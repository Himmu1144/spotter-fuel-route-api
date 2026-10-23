import itertools
import random

from django.test import SimpleTestCase

from fuel.optimizer import RESERVE_MILES, RouteNotFeasible, plan_fuel

# Plans keep a one-mile reserve, so the usable tank is 499 miles.
TANK, MPG = 500 - RESERVE_MILES, 10.0


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
        # Arrive at the $3 station (mile 400) with 99 miles left; 39.1 gal there reaches mile 890.
        # Buying at the $4 station instead would only cost more.
        plan = plan_fuel([100, 400], [4.0, 3.0], 890)
        self.assertEqual([(p.index, round(p.gallons, 2)) for p in plan.purchases], [(1, 39.1)])
        self.assertAlmostEqual(plan.fuel_cost, 117.30)

    def test_balanced_takes_one_stop_when_two_save_under_one_percent(self):
        # Cheapest: 0.1 gal at $3.00 (mile 400) to reach mile 500, then 39 gal at $2.99 = $116.91.
        # One stop: 39.1 gal at $3.00 = $117.30, 0.33% more.
        miles, prices = [400, 500], [3.00, 2.99]
        cheapest = plan_fuel(miles, prices, 890, mode='cheapest')
        balanced = plan_fuel(miles, prices, 890)
        self.assertEqual((len(cheapest.purchases), round(cheapest.fuel_cost, 2)), (2, 116.91))
        self.assertEqual((len(balanced.purchases), round(balanced.fuel_cost, 2)), (1, 117.30))
        self.assertEqual((balanced.cheapest_stops, round(balanced.cheapest_cost, 2)), (2, 116.91))

    def test_keeps_a_one_mile_reserve_so_rounding_never_stretches_the_range(self):
        self.assertEqual(plan_fuel([], [], 499.4).purchases, [])
        with self.assertRaises(RouteNotFeasible):
            plan_fuel([], [], 500.0)

    def test_says_when_the_stop_limit_was_reached(self):
        # Ever-cheaper stations every 10 miles: the cheapest plan would stop at each one.
        miles = list(range(100, 600, 10))
        prices = [4.0 - i * 0.01 for i in range(len(miles))]
        limited = plan_fuel(miles, prices, 900, mode='cheapest', max_stops=5)
        self.assertEqual(len(limited.purchases), 5)
        self.assertTrue(limited.stop_limit_reached)
        self.assertFalse(plan_fuel(miles, prices, 900, mode='cheapest').stop_limit_reached)

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
