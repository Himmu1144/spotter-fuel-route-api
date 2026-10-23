from django.test import SimpleTestCase

from fuel.places import PlaceNotFound, resolve


class ResolveTests(SimpleTestCase):
    def test_city_with_state_code_or_name(self):
        self.assertEqual(resolve('Chicago, IL').name, 'Chicago, IL')
        self.assertEqual(resolve('chicago,  illinois').name, 'Chicago, IL')

    def test_common_name_of_a_big_city(self):
        self.assertEqual(resolve('New York, NY').name, 'New York City, NY')

    def test_coordinates(self):
        location = resolve('41.88,-87.63')
        self.assertEqual((location.latitude, location.longitude), (41.88, -87.63))

    def test_typos_are_corrected_and_reported(self):
        location = resolve('Chicgo, Ilinois')
        self.assertEqual(location.name, 'Chicago, IL')
        self.assertEqual(location.note, 'Read "Chicgo, Ilinois" as "Chicago, IL".')

    def test_exact_match_is_not_reported_as_a_correction(self):
        self.assertIsNone(resolve('Denver, CO').note)

    def test_rejects_what_it_cannot_resolve(self):
        cases = {
            'Xyzzy': 'has no state',
            ', IL': 'has no city',
            'Toronto, ON': 'is not a US state',
            '51.5,-0.12': 'is not in the USA',
            '49.2827,-123.1207': 'is not in the USA',   # Vancouver, inside the old rough box
            '32.5149,-117.0382': 'is not in the USA',   # Tijuana
            '42.3149,-83.0364': 'is not in the USA',    # Windsor, across the river from Detroit
            '-87.63,41.88': 'Latitude comes first',
            'Xyz, CA': 'Could not find',
            '': 'empty',
        }
        for text, reason in cases.items():
            with self.subTest(text=text), self.assertRaisesMessage(PlaceNotFound, reason):
                resolve(text)

    def test_suggests_close_names_it_will_not_guess(self):
        with self.assertRaisesMessage(PlaceNotFound, 'Did you mean "Austin, TX"'):
            resolve('Austen, TX')


class NoStateTests(SimpleTestCase):
    def test_a_city_far_bigger_than_its_namesakes_is_accepted_with_a_note(self):
        location = resolve('Chicago')
        self.assertEqual(location.name, 'Chicago, IL')
        self.assertEqual(location.note, 'No state given; read "Chicago" as "Chicago, IL".')

    def test_an_ambiguous_name_lists_the_options_and_the_format(self):
        with self.assertRaises(PlaceNotFound) as raised:
            resolve('Portland')
        message = str(raised.exception)
        self.assertIn('several places called "Portland"', message)
        self.assertIn('Portland, OR; Portland, ME', message)
        self.assertIn('Use a city and state', message)


class InUsaTests(SimpleTestCase):
    def test_border_towns_on_the_us_side(self):
        from fuel.places import in_usa
        for name, (latitude, longitude) in {'Blaine, WA': (48.9937, -122.7471), 'Detroit, MI': (42.3314, -83.0458),
                                            'Calexico, CA': (32.6789, -115.4989), 'Key West, FL': (24.5551, -81.78),
                                            'Honolulu, HI': (21.3069, -157.8583), 'Anchorage, AK': (61.2181, -149.9003)}.items():
            with self.subTest(name=name):
                self.assertTrue(in_usa(latitude, longitude))
