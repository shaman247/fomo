"""BL24: a tag block binds even when the event already holds the tag.

Blocks copied onto a merge keeper (INSERT IGNORE) used to leave the keeper's
own row for that tag in place, so event_tags ∩ event_tag_blocks was non-empty
after merge-heavy runs. The database tests run on connection-local TEMPORARY
tables (FOMO_TEST_TEMP_DB=1); no production rows are read or changed.
"""
from datetime import date
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'pipeline'))
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import db
from test_tag_facets import FakeTagCursor

BLOCKED, OTHER = 20, 10


class WriterEnforcesBlocksTests(unittest.TestCase):
    def setUp(self):
        db._format_tag_id_cache = None
        self.addCleanup(setattr, db, '_format_tag_id_cache', None)

    def test_additive_upsert_strips_a_blocked_tag_the_event_already_holds(self):
        cur = FakeTagCursor('Talk', rows={'Music', 'Talk', 'Gathering', 'Format'}, blocks={'Music'})
        db.upsert_event_tags(cur, 1, ['Sports'])
        self.assertEqual(cur.tags(), {'Sports', 'Talk', 'Gathering', 'Format'})

    def test_additive_upsert_without_blocks_keeps_existing_rows(self):
        cur = FakeTagCursor('Talk', rows={'Music', 'Talk', 'Gathering', 'Format'})
        db.upsert_event_tags(cur, 1, ['Sports'])
        self.assertIn('Music', cur.tags())


class TempTablesMixin:
    SCHEMAS = {}

    def setUp(self):
        from db import create_connection
        self.conn = create_connection()
        self.assertIsNotNone(self.conn)
        self.addCleanup(self.conn.close)
        self.cur = self.conn.cursor()
        for table, schema in self.SCHEMAS.items():
            self.cur.execute(f'CREATE TEMPORARY TABLE {table} ({schema})')
        icons = patch('event_icon_assignments.merge_assignments')
        icons.start()
        self.addCleanup(icons.stop)

    def keeper_state(self, keep_id):
        self.cur.execute('SELECT tag_id FROM event_tags WHERE event_id=%s ORDER BY 1', (keep_id,))
        tags = [r[0] for r in self.cur.fetchall()]
        self.cur.execute('SELECT tag_id FROM event_tag_blocks WHERE event_id=%s ORDER BY 1', (keep_id,))
        return tags, [r[0] for r in self.cur.fetchall()]


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1',
                     'Opt in to connection-local MariaDB tests with FOMO_TEST_TEMP_DB=1')
class SameNameMergeBlockTests(TempTablesMixin, unittest.TestCase):
    DAY = date(2026, 10, 9)
    SCHEMAS = {
        'events': ('id INT PRIMARY KEY, name VARCHAR(255), website_id INT, '
                   'location_id INT, location_name VARCHAR(255), '
                   'archived INT DEFAULT 0, suppressed INT DEFAULT 0'),
        'event_occurrences': ('id INT AUTO_INCREMENT PRIMARY KEY, event_id INT, '
                              'start_date DATE, start_time VARCHAR(20), end_date DATE, '
                              'end_time VARCHAR(20), sort_order INT DEFAULT 0'),
        'event_merge_redirects': 'duplicate_id INT PRIMARY KEY, survivor_id INT, survivor_name VARCHAR(500)',
        'event_sources': 'event_id INT, crawl_event_id INT, UNIQUE(event_id,crawl_event_id)',
        'event_urls': 'event_id INT, url VARCHAR(255), UNIQUE(event_id,url)',
        'event_tags': 'event_id INT, tag_id INT, UNIQUE(event_id,tag_id)',
        'event_tag_blocks': 'event_id INT, tag_id INT, reason TEXT, UNIQUE(event_id,tag_id)',
        'website_urls': 'website_id INT, url VARCHAR(255)',
        'locations': 'id INT PRIMARY KEY, lat DOUBLE, lng DOUBLE',
        'dedupe_dismissed_pairs': ('event_id_a INT, event_id_b INT, reason VARCHAR(500), '
                                   'dismissed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, '
                                   'UNIQUE(event_id_a,event_id_b), CHECK(event_id_a < event_id_b)'),
    }

    def test_block_copied_onto_keeper_removes_keepers_tag(self):
        import merger
        self.cur.execute('INSERT INTO locations VALUES (10,40.7,-74)')
        for eid in (1, 2):
            self.cur.execute("INSERT INTO events(id,name,website_id,location_id,location_name) "
                             "VALUES (%s,'Lunch Hour Talk',101,10,'Centro')", (eid,))
            self.cur.execute('INSERT INTO event_occurrences(event_id,start_date,start_time,end_time) '
                             "VALUES (%s,%s,'1pm','2pm')", (eid, self.DAY))
            self.cur.execute('INSERT INTO event_sources VALUES (%s,%s)', (eid, 100 + eid))
            self.cur.execute('INSERT INTO event_tags VALUES (%s,%s)', (eid, OTHER))
        # Keeper (lower id) holds the tag; the twin carries the judged block.
        self.cur.execute('INSERT INTO event_tags VALUES (1,%s)', (BLOCKED,))
        self.cur.execute("INSERT INTO event_tag_blocks VALUES (2,%s,'judged')", (BLOCKED,))
        self.assertEqual(merger._deduplicate_same_name_events(
            self.cur, self.conn, self.DAY, website_ids=[101]), 1)
        self.assertEqual(self.keeper_state(1), ([OTHER], [BLOCKED]))


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1',
                     'Opt in to connection-local MariaDB tests with FOMO_TEST_TEMP_DB=1')
class ReviewedMergePairBlockTests(TempTablesMixin, unittest.TestCase):
    SCHEMAS = {
        'events': ("id INT PRIMARY KEY, name VARCHAR(500) DEFAULT '', website_id INT, location_id INT, "
                   'archived INT DEFAULT 0, suppressed INT DEFAULT 0, reviewed INT DEFAULT 0'),
        'event_occurrences': ('id INT AUTO_INCREMENT PRIMARY KEY, event_id INT, '
                              'start_date DATE, start_time VARCHAR(20), end_date DATE, '
                              'end_time VARCHAR(20), sort_order INT DEFAULT 0'),
        'event_urls': 'event_id INT, url VARCHAR(255), sort_order INT DEFAULT 0, UNIQUE(event_id,url)',
        'event_merge_redirects': ('duplicate_id INT PRIMARY KEY, survivor_id INT, '
                                  'survivor_name VARCHAR(500), source_identities JSON'),
        'dedupe_dismissed_pairs': 'event_id_a INT, event_id_b INT',
        'crawl_events': 'id INT, name VARCHAR(500), url VARCHAR(500), location_id INT, crawl_result_id INT',
        'crawl_results': 'id INT, website_id INT',
        'crawl_event_occurrences': 'crawl_event_id INT, start_date DATE, start_time VARCHAR(20), end_date DATE',
        'website_urls': 'website_id INT, url VARCHAR(500)',
        'event_tags': 'event_id INT, tag_id INT, UNIQUE(event_id,tag_id)',
        'event_sources': 'event_id INT, crawl_event_id INT, UNIQUE(event_id,crawl_event_id)',
        'event_tag_blocks': 'event_id INT, tag_id INT, reason TEXT, UNIQUE(event_id,tag_id)',
    }

    def test_block_copied_onto_keeper_removes_keepers_tag(self):
        from find_duplicate_events import merge_pair
        self.cur.execute('INSERT INTO events(id) VALUES (1),(2)')
        self.cur.execute('INSERT INTO event_tags VALUES (1,%s),(1,%s),(2,%s)', (BLOCKED, OTHER, OTHER))
        self.cur.execute("INSERT INTO event_tag_blocks VALUES (2,%s,'judged')", (BLOCKED,))
        merge_pair(self.cur, 1, 2)
        self.assertEqual(self.keeper_state(1), ([OTHER], [BLOCKED]))


if __name__ == '__main__':
    unittest.main()
