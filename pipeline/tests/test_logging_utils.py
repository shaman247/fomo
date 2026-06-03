"""Tests for the timestamped print wrapper used during pipeline runs."""

import io
import os
import re
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging_utils


def _norm(text):
    """Replace concrete HH:MM:SS stamps with a stable marker for comparison."""
    return re.sub(r'\[\d\d:\d\d:\d\d\]', '[TS]', text)


class TimestampedPrintTest(unittest.TestCase):
    def setUp(self):
        logging_utils._at_line_start = True

    def _capture(self, *calls):
        buf = io.StringIO()
        with redirect_stdout(buf):
            for args, kwargs in calls:
                logging_utils._timestamped_print(*args, **kwargs)
        return _norm(buf.getvalue())

    def test_single_line(self):
        self.assertEqual(self._capture((('hello',), {})), '[TS] hello\n')

    def test_blank_line_not_stamped(self):
        self.assertEqual(self._capture(((), {})), '\n')

    def test_leading_newline(self):
        self.assertEqual(self._capture((('\nfoo',), {})), '\n[TS] foo\n')

    def test_multiline_each_line_stamped(self):
        self.assertEqual(self._capture((('a\nb',), {})), '[TS] a\n[TS] b\n')

    def test_interior_blank_line_preserved(self):
        self.assertEqual(self._capture((('a\n\nb',), {})), '[TS] a\n\n[TS] b\n')

    def test_continuation_keeps_single_stamp(self):
        # print("Uploading...", end=' ') then print("done") shares one line.
        out = self._capture(
            (('Uploading...',), {'end': ' '}),
            (('done',), {}),
        )
        self.assertEqual(out, '[TS] Uploading... done\n')

    def test_sep_respected(self):
        self.assertEqual(self._capture((('a', 'b'), {'sep': '-'})), '[TS] a-b\n')


class FormatDurationTest(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(logging_utils.format_duration(0), '0s')
        self.assertEqual(logging_utils.format_duration(8.4), '8s')
        self.assertEqual(logging_utils.format_duration(59), '59s')

    def test_minutes(self):
        self.assertEqual(logging_utils.format_duration(60), '1m00s')
        self.assertEqual(logging_utils.format_duration(252), '4m12s')

    def test_hours(self):
        self.assertEqual(logging_utils.format_duration(3787), '1h03m07s')


class StepTimerTest(unittest.TestCase):
    def test_records_steps_in_order(self):
        timer = logging_utils.StepTimer()
        timer.start('a')
        timer.start('b')
        result = timer.stop()
        names = [n for n, _ in timer.steps]
        self.assertEqual(names, ['a', 'b'])
        self.assertEqual(result[0], 'b')

    def test_stop_when_idle_returns_none(self):
        timer = logging_utils.StepTimer()
        self.assertIsNone(timer.stop())

    def test_total_sums_steps(self):
        timer = logging_utils.StepTimer()
        timer._steps = [('a', 1.0), ('b', 2.5)]
        self.assertAlmostEqual(timer.total, 3.5)

    def test_start_closes_previous_step(self):
        timer = logging_utils.StepTimer()
        timer.start('a')
        timer.start('b')
        # 'a' was closed by starting 'b'; only 'a' recorded so far
        self.assertEqual([n for n, _ in timer.steps], ['a'])


if __name__ == '__main__':
    unittest.main()
