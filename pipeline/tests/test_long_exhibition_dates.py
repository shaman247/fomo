"""Explicit exhibition runs must not be mistaken for malformed long sessions."""
import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from processor import _parse_json_events, filter_by_date, group_event_occurrences


class LongExhibitionDatesTests(unittest.TestCase):
    TODAY = date(2026, 9, 20)
    LIMIT = TODAY + timedelta(days=90)

    def row(self, **overrides):
        row = {'name': 'An exhibition', 'start_date': '2025-03-07',
               'end_date': '2026-10-12', 'start_time': '', 'end_time': '',
               'hashtags': ['Art', 'Exhibition']}
        row.update(overrides)
        return row

    def check(self, row, expected=(True, None)):
        self.assertEqual(filter_by_date(row, self.TODAY, self.LIMIT), expected)

    def test_explicit_long_exhibition_keeps_both_dates(self):
        row = self.row()
        original = dict(row)
        self.check(row)
        self.assertEqual(row, original)

    def test_exhibition_tag_variants_and_processed_tags(self):
        for field in ('hashtags', 'tags'):
            for tags in (['Exhibition'], [' Exhibits '], 'Art, exhibition', ['EXHIBITIONS']):
                with self.subTest(field=field, tags=tags):
                    row = self.row(hashtags=[])
                    row[field] = tags
                    self.check(row)

    def test_broad_art_and_gallery_tags_do_not_exempt_long_sessions(self):
        for tags in ([], ['Art'], ['Gallery'], ['Installation'], ['Concert']):
            self.check(self.row(hashtags=tags), (False, 'duration_too_long'))

    def test_timed_exhibition_sessions_keep_duration_guard(self):
        for field in ('start_time', 'end_time'):
            self.check(self.row(**{field: '2pm'}), (False, 'duration_too_long'))

    def test_closing_only_does_not_turn_synthetic_opening_into_explicit_span(self):
        for opening in (None, '', '  '):
            self.check(self.row(start_date=opening, end_date='2035-04-25'),
                       (False, 'duration_too_long'))

    def test_opening_only_keeps_stale_date_guard(self):
        self.check(self.row(end_date=None), (False, 'duration_too_long'))

    def test_closed_exhibitions_stay_rejected(self):
        self.check(self.row(end_date='2026-09-19'), (False, 'end_in_past'))

    def test_future_openings_outside_window_stay_rejected(self):
        self.check(self.row(start_date='2027-01-01', end_date='2029-01-01'),
                   (False, 'start_too_future'))

    def test_invalid_explicit_dates_stay_rejected(self):
        for field in ('start_date', 'end_date'):
            self.check(self.row(**{field: '2026-02-30'}), (False, 'invalid_date'))

    def test_duration_boundary_unchanged_for_other_events(self):
        for days, expected in ((400, (True, None)), (401, (False, 'duration_too_long'))):
            self.check(self.row(start_date=(self.TODAY - timedelta(days=days)).isoformat(),
                                end_date=self.TODAY.isoformat(), hashtags=['Festival']), expected)

    def test_parser_and_grouping_preserve_source_confirmed_span(self):
        source = {'events': [{'name': 'Renée Green: The Equator Has Moved',
                             'location': 'Museum', 'hashtags': ['Art', 'Exhibition'],
                             'url': 'https://example.org/exhibition/renee-green',
                             'occurrences': [{'start_date': '2025-03-07',
                                              'end_date': '2026-10-12'}]}]}
        rows = _parse_json_events(json.dumps(source))
        self.check(rows[0])
        rows[0]['tags'] = rows[0].pop('hashtags')
        grouped = group_event_occurrences(rows, source['events'][0]['url'])
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]['occurrences'],
                         [['2025-03-07', '', '2026-10-12', '']])


if __name__ == '__main__':
    unittest.main()
