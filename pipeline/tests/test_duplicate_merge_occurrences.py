"""MariaDB regressions for reviewed duplicate merges.

Run with FOMO_TEST_TEMP_DB=1. All tables are connection-local TEMPORARY tables;
no production event data is read or changed. Icon merging is tested separately.
"""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from datetime import date

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'pipeline'))
sys.path.insert(0, str(ROOT / 'scripts'))
from db import create_connection
from find_duplicate_events import merge_pair, merge_exact_duplicates


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1',
                     'Opt in to connection-local MariaDB tests with FOMO_TEST_TEMP_DB=1')
class DuplicateMergeOccurrenceTests(unittest.TestCase):
    def setUp(self):
        self.conn = create_connection()
        self.assertIsNotNone(self.conn)
        self.addCleanup(self.conn.close)
        self.cur = self.conn.cursor()
        # Create every table touched by merge_pair before allowing test writes.
        schemas = {
            'events': 'id INT PRIMARY KEY, suppressed INT DEFAULT 0, reviewed INT DEFAULT 0',
            'event_occurrences': ('id INT AUTO_INCREMENT PRIMARY KEY, event_id INT, '
                                  'start_date DATE, start_time VARCHAR(20), end_date DATE, '
                                  'end_time VARCHAR(20), sort_order INT DEFAULT 0'),
            'event_urls': 'event_id INT, url VARCHAR(255), UNIQUE(event_id,url)',
            'event_tags': 'event_id INT, tag_id INT, UNIQUE(event_id,tag_id)',
            'event_sources': 'event_id INT, crawl_event_id INT, UNIQUE(event_id,crawl_event_id)',
            'event_tag_blocks': 'event_id INT, tag_id INT, reason TEXT, UNIQUE(event_id,tag_id)',
        }
        for table, schema in schemas.items():
            self.cur.execute(f'CREATE TEMPORARY TABLE {table} ({schema})')
        self.cur.execute('INSERT INTO events(id) VALUES (1),(2)')
        self.cur.execute('INSERT INTO event_sources VALUES (1,101),(2,202)')

    def merge(self, kept, incoming):
        for eid, rows in [(1, kept), (2, incoming)]:
            for row in rows:
                self.cur.execute('INSERT INTO event_occurrences '
                                 '(event_id,start_date,start_time,end_date,end_time) '
                                 'VALUES (%s,%s,%s,%s,%s)', (eid, *row))
        with patch('event_icon_assignments.merge_assignments') as icons:
            merge_pair(self.cur, 1, 2)
            icons.assert_called_once_with(self.cur, 1, 2)
        self.cur.execute('SELECT suppressed,reviewed FROM events WHERE id=2')
        self.assertEqual(self.cur.fetchone(), (1,1))
        self.cur.execute('SELECT event_id,crawl_event_id FROM event_sources ORDER BY 1,2')
        self.assertEqual(self.cur.fetchall(), [(1,101),(1,202),(2,202)])
        self.cur.execute('SELECT start_date,start_time,end_date,end_time '
                         'FROM event_occurrences WHERE event_id=2 ORDER BY id')
        self.assertEqual(self.cur.fetchall(), incoming)
        self.cur.execute('SELECT start_date,start_time,end_date,end_time '
                         'FROM event_occurrences WHERE event_id=1 ORDER BY id')
        return self.cur.fetchall()

    D = date(2026, 9, 16)

    def test_distinct_end_dates_survive_the_same_start(self):
        one = (self.D, '3pm', date(2026,9,17), '6pm')
        two = (self.D, '3pm', date(2026,9,18), '6pm')
        self.assertEqual(self.merge([one], [two]), [one,two])

    def test_missing_end_time_is_filled(self):
        complete = (self.D, '3pm', None, '6pm')
        self.assertEqual(self.merge([(self.D,'3pm',None,None)], [complete]), [complete])

    def test_conflicting_known_end_times_require_review(self):
        kept = (self.D,'3pm',None,'5pm')
        self.assertEqual(self.merge([kept], [(self.D,'3pm',None,'6pm')]), [kept])

    def test_equivalent_clock_formats_do_not_duplicate(self):
        kept = (self.D,'3pm',None,'6pm')
        self.assertEqual(self.merge([kept], [(self.D,'15:00',None,'18:00')]), [kept])

    def test_exact_legacy_duplicates_are_cleaned(self):
        row = (self.D,'3pm',None,'6pm')
        self.assertEqual(self.merge([row,row], [row,row]), [row])

    def test_existing_conflicting_spans_are_not_deleted(self):
        one = (self.D,'3pm',None,'5pm')
        two = (self.D,'3pm',date(2026,9,17),'6pm')
        self.assertEqual(self.merge([one,two], []), [one,two])

    def test_automatic_merge_preserves_chained_collections(self):
        self.cur.execute('INSERT INTO events(id) VALUES (3)')
        self.cur.execute('INSERT INTO event_sources VALUES (3,303)')
        self.cur.execute("INSERT INTO event_urls VALUES (2,'https://example.test/2'),"
                         "(3,'https://example.test/3')")
        self.cur.execute('INSERT INTO event_tags VALUES (2,12),(3,13)')
        self.cur.execute("INSERT INTO event_occurrences(event_id,start_date,start_time) "
                         "VALUES (2,'2026-09-16','3pm'),(3,'2026-09-17','4pm')")
        pairs = [{'id1': 1, 'id2': 2}, {'id1': 2, 'id2': 3},
                 {'id1': 2, 'id2': 3}]
        with patch('event_icon_assignments.merge_assignments'):
            self.assertEqual(merge_exact_duplicates(self.cur, pairs), 2)
        self.cur.execute('SELECT crawl_event_id FROM event_sources WHERE event_id=1 ORDER BY 1')
        self.assertEqual(self.cur.fetchall(), [(101,), (202,), (303,)])
        self.cur.execute('SELECT url FROM event_urls WHERE event_id=1 ORDER BY 1')
        self.assertEqual(self.cur.fetchall(), [('https://example.test/2',), ('https://example.test/3',)])
        self.cur.execute('SELECT tag_id FROM event_tags WHERE event_id=1 ORDER BY 1')
        self.assertEqual(self.cur.fetchall(), [(12,), (13,)])
        self.cur.execute('SELECT start_date FROM event_occurrences WHERE event_id=1 ORDER BY 1')
        self.assertEqual(self.cur.fetchall(), [(self.D,), (date(2026, 9, 17),)])
        self.cur.execute('SELECT id,suppressed,reviewed FROM events ORDER BY id')
        self.assertEqual(self.cur.fetchall(), [(1,0,0), (2,1,1), (3,1,1)])

    def test_multiple_keepers_do_not_expand_suppression(self):
        self.cur.execute('INSERT INTO events(id) VALUES (3)')
        self.cur.execute('INSERT INTO event_sources VALUES (3,303)')
        with patch('event_icon_assignments.merge_assignments'):
            self.assertEqual(merge_exact_duplicates(self.cur,
                [{'id1': 2, 'id2': 3}, {'id1': 1, 'id2': 3}]), 1)
        self.cur.execute('SELECT id FROM events WHERE suppressed=0 ORDER BY id')
        self.assertEqual(self.cur.fetchall(), [(1,), (2,)])
        self.cur.execute('SELECT crawl_event_id FROM event_sources WHERE event_id=1 ORDER BY 1')
        self.assertEqual(self.cur.fetchall(), [(101,), (303,)])


if __name__ == '__main__':
    unittest.main()
