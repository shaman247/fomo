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
CREATE TABLE websites (id INTEGER PRIMARY KEY, name TEXT, disabled INTEGER DEFAULT 0);
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
    def add_website(self, website_id, disabled=False):
        self.connection.execute(
            "INSERT INTO websites (id, name, disabled) VALUES (?, ?, ?)",
            (website_id, f"Website {website_id}", 1 if disabled else 0))

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


if __name__ == '__main__':
    unittest.main()
