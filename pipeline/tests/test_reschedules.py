"""Explicit notice regressions, including provenance and stale-source replay."""
import copy
import os
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reschedules import explicit_reschedule, reconcile_reschedules, superseded_slots
from processor import group_event_occurrences

OLD = (date(2026, 9, 28), '6:30pm', None, '7:30pm')
NEW = (date(2026, 9, 29), '6:30pm', None, '7:30pm')
JULY = (date(2026, 7, 27), '6:30pm', None, '7:30pm')
AUGUST = (date(2026, 8, 24), '6:30pm', None, '7:30pm')
EVENT = dict(id=180336, name='Nature Writing Book Group', location_id=7866, reviewed=True)


def source(id=1, rows=None, **kwargs):
    return dict(dict(id=id, website_id=93, name=EVENT['name'], location_id=7866,
                     description='Book discussion.', crawled_at='2026-09-14 10:00:00',
                     occurrences=[OLD] if rows is None else rows), **kwargs)


def notice(**kwargs):
    return source(kwargs.pop('id', 2), [NEW], **dict(dict(description='A book discussion. Rescheduled from September 28!',
                                      crawled_at='2026-09-20 10:00:00'), **kwargs))


def slot(row):
    return row[:2] + (row[2] or row[0], row[3])


class NoticeTests(unittest.TestCase):
    def test_greenlight_notice(self):
        self.assertEqual(explicit_reschedule(notice()), (OLD[0], slot(NEW)))

    def test_explicit_new_date_must_agree_with_schedule(self):
        for day, expected in [('29', (OLD[0], slot(NEW))), ('30', None)]:
            self.assertEqual(explicit_reschedule(notice(
                description=f'This event has been rescheduled from September 28, 2026 to September {day}, 2026.')),
                expected)

    def test_iso_date(self):
        self.assertEqual(explicit_reschedule(notice(description='Rescheduled from 2026-09-28.')),
                         (OLD[0], slot(NEW)))

    def test_no_inference_from_omission_or_postponement(self):
        for text in ['Now September 29!', 'Postponed. New date soon.', 'Date changed.',
                     'The September 28 event will not take place.', 'Originally scheduled in September.']:
            with self.subTest(text=text):
                self.assertIsNone(explicit_reschedule(notice(description=text)))

    def test_other_event_and_anecdotal_notices_are_not_evidence(self):
        for text in ['Another event was rescheduled from September 28.',
                     'We discuss the concert rescheduled from September 28.',
                     'Rescheduled from September 28 last year.',
                     'Rescheduled from September 28 and October 5.']:
            with self.subTest(text=text):
                self.assertIsNone(explicit_reschedule(notice(description=text)))

    def test_cancelled_replacement_declines(self):
        self.assertIsNone(explicit_reschedule(notice(description='Cancelled. Rescheduled from September 28!')))
        self.assertIsNone(explicit_reschedule(notice(name='Cancelled: Nature Writing Book Group')))

    def test_multi_day_multi_session_and_multi_showtime_decline(self):
        for rows in [[NEW, JULY], [NEW, (NEW[0], '8pm', None, '9pm')],
                     [(NEW[0], NEW[1], date(2026, 10, 1), NEW[3])], []]:
            self.assertIsNone(explicit_reschedule(notice(occurrences=rows)))

    def test_year_rollover_has_one_nearby_interpretation(self):
        new = (date(2027, 1, 2), '6pm', None, '')
        self.assertEqual(explicit_reschedule(notice(description='Rescheduled from December 30!',
                                                  occurrences=[new])),
                         (date(2026, 12, 30), slot(new)))

    def test_far_away_invalid_and_multiple_notices_decline(self):
        for text in ['Rescheduled from February 30!', 'Rescheduled from April 28!',
                     'Rescheduled from September 28, 2025!', 'Rescheduled from September 29!',
                     'Rescheduled from September 28! Rescheduled from September 27!']:
            self.assertIsNone(explicit_reschedule(notice(description=text)))

    def test_processor_preserves_literal_notice_in_normalized_source(self):
        event, = group_event_occurrences([dict(name=EVENT['name'], location='Greene Garden',
            description=notice()['description'], start_date='2026-09-29',
            start_time='6:30pm', end_date=None, end_time='7:30pm',
            url='https://example.org/event/new-date', hashtags=[])])
        self.assertIn('Rescheduled from September 28!', event['description'])
        self.assertEqual(explicit_reschedule(event), (OLD[0], slot(NEW)))


class ProvenanceTests(unittest.TestCase):
    def plan(self, rows=None, sources=None, event=None):
        return superseded_slots(event or EVENT, rows if rows is not None else [OLD, NEW],
                                sources if sources is not None else [source(), notice()])

    def test_only_named_old_date_removed_with_series_history(self):
        self.assertEqual(self.plan(rows=[JULY, AUGUST, OLD, NEW],
                                   sources=[source(rows=[JULY, AUGUST, OLD]), notice()]), {slot(OLD)})

    def test_changed_url_does_not_block_already_matched_identity(self):
        self.assertEqual(self.plan(sources=[source(url='https://example.org/event/2026-09-28/group'),
                                           notice(url='https://example.org/event/2026-09-29/group')]), {slot(OLD)})

    def test_future_rolling_window_without_notice_does_not_replace_series(self):
        self.assertFalse(self.plan(sources=[source(), source(2, [NEW])]))

    def test_independent_publisher_old_date_vetoes_even_when_older(self):
        self.assertFalse(self.plan(sources=[source(), notice(), source(3, website_id=94)]))

    def test_equal_newer_or_unknown_source_timestamp_vetoes(self):
        for timestamp in ['2026-09-20 10:00:00', '2026-09-21 10:00:00', None, 'invalid']:
            self.assertFalse(self.plan(sources=[source(crawled_at=timestamp), notice()]))

    def test_manual_slot_without_exact_source_provenance_is_preserved(self):
        custom = (OLD[0], '8pm', None, '9pm')
        self.assertFalse(self.plan(rows=[custom, NEW]))
        self.assertFalse(self.plan(sources=[notice()]))

    def test_multiple_old_showtimes_and_overlapping_spans_veto(self):
        for other in [(OLD[0], '8pm', None, '9pm'),
                      (date(2026, 9, 27), '', date(2026, 9, 30), '')]:
            self.assertFalse(self.plan(sources=[source(), notice(), source(3, [other])]))
        self.assertFalse(self.plan(rows=[OLD, (OLD[0], '8pm', None, '9pm'), NEW]))

    def test_wrong_venue_or_identity_never_uses_notice(self):
        for change in [dict(location_id=None), dict(location_id=365), dict(name='Other Book Group'),
                       dict(website_id=None)]:
            self.assertFalse(self.plan(sources=[source(), notice(**change)]))
            self.assertFalse(self.plan(sources=[source(**change), notice()]))
        self.assertFalse(self.plan(event=dict(EVENT, suppressed=True)))
        self.assertFalse(self.plan(event=dict(EVENT, location_id=None)))

    def test_replacement_must_be_in_current_merge_rows(self):
        self.assertFalse(self.plan(rows=[OLD]))

    def test_independent_conflicting_replacement_notice_vetoes(self):
        other = (date(2026, 9, 30), '6:30pm', None, '7:30pm')
        self.assertFalse(self.plan(sources=[source(), notice(),
            notice(id=3, website_id=94, occurrences=[other])]))

    def test_conflicting_replacement_clock_vetoes(self):
        other = (NEW[0], '8pm', None, '9pm')
        self.assertFalse(self.plan(rows=[OLD, NEW, other]))
        self.assertFalse(self.plan(sources=[source(), notice(), source(3, [other], website_id=94)]))

    def test_same_day_end_and_clock_format_normalize(self):
        equivalent = (OLD[0], '18:30', OLD[0], '19:30')
        self.assertEqual(self.plan(rows=[equivalent, NEW]), {slot(OLD)})

    def test_replay_order_does_not_revive_old_same_publisher_source(self):
        sources = [notice(), source()]
        self.assertEqual(self.plan(rows=[NEW, OLD], sources=sources), {slot(OLD)})
        self.assertEqual(self.plan(rows=[OLD, NEW], sources=list(reversed(sources))), {slot(OLD)})

    def test_inputs_are_unchanged(self):
        sources = [source(), notice()]
        original = copy.deepcopy(sources)
        self.plan(sources=sources)
        self.assertEqual(sources, original)


class Cursor:
    def __init__(self, sources):
        self.sources = sources
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchone(self):
        return EVENT['name'], EVENT['location_id'], False

    def fetchall(self):
        return [(s['id'], s['name'], s['description'], s['location_id'], s['website_id'],
                 s['crawled_at'], *o) for s in self.sources for o in s['occurrences']]


class WriteBoundaryTests(unittest.TestCase):
    def test_delete_targets_only_proven_old_slot(self):
        cursor = Cursor([source(), notice()])
        old, new = reconcile_reschedules(cursor, 180336, 2, [JULY, AUGUST, OLD], [NEW])
        self.assertEqual(old, [JULY, AUGUST])
        self.assertEqual(new, [NEW])
        writes = [(sql, params) for sql, params in cursor.calls if sql.startswith('DELETE')]
        self.assertEqual(len(writes), 1)
        self.assertIn('DELETE FROM event_occurrences', writes[0][0])
        self.assertEqual(writes[0][1], (180336, OLD[0], '6:30pm', '7:30pm'))

    def test_stale_replay_dropped_without_changing_source_history(self):
        cursor = Cursor([source(), notice()])
        old, new = reconcile_reschedules(cursor, 180336, 1, [JULY, AUGUST, NEW], [OLD])
        self.assertEqual(old, [JULY, AUGUST, NEW])
        self.assertEqual(new, [])
        self.assertFalse(any(sql.startswith('DELETE') for sql, _ in cursor.calls))

    def test_conflict_produces_no_deletion(self):
        cursor = Cursor([source(), notice(), source(3, website_id=94)])
        self.assertEqual(reconcile_reschedules(cursor, 180336, 2, [OLD], [NEW]), ([OLD], [NEW]))
        self.assertFalse(any(sql.startswith('DELETE') for sql, _ in cursor.calls))


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1',
                     'Opt in to connection-local MariaDB tables')
class DatabaseBoundaryTests(unittest.TestCase):
    def setUp(self):
        from db import create_connection
        self.conn = create_connection()
        self.assertIsNotNone(self.conn)
        self.addCleanup(self.conn.close)
        self.q = self.conn.cursor()
        schemas = {
            'events': 'id INT,name VARCHAR(500),location_id INT,suppressed BOOLEAN',
            'event_occurrences': 'id INT AUTO_INCREMENT PRIMARY KEY,event_id INT,start_date DATE,'
                'start_time VARCHAR(20),end_date DATE,end_time VARCHAR(20),sort_order INT DEFAULT 0',
            'crawl_events': 'id INT,crawl_result_id INT,name VARCHAR(500),description TEXT,location_id INT',
            'crawl_results': 'id INT,website_id INT,crawled_at DATETIME',
            'event_sources': 'event_id INT,crawl_event_id INT',
            'crawl_event_occurrences': 'crawl_event_id INT,start_date DATE,start_time VARCHAR(20),'
                'end_date DATE,end_time VARCHAR(20)',
        }
        for table, columns in schemas.items():
            self.q.execute(f'CREATE TEMPORARY TABLE {table} ({columns})')
        self.q.execute('INSERT INTO events VALUES(180336,%s,7866,FALSE)', (EVENT['name'],))
        for s in [source(rows=[JULY, AUGUST, OLD]), notice()]:
            self.q.execute('INSERT INTO crawl_results VALUES(%s,%s,%s)',
                           (s['id'], s['website_id'], s['crawled_at']))
            self.q.execute('INSERT INTO crawl_events VALUES(%s,%s,%s,%s,%s)',
                           (s['id'], s['id'], s['name'], s['description'], s['location_id']))
            self.q.execute('INSERT INTO event_sources VALUES(180336,%s)', (s['id'],))
            for o in s['occurrences']:
                self.q.execute('INSERT INTO crawl_event_occurrences VALUES(%s,%s,%s,%s,%s)', (s['id'], *o))
        for o in [JULY, AUGUST, OLD]:
            self.q.execute('''INSERT INTO event_occurrences
                (event_id,start_date,start_time,end_date,end_time) VALUES(180336,%s,%s,%s,%s)''', o)
        # A neighboring event with the identical old clock must remain untouched.
        self.q.execute('''INSERT INTO event_occurrences
            (event_id,start_date,start_time,end_date,end_time) VALUES(999,%s,%s,%s,%s)''', OLD)

    def rows(self, event_id=180336):
        self.q.execute('''SELECT start_date,start_time,end_date,end_time,sort_order
            FROM event_occurrences WHERE event_id=%s ORDER BY start_date,start_time''', (event_id,))
        return self.q.fetchall()

    def merge(self, source_id, incoming):
        from merger import _merge_occurrences_into_event
        retained, incoming = reconcile_reschedules(self.q, 180336, source_id, self.rows(), incoming)
        _merge_occurrences_into_event(self.q, 180336, incoming, crawl_event_id=source_id)
        return retained, incoming

    def test_forward_reconcile_preserves_history_neighbor_and_source_evidence(self):
        self.merge(2, [NEW])
        self.assertEqual([r[:4] for r in self.rows()], [JULY, AUGUST, NEW])
        self.assertEqual([r[:4] for r in self.rows(999)], [OLD])
        self.q.execute('SELECT COUNT(*) FROM crawl_event_occurrences')
        self.assertEqual(self.q.fetchone()[0], 4)

    def test_repeated_stale_reattach_does_not_restore_old_day(self):
        self.merge(2, [NEW])
        for _ in range(2):
            retained, incoming = self.merge(1, [OLD])
            self.assertEqual(incoming, [])
        self.assertEqual([r[:4] for r in self.rows()], [JULY, AUGUST, NEW])

    def test_independent_source_disagreement_prevents_delete(self):
        self.q.execute('INSERT INTO crawl_results VALUES(3,94,%s)', ('2026-09-13 10:00:00',))
        self.q.execute('INSERT INTO crawl_events VALUES(3,3,%s,%s,7866)', (EVENT['name'], 'Book discussion.'))
        self.q.execute('INSERT INTO event_sources VALUES(180336,3)')
        self.q.execute('INSERT INTO crawl_event_occurrences VALUES(3,%s,%s,%s,%s)', OLD)
        self.merge(2, [NEW])
        self.assertEqual([r[:4] for r in self.rows()], [JULY, AUGUST, OLD, NEW])

    def test_manual_clock_without_source_provenance_stays(self):
        self.q.execute("UPDATE event_occurrences SET start_time='8pm' WHERE event_id=180336 AND start_date=%s", (OLD[0],))
        self.merge(2, [NEW])
        self.assertIn((OLD[0], '8pm', None, OLD[3]), [r[:4] for r in self.rows()])


if __name__ == '__main__':
    unittest.main()
