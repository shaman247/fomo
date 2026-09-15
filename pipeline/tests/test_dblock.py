"""Lock bookkeeping must not own the caller's transaction.

Unit tests run without a database. Opt in to MariaDB regression tests with
FOMO_TEST_TEMP_DB=1; they create and remove a uniquely named fixture database,
never read or write application event rows, and use unique advisory lock names.
"""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import db
import dblock


class BookkeepingTests(unittest.TestCase):
    def setUp(self):
        self.caller = MagicMock()
        self.caller.cursor.return_value.fetchone.return_value = (1,)

    def test_normal_exit_only_commits_separate_metadata_connections(self):
        entry, cleanup = MagicMock(), MagicMock()
        with patch.object(db, "create_connection", side_effect=[entry, cleanup]):
            with dblock.write_lock(self.caller, label="test writer"):
                self.caller.commit.assert_not_called()
            self.caller.commit.assert_not_called()
            self.caller.rollback.assert_not_called()
        for metadata in (entry, cleanup):
            metadata.commit.assert_called_once()
            metadata.close.assert_called_once()
        queries = [call.args[0] for call in self.caller.cursor.return_value.execute.call_args_list]
        self.assertTrue(all("GET_LOCK" in sql or "RELEASE_LOCK" in sql for sql in queries))

    def test_exception_leaves_caller_transaction_untouched_and_releases_lock(self):
        with patch.object(db, "create_connection", side_effect=[MagicMock(), MagicMock()]):
            with self.assertRaisesRegex(ValueError, "incomplete batch"):
                with dblock.write_lock(self.caller):
                    raise ValueError("incomplete batch")
        self.caller.commit.assert_not_called()
        self.caller.rollback.assert_not_called()
        self.caller.cursor.return_value.execute.assert_called_with(
            "SELECT RELEASE_LOCK(%s)", (dblock.LOCK_NAME,)
        )

    def test_missing_table_bootstrap_never_uses_caller_connection(self):
        metadata = MagicMock()
        missing_table = RuntimeError("table does not exist")
        missing_table.errno = 1146
        metadata.cursor.return_value.execute.side_effect = [missing_table, None, None]
        with patch.object(db, "create_connection", return_value=metadata):
            dblock._set_holder(self.caller, "test lock", "manual pipeline writer")
        self.caller.cursor.assert_not_called()
        self.caller.commit.assert_not_called()
        queries = [call.args[0] for call in metadata.cursor.return_value.execute.call_args_list]
        self.assertTrue(any(sql.startswith("CREATE TABLE") for sql in queries))
        metadata.commit.assert_called_once()
        metadata.close.assert_called_once()

    def test_bookkeeping_failure_does_not_replace_body_exception(self):
        with patch.object(db, "create_connection", side_effect=ConnectionError("metadata offline")):
            with self.assertRaisesRegex(ValueError, "original failure"):
                with dblock.write_lock(self.caller):
                    raise ValueError("original failure")
        self.caller.commit.assert_not_called()
        self.caller.cursor.return_value.execute.assert_called_with(
            "SELECT RELEASE_LOCK(%s)", (dblock.LOCK_NAME,)
        )

    def test_failed_metadata_write_closes_its_connection(self):
        metadata = MagicMock()
        metadata.cursor.return_value.execute.side_effect = RuntimeError("metadata write failed")
        with patch.object(db, "create_connection", return_value=metadata):
            with self.assertRaisesRegex(RuntimeError, "metadata write failed"):
                dblock._set_holder(self.caller, "test lock", "writer")
        metadata.commit.assert_not_called()
        metadata.close.assert_called_once()
        self.caller.commit.assert_not_called()


@unittest.skipUnless(os.environ.get("FOMO_TEST_TEMP_DB") == "1",
                     "Opt in to isolated MariaDB fixtures with FOMO_TEST_TEMP_DB=1")
class TransactionVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = dict(db.get_db_config())
        cls.config.pop("database", None)
        cls.database = "fomo_dblock_test_" + uuid.uuid4().hex
        cls.admin = db.mysql.connector.connect(**cls.config, autocommit=True)
        with cls.admin.cursor() as cur:
            cur.execute(f"CREATE DATABASE `{cls.database}`")
        cls.addClassCleanup(cls.drop_fixture_database)
        fixture = cls.connect(autocommit=True)
        try:
            with fixture.cursor() as cur:
                cur.execute("CREATE TABLE event_write_probe (id INT PRIMARY KEY, name VARCHAR(80)) ENGINE=InnoDB")
                cur.execute("INSERT INTO event_write_probe VALUES (1, 'original'), (2, 'original')")
        finally:
            fixture.close()

    @classmethod
    def connect(cls, **kwargs):
        return db.mysql.connector.connect(**cls.config, database=cls.database, **kwargs)

    @classmethod
    def drop_fixture_database(cls):
        try:
            with cls.admin.cursor() as cur:
                cur.execute(f"DROP DATABASE `{cls.database}`")
        finally:
            cls.admin.close()

    def setUp(self):
        self.caller = self.connect()
        self.observer = self.connect(autocommit=True)
        self.addCleanup(self.observer.close)
        self.addCleanup(self.caller.close)
        self.addCleanup(self.caller.rollback)
        with self.observer.cursor() as cur:
            cur.execute("UPDATE event_write_probe SET name='original'")
        self.lock_name = "fomo_dblock_test_" + uuid.uuid4().hex
        factory = patch.object(db, "create_connection", side_effect=self.connect)
        factory.start()
        self.addCleanup(factory.stop)

    def update(self, value, event_id=1):
        with self.caller.cursor() as cur:
            cur.execute("UPDATE event_write_probe SET name=%s WHERE id=%s", (value, event_id))

    def read(self, connection, event_id=1):
        with connection.cursor() as cur:
            cur.execute("SELECT name FROM event_write_probe WHERE id=%s", (event_id,))
            return cur.fetchone()[0]

    def test_pending_before_entry_survives_metadata_bootstrap_and_normal_exit(self):
        # Exercise implicit DDL commits as well as explicit metadata commits.
        with self.observer.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS db_write_lock_holder")
        self.update("pending before entry")
        with dblock.write_lock(self.caller, name=self.lock_name, label="pending writer"):
            self.assertEqual(self.read(self.observer), "original")
            self.assertEqual(dblock.acquired_by(self.observer, self.lock_name), "pending writer")
        self.assertEqual(self.read(self.observer), "original")
        self.assertEqual(self.read(self.caller), "pending before entry")
        self.assertIsNone(dblock.acquired_by(self.observer, self.lock_name))
        self.caller.rollback()
        self.assertEqual(self.read(self.observer), "original")

    def test_exception_does_not_expose_partial_event_write(self):
        with self.assertRaisesRegex(ValueError, "batch failed"):
            with dblock.write_lock(self.caller, name=self.lock_name, label="failing writer"):
                self.update("partial edit")
                self.assertEqual(self.read(self.observer), "original")
                self.assertEqual(dblock.acquired_by(self.observer, self.lock_name), "failing writer")
                raise ValueError("batch failed")
        self.assertFalse(dblock.is_locked(self.observer, self.lock_name))
        self.assertEqual(self.read(self.observer), "original")
        self.assertEqual(self.read(self.caller), "partial edit")
        self.caller.rollback()
        self.assertEqual(self.read(self.observer), "original")

    def test_explicit_caller_commit_remains_visible(self):
        with dblock.write_lock(self.caller, name=self.lock_name):
            self.update("complete edit")
            self.caller.commit()
            self.assertEqual(self.read(self.observer), "complete edit")
        self.assertEqual(self.read(self.observer), "complete edit")

    def test_timeout_reports_holder_without_committing_waiters_pending_work(self):
        with dblock.write_lock(self.observer, name=self.lock_name, label="other writer"):
            self.update("waiting edit", event_id=2)
            with self.assertRaisesRegex(TimeoutError, "other writer"):
                with dblock.write_lock(self.caller, name=self.lock_name, timeout=0):
                    self.fail("Contender acquired a held lock")
            self.assertEqual(self.read(self.observer, event_id=2), "original")
            self.assertEqual(self.read(self.caller, event_id=2), "waiting edit")


if __name__ == "__main__":
    unittest.main()
