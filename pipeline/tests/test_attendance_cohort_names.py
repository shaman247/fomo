import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from merger import are_names_similar, _explicit_attendance_mode, is_false_positive


class AttendanceCohortNames(unittest.TestCase):
    def test_separate_attendance_labels(self):
        for suffix in [' (Online)', ', virtual', ' - online', ' [Virtual]']:
            with self.subTest(suffix=suffix):
                a, b = 'Animation Techniques' + suffix, 'Animation Techniques (In Person)'
                self.assertFalse(are_names_similar(a, b))
                self.assertFalse(are_names_similar(b, a))

    def test_same_mode_aliases(self):
        self.assertFalse(is_false_positive('Animation Techniques (Online)', 'Animation Techniques, virtual'))

    def test_subject_is_not_attendance(self):
        for title in ['Online Safety Workshop', 'Virtual Reality Workshop', 'Produce Remotely', 'Online']:
            with self.subTest(title=title):
                self.assertIsNone(_explicit_attendance_mode(title))

    def test_unlabelled_listing_still_matches(self):
        self.assertTrue(are_names_similar('Animation Techniques', 'Animation Techniques (Online)'))


if __name__ == '__main__':
    unittest.main()
