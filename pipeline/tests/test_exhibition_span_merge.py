"""Closing-only exhibition recrawls must not grow a span per crawl day."""
import unittest
from datetime import date

from pipeline.tests import test_merger as fixtures
import merger


class ExhibitionSpanMergeTests(unittest.TestCase):
    class Cursor(fixtures.BareClockTwinTests.FakeCursor):
        def __init__(self, rows, event_type):
            super().__init__(rows)
            self.event_type = event_type
            self.type_reads = 0

        def execute(self, sql, params=None):
            if sql.startswith('SELECT event_type'):
                self.type_reads += 1
                self._result = [(self.event_type,)]
            elif sql.startswith('DELETE') and 'end_time IS NULL' in sql:
                _, sd, ed = params
                self.rows = [r for r in self.rows
                             if not (r[0] == sd and not r[1] and r[2] == ed and not r[3])]
            else:
                super().execute(sql, params)

    START = date(2025, 4, 8)
    TODAY = date(2026, 9, 20)
    END = date(2027, 2, 21)

    def merge(self, existing, incoming, event_type='Exhibition'):
        cursor = self.Cursor(existing, event_type)
        merger._merge_occurrences_into_event(cursor, 76696, incoming)
        return cursor

    def test_closing_only_recrawl_keeps_known_opening(self):
        original = (self.START, '', self.END, '')
        cursor = self.merge([original], [(self.TODAY, '', self.END, '')])
        self.assertEqual(cursor.rows, [original])

    def test_known_opening_replaces_later_synthetic_opening(self):
        original = (self.START, '', self.END, '')
        cursor = self.merge([(self.TODAY, '', self.END, '')], [original])
        self.assertEqual(cursor.rows, [original])

    def test_repeated_new_spans_read_type_once(self):
        original = (self.START, '', self.END, '')
        cursor = self.merge([original], [(self.TODAY, '', self.END, '')] * 3)
        self.assertEqual(cursor.rows, [original])
        self.assertEqual(cursor.type_reads, 1)

    def test_other_event_types_keep_distinct_spans(self):
        for event_type in ('Festival', None, 'Class'):
            with self.subTest(event_type=event_type):
                cursor = self.merge([(self.START, '', self.END, '')],
                                    [(self.TODAY, '', self.END, '')], event_type)
                self.assertEqual(len(cursor.rows), 2)

    def test_conflicting_closing_dates_require_source_review(self):
        cursor = self.merge([(self.START, '', self.END, '')],
                            [(self.TODAY, '', date(2027, 5, 1), '')])
        self.assertEqual(len(cursor.rows), 2)
        self.assertEqual(cursor.type_reads, 0)

    def test_timed_sessions_and_single_days_survive(self):
        original = (self.START, '', self.END, '')
        for incoming in ((self.TODAY, '1pm', self.END, ''),
                         (self.TODAY, '', self.END, '5pm'),
                         (self.END, '', self.END, ''),
                         (self.TODAY, '', None, '')):
            with self.subTest(incoming=incoming):
                cursor = self.merge([original], [incoming])
                self.assertEqual(len(cursor.rows), 2)
                self.assertEqual(cursor.type_reads, 0)

    def test_existing_timed_span_is_not_removed(self):
        timed = (self.TODAY, '', self.END, '5pm')
        cursor = self.merge([timed], [(self.START, '', self.END, '')])
        self.assertIn(timed, cursor.rows)
        self.assertEqual(len(cursor.rows), 2)


if __name__ == '__main__':
    unittest.main()
