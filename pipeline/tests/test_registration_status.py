"""Closed enrollment does not turn a scheduled program into a date marker."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from processor import normalize_registration_status, is_obvious_non_event


class RegistrationStatusTests(unittest.TestCase):
    def test_reviewed_queens_programs_survive_with_visible_status(self):
        for title in ('Climate Week NYC: From Floods to Future Plans',
                      'Free Immigration & Citizenship Consultation Day'):
            raw = 'REGISTRATION CLOSED: ' + title
            self.assertEqual(normalize_registration_status(raw), title + ' (Registration Closed)')
            self.assertFalse(is_obvious_non_event(raw, 'Registration for this program has closed.'))

    def test_normalization_is_idempotent_and_retains_nested_title_colon(self):
        title = normalize_registration_status(' Registration Closed : Climate Week: Floods ')
        self.assertEqual(title, 'Climate Week: Floods (Registration Closed)')
        self.assertEqual(normalize_registration_status(title), title)
        self.assertEqual(normalize_registration_status('REGISTRATION CLOSED: ' + title), title)

    def test_bare_status_and_registration_windows_are_still_not_events(self):
        for title in ('Registration Closed', 'Registration Closed:',
                      'Registration closes Friday', 'Registration open: Summer Camp',
                      'Summer Camp Registration Now Open'):
            self.assertEqual(normalize_registration_status(title), title)
            self.assertTrue(is_obvious_non_event(title, ''))

    def test_closed_enrollment_does_not_exempt_other_junk(self):
        for title in ('Call for Submissions', 'Museum Closed', 'Cancelled: Poetry Workshop'):
            self.assertTrue(is_obvious_non_event('REGISTRATION CLOSED: ' + title, ''))
