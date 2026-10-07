"""Untimed listing spans get their own page fetched, and its sessions replace them.

Found 2026-10-07 by the Gothamist October music cross-reference: Park Avenue
Armory (w224) 196536 "Music for 18 Musicians: Staged Variations" was one
untimed 10/14–10/18 occurrence while its own page lists Wed–Sat 7pm and Sun
3pm. Six crawl_events all had detail_crawl_attempts = 0: a row with dates, a
description and a real venue was never a detail candidate, and the
known-complete URL skip reinforced it. Missing clocks were never considered.

Two halves:
- db.get_detail_crawl_candidates selects a single untimed 2–14-day run of a
  session format (schedule_envelopes.SESSION_TYPES), overriding the
  known-complete skip (SQLite shim, real query text).
- schedule_envelopes.refined_envelopes lets that page's timed sessions replace
  the publisher's own listing range on the canonical event, which the
  cross-publisher rule deliberately refuses.
"""

import os
import sqlite3
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db as pipeline_db
from schedule_envelopes import refined_envelopes
from tests.test_archival import _ShimCursor
from tests.test_detail_crawl_candidates import SCHEMA, FRESH_AT, RECRAWL_AT, STALE_AT

URL = 'https://www.armoryonpark.org/season-events/2026-season/music-for-18-musicians-staged-variations/'
NAME = 'Music for 18 Musicians: Staged Variations'
SPAN = ('2026-10-14', '', '2026-10-18', '')
SESSIONS = [('2026-10-14', '7pm', None, ''), ('2026-10-15', '7pm', None, ''),
            ('2026-10-16', '7pm', None, ''), ('2026-10-17', '7pm', None, ''),
            ('2026-10-18', '3pm', None, '')]


class TestUntimedSpanCandidates(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.executescript(SCHEMA)
        self.conn.execute("INSERT INTO websites (id, name, skip_reenrichment) VALUES (224,'Park Avenue Armory',0)")
        self.conn.execute('INSERT INTO crawl_results (id, website_id, crawled_at) VALUES (1, 224, ?)',
                          (RECRAWL_AT,))
        self.conn.commit()
        self.cur = _ShimCursor(self.conn)
        self._old_cap = os.environ.get('DETAIL_CRAWL_SITE_CAP')

    def tearDown(self):
        if self._old_cap is None:
            os.environ.pop('DETAIL_CRAWL_SITE_CAP', None)
        else:
            os.environ['DETAIL_CRAWL_SITE_CAP'] = self._old_cap

    def _add(self, ce_id, url=URL, rows=(SPAN,), name=NAME, attempts=0, created_at=FRESH_AT):
        # A fully described row at its real venue: nothing but the clocks is missing.
        self.conn.execute(
            "INSERT INTO crawl_events (id, crawl_result_id, name, url, location_name, location_id,"
            " description, detail_crawl_attempts, created_at)"
            " VALUES (?, 1, ?, ?, 'Park Avenue Armory', 645, 'Alan Pierson stages Steve Reich.', ?, ?)",
            (ce_id, name, url, attempts, created_at))
        for row in rows:
            self.conn.execute(
                'INSERT INTO crawl_event_occurrences (crawl_event_id, start_date, start_time, end_date, end_time)'
                ' VALUES (?,?,?,?,?)', (ce_id, *row))
        self.conn.commit()

    def _event(self, event_id=196536, url=URL, event_type='Concert', rows=(SPAN,), name=NAME):
        self.conn.execute(
            'INSERT INTO events (id, name, location_id, description, event_type) VALUES (?,?,645,?,?)',
            (event_id, name, 'Alan Pierson stages Steve Reich.', event_type))
        self.conn.execute('INSERT INTO event_urls (event_id, url) VALUES (?,?)', (event_id, url))
        for row in rows:
            self.conn.execute(
                'INSERT INTO event_occurrences (event_id, start_date, start_time, end_date, end_time)'
                ' VALUES (?,?,?,?,?)', (event_id, *row))
        self.conn.commit()

    def _ids(self, **kwargs):
        return {row[0] for row in pipeline_db.get_detail_crawl_candidates(self.cur, **kwargs)}

    def test_armory_span_overrides_the_known_complete_skip(self):
        self._add(1)
        self._event()
        skipped = []
        self.assertEqual(self._ids(known_complete_skips=skipped), {1})
        self.assertEqual(skipped, [])

    def test_timed_listing_keeps_the_known_complete_skip(self):
        self._add(1, rows=SESSIONS)
        self._event(rows=SESSIONS)
        self.assertEqual(self._ids(), set())

    def test_non_session_formats_and_unclassified_events_keep_their_runs(self):
        for event_type in ('Exhibition', 'Festival', 'Camp', None):
            with self.subTest(event_type=event_type):
                self.setUp()
                self._add(1)
                self._event(event_type=event_type)
                self.assertEqual(self._ids(), set())

    def test_no_canonical_event_yet_waits_for_a_type(self):
        self._add(1)
        self.assertEqual(self._ids(), set())

    def test_every_visible_event_on_the_url_must_be_a_session_format(self):
        self._add(1)
        self._event()
        self._event(event_id=2, event_type='Exhibition')
        self.assertEqual(self._ids(), set())

    def test_span_width_bounds(self):
        cases = {
            ('2026-10-14', '', '2026-10-15', ''): True,    # 2 calendar days
            ('2026-10-14', '', '2026-10-27', ''): True,    # 14
            ('2026-10-14', '', '2026-10-28', ''): False,   # 15: a run, not sessions
            ('2026-10-14', '', None, ''): False,           # single untimed day
            ('2026-10-14', '7pm', '2026-10-18', ''): False,  # already carries a clock
        }
        for row, expected in cases.items():
            with self.subTest(row=row):
                self.setUp()
                self._add(1, rows=(row,))
                self._event(rows=(row,))
                self.assertEqual(self._ids(), {1} if expected else set())

    def test_multi_row_schedule_is_not_fetched_for_clocks(self):
        # apply_crawled_details only replaces a schedule of at most one row.
        self._add(1, rows=(SPAN, ('2026-10-25', '', None, '')))
        self._event()
        self.assertEqual(self._ids(), set())

    def test_already_refined_canonical_is_not_refetched(self):
        # The merger drops the repeated listing range against the page's sessions.
        self._add(1)
        self._event(rows=SESSIONS)
        skipped = []
        self.assertEqual(self._ids(known_complete_skips=skipped), set())
        self.assertEqual(skipped, [1])

    def test_sessions_from_another_publisher_beside_the_range_still_fetch(self):
        # 196536 on 2026-10-07: MSM w1036 added the five sessions, the range stayed.
        self._add(1)
        self._event(rows=(SPAN,) + tuple(SESSIONS))
        self.assertEqual(self._ids(), {1})

    def test_page_already_fetched_for_the_same_range_is_not_refetched(self):
        self._add(1, attempts=1, created_at=STALE_AT)  # previous run, fetched, no sessions
        self._add(2)
        self._event()
        self.assertEqual(self._ids(), set())

    def test_a_changed_range_is_fetched_again(self):
        self._add(1, attempts=1, created_at=STALE_AT)
        self._add(2, rows=(('2026-10-14', '', '2026-10-19', ''),))
        self._event()
        self.assertEqual(self._ids(), {2})

    def test_own_retry_is_not_blocked_by_its_first_attempt(self):
        self._add(1, attempts=1)
        self._event()
        self.assertEqual(self._ids(), {1})

    def test_site_cap_still_applies(self):
        os.environ['DETAIL_CRAWL_SITE_CAP'] = '2'
        for i in range(1, 5):
            url = f'https://www.armoryonpark.org/e/{i}'
            self._add(i, url=url, name=f'Recital {i}')
            self._event(event_id=100 + i, url=url, name=f'Recital {i}')
        self.assertEqual(self._ids(), {1, 2})

    def test_revalidation_scope_is_respected(self):
        self._add(1)
        self._add(2, url='https://www.armoryonpark.org/e/other', name='Other Recital')
        self._event()
        self._event(event_id=2, url='https://www.armoryonpark.org/e/other', name='Other Recital')
        self.assertEqual(self._ids(crawl_event_ids=[2]), {2})


D = date(2026, 10, 14)
E = date(2026, 10, 18)
PSPAN = (D, '', E, '')
PSESSIONS = [(date(2026, 10, d), '7pm' if d < 18 else '3pm', None, '') for d in range(14, 19)]
EVENT = dict(event_type='Concert', location_id=645)


def source(id, rows, website=224, url=URL, location=645):
    return dict(id=id, website_id=website, source_type='primary', location_id=location,
                url=url, occurrences=rows)


class TestRefinedEnvelopes(unittest.TestCase):
    def plan(self, sources, rows=None, event=EVENT):
        return refined_envelopes(event, rows if rows is not None else [PSPAN] + PSESSIONS, sources)

    def test_same_page_sessions_replace_its_listing_range(self):
        self.assertEqual(self.plan([source(1, [PSPAN]), source(2, [PSPAN]), source(3, PSESSIONS)]),
                         {PSPAN: {o[0] for o in PSESSIONS}})

    def test_trailing_slash_is_the_same_page(self):
        self.assertIn(PSPAN, self.plan([source(1, [PSPAN]), source(2, PSESSIONS, url=URL.rstrip('/'))]))

    def test_dark_days_inside_the_run_are_the_pages_call(self):
        sessions = [PSESSIONS[0], PSESSIONS[2], PSESSIONS[4]]
        self.assertEqual(self.plan([source(1, [PSPAN]), source(2, sessions)], rows=[PSPAN] + sessions),
                         {PSPAN: {D, date(2026, 10, 16), E}})

    def test_sessions_must_reach_both_edges(self):
        self.assertFalse(self.plan([source(1, [PSPAN]), source(2, PSESSIONS[:-1])]))
        self.assertFalse(self.plan([source(1, [PSPAN]), source(2, PSESSIONS[1:])]))

    def test_a_page_printing_both_shapes_keeps_both(self):
        self.assertFalse(self.plan([source(1, [PSPAN] + PSESSIONS)]))

    def test_another_page_or_publisher_cannot_refine(self):
        self.assertFalse(self.plan([source(1, [PSPAN]), source(2, PSESSIONS, url=URL + 'tickets/')]))
        self.assertFalse(self.plan([source(1, [PSPAN]), source(2, PSESSIONS, website=1036)]))

    def test_range_claimed_by_a_second_publisher_is_kept(self):
        self.assertFalse(self.plan([source(1, [PSPAN]), source(2, [PSPAN], website=1036,
                                                               url='https://msmnyc.edu/x'),
                                    source(3, PSESSIONS)]))

    def test_no_provenance_no_removal(self):
        self.assertFalse(self.plan([source(3, PSESSIONS)]))

    def test_untimed_or_spanning_sessions_do_not_refine(self):
        for bad in [(E, '', None, ''), (date(2026, 10, 17), '7pm', E, ''), (E, '3', None, '')]:
            with self.subTest(bad=bad):
                self.assertFalse(self.plan([source(1, [PSPAN]), source(2, PSESSIONS[:-1] + [bad])]))

    def test_overlapping_other_run_vetoes(self):
        other = (date(2026, 10, 16), '', date(2026, 10, 20), '')
        self.assertFalse(self.plan([source(1, [PSPAN]), source(2, PSESSIONS)], rows=[PSPAN, other] + PSESSIONS))
        self.assertFalse(self.plan([source(1, [PSPAN]), source(2, PSESSIONS),
                                    source(3, [other], website=1036, url='https://msmnyc.edu/x')]))

    def test_other_venue_vetoes(self):
        self.assertFalse(self.plan([source(1, [PSPAN]), source(2, PSESSIONS, location=493)]))

    def test_exhibitions_festivals_and_unknown_types_keep_ranges(self):
        for typ in ('Exhibition', 'Festival', 'Camp', None):
            with self.subTest(typ=typ):
                self.assertFalse(self.plan([source(1, [PSPAN]), source(2, PSESSIONS)],
                                           event=dict(EVENT, event_type=typ)))


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1', 'Opt in to connection-local MariaDB tables')
class TestRefinedEnvelopeMerge(unittest.TestCase):
    """The merge path (merger._merge_occurrences_into_event → reconcile_envelopes)."""

    def setUp(self):
        from db import create_connection
        self.conn = create_connection()
        self.assertIsNotNone(self.conn)
        self.addCleanup(self.conn.close)
        self.q = self.conn.cursor()
        schemas = {
            'events': 'id INT,event_type VARCHAR(40),location_id INT',
            'event_occurrences': 'id INT AUTO_INCREMENT PRIMARY KEY,event_id INT,start_date DATE,'
                                 'start_time VARCHAR(20),end_date DATE,end_time VARCHAR(20),sort_order INT DEFAULT 0',
            'crawl_events': 'id INT,crawl_result_id INT,location_id INT,url VARCHAR(255)',
            'crawl_results': 'id INT,website_id INT', 'event_sources': 'event_id INT,crawl_event_id INT',
            'crawl_event_occurrences': 'crawl_event_id INT,start_date DATE,start_time VARCHAR(20),'
                                       'end_date DATE,end_time VARCHAR(20)'}
        for name, schema in schemas.items():
            self.q.execute(f'CREATE TEMPORARY TABLE {name} ({schema})')
        # Constant-only fixture shadowing websites on this connection.
        self.q.execute("CREATE TEMPORARY TABLE websites AS SELECT 224 AS id, 'primary' AS source_type")
        self.q.execute("INSERT INTO events VALUES(1,'Concert',645)")
        self.q.execute('INSERT INTO crawl_results VALUES(1,224)')
        # 1: an earlier listing extraction; 2: this run's row after its detail fetch.
        self.q.execute('INSERT INTO crawl_events VALUES(1,1,645,%s),(2,1,645,%s)', (URL, URL))
        self.q.execute('INSERT INTO event_sources VALUES(1,1)')
        for ce, rows in [(1, [PSPAN]), (2, PSESSIONS)]:
            for o in rows:
                self.q.execute('INSERT INTO crawl_event_occurrences VALUES(%s,%s,%s,%s,%s)', (ce, *o))

    def rows(self):
        self.q.execute('SELECT start_date,start_time,end_date,end_time FROM event_occurrences '
                       'ORDER BY start_date,start_time')
        return self.q.fetchall()

    def seed(self, rows):
        for o in rows:
            self.q.execute('INSERT INTO event_occurrences(event_id,start_date,start_time,end_date,end_time) '
                           'VALUES(1,%s,%s,%s,%s)', o)

    def test_detail_sessions_replace_the_stored_range(self):
        from merger import _merge_occurrences_into_event
        self.seed([PSPAN])
        _merge_occurrences_into_event(self.q, 1, PSESSIONS, crawl_event_id=2)
        self.assertEqual(self.rows(), PSESSIONS)
        self.q.execute('SELECT COUNT(*) FROM crawl_event_occurrences')
        self.assertEqual(self.q.fetchone()[0], 6)  # source evidence untouched

    def test_repeated_listing_range_is_ignored_once_refined(self):
        from merger import _merge_occurrences_into_event
        self.q.execute('INSERT INTO event_sources VALUES(1,2)')
        self.q.execute('INSERT INTO crawl_events VALUES(3,1,645,%s)', (URL,))
        self.q.execute('INSERT INTO crawl_event_occurrences VALUES(3,%s,%s,%s,%s)', PSPAN)
        self.seed(PSESSIONS)
        _merge_occurrences_into_event(self.q, 1, [PSPAN], crawl_event_id=3)
        self.assertEqual(self.rows(), PSESSIONS)

    def test_partial_merge_keeps_the_range(self):
        from merger import _merge_occurrences_into_event
        self.seed([PSPAN])
        _merge_occurrences_into_event(self.q, 1, PSESSIONS[:1], crawl_event_id=2)
        self.assertIn(PSPAN, self.rows())


if __name__ == '__main__':
    unittest.main()
