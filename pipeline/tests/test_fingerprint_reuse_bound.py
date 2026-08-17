"""Tests for the bounded content-fingerprint reuse.

A byte-stable page used to be extracted exactly ONCE, ever: every later crawl
matched its `content_hash` and copied that first extraction verbatim. Fine for the
page's content, wrong for the DATE WINDOW, which slides — an event beyond
FUTURE_WINDOW_DAYS when the hash was first cached was rejected as
`start_too_future` then, and never re-offered. Observed on w2813 Crown Hill, whose
November and December shows were on the page all along and never published.

The fix has two halves that ONLY work together:
  1. reuse must chain to a crawl that was really extracted, never to another copy;
  2. that extraction must be newer than FINGERPRINT_MAX_REUSE_DAYS.

Half 2 alone is useless — every crawl writes a fresh row with the same
content_hash, so the newest twin is always young and the chain refreshes itself
forever. These tests pin down both halves, and the cross-file marker agreement
that half 1 depends on.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import constants
import db
import extractor


class _CapturingCursor:
    """Records the SQL and params of the single execute() it receives."""

    def __init__(self, row=None):
        self.sql = None
        self.params = None
        self._row = row

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return self._row


class FingerprintQueryShapeTests(unittest.TestCase):
    """The guards must actually be in the query that runs."""

    def _run(self, row=None):
        cur = _CapturingCursor(row)
        result = db.find_prior_crawl_with_same_content(cur, 12345)
        return cur, result

    def test_query_bounds_reuse_by_age(self):
        cur, _ = self._run()
        self.assertIn("INTERVAL", cur.sql)
        self.assertIn("crawled_at", cur.sql)
        self.assertIn(constants.FINGERPRINT_MAX_REUSE_DAYS, cur.params)

    def test_query_refuses_to_chain_onto_a_copy(self):
        cur, _ = self._run()
        self.assertIn("NOT LIKE", cur.sql)
        self.assertIn("extracted_content", cur.sql)
        self.assertIn(f'%{constants.FINGERPRINT_COPY_MARKER}%', cur.params)

    def test_still_scoped_to_the_same_website_and_hash(self):
        """The guards must not have loosened the original matching conditions."""
        cur, _ = self._run()
        self.assertIn("cr_prior.website_id = cr_curr.website_id", cur.sql)
        self.assertIn("cr_prior.content_hash = cr_curr.content_hash", cur.sql)
        self.assertIn("cr_prior.id < cr_curr.id", cur.sql)

    def test_returns_the_prior_id_when_one_qualifies(self):
        _, result = self._run(row={"id": 999})
        self.assertEqual(result, 999)

    def test_returns_none_when_nothing_qualifies(self):
        _, result = self._run(row=None)
        self.assertIsNone(result)


class CopyMarkerAgreementTests(unittest.TestCase):
    """extractor writes the marker; db.py matches on it. They must agree.

    These live in different files, so a reword in one silently disables the
    copy-skipping guard in the other — and the symptom would be the ORIGINAL bug
    (a frozen page never re-read), which is invisible without this test.
    """

    def test_written_marker_matches_the_pattern_db_searches_for(self):
        captured = {}

        def fake_extracted(cursor, connection, crawl_result_id, content):
            captured['marker'] = content

        prep = mock.Mock()
        prep.copy_from_crawl_result_id = 4242
        prep.crawl_result_id = 1

        with mock.patch.object(extractor.db, 'update_crawl_result_extracted',
                               side_effect=fake_extracted), \
             mock.patch.object(extractor.db, 'update_crawl_result_processed'):
            extractor._apply_fingerprint_marker_and_status(None, None, prep, 7)

        marker = captured['marker']
        # The db-side guard is `NOT LIKE '%<MARKER>%'`, so containment is exactly
        # the property that must hold.
        self.assertIn(constants.FINGERPRINT_COPY_MARKER, marker)
        self.assertIn('4242', marker)

    def test_a_real_extraction_does_not_look_like_a_copy(self):
        """A genuine extraction payload must not accidentally match the guard."""
        real = '{"events": [{"name": "Some Show", "occurrences": []}]}'
        self.assertNotIn(constants.FINGERPRINT_COPY_MARKER, real)


if __name__ == "__main__":
    unittest.main()
