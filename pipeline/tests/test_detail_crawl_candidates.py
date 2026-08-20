"""Tests for db.get_detail_crawl_candidates' staleness guards.

Ground truth comes from the 2026-08-05 /run-pipeline, which found that Step 5
was spending its detail-crawl budget on SUPERSEDED crawl_events.

`crawl_results` rows are UPDATEd in place, so a re-crawl does not remove the
previous run's `crawl_events` — they keep pointing at the same `crawl_result`
with an older `created_at`. Without a guard the candidate query cannot tell them
apart from the fresh extraction, and the merger never reads the stale ones, so
every fetch spent on them is wasted.

Measured that day across the live candidate pool: **98 of 1533 candidates (6.4%)
were superseded** — w224 Park Avenue Armory 18, w369 Museum of the Moving Image
18, w3 NYPL 12. On w224's re-crawl all 28 fresh rows came out at
`detail_crawl_attempts = 0` while 17 superseded ones had already burned 1.

These tests run the real MySQL query text against SQLite via the same shim
`test_archival.py` uses, so the guard is exercised as written rather than mocked.
"""

import os
import sqlite3
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db as pipeline_db
from tests.test_archival import _ShimCursor

SCHEMA = """
CREATE TABLE websites (
    id INTEGER PRIMARY KEY, name TEXT, skip_reenrichment INTEGER DEFAULT 0);
CREATE TABLE crawl_results (
    id INTEGER PRIMARY KEY, website_id INTEGER, crawled_at TEXT);
CREATE TABLE crawl_events (
    id INTEGER PRIMARY KEY, crawl_result_id INTEGER, name TEXT, url TEXT,
    location_name TEXT, description TEXT, detail_crawl_attempts INTEGER DEFAULT 0,
    created_at TEXT);
CREATE TABLE crawl_event_occurrences (id INTEGER PRIMARY KEY, crawl_event_id INTEGER);
CREATE TABLE event_sources (id INTEGER PRIMARY KEY, event_id INTEGER, crawl_event_id INTEGER);
CREATE TABLE website_urls (id INTEGER PRIMARY KEY, website_id INTEGER, url TEXT);
"""

# The crawl_result was re-crawled at this moment; anything created before it is
# a leftover from the PREVIOUS extraction of the same row.
#
# These MUST be relative to now, not literals. `get_detail_crawl_candidates`
# also filters `cr.crawled_at >= DATE_SUB(NOW(), INTERVAL 14 DAY)`, so a
# hardcoded fixture date silently ages out of the candidate window and every
# test that expects a row starts failing — while the one test that expects an
# EMPTY set keeps passing, so the suite looks merely "partly broken" rather
# than stale. That is exactly what happened: the previous literals were
# 2026-08-05, which fell out of the window on 2026-08-19 and took 4 tests with
# it. Anchoring to now keeps the fixture inside the window forever.
_RECRAWL_DT = datetime.now() - timedelta(days=1)
_FMT = "%Y-%m-%d %H:%M:%S"

RECRAWL_AT = _RECRAWL_DT.strftime(_FMT)
STALE_AT = (_RECRAWL_DT - timedelta(minutes=22)).strftime(_FMT)   # previous run's crawl_events
FRESH_AT = (_RECRAWL_DT + timedelta(minutes=1)).strftime(_FMT)    # this run's crawl_events


class TestSupersededCrawlEventsExcluded(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(SCHEMA)
        self.conn.execute(
            "INSERT INTO websites (id, name, skip_reenrichment) VALUES (224,'Park Avenue Armory',0)")
        # One crawl_result, re-crawled — the shape that strands the old rows.
        self.conn.execute(
            "INSERT INTO crawl_results (id, website_id, crawled_at) VALUES (1, 224, ?)",
            (RECRAWL_AT,))
        self.conn.commit()
        self.cur = _ShimCursor(self.conn)

    def _add(self, ce_id, name, url, created_at, attempts=0):
        # description NULL + no occurrences => needs_detail_crawl() is True, so
        # the row's fate is decided purely by the SQL guards under test.
        self.conn.execute(
            "INSERT INTO crawl_events (id, crawl_result_id, name, url, location_name,"
            " description, detail_crawl_attempts, created_at)"
            " VALUES (?, 1, ?, ?, NULL, 'No description available.', ?, ?)",
            (ce_id, name, url, attempts, created_at))
        self.conn.commit()

    def _ids(self, website_ids=None):
        return {row[0] for row in
                pipeline_db.get_detail_crawl_candidates(self.cur, website_ids=website_ids)}

    def test_superseded_row_is_not_a_candidate(self):
        """The regression: a leftover from the previous extraction must be dropped."""
        self._add(1, 'Glorious Country', 'https://armoryonpark.org/e/glorious', STALE_AT)
        self.assertEqual(self._ids(), set())

    def test_fresh_row_is_a_candidate(self):
        self._add(2, 'Artist Talk: Steve Reich', 'https://armoryonpark.org/e/reich', FRESH_AT)
        self.assertEqual(self._ids(), {2})

    def test_only_the_fresh_twin_survives(self):
        """Both rows describe the same event; only the current extraction qualifies."""
        self._add(1, 'Pottier & Stymus', 'https://armoryonpark.org/e/pottier', STALE_AT)
        self._add(2, 'Pottier & Stymus', 'https://armoryonpark.org/e/pottier', FRESH_AT)
        self.assertEqual(self._ids(), {2})

    def test_guard_applies_to_the_website_ids_branch_too(self):
        """--ids runs go through a separate query string; it must guard identically."""
        self._add(1, 'Glorious Country', 'https://armoryonpark.org/e/glorious', STALE_AT)
        self._add(2, 'Under Construction', 'https://armoryonpark.org/e/under', FRESH_AT)
        self.assertEqual(self._ids(website_ids=[224]), {2})

    def test_row_created_exactly_at_crawled_at_is_kept(self):
        """Boundary: the guard is >=, so a same-instant row is fresh, not stale."""
        self._add(3, 'Recital Series', 'https://armoryonpark.org/e/recital', RECRAWL_AT)
        self.assertEqual(self._ids(), {3})

    def test_pre_existing_guards_still_apply(self):
        """The new predicate must not have displaced the attempts/merged guards."""
        self._add(4, 'Exhausted', 'https://armoryonpark.org/e/exhausted', FRESH_AT, attempts=2)
        self._add(5, 'Already Merged', 'https://armoryonpark.org/e/merged', FRESH_AT)
        self.conn.execute(
            "INSERT INTO event_sources (id, event_id, crawl_event_id) VALUES (1, 900, 5)")
        self.conn.commit()
        self.assertEqual(self._ids(), set())


if __name__ == '__main__':
    unittest.main()
