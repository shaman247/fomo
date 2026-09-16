"""Agent handoff must stop before processing/publication and resume exact saved work."""
import asyncio
from contextlib import ExitStack, nullcontext
from datetime import date
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_run
import agent_extraction
import main


class AgentRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original_queue = agent_extraction.work_dir()
        self.addCleanup(agent_extraction.configure, self.original_queue)
        self.result = dict(crawl_result_id=11, website_id=7, crawl_run_id=3,
                           name='Venue', notes='', run_date=date(2026, 9, 15),
                           status='crawled', source_hash='abc', use_vision=True)
        self.state = dict(version=1, city=os.environ.get('FOMO_CITY', 'nyc'),
                          phase='listing', reference_date='2026-09-15',
                          website_ids=[7], crawl_run_id=3, crawl_result_ids=[11],
                          source_hashes={'11': 'abc'})
        agent_run.save(self.root, self.state)

    def mocked_run(self, extraction=None, rows=None, details=None):
        stack = ExitStack()
        self.addCleanup(stack.close)
        conn = Mock()
        stack.enter_context(patch.object(main.db, 'create_connection', return_value=conn))
        stack.enter_context(patch.object(main.db, 'get_stranded_merge_summary', return_value=[]))
        read = stack.enter_context(patch.object(agent_run, 'read_results', side_effect=rows))
        if rows is None:
            read.side_effect = None
            read.return_value = [self.result]
        stack.enter_context(patch.object(main.dblock, 'write_lock', side_effect=lambda *a, **k: nullcontext()))
        extract = stack.enter_context(patch.object(main.extractor, 'extract_events', new=extraction or AsyncMock(return_value=True)))
        process = stack.enter_context(patch.object(main.processor, 'process_events', return_value=1))
        for name in ('build_locations_map', 'build_websites_map', 'load_tag_context'):
            stack.enter_context(patch.object(main.processor, name, return_value={}))
        due = stack.enter_context(patch.object(main.db, 'get_websites_due_for_crawling'))
        incomplete = stack.enter_context(patch.object(main.db, 'get_incomplete_crawl_results'))
        stack.enter_context(patch.object(main.db, 'get_detail_crawl_candidates', return_value=[(80, 'Event', 'https://example.test/e', 7)]))
        detail = stack.enter_context(patch.object(main.processor, 'crawl_event_details', new=details or AsyncMock(return_value=1)))
        stack.enter_context(patch.object(main, 'acquire_publish_lock', return_value=True))
        publish = stack.enter_context(patch.object(main, 'run_publish_tail', return_value=True))
        stack.enter_context(patch.object(main.frequency_analyzer, 'analyze_frequencies', return_value={'adjusted': 0}))
        complete = stack.enter_context(patch.object(main.db, 'complete_crawl_run'))
        return conn, extract, process, due, incomplete, detail, publish, complete

    def run_resume(self):
        return asyncio.run(main._run_pipeline(work_dir=self.root, resume=True))

    def test_pending_listing_never_processes_or_publishes(self):
        pending = agent_extraction.AgentExtractionPending('job', self.root / 'request.json')
        conn, extract, process, due, incomplete, detail, publish, complete = self.mocked_run(
            extraction=AsyncMock(side_effect=pending))
        self.assertIsNone(self.run_resume())
        extract.assert_awaited_once()
        self.assertTrue(extract.await_args.kwargs['use_vision'])
        for unused in (process, due, incomplete, detail, publish, complete):
            unused.assert_not_called()
        conn.rollback.assert_called()

    def test_new_run_saves_scope_before_requesting_agent_work(self):
        fresh_dir = self.root / 'new-run'
        pending = agent_extraction.AgentExtractionPending('job', fresh_dir / 'request.json')
        _, _, process, due, incomplete, _, publish, complete = self.mocked_run(
            extraction=AsyncMock(side_effect=pending))
        due.return_value = []
        incomplete.return_value = [self.result]
        with patch.object(main.db, 'get_or_create_crawl_run', return_value=3):
            result = asyncio.run(main._run_pipeline(work_dir=fresh_dir))
        self.assertIsNone(result)
        saved = agent_run.load(fresh_dir)
        self.assertEqual(saved['crawl_result_ids'], [11])
        self.assertEqual(saved['website_ids'], [7])
        self.assertEqual(saved['source_hashes'], {'11': 'abc'})
        process.assert_not_called()
        publish.assert_not_called()
        complete.assert_not_called()

    def test_empty_saved_scope_cannot_turn_into_global_publish(self):
        self.state.update(crawl_result_ids=[], source_hashes={}, website_ids=[])
        agent_run.save(self.root, self.state)
        _, extract, _, _, _, detail, publish, _ = self.mocked_run(rows=[[]])
        self.assertTrue(self.run_resume())
        extract.assert_not_called()
        detail.assert_not_called()
        publish.assert_not_called()

    def test_obsolete_failed_retry_is_retired_after_snapshot_validation(self):
        failed = dict(self.result, original_status='failed',
                      retry_exclusion_reason='content_too_small')
        _, extract, process, _, _, detail, publish, _ = self.mocked_run(rows=[[failed]])
        self.assertTrue(self.run_resume())
        extract.assert_not_called()
        process.assert_not_called()
        detail.assert_not_called()
        publish.assert_not_called()
        saved = agent_run.load(self.root)
        self.assertEqual(saved['crawl_result_ids'], [])
        self.assertEqual(saved['retired_retries'][0]['crawl_result_id'], 11)
        self.assertEqual(saved['retired_retries'][0]['retry_exclusion_reason'], 'content_too_small')

    def test_changed_failed_retry_cannot_evade_source_validation(self):
        failed = dict(self.result, source_hash='changed',
                      retry_exclusion_reason='content_too_small')
        _, extract, _, _, _, _, publish, _ = self.mocked_run(rows=[[failed]])
        self.assertFalse(self.run_resume())
        self.assertNotIn('retired_retries', agent_run.load(self.root))
        extract.assert_not_called()
        publish.assert_not_called()

    def test_invalid_response_fails_before_processing(self):
        _, _, process, _, _, detail, publish, _ = self.mocked_run(
            extraction=AsyncMock(side_effect=agent_extraction.AgentExtractionInvalid('incomplete')))
        self.assertFalse(self.run_resume())
        process.assert_not_called()
        detail.assert_not_called()
        publish.assert_not_called()

    def test_changed_source_rejected_before_extraction(self):
        changed = dict(self.result, source_hash='new content')
        _, extract, process, _, _, _, publish, _ = self.mocked_run(rows=[[changed]])
        self.assertFalse(self.run_resume())
        extract.assert_not_called()
        process.assert_not_called()
        publish.assert_not_called()

    def test_ready_resume_processes_exact_id_and_completes(self):
        processed = dict(self.result, status='processed')
        _, extract, process, due, incomplete, detail, publish, complete = self.mocked_run(
            rows=[[self.result], [self.result], [self.result], [processed], [processed]])
        self.assertTrue(self.run_resume())
        self.assertEqual(process.call_args.args[2:5], (11, 'Venue', '20260915'))
        due.assert_not_called()
        incomplete.assert_not_called()
        detail.assert_awaited_once()
        self.assertEqual(publish.call_args.args[2], [7])
        complete.assert_called_once()
        self.assertEqual(agent_run.load(self.root)['phase'], 'complete')
        self.assertTrue(self.run_resume())
        publish.assert_called_once()

    def test_pending_detail_does_not_publish_or_complete(self):
        processed = dict(self.result, status='processed')
        pending = agent_extraction.AgentExtractionPending('detail', self.root / 'request.json')
        _, _, process, _, _, detail, publish, complete = self.mocked_run(
            rows=[[processed], [processed], [processed]],
            details=AsyncMock(side_effect=pending))
        self.assertIsNone(self.run_resume())
        process.assert_not_called()
        publish.assert_not_called()
        complete.assert_not_called()
        self.assertIn('detail_candidates', agent_run.load(self.root))

    def test_publish_retry_does_not_reapply_details(self):
        self.state.update(phase='publishing', details_complete=True,
                          detail_candidates=[[80, 'Event', 'https://example.test/e', 7]])
        agent_run.save(self.root, self.state)
        processed = dict(self.result, status='processed')
        _, _, process, _, _, detail, publish, _ = self.mocked_run(
            rows=[[processed], [processed], [processed], [processed]])
        self.assertTrue(self.run_resume())
        detail.assert_not_called()
        process.assert_not_called()
        publish.assert_called_once()

    def test_processed_status_required_before_detail_or_publish(self):
        _, _, _, _, _, detail, publish, _ = self.mocked_run(
            rows=[[self.result], [self.result], [self.result], [self.result]])
        self.assertFalse(self.run_resume())
        detail.assert_not_called()
        publish.assert_not_called()

    def test_city_and_interrupted_crawl_validation(self):
        with patch.dict(os.environ, {'FOMO_CITY': 'different-city'}):
            with self.assertRaisesRegex(ValueError, 'FOMO_CITY'):
                agent_run.load(self.root)
        self.state['phase'] = 'crawling'
        agent_run.save(self.root, self.state)
        with self.assertRaisesRegex(ValueError, 'interrupted'):
            agent_run.load(self.root)

    def test_exact_rows_missing_or_source_mutated(self):
        cursor = Mock()
        cursor.fetchall.return_value = []
        with self.assertRaisesRegex(ValueError, 'removed'):
            agent_run.read_results(cursor, [11])
        cursor.fetchall.return_value = [(11, 'failed', 7, 3, 'Venue', '', date(2026, 9, 15), 'source', 1, None, 0, None, 6, 0)]
        rows = agent_run.read_results(cursor, [11])
        self.assertEqual(rows[0]['status'], 'crawled')
        cursor.fetchall.return_value[0] = (11, 'failed', 7, 3, 'Venue', 'changed notes', date(2026, 9, 15), 'source', 1, None, 0, None, 6, 0)
        changed = agent_run.read_results(cursor, [11])
        self.assertNotEqual(rows[0]['source_hash'], changed[0]['source_hash'])
        with self.assertRaisesRegex(ValueError, 'changed'):
            agent_run.verify_sources(self.state, rows)

    def test_singleton_rejects_overlapping_processes(self):
        with patch.object(agent_run, 'ROOT', self.root):
            with agent_run.singleton():
                with self.assertRaisesRegex(RuntimeError, 'Another pipeline'):
                    with agent_run.singleton():
                        pass
            with agent_run.singleton():
                pass


if __name__ == '__main__':
    unittest.main()
