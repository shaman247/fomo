"""Tests for db.get_coverage_drop_report — the relative-drop detector.

Motivating defect (2026-08-24, w3 NYPL): the FIRST of nine crawl URLs came back
with 940 chars instead of ~1.1 MB — a cold-start/hydration race on the first
request of the run — so the site stored `status='processed'` with
`event_count=179` instead of ~950 and **nothing flagged it**. The next run was
fine (1,075 events), so the failure is intermittent and order-dependent. Only
the 14-day detail-crawl grace kept ~770 live events off the archival pile.

The check is a REPORT, never a gate: a 90-day backtest put ~21% of its hits on
legitimate drops (a season ending, a calendar clearing). These tests therefore
pin two things in equal measure — that the real failure shapes fire, and that
the ordinary ones stay silent.

Like test_archival.py, these run the *real* MySQL query text against in-memory
SQLite through that module's dialect shim, so the SQL under test is the SQL
db.py ships.
"""

import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
from tests.test_archival import _ShimCursor

SCHEMA = """
CREATE TABLE websites (id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE crawl_results (
    id INTEGER PRIMARY KEY, crawl_run_id INTEGER, website_id INTEGER,
    status TEXT, event_count INTEGER, crawled_content TEXT,
    crawled_at TEXT DEFAULT (datetime('now')));
"""


class CoverageDropReportTest(unittest.TestCase):

    def setUp(self):
        self.connection = sqlite3.connect(':memory:')
        self.connection.executescript(SCHEMA)
        self.cursor = _ShimCursor(self.connection)
        self._next_id = 1

    def tearDown(self):
        self.connection.close()

    # ── fixture helpers ──
    def add_website(self, website_id, name=None):
        self.connection.execute(
            "INSERT INTO websites (id, name) VALUES (?, ?)",
            (website_id, name or f"Website {website_id}"))

    def add_crawl(self, website_id, event_count, run_id=1, status='processed',
                  chars=1000):
        """A crawl of `website_id`. Rows are inserted in ascending id, which is
        what the previous-crawl subquery orders on (crawl_results rows are
        created per (run, website) and updated in place, so id order IS crawl
        order)."""
        crawl_id = self._next_id
        self._next_id += 1
        self.connection.execute(
            "INSERT INTO crawl_results (id, crawl_run_id, website_id, status,"
            " event_count, crawled_content) VALUES (?, ?, ?, ?, ?, ?)",
            (crawl_id, run_id, website_id, status, event_count, 'x' * chars))
        return crawl_id

    def report(self, **kwargs):
        return db.get_coverage_drop_report(self.cursor, **kwargs)

    # ── the motivating case ──
    def test_nypl_partial_crawl_fires(self):
        """948 → 179 is the defect this whole check exists for."""
        self.add_website(3, "New York Public Library")
        self.add_crawl(3, 948, run_id=1, chars=686465)
        self.add_crawl(3, 179, run_id=2, chars=940)

        rows = self.report(crawl_run_id=2)
        self.assertEqual(len(rows), 1)
        website_id, name, now_count, prev_count = rows[0][:4]
        self.assertEqual((website_id, now_count, prev_count), (3, 179, 948))
        self.assertEqual(name, "New York Public Library")

    def test_content_length_returned_for_triage(self):
        """Content length is a triage hint, not a filter: a collapsed page next
        to the drop means partial crawl, a full page means the calendar really
        emptied. Both must be reported, with their sizes."""
        self.add_website(3)
        self.add_crawl(3, 948, run_id=1, chars=686465)
        self.add_crawl(3, 179, run_id=2, chars=940)
        self.add_website(9)
        self.add_crawl(9, 100, run_id=1, chars=50000)   # season ended:
        self.add_crawl(9, 4, run_id=2, chars=50000)     # page still full size

        rows = self.report(crawl_run_id=2)
        sizes = {r[0]: (r[4], r[5]) for r in rows}
        self.assertEqual(sizes[3], (940, 686465))
        self.assertEqual(sizes[9], (50000, 50000))

    # ── shapes that must fire ──
    def test_drop_to_zero_fires(self):
        """The Cloudflare-challenge / extraction-outage shape: 0 events stored
        as a healthy crawl."""
        self.add_website(1)
        self.add_crawl(1, 430, run_id=1)
        self.add_crawl(1, 0, run_id=2)
        self.assertEqual(len(self.report(crawl_run_id=2)), 1)

    def test_small_site_wiped_out_still_fires(self):
        """A 20-event site going to zero is below the sketch's `prev > 20`
        floor but is a real wipeout. min_absolute_drop is what filters jitter,
        so this must survive."""
        self.add_website(1)
        self.add_crawl(1, 20, run_id=1)
        self.add_crawl(1, 0, run_id=2)
        self.assertEqual(len(self.report(crawl_run_id=2)), 1)

    def test_ordered_by_absolute_loss(self):
        """Biggest coverage loss first — the report is truncated, so the rows
        that matter most have to be at the top."""
        for wid, prev, now in ((1, 100, 10), (2, 900, 100), (3, 60, 5)):
            self.add_website(wid)
            self.add_crawl(wid, prev, run_id=1)
            self.add_crawl(wid, now, run_id=2)
        self.assertEqual([r[0] for r in self.report(crawl_run_id=2)], [2, 1, 3])

    # ── shapes that must stay silent ──
    def test_small_absolute_drop_is_silent(self):
        """20 → 8 is a 60% drop but only 12 events; small-site extraction
        jitter is the single largest noise source and must not print."""
        self.add_website(1)
        self.add_crawl(1, 20, run_id=1)
        self.add_crawl(1, 8, run_id=2)
        self.assertEqual(self.report(crawl_run_id=2), [])

    def test_half_drop_boundary(self):
        """Exactly half is not a collapse; one below half is."""
        self.add_website(1)
        self.add_crawl(1, 100, run_id=1)
        self.add_crawl(1, 50, run_id=2)
        self.assertEqual(self.report(crawl_run_id=2), [])

        self.add_website(2)
        self.add_crawl(2, 100, run_id=1)
        self.add_crawl(2, 49, run_id=2)
        self.assertEqual(len(self.report(crawl_run_id=2)), 1)

    def test_growth_is_silent(self):
        self.add_website(1)
        self.add_crawl(1, 10, run_id=1)
        self.add_crawl(1, 500, run_id=2)
        self.assertEqual(self.report(crawl_run_id=2), [])

    def test_no_baseline_is_silent(self):
        """A website's first-ever crawl has nothing to compare against, and a
        previous crawl of 0 events gives no meaningful ratio."""
        self.add_website(1)
        self.add_crawl(1, 0, run_id=1)
        self.add_crawl(1, 0, run_id=2)
        self.assertEqual(self.report(crawl_run_id=2), [])

        self.add_website(2)
        first = self.add_crawl(2, 5, run_id=2)
        self.assertTrue(first)
        self.assertEqual(self.report(crawl_run_id=2), [])

    # ── baseline selection ──
    def test_baseline_skips_non_processed_crawls(self):
        """A failed crawl in between carries no event_count worth comparing to;
        the baseline must be the last *processed* crawl."""
        self.add_website(1)
        self.add_crawl(1, 400, run_id=1)
        self.add_crawl(1, 0, run_id=2, status='failed')
        self.add_crawl(1, 30, run_id=3)

        rows = self.report(crawl_run_id=3)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][3], 400)          # compared against 400, not 0

    def test_unprocessed_current_crawl_is_silent(self):
        """A crawl still in flight has no final count — comparing it would fire
        on every run in progress."""
        self.add_website(1)
        self.add_crawl(1, 400, run_id=1)
        self.add_crawl(1, 3, run_id=2, status='extracted')
        self.assertEqual(self.report(crawl_run_id=2), [])

    def test_run_scope_excludes_other_runs(self):
        """Scoping to this run must not re-report last run's drop every time."""
        self.add_website(1)
        self.add_crawl(1, 400, run_id=1)
        self.add_crawl(1, 20, run_id=2)     # the drop
        self.add_crawl(1, 22, run_id=3)     # still low, but no NEW collapse

        self.assertEqual(len(self.report(crawl_run_id=2)), 1)
        self.assertEqual(self.report(crawl_run_id=3), [])

    def test_day_window_scope_without_run_id(self):
        """The crawl_run_id-less path (ad-hoc use) filters on crawled_at."""
        self.add_website(1)
        self.add_crawl(1, 400, run_id=1)
        self.add_crawl(1, 5, run_id=2)
        self.assertEqual(len(self.report(since_days=1)), 1)

        self.connection.execute(
            "UPDATE crawl_results SET crawled_at = datetime('now', '-9 day')")
        self.assertEqual(self.report(since_days=1), [])
        self.assertEqual(len(self.report(since_days=30)), 1)

    def test_thresholds_are_tunable(self):
        self.add_website(1)
        self.add_crawl(1, 100, run_id=1)
        self.add_crawl(1, 60, run_id=2)
        self.assertEqual(self.report(crawl_run_id=2), [])
        self.assertEqual(len(self.report(crawl_run_id=2, max_ratio=0.7)), 1)


class CoverageDropFormatTest(unittest.TestCase):
    """The report line is the whole deliverable — it has to stay readable."""

    def row(self, wid, name, now_c, prev_c, now_len=1000, prev_len=1000):
        return (wid, name, now_c, prev_c, now_len, prev_len, 1, 2)

    def test_empty_renders_nothing(self):
        """Callers print unconditionally, so silence has to be the default."""
        self.assertEqual(db.format_coverage_drop_report([]), [])

    def test_line_shape(self):
        lines = db.format_coverage_drop_report(
            [self.row(3, "New York Public Library", 179, 948, 940, 686465)])
        self.assertIn("1 website(s) lost most of their events", lines[0])
        self.assertIn("⚠️", lines[0])
        self.assertIn("w3 New York Public Library: 948 → 179 events (-81%)", lines[1])
        self.assertIn("content 686,465 → 940 chars (-100%)", lines[1])

    def test_truncates_long_lists(self):
        """The 2026-06-14 extraction outage would have produced 63 rows."""
        rows = [self.row(i, f"Site {i}", 0, 100) for i in range(63)]
        lines = db.format_coverage_drop_report(rows, limit=15)
        self.assertIn("63 website(s)", lines[0])
        self.assertEqual(sum(1 for l in lines if l.strip().startswith("- w")), 15)
        self.assertTrue(any("and 48 more" in l for l in lines))


if __name__ == '__main__':
    unittest.main()
