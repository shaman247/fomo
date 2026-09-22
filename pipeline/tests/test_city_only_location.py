"""A municipality alone must not acquire a guessed station or street pin."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import processor


class CityOnlyLocationTests(unittest.TestCase):
    def make_map(self, extra=(), linked=None, scoped=None):
        specs = [
            (1, 'Chester Ct (Flatbush Ave–Dead End), Brooklyn', 'Chester Ct',
             'Chester Ct & Flatbush Ave, Brooklyn, NY 11225'),
            (2, 'University of Rochester', None, '500 Joseph C Wilson Blvd, Rochester, NY 14627'),
            (3, 'Chester Meeting House', None, '4 Liberty St, Chester, CT 06412'),
            (4, 'West Windsor Township Station', None, '1 Main St, West Windsor Township, NJ 08550'),
            *extra,
        ]
        rows = [dict(id=i, name=n, short_name=s, address=a, lat=1., lng=1., emoji='X',
                     alternate_names=[], website_scoped_names=(scoped or {}).get(i, {}))
                for i, n, s, a in specs]
        with patch.object(processor.db, 'get_all_locations', return_value=rows), \
             patch.object(processor.db, 'get_website_locations_map', return_value=linked or {}), \
             patch.object(processor.db, 'get_website_names', return_value={}), \
             patch.object(processor.db, 'get_roving_organizer_websites', return_value=set()):
            return processor.build_locations_map(None)

    def resolve(self, text, mapping, sub=None, website=None, event='A concert'):
        result = processor.get_location_id(text, sub, '', event, mapping, website_id=website)
        return result and result['id']

    def test_city_cannot_fuzzy_match_a_street(self):
        mapping = self.make_map()
        for text in ('Rochester, NY', 'Chester, CT'):
            with self.subTest(text=text):
                self.assertIsNone(self.resolve(text, mapping))

    def test_city_cannot_prefix_match_its_station(self):
        self.assertIsNone(self.resolve('West Windsor Township', self.make_map()))

    def test_actual_station_name_still_matches(self):
        self.assertEqual(self.resolve('West Windsor Township Station', self.make_map()), 4)

    def test_city_placemarkers_remain_available(self):
        for name, short in [('Rochester (exact location unspecified)', 'Rochester'),
                            ('Rochester Village', 'Rochester')]:
            with self.subTest(name=name):
                mapping = self.make_map([(5, name, short, 'Rochester, NY 14627')])
                self.assertEqual(self.resolve('Rochester, NY', mapping), 5)

    def test_curated_website_alias_remains_authoritative(self):
        mapping = self.make_map(scoped={3: {9: ['Chester']}})
        self.assertEqual(self.resolve('Chester, CT', mapping, website=9), 3)

    def test_single_venue_authority_is_preserved(self):
        mapping = self.make_map(linked={9: [{'id': 3, 'name': 'Chester Meeting House', 'emoji': 'X'}]})
        self.assertEqual(self.resolve('Chester, CT', mapping, website=9), 3)

    def test_street_address_still_resolves(self):
        self.assertEqual(self.resolve('Chester, CT', self.make_map(), sub='4 Liberty St'), 3)

    def test_event_name_can_supply_exact_venue_evidence(self):
        self.assertEqual(self.resolve('Rochester, NY', self.make_map(),
                                     event='University of Rochester'), 2)


if __name__ == '__main__':
    unittest.main()
