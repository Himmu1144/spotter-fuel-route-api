from django.test import TestCase, override_settings

from fuel.corridor import stations_along
from fuel.geo import MILES_PER_DEGREE_LATITUDE
from fuel.models import FuelStation

# A straight road along latitude 40 from longitude -100 to -99: about 53 miles.
ROUTE = [(40.0, -100 + i / 100) for i in range(101)]


def north_of_route(miles):
    return 40.0 + miles / MILES_PER_DEGREE_LATITUDE


def add_station(opis_id, latitude, longitude, placement='town'):
    return FuelStation.objects.create(
        opis_id=opis_id, name=f'Station {opis_id}', address='', city='', state='KS', rack_id=1,
        price_per_gallon='3.5', lowest_price='3.5', highest_price='3.5',
        latitude=latitude, longitude=longitude, placement=placement)


@override_settings(CORRIDOR_MILES={'exit': 3, 'town': 10, 'manual': 10})
class StationsAlongTests(TestCase):
    def setUp(self):
        # `migrate` loads the real stations; these tests use only their own.
        FuelStation.objects.all().delete()

    def test_keeps_stations_within_the_corridor_in_route_order(self):
        add_station(1, 40.0, -99.5)                    # on the road, about mile 26.5
        add_station(2, north_of_route(5), -99.8)       # 5 miles off, about mile 10.6
        add_station(3, north_of_route(20), -99.5)      # 20 miles off: too far
        add_station(4, 40.0, -98.0)                    # past the end of the route
        found = stations_along(ROUTE)
        self.assertEqual([s.station.opis_id for s in found], [2, 1])
        self.assertAlmostEqual(found[0].mile, 10.6, delta=0.5)
        self.assertAlmostEqual(found[0].off_route_miles, 5, delta=0.3)
        self.assertAlmostEqual(found[1].mile, 26.5, delta=0.5)

    def test_exact_exit_placements_get_a_narrower_corridor(self):
        add_station(1, north_of_route(5), -99.5, placement='exit')
        add_station(2, north_of_route(5), -99.4, placement='town')
        self.assertEqual([s.station.opis_id for s in stations_along(ROUTE)], [2])

    def test_station_at_the_start_is_mile_zero(self):
        add_station(1, 40.0, -100.0)
        self.assertAlmostEqual(stations_along(ROUTE)[0].mile, 0, delta=0.01)
