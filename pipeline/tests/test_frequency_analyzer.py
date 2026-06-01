"""Tests for frequency_analyzer periodicity detection."""

import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frequency_analyzer import (
    PERIODICITY_LEAD_BUFFER_DAYS,
    _detect_periodicity_from_history,
    _find_active_windows,
)


def _build_history(start, entries):
    """
    Build a (date, event_count) list from a compact specification.

    `entries` is a list of (offset_days, event_count) — offset relative to start.
    """
    return [(start + timedelta(days=off), ec) for off, ec in entries]


class FindActiveWindowsTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_find_active_windows([]), [])

    def test_all_zero(self):
        start = date(2026, 1, 1)
        hist = [(start + timedelta(days=i), 0) for i in range(10)]
        self.assertEqual(_find_active_windows(hist), [])

    def test_single_active_window(self):
        start = date(2026, 1, 1)
        hist = _build_history(start, [
            (0, 0), (7, 5), (14, 3), (21, 1), (28, 0), (35, 0),
        ])
        windows = _find_active_windows(hist)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0], (start + timedelta(days=7), start + timedelta(days=21)))

    def test_brief_dormant_gap_does_not_split(self):
        # 14-day gap is under PERIODICITY_WINDOW_GAP_TOLERANCE_DAYS=21 → window stays open
        start = date(2026, 1, 1)
        hist = _build_history(start, [
            (0, 5), (7, 3), (14, 0), (21, 0), (28, 4), (35, 2),
        ])
        windows = _find_active_windows(hist)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0][0], start)
        self.assertEqual(windows[0][1], start + timedelta(days=35))

    def test_long_dormant_gap_splits(self):
        start = date(2026, 1, 1)
        hist = _build_history(start, [
            (0, 5), (7, 3),
            (14, 0), (21, 0), (28, 0), (35, 0), (42, 0),  # 5-week gap (35d > 21d)
            (49, 4), (56, 2),
        ])
        windows = _find_active_windows(hist)
        self.assertEqual(len(windows), 2)


class DetectPeriodicityTest(unittest.TestCase):
    """Tests for the pure periodicity detector. Today is fixed for determinism."""

    def setUp(self):
        self.today = date(2027, 5, 1)

    def test_no_history(self):
        self.assertIsNone(_detect_periodicity_from_history([], self.today))

    def test_insufficient_crawls(self):
        start = date(2026, 1, 1)
        hist = _build_history(start, [(i * 30, 0) for i in range(5)])  # only 5 crawls
        self.assertIsNone(_detect_periodicity_from_history(hist, self.today))

    def test_insufficient_history_span(self):
        # 12 crawls but only spans 60 days — below MIN_HISTORY_DAYS=120
        start = date(2027, 3, 1)
        hist = _build_history(start, [(i * 5, 1 if i < 5 else 0) for i in range(12)])
        self.assertIsNone(_detect_periodicity_from_history(hist, self.today))

    def test_single_active_window_no_pattern(self):
        # One active window, no recurrence → can't infer periodicity
        start = date(2026, 1, 1)
        hist = _build_history(start, [
            (0, 0), (30, 0), (60, 5), (90, 3), (120, 0), (150, 0), (180, 0),
            (210, 0), (240, 0), (270, 0), (300, 0), (330, 0),
        ])
        self.assertIsNone(_detect_periodicity_from_history(hist, self.today))

    def test_annual_pattern_currently_dormant(self):
        # Two active windows ~365 days apart, currently dormant → detect annual cycle.
        # History runs Apr 1 2025 → Sep 15 2026 (~530 days); "today" is Sep 16 2026.
        start = date(2025, 4, 1)
        today = date(2026, 9, 16)
        hist = []
        i = 0
        while True:
            d = start + timedelta(days=i)
            if d > today:
                break
            active = (
                (d.month == 4 and d.day >= 20) or
                (d.month == 5 and d.day <= 15)
            )
            hist.append((d, 10 if active else 0))
            i += 7

        result = _detect_periodicity_from_history(hist, today=today)
        self.assertIsNotNone(result)
        self.assertEqual(result['total_windows'], 2)
        self.assertGreaterEqual(result['cycles_observed'], 1)
        # period should be ~365 days
        self.assertGreater(result['period_days'], 330)
        self.assertLess(result['period_days'], 400)
        # next_predicted_start should be ~April 2027
        self.assertEqual(result['next_predicted_start'].year, 2027)
        self.assertEqual(result['next_predicted_start'].month, 4)
        # crawl_after = next_predicted - lead buffer
        expected_crawl_after = result['next_predicted_start'] - timedelta(days=PERIODICITY_LEAD_BUFFER_DAYS)
        self.assertEqual(result['crawl_after'], expected_crawl_after)

    def test_annual_pattern_currently_active_returns_none(self):
        # Same annual pattern but the most recent crawls are active → don't set crawl_after
        start = date(2025, 4, 1)
        today = date(2027, 4, 25)  # in the middle of a new active window
        hist = []
        i = 0
        while True:
            d = start + timedelta(days=i)
            if d > today:
                break
            active = (
                (d.month == 4 and d.day >= 20) or
                (d.month == 5 and d.day <= 15)
            )
            hist.append((d, 10 if active else 0))
            i += 7

        result = _detect_periodicity_from_history(hist, today=today)
        self.assertIsNone(result, "Should not set crawl_after when site is currently active")

    def test_quarterly_pattern_detected(self):
        # Quarterly cycle (~90 days). 3 active windows at days 0, 90, 180.
        # Last active window starts at day 180 (Jun 30); predicted next at day 270
        # (~Sep 28). "Today" is day 220 (~Aug 9) — currently dormant, predicted
        # reactivation in the near future so crawl_after = ~Aug 29 > today.
        start = date(2025, 1, 1)
        today = start + timedelta(days=220)
        hist = []
        for i in range(0, 221, 7):
            d = start + timedelta(days=i)
            # Active for 7-14 days at start of each quarter
            active = i in (0, 7, 91, 98, 182, 189)
            hist.append((d, 5 if active else 0))

        result = _detect_periodicity_from_history(hist, today=today)
        self.assertIsNotNone(result)
        self.assertEqual(result['total_windows'], 3)
        self.assertGreater(result['period_days'], 60)
        # crawl_after must be strictly in the future
        self.assertGreater(result['crawl_after'], today)

    def test_irregular_gaps_not_periodic(self):
        # Active windows with inconsistent gaps → not periodic
        start = date(2025, 1, 1)
        hist = []
        for i in range(0, 800, 14):
            d = start + timedelta(days=i)
            # Active on days 0, 100, 300 (irregular gaps 100, 200)
            active = i in (0, 7, 100, 107, 300, 307)
            hist.append((d, 5 if active else 0))

        result = _detect_periodicity_from_history(hist, today=date(2027, 5, 1))
        self.assertIsNone(result, "Irregular gaps shouldn't be treated as periodic")

    def test_predicted_in_past_returns_none(self):
        # Periodicity detected, but the predicted next active date is already past
        # (we're way overdue for reactivation) — the site should be crawled normally.
        start = date(2024, 4, 1)
        hist = []
        for i in range(0, 800, 14):
            d = start + timedelta(days=i)
            active = (
                (d.year == 2024 and d.month == 4 and d.day >= 20) or
                (d.year == 2024 and d.month == 5 and d.day <= 15) or
                (d.year == 2025 and d.month == 4 and d.day >= 20) or
                (d.year == 2025 and d.month == 5 and d.day <= 15)
            )
            hist.append((d, 10 if active else 0))

        # "Today" is well past the predicted 2026 reactivation
        result = _detect_periodicity_from_history(hist, today=date(2026, 8, 1))
        self.assertIsNone(result, "Should not return a past crawl_after")


if __name__ == '__main__':
    unittest.main()
