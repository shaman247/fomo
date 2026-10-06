"""Reject only redundant truncated records, never an actual undated program."""
import copy
import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import processor
import db


class RedundantStubTests(unittest.TestCase):
    def setUp(self):
        self.stub = dict(name='Book Discussion', location='', sublocation='',
                        occurrences=None, description='Discuss the book with other readers.',
                        url='https://library.test/node/', hashtags=['Literature'], emoji='📚')
        self.full = dict(self.stub, location='Neighborhood Library',
                         url='https://library.test/node/12345',
                         occurrences=[dict(start_date='2026-10-01', start_time='3pm',
                                           end_date=None, end_time='4pm')])
        self.content = f"[Book Discussion]({self.full['url']})"

    def check(self, events=None, content=None):
        rows = processor._parse_json_events(json.dumps({'events': events or [self.stub, self.full]}))
        before = copy.deepcopy(rows)
        result = processor._redundant_extraction_stub_urls(rows, self.content if content is None else content)
        self.assertEqual(rows, before)
        return result

    def test_truncated_and_zero_id_duplicates_keep_the_rich_dated_successor(self):
        for suffix in ('/node/', '/node/0', '/node/0/'):
            self.stub['url'] = 'https://library.test' + suffix
            with self.subTest(suffix=suffix):
                self.assertEqual(self.check(), {0: self.full['url']})

    def test_placeholder_body_and_punctuation_only_location(self):
        self.stub['location'] = ':'
        for value in ('', 'No description available.'):
            self.stub['description'] = self.full['description'] = value
            self.assertEqual(self.check(), {0: self.full['url']})

    def test_every_dated_occurrence_survives(self):
        self.full['occurrences'].append(dict(start_date='2026-10-08', start_time='5pm'))
        self.assertEqual(self.check(), {0: self.full['url']})

    def test_stub_with_any_date_clock_venue_or_room_survives(self):
        for key in ('start_date', 'start_time', 'end_date', 'end_time'):
            stub = dict(self.stub, occurrences=[{key: '2026-10-01' if 'date' in key else '3pm'}])
            with self.subTest(key=key):
                self.assertEqual(self.check([stub, self.full]), {})
        for key, value in [('location', 'Other Branch'), ('sublocation', 'Room A')]:
            self.assertEqual(self.check([dict(self.stub, **{key: value}), self.full]), {})

    def test_unique_metadata_is_not_lost(self):
        for key, value in [('name', 'Other Book Discussion'), ('description', 'Bring your own book.'),
                           ('hashtags', ['Literature', 'Virtual']), ('emoji', '💻'), ('sublocation', 'Online')]:
            with self.subTest(key=key):
                self.assertEqual(self.check([dict(self.stub, **{key: value}), self.full]), {})

    def test_unpaired_or_nonadjacent_undated_program_survives(self):
        self.assertEqual(self.check([self.stub]), {})
        self.assertEqual(self.check([self.stub, dict(self.full, name='Other'), self.full]), {})
        self.assertEqual(self.check([self.full, self.stub]), {})

    def test_complete_successor_requires_valid_date_and_venue(self):
        for changes in [dict(location=''), dict(location=':'), dict(occurrences=None),
                        dict(occurrences=[dict(start_date='2026-99-01')]),
                        dict(occurrences=[dict(start_date='2026-10-01', end_date='not a date')])]:
            with self.subTest(changes=changes):
                self.assertEqual(self.check([self.stub, dict(self.full, **changes)]), {})

    def test_only_same_host_numeric_child_without_query_is_eligible(self):
        for url in ('https://other.test/node/12345', 'https://library.test/other/12345',
                    'https://library.test/node/book-club', 'https://library.test/node/12345?session=2',
                    'https://library.test/node/12345#session', 'https://[invalid/node/12345'):
            with self.subTest(url=url):
                self.assertEqual(self.check([self.stub, dict(self.full, url=url)], f'[Event]({url})'), {})
        for url in ('https://library.test/', 'https://library.test/node/123',
                    'https://library.test/node/?session=2', 'https://library.test/node/#other'):
            self.assertEqual(self.check([dict(self.stub, url=url), self.full]), {})

    def test_source_must_show_complete_link_and_not_the_stub_itself(self):
        for content in ('', 'No link in this capture.', self.full['url'] + '6',
                        self.full['url'] + '?session=2',
                        self.content + f" [Other]({self.stub['url']})"):
            with self.subTest(content=content):
                self.assertEqual(self.check(content=content), {})
        self.stub['url'] += '0'
        self.assertEqual(self.check(content=self.content + f" [Real zero ID]({self.stub['url']})"), {})

    def test_generic_numeric_record_paths_and_legacy_table_work(self):
        self.stub['url'] = 'https://museum.test/programs/'
        self.full['url'] = 'https://museum.test/programs/12345'
        keys = ['name', 'location', 'sublocation', 'start_date', 'start_time', 'end_date',
                'end_time', 'description', 'url', 'hashtags', 'emoji']
        rows = processor._parse_json_events(json.dumps({'events': [self.stub, self.full]}))
        text = '| ' + ' | '.join(keys) + ' |\n| ' + ' | '.join(['---'] * len(keys)) + ' |\n'
        text += '\n'.join('| ' + ' | '.join(str(r.get(k) or '') for k in keys) + ' |' for r in rows)
        parsed = processor._parse_markdown_table(text)
        self.assertEqual(processor._redundant_extraction_stub_urls(parsed, f"<{self.full['url']}>"),
                         {0: self.full['url']})

    def test_processing_logs_stub_and_stores_only_the_complete_dated_record(self):
        cursor = mock.Mock(lastrowid=1, rowcount=0)
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = []
        extracted = json.dumps({'events': [self.stub, self.full]})
        with mock.patch.object(db, 'get_extracted_content', return_value=(extracted, 42)), \
                mock.patch.object(db, 'get_crawled_content', return_value=self.content), \
                mock.patch.object(db, 'update_crawl_result_processed'), \
                mock.patch.object(db, 'insert_crawl_event_occurrences') as occurrences, \
                mock.patch.object(processor, 'log_rejection') as rejection, \
                mock.patch.object(processor, 'get_location_id', return_value={'id': 123}) as location, \
                mock.patch.object(processor, 'get_active_date_window',
                                  return_value=(date(2026, 9, 26), date(2026, 12, 25))):
            count = processor.process_events(
                cursor, mock.Mock(), 456, 'Example Library', '20260926',
                locations_map={}, websites_map={}, tag_context=({}, {}, set(), []))

        self.assertEqual(count, 1)
        rejection.assert_called_once()
        self.assertEqual(rejection.call_args.kwargs['rejection_type'], 'redundant_extraction_stub')
        self.assertEqual(rejection.call_args.kwargs['event_url'], self.stub['url'])
        self.assertIn(self.full['url'], rejection.call_args.kwargs['details'])
        location.assert_called_once()
        self.assertEqual(location.call_args.args[0], self.full['location'])
        inserts = [call.args[1] for call in cursor.execute.call_args_list
                   if call.args[0].strip().startswith('INSERT INTO crawl_events')]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][8], self.full['url'])
        stored = json.loads(inserts[0][9])
        self.assertEqual(stored['description'], self.full['description'])
        self.assertEqual(stored['location_id'], 123)
        self.assertNotIn(self.stub['url'], stored['urls'])
        self.assertEqual(stored['occurrences'], [['2026-10-01', '3pm', '', '4pm']])
        occurrences.assert_called_once_with(cursor, 1, [('2026-10-01', '3pm', None, '4pm', 0)])


if __name__ == '__main__':
    unittest.main()
