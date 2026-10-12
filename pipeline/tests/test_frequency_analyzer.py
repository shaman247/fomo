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



class FrequencyLockTest(unittest.TestCase):
    """crawl_frequency_locked is the per-site cadence override: the analyzer
    must neither back the frequency off nor set a periodicity crawl_after.
    African Film Festival w1547 (posts 0-20 days ahead) is locked at 7d after a
    22d+ cadence missed its Aug 1 / Aug 29 / Sep 12 2026 events."""

    def test_locked_site_is_never_adjusted(self):
        from unittest.mock import Mock
        import frequency_analyzer
        cursor, conn = Mock(), Mock()
        cursor.fetchall.return_value = [(1547, 'African Film Festival NYC', 7, 1, None, 40)]
        results = frequency_analyzer.analyze_frequencies(cursor, conn, website_ids=[1547])
        self.assertEqual((results['skipped'], results['analyzed'], results['adjusted']), (1, 0, 0))
        statements = [c.args[0] for c in cursor.execute.call_args_list]
        self.assertFalse(any('UPDATE websites' in q for q in statements))
        conn.commit.assert_not_called()


class AnalysisWindowTest(unittest.TestCase):
    """BL39: the lookback is a function of the crawl history, never of
    crawl_frequency (the analyzer's own output)."""

    def setUp(self):
        self.today = date(2026, 10, 12)

    def test_reaches_back_to_last_four_crawls(self):
        from frequency_analyzer import _analysis_window
        dates = [self.today - timedelta(days=d) for d in (300, 150, 120, 60, 20)]
        # 4th-newest crawl is 150 days back -> span 151 -> bucketed to 180
        self.assertEqual(_analysis_window(dates, self.today), 180)

    def test_floor_and_cap(self):
        from frequency_analyzer import (
            ANALYSIS_WINDOW_DAYS, ANALYSIS_WINDOW_MAX_DAYS, _analysis_window)
        recent = [self.today - timedelta(days=d) for d in (40, 30, 20, 10)]
        self.assertEqual(_analysis_window(recent, self.today), ANALYSIS_WINDOW_DAYS)
        ancient = [self.today - timedelta(days=d) for d in (900, 800, 700, 600)]
        self.assertEqual(_analysis_window(ancient, self.today), ANALYSIS_WINDOW_MAX_DAYS)
        self.assertEqual(_analysis_window(recent[:3], self.today), ANALYSIS_WINDOW_MAX_DAYS)


# 10th Muses (w4460) as of 2026-10-12: productive May/June crawls, then six
# empty crawls Aug 9 - Sep 22. (days_ago, new_events, horizon, lead_time)
TENTH_MUSES_CRAWLS = [
    (161, 1, 27, 27), (154, 1, 20, 12), (147, 1, 14, None), (141, 0, 12, None),
    (132, 1, 5, None), (126, 0, None, None),
    (64, 0, None, None), (58, 0, None, None), (56, 0, None, None),
    (50, 0, None, None), (44, 0, None, None), (20, 0, None, None),
]


class FakeSite:
    """In-memory stand-in for one website's DB rows, served through the
    analyzer's loader functions so each metric honours the lookback window."""

    def __init__(self, wid, frequency, crawls, today):
        self.wid = wid
        self.frequency = frequency
        self.today = today
        self.crawls = list(crawls)
        self.updated_at = None
        self.evidence_at = None
        self.windows_seen = []
        self._clock = 0
        self.add_crawl_evidence()
        self.touch()  # row last changed after its last crawl...
        self.add_crawl_evidence()  # ...then a new crawl arrived

    def _tick(self):
        self._clock += 1
        from datetime import datetime
        return datetime(2026, 10, 12, 9, 0, self._clock)

    def touch(self):
        self.updated_at = self._tick()

    def add_crawl_evidence(self):
        self.evidence_at = self._tick()

    def _in_window(self, window):
        self.windows_seen.append(window)
        return [c for c in self.crawls if c[0] < window]

    def patches(self):
        from unittest.mock import patch
        import frequency_analyzer as fa
        wid = self.wid
        site = self

        def websites(cursor, ids=None):
            return [{'id': wid, 'name': '10th Muses', 'crawl_frequency': site.frequency,
                     'locked': False, 'crawl_after': None, 'updated_at': site.updated_at}]

        def histories(cursor, ids):
            return {wid: [(site.today - timedelta(days=c[0]), 1) for c in
                          sorted(site.crawls, key=lambda c: -c[0])]}

        def rates(cursor, ids, window):
            crawls = sorted(self._in_window(window), key=lambda c: c[0])  # newest first
            rows = [{'crawled_at': None, 'event_count': 0, 'new_events': c[1]} for c in crawls]
            with_new = sum(1 for r in rows if r['new_events'])
            return {wid: {'total_crawls': len(rows), 'crawls_with_new_events': with_new,
                          'rate': with_new / len(rows) if rows else 0.0, 'crawls': rows}}

        return [
            patch.object(fa, '_load_websites', websites),
            patch.object(fa, '_load_crawl_histories', histories),
            patch.object(fa, '_load_latest_evidence', lambda c, ids: {wid: site.evidence_at}),
            patch.object(fa, '_load_lead_times', lambda c, ids, w: {wid: sorted(
                x[3] for x in site.crawls if x[0] < w and x[3] is not None)}),
            patch.object(fa, '_load_event_horizons', lambda c, ids, w: {wid: sorted(
                x[2] for x in site.crawls if x[0] < w and x[2] is not None)}),
            patch.object(fa, '_load_new_event_rates', rates),
            patch.object(fa, '_load_content_staleness', lambda c, ids, w: {}),
            patch.object(fa, '_load_has_upcoming', lambda c, ids: set()),
        ]

    def cursor(self):
        from unittest.mock import Mock
        site = self
        cursor = Mock()

        def execute(sql, params=()):
            if sql.startswith('UPDATE websites SET crawl_frequency'):
                site.frequency = params[0]
                site.touch()  # ON UPDATE CURRENT_TIMESTAMP
        cursor.execute.side_effect = execute
        return cursor


class FrequencyFixedPointTest(unittest.TestCase):
    """BL39: 10th Muses flipped 24d -> 48d -> 24d on alternating pipeline runs
    with no new crawl, because the lookback (4 x crawl_frequency) changed which
    crawls the analyzer saw: 96 days -> "No new events", 192 days -> horizon."""

    def analyze(self, site, **kwargs):
        from contextlib import ExitStack
        from unittest.mock import Mock
        import frequency_analyzer as fa
        with ExitStack() as stack:
            for p in site.patches():
                stack.enter_context(p)
            return fa.analyze_frequencies(site.cursor(), Mock(), website_ids=[site.wid], **kwargs)

    def test_branch_does_not_depend_on_current_frequency(self):
        today = date.today()
        reasons = []
        for freq in (24, 48):
            site = FakeSite(4460, freq, TENTH_MUSES_CRAWLS, today)
            result = self.analyze(site)
            reasons.append(result['details'][0]['reason'])
            self.assertEqual(set(site.windows_seen), {90})
        self.assertTrue(all(r.startswith('No new events in 6 crawls') for r in reasons), reasons)

    def test_two_analyses_without_new_crawl_are_a_fixed_point(self):
        site = FakeSite(4460, 24, TENTH_MUSES_CRAWLS, date.today())
        first = self.analyze(site)
        self.assertEqual(first['adjusted'], 1)
        after_first = site.frequency
        self.assertEqual(after_first, 48)

        second = self.analyze(site)
        self.assertEqual((second['analyzed'], second['adjusted']), (0, 0))
        self.assertEqual(site.frequency, after_first)

        # A new crawl is new evidence: the site is analyzed again.
        site.crawls.append((0, 0, None, None))
        site.add_crawl_evidence()
        third = self.analyze(site)
        self.assertEqual(third['analyzed'], 1)

    def test_unchanged_recommendation_is_stable_on_rerun(self):
        # Same history, already at the analyzer's answer: re-running with
        # forced re-evaluation repeats the decision instead of drifting.
        steady = [(d, 1, 14, 14) for d in (80, 66, 52, 38, 24, 10)]
        site = FakeSite(1, 14, steady, date.today())
        for _ in range(2):
            result = self.analyze(site, require_new_evidence=False)
            self.assertEqual(result['adjusted'], 0, result['details'])
            self.assertEqual(site.frequency, 14)

    def test_empty_scope_analyzes_nothing(self):
        from unittest.mock import Mock
        import frequency_analyzer as fa
        cursor = Mock()
        results = fa.analyze_frequencies(cursor, Mock(), website_ids=[])
        self.assertEqual(results['analyzed'], 0)
        cursor.execute.assert_not_called()

if __name__ == '__main__':
    unittest.main()
