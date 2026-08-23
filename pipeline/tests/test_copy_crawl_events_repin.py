"""Tests for the location re-pin applied when a fingerprint copy reuses an
older extraction.

A content fingerprint says the PAGE is unchanged. It says nothing about the
`locations` table, which changes constantly. `db.copy_crawl_events` used to copy
`location_id` verbatim, so a pin resolved the first time the content was seen was
frozen for as long as the page stayed byte-stable — NYC-DSA events carried a
correct `location_name` of "BAM" pinned to the DSA office row, and Industry
City's sub-venues stayed on the campus row long after they had their own.

The asymmetry is the whole design and is measured in `copy_crawl_events`'s
docstring: a resolver hit re-pins, a resolver MISS keeps the stored id. Over the
118,892 crawl_events feeding live events on 2026-08-23, re-resolving
unconditionally would have unpinned 1,437 rows whose names today's map cannot
resolve, dropping those events out of the export.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db


class _FakeCursor:
    """Minimal cursor: replays canned SELECT rows, records INSERT params."""

    def __init__(self, src_rows):
        self._src_rows = src_rows
        self.inserted = []
        self.rowcount = 0
        self._last = None

    def execute(self, sql, params=None):
        s = ' '.join(sql.split())
        if s.startswith('SELECT') and 'FROM crawl_events' in s:
            self._last = list(self._src_rows)
        elif s.startswith('INSERT INTO crawl_events'):
            self.inserted.append(params)
            self._last = []
        else:
            self._last = []
        return None

    def fetchall(self):
        return self._last or []

    def fetchone(self):
        rows = self._last or []
        return rows[0] if rows else None

    @property
    def lastrowid(self):
        return 1000 + len(self.inserted)


class _FakeConn:
    def commit(self):
        pass


# Column order matches the SELECT in copy_crawl_events.
def _row(src_id, name, location_name, location_id):
    return (src_id, name, None, 'desc', '🎭', location_name, None,
            location_id, 'https://x.com/e/1', '{}', 'hash')


# Index of location_id in the INSERT params tuple:
# (dst_crawl_result_id, name, short_name, description, emoji,
#  location_name, sublocation, location_id, url, raw_data, content_hash)
_LOC_ID = 7
_LOC_NAME = 5


class TestCopyCrawlEventsRepin(unittest.TestCase):

    def _copy(self, rows, resolver):
        cur = _FakeCursor(rows)
        db.copy_crawl_events(cur, _FakeConn(), 1, 2, resolve_location=resolver)
        return cur.inserted

    def test_resolver_hit_repins_the_copied_row(self):
        """The NYC-DSA shape: correct name, stale pin."""
        inserted = self._copy(
            [_row(1, 'Cinema with Comrades', 'BAM', 1940)],
            lambda ln, sl, n: 135,
        )
        self.assertEqual(len(inserted), 1)
        self.assertEqual(inserted[0][_LOC_ID], 135)
        self.assertEqual(inserted[0][_LOC_NAME], 'BAM')

    def test_resolver_miss_keeps_the_stored_pin(self):
        """A NULL must never unpin — that is what would drop the event."""
        inserted = self._copy(
            [_row(1, 'Some Event', 'A Venue We Cannot Resolve', 4321)],
            lambda ln, sl, n: None,
        )
        self.assertEqual(inserted[0][_LOC_ID], 4321)

    def test_resolver_can_pin_a_previously_unpinned_row(self):
        inserted = self._copy(
            [_row(1, 'Some Event', 'Newly Added Venue', None)],
            lambda ln, sl, n: 777,
        )
        self.assertEqual(inserted[0][_LOC_ID], 777)

    def test_no_resolver_preserves_the_legacy_behaviour(self):
        inserted = self._copy([_row(1, 'Some Event', 'BAM', 1940)], None)
        self.assertEqual(inserted[0][_LOC_ID], 1940)

    def test_rows_without_a_location_name_are_left_alone(self):
        """Nothing to resolve from, so the resolver must not even be consulted."""
        calls = []

        def resolver(ln, sl, n):
            calls.append(ln)
            return 999

        inserted = self._copy([_row(1, 'Some Event', None, 55)], resolver)
        self.assertEqual(calls, [])
        self.assertEqual(inserted[0][_LOC_ID], 55)

    def test_a_throwing_resolver_cannot_lose_the_extraction(self):
        """A repin bug must degrade to the old behaviour, not drop events."""
        def boom(ln, sl, n):
            raise RuntimeError('resolver exploded')

        inserted = self._copy([_row(1, 'Some Event', 'BAM', 1940)], boom)
        self.assertEqual(len(inserted), 1)
        self.assertEqual(inserted[0][_LOC_ID], 1940)

    def test_each_row_is_resolved_independently(self):
        inserted = self._copy(
            [_row(1, 'A', 'BAM', 1940), _row(2, 'B', 'Unresolvable', 1940)],
            lambda ln, sl, n: 135 if ln == 'BAM' else None,
        )
        self.assertEqual([p[_LOC_ID] for p in inserted], [135, 1940])


if __name__ == '__main__':
    unittest.main()
