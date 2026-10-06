"""A complete duplicate must not turn an empty calendar stub into session prose."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from processor import group_event_occurrences
from session_details import preserve_session_details


class PlaceholderDetailsTests(unittest.TestCase):
    def row(self, description='No description available.', **changes):
        row = dict(name='Concert', location='Concert Hall', location_id=17,
                   sublocation='Main Room', description=description,
                   start_date='2026-10-01', start_time='7pm', end_date='',
                   end_time='', url='https://example.org/events/concert/',
                   tags=['Music'], emoji='🎵')
        row.update(changes)
        return row

    def preserve(self, rows):
        original = copy.deepcopy(rows)
        event = dict(description=rows[0]['description'],
                     occurrences=[['2026-10-01', '7pm', '', '']],
                     urls=['https://example.org/events/concert/'],
                     location_id=17, tags=['Music'], emoji='🎵')
        untouched = {k: copy.deepcopy(v) for k, v in event.items()
                     if k != 'description'}
        preserve_session_details(event, rows)
        self.assertEqual(rows, original)
        for key, value in untouched.items():
            self.assertEqual(event[key], value, key)
        return event

    def test_complete_duplicate_replaces_placeholder_in_either_order(self):
        for placeholder in (None, '', '   ', 'No description available.',
                            ' NO   DESCRIPTION\nAVAILABLE. '):
            for reverse in (False, True):
                with self.subTest(placeholder=placeholder, reverse=reverse):
                    rows = [self.row(placeholder), self.row('A jazz trio performs.')]
                    if reverse:
                        rows.reverse()
                    event = self.preserve(rows)
                    self.assertEqual(event['description'], 'A jazz trio performs.')
                    self.assertNotIn('session_details', event)

    def test_actual_grouper_keeps_slots_and_urls_in_either_order(self):
        rows = [self.row(), self.row('A jazz trio performs.')]
        for ordered in (rows, list(reversed(rows))):
            event, = group_event_occurrences(copy.deepcopy(ordered))
            self.assertEqual(event['description'], 'A jazz trio performs.')
            self.assertEqual(event['occurrences'], [['2026-10-01', '7pm', '', '']])
            self.assertEqual(event['urls'], ['https://example.org/events/concert/'])
            self.assertNotIn('session_details', event)

    def test_different_session_evidence_is_not_discarded(self):
        differences = [dict(start_date='2026-10-02'), dict(start_time='8pm'),
                       dict(end_date='2026-10-02'), dict(end_time='9pm'),
                       dict(sublocation='Balcony'), dict(location='Other Hall'),
                       dict(location_id=18),
                       dict(url='https://example.org/events/other/')]
        for difference in differences:
            with self.subTest(difference=difference):
                event = self.preserve([self.row(**difference),
                                       self.row('Tickets are $20.')])
                self.assertIn('No description available.', event['description'])
                self.assertIn('Tickets are $20.', event['description'])
                self.assertEqual(len(event['session_details']), 2)

    def test_missing_url_date_or_start_time_cannot_prove_duplicate(self):
        for field in ('url', 'start_date', 'start_time'):
            for value in ('', None):
                with self.subTest(field=field, value=value):
                    event = self.preserve([self.row(**{field: value}),
                                           self.row('Registration required.', **{field: value})])
                    self.assertIn('No description available.', event['description'])
                    self.assertEqual(len(event['session_details']), 2)

    def test_only_covered_date_is_removed_from_placeholder_variant(self):
        rows = [self.row(), self.row(start_date='2026-10-02'),
                self.row('A jazz trio performs.')]
        event, = group_event_occurrences(copy.deepcopy(rows))
        self.assertEqual(event['occurrences'], [
            ['2026-10-01', '7pm', '', ''], ['2026-10-02', '7pm', '', '']])
        placeholder, = [v for v in event['session_details']
                         if v['description'] == 'No description available.']
        self.assertEqual([s['start_date'] for s in placeholder['sessions']],
                         ['2026-10-02'])
        substantive, = [v for v in event['session_details']
                         if v['description'] == 'A jazz trio performs.']
        self.assertEqual([s['start_date'] for s in substantive['sessions']],
                         ['2026-10-01'])
        self.assertEqual(event['urls'], ['https://example.org/events/concert/'])

    def test_distinct_nonempty_end_times_and_spans_remain(self):
        for later in (dict(end_time='10pm', end_date='2026-10-02'),
                      dict(end_time='9pm', end_date='2026-10-03')):
            rows = [self.row(end_time='9pm', end_date='2026-10-02'),
                    self.row('A two-day program.', **later)]
            event = self.preserve(rows)
            self.assertEqual(len(event['session_details']), 2)
            self.assertIn('through 2026-10-02', event['description'])
            self.assertIn('No description available.', event['description'])

    def test_conflicting_substantive_prose_survives_with_own_sessions(self):
        rows = [self.row(), self.row('Adults only; tickets $20.'),
                self.row('All ages; admission is free.')]
        for ordered in (rows, list(reversed(rows))):
            event = self.preserve(ordered)
            self.assertNotIn('No description available.', event['description'])
            self.assertIn('Adults only; tickets $20.', event['description'])
            self.assertIn('All ages; admission is free.', event['description'])
            self.assertEqual(len(event['session_details']), 2)
            self.assertTrue(all(v['sessions'][0]['start_date'] == '2026-10-01'
                                for v in event['session_details']))

    def test_all_placeholders_and_single_placeholder_stay_unchanged(self):
        for rows in ([self.row()], [self.row(), self.row()],
                     [self.row(''), self.row()]):
            event = self.preserve(rows)
            if rows[0]['description']:
                self.assertEqual(event['description'], 'No description available.')
            else:
                self.assertIn('No description available.', event['description'])
                self.assertEqual(len(event['session_details']), 2)

    def test_placeholder_phrase_with_real_notice_is_not_empty(self):
        text = 'No description available. Tickets $20; wheelchair access at side door.'
        event = self.preserve([self.row(text), self.row('Registration required.')])
        self.assertIn(text, event['description'])
        self.assertEqual(len(event['session_details']), 2)


if __name__ == '__main__':
    unittest.main()
