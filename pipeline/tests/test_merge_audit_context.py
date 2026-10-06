"""The actual merge path forwards one batch ID to inserts and both archival paths."""
from contextlib import ExitStack, redirect_stdout
from datetime import date, timedelta
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger


class MergeAuditContextTests(unittest.TestCase):
    def run_merge(self, crawl_run_id=None):
        today = date(2026, 9, 26)
        cursor = MagicMock(lastrowid=1000)

        def execute(query, params=None):
            rows = []
            if 'SELECT ce.id, ce.name' in query:
                rows = [(1, 'Outdoor Walk', None, 'A guided walk.', '🌳',
                         'Test Venue', None, 10, None, 101, None, None, 100)]
            elif 'FROM crawl_event_occurrences' in query:
                rows = [(1, today, '3pm', None, '4pm', 0)]
            elif 'SELECT DISTINCT cr.website_id' in query:
                rows = [(101,), (202,)]
            cursor.fetchall.return_value = rows
            cursor.fetchone.return_value = None

        cursor.execute.side_effect = execute
        loggers = []

        def logger_factory(*args, **kwargs):
            logger = MagicMock(editor_info=kwargs['editor_info'])
            loggers.append(logger)
            return logger

        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(patch.object(merger, 'EditLogger', side_effect=logger_factory))
            stack.enter_context(patch.object(merger, 'get_active_date_window',
                                            return_value=(today, today + timedelta(days=90))))
            db = stack.enter_context(patch.object(merger, 'db'))
            db.build_tag_ancestor_map.return_value = ({}, set())
            db.archive_outdated_events.return_value = (0, [])
            db.archive_dead_source_events.return_value = (0, [])
            stack.enter_context(patch.object(merger, '_deduplicate_same_name_events', return_value=0))
            self.assertEqual(merger.merge_crawl_events(
                cursor, MagicMock(), crawl_run_id=crawl_run_id, website_ids=[101, 202]), (1, 0))

            self.assertEqual(len(loggers), 4)
            loggers[0].log_insert.assert_called_once()
            for call, logger, website_id in zip(
                    db.archive_outdated_events.call_args_list, loggers[1:3], (101, 202)):
                self.assertIs(call.kwargs['edit_logger'], logger)
                self.assertEqual(call.args[2], website_id)
                self.assertTrue(call.kwargs['temps_built'])
            self.assertEqual(db.archive_outdated_events.call_count, 2)
            self.assertIs(db.archive_dead_source_events.call_args.kwargs['edit_logger'], loggers[3])

        contexts = [json.loads(logger.editor_info) for logger in loggers]
        base = contexts[0]
        self.assertEqual(len(base['merge_id']), 32)
        self.assertEqual(contexts[1], dict(base, archival_reason='missing_from_latest_sources',
                                         trigger_website_id=101))
        self.assertEqual(contexts[2], dict(base, archival_reason='missing_from_latest_sources',
                                         trigger_website_id=202))
        self.assertEqual(contexts[3], dict(base, archival_reason='all_sources_disabled'))
        for logger in loggers:
            self.assertLessEqual(len(logger.editor_info), 500)
        return base

    def test_merge_run_context_reaches_every_archival_path(self):
        self.assertEqual(self.run_merge(crawl_run_id=42)['crawl_run_id'], 42)

    def test_merge_only_calls_have_distinct_batch_ids_without_fake_crawl_run(self):
        first, second = self.run_merge(), self.run_merge()
        self.assertNotIn('crawl_run_id', first)
        self.assertNotEqual(first['merge_id'], second['merge_id'])

    def test_publish_tail_forwards_actual_run_id_and_merge_only_default(self):
        import main
        cursor, connection = MagicMock(), MagicMock()
        for run_id in (42, None):
            with self.subTest(run_id=run_id), patch.object(
                    main.merger, 'merge_crawl_events', side_effect=RuntimeError('stop before export')) as merge:
                with self.assertRaisesRegex(RuntimeError, 'stop before export'):
                    main.run_publish_tail(cursor, connection, [101], MagicMock(), crawl_run_id=run_id)
                merge.assert_called_once_with(cursor, connection, crawl_run_id=run_id, website_ids=[101])


if __name__ == '__main__':
    unittest.main()
