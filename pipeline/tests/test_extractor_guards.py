"""Tests for extractor.py reliability guards (variance retry, max_batches
auto-bump) and the fix_recurring_spans course-shape classifier."""

import importlib.util
import os
import sys
import unittest
from datetime import date

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extractor import (
    PreparedExtraction,
    _variance_retry_reason,
    _maybe_auto_bump_max_batches,
    _normalize_extraction_response,
    AUTO_MAX_BATCHES_CEILING,
    DEFAULT_MAX_BATCHES,
)


class FakeCursor:
    """Routes the two _variance_retry_reason queries to canned results."""

    def __init__(self, current_row, history_rows):
        self.current_row = current_row
        self.history_rows = history_rows
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.current_row

    def fetchall(self):
        return self.history_rows


class FakeConnection:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class TestVarianceRetryReason(unittest.TestCase):
    HISTORY = [(20, 60000), (22, 61000), (18, 59000), (21, 60500), (19, 60200)]

    def test_collapse_on_stable_content_triggers_retry(self):
        cur = FakeCursor((42, 60000), self.HISTORY)
        reason = _variance_retry_reason(cur, 1, new_count=5)
        self.assertIsNotNone(reason)
        self.assertIn("5 events", reason)

    def test_healthy_count_no_retry(self):
        cur = FakeCursor((42, 60000), self.HISTORY)
        self.assertIsNone(_variance_retry_reason(cur, 1, new_count=15))

    def test_exact_half_median_no_retry(self):
        # median count is 20; 10 == 20 * 0.5 is NOT below half
        cur = FakeCursor((42, 60000), self.HISTORY)
        self.assertIsNone(_variance_retry_reason(cur, 1, new_count=10))

    def test_content_size_changed_no_retry(self):
        # Page shrank 50% — a real change, not extraction variance
        cur = FakeCursor((42, 30000), self.HISTORY)
        self.assertIsNone(_variance_retry_reason(cur, 1, new_count=5))

    def test_too_little_history_no_retry(self):
        cur = FakeCursor((42, 60000), self.HISTORY[:2])
        self.assertIsNone(_variance_retry_reason(cur, 1, new_count=5))

    def test_tiny_site_no_retry(self):
        # median 3 < 4: too noisy to judge
        cur = FakeCursor((42, 2700), [(3, 2700), (3, 2700), (2, 2700)])
        self.assertIsNone(_variance_retry_reason(cur, 1, new_count=1))

    def test_missing_crawl_result_no_retry(self):
        cur = FakeCursor(None, self.HISTORY)
        self.assertIsNone(_variance_retry_reason(cur, 1, new_count=0))

    def test_cursor_error_fails_open(self):
        class BoomCursor:
            def execute(self, *a, **k):
                raise RuntimeError("boom")
        self.assertIsNone(_variance_retry_reason(BoomCursor(), 1, new_count=0))


class TestMaybeAutoBumpMaxBatches(unittest.TestCase):
    def _prep(self, max_batches, website_id=99):
        return PreparedExtraction(
            crawl_result_id=1, website_name="Test Site", extraction_type='chunked',
            max_batches=max_batches, website_id=website_id,
        )

    def test_bumps_default_capped_site(self):
        cur, conn = FakeCursor(None, []), FakeConnection()
        new_cap = _maybe_auto_bump_max_batches(cur, conn, self._prep(3), batches_needed=10)
        self.assertEqual(new_cap, 11)
        self.assertEqual(conn.commits, 1)
        self.assertIn("UPDATE websites SET max_batches", cur.executed[0][0])
        self.assertEqual(cur.executed[0][1], (11, 99))

    def test_respects_deliberate_throttle_below_default(self):
        cur, conn = FakeCursor(None, []), FakeConnection()
        self.assertIsNone(_maybe_auto_bump_max_batches(cur, conn, self._prep(2), batches_needed=10))
        self.assertEqual(cur.executed, [])

    def test_clamps_to_ceiling(self):
        cur, conn = FakeCursor(None, []), FakeConnection()
        new_cap = _maybe_auto_bump_max_batches(cur, conn, self._prep(DEFAULT_MAX_BATCHES), batches_needed=100)
        self.assertEqual(new_cap, AUTO_MAX_BATCHES_CEILING)

    def test_no_bump_when_already_at_ceiling(self):
        cur, conn = FakeCursor(None, []), FakeConnection()
        self.assertIsNone(_maybe_auto_bump_max_batches(
            cur, conn, self._prep(AUTO_MAX_BATCHES_CEILING), batches_needed=100))

    def test_no_bump_without_website_id(self):
        cur, conn = FakeCursor(None, []), FakeConnection()
        self.assertIsNone(_maybe_auto_bump_max_batches(
            cur, conn, self._prep(3, website_id=None), batches_needed=10))

    def test_no_bump_when_not_needed(self):
        cur, conn = FakeCursor(None, []), FakeConnection()
        self.assertIsNone(_maybe_auto_bump_max_batches(cur, conn, self._prep(10), batches_needed=8))


class TestNormalizeExtractionResponse(unittest.TestCase):
    def test_valid(self):
        text = '{"events": [{"name": "A", "occurrences": [["2026-01-01"]]}]}'
        out, n, occ = _normalize_extraction_response(text)
        self.assertEqual((out, n, occ), (text, 1, 1))

    def test_empty_and_invalid(self):
        self.assertEqual(_normalize_extraction_response(''), ('{"events": []}', 0, 0))
        self.assertEqual(_normalize_extraction_response('not json'), ('{"events": []}', 0, 0))


def _load_fix_recurring_spans():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), 'scripts', 'fix_recurring_spans.py')
    spec = importlib.util.spec_from_file_location('fix_recurring_spans', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestClassifyCourse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frs = _load_fix_recurring_spans()

    @staticmethod
    def _occ(start, end, st='', et=''):
        return {'start_date': start, 'end_date': end, 'start_time': st, 'end_time': et}

    def test_bhakti_shape_timed_span(self):
        # Aug 11 -> Dec 15 2026 are both Tuesdays; 6:30pm class
        occ = [self._occ(date(2026, 8, 11), date(2026, 12, 15), '6:30pm', '8:30pm')]
        verdict, info = self.frs.classify_course('Bhakti Sastri Module 4', occ)
        self.assertEqual(verdict, 'course_weekly')
        dates = self.frs.planned_dates('course_weekly', info)
        self.assertEqual(len(dates), 19)
        self.assertEqual(dates[0], date(2026, 8, 11))
        self.assertEqual(dates[-1], date(2026, 12, 15))
        self.assertTrue(all(d.weekday() == 1 for d in dates))

    def test_bisr_shape_recurrence_keyword_no_time(self):
        # Jul 6 -> Jul 27 2026 are both Mondays; no time but explicit "weekly"
        occ = [self._occ(date(2026, 7, 6), date(2026, 7, 27))]
        verdict, info = self.frs.classify_course(
            'Literature and Catastrophe', occ, 'A four-week course meeting weekly.')
        self.assertEqual(verdict, 'course_weekly')
        self.assertEqual(len(self.frs.planned_dates('course_weekly', info)), 4)

    def test_program_keyword_alone_does_not_corroborate(self):
        # Daily summer programs match PROGRAM_RE but are NOT weekly — "program"/
        # "camp" wording without a time or explicit recurrence keyword must skip
        occ = [self._occ(date(2026, 7, 6), date(2026, 8, 3))]
        verdict, _ = self.frs.classify_course(
            '2026 International Summer Program', occ, 'A four-week intensive program for students.')
        self.assertEqual(verdict, 'skip')

    def test_exhibition_keyword_vetoes(self):
        occ = [self._occ(date(2026, 8, 11), date(2026, 12, 15), '6:30pm')]
        verdict, _ = self.frs.classify_course('Group Show', occ, 'An exhibition on view daily.')
        self.assertEqual(verdict, 'skip')

    def test_different_weekday_endpoints_skip(self):
        occ = [self._occ(date(2026, 8, 11), date(2026, 12, 14), '6:30pm')]
        verdict, _ = self.frs.classify_course('Some Class', occ)
        self.assertEqual(verdict, 'skip')

    def test_no_time_no_keyword_skip(self):
        occ = [self._occ(date(2026, 7, 6), date(2026, 7, 27))]
        verdict, _ = self.frs.classify_course('Some Long Thing', occ)
        self.assertEqual(verdict, 'skip')

    def test_multiple_occurrences_skip(self):
        occ = [self._occ(date(2026, 7, 6), date(2026, 7, 27), '6pm'),
               self._occ(date(2026, 7, 6), None, '6pm')]
        verdict, _ = self.frs.classify_course('Weekly Course', occ)
        self.assertEqual(verdict, 'skip')

    def test_span_too_long_skip(self):
        occ = [self._occ(date(2026, 1, 6), date(2026, 12, 29), '6pm')]  # 358d
        verdict, _ = self.frs.classify_course('Weekly Course', occ)
        self.assertEqual(verdict, 'skip')

    def test_one_week_span_skip(self):
        occ = [self._occ(date(2026, 7, 6), date(2026, 7, 13), '6pm')]  # 7d < 14
        verdict, _ = self.frs.classify_course('Weekly Course', occ)
        self.assertEqual(verdict, 'skip')


if __name__ == '__main__':
    unittest.main()
