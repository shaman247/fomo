"""Post-merge cleanup must respect website scope and reviewed pair decisions.

The MariaDB cases use connection-local temporary tables only; opt in with
FOMO_TEST_TEMP_DB=1. The caller tests need no database connection.
"""
from contextlib import ExitStack, redirect_stdout
from datetime import date, timedelta
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger
from db import create_connection


class MergeScopeForwardingTests(unittest.TestCase):
    def run_merge(self, website_ids):
        today = date(2026, 9, 20)
        cursor = MagicMock(lastrowid=1000)

        def execute(query, params=None):
            rows = []
            if 'SELECT ce.id, ce.name' in query:
                rows = [(1, 'Test Outdoor Walk', None, 'A guided walk.', '🌳',
                         'Test Venue', None, 10, None, 101, None, None, 100)]
            elif 'FROM crawl_event_occurrences' in query:
                rows = [(1, today, '3pm', None, '4pm', 0)]
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
            cleanup = stack.enter_context(patch.object(
                merger, '_deduplicate_same_name_events', return_value=0))
            connection = MagicMock()
            self.assertEqual(merger.merge_crawl_events(
                cursor, connection, website_ids=website_ids), (1, 0))
            cleanup.assert_called_once_with(
                cursor, connection, today, None, website_ids=website_ids)
            # Disabled sources never enter a normal run's frozen crawl list.
            # Their separate maintenance sweep must remain global, even when
            # candidate merging and duplicate cleanup are website-filtered.
            db.archive_dead_source_events.assert_called_once_with(
                cursor, connection, temps_built=True)

    def test_targeted_merge_forwards_all_requested_websites(self):
        self.run_merge([101, 202])

    def test_unfiltered_merge_preserves_global_cleanup(self):
        self.run_merge(None)

    def test_empty_filter_keeps_existing_unfiltered_semantics(self):
        self.run_merge([])


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1',
                     'Opt in to connection-local MariaDB tests with FOMO_TEST_TEMP_DB=1')
class PostMergeScopeDatabaseTests(unittest.TestCase):
    DAY = date(2026, 9, 28)
    CHILD_TABLES = ('event_occurrences', 'event_sources', 'event_urls',
                    'event_tags', 'event_tag_blocks')

    def setUp(self):
        self.conn = create_connection()
        self.assertIsNotNone(self.conn)
        self.addCleanup(self.conn.close)
        self.cur = self.conn.cursor()
        schemas = {
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
        # Every table the cleanup can access is shadowed before test writes.
        for table, schema in schemas.items():
            self.cur.execute(f'CREATE TEMPORARY TABLE {table} ({schema})')
        icons = patch('event_icon_assignments.merge_assignments')
        icons.start()
        self.addCleanup(icons.stop)
        self.cur.execute('INSERT INTO locations VALUES (10,40.7,-74),(20,41,-73)')
        self.seed_pair(101, 1)
        self.seed_pair(202, 3)

    def seed_pair(self, website_id, first_id):
        for eid in (first_id, first_id + 1):
            self.cur.execute('INSERT INTO events(id,name,website_id,location_id,location_name) '
                             'VALUES (%s,%s,%s,10,%s)',
                             (eid, 'Guided Walk', website_id, 'Test Venue'))
            self.cur.execute('INSERT INTO event_occurrences '
                             '(event_id,start_date,start_time,end_time) VALUES (%s,%s,%s,%s)',
                             (eid, self.DAY, '3pm', '4pm'))
            self.cur.execute('INSERT INTO event_sources VALUES (%s,%s)', (eid, 100 + eid))
            self.cur.execute('INSERT INTO event_urls VALUES (%s,%s)',
                             (eid, f'https://example.test/{website_id}/walk'))
            self.cur.execute('INSERT INTO event_tags VALUES (%s,10)', (eid,))
            self.cur.execute("INSERT INTO event_tag_blocks VALUES (%s,20,'reviewed')", (eid,))

    def cleanup(self, website_ids=None):
        return merger._deduplicate_same_name_events(
            self.cur, self.conn, self.DAY, website_ids=website_ids)

    def ids(self):
        self.cur.execute('SELECT id FROM events ORDER BY id')
        return [row[0] for row in self.cur.fetchall()]

    def unrelated_snapshot(self):
        snapshot = {}
        for table, key in [('events', 'id'), *[(t, 'event_id') for t in self.CHILD_TABLES]]:
            self.cur.execute(f'SELECT * FROM {table} WHERE {key} IN (3,4) ORDER BY 1,2')
            snapshot[table] = self.cur.fetchall()
        return snapshot

    def test_one_website_preserves_unrelated_event_and_child_rows(self):
        before = self.unrelated_snapshot()
        self.cur.execute('INSERT INTO event_occurrences(event_id,start_date,start_time) '
                         'VALUES (2,%s,%s)', (self.DAY + timedelta(days=7), '3pm'))
        self.assertEqual(self.cleanup([101]), 1)
        self.assertEqual(self.ids(), [1, 3, 4])
        self.assertEqual(self.unrelated_snapshot(), before)
        self.cur.execute('SELECT crawl_event_id FROM event_sources WHERE event_id=1 ORDER BY 1')
        self.assertEqual(self.cur.fetchall(), [(101,), (102,)])
        self.cur.execute('SELECT start_date FROM event_occurrences WHERE event_id=1 ORDER BY 1')
        self.assertEqual(self.cur.fetchall(), [(self.DAY,), (self.DAY + timedelta(days=7),)])

    def test_multiple_requested_websites_leave_third_website_alone(self):
        self.seed_pair(303, 5)
        self.assertEqual(self.cleanup([101, 202]), 2)
        self.assertEqual(self.ids(), [1, 3, 5, 6])

    def test_unfiltered_cleanup_still_processes_both_websites(self):
        self.assertEqual(self.cleanup(), 2)
        self.assertEqual(self.ids(), [1, 3])

    def test_empty_filter_matches_unfiltered_merge_semantics(self):
        self.assertEqual(self.cleanup([]), 2)
        self.assertEqual(self.ids(), [1, 3])

    def test_unknown_website_does_not_fall_back_to_global_cleanup(self):
        before = self.unrelated_snapshot()
        self.assertEqual(self.cleanup([999]), 0)
        self.assertEqual(self.ids(), [1, 2, 3, 4])
        self.assertEqual(self.unrelated_snapshot(), before)

    def test_different_known_venues_remain_separate(self):
        self.cur.execute('UPDATE events SET location_id=20 WHERE id=2')
        self.assertEqual(self.cleanup([101]), 0)
        self.assertEqual(self.ids(), [1, 2, 3, 4])

    def test_archived_lower_id_never_becomes_keeper(self):
        self.cur.execute('UPDATE events SET archived=1,suppressed=1 WHERE id=1')
        self.assertEqual(self.cleanup([101]), 1)
        self.assertEqual(self.ids(), [2, 3, 4])
        self.cur.execute('SELECT archived,suppressed FROM events WHERE id=2')
        self.assertEqual(self.cur.fetchone(), (0, 0))

    def test_dismissed_archived_pair_remains_separate(self):
        self.cur.execute('UPDATE events SET archived=1 WHERE id=1')
        self.cur.execute('INSERT INTO dedupe_dismissed_pairs(event_id_a,event_id_b) VALUES (1,2)')
        self.assertEqual(self.cleanup([101]), 0)
        self.assertEqual(self.ids(), [1, 2, 3, 4])

    def add_candidate(self, eid, *, archived=0, day=None):
        self.cur.execute('INSERT INTO events '
                         '(id,name,website_id,location_id,location_name,archived) '
                         "VALUES (%s,'Guided Walk',101,10,'Test Venue',%s)", (eid, archived))
        self.cur.execute('INSERT INTO event_occurrences '
                         '(event_id,start_date,start_time,end_time) VALUES (%s,%s,%s,%s)',
                         (eid, day or self.DAY, '3pm', '4pm'))
        self.cur.execute('INSERT INTO event_sources VALUES (%s,%s)', (eid, 100 + eid))

    def dismiss(self, a, b, reason='Distinct programs'):
        self.cur.execute('INSERT INTO dedupe_dismissed_pairs '
                         '(event_id_a,event_id_b,reason,dismissed_at) VALUES (%s,%s,%s,%s)',
                         (*sorted((a, b)), reason, '2026-09-01 12:00:00'))

    def test_dismissed_active_pair_keeps_both_events_and_sources(self):
        self.dismiss(1, 2)
        self.assertEqual(self.cleanup([101]), 0)
        self.assertEqual(self.ids(), [1, 2, 3, 4])
        self.cur.execute('SELECT event_id,crawl_event_id FROM event_sources ORDER BY 1,2')
        self.assertEqual(self.cur.fetchall(), [(1, 101), (2, 102), (3, 103), (4, 104)])

    def test_active_chain_transfers_dismissal_and_survives_next_run(self):
        self.add_candidate(5)
        self.dismiss(2, 5)
        self.assertEqual(self.cleanup([101]), 1)
        self.assertEqual(self.ids(), [1, 3, 4, 5])
        self.cur.execute('SELECT reason,dismissed_at FROM dedupe_dismissed_pairs '
                         'WHERE event_id_a=1 AND event_id_b=5')
        reason, when = self.cur.fetchone()
        self.assertEqual(reason, 'Distinct programs')
        self.assertEqual(str(when), '2026-09-01 12:00:00')
        self.assertEqual(self.cleanup([101]), 0)
        self.assertEqual(self.ids(), [1, 3, 4, 5])

    def test_chain_across_different_dates_preserves_dismissal(self):
        later = self.DAY + timedelta(days=7)
        self.add_candidate(5, day=later)
        self.cur.execute('INSERT INTO event_occurrences(event_id,start_date,start_time) '
                         'VALUES (2,%s,%s)', (later, '3pm'))
        self.dismiss(2, 5)
        self.assertEqual(self.cleanup([101]), 1)
        self.assertEqual(self.ids(), [1, 3, 4, 5])

    def test_archived_twin_respects_dismissal_inherited_from_active_merge(self):
        self.add_candidate(5, archived=1)
        self.dismiss(2, 5)
        self.assertEqual(self.cleanup([101]), 1)
        self.assertEqual(self.ids(), [1, 3, 4, 5])

    def test_archived_merge_transfers_decision_to_higher_id_keeper(self):
        self.cur.execute('UPDATE events SET archived=1 WHERE id=1')
        self.dismiss(1, 5)
        self.assertEqual(self.cleanup([101]), 1)
        self.add_candidate(5)
        self.assertEqual(self.cleanup([101]), 0)
        self.assertEqual(self.ids(), [2, 3, 4, 5])

    def test_conflicting_active_pair_still_allows_compatible_third_event(self):
        self.add_candidate(5)
        self.dismiss(1, 2)
        self.assertEqual(self.cleanup([101]), 1)
        self.assertEqual(self.ids(), [1, 2, 3, 4])
        self.cur.execute('SELECT crawl_event_id FROM event_sources WHERE event_id=1 ORDER BY 1')
        self.assertEqual(self.cur.fetchall(), [(101,), (105,)])

    def test_two_archived_twins_cannot_merge_through_shared_active_keeper(self):
        self.add_candidate(5, archived=1)
        self.add_candidate(6, archived=1)
        self.dismiss(5, 6)
        self.assertEqual(self.cleanup([101]), 2)
        self.assertEqual(self.ids(), [1, 3, 4, 6])

    def test_existing_keeper_decision_metadata_is_not_overwritten(self):
        self.dismiss(1, 999, 'Original keeper decision')
        self.dismiss(2, 999, 'Decision on absorbed event')
        self.assertEqual(self.cleanup([101]), 1)
        self.cur.execute('SELECT reason FROM dedupe_dismissed_pairs '
                         'WHERE event_id_a=1 AND event_id_b=999')
        self.assertEqual(self.cur.fetchone(), ('Original keeper decision',))
        # Preserve the original record as evidence, even after its event is absorbed.
        self.cur.execute('SELECT reason FROM dedupe_dismissed_pairs '
                         'WHERE event_id_a=2 AND event_id_b=999')
        self.assertEqual(self.cur.fetchone(), ('Decision on absorbed event',))

    def test_inherited_pair_is_ordered_when_other_event_is_below_keeper(self):
        self.cur.execute('UPDATE events SET archived=1 WHERE id=1')
        self.cur.execute('UPDATE events SET suppressed=1 WHERE id=2')
        self.add_candidate(5)
        self.dismiss(1, 3)
        self.assertEqual(self.cleanup([101]), 1)
        self.cur.execute('SELECT reason FROM dedupe_dismissed_pairs '
                         'WHERE event_id_a=3 AND event_id_b=5')
        self.assertEqual(self.cur.fetchone(), ('Distinct programs',))

    def test_two_merged_groups_cannot_swallow_a_dismissed_relationship(self):
        later = self.DAY + timedelta(days=7)
        self.add_candidate(5, day=later)
        self.add_candidate(6, day=later)
        self.dismiss(2, 6)
        # Connect both duplicate groups through another date. Regardless of
        # group iteration order, the two reviewed identities must stay apart.
        for eid in (1, 5):
            self.cur.execute('INSERT INTO event_occurrences(event_id,start_date,start_time) '
                             'VALUES (%s,%s,%s)', (eid, later + timedelta(days=7), '3pm'))
        self.assertEqual(self.cleanup([101]), 2)
        self.cur.execute('SELECT event_id FROM event_sources WHERE crawl_event_id=102')
        first_owner = self.cur.fetchone()[0]
        self.cur.execute('SELECT event_id FROM event_sources WHERE crawl_event_id=106')
        second_owner = self.cur.fetchone()[0]
        self.assertNotEqual(first_owner, second_owner)
        self.assertEqual(self.cleanup([101]), 0)

    def test_cleanup_rehomes_previously_reviewed_redirect_targets(self):
        self.cur.execute("INSERT INTO events(id,name,website_id,location_id,suppressed) VALUES (5,'Old Alias',101,10,1)")
        self.cur.execute("INSERT INTO event_merge_redirects VALUES (5,2,'Guided Walk')")
        self.assertEqual(self.cleanup([101]),1)
        self.cur.execute('SELECT survivor_id,survivor_name FROM event_merge_redirects WHERE duplicate_id=5')
        self.assertEqual(self.cur.fetchone(),(1,'Guided Walk'))


if __name__ == '__main__':
    unittest.main()
