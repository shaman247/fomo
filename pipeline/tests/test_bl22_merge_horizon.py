"""BL22: the merge candidate query honours the loop's FUTURE_WINDOW_DAYS horizon,
horizon-only crawl results still get merged_at, and the stamp is by primary key.

w336 NY Parks kept four 2027-05-01 crawl_events (past the 90-day horizon)
eligible to every merge: the loop always skipped them, but fetching them forced
the ~50k-event dedupe index load each time. The `merged_at` UPDATE used a
dependent subquery that scanned (and locked) all of crawl_results.

The database tests run on connection-local TEMPORARY tables
(FOMO_TEST_TEMP_DB=1); no production rows are read or changed.
Run: cd pipeline/tests && PYTHONPATH=..:../.. FOMO_TEST_TEMP_DB=1 ../../venv/bin/python test_bl22_merge_horizon.py
"""
import contextlib
import io
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger
from constants import get_active_date_window


class StampTests(unittest.TestCase):
    def test_stamp_is_by_primary_key_in_chunks(self):
        cursor = MagicMock()
        merger._stamp_merged_at(cursor, list(range(2500, 0, -1)) + [7, 7])
        calls = cursor.execute.call_args_list
        self.assertEqual(len(calls), 3)
        for call in calls:
            sql = call.args[0]
            self.assertTrue(sql.startswith('UPDATE crawl_results SET merged_at = NOW() WHERE id IN ('))
            self.assertNotIn('SELECT', sql)
        self.assertEqual(calls[0].args[1][:3], [1, 2, 3])
        self.assertEqual(sum(len(c.args[1]) for c in calls), 2500)

    def test_empty_stamp_runs_nothing(self):
        cursor = MagicMock()
        merger._stamp_merged_at(cursor, set())
        cursor.execute.assert_not_called()


class _Stop(Exception):
    """Raised right after the early-return check to inspect the candidate set."""


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1',
                     'Opt in to connection-local MariaDB tests with FOMO_TEST_TEMP_DB=1')
class MergeHorizonTests(unittest.TestCase):
    SCHEMAS = {
        'tags': "id INT PRIMARY KEY, name VARCHAR(255), type VARCHAR(20), scope VARCHAR(20)",
        'crawl_results': ("id INT PRIMARY KEY, website_id INT, status VARCHAR(20), "
                          "processed_at DATETIME, merged_at DATETIME NULL"),
        'crawl_events': ("id INT PRIMARY KEY, name VARCHAR(500), short_name VARCHAR(255), "
                         "description TEXT, emoji VARCHAR(10), location_name VARCHAR(255), "
                         "sublocation VARCHAR(255), location_id INT, url VARCHAR(500), "
                         "crawl_result_id INT, KEY idx_crawl_result (crawl_result_id)"),
        'crawl_event_occurrences': ("id INT AUTO_INCREMENT PRIMARY KEY, crawl_event_id INT, "
                                    "start_date DATE, end_date DATE NULL, "
                                    "KEY idx_crawl_event (crawl_event_id), KEY idx_start_date (start_date)"),
        'event_sources': "id INT AUTO_INCREMENT PRIMARY KEY, event_id INT, crawl_event_id INT",
        'locations': "id INT PRIMARY KEY, lat DOUBLE, lng DOUBLE",
    }

    def setUp(self):
        from db import create_connection
        self.conn = create_connection()
        self.assertIsNotNone(self.conn)
        self.addCleanup(self.conn.close)
        self.cur = self.conn.cursor()
        for table, schema in self.SCHEMAS.items():
            self.cur.execute(f'CREATE TEMPORARY TABLE {table} ({schema})')
        self.today, self.horizon = get_active_date_window()
        for target, value in (
                ('merger.db.build_tag_ancestor_map', ({}, set())),
                ('merger._merge_edit_logger', None),
                ('merger._empty_latest_archival_websites', {})):
            p = patch(target, return_value=value)
            p.start()
            self.addCleanup(p.stop)

    def crawl_event(self, ce_id, cr_id, website_id, *starts, linked=False):
        self.cur.execute("INSERT IGNORE INTO crawl_results VALUES (%s,%s,'processed',%s,NULL)",
                         (cr_id, website_id, datetime.now() - timedelta(days=1)))
        self.cur.execute("INSERT INTO crawl_events(id,name,crawl_result_id) VALUES (%s,%s,%s)",
                         (ce_id, f'Event {ce_id}', cr_id))
        for start in starts:
            self.cur.execute("INSERT INTO crawl_event_occurrences(crawl_event_id,start_date) "
                             "VALUES (%s,%s)", (ce_id, start))
        if linked:
            self.cur.execute("INSERT INTO event_sources(event_id,crawl_event_id) VALUES (1,%s)",
                             (ce_id,))

    def merged(self):
        self.cur.execute("SELECT id FROM crawl_results WHERE merged_at IS NOT NULL ORDER BY id")
        return [r[0] for r in self.cur.fetchall()]

    def merge(self, website_ids=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = merger.merge_crawl_events(self.cur, self.conn, website_ids=website_ids)
        return result, out.getvalue()

    def test_w336_horizon_only_rows_take_the_early_return_and_are_stamped(self):
        far = self.horizon + timedelta(days=180)
        self.crawl_event(1300646, 117887, 336, far)
        self.crawl_event(1318907, 118000, 336, far)
        # A past-only crawl result was never a candidate and stays unstamped.
        self.crawl_event(5, 50, 336, self.today - timedelta(days=30))
        with patch.object(merger.LocationContainment, 'load', side_effect=_Stop):
            result, out = self.merge([336])
        self.assertEqual(result, (0, 0))
        self.assertIn('Found 0 unprocessed crawl_events', out)
        self.assertEqual(self.merged(), [117887, 118000])

    def test_scope_bounds_the_horizon_stamp(self):
        far = self.horizon + timedelta(days=30)
        self.crawl_event(1, 10, 336, far)
        self.crawl_event(2, 20, 999, far)
        self.merge([336])
        self.assertEqual(self.merged(), [10])

    def test_row_on_the_horizon_is_still_a_candidate(self):
        self.crawl_event(1, 10, 336, self.horizon)
        self.crawl_event(2, 20, 336, self.horizon + timedelta(days=1))
        with patch.object(merger.LocationContainment, 'load', side_effect=_Stop):
            with self.assertRaises(_Stop):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    merger.merge_crawl_events(self.cur, self.conn, website_ids=[336])
        self.assertIn('Found 1 unprocessed crawl_events', out.getvalue())

    def test_horizon_query_skips_stamped_and_linked_window(self):
        far = self.horizon + timedelta(days=30)
        self.crawl_event(1, 10, 336, far)
        self.cur.execute("UPDATE crawl_results SET merged_at = NOW() WHERE id = 10")
        self.crawl_event(2, 20, 336, far)
        self.cur.execute("UPDATE crawl_results SET status = 'extracted' WHERE id = 20")
        self.crawl_event(3, 30, 336, far)
        self.assertEqual(merger._horizon_only_unmerged_results(self.cur, self.horizon), [30])
        self.assertEqual(merger._horizon_only_unmerged_results(self.cur, self.horizon, [7]), [])


if __name__ == '__main__':
    unittest.main()
