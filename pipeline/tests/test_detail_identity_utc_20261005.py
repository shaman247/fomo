"""detail_identity._day must read explicit-offset instants in the city's zone.

Partiful JSON-LD publishes startDate as UTC ('...T03:00:00.000Z'); taking the
leading 10 chars made every 8-11 PM ET session read as the next day, and the
detail guard rejected the page as "schedule is disjoint" (2026-10-04, 8 cases).
"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import detail_identity as di


class DayParsingTests(unittest.TestCase):
    def test_utc_z_evening_session_maps_to_local_date(self):
        self.assertEqual(di._day('2026-10-10T03:00:00.000Z'), date(2026, 10, 9))

    def test_explicit_utc_offset_maps_to_local_date(self):
        self.assertEqual(di._day('2026-10-10T00:30:00+00:00'), date(2026, 10, 9))

    def test_local_offset_keeps_its_calendar_date(self):
        self.assertEqual(di._day('2026-10-09T23:00:00-04:00'), date(2026, 10, 9))
        self.assertEqual(di._day('2026-10-09T23:00:00-0400'), date(2026, 10, 9))

    def test_naive_datetime_keeps_publisher_date(self):
        self.assertEqual(di._day('2026-10-09T23:30:00'), date(2026, 10, 9))

    def test_plain_date_and_garbage(self):
        self.assertEqual(di._day('2026-10-09'), date(2026, 10, 9))
        self.assertIsNone(di._day('not a date'))
        self.assertIsNone(di._day(None))

    def test_daytime_utc_instant_is_unchanged(self):
        self.assertEqual(di._day('2026-10-09T17:00:00Z'), date(2026, 10, 9))


if __name__ == '__main__':
    unittest.main()
