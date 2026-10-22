from unittest import mock

import requests
from django.test import SimpleTestCase, override_settings

from fuel.places import Location
from fuel.routing import RouteNotFound, RoutingUnavailable, decode_polyline, get_route

START = Location('Chicago, IL', 41.85, -87.65)
FINISH = Location('Denver, CO', 39.74, -104.98)
SERVERS = ['https://first.example', 'https://second.example']
# Two points, (38.5, -120.2) and (40.7, -120.95), in polyline6 encoding.
GEOMETRY = '_izlhA~rlgdF_{geC~ywl@'


def osrm_reply(body):
    reply = mock.Mock()
    reply.json.return_value = body
    return reply


OK = osrm_reply({'code': 'Ok', 'routes': [{'geometry': GEOMETRY, 'distance': 160934.4, 'duration': 7200}]})


@override_settings(OSRM_SERVERS=SERVERS)
class GetRouteTests(SimpleTestCase):
    @mock.patch('fuel.routing.requests.get', return_value=OK)
    def test_one_call_when_the_first_server_answers(self, get):
        route = get_route(START, FINISH)
        self.assertEqual(get.call_count, 1)
        self.assertEqual((route.calls, route.provider), (1, SERVERS[0]))
        self.assertAlmostEqual(route.distance_miles, 100)
        self.assertAlmostEqual(route.duration_hours, 2)
        self.assertEqual(route.points, [(38.5, -120.2), (40.7, -120.95)])

    @mock.patch('fuel.routing.requests.get', side_effect=[requests.Timeout(), OK])
    def test_falls_back_to_the_next_server(self, get):
        route = get_route(START, FINISH)
        self.assertEqual((route.calls, route.provider), (2, SERVERS[1]))

    @mock.patch('fuel.routing.requests.get', return_value=osrm_reply({'code': 'NoRoute'}))
    def test_no_route_is_an_answer_not_an_outage(self, get):
        with self.assertRaises(RouteNotFound):
            get_route(START, FINISH)
        self.assertEqual(get.call_count, 1)

    @mock.patch('fuel.routing.requests.get', side_effect=requests.ConnectionError())
    def test_every_server_down(self, get):
        with self.assertRaises(RoutingUnavailable):
            get_route(START, FINISH)
        self.assertEqual(get.call_count, 2)


class DecodePolylineTests(SimpleTestCase):
    def test_decodes_googles_reference_example(self):
        # The example from Google's documentation, at OSRM's 5-digit precision.
        points = decode_polyline('_p~iF~ps|U_ulLnnqC_mqNvxq`@', precision=5)
        self.assertEqual(points, [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)])
