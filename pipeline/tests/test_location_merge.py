"""Opt-in DB cases shadow every touched table on one connection; no live rows."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dblock
import location_merge as merge


class CachedReferenceTests(unittest.TestCase):
    def rewrite(self, value):
        return json.loads(merge.remap_json(json.dumps(value), 12, 34, 'Old', 'New'))

    def test_both_cache_shapes_and_nested_references(self):
        for value in ([dict(location_id=12, location='Old')],
                      dict(events=[dict(location_id=12, location_name='Old')])):
            result = self.rewrite(value)
            self.assertNotIn('12', json.dumps(result))
            self.assertIn('New', json.dumps(result))

    def test_preserves_representation_and_other_fields(self):
        row = dict(location_id='12', location='Custom room', id=12,
                   description='Old location_id 12', occurrences=[dict(start_date='2026-10-12')])
        self.assertEqual(self.rewrite(row), dict(row, location_id='34'))

    def test_does_not_guess_unassigned_or_conflicting_location(self):
        for ref in (None, 99, False, 12.0):
            value = dict(location_id=ref, location='Old')
            self.assertEqual(self.rewrite(value), value)
        self.assertEqual(self.rewrite(dict(location='Old')), dict(location='Old'))

    def test_unchanged_cache_keeps_exact_bytes(self):
        raw = '[ {"location_id":99,"location":"Old"} ]'
        self.assertEqual(merge.remap_json(raw, 12, 34, 'Old', 'New'), raw)

    def test_invalid_json_fails(self):
        with self.assertRaises(ValueError):
            merge.remap_json('{bad', 12, 34, 'Old', 'New')

    def test_link_collision_fills_url_and_keeps_primary(self):
        self.assertEqual(merge.merge_link_metadata(
            dict(website_id=1, url=None, is_primary=0), dict(url='https://venue.test', is_primary=1)),
            dict(url='https://venue.test', is_primary=1))

    def test_link_conflict_is_explicit(self):
        with self.assertRaisesRegex(ValueError, 'Website 1'):
            merge.merge_link_metadata(dict(website_id=1, url='a', is_primary=1), dict(url='b', is_primary=0))

    def test_invalid_and_overlapping_pairs(self):
        for pairs in ([(1, 1)], [(0, 1)], [(1, 2), (2, 3)], [(1, 3), (2, 3)]):
            with self.subTest(pairs=pairs), self.assertRaises(ValueError):
                merge.validate_pairs(pairs)


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1', 'Opt in to connection-local MariaDB fixtures')
class LocationMergeDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = merge.create_connection()
        self.addCleanup(self.conn.close)
        self.cursor = self.conn.cursor(dictionary=True)
        self.addCleanup(self.cursor.close)
        # No real location inserts, triggers, or foreign keys. Each table is
        # shadowed BEFORE any fixture write; InnoDB exercises real rollback.
        self.cursor.execute('''CREATE TEMPORARY TABLE locations ENGINE=InnoDB AS
            SELECT 12 AS id, CAST('Old' AS CHAR(255)) AS name, 'keeper metadata' AS description
            UNION ALL SELECT 34, 'New', 'keeper metadata'
            UNION ALL SELECT 56, 'Second old', 'second metadata'
            UNION ALL SELECT 78, 'Second new', 'second metadata' ''')
        schemas = {
            'events': 'id INT PRIMARY KEY, location_id INT, location_name VARCHAR(255), name VARCHAR(255)',
            'crawl_events': 'id INT PRIMARY KEY, location_id INT, location_name VARCHAR(255), raw_data LONGTEXT',
            'crawl_results': 'id INT PRIMARY KEY, extracted_content LONGTEXT',
            'website_locations': 'id INT PRIMARY KEY, website_id INT, location_id INT, is_primary BOOL, url VARCHAR(500), UNIQUE(website_id,location_id)',
            'event_venue_overrides': 'id INT PRIMARY KEY, location_id INT, location_name VARCHAR(255)',
            'location_match_policies': 'location_id INT PRIMARY KEY, ambiguous_bare_names JSON',
            'location_tags': 'id INT PRIMARY KEY, location_id INT, tag_id INT, UNIQUE(location_id,tag_id)',
            'location_instagram': 'location_id INT, instagram_id INT, PRIMARY KEY(location_id,instagram_id)',
            'location_alternate_names': 'id INT AUTO_INCREMENT PRIMARY KEY, location_id INT, alternate_name VARCHAR(255), website_id INT NULL, portable BOOL DEFAULT 1',
            'edits': 'id INT AUTO_INCREMENT PRIMARY KEY, edit_uuid VARCHAR(36), table_name VARCHAR(64), record_id INT, field_name VARCHAR(64), action VARCHAR(10), old_value LONGTEXT, new_value LONGTEXT, source VARCHAR(20), user_id INT, editor_ip VARCHAR(50), editor_user_agent TEXT, editor_info TEXT, applied_at DATETIME',
        }
        for table, columns in schemas.items():
            self.cursor.execute(f'CREATE TEMPORARY TABLE {table} ({columns}) ENGINE=InnoDB')
        self.cursor.execute("INSERT INTO events VALUES (1,12,'Old','Preserved title'),(2,12,'Custom room','Another'),(3,99,'Old','Unrelated')")
        self.cursor.execute('INSERT INTO crawl_events VALUES (1,12,%s,%s),(2,34,%s,%s)',
                            ('Old', json.dumps(dict(location_id=12, location='Old', id=12)),
                             'New', json.dumps(dict(location_id='12', location='Custom'))))
        self.cursor.execute('INSERT INTO crawl_results VALUES (1,%s),(2,%s),(3,%s)',
                            (json.dumps([dict(location_id=12, location='Old')]),
                             json.dumps(dict(events=[dict(location_id='12', location='Old')])),
                             '[ {"location_id":99,"location":"Old"} ]'))
        self.cursor.execute("INSERT INTO website_locations VALUES (1,5,12,1,'https://venue.test'),(2,5,34,0,NULL),(3,6,12,0,'https://other.test')")
        self.cursor.execute('INSERT INTO location_tags VALUES (1,12,7),(2,34,7),(3,12,8)')
        self.cursor.execute('INSERT INTO location_instagram VALUES (12,7),(34,7),(12,8)')
        self.cursor.execute("INSERT INTO location_alternate_names (id,location_id,alternate_name,website_id) VALUES (1,12,'Scoped',5),(2,34,'Scoped',NULL),(3,12,'Shared',5),(4,34,'shared',5),(5,12,'Scoped',6),(6,12,'Scoped',5)")
        self.conn.commit()
        self.lock_name = 'location_merge_test_' + uuid.uuid4().hex
        real_lock = dblock.write_lock
        self.lock_patch = patch.object(merge, 'write_lock', side_effect=lambda conn, **kw: real_lock(conn, name=self.lock_name, **kw))
        self.lock_patch.start()
        self.addCleanup(self.lock_patch.stop)
        bookkeeping = patch.object(dblock, '_set_holder')
        bookkeeping.start()
        self.addCleanup(bookkeeping.stop)

    def rows(self, table, order='id'):
        self.cursor.execute(f'SELECT * FROM {table} ORDER BY {order}')
        return self.cursor.fetchall()

    def run_merge(self, **kwargs):
        return merge.merge_locations(self.conn, [(12, 34)], **kwargs)

    def test_preserves_restrictive_alias_and_name_policies(self):
        self.cursor.execute("UPDATE location_alternate_names SET portable=0 WHERE id=3")
        self.cursor.execute('INSERT INTO location_match_policies VALUES (12,%s),(34,%s)',
                            ('["Brand"]', '["Other brand"]'))
        self.conn.commit()
        self.run_merge()
        self.cursor.execute('SELECT portable FROM location_alternate_names WHERE id=4')
        self.assertEqual(self.cursor.fetchone()['portable'], 0)
        self.assertEqual(self.rows('location_match_policies', 'location_id'),
                         [dict(location_id=34, ambiguous_bare_names='["Brand", "Other brand"]')])

    def test_full_merge_preserves_scopes_metadata_and_caches(self):
        result = self.run_merge()
        self.assertFalse(result['dry_run'])
        self.assertEqual([r['id'] for r in self.rows('locations')], [34,56,78])
        events = self.rows('events')
        self.assertEqual([(r['location_id'], r['location_name']) for r in events], [(34,'New'),(34,'Custom room'),(99,'Old')])
        self.assertEqual(events[0]['name'], 'Preserved title')
        aliases = self.rows('location_alternate_names')
        self.assertEqual({(r['alternate_name'],r['website_id']) for r in aliases},
                         {('Scoped',None),('Scoped',5),('Scoped',6),('shared',5),('Old',None)})
        self.assertTrue(all(r['location_id'] == 34 for r in aliases))
        links = self.rows('website_locations')
        self.assertEqual(links[0], dict(id=2,website_id=5,location_id=34,is_primary=1,url='https://venue.test'))
        self.assertEqual([r['tag_id'] for r in self.rows('location_tags')], [7,8])
        self.assertEqual(self.rows('location_instagram','instagram_id'), [dict(location_id=34,instagram_id=7),dict(location_id=34,instagram_id=8)])
        source = self.rows('crawl_events')
        self.assertEqual(json.loads(source[0]['raw_data']), dict(location_id=34,location='New',id=12))
        self.assertEqual(json.loads(source[1]['raw_data']), dict(location_id='34',location='Custom'))
        caches = self.rows('crawl_results')
        self.assertEqual(json.loads(caches[0]['extracted_content']), [dict(location_id=34,location='New')])
        self.assertEqual(json.loads(caches[1]['extracted_content']), dict(events=[dict(location_id='34',location='New')]))
        self.assertEqual(caches[2]['extracted_content'], '[ {"location_id":99,"location":"Old"} ]')
        self.assertTrue(any(r['table_name']=='locations' and r['action']=='DELETE' for r in self.rows('edits')))

    def test_dry_run_is_read_only_and_no_edit_log(self):
        before = self.rows('location_alternate_names')
        self.conn.rollback()
        result = self.run_merge(dry_run=True)
        self.assertTrue(result['changes']['crawl_results.update'])
        self.assertEqual(self.rows('location_alternate_names'), before)
        self.assertEqual(len(self.rows('locations')), 4)
        self.assertFalse(self.rows('edits'))
        merge.write_lock.assert_not_called()

    def test_url_conflict_aborts_without_writes(self):
        self.cursor.execute("UPDATE website_locations SET url='https://conflict.test' WHERE id=2")
        self.conn.commit()
        with self.assertRaisesRegex(ValueError, 'conflicting location URLs'):
            self.run_merge()
        self.assertEqual(self.rows('events')[0]['location_id'], 12)
        self.assertFalse(self.rows('edits'))

    def test_malformed_affected_json_aborts(self):
        self.cursor.execute("UPDATE crawl_results SET extracted_content=%s WHERE id=1", ('[{"location_id":12}, broken]',))
        self.conn.commit()
        with self.assertRaisesRegex(ValueError, 'crawl_results.extracted_content, row 1'):
            self.run_merge()
        self.assertEqual(len(self.rows('locations')), 4)
        self.assertFalse(self.rows('edits'))

    def test_late_failure_rolls_back_data_and_edits_and_releases_lock(self):
        original = merge.EditLogger.log_delete
        def fail(logger, table, *args):
            if table == 'locations':
                raise RuntimeError('injected late failure')
            return original(logger, table, *args)
        with patch.object(merge.EditLogger, 'log_delete', fail), self.assertRaisesRegex(RuntimeError, 'injected'):
            self.run_merge()
        self.assertEqual(len(self.rows('locations')), 4)
        self.assertEqual(self.rows('events')[0]['location_id'], 12)
        self.assertEqual(len(self.rows('location_alternate_names')), 6)
        self.assertFalse(self.rows('edits'))
        self.cursor.execute('SELECT IS_FREE_LOCK(%s) AS free', (self.lock_name,))
        self.assertEqual(self.cursor.fetchone()['free'], 1)

    def test_lock_contention_prevents_writes(self):
        other = merge.create_connection()
        try:
            with dblock.write_lock(other, name=self.lock_name):
                with self.assertRaises(TimeoutError):
                    self.run_merge(lock_timeout=0)
            self.assertEqual(len(self.rows('locations')), 4)
            self.assertFalse(self.rows('edits'))
        finally:
            other.close()

    def test_missing_location_aborts(self):
        with self.assertRaisesRegex(ValueError, 'Missing duplicate'):
            merge.merge_locations(self.conn, [(12, 999)])
        self.assertFalse(self.rows('edits'))

    def test_batch_preserves_both_changes_to_a_shared_cache(self):
        self.cursor.execute('UPDATE crawl_results SET extracted_content=%s WHERE id=1',
                            (json.dumps([dict(location_id=12),dict(location_id=56)]),))
        self.conn.commit()
        merge.merge_locations(self.conn, [(12,34),(56,78)])
        self.assertEqual(json.loads(self.rows('crawl_results')[0]['extracted_content']),
                         [dict(location_id=34),dict(location_id=78)])

    def test_later_pair_failure_rolls_back_entire_batch(self):
        with self.assertRaisesRegex(ValueError, 'Missing duplicate'):
            merge.merge_locations(self.conn, [(12,34),(56,999)])
        self.assertEqual(len(self.rows('locations')), 4)
        self.assertEqual(self.rows('events')[0]['location_id'], 12)
        self.assertFalse(self.rows('edits'))

    def test_existing_transaction_is_not_committed_or_rolled_back(self):
        self.cursor.execute("UPDATE events SET name='Pending caller change' WHERE id=1")
        with self.assertRaisesRegex(ValueError, 'fresh connection'):
            self.run_merge()
        self.assertTrue(self.conn.in_transaction)
        self.conn.rollback()
        self.assertEqual(self.rows('events')[0]['name'], 'Preserved title')


if __name__ == '__main__':
    unittest.main()
