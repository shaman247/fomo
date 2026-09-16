"""Large content writes stay bounded and never commit incomplete snapshots."""
import hashlib
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import db


class Connection:
    def __init__(self, autocommit=False):
        self.in_transaction = not autocommit
        self.value = 'previous snapshot'
        self.original = self.value
        self.commits = self.rollbacks = self.starts = 0
    def start_transaction(self):
        self.starts += 1
        self.in_transaction = True
    def commit(self):
        self.commits += 1
    def rollback(self):
        self.rollbacks += 1
        self.value = self.original


class Cursor:
    def __init__(self, conn, packet=4096, fail_at=None, corrupt=False, dictionaries=False):
        self.conn, self.packet = conn, packet
        self.fail_at, self.corrupt, self.dictionaries = fail_at, corrupt, dictionaries
        self.appends = 0
        self.calls = []
    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        # Bound the actual wire SQL, including worst-case quote/backslash escaping.
        size = len(sql.encode()) + sum(len(str(p).encode()) * 2 + 2 for p in params)
        if size >= self.packet:
            raise RuntimeError('packet too large')
        if " = '' WHERE" in sql:
            self.conn.value = ''
        elif 'CONCAT(' in sql:
            self.appends += 1
            if self.fail_at == self.appends:
                raise RuntimeError('append failure')
            self.conn.value += params[0]
        elif sql.startswith('SELECT OCTET_LENGTH'):
            self.result = (len(self.conn.value.encode()), hashlib.sha256(self.conn.value.encode()).hexdigest())
            if self.corrupt:
                self.result = (None, None)
        elif sql.startswith('SELECT @@'):
            self.result = (self.packet,)
    def fetchone(self):
        if not self.dictionaries:
            return self.result
        if len(self.result) == 1:
            return {'packet_limit': self.result[0]}
        return dict(zip(('content_bytes', 'content_hash'), self.result))


class ContentStorageTests(unittest.TestCase):
    def test_unicode_escaping_round_trip_and_status_last(self):
        conn = Connection(autocommit=True)
        cur = Cursor(conn, dictionaries=True)
        content = "é🎭'\\\n" * 18000
        db.update_crawl_result_crawled(cur, conn, 45, content)
        self.assertEqual(conn.value, content)
        self.assertEqual((conn.commits, conn.rollbacks, conn.starts), (1, 0, 1))
        self.assertGreater(cur.appends, 1)
        last_sql, last_params = cur.calls[-1]
        self.assertIn('status = %s', last_sql)
        self.assertIn('merged_at = NULL', last_sql)
        self.assertEqual(last_params, ('crawled', db.compute_content_hash(content), 45))
        self.assertNotIn('status =', ''.join(q for q, _ in cur.calls[:-1]))

    def test_midstream_failure_rolls_back_previous_snapshot(self):
        conn = Connection()
        cur = Cursor(conn, fail_at=3)
        with self.assertRaisesRegex(RuntimeError, 'append failure'):
            db.update_crawl_result_crawled(cur, conn, 45, 'x' * 70000)
        self.assertEqual(conn.value, 'previous snapshot')
        self.assertEqual((conn.commits, conn.rollbacks), (0, 1))
        self.assertFalse(any('status =' in q for q, _ in cur.calls))

    def test_server_null_or_truncation_is_not_success(self):
        conn = Connection()
        cur = Cursor(conn, corrupt=True)
        with self.assertRaisesRegex(ValueError, 'verification failed'):
            db.update_crawl_result_crawled(cur, conn, 45, 'x' * 70000)
        self.assertEqual(conn.value, 'previous snapshot')
        self.assertEqual((conn.commits, conn.rollbacks), (0, 1))

    def test_extracted_content_uses_same_atomic_path(self):
        conn = Connection()
        cur = Cursor(conn)
        db.update_crawl_result_extracted(cur, conn, 45, 'x' * 70000)
        self.assertTrue(any('extracted_content = CONCAT' in q for q, _ in cur.calls))
        self.assertEqual(cur.calls[-1][1], ('extracted', 45))
        self.assertEqual(conn.commits, 1)

    def test_small_content_preserves_single_update(self):
        conn = Connection()
        cur = Cursor(conn)
        db.update_crawl_result_crawled(cur, conn, 45, 'small')
        self.assertEqual(len(cur.calls), 1)
        self.assertEqual(cur.calls[0][1], ('crawled', 'small', db.compute_content_hash('small'), 45))
        self.assertEqual(conn.commits, 1)


if __name__ == '__main__':
    unittest.main()
