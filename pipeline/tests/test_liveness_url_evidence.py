"""Persist URL-specific evidence only after the source's control gate passes."""
from contextlib import ExitStack
from datetime import date, datetime
from pathlib import Path
import os
import sqlite3
import sys
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import liveness_probe as probe


class SQLCursor:
    def __init__(self, connection):
        self.cursor = connection.cursor()

    def execute(self, query, args=()):
        return self.cursor.execute(query.replace('%s', '?'), args)

    @property
    def rowcount(self):
        return self.cursor.rowcount


class LivenessURLEvidenceTests(unittest.TestCase):
    OLD = 'https://example.test/events/old'
    NEW = 'https://example.test/events/new'
    CONTROL = 'https://example.test/events/control'

    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        self.conn.executescript('''
            CREATE TABLE events (id INTEGER PRIMARY KEY, archived INTEGER);
            INSERT INTO events VALUES (1,0);
            CREATE TABLE event_liveness_probes (
                event_id INTEGER, website_id INTEGER, url TEXT, verdict TEXT,
                http_status INTEGER, page_title TEXT, reason TEXT, archived INTEGER);
        ''')
        self.cur = SQLCursor(self.conn)

    def candidate(self, **kwargs):
        return dict(event_id=1, name='Event', website_id=7, next_occ=date(2026, 10, 1),
                    urls=[self.OLD, self.NEW], still_listed=False, **kwargs)

    def run_probe(self, statuses=(404, 200), control_status=200, missing_control=False,
                  dry_run=False, candidate=None):
        c = candidate or self.candidate()
        fetched = {u: {'status': s, 'title': 'Event' if s == 200 else 'Page not found' if s == 404 else '',
                       'content': 'Detailed public event information. ' * 10 if s == 200 else ''}
                   for u, s in zip(c['urls'], statuses)}
        controls = {} if missing_control else {7: self.CONTROL}
        if not missing_control:
            fetched[self.CONTROL] = {'status': control_status, 'title': '',
                                    'content': 'Detailed public control event information. ' * 10}
        with patch.object(probe, '_read_probe_inputs', return_value=([c], [7], {}, controls)), \
                patch.object(probe, 'probe_urls', new=AsyncMock(return_value=fetched)), \
                patch.object(probe, 'EditLogger', None):
            return probe.run(self.cur, self.conn, dry_run=dry_run, verbose=False)

    def stored(self):
        return {url: (verdict, reason, archived) for url, verdict, reason, archived in
                self.conn.execute('SELECT url,verdict,reason,archived FROM event_liveness_probes')}

    def test_failed_or_missing_control_downgrades_dead_url_in_mixed_result(self):
        for kwargs in ({'control_status': 403}, {'control_status': 500},
                       {'control_status': 404}, {'missing_control': True}):
            with self.subTest(kwargs=kwargs):
                self.conn.execute('DELETE FROM event_liveness_probes')
                result = self.run_probe(**kwargs)
                old, new = self.stored()[self.OLD], self.stored()[self.NEW]
                self.assertEqual(old, ('unknown', 'walled site; was: http 404', 0))
                self.assertEqual(new, ('alive', 'http 200', 0))
                self.assertEqual((result['alive'], result['dead'], result['archived']), (1, 0, 0))
                self.assertEqual(self.conn.execute('SELECT archived FROM events').fetchone(), (0,))

    def test_failed_control_preserves_unknown_reason_and_never_archives(self):
        result = self.run_probe(statuses=(404, 500), control_status=403)
        self.assertEqual(self.stored()[self.OLD][0], 'unknown')
        self.assertEqual(self.stored()[self.NEW][0], 'unknown')
        self.assertNotIn('walled site', self.stored()[self.NEW][1])
        self.assertEqual((result['unknown'], result['archived']), (1, 0))

    def test_all_dead_without_working_control_remains_unknown(self):
        result = self.run_probe(statuses=(404, 404), missing_control=True)
        self.assertEqual({v[0] for v in self.stored().values()}, {'unknown'})
        self.assertEqual((result['unknown'], result['archived']), (1, 0))

    def test_working_control_preserves_mixed_verdicts_and_all_dead_archival(self):
        result = self.run_probe()
        self.assertEqual(self.stored()[self.OLD], ('dead', 'http 404', 0))
        self.assertEqual(self.stored()[self.NEW], ('alive', 'http 200', 0))
        self.assertEqual(result['archived'], 0)
        self.conn.execute('DELETE FROM event_liveness_probes')
        result = self.run_probe(statuses=(404, 404))
        self.assertEqual({v[0] for v in self.stored().values()}, {'dead'})
        self.assertEqual({v[2] for v in self.stored().values()}, {1})
        self.assertEqual((result['dead'], result['archived']), (1, 1))
        self.assertEqual(self.conn.execute('SELECT archived FROM events').fetchone(), (1,))

    def test_listing_shortcut_verifies_only_the_url_actually_listed(self):
        c = self.candidate(listed_urls=[self.NEW]); c['still_listed'] = True
        result = self.run_probe(candidate=c, missing_control=True)
        self.assertEqual(self.stored()[self.NEW], ('alive', 'still listed in latest crawl', 0))
        self.assertEqual(self.stored()[self.OLD],
                         ('unknown', 'event still listed; this URL not verified', 0))
        self.assertEqual((result['alive'], result['archived']), (1, 0))

    def test_listed_url_outside_probe_budget_still_protects_event(self):
        for listed in ([self.CONTROL], []):
            with self.subTest(listed=listed):
                self.conn.execute('DELETE FROM event_liveness_probes')
                c = self.candidate(listed_urls=listed); c['still_listed'] = True
                result = self.run_probe(candidate=c, missing_control=True)
                self.assertEqual({v[0] for v in self.stored().values()}, {'unknown'})
                self.assertEqual((result['alive'], result['archived']), (1, 0))

    def test_empty_urls_cannot_archive_event(self):
        c = self.candidate(); c['urls'] = []
        result = self.run_probe(candidate=c, statuses=())
        self.assertEqual((result['unknown'], result['archived']), (1, 0))
        self.assertEqual(self.stored(), {})

    def test_dry_run_reports_same_verdicts_without_persistent_changes(self):
        result = self.run_probe(statuses=(404, 500), missing_control=True, dry_run=True)
        self.assertEqual((result['unknown'], result['archived']), (1, 0))
        self.assertEqual(self.stored(), {})
        self.assertEqual(self.conn.execute('SELECT archived FROM events').fetchone(), (0,))


class ListedURLSnapshotTests(unittest.TestCase):
    def test_snapshot_retains_exact_urls_from_selected_publisher_before_temp_cleanup(self):
        cursor = MagicMock()
        now = datetime(2026, 9, 26)
        captured = []
        def execute(sql, params=()):
            captured.append(sql)
            rows = []
            if 'SELECT e.id, e.name,' in sql:
                rows = [(1, 'Tour', now, 7, now, now.date(), True)]
            elif 'SELECT DISTINCT eu.event_id, ll.website_id, eu.url' in sql:
                self.assertFalse(any('DROP TEMPORARY TABLE' in q for q in captured))
                self.assertIn('BINARY ll.url = BINARY eu.url', sql)
                rows = [(1, 7, 'https://example.test/tour-1'),
                        (1, 8, 'https://example.test/other-publisher')]
            elif 'SELECT event_id, url FROM event_urls' in sql:
                rows = [(1, 'https://example.test/tour'), (1, 'https://example.test/tour-1')]
            cursor.fetchall.return_value = rows
        cursor.execute.side_effect = execute
        with ExitStack() as stack:
            stack.enter_context(patch.object(probe.db, 'build_archival_temps'))
            stack.enter_context(patch.object(probe.db, 'drop_archival_temps'))
            stack.enter_context(patch.object(probe, '_build_latest_merged_temps'))
            candidates = probe.get_candidates(cursor)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['listed_urls'], ['https://example.test/tour-1'])
        self.assertEqual(len(candidates[0]['urls']), 2)
        self.assertTrue(candidates[0]['still_listed'])
        self.assertTrue(any('DROP TEMPORARY TABLE' in sql for sql in captured))


# Exercise the candidate SQL against MariaDB without touching application rows.
@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1',
                     'Opt in to isolated MariaDB fixtures with FOMO_TEST_TEMP_DB=1')
class ListedURLDatabaseTests(unittest.TestCase):
    def test_listing_evidence_is_exact_scoped_and_not_limited_to_first_three_urls(self):
        config = dict(probe.db.get_db_config()); config.pop('database', None)
        database = 'fomo_url_evidence_test_' + uuid.uuid4().hex
        admin = probe.db.mysql.connector.connect(**config, autocommit=True)
        self.addCleanup(admin.close)
        with admin.cursor() as cur:
            cur.execute(f'CREATE DATABASE `{database}`')
        def drop():
            with admin.cursor() as cur:
                cur.execute(f'DROP DATABASE `{database}`')
        self.addCleanup(drop)
        conn = probe.db.mysql.connector.connect(**config, database=database)
        self.addCleanup(conn.close)
        cur = conn.cursor()
        for sql in (
            'CREATE TABLE events (id INT, name TEXT, archived INT, suppressed INT)',
            'CREATE TABLE event_urls (id INT, event_id INT, url VARCHAR(2000), sort_order INT)',
            'CREATE TABLE event_sources (event_id INT, crawl_event_id INT)',
            'CREATE TABLE crawl_events (id INT, crawl_result_id INT)',
            'CREATE TABLE crawl_results (id INT, website_id INT, processed_at DATETIME)',
            'CREATE TABLE event_occurrences (event_id INT, start_date DATE)',
            'CREATE TABLE event_liveness_probes (event_id INT, probed_at DATETIME)',
            "INSERT INTO events VALUES (1,'Tour',0,0),(2,'Case-sensitive path',0,0),(3,'Many links',0,0)",
            "INSERT INTO event_urls VALUES (1,1,'https://example.test/old',0),(2,1,'https://example.test/live',1),"
            "(3,2,'https://example.test/Case',0),"
            "(4,3,'https://example.test/older-1',0),(5,3,'https://example.test/older-2',1),"
            "(6,3,'https://example.test/older-3',2),(7,3,'https://example.test/fourth',3)",
            'INSERT INTO event_sources VALUES (1,10),(2,10),(3,10)',
            'INSERT INTO crawl_events VALUES (10,10)',
            'INSERT INTO crawl_results VALUES (10,7,DATE_SUB(NOW(),INTERVAL 1 DAY))',
            'INSERT INTO event_occurrences SELECT id,DATE_ADD(CURDATE(),INTERVAL 1 DAY) FROM events',
        ):
            cur.execute(sql)
        conn.commit()
        def archival(cursor):
            cursor.execute('CREATE TEMPORARY TABLE _evt_future AS SELECT id AS event_id FROM events')
        def latest(cursor):
            cursor.execute('CREATE TEMPORARY TABLE _lp_latest (website_id INT,latest DATETIME)')
            cursor.execute('INSERT INTO _lp_latest VALUES (7,NOW()),(8,NOW())')
            cursor.execute('CREATE TEMPORARY TABLE _lp_listed (website_id INT,url VARCHAR(2000),INDEX(website_id,url(191)))')
            cursor.execute("INSERT INTO _lp_listed VALUES (7,'https://example.test/live'),"
                           "(8,'https://example.test/old'),(7,'https://example.test/case'),"
                           "(7,'https://example.test/fourth')")
        with patch.object(probe.db, 'build_archival_temps', side_effect=archival), \
                patch.object(probe.db, 'drop_archival_temps',
                             side_effect=lambda cursor: cursor.execute('DROP TEMPORARY TABLE _evt_future')), \
                patch.object(probe, '_build_latest_merged_temps', side_effect=latest):
            candidates = {c['event_id']: c for c in probe.get_candidates(cur)}
        self.assertEqual(set(candidates), {1, 2, 3})
        self.assertEqual(candidates[1]['listed_urls'], ['https://example.test/live'])
        self.assertTrue(candidates[1]['still_listed'])
        self.assertEqual(candidates[2]['listed_urls'], [])
        self.assertFalse(candidates[2]['still_listed'])
        self.assertEqual(candidates[3]['listed_urls'], ['https://example.test/fourth'])
        self.assertEqual(len(candidates[3]['urls']), 3)
        self.assertNotIn('https://example.test/fourth', candidates[3]['urls'])
        self.assertTrue(candidates[3]['still_listed'])
        conn.rollback()


if __name__ == '__main__':
    unittest.main()
