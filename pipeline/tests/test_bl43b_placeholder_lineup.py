"""BL43b: two RA parties that share only "+ Special Guests TBA" are two events.

Jupiter Disco (w388, loc 448) lists "Youngins: Special Guests TBA" (10/24 10pm,
ra.co/events/2542555) and "señoritajuicy + Special Guests TBA" (10/25 7pm,
ra.co/events/2542552). The placeholder tail gave them three of four significant
words, so `are_names_similar` matched them through the asymmetric containment
tier and `same_capture_names_related` through the 0.5 ratio. Event 264934 kept
re-absorbing the second party after every manual detach.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import merger
from test_bl25_same_capture_partition import run_merge

YOUNGINS = ('Youngins: Special Guests TBA', 'https://ra.co/events/2542555')
SENORITA = ('señoritajuicy + Special Guests TBA', 'https://ra.co/events/2542552')


class PlaceholderLineupNameTests(unittest.TestCase):

    def test_different_headliners_with_a_shared_tail_differ(self):
        for a, b in [
            (YOUNGINS[0], SENORITA[0]),
            ('Halloween Party: Lineup TBA', 'Disco Night: Lineup TBA'),
            ('Clayton Hopkins / Death by Comet / Aunt Judy', 'Dylan Charles & special guests'),
        ]:
            with self.subTest(a=a, b=b):
                self.assertFalse(merger.are_names_similar(a, b))
                self.assertFalse(merger.same_capture_names_related(a, b, a))

    def test_same_headliner_with_or_without_the_tail_still_matches(self):
        for a, b in [
            (YOUNGINS[0], 'Youngins'),
            (YOUNGINS[0], 'Youngins w/ Special Guest'),
            ('Jazz Night with Special Guests', 'Jazz Night'),
            ('The Comedy Show', 'Comedy Show feat. Special Guest'),
        ]:
            with self.subTest(a=a, b=b):
                self.assertTrue(merger.are_names_similar(a, b))
                self.assertTrue(merger.same_capture_names_related(a, b, a))

    def test_a_bare_placeholder_carries_no_verdict(self):
        self.assertFalse(merger._placeholder_lineup_differs('Special Guests TBA', 'Youngins'))
        self.assertFalse(merger._placeholder_lineup_differs('Youngins', 'Señoritajuicy'))


class PlaceholderLineupMergeTests(unittest.TestCase):

    def test_second_party_gets_its_own_event(self):
        links, created = run_merge([(1478812, *SENORITA, 1)],
                                   events=[(264934, YOUNGINS[0])], website=388)
        self.assertNotEqual(links[1478812], 264934)
        self.assertEqual(list(created.values()), [SENORITA[0]])

    def test_without_the_rule_the_party_was_absorbed(self):
        without = tuple(d for d in merger._PAIR_DISCRIMINATORS
                        if d is not merger._placeholder_lineup_differs)
        with patch.object(merger, '_PAIR_DISCRIMINATORS', without), \
                patch.object(merger, '_placeholder_lineup_differs', return_value=False):
            links, created = run_merge([(1478812, *SENORITA, 1)],
                                       events=[(264934, YOUNGINS[0])], website=388)
        self.assertEqual(links[1478812], 264934)
        self.assertEqual(created, {})

    def test_same_capture_pair_splits_in_either_order(self):
        for order in ([(1, *YOUNGINS, 0), (2, *SENORITA, 1)],
                      [(2, *SENORITA, 1), (1, *YOUNGINS, 0)]):
            links, created = run_merge(order, events=[(264934, YOUNGINS[0])], website=388)
            self.assertEqual(links[1], 264934)
            self.assertNotEqual(links[2], 264934)
            self.assertEqual(list(created.values()), [SENORITA[0]])


if __name__ == '__main__':
    unittest.main()
