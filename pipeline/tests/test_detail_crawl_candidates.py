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
CREATE TABLE location_alternate_names (
    id INTEGER PRIMARY KEY, location_id INTEGER, alternate_name TEXT, website_id INTEGER);
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


class TestSuffixedGenericLocationNames(unittest.TestCase):
    """A generic place name carrying a state/country suffix must still count.

    `generic_locations` is matched by exact string equality, so "New York, NY"
    never matched the "new york" entry and the row never became a detail-crawl
    candidate. Measured 2026-08-31: 1,781 crawl_event rows were stranded this
    way. The Moth (w199) lost the venue on every event because its listing page
    emits the city-filter label "New York, NY".
    """

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(SCHEMA)
        self.conn.execute(
            "INSERT INTO websites (id, name, skip_reenrichment) VALUES (199,'The Moth',0)")
        self.conn.execute(
            "INSERT INTO websites (id, name, skip_reenrichment) VALUES (763,'Big Reuse',0)")
        self.conn.execute(
            "INSERT INTO crawl_results (id, website_id, crawled_at) VALUES (1, 199, ?)",
            (RECRAWL_AT,))
        self.conn.execute(
            "INSERT INTO crawl_results (id, website_id, crawled_at) VALUES (2, 763, ?)",
            (RECRAWL_AT,))
        self.conn.commit()
        self.cur = _ShimCursor(self.conn)

    def _add(self, ce_id, location_name, crawl_result_id=1):
        # A real description and an occurrence, so the ONLY thing that can make
        # this row a candidate is the location_name test under examination.
        self.conn.execute(
            "INSERT INTO crawl_events (id, crawl_result_id, name, url, location_name,"
            " description, detail_crawl_attempts, created_at)"
            " VALUES (?, ?, ?, ?, ?, 'A real description.', 0, ?)",
            (ce_id, crawl_result_id, 'Event %d' % ce_id,
             'https://themoth.org/tickets/e%d' % ce_id, location_name, FRESH_AT))
        self.conn.execute(
            "INSERT INTO crawl_event_occurrences (id, crawl_event_id) VALUES (?, ?)",
            (ce_id, ce_id))
        self.conn.commit()

    def _alt(self, alt_id, location_id, name, website_id):
        self.conn.execute(
            "INSERT INTO location_alternate_names (id, location_id, alternate_name, website_id)"
            " VALUES (?, ?, ?, ?)", (alt_id, location_id, name, website_id))
        self.conn.commit()

    def _ids(self):
        return {row[0] for row in pipeline_db.get_detail_crawl_candidates(self.cur)}

    def test_bare_generic_name_still_qualifies(self):
        """The pre-existing exact-match arm must be untouched."""
        self._add(1, 'New York')
        self.assertEqual(self._ids(), {1})

    def test_state_suffixed_generic_name_now_qualifies(self):
        """The regression this fix closes."""
        self._add(2, 'New York, NY')
        self.assertEqual(self._ids(), {2})

    def test_repeated_suffixes_are_stripped(self):
        self._add(3, 'Central Park, New York, NY, US')
        self.assertEqual(self._ids(), {3})

    def test_real_venue_ending_in_a_place_name_is_not_generic(self):
        """No comma, so no strip.

        "Coney Island USA" is a real venue (loc 3390, 1208 Surf Ave, 106 live
        events). Stripping a suffix without requiring a comma would have made it
        generic and burned 483 rows of pointless detail crawls. "Museum of the
        City of New York" is the same trap without any suffix token at all.
        """
        self._add(4, 'Coney Island USA')
        self._add(5, 'Museum of the City of New York')
        self.assertEqual(self._ids(), set())

    def test_website_scoped_alt_name_suppresses_the_new_arm(self):
        """A site that deliberately maps a suffixed place name to its one venue.

        Big Reuse's own site uses "Bronx, NY" to mean its Bronx location, so a
        detail crawl is wasted work -- the matcher already resolves it.
        """
        self._alt(1, 2331, 'bronx, ny', 763)
        self._add(6, 'Bronx, NY', crawl_result_id=2)
        self.assertEqual(self._ids(), set())

    def test_scoped_alt_for_a_different_website_does_not_suppress(self):
        """The guard is per-website; another site's fallback must not apply."""
        self._alt(1, 2331, 'bronx, ny', 763)
        self._add(7, 'Bronx, NY', crawl_result_id=1)   # w199, not w763
        self.assertEqual(self._ids(), {7})

    def test_global_alt_name_suppresses_the_new_arm(self):
        self._alt(2, 2208, 'brooklyn, ny', None)
        self._add(8, 'Brooklyn, NY')
        self.assertEqual(self._ids(), set())

    def test_scoped_alt_does_not_suppress_the_pre_existing_exact_arm(self):
        """Deliberate asymmetry, and it was measured.

        19,589 of the 46,156 rows the exact arm already catches have a scoped
        alt. Guarding that arm too would silently drop 42% of existing
        candidates, so the guard is confined to the new suffix arm.
        """
        self._alt(3, 999, 'chelsea', 199)
        self._add(9, 'Chelsea')
        self.assertEqual(self._ids(), {9})

    def test_a_real_venue_name_is_never_a_candidate(self):
        self._add(10, 'The Bell House')
        self.assertEqual(self._ids(), set())


if __name__ == '__main__':
    unittest.main()
