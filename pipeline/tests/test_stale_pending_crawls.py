"""Step 0 fails crawl_results a dead process left 'pending' (BL10, 2026-10-08).

crawler._mark_crawl_cancelled covers watchdog cancels, but a SIGKILLed or
crashed run runs no exception path and get_incomplete_crawl_results never
retries 'pending', so those rows sat in limbo. Step 0 now fails rows pending
longer than db.STALE_PENDING_CRAWL_HOURS, under the write lock, without touching
a live attempt or a paused agent run's bound rows.
"""
import asyncio
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import db
import main
import test_agent_run


class StalePendingQueryTests(unittest.TestCase):
    def test_find_selects_only_old_pending_rows_and_honours_exclusions(self):
        cursor = Mock()
        cursor.fetchall.return_value = [(5, 7, datetime(2026, 10, 1, 3))]
        rows = db.find_stale_pending_crawl_results(cursor, 6, exclude_ids=[11, 9, 11])
        self.assertEqual(rows, [(5, 7, datetime(2026, 10, 1, 3))])
        query, params = cursor.execute.call_args.args
        self.assertIn("status = 'pending'", query)
        self.assertIn('created_at < NOW() - INTERVAL %s HOUR', query)
        self.assertIn('id NOT IN (%s,%s)', query)
        self.assertEqual(params, [6, 9, 11])

    def test_find_without_exclusions(self):
        cursor = Mock()
        cursor.fetchall.return_value = []
        self.assertEqual(db.find_stale_pending_crawl_results(cursor), [])
        query, params = cursor.execute.call_args.args
        self.assertNotIn('NOT IN', query)
        self.assertEqual(params, [db.STALE_PENDING_CRAWL_HOURS])

    def test_fail_rechecks_status_and_age_and_commits(self):
        cursor, conn = Mock(rowcount=2), Mock()
        self.assertEqual(db.fail_stale_pending_crawl_results(cursor, conn, [8, 3, 8], 6), 2)
        query, params = cursor.execute.call_args.args
        self.assertIn("SET status = 'failed', error_message = %s", query)
        self.assertIn("AND status = 'pending'", query)
        self.assertIn('created_at < NOW() - INTERVAL %s HOUR', query)
        self.assertEqual(params[1:], [3, 8, 6])
        self.assertIn('still pending after 6h', params[0])
        conn.commit.assert_called_once()

    def test_fail_with_no_ids_writes_nothing(self):
        cursor, conn = Mock(), Mock()
        self.assertEqual(db.fail_stale_pending_crawl_results(cursor, conn, []), 0)
        cursor.execute.assert_not_called()
        conn.commit.assert_not_called()

    def test_reused_attempt_restarts_its_age(self):
        """A same-day retry of an old failed row must not look abandoned mid-fetch."""
        cursor, conn = Mock(), Mock()
        cursor.fetchone.return_value = (42, 'failed')
        self.assertEqual(db.create_crawl_result(cursor, conn, 3, 7, 'venue.md'), 42)
        update = cursor.execute.call_args_list[-1].args[0]
        self.assertIn("status = 'pending', created_at = NOW()", update)


class ReconcileTests(unittest.TestCase):
    def run_reconcile(self, stale, changed=None, lock=None, **kwargs):
        lock = lock or MagicMock(side_effect=lambda *a, **k: nullcontext())
        with patch.object(main.db, 'find_stale_pending_crawl_results', return_value=stale) as find, \
             patch.object(main.db, 'fail_stale_pending_crawl_results',
                          return_value=len(stale) if changed is None else changed) as fail, \
             patch.object(main.dblock, 'write_lock', lock):
            count = main.reconcile_stale_pending_crawls(Mock(), Mock(), **kwargs)
        return count, find, fail, lock

    def test_nothing_stale_takes_no_lock(self):
        count, _, fail, lock = self.run_reconcile([])
        self.assertEqual(count, 0)
        lock.assert_not_called()
        fail.assert_not_called()

    def test_stale_rows_failed_under_the_lock(self):
        stale = [(101, 7, None), (102, None, None)]
        count, find, fail, lock = self.run_reconcile(stale, exclude_ids=[5])
        self.assertEqual(count, 2)
        lock.assert_called_once()
        self.assertEqual(fail.call_args.args[2], [101, 102])
        self.assertEqual(find.call_args.args[1:], (db.STALE_PENDING_CRAWL_HOURS, [5]))

    def test_lock_timeout_never_aborts_the_run(self):
        lock = MagicMock(side_effect=TimeoutError('held by another session'))
        count, _, fail, _ = self.run_reconcile([(101, 7, None)], lock=lock)
        self.assertEqual(count, 0)
        fail.assert_not_called()


class StepZeroWiringTests(unittest.TestCase):
    """Step 0 runs the reconciliation; a resume excludes its own bound rows."""
    setUp = test_agent_run.AgentRunTests.setUp
    mocked_run = test_agent_run.AgentRunTests.mocked_run

    def test_resume_excludes_bound_rows_and_still_completes_its_work(self):
        _, extract, *_ = self.mocked_run()
        with patch.object(main, 'reconcile_stale_pending_crawls', return_value=0) as rec:
            asyncio.run(main._run_pipeline(work_dir=self.root, resume=True))
        self.assertEqual(rec.call_args.kwargs['exclude_ids'], [11])
        extract.assert_called()  # the paused run's crawled row is still extracted

    def test_fresh_run_reconciles_before_finding_incomplete_results(self):
        order = []
        _, _, _, due, incomplete, *_ = self.mocked_run()
        due.return_value = []
        incomplete.side_effect = lambda *a, **k: order.append('incomplete') or []
        with patch.object(main, 'reconcile_stale_pending_crawls',
                          side_effect=lambda *a, **k: order.append('reconcile') or 0) as rec:
            asyncio.run(main._run_pipeline(work_dir=self.root / 'fresh'))
        self.assertEqual(rec.call_args.kwargs['exclude_ids'], ())
        self.assertEqual(order, ['reconcile', 'incomplete'])


if __name__ == '__main__':
    unittest.main()
