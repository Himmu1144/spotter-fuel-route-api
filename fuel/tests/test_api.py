from unittest import mock

from django.test import TestCase

from fuel.routing import Route, RouteNotFound, RoutingUnavailable


def straight_route(start, finish, miles):
    """A fake OSRM answer: a straight line between the two places, with a given length."""
    steps = 200
    points = [(start.latitude + (finish.latitude - start.latitude) * i / steps,
               start.longitude + (finish.longitude - start.longitude) * i / steps) for i in range(steps + 1)]
    return Route(points=points, distance_miles=miles, duration_hours=miles / 60,
                 provider='https://osrm.example', calls=1)


class RouteApiTests(TestCase):
    # The stations are already in the test database: `migrate` loads them.

    def get(self, **params):
        return self.client.get('/api/route/', params, HTTP_ACCEPT='application/json')

    @mock.patch('fuel.planner.get_route', side_effect=lambda s, f: straight_route(s, f, 1004))
    def test_plans_a_trip(self, get_route):
        response = self.get(start='Chicago, IL', finish='Denver, CO')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['map_url'].startswith('http://testserver/map/?start=Chicago'))
        self.assertEqual(body['start']['resolved'], 'Chicago, IL')
        self.assertGreaterEqual(body['summary']['stops'], 1)
        summary = body['summary']
        self.assertAlmostEqual(sum(s['cost_usd'] for s in body['stops']), summary['fuel_bought_usd'], delta=0.05)
        self.assertGreater(summary['trip_fuel_cost_usd'], summary['fuel_bought_usd'])
        self.assertTrue(summary['plan'].startswith('balanced: the fewest stops within 1%'))
        first, last = body['stops'][0], body['stops'][-1]
        self.assertTrue(first['price_basis'].startswith(('the one price', 'median of')))
        self.assertTrue(first['location_basis'])
        self.assertEqual(last['why'], 'Enough to reach the destination.')
        self.assertEqual(body['meta']['external_calls'], 1)
        self.assertEqual([f['geometry']['type'] for f in body['map']['features']][0], 'LineString')
        get_route.assert_called_once()

    @mock.patch('fuel.planner.get_route', side_effect=lambda s, f: straight_route(s, f, 180))
    def test_reports_a_corrected_typo(self, get_route):
        body = self.get(start='Chicgo, IL', finish='Indianapolis, IN').json()
        self.assertEqual(body['start']['note'], 'Read "Chicgo, IL" as "Chicago, IL".')
        # No stops, but the trip still burns fuel: the starting tank is priced, so the total is never a confusing $0.
        self.assertEqual((body['summary']['stops'], body['summary']['fuel_bought_usd']), (0, 0))
        self.assertGreater(body['summary']['trip_fuel_cost_usd'], 50)

    def test_bad_input_is_a_400_that_says_why(self):
        cases = [({'finish': 'Denver, CO'}, 'invalid_input'),
                 ({'start': 'Chicago, IL', 'finish': 'Denver, CO', 'mode': 'fastest'}, 'invalid_input'),
                 ({'start': 'Springfield', 'finish': 'Denver, CO'}, 'place_not_found'),
                 ({'start': 'Xyzzy, CO', 'finish': 'Denver, CO'}, 'place_not_found')]
        for params, code in cases:
            with self.subTest(params=params):
                response = self.get(**params)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['error']['code'], code)

    @mock.patch('fuel.planner.get_route', side_effect=RouteNotFound('There is no driving route between these two places.'))
    def test_no_road_route_is_a_422(self, get_route):
        response = self.get(start='Honolulu, HI', finish='Denver, CO')
        self.assertEqual((response.status_code, response.json()['error']['code']), (422, 'no_route'))

    @mock.patch('fuel.planner.get_route', side_effect=lambda s, f: straight_route(s, f, 1300))
    def test_a_gap_longer_than_a_tank_is_a_422_naming_it(self, get_route):
        # The price list has no stations in central or northern California.
        response = self.get(start='Seattle, WA', finish='San Diego, CA')
        error = response.json()['error']
        self.assertEqual((response.status_code, error['code']), (422, 'no_fuel_in_range'))
        self.assertTrue(error['message'].startswith('No fuel station in the price list between'))
        self.assertGreater(error['gap']['miles'], 500)

    @mock.patch('fuel.planner.get_route', side_effect=RoutingUnavailable('The routing service is unavailable.'))
    def test_routing_down_is_a_502(self, get_route):
        response = self.get(start='Chicago, IL', finish='Denver, CO')
        self.assertEqual((response.status_code, response.json()['error']['code']), (502, 'routing_unavailable'))

    def test_map_page_loads(self):
        response = self.client.get('/map/?start=Chicago, IL&finish=Denver, CO')
        self.assertContains(response, 'leaflet')
