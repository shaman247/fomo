"""Tests for the archival queries in db.py.

`archive_outdated_events` / `archive_dead_source_events` are pure SQL, and the
bugs they have had are SQL-semantics bugs (a disabled website's frozen last
crawl pinning an event as "still listed" forever). String-matching the query
text would not have caught that, so these tests run the *real* SQL against an
in-memory SQLite database through a small MySQL-dialect shim: the statements
under test are the ones db.py actually ships, only the handful of MySQL-only
spellings (`CREATE TEMPORARY TABLE t (cols) SELECT ...`, `NOW()`, `CURDATE()`,
`DATE_SUB(..., INTERVAL n DAY)`, `%s` placeholders) are rewritten.
"""

import os
import re
import sqlite3
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db


# ── MySQL → SQLite dialect shim ──────────────────────────────────────────────

def _translate(sql):
    """Rewrite the MySQL-only spellings used by the archival queries."""
    # CREATE TEMPORARY TABLE x (col defs) SELECT ...  →  CREATE TEMP TABLE x AS SELECT ...
    sql = re.sub(
        r"CREATE TEMPORARY TABLE\s+(\w+)\s*\(.*?\)\s*SELECT",
        r"CREATE TEMPORARY TABLE \1 AS SELECT",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    sql = re.sub(r"DROP TEMPORARY TABLE", "DROP TABLE", sql, flags=re.IGNORECASE)
    sql = re.sub(r"DATE_SUB\(\s*NOW\(\)\s*,\s*INTERVAL\s+(\d+)\s+DAY\s*\)",
                 r"datetime('now', '-\1 day')", sql, flags=re.IGNORECASE)
    # Must precede the bare CURDATE() rewrite below, which would otherwise eat
    # the argument and leave a stray DATE_ADD(...) SQLite cannot parse.
    sql = re.sub(r"DATE_ADD\(\s*CURDATE\(\)\s*,\s*INTERVAL\s+(\d+)\s+DAY\s*\)",
                 r"date('now', '+\1 day')", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bCURDATE\(\)", "date('now')", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bNOW\(\)", "datetime('now')", sql, flags=re.IGNORECASE)
    return sql.replace("%s", "?")


class _ShimCursor:
    """Cursor that speaks the pipeline's MySQL SQL to a SQLite connection."""

    def __init__(self, connection):
        self._cursor = connection.cursor()

    def execute(self, sql, params=()):
        self._cursor.execute(_translate(sql), tuple(params or ()))

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchone(self):
        return self._cursor.fetchone()

    @property
    def rowcount(self):
        return self._cursor.rowcount


SCHEMA = """
CREATE TABLE websites (
    id INTEGER PRIMARY KEY, name TEXT, base_url TEXT, disabled INTEGER DEFAULT 0);
CREATE TABLE crawl_results (
    id INTEGER PRIMARY KEY, website_id INTEGER, status TEXT, processed_at TEXT);
CREATE TABLE crawl_events (id INTEGER PRIMARY KEY, crawl_result_id INTEGER, name TEXT);
CREATE TABLE events (id INTEGER PRIMARY KEY, name TEXT, website_id INTEGER, archived INTEGER DEFAULT 0);
CREATE TABLE event_sources (event_id INTEGER, crawl_event_id INTEGER);
CREATE TABLE event_occurrences (
    id INTEGER PRIMARY KEY, event_id INTEGER, start_date TEXT, end_date TEXT);
CREATE TABLE extraction_rejections (
    id INTEGER PRIMARY KEY, website_id INTEGER, rejection_type TEXT,
    event_name TEXT, created_at TEXT);
CREATE TABLE website_urls (
    id INTEGER PRIMARY KEY, website_id INTEGER, url TEXT);
"""


def _days_ago(n):
    return (datetime.now() - timedelta(days=n)).strftime('%Y-%m-%d %H:%M:%S')


def _days_ahead(n):
    return (datetime.now() + timedelta(days=n)).strftime('%Y-%m-%d')


class ArchivalTestBase(unittest.TestCase):
    """Builds a tiny crawl graph; subclasses assert which events get archived."""

    def setUp(self):
        self.connection = sqlite3.connect(':memory:')
        self.connection.executescript(SCHEMA)
        self.cursor = _ShimCursor(self.connection)
        self._crawl_event_seq = 0

    def tearDown(self):
        self.connection.close()

    # ── fixture helpers ──
    def add_website(self, website_id, disabled=False, base_url=None):
        self.connection.execute(
            "INSERT INTO websites (id, name, base_url, disabled) VALUES (?, ?, ?, ?)",
            (website_id, f"Website {website_id}", base_url, 1 if disabled else 0))

    def add_website_url(self, website_id, url):
        """Give a website a crawl URL. A website with no rows here falls back to
        its `base_url` for the IG-only test, and a website with neither is
        treated as non-Instagram (a NULL can't satisfy the IG-only HAVING),
        which is why the pre-existing fixtures need no changes."""
        self.connection.execute(
            "INSERT INTO website_urls (website_id, url) VALUES (?, ?)",
            (website_id, url))

    def add_event(self, event_id, website_id, future_days=None, past=True):
        self.connection.execute(
            "INSERT INTO events (id, name, website_id, archived) VALUES (?, ?, ?, 0)",
            (event_id, f"Event {event_id}", website_id))
        if future_days is not None:
            self.connection.execute(
                "INSERT INTO event_occurrences (event_id, start_date, end_date) VALUES (?, ?, NULL)",
                (event_id, _days_ahead(future_days)))
        elif past:
            self.connection.execute(
                "INSERT INTO event_occurrences (event_id, start_date, end_date) VALUES (?, ?, NULL)",
                (event_id, (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')))

    def add_crawl(self, crawl_id, website_id, days_ago, event_ids=(), status='processed'):
        """A processed crawl of `website_id` that listed `event_ids`."""
        self.connection.execute(
            "INSERT INTO crawl_results (id, website_id, status, processed_at) VALUES (?, ?, ?, ?)",
            (crawl_id, website_id, status, _days_ago(days_ago)))
        for event_id in event_ids:
            self._crawl_event_seq += 1
            ce_id = self._crawl_event_seq
            self.connection.execute(
                "INSERT INTO crawl_events (id, crawl_result_id, name) VALUES (?, ?, ?)",
                (ce_id, crawl_id, f"ce{ce_id}"))
            self.connection.execute(
                "INSERT INTO event_sources (event_id, crawl_event_id) VALUES (?, ?)",
                (event_id, ce_id))

    def archived_ids(self):
        rows = self.connection.execute(
            "SELECT id FROM events WHERE archived = 1 ORDER BY id").fetchall()
        return [r[0] for r in rows]


class TestDisabledWebsiteDoesNotPinEvents(ArchivalTestBase):
    """A disabled website's frozen final crawl must not count as 'still listed'."""

    def _build(self, second_site_disabled):
        # w1 (enabled, just crawled) listed the event two crawls ago but not in
        # its latest crawl. w2 also listed it, then was disabled/stopped.
        self.add_website(1)
        self.add_website(2, disabled=second_site_disabled)
        self.add_event(100, website_id=1)
        self.add_crawl(10, website_id=1, days_ago=60, event_ids=[100])
        self.add_crawl(11, website_id=1, days_ago=30, event_ids=[])
        self.add_crawl(12, website_id=1, days_ago=1, event_ids=[])
        self.add_crawl(20, website_id=2, days_ago=45, event_ids=[100])  # w2's LAST crawl

    def test_disabled_source_does_not_block_archival(self):
        self._build(second_site_disabled=True)
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 1)
        self.assertEqual(self.archived_ids(), [100])

    def test_enabled_source_still_blocks_archival(self):
        """Unchanged behaviour for enabled websites: w2's latest crawl still lists it."""
        self._build(second_site_disabled=False)
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 0)
        self.assertEqual(self.archived_ids(), [])

    def test_event_dropped_by_its_only_enabled_website_is_archived(self):
        """Baseline single-website behaviour must not regress."""
        self.add_website(1)
        self.add_event(101, website_id=1)
        self.add_crawl(10, website_id=1, days_ago=60, event_ids=[101])
        self.add_crawl(11, website_id=1, days_ago=1, event_ids=[])
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(self.archived_ids(), [101])


class TestArchiveDeadSourceEvents(ArchivalTestBase):
    """Events whose every source website is disabled are archivable by a sweep.

    The per-website loop can never reach them: it only runs for websites that
    were just crawled, and a disabled website is never crawled again.
    """

    def test_disabled_only_source_is_archived(self):
        self.add_website(2, disabled=True)
        self.add_event(200, website_id=2)
        self.add_crawl(20, website_id=2, days_ago=45, event_ids=[200])
        archived, _ = db.archive_dead_source_events(self.cursor, self.connection)
        self.assertEqual(archived, 1)
        self.assertEqual(self.archived_ids(), [200])

    def test_per_website_pass_cannot_reach_them(self):
        """Documents why the sweep is needed at all."""
        self.add_website(1)
        self.add_website(2, disabled=True)
        self.add_event(200, website_id=2)
        self.add_crawl(20, website_id=2, days_ago=45, event_ids=[200])
        self.add_crawl(10, website_id=1, days_ago=1, event_ids=[])
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 0)

    def test_event_with_a_live_source_is_left_alone(self):
        self.add_website(1)
        self.add_website(2, disabled=True)
        self.add_event(201, website_id=1)
        self.add_crawl(20, website_id=2, days_ago=45, event_ids=[201])
        self.add_crawl(10, website_id=1, days_ago=1, event_ids=[201])
        archived, _ = db.archive_dead_source_events(self.cursor, self.connection)
        self.assertEqual(archived, 0)
        self.assertEqual(self.archived_ids(), [])

    def test_future_event_keeps_the_14_day_grace(self):
        """A site disabled yesterday must not lose its upcoming events today."""
        self.add_website(2, disabled=True)
        self.add_event(202, website_id=2, future_days=20)
        self.add_crawl(20, website_id=2, days_ago=1, event_ids=[202])
        archived, _ = db.archive_dead_source_events(self.cursor, self.connection)
        self.assertEqual(archived, 0)
        self.assertEqual(self.archived_ids(), [])

    def test_future_event_archived_once_grace_expires(self):
        self.add_website(2, disabled=True)
        self.add_event(203, website_id=2, future_days=20)
        self.add_crawl(20, website_id=2, days_ago=45, event_ids=[203])
        archived, upcoming = db.archive_dead_source_events(self.cursor, self.connection)
        self.assertEqual(archived, 1)
        self.assertEqual([row[0] for row in upcoming], [203])

    def test_event_with_no_sources_at_all_is_left_alone(self):
        """Deliberate: source-less events are a separate (unfixed) class — see
        the docstring on archive_dead_source_events. The sweep must not sneak
        them in."""
        self.add_website(2, disabled=True)
        self.add_event(204, website_id=2)
        archived, _ = db.archive_dead_source_events(self.cursor, self.connection)
        self.assertEqual(archived, 0)
        self.assertEqual(self.archived_ids(), [])

    def test_already_archived_events_are_not_recounted(self):
        self.add_website(2, disabled=True)
        self.add_event(205, website_id=2)
        self.add_crawl(20, website_id=2, days_ago=45, event_ids=[205])
        self.connection.execute("UPDATE events SET archived = 1 WHERE id = 205")
        archived, _ = db.archive_dead_source_events(self.cursor, self.connection)
        self.assertEqual(archived, 0)


class TestInstagramOnlySourcesKeepFutureEvents(ArchivalTestBase):
    """Absence from a picnob bundle is not evidence the event was delisted.

    A bundle is the FIRST PAGE of a handle's grid (12 posts), so an
    announcement scrolls out purely because the venue kept posting. The three
    future-event guards all assume absence == delisting, so they only delayed
    the wrong answer: 191217 "Luna Pink Performance" and 189114 "Tonights
    Special" were archived on 07-31, un-archived by triage, then re-archived
    identically on 08-03 and 08-06 — 191217 while its occurrence was TODAY.
    Measured when the guard shipped: 9 archived-but-still-upcoming IG-sourced
    events, 236 live ones newly protected.

    The exemption is narrow on purpose — it applies only while a future
    occurrence exists, and only when EVERY source is Instagram-only.
    """

    def _ig_site(self, website_id):
        self.add_website(website_id)
        self.add_website_url(website_id, f"https://www.instagram.com/venue{website_id}/")

    def _calendar_site(self, website_id):
        self.add_website(website_id)
        self.add_website_url(website_id, f"https://venue{website_id}.com/events")

    def _dropped_from_latest_crawl(self, website_id, event_id):
        """The shape that trips all three guards: last seen 60d ago, two fresh
        crawls since, no too-future rejection."""
        self.add_crawl(website_id * 10 + 1, website_id, days_ago=60, event_ids=[event_id])
        self.add_crawl(website_id * 10 + 2, website_id, days_ago=30, event_ids=[])
        self.add_crawl(website_id * 10 + 3, website_id, days_ago=1, event_ids=[])

    def test_ig_only_future_event_is_not_archived(self):
        self._ig_site(1)
        self.add_event(300, website_id=1, future_days=16)
        self._dropped_from_latest_crawl(1, 300)
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 0)
        self.assertEqual(self.archived_ids(), [])

    def test_ig_only_event_whose_dates_have_passed_is_still_archived(self):
        """The exemption must not make IG events immortal — once the last
        occurrence is past, the no-future-occurrence branch archives normally."""
        self._ig_site(1)
        self.add_event(301, website_id=1)  # past occurrence only
        self._dropped_from_latest_crawl(1, 301)
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 1)
        self.assertEqual(self.archived_ids(), [301])

    def test_non_ig_future_event_still_archives_on_the_normal_rules(self):
        """Baseline: a calendar site's silence IS evidence. Must not regress."""
        self._calendar_site(1)
        self.add_event(302, website_id=1, future_days=16)
        self._dropped_from_latest_crawl(1, 302)
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 1)
        self.assertEqual(self.archived_ids(), [302])

    def test_a_website_with_no_urls_and_no_base_url_is_treated_as_non_instagram(self):
        """Fail-closed: a site with no crawl URL *and* no base_url has nothing
        identifying it as Instagram, so it must not inherit the exemption. The
        NULL makes the LIKE NULL, which SUM skips, so COUNT(*) = SUM(...) is
        never satisfied."""
        self.add_website(1)
        self.add_event(303, website_id=1, future_days=16)
        self._dropped_from_latest_crawl(1, 303)
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 1)

    def test_mixed_url_website_is_not_exempt(self):
        """A site that also carries a real calendar URL yields a genuine
        delisting signal, so it keeps the normal rules (3 of 316 are mixed)."""
        self.add_website(1)
        self.add_website_url(1, "https://www.instagram.com/venue1/")
        self.add_website_url(1, "https://venue1.com/events")
        self.add_event(304, website_id=1, future_days=16)
        self._dropped_from_latest_crawl(1, 304)
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 1)

    def test_one_non_ig_source_removes_the_exemption(self):
        """The exemption requires EVERY source to be Instagram-only. A calendar
        site that also carried the event still speaks for it."""
        self._ig_site(1)
        self._calendar_site(2)
        self.add_event(305, website_id=1, future_days=16)
        self._dropped_from_latest_crawl(1, 305)
        # w2 listed it long ago and has since dropped it too.
        self.add_crawl(21, website_id=2, days_ago=60, event_ids=[305])
        self.add_crawl(22, website_id=2, days_ago=2, event_ids=[])
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 1)
        self.assertEqual(self.archived_ids(), [305])

    def test_second_ig_source_keeps_the_exemption(self):
        """Two Instagram sources are still two capped grids — still exempt."""
        self._ig_site(1)
        self._ig_site(2)
        self.add_event(306, website_id=1, future_days=16)
        self._dropped_from_latest_crawl(1, 306)
        self.add_crawl(21, website_id=2, days_ago=60, event_ids=[306])
        self.add_crawl(22, website_id=2, days_ago=2, event_ids=[])
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 0)


class TestInstagramSiteIdentifiedByBaseUrl(ArchivalTestBase):
    """An IG website needs no `website_urls` row at all to be scraped.

    picnob resolves a handle straight to its website row by base_url
    (`picnob_to_pipeline.py`: WHERE base_url IN (.../handle/, .../handle)), so
    43 of the 356 IG-only sites carry zero `website_urls` rows. The first cut of
    the exemption grouped over `website_urls` alone, and a website with no rows
    there produces no group — so those 43 could never appear in `_ws_ig_only`
    and kept churning while the 313 that did have rows went quiet. Event 193156
    "Atkinson Beach Club" (w3963 Ke-nee-go-keshek, weekly Sat through 09-05) was
    archived by this hole on 07-31, 08-03 and 08-09 with its next occurrence
    still five days out.
    """

    def _dropped_from_latest_crawl(self, website_id, event_id):
        self.add_crawl(website_id * 10 + 1, website_id, days_ago=60, event_ids=[event_id])
        self.add_crawl(website_id * 10 + 2, website_id, days_ago=30, event_ids=[])
        self.add_crawl(website_id * 10 + 3, website_id, days_ago=1, event_ids=[])

    def test_ig_base_url_with_no_website_urls_is_exempt(self):
        """The 193156 regression, in miniature."""
        self.add_website(1, base_url="https://www.instagram.com/keneegokeshekstudio/")
        self.add_event(400, website_id=1, future_days=6)
        self._dropped_from_latest_crawl(1, 400)
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 0)
        self.assertEqual(self.archived_ids(), [])

    def test_non_ig_base_url_with_no_website_urls_still_archives(self):
        """The other 13 URL-less sites are ordinary calendar venues. A blanket
        'no website_urls ⇒ exempt' rule would have swept them in too."""
        self.add_website(1, base_url="https://www.nycballet.com")
        self.add_event(401, website_id=1, future_days=6)
        self._dropped_from_latest_crawl(1, 401)
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 1)
        self.assertEqual(self.archived_ids(), [401])

    def test_website_urls_win_over_a_non_ig_base_url(self):
        """base_url is a FALLBACK, not an extra source. 5 sites in the exempt
        set have an Instagram `website_urls` row but a venue-domain base_url —
        unioning the two instead of falling back would have dropped them."""
        self.add_website(1, base_url="https://venue1.com")
        self.add_website_url(1, "https://www.instagram.com/venue1/")
        self.add_event(402, website_id=1, future_days=6)
        self._dropped_from_latest_crawl(1, 402)
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 0)

    def test_website_urls_win_over_an_ig_base_url(self):
        """Converse of the above: a real calendar URL is a genuine delisting
        signal even when base_url points at the venue's Instagram profile."""
        self.add_website(1, base_url="https://www.instagram.com/venue1/")
        self.add_website_url(1, "https://venue1.com/events")
        self.add_event(403, website_id=1, future_days=6)
        self._dropped_from_latest_crawl(1, 403)
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 1)

    def test_disabled_ig_site_is_still_reaped_by_the_dead_source_sweep(self):
        """The exemption lives only in archive_outdated_events. Disabling the
        website remains the escape hatch for a dead IG venue — otherwise the
        exemption would combine with `disabled_website_blocks_archival` to make
        its upcoming events permanently unarchivable."""
        self.add_website(1, base_url="https://www.instagram.com/venue1/", disabled=True)
        self.add_event(404, website_id=1, future_days=6)
        self.add_crawl(11, website_id=1, days_ago=45, event_ids=[404])
        archived, upcoming = db.archive_dead_source_events(self.cursor, self.connection)
        self.assertEqual(archived, 1)
        self.assertEqual([row[0] for row in upcoming], [404])


class TestInstagramExemptionHorizon(ArchivalTestBase):
    """The exemption holds only while a live occurrence sits inside 180 days.

    Without a cap, one bad extraction synthesizing a multi-year IG span would
    mint a permanently unarchivable event. 180d is a no-op on real data (all
    300 live IG-only events on 2026-08-09 had an occurrence within 90d, and the
    longest tail of any was +138d) and sits clear of FUTURE_WINDOW_DAYS = 90,
    the furthest out the processor accepts a start date at all.
    """

    def _ig_site(self, website_id):
        self.add_website(website_id, base_url=f"https://www.instagram.com/venue{website_id}/")

    def _dropped_from_latest_crawl(self, website_id, event_id):
        self.add_crawl(website_id * 10 + 1, website_id, days_ago=60, event_ids=[event_id])
        self.add_crawl(website_id * 10 + 2, website_id, days_ago=30, event_ids=[])
        self.add_crawl(website_id * 10 + 3, website_id, days_ago=1, event_ids=[])

    def test_occurrence_inside_the_horizon_keeps_the_exemption(self):
        self._ig_site(1)
        self.add_event(500, website_id=1, future_days=170)
        self._dropped_from_latest_crawl(1, 500)
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 0)

    def test_occurrences_all_beyond_the_horizon_lose_the_exemption(self):
        self._ig_site(1)
        self.add_event(501, website_id=1, future_days=400)
        self._dropped_from_latest_crawl(1, 501)
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 1)
        self.assertEqual(self.archived_ids(), [501])

    def test_one_near_occurrence_protects_a_long_tail(self):
        """A weekly series running past the horizon is NOT punished for it —
        the horizon asks whether ANY live occurrence is near, not all of them."""
        self._ig_site(1)
        self.add_event(502, website_id=1, future_days=3)
        self.connection.execute(
            "INSERT INTO event_occurrences (event_id, start_date, end_date) VALUES (?, ?, NULL)",
            (502, _days_ahead(400)))
        self._dropped_from_latest_crawl(1, 502)
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 0)

    def test_horizon_does_not_rescue_a_non_ig_event(self):
        """The horizon is an escape from the IG exemption, not a new guard. A
        calendar site's far-future event archives on the normal rules, exactly
        as before."""
        self.add_website(1, base_url="https://venue1.com")
        self.add_website_url(1, "https://venue1.com/events")
        self.add_event(503, website_id=1, future_days=400)
        self._dropped_from_latest_crawl(1, 503)
        archived, _ = db.archive_outdated_events(self.cursor, self.connection, 1)
        self.assertEqual(archived, 1)


if __name__ == '__main__':
    unittest.main()
