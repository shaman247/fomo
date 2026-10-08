"""BL12: publisher all-day evidence and full-day placeholder retirement.

Pure tests run everywhere. The merge tests use connection-local TEMPORARY
tables and only run with FOMO_TEST_TEMP_DB=1; no production rows are touched.
"""
import json
import os
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import occurrence_provenance as op  # noqa: E402

URL = 'https://publisher.example/event/first-friday-37/'


def block(title, url, all_day, lines, venues=('Poster House',), meta_title=None):
    meta = {'title': meta_title or title, 'all_day': all_day, 'timezone': 'America/New_York',
            'venues': [{'venue': v} for v in venues]}
    parts = [f'### [{title}]({url})', json.dumps(meta), op.GRAMMAR_HEADER]
    parts += [f'- {s} / {e} / {u} / {i}' for s, e, u, i in lines]
    return '\n\n'.join(parts)


def page(*blocks):
    return '\n\n'.join(['https://publisher.example/events/',
                        '# Complete upcoming calendar from the official Tribe API',
                        'An explicit all_day=true means no clock time.'] + list(blocks))


ALL_DAY = block('First Friday', URL, True,
                [('2026-10-02 00:00:00', '2026-10-02 23:59:59', URL, '112688')])
CAPTURE = dict(crawl_result_id=126404, observed_at='2026-09-22 18:38:40')


def event(name='First Friday', occurrences=None, urls=(URL,)):
    return dict(name=name, urls=list(urls),
                occurrences=[list(o) for o in (occurrences or [['2026-10-02', '', '', '']])])


def bind(content, ev):
    return op.bind_event(ev, op.index_records(op.parse_explicit_records(content)), CAPTURE)


class GrammarTests(unittest.TestCase):
    def test_parses_exact_records(self):
        records = op.parse_explicit_records(page(ALL_DAY))
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual((r['record_id'], r['all_day'], r['start_date'], r['end_date']),
                         ('112688', True, '2026-10-02', '2026-10-02'))
        self.assertEqual(len(r['sha256']), 64)

    def test_string_numeric_and_null_flags_are_unknown(self):
        for flag in ('true', 1, None):
            content = page(block('First Friday', URL, flag,
                                 [('2026-10-02 00:00:00', '2026-10-02 23:59:59', URL, '1')]))
            self.assertIsNone(op.parse_explicit_records(content)[0]['all_day'])

    def test_metadata_title_mismatch_and_bad_json_are_unknown(self):
        content = page(block('First Friday', URL, True,
                             [('2026-10-02 00:00:00', '2026-10-02 23:59:59', URL, '1')],
                             meta_title='Another Event'))
        self.assertIsNone(op.parse_explicit_records(content)[0]['all_day'])
        broken = page(ALL_DAY).replace('"all_day": true', '"all_day": true,,')
        self.assertIsNone(op.parse_explicit_records(broken)[0]['all_day'])

    def test_free_text_phrase_is_not_evidence(self):
        self.assertEqual(op.parse_explicit_records('Event all_day=true\n\nOct 2, 12:00 AM'), [])


class BindingTests(unittest.TestCase):
    def test_true_with_blank_clocks_records_entry(self):
        ev = event()
        sidecar = bind(page(ALL_DAY), ev)
        self.assertEqual(ev['occurrences'], [['2026-10-02', '', '', '']])
        entry = sidecar['entries'][0]
        self.assertIs(entry['all_day'], True)
        self.assertEqual(entry['slot'], ['2026-10-02', '', '', ''])
        self.assertEqual((entry['source_record_id'], entry['evidence_capture_id']),
                         ('112688', 126404))
        self.assertEqual(entry['evidence_observed_at'], '2026-09-22 18:38:40')

    def test_true_with_boundary_clocks_normalizes_to_blank(self):
        for clocks in (('12am', '11:59pm'), ('00:00', '23:59'), ('12:00 AM', '11:59:59 PM')):
            ev = event(occurrences=[['2026-10-02', clocks[0], '', clocks[1]]])
            sidecar = bind(page(ALL_DAY), ev)
            self.assertEqual(ev['occurrences'], [['2026-10-02', '', '', '']], clocks)
            self.assertEqual(sidecar['entries'][0]['slot'], ['2026-10-02', '', '', ''])

    def test_true_with_substantive_clock_keeps_clock_and_flags_conflict(self):
        ev = event(occurrences=[['2026-10-02', '7pm', '', '9pm']])
        sidecar = bind(page(ALL_DAY), ev)
        self.assertEqual(ev['occurrences'], [['2026-10-02', '7pm', '', '9pm']])
        self.assertEqual(sidecar['entries'], [])
        self.assertEqual(sidecar['conflicts'][0]['reason'], 'all_day_vs_clock')

    def test_false_flag_protects_real_midnight(self):
        content = page(block('Late Set', URL, False,
                             [('2026-10-02 00:00:00', '2026-10-02 03:00:00', URL, '9')]))
        ev = event('Late Set', [['2026-10-02', '12am', '', '3am']])
        sidecar = bind(content, ev)
        self.assertEqual(ev['occurrences'], [['2026-10-02', '12am', '', '3am']])
        self.assertIs(sidecar['entries'][0]['all_day'], False)

    def test_missing_flag_with_boundary_clock_stays_timed(self):
        content = page(block('First Friday', URL, None,
                             [('2026-10-02 00:00:00', '2026-10-02 23:59:59', URL, '1')]))
        ev = event(occurrences=[['2026-10-02', '12am', '', '11:59pm']])
        sidecar = bind(content, ev)
        self.assertEqual(ev['occurrences'], [['2026-10-02', '12am', '', '11:59pm']])
        self.assertEqual(sidecar['entries'], [])

    def test_child_program_sharing_the_url_does_not_inherit(self):
        content = page(block('The Art Guild presents 2026 Student Juried Art Competition', URL, True,
                             [('2026-10-13 00:00:00', '2026-10-13 23:59:59', URL, '5')]))
        ev = event('2026 Student Juried Art Competition: Awards & Reception',
                   [['2026-10-13', '12am', '', '11:59pm']])
        sidecar = bind(content, ev)
        self.assertEqual(ev['occurrences'][0][1], '12am')
        self.assertEqual(sidecar['conflicts'][0]['reason'], 'title_mismatch')

    def test_neighboring_dates_and_other_urls_do_not_bind(self):
        ev = event(occurrences=[['2026-10-03', '12am', '', '11:59pm']])
        self.assertIsNone(bind(page(ALL_DAY), ev))
        ev = event(urls=['https://publisher.example/event/first-friday-38/'],
                   occurrences=[['2026-10-02', '12am', '', '11:59pm']])
        self.assertIsNone(bind(page(ALL_DAY), ev))
        self.assertEqual(ev['occurrences'][0][1], '12am')

    def test_multiday_span_binds_only_as_exact_span(self):
        url = 'https://publisher.example/events/retreat/'
        content = page(block('Member Retreat', url, True,
                             [('2026-10-16 00:00:00', '2026-10-18 23:59:59', url, '57')]))
        span = event('Member Retreat', [['2026-10-16', '12am', '2026-10-18', '11:59pm']], (url,))
        bind(content, span)
        self.assertEqual(span['occurrences'], [['2026-10-16', '', '2026-10-18', '']])
        daily = event('Member Retreat', [['2026-10-16', '12am', '', '11:59pm'],
                                         ['2026-10-17', '12am', '', '11:59pm']], (url,))
        self.assertIsNone(bind(content, daily))
        self.assertEqual(daily['occurrences'][0][1], '12am')

    def test_mixed_event_keeps_per_occurrence_evidence(self):
        url2 = 'https://publisher.example/event/first-friday-38/'
        content = page(ALL_DAY, block('First Friday', url2, False,
                                      [('2026-11-06 18:00:00', '2026-11-06 21:00:00', url2, '7')]))
        ev = event(occurrences=[['2026-10-02', '12am', '', '11:59pm'], ['2026-11-06', '6pm', '', '9pm']],
                   urls=(URL, url2))
        sidecar = bind(content, ev)
        self.assertEqual(ev['occurrences'], [['2026-10-02', '', '', ''], ['2026-11-06', '6pm', '', '9pm']])
        self.assertEqual({(e['slot'][0], e['all_day']) for e in sidecar['entries']},
                         {('2026-10-02', True), ('2026-11-06', False)})

    def test_contradictory_duplicate_records_are_ambiguous(self):
        content = page(ALL_DAY, block('First Friday', URL, False,
                                      [('2026-10-02 00:00:00', '2026-10-02 23:59:59', URL, '999')]))
        ev = event(occurrences=[['2026-10-02', '12am', '', '11:59pm']])
        sidecar = bind(content, ev)
        self.assertEqual(ev['occurrences'][0][1], '12am')
        self.assertEqual(sidecar['conflicts'][0]['reason'], 'ambiguous_records')

    def test_rebinding_is_deterministic(self):
        first, second = event(occurrences=[['2026-10-02', '12am', '', '11:59pm']]), event()
        self.assertEqual(bind(page(ALL_DAY), first), bind(page(ALL_DAY), second))


class DetailResyncTests(unittest.TestCase):
    def raw(self):
        ev = event()
        bind(page(ALL_DAY), ev)
        return json.dumps(ev)

    def test_same_slot_survives_and_boundary_is_blanked(self):
        raw, rows = op.resync_after_detail(self.raw(), [('2026-10-02', '12am', None, '11:59pm')])
        self.assertEqual(rows, [('2026-10-02', '', None, '')])
        self.assertEqual(len(op.sidecar_from_raw(raw)['entries']), 1)

    def test_newer_clock_or_changed_date_supersedes_the_claim(self):
        for detail in ([('2026-10-02', '7pm', None, '9pm')], [('2026-10-09', '', None, '')]):
            raw, rows = op.resync_after_detail(self.raw(), detail)
            self.assertEqual(rows, detail)
            sidecar = op.sidecar_from_raw(raw)
            self.assertEqual(sidecar['entries'], [])
            self.assertEqual(len(sidecar['superseded']), 1)

    def test_no_sidecar_is_a_no_op(self):
        rows = [('2026-10-02', '12am', None, '11:59pm')]
        self.assertEqual(op.resync_after_detail(json.dumps({'name': 'x'}), rows), (None, rows))


D = date(2026, 10, 18)
PH = (D, '12am', None, '11:59pm')
BLANK = (D, '', None, '')
OLD, NEW = datetime(2026, 8, 2), datetime(2026, 10, 3)


def src(occ, observed, website=593, url='https://club.example/event/crisp-autumn/', sidecar=None):
    return dict(website_id=website, url=url, observed_at=observed, occurrences=list(occ),
                sidecar=sidecar)


def key(u):
    return (u or '').rstrip('/').lower()


class RetirementPlanTests(unittest.TestCase):
    def plan(self, rows, sources):
        return op.plan_placeholder_retirement(rows, sources, key)

    def test_same_page_newer_blank_retires_placeholder(self):
        plan, _ = self.plan([PH], [src([PH], OLD), src([BLANK], NEW)])
        self.assertEqual(plan, {('2026-10-18', None): 'blank'})

    def test_existing_blank_twin_drops_placeholder(self):
        plan, _ = self.plan([PH, BLANK], [src([PH], OLD), src([BLANK], NEW)])
        self.assertEqual(plan, {('2026-10-18', None): 'drop'})

    def test_other_clocked_session_keeps_session_and_drops_placeholder(self):
        session = (D, '9:30am', None, '')
        plan, _ = self.plan([PH, session], [src([PH], OLD), src([BLANK], NEW),
                                            src([session], NEW, website=9, url='https://o.example/')])
        self.assertEqual(plan, {('2026-10-18', None): 'drop'})

    def test_vetoes(self):
        cases = {
            'placeholder_is_newest': ([PH], [src([BLANK], OLD), src([PH], NEW)]),
            'no_owner': ([PH], [src([BLANK], NEW)]),
            'mixed_owners': ([PH], [src([PH], OLD), src([PH], OLD, website=9), src([BLANK], NEW)]),
            'unknown_chronology': ([PH], [src([PH], None), src([BLANK], NEW)]),
            'newest_not_blank': ([PH], [src([PH], OLD), src([BLANK], NEW), src([(D, '8am', None, '')], NEW)]),
        }
        for reason, (rows, sources) in cases.items():
            plan, vetoes = self.plan(rows, sources)
            self.assertEqual(plan, {}, reason)
            self.assertEqual(vetoes, {('2026-10-18', None): reason}, reason)

    def test_independent_publisher_blank_does_not_retire(self):
        plan, vetoes = self.plan([PH], [src([PH], OLD), src([BLANK], NEW, website=9,
                                                            url='https://other.example/x')])
        self.assertEqual(plan, {})
        self.assertEqual(vetoes[('2026-10-18', None)], 'placeholder_is_newest')

    def test_explicit_false_vetoes(self):
        sidecar = {'version': 1, 'entries': [{'slot': ['2026-10-18', '12am', '', '11:59pm'],
                                              'all_day': False}]}
        plan, vetoes = self.plan([PH], [src([PH], OLD, sidecar=sidecar), src([BLANK], NEW)])
        self.assertEqual((plan, vetoes[('2026-10-18', None)]), ({}, 'explicit_false'))

    def test_real_midnight_and_partial_midnight_untouched(self):
        for row in ((D, '12am', None, '3am'), (D, '12am', None, '')):
            plan, vetoes = self.plan([row], [src([row], OLD), src([BLANK], NEW)])
            self.assertEqual((plan, vetoes), ({}, {}))

    def test_multiday_span(self):
        span = (date(2026, 10, 22), '12am', date(2026, 11, 22), '11:59pm')
        blank = (date(2026, 10, 22), '', date(2026, 11, 22), '')
        plan, _ = self.plan([span], [src([span], OLD), src([blank], NEW)])
        self.assertEqual(plan, {('2026-10-22', '2026-11-22'): 'blank'})


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1',
                     'Opt in to connection-local MariaDB tables with FOMO_TEST_TEMP_DB=1')
class MergeWriteTests(unittest.TestCase):
    """Matched-merge path and replay order on connection-local tables."""

    def setUp(self):
        from db import create_connection
        from merger import _merge_occurrences_into_event
        self.merge = _merge_occurrences_into_event
        self.conn = create_connection()
        self.assertIsNotNone(self.conn)
        self.addCleanup(self.conn.close)
        self.q = self.conn.cursor()
        schemas = {
            'events': 'id INT, event_type VARCHAR(40), location_id INT, suppressed INT DEFAULT 0',
            'event_occurrences': ('id INT AUTO_INCREMENT PRIMARY KEY, event_id INT, start_date DATE, '
                                  'start_time VARCHAR(20), end_date DATE, end_time VARCHAR(20), '
                                  'sort_order INT DEFAULT 0'),
            'crawl_events': 'id INT, crawl_result_id INT, location_id INT, url VARCHAR(255), raw_data TEXT',
            'crawl_results': 'id INT, website_id INT, crawled_at DATETIME, processed_at DATETIME',
            'event_sources': 'event_id INT, crawl_event_id INT',
            'crawl_event_occurrences': ('crawl_event_id INT, start_date DATE, start_time VARCHAR(20), '
                                        'end_date DATE, end_time VARCHAR(20)'),
        }
        for name, schema in schemas.items():
            self.q.execute(f'CREATE TEMPORARY TABLE {name} ({schema})')
        self.q.execute("CREATE TEMPORARY TABLE websites AS SELECT 593 AS id, 'primary' AS source_type")
        self.q.execute("INSERT INTO events VALUES (1, 'Tour', 5, 0)")
        self.q.execute("INSERT INTO crawl_results VALUES (1, 593, '2026-08-02', '2026-08-02'), "
                       "(2, 593, '2026-10-03', '2026-10-03')")
        url = 'https://club.example/event/crisp-autumn/'
        self.q.execute('INSERT INTO crawl_events VALUES (11, 1, 5, %s, NULL), (12, 2, 5, %s, NULL)',
                       (url, url))
        self.q.execute('INSERT INTO crawl_event_occurrences VALUES (11, %s, %s, NULL, %s), '
                       "(12, %s, '', NULL, '')", (D, '12am', '11:59pm', D))

    def rows(self):
        self.q.execute('SELECT start_date, start_time, end_date, end_time FROM event_occurrences '
                       'WHERE event_id = 1 ORDER BY start_date, start_time')
        return [tuple(r) for r in self.q.fetchall()]

    def test_newer_blank_retires_then_old_replay_cannot_restore(self):
        self.q.execute('INSERT INTO event_sources VALUES (1, 11)')
        self.merge(self.q, 1, [PH], crawl_event_id=11)
        self.assertEqual(self.rows(), [(D, '12am', None, '11:59pm')])
        rows = self.merge(self.q, 1, [BLANK], crawl_event_id=12)
        self.assertEqual(self.rows(), [(D, '', None, '')])
        self.assertIsNotNone(rows)
        self.q.execute('INSERT INTO event_sources VALUES (1, 12)')
        for _ in range(2):
            self.merge(self.q, 1, [PH], crawl_event_id=11)
            self.assertEqual(self.rows(), [(D, '', None, '')])
        self.q.execute('SELECT COUNT(*) FROM crawl_event_occurrences')
        self.assertEqual(self.q.fetchone()[0], 2)

    def test_explicit_false_source_demotes_blank(self):
        sidecar = {'version': 1, 'entries': [{'slot': ['2026-10-18', '12am', '', '11:59pm'],
                                              'all_day': False}]}
        self.q.execute('UPDATE crawl_events SET raw_data = %s WHERE id = 11',
                       (json.dumps({'occurrence_provenance': sidecar}),))
        self.merge(self.q, 1, [BLANK], crawl_event_id=12)
        self.merge(self.q, 1, [PH], crawl_event_id=11)
        self.assertEqual(self.rows(), [(D, '12am', None, '11:59pm')])

    def test_independent_timed_session_is_never_erased(self):
        self.q.execute("INSERT INTO event_occurrences (event_id, start_date, start_time, end_date, end_time) "
                       "VALUES (1, %s, '7pm', NULL, '9pm')", (D,))
        self.merge(self.q, 1, [BLANK], crawl_event_id=12)
        self.assertEqual(self.rows(), [(D, '7pm', None, '9pm')])


    # --- open-run horizon spans -------------------------------------------
    OPEN = date(2026, 4, 23)

    def horizon_source(self, ce, cr, crawled, end, marked):
        raw = None
        if marked:
            raw = json.dumps({op.PROVENANCE_KEY: {'version': 1, 'entries': [], 'endpoints': [
                {'slot': [str(self.OPEN), '', str(end), ''], 'kind': op.END_OPEN_RUN_HORIZON}]}})
        self.q.execute('INSERT INTO crawl_results VALUES (%s, 62, %s, %s)', (cr, crawled, crawled))
        self.q.execute('INSERT INTO crawl_events VALUES (%s, %s, 5, %s, %s)',
                       (ce, cr, 'https://museum.example/exhibitions/5907', raw))
        self.q.execute("INSERT INTO crawl_event_occurrences VALUES (%s, %s, '', %s, '')",
                       (ce, self.OPEN, end))

    def spans(self):
        return [r[2] for r in self.rows() if r[0] == self.OPEN]

    def test_newer_horizon_supersedes_legacy_horizon_and_replay_is_skipped(self):
        self.horizon_source(21, 21, '2026-09-17', date(2026, 11, 16), marked=False)  # legacy +60
        self.horizon_source(22, 22, '2026-09-26', date(2026, 11, 25), marked=True)
        self.q.execute('INSERT INTO event_sources VALUES (1, 21)')
        self.merge(self.q, 1, [(self.OPEN, '', date(2026, 11, 16), '')], crawl_event_id=21)
        self.merge(self.q, 1, [(self.OPEN, '', date(2026, 11, 25), '')], crawl_event_id=22)
        self.assertEqual(self.spans(), [date(2026, 11, 25)])
        self.q.execute('INSERT INTO event_sources VALUES (1, 22)')
        self.merge(self.q, 1, [(self.OPEN, '', date(2026, 11, 16), '')], crawl_event_id=21)
        self.assertEqual(self.spans(), [date(2026, 11, 25)])

    def test_published_end_is_kept_and_covers_a_shorter_horizon(self):
        self.horizon_source(23, 23, '2026-07-29', date(2026, 12, 31), marked=False)  # +155: published
        self.horizon_source(21, 21, '2026-09-17', date(2026, 11, 16), marked=False)
        self.horizon_source(22, 22, '2026-09-26', date(2026, 11, 25), marked=True)
        self.q.execute('INSERT INTO event_sources VALUES (1, 21), (1, 23)')
        for ce, end in ((23, date(2026, 12, 31)), (21, date(2026, 11, 16)), (22, date(2026, 11, 25))):
            self.merge(self.q, 1, [(self.OPEN, '', end, '')], crawl_event_id=ce)
        self.assertEqual(self.spans(), [date(2026, 12, 31)])

    def test_published_span_never_deletes_a_horizon(self):
        self.horizon_source(21, 21, '2026-09-17', date(2026, 11, 16), marked=False)
        self.horizon_source(23, 23, '2026-09-26', date(2026, 12, 31), marked=False)
        self.q.execute('INSERT INTO event_sources VALUES (1, 21)')
        self.merge(self.q, 1, [(self.OPEN, '', date(2026, 11, 16), '')], crawl_event_id=21)
        self.merge(self.q, 1, [(self.OPEN, '', date(2026, 12, 31), '')], crawl_event_id=23)
        self.assertEqual(sorted(self.spans()), [date(2026, 11, 16), date(2026, 12, 31)])


class SynthesizedEndpointTests(unittest.TestCase):
    def test_marks_follow_surviving_slots_only(self):
        ev = event(occurrences=[['2026-04-23', '', '2026-11-25', ''], ['2026-10-02', '7pm', '', '']])
        op.record_synthesized_endpoints(ev, [(['2026-04-23', '', '2026-11-25', ''], op.END_OPEN_RUN_HORIZON),
                                             (['2026-05-01', '', '2026-11-25', ''], op.END_OPEN_RUN_HORIZON)])
        self.assertEqual(op.endpoint_slots(ev[op.PROVENANCE_KEY], op.END_OPEN_RUN_HORIZON),
                         {('2026-04-23', '2026-11-25')})
        # A later all-day binding keeps the endpoint marks.
        bind(page(ALL_DAY), ev)
        self.assertIn('endpoints', ev[op.PROVENANCE_KEY])

    def test_processor_marks_and_grouping_carries_them(self):
        from datetime import timedelta
        import processor
        today = date(2026, 10, 7)
        row = dict(name='Show', start_date='2026-04-23', end_date='', hashtags=['Exhibition'],
                   url='https://museum.example/x')
        self.assertEqual(processor.filter_by_date(row, today, today + timedelta(days=90)), (True, None))
        self.assertEqual(row['end_date'], '2026-12-06')
        self.assertEqual(row[processor.SYNTHESIZED_ENDPOINT_KEY], op.END_OPEN_RUN_HORIZON)
        closing = dict(name='Other', start_date='', end_date='2026-11-01', url='https://museum.example/y')
        processor.filter_by_date(closing, today, today + timedelta(days=90))
        self.assertEqual(closing[processor.SYNTHESIZED_ENDPOINT_KEY], op.START_AS_OF_CRAWL)
        events = processor.group_event_occurrences([row, closing], 'https://museum.example/')
        class Cursor:
            def execute(self, *a): pass
            def fetchone(self): return None
        processor._annotate_occurrence_provenance(Cursor(), 1, '', events)
        by_name = {e['name']: e for e in events}
        self.assertNotIn(processor.SYNTHESIZED_ENDPOINT_KEY, by_name['Show'])
        self.assertEqual(op.endpoint_slots(by_name['Show'][op.PROVENANCE_KEY], op.END_OPEN_RUN_HORIZON),
                         {('2026-04-23', '2026-12-06')})
        self.assertEqual(op.endpoint_slots(by_name['Other'][op.PROVENANCE_KEY], op.START_AS_OF_CRAWL),
                         {('2026-10-07', '2026-11-01')})
        json.dumps(events)  # raw_data stays serializable

    def test_detail_resync_records_its_own_synthesized_endpoint(self):
        raw, rows = op.resync_after_detail(json.dumps({'name': 'x'}),
                                           [('2026-10-07', '', '2026-11-01', '')],
                                           [(('2026-10-07', '', '2026-11-01', ''), op.START_AS_OF_CRAWL)])
        self.assertEqual(op.endpoint_slots(op.sidecar_from_raw(raw), op.START_AS_OF_CRAWL),
                         {('2026-10-07', '2026-11-01')})


if __name__ == '__main__':
    unittest.main()
