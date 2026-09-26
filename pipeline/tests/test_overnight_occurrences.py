"""Conservative overnight equivalence and actual SQL merge boundary regressions."""
import itertools
import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overnight_occurrences import coalesce_overnight_occurrences
from merger import _merge_occurrences_into_event, _refresh_occurrence_indexes

DAY = date(2026, 10, 24)
NULL = (DAY, '8pm', None, '1am')
EXPLICIT = (DAY, '8pm', DAY + timedelta(days=1), '1am')


class EquivalenceTests(unittest.TestCase):
    def test_both_arrival_orders_prefer_explicit(self):
        self.assertEqual(coalesce_overnight_occurrences([NULL], [EXPLICIT]),
                         ([], [EXPLICIT], [NULL]))
        self.assertEqual(coalesce_overnight_occurrences([EXPLICIT], [NULL]),
                         ([EXPLICIT], [], []))

    def test_creation_batch_both_orders(self):
        for incoming in ([NULL, EXPLICIT], [EXPLICIT, NULL]):
            self.assertEqual(coalesce_overnight_occurrences([], incoming),
                             ([], [EXPLICIT], []))

    def test_existing_duplicate_reconciliation_only_when_touched(self):
        other = (DAY + timedelta(days=7), '8pm', None, '1am')
        self.assertEqual(coalesce_overnight_occurrences([NULL, EXPLICIT], [other]),
                         ([NULL, EXPLICIT], [other], []))
        self.assertEqual(coalesce_overnight_occurrences([NULL, EXPLICIT], [NULL]),
                         ([EXPLICIT], [], [NULL]))

    def test_never_infers_next_day_from_clocks_alone(self):
        self.assertEqual(coalesce_overnight_occurrences([], [NULL]), ([], [NULL], []))

    def test_normalized_clock_spellings(self):
        alias = (DAY, '20:00', None, '1:00 AM')
        self.assertEqual(coalesce_overnight_occurrences([alias], [EXPLICIT]),
                         ([], [EXPLICIT], [alias]))

    def test_unknown_or_bare_clocks_are_not_deleted(self):
        for st, et in [('', '1am'), ('8pm', ''), ('8', '1am'), ('8pm', '1'),
                       ('8pm', 'late'), ('25pm', '1am'), ('8pm', '13am')]:
            row = (DAY, st, None, et)
            with self.subTest(row=row):
                self.assertEqual(coalesce_overnight_occurrences([row], [EXPLICIT]),
                                 ([row], [EXPLICIT], []))

    def test_conflicting_clock_or_showtime_preserved(self):
        for row in [(DAY, '9pm', None, '1am'), (DAY, '8pm', None, '2am'),
                    (DAY + timedelta(days=1), '8pm', None, '1am')]:
            self.assertEqual(coalesce_overnight_occurrences([row], [EXPLICIT]),
                             ([row], [EXPLICIT], []))
        conflict = (DAY, '8pm', None, '2am')
        self.assertEqual(coalesce_overnight_occurrences([NULL, conflict], [EXPLICIT]),
                         ([NULL, conflict], [EXPLICIT], []))

    def test_competing_explicit_clock_cannot_discard_null_evidence(self):
        conflict = (DAY, '8pm', DAY + timedelta(days=1), '2am')
        for incoming in ([conflict, EXPLICIT], [EXPLICIT, conflict]):
            self.assertEqual(coalesce_overnight_occurrences([NULL], incoming),
                             ([NULL], incoming, []))
        self.assertEqual(coalesce_overnight_occurrences([NULL, conflict], [EXPLICIT]),
                         ([NULL, conflict], [EXPLICIT], []))

    def test_ambiguous_nonempty_explicit_end_clock_declines(self):
        for clock in ['1', '1:30', 'TBA', 'late', 'not-a-clock', ' ']:
            ambiguous = EXPLICIT[:3] + (clock,)
            with self.subTest(clock=clock):
                self.assertEqual(coalesce_overnight_occurrences(
                    [NULL, ambiguous], [EXPLICIT]), ([NULL, ambiguous], [EXPLICIT], []))

    def test_truly_empty_explicit_end_clock_remains_promotable(self):
        for clock in ['', None]:
            unknown = EXPLICIT[:3] + (clock,)
            self.assertEqual(coalesce_overnight_occurrences([NULL, unknown], [EXPLICIT]),
                             ([unknown], [EXPLICIT], [NULL]))

    def test_same_day_multiday_and_twenty_four_hour_spans_preserved(self):
        pairs = [(NULL, (DAY, '8pm', DAY, '1am')),
                 (NULL, (DAY, '8pm', DAY + timedelta(days=2), '1am')),
                 ((DAY, '8pm', None, '8pm'), (DAY, '8pm', DAY + timedelta(days=1), '8pm')),
                 ((DAY, '8am', None, '9am'), (DAY, '8am', DAY + timedelta(days=1), '9am'))]
        for old, incoming in pairs:
            self.assertEqual(coalesce_overnight_occurrences([old], [incoming]),
                             ([old], [incoming], []))

    def test_date_rollover_and_midnight(self):
        for day in (date(2026, 12, 31), date(2028, 2, 29)):
            old = (day, '11:30pm', None, '12am')
            new = (day, '11:30pm', day + timedelta(days=1), '12am')
            self.assertEqual(coalesce_overnight_occurrences([old], [new]), ([], [new], [old]))

    def test_trailing_metadata_retained(self):
        old, new = NULL + (8, 'source-old'), EXPLICIT + (9, 'source-new')
        self.assertEqual(coalesce_overnight_occurrences([old], [new]), ([], [new], [old]))

    def test_non_date_input_declines(self):
        old = ('2026-10-24', '8pm', None, '1am')
        new = ('2026-10-24', '8pm', '2026-10-25', '1am')
        self.assertEqual(coalesce_overnight_occurrences([old], [new]), ([old], [new], []))

    def test_index_refresh_uses_dates_ranges_and_in_place_slots(self):
        dates, ranges, slots = {1: {'stale'}}, {1: [('stale', 'stale')]}, {1: {('stale', '8pm')}}
        url_slots = slots[1]
        rows = [EXPLICIT, (DAY - timedelta(days=10), '8pm', None, '1am'),
                (DAY + timedelta(days=1), '9pm', None, '')]
        _refresh_occurrence_indexes(1, rows, dates, ranges, slots, DAY, DAY + timedelta(days=90))
        self.assertEqual(dates[1], {'2026-10-24', '2026-10-25'})
        self.assertEqual(ranges[1], [(DAY, DAY + timedelta(days=1))])
        self.assertIs(url_slots, slots[1])
        self.assertEqual(url_slots, {('2026-10-24', '8pm'), ('2026-10-25', '9pm')})


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1',
                     'Opt in to connection-local MariaDB tables')
class TemporaryDatabaseTests(unittest.TestCase):
    def setUp(self):
        from db import create_connection
        self.conn = create_connection()
        self.assertIsNotNone(self.conn)
        self.addCleanup(self.conn.close)
        self.q = self.conn.cursor()
        self.q.execute('''CREATE TEMPORARY TABLE event_occurrences (
            id INT AUTO_INCREMENT PRIMARY KEY,event_id INT,start_date DATE,
            start_time VARCHAR(20),end_date DATE,end_time VARCHAR(20),sort_order INT DEFAULT 0)''')
        self.q.execute('''CREATE TEMPORARY TABLE crawl_event_occurrences (
            crawl_event_id INT,start_date DATE,start_time VARCHAR(20),end_date DATE,end_time VARCHAR(20))''')
        self.q.execute('INSERT INTO crawl_event_occurrences VALUES(100,%s,%s,%s,%s)', NULL)

    def seed(self, rows, event_id=1):
        for order, row in enumerate(rows):
            self.q.execute('''INSERT INTO event_occurrences
                (event_id,start_date,start_time,end_date,end_time,sort_order)
                VALUES(%s,%s,%s,%s,%s,%s)''', (event_id, *row[:4], order))

    def rows(self, event_id=1):
        self.q.execute('''SELECT start_date,start_time,end_date,end_time FROM event_occurrences
            WHERE event_id=%s ORDER BY start_date,start_time,end_date,end_time''', (event_id,))
        return self.q.fetchall()

    def test_explicit_arrives_after_null_and_stale_replay_is_idempotent(self):
        self.seed([NULL])
        returned = _merge_occurrences_into_event(self.q, 1, [EXPLICIT])
        self.assertEqual(returned, [EXPLICIT])
        for incoming in ([NULL], [EXPLICIT], [NULL, EXPLICIT]):
            _merge_occurrences_into_event(self.q, 1, incoming)
            self.assertEqual(self.rows(), [EXPLICIT])

    def test_null_arrives_after_explicit(self):
        self.seed([EXPLICIT])
        self.assertEqual(_merge_occurrences_into_event(self.q, 1, [NULL]), [EXPLICIT])
        self.assertEqual(self.rows(), [EXPLICIT])

    def test_both_orders_inside_one_merge(self):
        for event_id, rows in enumerate(itertools.permutations([NULL, EXPLICIT]), 1):
            _merge_occurrences_into_event(self.q, event_id, rows)
            self.assertEqual(self.rows(event_id), [EXPLICIT])

    def test_exact_delete_preserves_conflicting_clocks_history_neighbor_and_sources(self):
        conflict = (DAY, '9pm', None, '2am')
        unknown = (DAY, '9pm', None, '')
        other_day = (DAY + timedelta(days=7), '8pm', None, '1am')
        self.seed([NULL, conflict, unknown, other_day])
        self.seed([NULL], event_id=2)
        _merge_occurrences_into_event(self.q, 1, [EXPLICIT])
        self.assertCountEqual(self.rows(), [conflict, unknown, other_day, EXPLICIT])
        self.assertEqual(self.rows(2), [NULL])
        self.q.execute('SELECT start_date,start_time,end_date,end_time FROM crawl_event_occurrences')
        self.assertEqual(self.q.fetchall(), [NULL])

    def test_conflicting_explicit_clock_preserves_null_evidence(self):
        conflict = (DAY, '8pm', DAY + timedelta(days=1), '2am')
        self.seed([NULL, conflict])
        _merge_occurrences_into_event(self.q, 1, [EXPLICIT])
        self.assertCountEqual(self.rows(), [NULL, conflict])

    def test_nonempty_ambiguous_first_writer_cannot_erase_qualified_null_twin(self):
        null = (DAY, '9pm', None, '12am')
        explicit = (DAY, '9pm', DAY + timedelta(days=1), '12am')
        for event_id, clock in enumerate(['12', '1', '11:30', 'TBA', 'late', ' '], 1):
            ambiguous = explicit[:3] + (clock,)
            self.seed([null, ambiguous], event_id)
            with self.subTest(clock=clock):
                for incoming in ([explicit], [null], [explicit]):
                    _merge_occurrences_into_event(self.q, event_id, incoming)
                    self.assertCountEqual(self.rows(event_id), [null, ambiguous])

    def test_empty_explicit_first_writer_is_promoted_without_losing_known_clock(self):
        for event_id, clock in enumerate(['', None], 1):
            self.seed([NULL, EXPLICIT[:3] + (clock,)], event_id)
            _merge_occurrences_into_event(self.q, event_id, [EXPLICIT])
            self.assertEqual(self.rows(event_id), [EXPLICIT])
            _merge_occurrences_into_event(self.q, event_id, [NULL])
            self.assertEqual(self.rows(event_id), [EXPLICIT])

    def test_existing_duplicates_removed_and_index_state_matches_stored(self):
        self.seed([NULL, EXPLICIT, NULL])
        returned = _merge_occurrences_into_event(self.q, 1, [NULL])
        self.assertEqual(returned, [EXPLICIT])
        self.assertEqual(self.rows(), [EXPLICIT])
        dates, ranges, slots = {}, {}, {1: set()}
        _refresh_occurrence_indexes(1, returned, dates, ranges, slots, DAY, DAY + timedelta(days=90))
        self.assertEqual(ranges[1], [(DAY, DAY + timedelta(days=1))])
        self.assertEqual(slots[1], {('2026-10-24', '8pm')})

    def test_unknown_end_clock_is_not_removed(self):
        unknown = (DAY, '8pm', None, '')
        self.seed([unknown, EXPLICIT])
        _merge_occurrences_into_event(self.q, 1, [NULL])
        self.assertCountEqual(self.rows(), [unknown, EXPLICIT])

    def test_three_actual_dance_repro_schedules(self):
        cases = {
            179680: [(date(2026, 9, 26), '8pm', '1am'),
                     (date(2026, 10, 24), '8pm', '1am'),
                     (date(2026, 11, 14), '8pm', '1am'),
                     (date(2026, 12, 12), '8pm', '1am')],
            194432: [(date(2026, 9, 26), '7:15pm', '12am')],
            251880: [(date(2026, 10, 9), '6pm', '12am')],
        }
        for event_id, clocks in cases.items():
            explicit = [(d, st, d + timedelta(days=1), et) for d, st, et in clocks]
            null = [(d, st, None, et) for d, st, et in clocks]
            self.seed(explicit + null, event_id)
            for incoming in (null, explicit, null):
                _merge_occurrences_into_event(self.q, event_id, incoming)
                self.assertEqual(self.rows(event_id), explicit)


if __name__ == '__main__':
    unittest.main()
