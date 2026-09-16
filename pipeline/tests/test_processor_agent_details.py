"""Detail extraction pauses durably and never consumes retries while waiting."""

import asyncio
from contextlib import ExitStack, asynccontextmanager, contextmanager
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent_extraction
import extractor
import processor


class TestAgentDetailResume(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.cursor = Mock()
        self.connection = Mock()
        self.candidates = [
            (11, 'First event', 'https://example.com/events/first', 7),
            (12, 'Second event', 'https://example.com/events/second', 7),
        ]
        self.identities = {11: 'identity-first', 12: 'identity-second'}
        self.read_identities = self.stack.enter_context(patch.object(
            processor, '_detail_candidate_identities',
            side_effect=lambda *_: dict(self.identities)))
        self.settings = {7: {'notes': 'Only use the listed showtimes.'}}
        self.stack.enter_context(patch.object(
            processor.db, 'get_website_crawl_settings', return_value=self.settings))
        self.stack.enter_context(patch.object(processor, 'load_tag_context', return_value=()))
        self.stack.enter_context(patch.object(processor, 'build_locations_map', return_value={}))
        self.stack.enter_context(patch.object(processor.crawler, 'build_event_crawl_config'))
        self.stack.enter_context(patch.object(
            processor.crawler, 'get_browser_key', return_value=(True, True, False, False, None)))
        self.browser_config = self.stack.enter_context(patch.object(
            processor.crawler, 'get_browser_config'))

        @asynccontextmanager
        async def fake_browser(config):
            yield object()

        self.stack.enter_context(patch.object(processor, 'managed_crawler', fake_browser))
        self.fetch = self.stack.enter_context(patch.object(
            processor.crawler, 'crawl_event_url', new=AsyncMock(return_value='Full page content')))
        self.extract = self.stack.enter_context(patch.object(
            extractor, 'extract_single_event', new=AsyncMock()))
        self.in_write_lock = False
        self.lock_calls = 0

        @contextmanager
        def fake_lock(connection):
            self.assertIs(connection, self.connection)
            self.lock_calls += 1
            self.in_write_lock = True
            try:
                yield
            finally:
                self.in_write_lock = False

        self.stack.enter_context(patch('dblock.write_lock', fake_lock))

        def fake_apply(*args, **kwargs):
            self.assertTrue(self.in_write_lock)
            return False

        self.apply = self.stack.enter_context(patch.object(
            processor, 'apply_crawled_details', side_effect=fake_apply))

    def run_details(self):
        return asyncio.run(processor.crawl_event_details(
            self.cursor, self.connection, self.candidates,
            extraction_dir=self.directory))

    def pending(self):
        return agent_extraction.AgentExtractionPending(
            'detail-request', Path(self.directory) / 'detail-request.json')

    def test_pending_queues_every_page_and_resume_uses_snapshots_without_browser(self):
        self.extract.side_effect = [self.pending(), self.pending()]
        with self.assertRaises(agent_extraction.AgentExtractionPending):
            self.run_details()

        self.assertEqual(self.fetch.await_count, 2)
        self.assertEqual(self.extract.await_count, 2)
        self.assertEqual(self.lock_calls, 0)
        self.cursor.execute.assert_not_called()
        self.connection.commit.assert_called_once()  # Read snapshot refresh only.
        self.apply.assert_not_called()
        snapshots = list((Path(self.directory) / 'detail_sources').glob('*.json'))
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(json.loads(snapshots[0].read_text())['content'], 'Full page content')

        self.fetch.reset_mock()
        self.browser_config.reset_mock()
        self.extract.reset_mock()
        self.extract.side_effect = None
        self.extract.return_value = {'description': 'A useful description', 'hashtags': []}
        self.connection.commit.reset_mock()

        self.assertEqual(self.run_details(), 2)
        self.fetch.assert_not_awaited()
        self.browser_config.assert_not_called()
        self.assertEqual(self.extract.await_count, 2)
        self.assertEqual(self.apply.call_count, 2)
        self.assertEqual(self.lock_calls, 1)
        self.assertEqual(set(self.cursor.execute.call_args.args[1]), {11, 12})
        self.assertEqual(self.connection.commit.call_count, 3)  # Two read refreshes and one write.

    def test_extraction_failure_is_propagated_without_marking_attempts_done(self):
        self.extract.side_effect = [
            agent_extraction.AgentExtractionInvalid('Invalid agent output'), self.pending()]
        with self.assertRaisesRegex(agent_extraction.AgentExtractionInvalid, 'Invalid agent output'):
            self.run_details()
        self.assertEqual(self.extract.await_count, 2)
        self.cursor.execute.assert_not_called()
        self.connection.commit.assert_called_once()  # Read snapshot refresh only.
        self.apply.assert_not_called()
        self.assertEqual(self.lock_calls, 0)

    def test_cached_response_cannot_overwrite_a_changed_live_event(self):
        self.extract.side_effect = [self.pending(), self.pending()]
        with self.assertRaises(agent_extraction.AgentExtractionPending):
            self.run_details()
        self.identities[11] = 'edited-by-another-session'
        self.extract.reset_mock()
        self.fetch.reset_mock()
        with self.assertRaisesRegex(ValueError, 'changed during agent extraction'):
            self.run_details()
        self.extract.assert_not_awaited()
        self.fetch.assert_not_awaited()
        self.apply.assert_not_called()
        self.assertEqual(self.lock_calls, 0)

    def test_identity_is_rechecked_under_lock_after_refresh_before_any_write(self):
        self.extract.return_value = {'description': 'A useful description', 'hashtags': []}
        read_calls = 0

        def changing_identity(*args):
            nonlocal read_calls
            read_calls += 1
            if read_calls == 2:
                self.assertTrue(self.in_write_lock)
                self.assertEqual(self.connection.commit.call_count, 2)
                return {11: 'changed-after-source-fetch', 12: 'identity-second'}
            return dict(self.identities)

        self.read_identities.side_effect = changing_identity
        with self.assertRaisesRegex(ValueError, 'changed before applying agent responses'):
            self.run_details()
        self.apply.assert_not_called()
        self.cursor.execute.assert_not_called()
        self.assertEqual(self.lock_calls, 1)

    def test_snapshot_identity_changes_with_row_and_extraction_context(self):
        original = processor._detail_source_path(
            self.directory, self.candidates[0], self.settings[7])
        changed_notes = processor._detail_source_path(
            self.directory, self.candidates[0], {'notes': 'Changed instructions'})
        changed_name = processor._detail_source_path(
            self.directory, (11, 'Renamed event', self.candidates[0][2], 7), self.settings[7])
        self.assertNotEqual(original, changed_notes)
        self.assertNotEqual(original, changed_name)


class TestDetailCandidateIdentity(unittest.TestCase):
    def setUp(self):
        self.candidate = (11, 'An event', 'https://example.com/event', 7)
        self.row = self.candidate + (1, 0, 11, 40, 'original description', 'listing-hash')

    def identity(self, row=None, occurrences=None, tags=None):
        cursor = Mock()
        cursor.fetchall.side_effect = [
            [self.row if row is None else row], occurrences or [], tags or []]
        return processor._detail_candidate_identities(cursor, [self.candidate])

    def test_identity_covers_event_source_occurrences_and_tags(self):
        original = self.identity()
        self.assertNotEqual(original, self.identity(row=self.row[:-1] + ('new-listing-hash',)))
        self.assertNotEqual(original, self.identity(occurrences=[(11, 30, '2026-09-20', '7pm')]))
        self.assertNotEqual(original, self.identity(tags=[(11, 50, 'Music')]))

    def test_rejects_missing_renamed_superseded_or_merged_event(self):
        cursor = Mock()
        cursor.fetchall.return_value = []
        with self.assertRaisesRegex(ValueError, 'removed'):
            processor._detail_candidate_identities(cursor, [self.candidate])
        for changes in ({1: 'Renamed'}, {2: 'https://example.com/different'}, {4: 0}, {5: 1}):
            row = list(self.row)
            for index, value in changes.items():
                row[index] = value
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.identity(row=tuple(row))


if __name__ == '__main__':
    unittest.main()
