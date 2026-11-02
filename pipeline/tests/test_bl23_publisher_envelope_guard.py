"""BL23 follow-up: a publisher's run span yields to the dated performances that tile it.

The 2026-11-02 run re-added an untimed run span ("Oct 15 – Nov 8") on top of
existing dated performances for ~15 events (The Tank w94, Irish Rep w287, ...):
the R2 guard `_drop_covered_season_envelopes` only acts when the covering
sessions come from a DIFFERENT website and the span is >= 31 days. The sibling
`_drop_tiled_publisher_envelopes` refuses (incoming) or deletes (stored) a span
of any length on a scheduled-attendance event when >= 3 distinct days inside it
hold timed single-day occurrences that the span's own website supports, or that
no source carries (written from the publisher's pages by a reviewer), and those
days reach both ends of the span's visible part.

The database tests run on connection-local TEMPORARY tables
(FOMO_TEST_TEMP_DB=1); no production rows are read or changed.
Run: cd pipeline/tests && PYTHONPATH=..:../.. FOMO_TEST_TEMP_DB=1 ../../venv/bin/python test_bl23_publisher_envelope_guard.py
"""
import contextlib
import io
import json
import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger

EVENT = 258881  # The Tank "Show Trial"
TANK, OTHER = 94, 4766
RUN = (date(2026, 10, 15), '', date(2026, 11, 8), '')
# The stored performances: the run's 16 dated nights, 7pm (3pm Sundays).
NIGHTS = [date(2026, 10, d) for d in (15, 16, 17, 19, 22, 23, 24, 26, 29, 30)] + \
         [date(2026, 11, d) for d in (1, 2, 5, 6, 7, 8)]
PERFORMANCES = [(d, '3pm' if d.weekday() == 6 else '7pm', None, '') for d in NIGHTS]


class EdgeToleranceTests(unittest.TestCase):

    def test_short_runs_get_a_tight_edge_and_long_runs_r2s(self):
        edge = merger._publisher_envelope_edge
        self.assertEqual(edge(date(2026, 11, 2), date(2026, 11, 8)).days, 3)
        self.assertEqual(edge(date(2026, 11, 2), date(2026, 11, 22)).days, 5)
        self.assertEqual(edge(date(2026, 11, 2), date(2027, 1, 31)).days,
                         merger.SEASON_ENVELOPE_EDGE_DAYS)
        # A span already over (stored, end before today) still gets the floor.
        self.assertEqual(edge(date(2026, 11, 2), date(2026, 10, 30)).days, 3)


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1',
                     'Opt in to connection-local MariaDB tests with FOMO_TEST_TEMP_DB=1')
class PublisherEnvelopeGuardTests(unittest.TestCase):
    SCHEMAS = {
        'events': 'id INT PRIMARY KEY, event_type VARCHAR(50), location_id INT',
        'event_occurrences': ('id INT AUTO_INCREMENT PRIMARY KEY, event_id INT, start_date DATE, '
                              'start_time VARCHAR(20), end_date DATE NULL, end_time VARCHAR(20), '
                              'sort_order INT DEFAULT 0'),
        'event_sources': 'event_id INT, crawl_event_id INT',
        'crawl_events': ('id INT PRIMARY KEY, crawl_result_id INT, raw_data TEXT, '
                         'location_id INT, url VARCHAR(500)'),
        'crawl_results': 'id INT PRIMARY KEY, website_id INT, crawled_at DATETIME, processed_at DATETIME',
        'crawl_event_occurrences': ('crawl_event_id INT, start_date DATE, start_time VARCHAR(20), '
                                    'end_date DATE NULL, end_time VARCHAR(20)'),
        'websites': 'id INT PRIMARY KEY, source_type VARCHAR(20)',
    }

    def setUp(self):
        from db import create_connection
        self.conn = create_connection()
        self.assertIsNotNone(self.conn)
        self.addCleanup(self.conn.close)
        self.cur = self.conn.cursor()
        for table, schema in self.SCHEMAS.items():
            self.cur.execute(f'CREATE TEMPORARY TABLE {table} ({schema})')
        self.event('Theater Show')
        # "Today" is the 2026-11-02 run; the span's visible part is Nov 2 – Nov 8.
        window = patch('merger.get_active_date_window',
                       return_value=(date(2026, 11, 2), date(2027, 1, 31)))
        window.start()
        self.addCleanup(window.stop)

    def event(self, event_type, event_id=EVENT):
        self.cur.execute('INSERT INTO events VALUES (%s,%s,898)', (event_id, event_type))

    def source(self, ce_id, website_id, rows, linked=True, event_id=EVENT, raw=None):
        self.cur.execute('INSERT INTO crawl_results VALUES (%s,%s,NOW(),NOW())', (ce_id, website_id))
        self.cur.execute('INSERT INTO crawl_events(id,crawl_result_id,raw_data) VALUES (%s,%s,%s)',
                         (ce_id, ce_id, raw))
        for sd, st, ed, et in rows:
            self.cur.execute('INSERT INTO crawl_event_occurrences VALUES (%s,%s,%s,%s,%s)',
                             (ce_id, sd, st, ed, et))
        if linked:
            self.cur.execute('INSERT INTO event_sources VALUES (%s,%s)', (event_id, ce_id))

    def store(self, rows, event_id=EVENT):
        for sd, st, ed, et in rows:
            self.cur.execute('INSERT INTO event_occurrences(event_id,start_date,start_time,end_date,'
                             'end_time) VALUES (%s,%s,%s,%s,%s)', (event_id, sd, st, ed, et))

    def merge(self, ce_id, rows, event_id=EVENT):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            merger._merge_occurrences_into_event(self.cur, event_id, rows, crawl_event_id=ce_id)
        self.log = out.getvalue()

    def stored(self, event_id=EVENT):
        self.cur.execute('SELECT start_date, start_time, end_date FROM event_occurrences '
                         'WHERE event_id=%s ORDER BY start_date, end_date', (event_id,))
        return [tuple(r) for r in self.cur.fetchall()]

    def spans(self, event_id=EVENT):
        return [r for r in self.stored(event_id) if r[2] and r[2] != r[0]]

    # ── Positive: the Tank shape ──
    def test_tank_run_span_is_refused_over_reviewer_written_performances(self):
        # Show Trial: the performances carry no source (a detail reviewer wrote
        # them from the show page); the listing re-crawl brings the run span.
        self.store(PERFORMANCES)
        self.source(1, TANK, [RUN], linked=False)
        self.merge(1, [RUN])
        self.assertEqual(self.spans(), [])
        self.assertEqual(len(self.stored()), len(PERFORMANCES))
        self.assertIn('PUBLISHER-ENVELOPE refused e258881 2026-10-15..2026-11-08 (from w94): '
                      '16 dated day(s) tile it (0 from the same website, 16 unsourced)', self.log)

    def test_stored_run_span_is_removed_when_its_sites_performances_arrive(self):
        # My Mobster: the span is stored; the Tank's detail crawl lists the nights.
        self.source(1, TANK, [RUN])
        self.store([RUN])
        self.source(2, TANK, PERFORMANCES, linked=False)
        self.merge(2, PERFORMANCES)
        self.assertEqual(self.spans(), [])
        self.assertIn('PUBLISHER-ENVELOPE removed e258881', self.log)
        self.assertIn('(16 from the same website, 0 unsourced)', self.log)

    def test_long_class_term_tiled_by_its_sessions_is_dropped(self):
        # Center & Throw: a 90-day term span over the class's dated Saturdays.
        self.cur.execute("UPDATE events SET event_type='Class'")
        term = (date(2026, 9, 13), '', date(2026, 12, 12), '')
        saturdays = [(date(2026, 11, 7) + timedelta(weeks=w), '10am', None, '') for w in range(6)]
        self.store(saturdays)
        self.source(1, 5293, [term], linked=False)
        self.source(2, 5293, saturdays)
        self.merge(1, [term])
        self.assertEqual(self.spans(), [])

    # ── Negatives ──
    def test_exhibition_run_is_never_touched(self):
        self.cur.execute("UPDATE events SET event_type='Exhibition'")
        self.store(PERFORMANCES)
        self.source(1, TANK, [RUN], linked=False)
        self.merge(1, [RUN])
        self.assertEqual(len(self.spans()), 1)
        self.assertNotIn('PUBLISHER-ENVELOPE', self.log)

    def test_festival_run_is_never_touched(self):
        self.cur.execute("UPDATE events SET event_type='Festival'")
        self.store(PERFORMANCES)
        self.source(1, TANK, [RUN], linked=False)
        self.merge(1, [RUN])
        self.assertEqual(len(self.spans()), 1)

    def test_two_dated_previews_do_not_erase_the_run(self):
        previews = PERFORMANCES[-2:]
        self.store(previews)
        self.source(1, TANK, [RUN], linked=False)
        self.merge(1, [RUN])
        self.assertEqual(len(self.spans()), 1)
        self.assertNotIn('PUBLISHER-ENVELOPE', self.log)

    def test_dates_that_stop_short_of_the_end_keep_the_span(self):
        # The Hairy Ape before its extension's dates arrived: Sep 25 – Dec 6
        # run, performances stored only through Nov 15.
        run = (date(2026, 9, 25), '', date(2026, 12, 6), '')
        through_nov_15 = [(date(2026, 11, d), '7pm', None, '') for d in (4, 5, 6, 7, 11, 12, 13, 14, 15)]
        self.store(through_nov_15)
        self.source(1, 287, [run], linked=False)
        self.merge(1, [run])
        self.assertEqual(len(self.spans()), 1)

    def test_short_run_with_dates_only_at_its_start_keeps_the_span(self):
        # Three nights at the start of a ten-day run: R2's 14-day tolerance
        # would accept this; the publisher edge (a quarter of the run, min 3) does not.
        run = (date(2026, 12, 2), '', date(2026, 12, 11), '')
        first_nights = [(date(2026, 12, d), '7pm', None, '') for d in (2, 3, 4)]
        self.store(first_nights)
        self.source(1, TANK, [run], linked=False)
        self.merge(1, [run])
        self.assertEqual(len(self.spans()), 1)

    def test_span_without_provenance_is_kept(self):
        self.store(PERFORMANCES + [RUN])
        self.source(1, TANK, PERFORMANCES[:1], linked=False)
        self.merge(1, PERFORMANCES[:1])
        self.assertEqual(len(self.spans()), 1)

    def test_another_publishers_dates_do_not_tile_a_short_span(self):
        # Learning to Speak shape: the span is w4766's, the dated nights only
        # w78's. Under 31 days this is neither rule's business.
        self.source(1, 78, PERFORMANCES)
        self.store(PERFORMANCES)
        self.source(2, OTHER, [RUN], linked=False)
        self.merge(2, [RUN])
        self.assertEqual(len(self.spans()), 1)

    def test_timed_span_is_outside_the_rule(self):
        timed = (date(2026, 10, 15), '7pm', date(2026, 11, 8), '')
        self.store(PERFORMANCES)
        self.source(1, TANK, [timed], linked=False)
        self.merge(1, [timed])
        self.assertIn((timed[0], '7pm', timed[2]), self.stored())

    def test_all_day_span_from_the_publisher_is_kept(self):
        raw = json.dumps({'occurrence_provenance': {'version': 1, 'entries': [
            {'slot': [str(RUN[0]), '', str(RUN[2]), ''], 'all_day': True}]}})
        self.store(PERFORMANCES)
        self.source(1, TANK, [RUN], linked=False, raw=raw)
        self.merge(1, [RUN])
        self.assertEqual(len(self.spans()), 1)


if __name__ == '__main__':
    unittest.main()
