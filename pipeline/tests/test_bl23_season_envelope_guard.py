"""BL23 R2: a season envelope yields to another publisher's dated sessions.

The w3524 NYC Tourism "New York Knicks Basketball" card (untimed Oct 20 – Apr 11)
re-attached to e240927 beside MSG's dated games on the 2026-10-10 merge:
schedule_envelopes.envelope() stops at 30 days and SESSION_TYPES lacks Sports,
so nothing reconciled it. `_drop_covered_season_envelopes` refuses (incoming)
or deletes (stored) an untimed span of >= 31 days on a scheduled-attendance
event once >= 3 distinct days inside it carry timed single-day sessions from a
website that does not carry the span.

The database tests run on connection-local TEMPORARY tables
(FOMO_TEST_TEMP_DB=1); no production rows are read or changed.
Run: cd pipeline/tests && PYTHONPATH=..:../.. FOMO_TEST_TEMP_DB=1 ../../venv/bin/python test_bl23_season_envelope_guard.py
"""
import contextlib
import io
import os
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger

EVENT = 240927
TOURISM, MSG = 3524, 271
SEASON = (date(2026, 10, 20), '', date(2027, 4, 11), '')
GAMES = [(date(2026, 10, 20), '7pm', None, ''), (date(2026, 10, 25), '7pm', None, ''),
         (date(2026, 10, 27), '8pm', None, '')]


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1',
                     'Opt in to connection-local MariaDB tests with FOMO_TEST_TEMP_DB=1')
class SeasonEnvelopeGuardTests(unittest.TestCase):
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
        self.event('Sports')
        # Pin "today" and the horizon so the edge-coverage rule is date-stable.
        window = patch('merger.get_active_date_window',
                       return_value=(date(2026, 10, 19), date(2026, 11, 10)))
        window.start()
        self.addCleanup(window.stop)

    def event(self, event_type, event_id=EVENT):
        self.cur.execute('INSERT INTO events VALUES (%s,%s,511)', (event_id, event_type))

    def source(self, ce_id, website_id, rows, linked=True, event_id=EVENT):
        self.cur.execute('INSERT INTO crawl_results VALUES (%s,%s,NOW(),NOW())', (ce_id, website_id))
        self.cur.execute('INSERT INTO crawl_events(id,crawl_result_id) VALUES (%s,%s)', (ce_id, ce_id))
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

    def has_season(self):
        return any(r[2] == SEASON[2] for r in self.stored())

    def test_knicks_incoming_season_card_is_refused(self):
        self.source(1, MSG, GAMES)
        self.store(GAMES)
        self.source(2, TOURISM, [SEASON], linked=False)
        self.merge(2, [SEASON])
        self.assertFalse(self.has_season())
        self.assertEqual(len(self.stored()), 3)
        self.assertIn('SEASON-ENVELOPE refused e240927 2026-10-20..2027-04-11 (from w3524)', self.log)

    def test_stored_season_card_is_removed_when_games_arrive(self):
        self.source(2, TOURISM, [SEASON])
        self.store([SEASON])
        self.source(1, MSG, GAMES, linked=False)
        self.merge(1, GAMES)
        self.assertFalse(self.has_season())
        self.assertEqual([r[0] for r in self.stored()], [g[0] for g in GAMES])
        self.assertIn('SEASON-ENVELOPE removed e240927', self.log)

    def test_two_session_days_are_not_enough(self):
        self.source(1, MSG, GAMES[:2])
        self.store(GAMES[:2])
        self.source(2, TOURISM, [SEASON], linked=False)
        self.merge(2, [SEASON])
        self.assertTrue(self.has_season())
        self.assertNotIn('SEASON-ENVELOPE', self.log)

    def test_same_publisher_may_offer_both_shapes(self):
        self.source(1, TOURISM, GAMES)
        self.store(GAMES)
        self.source(2, TOURISM, [SEASON], linked=False)
        self.merge(2, [SEASON])
        self.assertTrue(self.has_season())

    def test_exhibition_run_is_never_touched(self):
        self.cur.execute("UPDATE events SET event_type='Exhibition'")
        self.source(1, MSG, GAMES)
        self.store(GAMES)
        self.source(2, TOURISM, [SEASON], linked=False)
        self.merge(2, [SEASON])
        self.assertTrue(self.has_season())

    def test_thirty_day_span_is_outside_the_rule(self):
        month = (date(2026, 10, 20), '', date(2026, 11, 19), '')
        self.source(1, MSG, GAMES)
        self.store(GAMES)
        self.source(2, TOURISM, [month], linked=False)
        self.merge(2, [month])
        self.assertIn((month[0], '', month[2]), self.stored())
        self.assertNotIn('SEASON-ENVELOPE', self.log)

    def test_stored_span_without_provenance_is_kept(self):
        self.store([SEASON])
        self.source(1, MSG, GAMES, linked=False)
        self.merge(1, GAMES)
        self.assertTrue(self.has_season())

    def test_sessions_without_source_support_do_not_count(self):
        self.store(GAMES)  # legacy canonical rows, no crawl evidence
        self.source(2, TOURISM, [SEASON], linked=False)
        self.merge(2, [SEASON])
        self.assertTrue(self.has_season())

    def test_preview_dates_of_a_long_run_do_not_erase_it(self):
        """Three dates in the run's first week; the visible window reaches far past."""
        with patch('merger.get_active_date_window',
                   return_value=(date(2026, 10, 19), date(2027, 1, 17))):
            self.source(1, MSG, GAMES)
            self.store(GAMES)
            self.source(2, TOURISM, [SEASON], linked=False)
            self.merge(2, [SEASON])
        self.assertTrue(self.has_season())
        self.assertNotIn('SEASON-ENVELOPE', self.log)

    def test_sessions_outside_the_span_do_not_count(self):
        late = [(date(2027, 5, d), '7pm', None, '') for d in (1, 3, 5)]
        self.source(1, MSG, late)
        self.store(late)
        self.source(2, TOURISM, [SEASON], linked=False)
        self.merge(2, [SEASON])
        self.assertTrue(self.has_season())


if __name__ == '__main__':
    unittest.main()
