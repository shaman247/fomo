"""Rejected long spans must retain an audit trail without changing eligibility."""
import contextlib
import io
import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import db
import processor


class DurationRejectionLoggingTests(unittest.TestCase):
    TODAY = date(2026, 9, 26)
    URL = 'https://example.org/events/guided-tours'

    def event(self, occurrences, **overrides):
        item = dict(name='Guided Tours', location='Art Center',
                    description='Guided visits to the art center.',
                    hashtags=['Art', 'Tour'], emoji='🖼️', url=self.URL,
                    occurrences=occurrences)
        item.update(overrides)
        return item

    def process(self, events):
        cursor = mock.Mock(lastrowid=1, rowcount=0)
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = []
        output = io.StringIO()
        with mock.patch.object(db, 'get_extracted_content',
                               return_value=(json.dumps({'events': events}), 42)), \
                mock.patch.object(db, 'get_crawled_content', return_value=self.URL), \
                mock.patch.object(db, 'update_crawl_result_processed'), \
                mock.patch.object(db, 'insert_crawl_event_occurrences') as insert, \
                mock.patch.object(processor, 'get_location_id', return_value={'id': 123}), \
                mock.patch.object(processor, 'get_active_date_window',
                                  return_value=(self.TODAY, self.TODAY + timedelta(days=90))), \
                contextlib.redirect_stdout(output):
            count = processor.process_events(
                cursor, mock.Mock(), 456, 'Art Center', '20260926',
                locations_map={}, websites_map={}, tag_context=({}, {}, set(), []))
        rejections = [call.args[1] for call in cursor.execute.call_args_list
                      if 'INSERT INTO extraction_rejections' in call.args[0]]
        return count, rejections, insert, output.getvalue()

    def test_actual_long_tour_shape_is_logged_with_source_and_dates(self):
        count, rows, insert, output = self.process([self.event([
            dict(start_date='2026-01-23', start_time='2pm',
                 end_date='2027-12-23', end_time='3pm')])])
        self.assertEqual(count, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][:8], (456, 42, 'duration_too_long', 'extract',
                                     'Guided Tours', self.URL, '2026-01-23', '2027-12-23'))
        insert.assert_not_called()
        self.assertIn('duration_too_long=1', output)

    def test_valid_sibling_occurrence_survives_one_rejected_span(self):
        count, rows, insert, _ = self.process([self.event([
            dict(start_date='2026-01-23', start_time='2pm', end_date='2027-12-23'),
            dict(start_date='2026-10-01', start_time='2pm', end_time='3pm')])])
        self.assertEqual(count, 1)
        self.assertEqual([row[2] for row in rows], ['duration_too_long'])
        insert.assert_called_once()
        self.assertEqual(insert.call_args.args[2][0][:4],
                         ('2026-10-01', '2pm', None, '3pm'))

    def test_explicit_untimed_exhibition_remains_eligible_without_rejection(self):
        count, rows, insert, _ = self.process([self.event([
            dict(start_date='2025-03-07', end_date='2026-10-12')],
            name='Long Exhibition', hashtags=['Art', 'Exhibition'])])
        self.assertEqual(count, 1)
        self.assertEqual(rows, [])
        self.assertEqual(insert.call_args.args[2][0][:4],
                         ('2025-03-07', '', '2026-10-12', ''))

    def test_400_day_boundary_keeps_only_the_eligible_span(self):
        events = [self.event([dict(start_date=(self.TODAY - timedelta(days=days)).isoformat(),
                                  start_time='2pm', end_date=self.TODAY.isoformat())],
                             name=f'Tour {days}') for days in (400, 401)]
        count, rows, insert, _ = self.process(events)
        self.assertEqual(count, 1)
        self.assertEqual([(row[2], row[4]) for row in rows],
                         [('duration_too_long', 'Tour 401')])
        insert.assert_called_once()


if __name__ == '__main__':
    unittest.main()
