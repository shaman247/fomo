"""Two teams of one sport must not merge through a shared '<Sport>' suffix.

Regression 2026-10-01: NYC Tourism (w3524) lists "New York Giants Football" and
"New York Jets Football" at MetLife Stadium over overlapping season envelopes;
3 of 4 shared words cleared the 0.75 asymmetric-containment tier and the Jets
page merged into the Giants event (ev252897).
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger


class TeamSportNameTests(unittest.TestCase):
    def test_different_teams_same_sport_do_not_match(self):
        pairs = (
            ('New York Giants Football', 'New York Jets Football'),
            ('New York Yankees Baseball', 'New York Mets Baseball'),
            ('New York Rangers Hockey', 'New York Islanders Hockey'),
        )
        for a, b in pairs:
            with self.subTest(a=a, b=b):
                self.assertFalse(merger.are_names_similar(a, b))
                self.assertFalse(merger.are_names_similar(b, a))

    def test_same_team_variants_still_match(self):
        pairs = (
            ('New York Giants Football', 'New York Giants Football'),
            ('New York Giants Football', 'NY Giants Football'),
            ('New York Mets Baseball', 'New York Metz Baseball'),   # spelling slip
            ('New York Yankees Baseball', 'New York Yankees Baseball Game'),
        )
        for a, b in pairs:
            with self.subTest(a=a, b=b):
                self.assertTrue(merger.are_names_similar(a, b))

    def test_guard_requires_trailing_sport_noun(self):
        self.assertFalse(merger._team_names_differ(
            'Art Omi NYC Benefit', 'Art Omi Upstate Benefit', '', ''))
        self.assertFalse(merger._team_names_differ(
            'Monday Night Football', 'Thursday Night Football', '', ''))


if __name__ == '__main__':
    unittest.main()
