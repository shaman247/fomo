"""Two websites sharing a NAME must not share a crawl_results row.

`crawl_results` is unique on `(crawl_run_id, filename)` and `filename` is derived
from `websites.name` (`crawler.create_safe_filename`), so before this fix the
second of two same-named websites due in one run hit `ON DUPLICATE KEY UPDATE`
and was handed the FIRST website's row. Its crawled content overwrote the other
site's, stored under the wrong `website_id`, while the losing site got a
`last_crawled_at` stamp with no crawl_result of its own — which suppresses its
scheduling (`get_websites_to_crawl` keys off `last_crawled_at`) and starves its
events of sources.

Observed on 2026-08-17, run 326: w3501 "Caveat" finished at 05:22:17 and stamped
itself; w180 "Caveat" finished at 05:22:42, wrote its content into w3501's
cr-114535 (whose `crawled_at` then read 05:22:42, LATER than w3501's own
last_crawled_at) and left w180 with a last_crawled_at and no row. 28 filename
collisions exist among enabled crawlable websites.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402


class _FakeCursor:
    """An in-memory stand-in for crawl_results with the real unique key."""

    def __init__(self, rows=None):
        self.rows = list(rows or [])  # dicts: id, crawl_run_id, website_id, filename
        self._result = []
        self._next_id = 1 + max((r['id'] for r in (rows or [])), default=0)

    def execute(self, sql, params=()):
        head = ' '.join(sql.split())
        if head.startswith('SELECT id, status FROM crawl_results WHERE crawl_run_id = %s AND website_id'):
            run, wid, filename, logical_filename = params
            hits = [r for r in self.rows if r['crawl_run_id'] == run and r['website_id'] == wid
                    and (r['filename'] == filename or
                         re.sub(db._CRAWL_RETRY_SUFFIX_RE, '', r['filename']) == logical_filename)]
            latest = max(hits, key=lambda r: r['id']) if hits else None
            self._result = [(latest['id'], latest.get('status', 'pending'))] if latest else []
        elif head.startswith('SELECT website_id FROM crawl_results'):
            run, fn = params
            hits = [r for r in self.rows if r['crawl_run_id'] == run and r['filename'] == fn]
            self._result = [(hits[0]['website_id'],)] if hits else []
        elif head.startswith('SELECT id FROM crawl_results WHERE crawl_run_id = %s AND filename'):
            run, fn = params
            hits = [r for r in self.rows if r['crawl_run_id'] == run and r['filename'] == fn]
            self._result = [(hits[0]['id'],)] if hits else []
        elif head.startswith('UPDATE crawl_results SET status'):
            for row in self.rows:
                if row['id'] == params[0]:
                    row['status'] = 'pending'
            self._result = []
        elif head.startswith('INSERT INTO crawl_results'):
            run, wid, fn = params
            existing = [r for r in self.rows
                        if r['crawl_run_id'] == run and r['filename'] == fn]
            if not existing:  # ON DUPLICATE KEY UPDATE status — no new row
                self.rows.append({'id': self._next_id, 'crawl_run_id': run,
                                  'website_id': wid, 'filename': fn, 'status': 'pending'})
                self._next_id += 1
            self._result = []
        else:  # pragma: no cover - guards against a silently unhandled statement
            raise AssertionError(f'unexpected SQL: {head}')

    def fetchone(self):
        return self._result[0] if self._result else None


class _FakeConn:
    def commit(self):
        pass


class CrawlResultNameCollisionTest(unittest.TestCase):

    def test_same_named_websites_get_separate_rows(self):
        cur, conn = _FakeCursor(), _FakeConn()
        first = db.create_crawl_result(cur, conn, 326, 3501, 'caveat.md')
        second = db.create_crawl_result(cur, conn, 326, 180, 'caveat.md')

        self.assertNotEqual(first, second)
        by_id = {r['id']: r for r in cur.rows}
        self.assertEqual(by_id[first]['website_id'], 3501)
        self.assertEqual(by_id[second]['website_id'], 180)
        self.assertEqual(by_id[second]['filename'], 'caveat_w180.md')
        self.assertEqual(db.create_crawl_result(cur, conn, 326, 180, 'caveat.md'), second)

    def test_same_website_recrawled_in_run_reuses_its_row(self):
        cur, conn = _FakeCursor(), _FakeConn()
        first = db.create_crawl_result(cur, conn, 326, 3501, 'caveat.md')
        again = db.create_crawl_result(cur, conn, 326, 3501, 'caveat.md')

        self.assertEqual(first, again)
        self.assertEqual(len(cur.rows), 1)

    def test_row_written_before_the_fix_is_reused_not_duplicated(self):
        # Pre-existing rows keep their plain filename; the (run, website) lookup
        # finds them, so rolling this out mints no parallel rows.
        cur = _FakeCursor([{'id': 114535, 'crawl_run_id': 326,
                            'website_id': 3501, 'filename': 'caveat.md'}])
        self.assertEqual(db.create_crawl_result(cur, _FakeConn(), 326, 3501, 'caveat.md'),
                         114535)
        self.assertEqual(len(cur.rows), 1)

    def test_extensionless_filename_still_disambiguates(self):
        cur, conn = _FakeCursor(), _FakeConn()
        db.create_crawl_result(cur, conn, 1, 10, 'animal')
        db.create_crawl_result(cur, conn, 1, 20, 'animal')
        self.assertEqual({r['filename'] for r in cur.rows}, {'animal', 'animal_w20'})

    def test_completed_snapshots_survive_a_same_day_recrawl(self):
        for status in ('crawled', 'extracted', 'processed'):
            original = dict(id=7, crawl_run_id=326, website_id=3501,
                            filename='caveat.md', status=status,
                            crawled_content='original source', event_count=12)
            cur = _FakeCursor([original.copy()])
            new = db.create_crawl_result(cur, _FakeConn(), 326, 3501, 'caveat.md')
            self.assertNotEqual(new, 7)
            self.assertEqual(cur.rows[0], original)
            self.assertEqual(cur.rows[1]['status'], 'pending')
            cur.rows[1]['status'] = 'failed'
            self.assertEqual(db.create_crawl_result(cur, _FakeConn(), 326, 3501, 'caveat.md'), new)
            self.assertEqual(cur.rows[0], original)

    def test_repeated_completed_attempts_have_distinct_filenames(self):
        cur, conn = _FakeCursor(), _FakeConn()
        for _ in range(3):
            eid = db.create_crawl_result(cur, conn, 326, 3501, 'caveat.md')
            next(r for r in cur.rows if r['id'] == eid)['status'] = 'processed'
        self.assertEqual(len(cur.rows), 3)
        self.assertEqual(len({r['filename'] for r in cur.rows}), 3)

    def test_generated_filename_collision_cannot_reset_another_site(self):
        cur = _FakeCursor([
            dict(id=1, crawl_run_id=1, website_id=1, filename='caveat.md', status='processed'),
            dict(id=2, crawl_run_id=1, website_id=2, filename='caveat_w1_retry1.md', status='processed'),
        ])
        new = db.create_crawl_result(cur, _FakeConn(), 1, 1, 'caveat.md')
        self.assertEqual(new, 3)
        self.assertEqual(cur.rows[1]['status'], 'processed')

    def test_failed_import_is_not_reused_for_another_source_surface(self):
        cur = _FakeCursor([dict(id=1, crawl_run_id=1, website_id=1,
                               filename='picnob_venue_123.md', status='failed')])
        new = db.create_crawl_result(cur, _FakeConn(), 1, 1, 'venue.md')
        self.assertEqual(new, 2)
        self.assertEqual(cur.rows[0]['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
