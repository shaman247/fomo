"""Tests for the private-audience rules added 2026-08-20.

Two closed-audience events reached the live map and were reported by the user:

    220070  AI Incubator for Solopreneurs | Work Session | MEMBERS ONLY
            (w662 Fabrik DUMBO)
    207564  New Student Orientation                 (w536 Pratt Institute)

Both are real, attendable occasions — but not attendable by the general
public, so they don't belong on the map. Each capped a long hand-suppression
trail: Fabrik members-only rows alone had been suppressed at least eight times
(90906, 157004, 173129, 197142, 206565, 210142, 223832, 224595), and Pratt's
orientation cluster (207563-207566) had been individually reviewed.

Measured over all 193,909 events (2026-08-20):

* "member(s) only" in the NAME: 146 matches, 22 live — every one a true
  members-only occasion (museum member tours/previews, social clubs, coworking
  members' sessions) EXCEPT e5405, a public NYE party at a West Village lounge
  literally NAMED "Members Only". The venue veto exists for that one shape.
* "member(s) exclusive" in the NAME: 20 matches, 0 live, all true.
* "Student(s) Orientation" literal phrase in the NAME: 3 matches, all true.
* "Orientation" in the NAME + a student audience in the BODY: 6 matches, all
  school orientations for enrolled students or their families (Pratt, NYU),
  0 false positives.

Deliberate boundaries, pinned below — do not loosen without re-measuring:

* A "members only" phrase in the DESCRIPTION is NOT a junk signal. Museums
  advertise a members-only preview day inside the body of a fully public
  exhibition, and "become a member" upsell copy is everywhere.
* Bare "Member" without only/exclusive ("New Member Lunch", "Member
  Appreciation Night") stays editorial — too ambiguous for the auto-drop.
* Volunteer/docent orientations are PUBLIC (anyone may show up to become one)
  and must survive; the academic-milestone veto already spares "orientation"
  for the same reason.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import is_obvious_non_event

BLANK = 'No description available.'


class TestMembersOnly(unittest.TestCase):

    def test_fabrik_members_only_work_session(self):
        """220070 — the reported Fabrik DUMBO row."""
        self.assertTrue(is_obvious_non_event(
            'AI Incubator for Solopreneurs | Work Session | MEMBERS ONLY',
            'A members-only working session in an 8-week incubator series.'))

    def test_members_only_name_shapes_across_the_corpus(self):
        for name in (
            'Members-Only Tour: Indigenous American Art at the Met',
            '[MEMBERS ONLY] Revisiting U.S. Interests in Asia',
            'Lunchtime Spanish Chat, members only!',
            'Birding in Peace: Late-Risers Edition (Members Only)',
            'Members Only Hour',
            '[member-only] CNC Router: Basic Use & Safety',
            'Jazz & Mingle (Member-Only Event)',
        ):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, BLANK))
                # Name-only: must fire without any description at all.
                self.assertTrue(is_obvious_non_event(name))

    def test_member_exclusive_name_shapes(self):
        for name in (
            'Substack Creative Club – Fabrik Member Exclusive',
            'Angelika Members Exclusive Mystery Screening: August 5',
            'Member-Exclusive Book Club: The Mind Electric',
        ):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name))

    def test_venue_named_members_only_is_spared(self):
        """e5405 — a public party AT a lounge named "Members Only"."""
        self.assertFalse(is_obvious_non_event(
            "New Year's Eve @ Members Only West Village Lounge", BLANK))
        self.assertFalse(is_obvious_non_event(
            '80s Night at Members Only Lounge', BLANK))

    def test_members_only_in_description_is_not_a_signal(self):
        """A public exhibition advertising a members-only preview day."""
        self.assertFalse(is_obvious_non_event(
            "Sean Kenney's Nature Connects: Opening Weekend",
            'Opens to the public Saturday. Members-only preview Friday — '
            'become a member today for early access!'))

    def test_bare_member_events_stay_editorial(self):
        for name in ('New Member Lunch', 'Member Appreciation Night',
                     'Monthly Member Happy Hour'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, BLANK))


class TestStudentOrientation(unittest.TestCase):

    def test_pratt_new_student_orientation(self):
        """207564 — the reported Pratt row; name-only arm."""
        self.assertTrue(is_obvious_non_event('New Student Orientation'))
        self.assertTrue(is_obvious_non_event(
            'New Student Orientation',
            'New student orientation is an exciting time at Pratt. Whether '
            'you are a first year student, a graduate student, or a '
            'transfer/Pratt Munson relocation student, we have a '
            'comprehensive program for you.'))

    def test_student_orientation_phrase_variants(self):
        for name in (
            'History of Art and Design Student Orientation',
            'Performance Studies New Student Orientation 2026',
            "Students' Orientation",
        ):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name))

    def test_orientation_with_student_audience_in_body(self):
        """207565 — no literal phrase in the name; the body carries it."""
        self.assertTrue(is_obvious_non_event(
            'Welcome and Orientation Day MFA Fashion Collection + '
            'Communication',
            'A welcome and orientation day for MFA Fashion Collection + '
            'Communication students.'))

    def test_public_orientations_survive(self):
        for name, desc in (
            ('Teen Volunteer Orientation',
             'Learn how to volunteer at the library this summer.'),
            ('Grassroots Volunteer Orientation (evening session)',
             'An orientation for new Riverside Park volunteers.'),
            ('Docent Volunteer Orientation (virtual)', BLANK),
            ('In-Person: Free Mindfulness-Based Stress Reduction (MBSR) '
             'Orientation', BLANK),
            # "students" in the open-enrollment sense — the all-levels veto.
            ('Tango Orientation Class',
             'Students of all levels welcome, no experience required.'),
            # Bare "Orientation" name with a non-student body stays alive.
            ('Laser Cutter Orientation',
             'Get certified to use the makerspace laser cutter.'),
        ):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))


if __name__ == '__main__':
    unittest.main()
