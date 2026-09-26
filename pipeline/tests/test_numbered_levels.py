"""Numeric skill levels are identity; combined or missing levels are ambiguous."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger

LEFT = 'West Coast Swing Level 1 with Sophie Cazeneuve'
RIGHT = 'West Coast Swing Level 2 with Sophie Cazeneuve'


class NumberedLevelTests(unittest.TestCase):
    def test_actual_dance_source_pair_stays_separate_in_both_orders(self):
        for left, right in [(LEFT, RIGHT), (RIGHT, LEFT)]:
            self.assertTrue(merger.is_false_positive(left, right))
            self.assertFalse(merger.are_names_similar(left, right))

    def test_shared_core_and_long_common_title_cannot_override_level(self):
        for head in ['Monday West Coast Swing', 'Crafts: Long Weekly Creative Studio Program']:
            self.assertFalse(merger.are_names_similar(head + ' Level 2', head + ' Level 3'))

    def test_same_level_spelling_and_case_are_not_conflicting(self):
        for a, b in [('LEVEL 1', 'Level 01'), ('Level1', 'Level 1'), ('Level 2. Beginners', 'Level 2')]:
            self.assertFalse(merger._numbered_levels_differ(a, b))
        self.assertTrue(merger.are_names_similar(LEFT, LEFT.replace('Level 1', 'LEVEL 1')))

    def test_combined_plural_range_and_open_levels_do_not_invent_conflict(self):
        for label in ['Level 1&2', 'Level 1 & 2', 'Levels 1–2', 'Level 1/2',
                      'Level 1-2', 'Level 1—2', 'Level 1 to 2', 'Level 1 through 2',
                      'Level 1, 2', 'Level 1 and 2', 'Level 1 or 2', 'Level 1 & Level 2',
                      'Level 1 (and 2)', 'Level 1+', 'Level 1 and up', 'Level 1 & above',
                      'Level 1 / II', 'Level 1 and II', 'Level 1 through III',
                      'Level 1 & Level II', 'Level 1 and higher',
                      'Level 1.5', 'Level 1A']:
            with self.subTest(label=label):
                self.assertIsNone(merger._explicit_numbered_level('Swing ' + label))
                self.assertFalse(merger._numbered_levels_differ('Swing ' + label, 'Swing Level 3'))

    def test_unqualified_title_and_unrelated_numbers_do_not_invent_level(self):
        for title in ['Swing', 'Swing 1', 'Swing 2', 'Floor 1 Dance', 'Grade 2 Dance',
                      'Ballet 101', 'Level Up Your Dance', 'Next Level Dance 2', 'Levels for Everyone']:
            self.assertIsNone(merger._explicit_numbered_level(title))
            self.assertFalse(merger._numbered_levels_differ(title, LEFT))
        self.assertTrue(merger.are_names_similar('West Coast Swing with Sophie Cazeneuve', LEFT))

    def test_mixed_numbered_titles_remain_compatible_with_single_label(self):
        for label in ['Level 1 & 2', 'Levels 1–2', 'Level 1/2', 'Level 1+']:
            self.assertTrue(merger.are_names_similar('West Coast Swing ' + label, 'West Coast Swing Level 2'))

    def test_dateless_exact_shortcut_obeys_guard_even_if_normalizer_collapses_levels(self):
        existing = dict(id=1, name=LEFT, location_id=10)
        # Exercise the bypass explicitly, independent of today's normalization.
        with patch.object(merger, 'normalize_name_for_dedup', return_value='same core'):
            self.assertIsNone(merger._match_dateless_crawl_event(
                RIGHT, 10, None, None, None, {10: [existing]}, {}, {}))
            self.assertIsNone(merger._match_dateless_crawl_event(
                RIGHT, None, None, None, None, {}, {}, {}, 7, {7: [existing]}))

    def test_shared_url_shortcut_cannot_override_explicit_level(self):
        url = 'https://example.org/classes'; key = (7, merger.normalize_url_for_identity(url))
        slots = {('2026-10-03', '2pm')}
        index = {key: [dict(id=1, name=LEFT, location_id=10, slots=slots)]}
        with patch.object(merger, 'normalize_name_for_dedup', return_value='same core'):
            self.assertIsNone(merger._match_by_url_identity(
                RIGHT, url, 7, 10, slots, index, {key: 1}, set(), {}))

    def test_duplicate_classifier_does_not_auto_suppress_distinct_levels(self):
        from scripts.find_duplicate_events import classify_pairs
        pair = (1, 2, LEFT, RIGHT, 10, 'Studio', 7, 7)
        self.assertFalse(classify_pairs([pair], {(1, 2)}, set())[0])
        # The existing exact-normalized classifier shortcut calls the shared
        # false-positive policy before auto-suppression as well.
        with patch('scripts.find_duplicate_events.normalize_name_for_dedup', return_value='same core'):
            self.assertFalse(any(classify_pairs([pair], set(), set())))


if __name__ == '__main__':
    unittest.main()
