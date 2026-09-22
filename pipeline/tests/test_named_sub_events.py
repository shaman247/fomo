"""A shared exhibition URL must not absorb its independently timed gathering."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from event_name_guards import named_sub_event_mismatch
from processor import group_event_occurrences
from merger import are_names_similar


class NamedSubEvents(unittest.TestCase):
    def test_shared_url_run_and_gathering_stay_separate_in_either_order(self):
        for base, gathering in [
            ('A Vivid Blur', 'A Vivid Blur: Curator Walk-Through'),
            ('A Vivid Blur', '“A Vivid Blur”: Mirror-Making Workshop'),
            ('Andrew Ginzel', 'Andrew Ginzel: Opening Reception'),
            ('MFA Illustration Exhibition 2026', 'MFA Illustration Exhibition 2026 — Reception'),
        ]:
            run = dict(name=base, location_id=1, location='Gallery',
                       start_date='2026-10-01', end_date='2026-10-30', start_time='',
                       url='https://example.org/exhibition')
            visit = dict(name=gathering, location_id=1, location='Gallery',
                         start_date='2026-10-30', start_time='5pm',
                         url='https://example.org/exhibition')
            for rows in ([run, visit], [visit, run]):
                with self.subTest(names=[r['name'] for r in rows]):
                    result = group_event_occurrences(rows)
                    self.assertEqual(len(result), 2)
                    self.assertTrue(all(len(e['occurrences']) == 1 for e in result))
                    self.assertFalse(are_names_similar(rows[0]['name'], rows[1]['name']))

    def test_prefix_label_also_distinguishes_gathering(self):
        self.assertTrue(named_sub_event_mismatch('Opening Reception: Andrew Ginzel', 'Andrew Ginzel'))

    def test_older_parent_title_with_exhibition_suffix(self):
        self.assertFalse(are_names_similar('A Vivid Blur Exhibition', 'A Vivid Blur: Curator Walk-Through'))
        self.assertFalse(are_names_similar('Andrew Ginzel Exhibition', 'Andrew Ginzel: Opening Reception'))
        self.assertFalse(are_names_similar('A Vivid Blur Exhibition', '“A Vivid Blur”: Mirror-Making Workshop'))

    def test_two_same_gathering_spellings_are_not_vetoed(self):
        self.assertFalse(named_sub_event_mismatch('Opening Reception: Andrew Ginzel', 'Andrew Ginzel — Reception'))
        self.assertTrue(are_names_similar('Andrew Ginzel: Reception', 'Andrew Ginzel — Reception'))

    def test_different_satellite_kinds_stay_separate(self):
        self.assertTrue(named_sub_event_mismatch('Andrew Ginzel: Reception', 'Andrew Ginzel: Artist Talk'))

    def test_ambiguous_bare_labels_and_fuller_titles_keep_existing_policy(self):
        for suffix in ['Opening', 'Preview', 'Tour', 'Part Two', 'Special Edition']:
            self.assertFalse(named_sub_event_mismatch('Example', 'Example: '+suffix))


if __name__ == '__main__':
    unittest.main()
