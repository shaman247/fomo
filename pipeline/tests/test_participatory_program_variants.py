"""Similarly named shows and classes must retain their own source schedules."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from event_name_guards import participatory_program_variant_mismatch
from merger import are_names_similar, is_false_positive
from processor import group_event_occurrences


class ParticipatoryProgramVariants(unittest.TestCase):
    PAIRS = [
        ('Asian AF Jam!', 'Asian AF'),
        ('Ciao Bambini! Italian Language for Families by The Bilingual Garden NY',
         'Ciao Bambini! Italian Language Readiness for PreSchool by The Bilingual Garden NY'),
        ('3D Printer : BUS (Basic Use and Safety)', 'Laser Cutter : BUS (Basic Use and Safety)'),
        ('3D Printing', 'Laser Cutting'),
        ('3D Printer: Basic Use and Safety', 'Laser Cutter : BUS (Basic Use and Safety)'),
    ]

    def test_canonical_matching_rejects_different_activities_in_both_orders(self):
        for left, right in self.PAIRS:
            for a, b in [(left, right), (right, left)]:
                with self.subTest(a=a, b=b):
                    self.assertTrue(is_false_positive(a, b))
                    self.assertFalse(are_names_similar(a, b))

    def test_shared_listing_url_and_date_cannot_join_sibling_schedules(self):
        for left, right in self.PAIRS:
            for names in [(left, right), (right, left)]:
                rows = [dict(name=n, location='Venue', location_id=1,
                             start_date='2026-10-17', start_time=t,
                             url='https://example.org/classes')
                        for n, t in zip(names, ['12pm', '1:30pm'])]
                with self.subTest(names=names):
                    grouped = group_event_occurrences(rows)
                    self.assertEqual(len(grouped), 2)
                    self.assertTrue(all(len(e['occurrences']) == 1 for e in grouped))

    def test_same_activity_spelling_still_matches(self):
        for a, b in [('Asian AF Jam!', 'ASIAN AF JAM'),
                     ('3D Printer : BUS (Basic Use and Safety)', '3D Printer: Basic Use and Safety'),
                     ('Laser Cutter : BUS (Basic Use and Safety)', 'Laser Cutter: Basic Use and Safety')]:
            self.assertFalse(participatory_program_variant_mismatch(a, b))
            self.assertTrue(are_names_similar(a, b))

    def test_ambiguous_titles_do_not_trigger_activity_guard(self):
        for a, b in [('Pearl', 'Pearl Jam'), ('Space', 'Space Jam'),
                     ('Jazz Jam', 'Jazz Jam Session'),
                     ('Italian Language', 'Italian Language for Families'),
                     ('3D Printing and Laser Cutting', 'Laser Cutting'),
                     ('Talk: 3D Printing', 'Talk: Laser Cutting')]:
            self.assertFalse(participatory_program_variant_mismatch(a, b))


if __name__ == '__main__':
    unittest.main()
