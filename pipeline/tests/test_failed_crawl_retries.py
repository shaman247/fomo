"""Failed retry admission must not strand tiny crawls or stale source surfaces."""

from datetime import date
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent_run
import db
import extractor


class FailedRetryTests(unittest.TestCase):
    def incomplete_row(self, crid, status, chars, superseded=False):
        return (crid, status, 7, 3, 'Venue', '', date(2026, 9, 16),
                'crawled' if status == 'failed' else status, None, chars, int(superseded))

    def saved_row(self, crid=11, status='failed', content='x' * 700, superseded=False):
        return (crid, status, 7, 3, 'Venue', '', date(2026, 9, 16),
                content, 0, None, 0, None, len(content), int(superseded))

    def test_threshold_matches_extraction_guard(self):
        self.assertEqual(db.MIN_FAILED_RETRY_CONTENT_CHARS, extractor.MIN_CONTENT_SIZE)

    def test_only_inadmissible_failed_rows_are_excluded_from_new_run(self):
        cursor = Mock()
        cursor.fetchall.return_value = [
            self.incomplete_row(96639, 'failed', 126, True),
            self.incomplete_row(122328, 'failed', 284),
            self.incomplete_row(21, 'failed', 499),
            self.incomplete_row(22, 'failed', 500),
            self.incomplete_row(23, 'failed', 1000, True),
            self.incomplete_row(24, 'crawled', 126, True),
            self.incomplete_row(25, 'extracted', 284, True),
        ]
        results = db.get_incomplete_crawl_results(cursor, website_ids=[7])
        self.assertEqual([r['crawl_result_id'] for r in results], [22, 24, 25])
        self.assertEqual(results[0]['original_status'], 'failed')
        self.assertEqual(results[0]['content_chars'], 500)
        self.assertFalse(results[0]['superseded_by_success'])
        query, params = cursor.execute.call_args.args
        self.assertIn('newer.filename = cr.filename', query)
        self.assertIn('newer.website_id = cr.website_id', query)
        self.assertIn("newer.status IN ('extracted', 'processed')", query)
        self.assertIn('newer.crawled_at > cr.crawled_at', query)
        self.assertEqual(params, [7])

    def test_saved_legacy_failures_remain_visible_for_verified_retirement(self):
        cursor = Mock()
        cursor.fetchall.return_value = [
            self.saved_row(96639, content='x' * 126, superseded=True),
            self.saved_row(122328, content='x' * 284),
            self.saved_row(30, content='x' * 1000, superseded=True),
            self.saved_row(31, status='crawled', content='x' * 126),
        ]
        results = agent_run.read_results(cursor, [96639, 122328, 30, 31])
        self.assertEqual([r['retry_exclusion_reason'] for r in results], [
            'content_too_small', 'content_too_small', 'superseded_by_success', None])
        self.assertEqual(results[0]['original_status'], 'failed')
        self.assertEqual(results[0]['content_chars'], 126)
        self.assertTrue(results[0]['superseded_by_success'])
        self.assertEqual(results[-1]['original_status'], 'crawled')
        self.assertEqual(len(results), 4)  # Main verifies every source before retirement.

    def test_supersession_metadata_does_not_change_saved_source_hash(self):
        cursor = Mock()
        cursor.fetchall.return_value = [self.saved_row()]
        before = agent_run.read_results(cursor, [11])
        cursor.fetchall.return_value = [self.saved_row(superseded=True)]
        after = agent_run.read_results(cursor, [11])
        self.assertIsNone(before[0]['retry_exclusion_reason'])
        self.assertEqual(after[0]['retry_exclusion_reason'], 'superseded_by_success')
        self.assertEqual(before[0]['source_hash'], after[0]['source_hash'])
        agent_run.verify_sources({'source_hashes': {'11': before[0]['source_hash']}}, after)


if __name__ == '__main__':
    unittest.main()
