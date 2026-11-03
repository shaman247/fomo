"""Tests for the "Submit <work> for ..." gap found on 2026-11-03.

e312894 "Submit Art and Photography for Lenoir Nature Center's Exhibit"
(w4718 Westchester County Parks) is an artwork drop-off for an exhibit, not an
attendable event. It said "Submit" rather than "open call", so no name rule
fired and it was hand-suppressed at classification. The same start-anchored
shape covers "Submit by <date> | <show>" entry deadlines (three such rows were
already hand-suppressed). Corpus-checked over all 73 titles holding
"submit"/"drop-off": 4 matches, 0 false positives.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import is_obvious_non_event


class TestSubmitIntake(unittest.TestCase):
    def test_submit_work_for_an_exhibit(self):
        self.assertTrue(is_obvious_non_event(
            "Submit Art and Photography for Lenoir Nature Center's Exhibit",
            'Drop-off for nature-related art and photography for the exhibit.'))
        self.assertTrue(is_obvious_non_event('Submit Your Poems for the Anthology', ''))

    def test_submit_by_deadline_listing(self):
        self.assertTrue(is_obvious_non_event('Submit by Oct. 19 | Figuratively Speaking', ''))

    def test_real_events_containing_submit_survive(self):
        for name in ['I Cannot Submit to Injustices: Martin Sostre’s Continuous Struggle',
                     'Primary Election Day · polls 6am–9pm · last day to submit mail ballots',
                     'Navigate Training (For Faculty) – Submitting Progress Reports',
                     'Weekend Table Reads Marathon (Sat through Sun) submit a script or read a part!',
                     'Photography Exhibit Opening Reception']:
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, ''))


if __name__ == '__main__':
    unittest.main()
