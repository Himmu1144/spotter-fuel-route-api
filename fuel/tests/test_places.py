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
        self.assertEqual(location.corrected_from, 'Chicgo, Ilinois')

    def test_exact_match_is_not_reported_as_a_correction(self):
        self.assertIsNone(resolve('Denver, CO').corrected_from)

    def test_rejects_what_it_cannot_resolve(self):
        cases = {
            'Springfield': 'has no state',
            'Toronto, ON': 'is not a US state',
            '51.5,-0.12': 'is not in the USA',
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
