"""Execute archival SQL against failed attempts and short calendar horizons."""
import os
import unittest
import uuid

from test_archival import ArchivalTestBase, SCHEMA, _days_ahead, db


class CrawlCoverageArchivalTests(ArchivalTestBase):
    def build_missing(self, *, future=30):
        self.add_website(1)
        self.add_event(100, 1, future_days=future)
        self.add_crawl(10, 1, 60, [100])
        self.add_crawl(11, 1, 20)
        self.add_crawl(12, 1, 1)

    def visible_date(self, crawl_id, start, end=None):
        self._crawl_event_seq += 1
        ce = self._crawl_event_seq
        self.connection.execute('INSERT INTO crawl_events VALUES (?, ?, ?)',
                                (ce, crawl_id, 'Other listed program'))
        self.connection.execute('INSERT INTO crawl_event_occurrences VALUES (?, ?, ?)',
                                (ce, _days_ahead(start), _days_ahead(end) if end else None))

    def archive(self):
        return db.archive_outdated_events(self.cursor, self.connection, 1)

    def test_failed_or_unprocessed_latest_attempt_is_not_negative_evidence(self):
        self.build_missing()
        self.add_crawl(13, 1, 0, status='failed')
        for status in ['failed', 'pending', 'crawled']:
            self.connection.execute('UPDATE crawl_results SET status=? WHERE id=13', (status,))
            self.assertEqual(self.archive()[0], 0)
        self.connection.execute('UPDATE crawl_results SET status=?,processed_at=NULL WHERE id=13',
                                ('extracted',))
        self.assertEqual(self.archive()[0], 0)

    def test_successful_recovery_restores_normal_archival(self):
        self.build_missing()
        self.add_crawl(13, 1, 0, status='failed')
        self.assertEqual(self.archive()[0], 0)
        self.add_crawl(14, 1, 0)
        self.assertEqual(self.archive()[0], 1)

    def test_other_publisher_merge_cannot_archive_failed_source_event(self):
        self.build_missing()
        self.add_website(2)
        self.add_crawl(20, 2, 50, [100])
        self.add_crawl(21, 2, 15)
        self.add_crawl(22, 2, 0, status='failed')
        self.assertEqual(self.archive()[0], 0)

    def test_event_beyond_visible_horizon_stays_active(self):
        self.build_missing(future=30)
        self.visible_date(12, 15)
        self.assertEqual(self.archive()[0], 0)

    def test_end_of_long_exhibition_does_not_extend_listing_horizon(self):
        self.build_missing(future=30)
        self.visible_date(12, 10, 300)
        self.assertEqual(self.archive()[0], 0)

    def test_within_horizon_event_can_still_archive(self):
        self.build_missing(future=10)
        self.visible_date(12, 15)
        self.assertEqual(self.archive()[0], 1)

    def test_complete_empty_calendar_can_still_archive(self):
        self.build_missing()
        self.assertEqual(self.archive()[0], 1)

    def test_failed_latest_attempt_does_not_protect_expired_events(self):
        self.build_missing(future=None)
        self.add_crawl(13, 1, 0, status='failed')
        self.assertEqual(self.archive()[0], 1)

    def test_disabled_failed_source_does_not_pin_event(self):
        self.build_missing()
        self.add_website(2, disabled=True)
        self.add_crawl(20, 2, 50, [100])
        self.add_crawl(21, 2, 0, status='failed')
        self.assertEqual(self.archive()[0], 1)

    def test_old_far_future_source_does_not_expand_latest_horizon(self):
        self.build_missing()
        self.visible_date(11, 90)
        self.visible_date(12, 15)
        self.assertEqual(self.archive()[0], 0)


class _MariaFixtureConnection:
    """Allow the same fixture helpers to use real MariaDB instead of SQLite."""
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=()):
        cursor = self.connection.cursor(buffered=True)
        cursor.execute(sql.replace('?', '%s'), params)
        return cursor

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1', 'Opt in to isolated MariaDB fixtures')
class MariaCrawlCoverageTests(CrawlCoverageArchivalTests):
    def setUp(self):
        config = dict(db.get_db_config())
        config.pop('database', None)
        name = 'fomo_crawl_integrity_test_' + uuid.uuid4().hex
        admin = db.mysql.connector.connect(**config, autocommit=True)
        self.addCleanup(admin.close)
        with admin.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE `{name}`')
        def cleanup():
            with admin.cursor() as cursor:
                cursor.execute(f'DROP DATABASE `{name}`')
        self.addCleanup(cleanup)
        connection = db.mysql.connector.connect(**config, database=name)
        self.connection = _MariaFixtureConnection(connection)
        self.cursor = connection.cursor(buffered=True)
        # Fixture dates are ISO text in both engines; production query remains
        # completely unmodified in this run (including temp table declarations).
        for statement in SCHEMA.replace('INTEGER PRIMARY KEY', 'INTEGER AUTO_INCREMENT PRIMARY KEY').split(';'):
            if statement.strip():
                self.cursor.execute(statement)
        self._crawl_event_seq = 0


if __name__ == '__main__':
    unittest.main()
