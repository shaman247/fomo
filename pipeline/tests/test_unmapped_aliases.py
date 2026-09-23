"""Alias evidence clears only the correct generic pin and publisher scope."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from find_unmapped_events import classify


class UnmappedAliasTests(unittest.TestCase):
    def event(self, **changes):
        return dict(dict(location_id=385, location_name='Upper Highland Lawn',
                         venue_name='Highland Park', venue_address='Highland Boulevard',
                         venue_generic=1, website_id=2, website_name='NYC Parks'), **changes)

    def classify(self, aliases=None, **changes):
        return classify(self.event(**changes), aliases or {}, generic_names=set())

    def test_exact_global_alias_clears_generic_pin(self):
        self.assertIsNone(self.classify({385: [('Upper Highland Lawn', None)]}))

    def test_alias_normalization_matches_pipeline(self):
        self.assertIsNone(self.classify({385: [('Children’s Lawn & Garden', None)]},
                                       location_name="CHILDREN'S LAWN + GARDEN"))

    def test_website_scoped_alias_requires_same_publisher(self):
        aliases = {385: [('Upper Highland Lawn', 2)]}
        self.assertIsNone(self.classify(aliases))
        self.assertEqual(self.classify(aliases, website_id=3), 'GENERIC')
        self.assertEqual(self.classify(aliases, website_id=None), 'GENERIC')

    def test_alias_for_another_location_does_not_hide_wrong_pin(self):
        self.assertEqual(self.classify({999: [('Upper Highland Lawn', None)]}), 'GENERIC')

    def test_missing_alias_is_not_globally_skip_listed(self):
        self.assertEqual(self.classify(), 'GENERIC')

    def test_park_alias_does_not_hide_more_specific_venue(self):
        self.assertEqual(self.classify({385: [('Central Park', None)]},
                                       location_name='Central Park Zoo',
                                       venue_name='Central Park'), 'GENERIC')

    def test_partial_subfacility_alias_requires_review_in_both_directions(self):
        for alias in ('Upper Highland', 'Upper Highland Lawn Pavilion'):
            with self.subTest(alias=alias):
                self.assertEqual(self.classify({385: [(alias, None)]}), 'GENERIC')

    def test_specific_venue_keeps_substring_alias_behavior(self):
        self.assertIsNone(self.classify({385: [('Upper Highland', None)]}, venue_generic=0))

    def test_blank_alias_cannot_clear_pin(self):
        self.assertEqual(self.classify({385: [('', None), ('   ', None)]}), 'GENERIC')

    def test_unmapped_still_reported_even_with_alias(self):
        self.assertEqual(self.classify({385: [('Upper Highland Lawn', None)]},
                                       location_id=None), 'NO_LOCATION')

    def test_publisher_mismatch_exemption_does_not_clear_generic_pin(self):
        self.assertEqual(self.classify(website_name='New York Cares'), 'GENERIC')
        self.assertIsNone(self.classify(website_name='New York Cares', venue_generic=0))

    def test_stage_exemption_is_scoped_to_the_pinned_venue_and_publisher(self):
        name = 'Picture Book Stage, Brooklyn Borough Hall Plaza'
        aliases = {9425: [(name, 1120)]}
        changes = dict(location_name=name, location_id=9425, website_id=1120,
                       venue_name='Columbus Park (Downtown Brooklyn)')
        self.assertIsNone(self.classify(aliases, **changes))
        self.assertEqual(self.classify(aliases, **dict(changes, website_id=2)), 'GENERIC')
        self.assertEqual(self.classify(aliases, **dict(changes, location_id=5307,
                                                      venue_name='Columbus Park (Chinatown)')), 'GENERIC')


if __name__ == '__main__':
    unittest.main()
