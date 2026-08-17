"""Tests for the public NDJSON dataset export (exporter.export_public_dataset).

Covers the pure helpers: occurrence window-filtering/dedupe (including the
legacy overlapping-span collapse), the weekly scheduling gate driven by dated
snapshot filenames, and NDJSON serialization.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exporter import (dedupe_past_occurrences, dedupe_public_occurrences,
                      should_export_public_dataset, write_ndjson)


WINDOW = (date(2026, 8, 14), date(2026, 11, 12))


class TestDedupePublicOccurrences(unittest.TestCase):
    def test_window_filtering(self):
        rows = [
            (date(2026, 8, 1), None, None, None),     # past — dropped
            (date(2026, 8, 20), '7pm', None, None),   # in window
            (date(2026, 12, 1), None, None, None),    # beyond window — dropped
            (None, '7pm', None, None),                # no date — dropped
        ]
        out = dedupe_public_occurrences(rows, *WINDOW)
        self.assertEqual([o['start_date'] for o in out], ['2026-08-20'])

    def test_span_overlapping_window_edge_kept(self):
        # Ends inside the window though it started before it.
        rows = [(date(2026, 8, 1), None, date(2026, 9, 1), None)]
        out = dedupe_public_occurrences(rows, *WINDOW)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['end_date'], '2026-09-01')

    def test_exact_duplicates_collapse(self):
        rows = [
            (date(2026, 8, 20), '7pm', None, '9pm'),
            (date(2026, 8, 20), '7pm', None, '9pm'),
        ]
        out = dedupe_public_occurrences(rows, *WINDOW)
        self.assertEqual(len(out), 1)

    def test_contained_span_collapses(self):
        # The legacy artifact: 08-20→10-05 alongside 08-24→10-05 (same times).
        rows = [
            (date(2026, 8, 20), None, date(2026, 10, 5), None),
            (date(2026, 8, 24), None, date(2026, 10, 5), None),
        ]
        out = dedupe_public_occurrences(rows, *WINDOW)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['start_date'], '2026-08-20')
        self.assertEqual(out[0]['end_date'], '2026-10-05')

    def test_different_times_spans_not_collapsed(self):
        rows = [
            (date(2026, 8, 20), '10am', date(2026, 10, 5), '5pm'),
            (date(2026, 8, 24), '11am', date(2026, 10, 5), '5pm'),
        ]
        out = dedupe_public_occurrences(rows, *WINDOW)
        self.assertEqual(len(out), 2)

    def test_single_day_repeats_kept(self):
        # A weekly recurring event is NOT an overlapping span — all kept.
        rows = [(date(2026, 8, 20) + timedelta(days=7 * i), '7pm', None, None)
                for i in range(3)]
        out = dedupe_public_occurrences(rows, *WINDOW)
        self.assertEqual(len(out), 3)

    def test_sorted_by_start(self):
        rows = [
            (date(2026, 9, 1), None, None, None),
            (date(2026, 8, 20), '7pm', None, None),
        ]
        out = dedupe_public_occurrences(rows, *WINDOW)
        self.assertEqual([o['start_date'] for o in out],
                         ['2026-08-20', '2026-09-01'])

    def test_null_end_date_preserved(self):
        out = dedupe_public_occurrences([(date(2026, 8, 20), '7pm', None, None)], *WINDOW)
        self.assertIsNone(out[0]['end_date'])
        self.assertIsNone(out[0]['end_time'])


class TestDedupePastOccurrences(unittest.TestCase):
    TODAY = date(2026, 8, 14)

    def test_recently_ended_kept(self):
        rows = [
            (date(2026, 8, 13), '7pm', None, None),    # yesterday — kept
            (date(2026, 7, 20), None, None, None),     # 25 days ago — kept
        ]
        out = dedupe_past_occurrences(rows, self.TODAY)
        self.assertEqual(len(out), 2)

    def test_lookback_boundary(self):
        rows = [
            (date(2026, 7, 17), None, None, None),  # exactly 28 days ago — kept
            (date(2026, 7, 16), None, None, None),  # 29 days ago — dropped
        ]
        out = dedupe_past_occurrences(rows, self.TODAY)
        self.assertEqual([o['start_date'] for o in out], ['2026-07-17'])

    def test_today_and_future_excluded(self):
        rows = [
            (date(2026, 8, 14), '7pm', None, None),   # today — upcoming, not past
            (date(2026, 8, 20), '7pm', None, None),   # future — dropped
        ]
        self.assertEqual(dedupe_past_occurrences(rows, self.TODAY), [])

    def test_ongoing_span_excluded(self):
        # Started long ago but hasn't ended — belongs to upcoming, not past.
        rows = [(date(2025, 6, 11), None, date(2031, 4, 20), None)]
        self.assertEqual(dedupe_past_occurrences(rows, self.TODAY), [])

    def test_span_ended_last_week_kept_despite_old_start(self):
        rows = [(date(2026, 5, 1), None, date(2026, 8, 10), None)]
        out = dedupe_past_occurrences(rows, self.TODAY)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['end_date'], '2026-08-10')


class TestShouldExportPublicDataset(unittest.TestCase):
    def _touch(self, dirname, filename):
        with open(os.path.join(dirname, filename), 'w') as f:
            f.write('')

    def test_no_dir_or_snapshots_means_due(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(should_export_public_dataset(
                today=date(2026, 8, 14), export_dir=os.path.join(d, 'missing')))
            self.assertTrue(should_export_public_dataset(
                today=date(2026, 8, 14), export_dir=d))

    def test_recent_snapshot_not_due(self):
        with tempfile.TemporaryDirectory() as d:
            self._touch(d, 'events-upcoming-2026-08-10.ndjson')
            self.assertFalse(should_export_public_dataset(
                today=date(2026, 8, 14), export_dir=d))

    def test_week_old_snapshot_due(self):
        with tempfile.TemporaryDirectory() as d:
            self._touch(d, 'events-upcoming-2026-08-07.ndjson')
            self.assertTrue(should_export_public_dataset(
                today=date(2026, 8, 14), export_dir=d))

    def test_newest_snapshot_governs(self):
        with tempfile.TemporaryDirectory() as d:
            self._touch(d, 'events-upcoming-2026-07-01.ndjson')
            self._touch(d, 'events-upcoming-2026-08-12.ndjson')
            self.assertFalse(should_export_public_dataset(
                today=date(2026, 8, 14), export_dir=d))

    def test_unrelated_files_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            self._touch(d, 'manifest.json')
            self._touch(d, 'events-upcoming.ndjson')  # stable alias — not dated
            self._touch(d, 'events-past.ndjson')
            self._touch(d, 'events-2026-08-14.ndjson')  # legacy naming — ignored
            self.assertTrue(should_export_public_dataset(
                today=date(2026, 8, 14), export_dir=d))


class TestWriteNdjson(unittest.TestCase):
    def test_round_trip_and_unicode(self):
        records = [
            {'event_id': 1, 'name': 'Café Concert', 'emoji': '🎸'},
            {'event_id': 2, 'name': 'Line\nBreak in name'},
        ]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'out.ndjson')
            write_ndjson(records, path)
            with open(path, encoding='utf-8') as f:
                lines = f.read().splitlines()
            self.assertEqual(len(lines), 2)
            parsed = [json.loads(line) for line in lines]
            self.assertEqual(parsed, records)
            # Emoji shipped raw (ensure_ascii=False), newlines escaped in-line
            self.assertIn('🎸', lines[0])


if __name__ == '__main__':
    unittest.main()
