"""Grouped dates must keep all reviewed booking links without changing identity."""
import json
from contextlib import ExitStack, redirect_stdout
from datetime import date, timedelta
import io
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger


class SQLCursor:
    def __init__(self, conn):
        self.cursor = conn.cursor()

    def execute(self, query, params=()):
        return self.cursor.execute(query.replace('%s', '?'), params)

    def fetchall(self):
        return self.cursor.fetchall()


class GroupedEventURLTests(unittest.TestCase):
    LISTING = 'https://example.org/events'
    FIRST = 'https://example.org/events/class-1'
    SECOND = 'https://example.org/events/class-2'

    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        self.cur = SQLCursor(self.conn)
        self.cur.execute('CREATE TABLE event_urls (id INTEGER PRIMARY KEY, '
                         'event_id INTEGER, url TEXT, sort_order INTEGER, UNIQUE(event_id,url))')

    def seed(self, url, order=0, eid=1):
        self.cur.execute('INSERT INTO event_urls(event_id,url,sort_order) VALUES(%s,%s,%s)',
                         (eid, url, order))

    def merge(self, raw=None):
        if raw is None:
            raw = json.dumps({'urls': [self.FIRST, self.SECOND, self.LISTING]})
        merger._merge_grouped_event_urls(self.cur, 1, raw, {self.LISTING})

    def rows(self):
        self.cur.execute('SELECT event_id,url,sort_order FROM event_urls ORDER BY event_id,sort_order,id')
        return self.cur.fetchall()

    def test_new_series_keeps_both_dates_booking_urls(self):
        self.seed(self.FIRST)
        self.merge()
        self.assertEqual(self.rows(), [(1, self.FIRST, 0), (1, self.SECOND, 1)])

    def test_existing_priorities_and_other_events_are_preserved(self):
        self.seed('https://example.org/older-detail', 0)
        self.seed(self.FIRST, 8)
        self.seed(self.SECOND, 0, eid=2)
        self.merge()
        self.assertEqual(self.rows(), [(1, 'https://example.org/older-detail', 0),
                                      (1, self.FIRST, 8), (1, self.SECOND, 9),
                                      (2, self.SECOND, 0)])

    def test_repeating_merge_is_idempotent(self):
        self.seed(self.FIRST)
        self.merge()
        before = self.rows()
        self.merge()
        self.assertEqual(self.rows(), before)

    def test_first_detail_replaces_listing_primary(self):
        self.seed(self.LISTING, 99)
        self.merge()
        self.assertEqual(self.rows(), [(1, self.FIRST, 0), (1, self.SECOND, 1)])

    def test_listing_only_or_bad_raw_data_cannot_delete_existing_links(self):
        self.seed(self.LISTING)
        before = self.rows()
        for raw in ('bad json', 'null', '[]', '{}', '{"urls":"bad"}',
                    json.dumps({'urls': [self.LISTING + '/']})):
            with self.subTest(raw=raw):
                self.merge(raw)
                self.assertEqual(self.rows(), before)

    def test_invalid_urls_do_not_reach_storage(self):
        raw = {'urls': [None, 7, {}, '/relative', 'javascript:alert(1)',
                        'https://', 'https://[bad/', 'https://user:pass@example.org/',
                        'https://example.org:invalid/', 'https://example.org/\nfoo',
                        'https://example.org/' + 'x' * 2000, self.SECOND]}
        self.merge(raw)
        self.assertEqual(self.rows(), [(1, self.SECOND, 0)])

    def test_host_aliases_are_canonicalized_before_duplicate_checks(self):
        self.seed('https://luma.com/class')
        self.merge({'urls': ['https://lu.ma/class', 'https://luma.com/class', self.SECOND]})
        self.assertEqual(self.rows(), [(1, 'https://luma.com/class', 0), (1, self.SECOND, 1)])


class GroupedURLMergePathTests(unittest.TestCase):
    def run_path(self, existing_id):
        today = date(2026, 9, 20)
        raw = json.dumps({'urls': ['https://example.org/class-1', 'https://example.org/class-2']})
        cursor = MagicMock(lastrowid=1000)

        def execute(query, params=None):
            rows = []
            if 'SELECT ce.id, ce.name' in query:
                rows = [(1, 'Test Outdoor Walk', None, 'A guided walk.', '🌳',
                         'Test Venue', None, 10, 'https://example.org/class-1',
                         101, None, None, 100)]
            elif 'FROM crawl_event_occurrences' in query:
                rows = [(1, today, '3pm', None, '4pm', 0)]
            elif 'SELECT id, raw_data FROM crawl_events' in query:
                rows = [(1, raw)]
            cursor.fetchall.return_value = rows
            cursor.fetchone.return_value = None

        cursor.execute.side_effect = execute
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(patch.object(merger, 'EditLogger', None))
            stack.enter_context(patch.object(merger, 'get_active_date_window',
                                            return_value=(today, today + timedelta(days=90))))
            db = stack.enter_context(patch.object(merger, 'db'))
            db.build_tag_ancestor_map.return_value = ({}, set())
            db.archive_dead_source_events.return_value = (0, [])
            stack.enter_context(patch.object(merger, '_deduplicate_same_name_events', return_value=0))
            identity = stack.enter_context(patch.object(merger, '_match_by_url_identity', return_value=existing_id))
            stack.enter_context(patch.object(merger, '_merge_occurrences_into_event'))
            retain = stack.enter_context(patch.object(merger, '_merge_grouped_event_urls'))
            self.assertEqual(merger.merge_crawl_events(cursor, MagicMock(), website_ids=[101]),
                             (0, 1) if existing_id else (1, 0))
            retain.assert_called_once_with(cursor, existing_id or 1000, raw, set())
            self.assertEqual(identity.call_args.args[1], 'https://example.org/class-1')

    def test_new_event_receives_all_processed_links(self):
        self.run_path(None)

    def test_matched_event_receives_all_processed_links(self):
        self.run_path(500)


if __name__ == '__main__':
    unittest.main()
