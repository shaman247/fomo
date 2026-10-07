"""Campus/venue containment and the merger's location re-pin rule (2026-10-07).

Lincoln Center Presents w4833 is linked to the campus row 493, so a source row
that only said "Lincoln Center" re-pinned Hania Rani 220582 off David Geffen
Hall 248, and the OSL Koch Theater programs never left 493 for 249.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from location_containment import LocationContainment
from merger import same_place, should_repin_location

CAMPUS, GEFFEN, KOCH, TULLY, JALC, MOMA, STORE, CHIPS, DINER, BOOKS, CHAMBERS, DORIS = range(1, 13)
UWS, UNRELATED = 20, 21

LOCATIONS = [
    (CAMPUS, 'Lincoln Center for the Performing Arts',
     '10 Lincoln Center Plaza, New York, NY 10023, USA', 40.772786, -73.983104, 0),
    (GEFFEN, 'David Geffen Hall at Lincoln Center',
     '10 Lincoln Center Plaza, New York, NY 10023, USA', 40.772870, -73.983100, 0),
    (KOCH, 'David H. Koch Theater',
     '20 Lincoln Center Plaza, New York, NY 10023, USA', 40.771870, -73.983620, 0),
    (TULLY, 'Alice Tully Hall', '1941 Broadway, New York, NY 10023, USA',
     40.773703, -73.982641, 0),
    # Names the campus but sits ~2.4 km away.
    (JALC, 'Lincoln Center Annex Midtown', '11 W 53rd St, New York, NY 10019',
     40.761433, -73.977622, 0),
    (MOMA, 'Museum of Modern Art', '11 W 53rd St, New York, NY 10019',
     40.761433, -73.977622, 0),
    (STORE, 'Lincoln Center Pet Store', '1900 Broadway, New York, NY 10023',
     40.7725, -73.9830, 0),
    (CHIPS, 'CHiPS', '200 4th Ave, Brooklyn, NY 11217, USA', 40.6790, -73.9830, 0),
    (DINER, 'Montague Diner', '100 Montague St, Brooklyn, NY 11201', 40.6950, -73.9940, 0),
    (BOOKS, 'Books Are Magic (Montague St.)', '122 Montague St, Brooklyn, NY 11201',
     40.6951, -73.9938, 0),
    (CHAMBERS, 'Chambers', '94 Chambers St, New York, NY 10007, USA', 40.7155, -74.0070, 0),
    (DORIS, 'NYC Department of Records', '31 Chambers St, New York, NY 10007',
     40.7140, -74.0040, 0),
    (UWS, 'Upper West Side', None, 40.7870, -73.9754, 1),
    (UNRELATED, 'Some Wrong Fuzzy Match Bar', '200 W 70th St, New York, NY 10023',
     40.7770, -73.9850, 0),
]
ALIASES = [
    (CAMPUS, 'Lincoln Center'),
    (TULLY, 'Alice Tully Hall at Lincoln Center'),
    (CHIPS, 'Brooklyn, NY 11217'),
    (CHIPS, '200 4th Ave, Brooklyn, NY 11217, USA'),
    (BOOKS, 'Montague St'),
]


def containment():
    return LocationContainment(LOCATIONS, ALIASES)


class ContainmentTests(unittest.TestCase):
    def test_campus_contains_halls_by_name_address_or_alias(self):
        lc = containment()
        self.assertTrue(lc.contains(CAMPUS, GEFFEN))   # "... at Lincoln Center" name
        self.assertTrue(lc.contains(CAMPUS, KOCH))     # "20 Lincoln Center Plaza"
        self.assertTrue(lc.contains(CAMPUS, TULLY))    # global alias

    def test_containment_is_one_way(self):
        lc = containment()
        for hall in (GEFFEN, KOCH, TULLY):
            self.assertFalse(lc.contains(hall, CAMPUS))

    def test_siblings_do_not_contain_each_other(self):
        lc = containment()
        for a in (GEFFEN, KOCH, TULLY):
            for b in (GEFFEN, KOCH, TULLY):
                self.assertFalse(lc.contains(a, b))

    def test_distance_gate(self):
        self.assertFalse(containment().contains(CAMPUS, JALC))

    def test_unrelated_and_unknown(self):
        lc = containment()
        self.assertFalse(lc.contains(CAMPUS, UNRELATED))
        self.assertFalse(lc.contains(CAMPUS, None))
        self.assertFalse(lc.contains(CAMPUS, 999))
        self.assertFalse(lc.contains(CAMPUS, CAMPUS))

    def test_generic_area_is_never_inside_a_venue(self):
        self.assertFalse(containment().contains(CAMPUS, UWS))

    def test_address_and_street_aliases_are_not_keys(self):
        lc = containment()
        self.assertFalse(lc.contains(CHIPS, KOCH))     # ZIP-bearing alias
        self.assertFalse(lc.contains(BOOKS, DINER))    # bare street alias

    def test_one_word_key_does_not_match_a_street_address(self):
        self.assertFalse(containment().contains(CHAMBERS, DORIS))

    def test_related_lists_both_grains_and_not_siblings(self):
        lc = containment()
        self.assertEqual(lc.related(CAMPUS), {GEFFEN, KOCH, TULLY, STORE})
        self.assertEqual(lc.related(GEFFEN), {CAMPUS})
        self.assertEqual(lc.related(JALC), set())
        self.assertEqual(lc.related(999), set())

    def test_shop_named_for_the_campus_counts_as_inside(self):
        # Harmless by design: a specific pin is never pulled back to the campus.
        self.assertTrue(containment().contains(CAMPUS, STORE))


class RepinTests(unittest.TestCase):
    def setUp(self):
        self.lc = containment()
        self.linked = {CAMPUS}   # Lincoln Center Presents w4833

    def repin(self, current, incoming, linked=None):
        return should_repin_location(current, incoming,
                                     self.linked if linked is None else linked, self.lc)

    def test_linked_umbrella_never_replaces_contained_hall(self):
        self.assertFalse(self.repin(GEFFEN, CAMPUS))
        self.assertFalse(self.repin(KOCH, CAMPUS, linked={KOCH, CAMPUS}))

    def test_umbrella_is_refined_to_contained_hall_even_when_unlinked(self):
        self.assertTrue(self.repin(CAMPUS, GEFFEN))
        self.assertTrue(self.repin(CAMPUS, KOCH, linked=set()))

    def test_stale_fuzzy_match_still_corrected_to_linked_location(self):
        self.assertTrue(self.repin(UNRELATED, CAMPUS))
        self.assertTrue(self.repin(JALC, CAMPUS))

    def test_unlinked_unrelated_venue_does_not_repin(self):
        self.assertFalse(self.repin(GEFFEN, TULLY))
        self.assertFalse(self.repin(GEFFEN, UNRELATED))

    def test_missing_current_is_filled_and_same_is_noop(self):
        self.assertTrue(self.repin(None, CAMPUS, linked=set()))
        self.assertFalse(self.repin(GEFFEN, GEFFEN))
        self.assertFalse(self.repin(GEFFEN, None))

    def test_two_merges_in_any_source_order_settle_on_the_hall(self):
        # The sources of one event, replayed in both orders and twice over.
        sources = [CAMPUS, GEFFEN, CAMPUS, GEFFEN]
        for order in (sources, list(reversed(sources))):
            pin = CAMPUS
            for _ in range(2):
                for incoming in order:
                    if self.repin(pin, incoming):
                        pin = incoming
            self.assertEqual(pin, GEFFEN)


class SamePlaceTests(unittest.TestCase):
    def test_campus_and_hall_are_one_place_for_the_cross_location_guard(self):
        lc = containment()
        self.assertTrue(same_place(GEFFEN, CAMPUS, lc))
        self.assertTrue(same_place(CAMPUS, KOCH, lc))
        self.assertTrue(same_place(KOCH, KOCH, lc))

    def test_sibling_halls_stay_distinct(self):
        lc = containment()
        self.assertFalse(same_place(GEFFEN, KOCH, lc))
        self.assertFalse(same_place(GEFFEN, TULLY, lc))
        self.assertFalse(same_place(CAMPUS, UNRELATED, lc))


if __name__ == '__main__':
    unittest.main()
