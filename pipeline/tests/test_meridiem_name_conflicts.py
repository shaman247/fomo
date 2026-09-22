"""Morning and afternoon sessions must survive every fuzzy-name tier."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger


class MeridiemNameConflictTests(unittest.TestCase):
    def assert_distinct(self, first, second):
        self.assertFalse(merger.are_names_similar(first, second))
        self.assertFalse(merger.are_names_similar(second, first))

    def test_instructional_class_and_long_camp_names_do_not_merge(self):
        for name in (
            'Mah Jongg {} Instructional Class – Session 1',
            'CQ Mini Camp (4th – 8th gr.) – Extended Care {} – WK 1 – 3 DAYS Aug. 19-21, 2026',
            'Beginner Wednesday {} Wheel Class',
            'Art Class: {} Session',
        ):
            with self.subTest(name=name):
                self.assert_distinct(name.format('AM'), name.format('PM'))

    def test_dotted_and_lowercase_labels_are_equivalent(self):
        self.assert_distinct('Mah Jongg A.M. Instructional Class', 'Mah Jongg p.m. Instructional Class')
        self.assertTrue(merger.are_names_similar('Mah Jongg A.M. Instructional Class',
                                                'Mah Jongg AM Instructional Class'))

    def test_missing_and_combined_labels_do_not_create_a_conflict(self):
        for first, second in (
            ('Mah Jongg AM Instructional Class', 'Mah Jongg Instructional Class'),
            ('Morning Art Class', 'Morning Art Class PM'),
            ('Art Class AM/PM', 'Art Class PM'),
            ('I Am Here', 'I Am Here Film Screening'),
            ('Camp Class', 'Camp Class'),
        ):
            with self.subTest(first=first, second=second):
                self.assertFalse(merger.is_false_positive(first, second))

    def test_existing_numeric_cohort_and_clock_guards_remain(self):
        self.assert_distinct('Comedy Show 8pm', 'Comedy Show 10pm')
        self.assert_distinct('Drawing Session 1', 'Drawing Session 2')
        self.assertIn('2', merger.get_significant_words('Drawing Session 2'))


if __name__ == '__main__':
    unittest.main()
