"""Candidate reads must release locks without ending the caller's transaction.

Opt-in integration tests use a uniquely named fixture database, never application
rows. Browser work is mocked; the competing update runs during that network phase.
"""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import db
import liveness_probe as probe


class ProbeReaderCleanupTests(unittest.TestCase):
    def test_empty_candidates_release_reader(self):
        reader = MagicMock()
        with patch.object(db, 'create_connection', return_value=reader), \
                patch.object(probe, 'get_candidates', return_value=[]):
            self.assertEqual(probe._read_probe_inputs(None, 1), ([], [], {}, {}))
        reader.rollback.assert_called_once()
        reader.close.assert_called_once()
        reader.commit.assert_not_called()

    def test_failed_selection_releases_reader(self):
        reader = MagicMock()
        with patch.object(db, 'create_connection', return_value=reader), \
                patch.object(probe, 'get_candidates', side_effect=ValueError('selection failed')):
            with self.assertRaisesRegex(ValueError, 'selection failed'):
                probe._read_probe_inputs(None, 1)
        reader.cursor.return_value.close.assert_called_once()
        reader.rollback.assert_called_once()
        reader.close.assert_called_once()


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1',
                     'Opt in to isolated MariaDB fixtures with FOMO_TEST_TEMP_DB=1')
class ProbeTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = dict(db.get_db_config())
        cls.config.pop('database', None)
        cls.database = 'fomo_liveness_test_' + uuid.uuid4().hex
        cls.admin = db.mysql.connector.connect(**cls.config, autocommit=True)
        with cls.admin.cursor() as cur:
            cur.execute(f'CREATE DATABASE `{cls.database}`')
        cls.addClassCleanup(cls.drop_database)
        conn = cls.connect(autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute('CREATE TABLE event_occurrences '
                            '(id INT PRIMARY KEY, value VARCHAR(40)) ENGINE=InnoDB')
                cur.execute("INSERT INTO event_occurrences VALUES (1,'original')")
                cur.execute('CREATE TABLE caller_work '
                            '(id INT PRIMARY KEY, value VARCHAR(40)) ENGINE=InnoDB')
                cur.execute("INSERT INTO caller_work VALUES (1,'original')")
        finally:
            conn.close()

    @classmethod
    def connect(cls, **kwargs):
        return db.mysql.connector.connect(**cls.config, database=cls.database, **kwargs)

    @classmethod
    def drop_database(cls):
        try:
            with cls.admin.cursor() as cur:
                cur.execute(f'DROP DATABASE `{cls.database}`')
        finally:
            cls.admin.close()

    def test_dry_run_releases_source_locks_and_preserves_pending_caller_work(self):
        caller, writer = self.connect(), self.connect()
        self.addCleanup(caller.close)
        self.addCleanup(writer.close)
        self.addCleanup(caller.rollback)
        self.addCleanup(writer.rollback)
        cur = caller.cursor(buffered=True)
        cur.execute("UPDATE caller_work SET value='pending' WHERE id=1")

        def candidates(read_cursor, **kwargs):
            # Same lock-taking SQL shape used by build_archival_temps.
            read_cursor.execute('CREATE TEMPORARY TABLE probe_snapshot ENGINE=InnoDB '
                                'SELECT * FROM event_occurrences')
            read_cursor.execute('DROP TEMPORARY TABLE probe_snapshot')
            return [dict(event_id=1, name='Fixture', website_id=1, next_occ=None,
                         urls=['https://example.test/event'], still_listed=False)]

        async def network(plan):
            # This would time out if the reader merely dropped its temp tables.
            with writer.cursor() as wc:
                wc.execute('SET SESSION innodb_lock_wait_timeout=1')
                wc.execute("UPDATE event_occurrences SET value='writer pending' WHERE id=1")
                wc.execute('SELECT value FROM caller_work WHERE id=1')
                self.assertEqual(wc.fetchone(), ('original',))  # Caller wasn't committed.
            writer.rollback()
            cur.execute('SELECT value FROM caller_work WHERE id=1')
            self.assertEqual(cur.fetchone(), ('pending',))  # Caller wasn't rolled back.
            return {'https://example.test/event': dict(status=404),
                    'https://example.test/control': dict(status=200)}

        def verdict(url, status, *args):
            return ('dead' if status == 404 else 'alive', 'fixture')

        with patch.object(db, 'create_connection', side_effect=self.connect), \
                patch.object(probe, 'get_candidates', side_effect=candidates), \
                patch.object(db, 'get_website_crawl_settings', return_value={1: {}}), \
                patch.object(probe, 'get_control_urls', return_value={1: 'https://example.test/control'}), \
                patch.object(probe, 'probe_urls', side_effect=network), \
                patch.object(probe, 'classify', side_effect=verdict):
            stats = probe.run(cur, caller, dry_run=True, verbose=False)
        self.assertEqual(stats['dead'], 1)
        self.assertEqual(stats['archived'], 0)
        self.assertEqual(stats['probed'], 2)
        cur.execute('SELECT value FROM event_occurrences WHERE id=1')
        self.assertEqual(cur.fetchone(), ('original',))
        # No persistent verdict table exists: any accidental dry-run INSERT fails.

    def test_original_temp_table_shape_keeps_source_locks_until_transaction_ends(self):
        reader, writer = self.connect(), self.connect()
        self.addCleanup(reader.close)
        self.addCleanup(writer.close)
        self.addCleanup(reader.rollback)
        self.addCleanup(writer.rollback)
        with reader.cursor() as rc:
            rc.execute('CREATE TEMPORARY TABLE probe_snapshot ENGINE=InnoDB '
                       'SELECT * FROM event_occurrences')
            rc.execute('DROP TEMPORARY TABLE probe_snapshot')
        with writer.cursor() as wc:
            wc.execute('SET SESSION innodb_lock_wait_timeout=1')
            with self.assertRaises(db.mysql.connector.Error) as raised:
                wc.execute("UPDATE event_occurrences SET value='blocked' WHERE id=1")
            self.assertEqual(raised.exception.errno, 1205)
            reader.rollback()
            wc.execute("UPDATE event_occurrences SET value='unblocked' WHERE id=1")


if __name__ == '__main__':
    unittest.main()
