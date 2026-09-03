#!/usr/bin/env python
"""Tests for the parent-qualified sublocation tier in processor.get_location_id.

Run: ./venv/bin/python pipeline/tests/test_parent_qualified_sublocation.py

Guards the 2026-09-02 fix for a resolver that did WORSE when handed MORE
information. A source that writes "<Parent venue> - <specific feature>" makes
every search key carry the parent's name, so the only exact hit available was
the parent's own `names` entry and the event landed on the whole 85-acre park:

    "Brooklyn Bridge Park - Pier 3 Central Lawn"  ->  Brooklyn Bridge Park
    "Pier 3"           (same page, older crawl)   ->  Pier 3 at Brooklyn Bridge Park

Step 1b recovers the trailing half as a key of its own. Three gates keep it
narrow, and the tests below pin all three: an explicit delimiter after a
leading half that EXACTLY names a location; a lookup confined to the curated
website-scoped tier (the global tiers never see a bare feature name — that is
the sibling-hijack risk the composite-key comment in get_location_id warns
about); and `_child_of_parent`, which requires the answer to actually sit
inside the parent. Measured over the whole crawl_events corpus, the third gate
is what turns 3 mis-pins in 51 changes into 32 changes and 0 mis-pins.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import processor


class _StubCursor:
    """Feeds build_locations_map a fixed corpus instead of the live DB."""

    def __init__(self, locations, alternates, website_locations):
        self._locations = locations
        self._alternates = alternates
        self._website_locations = website_locations
        self._rows = []

    def execute(self, sql, *args):
        if 'FROM locations' in sql and 'website_locations' not in sql:
            self._rows = self._locations
        elif 'FROM location_alternate_names' in sql:
            self._rows = self._alternates
        elif 'website_locations' in sql:
            self._rows = self._website_locations
        else:  # pragma: no cover - build_locations_map grew a new query
            raise AssertionError('unexpected query: %s' % sql)

    def fetchall(self):
        return self._rows


# id, name, short_name, address, lat, lng, emoji
_LOCATIONS = [
    (140, 'Brooklyn Bridge Park', None,
     'Brooklyn Bridge Park, Brooklyn, NY 11201, USA', 40.70224, -73.99586, '🌳'),
    (10219, 'Pier 3 at Brooklyn Bridge Park', None,
     'Pier 3 at Brooklyn Bridge Park, Furman St, Brooklyn, NY 11201, USA',
     40.698443, -74.000021, '🌳'),
    (10218, 'Pier 2 at Brooklyn Bridge Park', None,
     'Pier 2 at Brooklyn Bridge Park, Furman St, Brooklyn, NY 11201, USA',
     40.699937, -73.999065, '🏀'),
    # An unrelated venue that happens to own the same bare feature name. If the
    # feature key ever escapes the website-scoped tier, this is what it hits.
    (9001, 'Pier 3 Central Lawn', None,
     '1 Marina Way, Yonkers, NY 10701, USA', 40.9312, -73.8988, '⚓'),
    # The `_child_of_parent` decoy, modelled on the real "The Paris Theater -
    # Screen 1" -> Upstate Films (Rhinebeck) mis-pin: w162 curates the generic
    # room key "screen 1" for a venue that is NOT inside Brooklyn Bridge Park.
    (9002, 'The Paris Theater', None,
     '4 W 58th St, New York, NY 10019, USA', 40.7643, -73.9738, '🎬'),
    (9003, 'Upstate Films', None,
     '6415 Montgomery St, Rhinebeck, NY 12572, USA', 41.9270, -73.9126, '🎬'),
]

# location_id, alternate_name, website_id
_ALTERNATES = [
    (10219, 'Pier 3 Central Lawn', 162),
    (10218, 'Pier 2 Turf', 162),
    (10218, 'Brooklyn Bridge Park Pier 2', 162),
    (9003, 'Screen 1', 162),
]

# website_id, location_id, name, lat, lng, emoji  (w162 is single-venue-linked
# to the PARENT, which is what Step 3.5 answered with before the fix)
_WEBSITE_LOCATIONS = [
    (162, 140, 'Brooklyn Bridge Park', 40.70224, -73.99586, '🌳'),
]


class ParentQualifiedFeatureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lm = processor.build_locations_map(
            _StubCursor(_LOCATIONS, _ALTERNATES, _WEBSITE_LOCATIONS))

    def resolve(self, location_name, sublocation=None, website_id=162):
        got = processor.get_location_id(
            location_name, sublocation, None, None, self.lm, website_id=website_id)
        return got and got['id']

    # -- the feature half wins over the parent ----------------------------
    def test_em_dash_parent_prefers_the_child(self):
        self.assertEqual(10219,
                         self.resolve('Brooklyn Bridge Park — Pier 3 Central Lawn'))
        self.assertEqual(10218,
                         self.resolve('Brooklyn Bridge Park — Pier 2 Turf'))

    def test_hyphen_and_pipe_delimiters_behave_the_same(self):
        self.assertEqual(10219, self.resolve('Brooklyn Bridge Park - Pier 3 Central Lawn'))
        self.assertEqual(10219, self.resolve('Brooklyn Bridge Park | Pier 3 Central Lawn'))

    def test_bare_feature_name_still_resolves(self):
        """The shape that already worked must keep working."""
        self.assertEqual(10219, self.resolve('Pier 3 Central Lawn'))

    def test_bare_parent_name_still_resolves_to_the_parent(self):
        self.assertEqual(140, self.resolve('Brooklyn Bridge Park'))

    # -- the guards -------------------------------------------------------
    def test_feature_key_never_reaches_the_global_tiers(self):
        """Loc 9001 is a same-named venue 15 miles away in Yonkers, sitting in
        the GLOBAL `names` tier. The feature key is offered to the
        website-scoped tier only, so no website may reach it that way."""
        self.assertNotEqual(9001,
                            self.resolve('Brooklyn Bridge Park — Pier 3 Central Lawn',
                                         website_id=999))
        self.assertNotEqual(9001,
                            self.resolve('Brooklyn Bridge Park — Pier 3 Central Lawn'))

    def test_unknown_leading_half_is_not_a_parent(self):
        """The leading half must EXACTLY name a location, or nothing splits."""
        self.assertIsNone(self.resolve('Some Random Org — Pier 3 Central Lawn'))

    def test_feature_must_sit_inside_the_parent(self):
        """The trailing half is "the other half", not automatically the more
        specific one. w162 curates "screen 1" for Upstate Films in Rhinebeck;
        "The Paris Theater - Screen 1" must not land 90 miles upstate."""
        self.assertNotEqual(9003, self.resolve('The Paris Theater — Screen 1'))
        # And the gate refuses rather than guessing: this is exactly the
        # pre-fix answer, so the new tier costs nothing when it declines.
        self.assertIsNone(self.resolve('The Paris Theater — Screen 1'))

    def test_child_of_parent_reads_name_and_address(self):
        park = {'name': 'Pier 3 at Brooklyn Bridge Park', 'address': 'Furman St'}
        lawn = {'name': 'Liberty Lawn', 'address': 'Brooklyn Bridge Park Pier 6, Brooklyn'}
        upstate = {'name': 'Upstate Films', 'address': '6415 Montgomery St, Rhinebeck'}
        self.assertTrue(processor._child_of_parent(park, 'brooklyn bridge park'))
        self.assertTrue(processor._child_of_parent(lawn, 'brooklyn bridge park'))
        self.assertFalse(processor._child_of_parent(upstate, 'the paris theater'))

    def test_hyphenated_venue_name_is_not_split(self):
        """No whitespace around the hyphen => not a delimiter."""
        self.assertIsNone(
            processor._parent_qualified_feature_key(
                'Bed-Stuy Restoration Plaza', self.lm))

    def test_delimiter_without_a_known_parent_returns_none(self):
        self.assertIsNone(
            processor._parent_qualified_feature_key(
                '123 Main St - Suite 400', self.lm))

    def test_feature_half_too_short_is_rejected(self):
        self.assertIsNone(
            processor._parent_qualified_feature_key(
                'Brooklyn Bridge Park - P2', self.lm))

    def test_split_returns_both_halves(self):
        self.assertEqual(
            ('brooklyn bridge park', 'pier 3 central lawn'),
            processor._parent_qualified_feature_key(
                'Brooklyn Bridge Park — Pier 3 Central Lawn', self.lm))


if __name__ == '__main__':
    unittest.main(verbosity=2)
