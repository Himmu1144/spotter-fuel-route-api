import tempfile
from io import StringIO
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from fuel.models import FuelStation
from fuel.places import normalize
from scripts.build_stations import read_prices

PRICE_ROWS = '''OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price
105,TA SAGINAW,"I-75, EXIT 144-B",Bridgeport,MI,260,3.339
105,TA SAGINAW,"I-75, EXIT 144-B",Bridgeport,MI,260,3.269
105,TA SAGINAW,"I-75, EXIT 144-B",Bridgeport,MI,260,3.429
128,THE EFFINGHAM CHROME SHOP,"I-57 & I-70, EXIT 159",Effingham          ,IL,510,3.399
900,PETRO CANADA,HWY 1,Calgary,AB,1,1.999
'''


class NormalizeTests(SimpleTestCase):
    def test_spellings_of_the_same_town_match(self):
        self.assertEqual(normalize('St. Louis'), normalize('SAINT LOUIS'))
        self.assertEqual(normalize('Mc Calla'), normalize('McCalla'))
        self.assertEqual(normalize("O'Neill"), normalize('ONEILL'))
        self.assertEqual(normalize('S Coffeyville'), normalize('South Coffeyville'))
        self.assertEqual(normalize('Effingham        '), 'effingham')


class ReadPricesTests(SimpleTestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / 'prices.csv'
        self.path.write_text(PRICE_ROWS)

    def test_keeps_one_row_per_station_at_its_median_price(self):
        stations = read_prices(self.path, report=lambda message: None)
        self.assertEqual(stations[105]['price_per_gallon'], Decimal('3.339'))

    def test_drops_stations_outside_the_us_and_trims_text(self):
        stations = read_prices(self.path, report=lambda message: None)
        self.assertEqual(sorted(stations), [105, 128])
        self.assertEqual(stations[128]['city'], 'Effingham')


class LoadStationsTests(TestCase):
    def test_loads_every_station_and_can_run_twice(self):
        call_command('load_stations', stdout=StringIO())
        call_command('load_stations', stdout=StringIO())
        self.assertEqual(FuelStation.objects.count(), 6626)
        self.assertEqual(FuelStation.objects.get(opis_id=105).price_per_gallon, Decimal('3.319'))
