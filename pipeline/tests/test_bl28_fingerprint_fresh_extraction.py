"""websites.fresh_extraction_after invalidates a cached extraction (BL28, 2026-10-12).

Prospect Park w171 cr-130506 missed "Haunted Carousel" (e263259); the 10-09
re-crawl was byte-identical, copied that extraction, and the merge re-archived
the event triage had un-archived. The variance guard only catches LOW counts.
"""
import asyncio
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extractor as ex


class _Cursor:
    """Answers the fingerprint_invalidated query from a fixed verdict."""

    def __init__(self, invalidated):
        self.invalidated = invalidated
        self.queries = []

    def execute(self, sql, params=None):
        self.queries.append((sql, params))

    def fetchone(self):
        return (1,) if self.invalidated else None


class FingerprintInvalidationTests(unittest.TestCase):

    def test_query_compares_the_prior_extraction_to_the_site_timestamp(self):
        cur = _Cursor(True)
        self.assertTrue(ex.fingerprint_invalidated(cur, 130506))
        sql, params = cur.queries[0]
        self.assertEqual(params, (130506,))
        self.assertIn('fresh_extraction_after', sql)
        self.assertIn('COALESCE(cr.extracted_at, cr.crawled_at) < w.fresh_extraction_after', sql)
        self.assertFalse(ex.fingerprint_invalidated(_Cursor(False), 130506))

    def test_mark_sets_the_timestamp(self):
        cur = _Cursor(False)
        ex.mark_fresh_extraction_needed(cur, 171)
        sql, params = cur.queries[0]
        self.assertIn('SET fresh_extraction_after = NOW()', sql)
        self.assertEqual(params, (171,))

    def _prepare(self, invalidated):
        cur = _Cursor(invalidated)
        with mock.patch.object(ex.db, 'get_crawled_content', return_value='x' * 5000), \
             mock.patch.object(ex.db, 'find_prior_crawl_with_same_content', return_value=130506), \
             mock.patch.object(ex, '_fingerprint_copy_is_suspect', return_value=False), \
             mock.patch.object(ex, '_profile_candidate_urls', return_value=[]), \
             mock.patch.object(ex, 'has_event_evidence', return_value=False), \
             mock.patch.object(ex, 'fingerprint_invalidated', return_value=invalidated):
            try:
                return asyncio.run(ex.prepare_extraction(cur, 130578, 'Prospect Park'))
            except Exception as e:  # past the fingerprint step the fake cursor runs out
                return e

    def test_valid_fingerprint_is_copied(self):
        prep = self._prepare(False)
        self.assertEqual(prep.copy_from_crawl_result_id, 130506)

    def test_invalidated_fingerprint_forces_fresh_extraction(self):
        prep = self._prepare(True)
        self.assertNotEqual(getattr(prep, 'copy_from_crawl_result_id', None), 130506)


if __name__ == '__main__':
    unittest.main()
