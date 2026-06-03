"""Tests for the canonical time format: standardize_time + Pydantic validators.

Mirrors the canonicalization invariant documented in
memory/occurrence_time_canonicalization.md. If you change the rules in
processor.py::_standardize_time or extractor.py::_clean_extracted_time, update
this file and verify src/api/time_format.php still passes the same cases.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import _standardize_time
from extractor import EventOccurrence, SimpleOccurrence


STANDARDIZE_CASES = [
    # canonical / idempotent
    ('', ''),
    (None, ''),
    ('7pm', '7pm'),
    ('7:30pm', '7:30pm'),
    ('11am', '11am'),
    ('12am', '12am'),
    ('12pm', '12pm'),
    # case + whitespace + dots
    ('7PM', '7pm'),
    ('7:00pm', '7pm'),
    ('7:30 PM', '7:30pm'),
    ('7 p.m.', '7pm'),
    # 24-hour HH:MM
    ('17:38', '5:38pm'),
    ('20:08', '8:08pm'),
    ('00:30', '12:30am'),
    ('12:00', '12pm'),
    ('14:30', '2:30pm'),
    # bare HH (leading zero or hour >= 13 unambiguous; 0 -> midnight, 12 -> noon)
    ('08', '8am'),
    ('20', '8pm'),
    ('00', '12am'),
    ('12', '12pm'),
    # TZ suffix
    ('1pmest', '1pm'),
    ('8 PM EST', '8pm'),
    # sentinels
    ('allday', ''),
    ('varioustimes', ''),
    ('close', ''),
    ('ongoing', ''),
    ('TBA', ''),
    # underscore + single-digit zero minute (real-world noise we observed)
    ('9_pm', '9pm'),
    ('7:0pm', '7pm'),
    # ambiguous — preserved
    ('6:30', '6:30'),
    ('7', '7'),
    # unrecognized — preserved
    ('11am,12pm,3pm,4pm', '11am,12pm,3pm,4pm'),
    ('weird-input', 'weird-input'),
]


class TestStandardizeTime(unittest.TestCase):
    def test_canonicalization(self):
        for inp, expected in STANDARDIZE_CASES:
            with self.subTest(inp=inp):
                self.assertEqual(_standardize_time(inp), expected)

    def test_idempotent(self):
        for inp, _ in STANDARDIZE_CASES:
            once = _standardize_time(inp)
            twice = _standardize_time(once)
            with self.subTest(inp=inp):
                self.assertEqual(once, twice)


class TestEventOccurrenceValidator(unittest.TestCase):
    """The Pydantic validator should accept canonical / canonicalizable inputs and
    null out anything Gemini hallucinates (paragraphs, dates in time fields,
    sentinels, integers, etc.).
    """

    def assertOccurrence(self, raw, expected_sd, expected_st, expected_et):
        occ = EventOccurrence.model_validate(raw)
        self.assertEqual(occ.start_date, expected_sd)
        self.assertEqual(occ.start_time, expected_st)
        self.assertEqual(occ.end_time, expected_et)

    def test_canonical_passthrough(self):
        self.assertOccurrence(
            {'start_date': '2026-06-15', 'start_time': '7pm', 'end_time': '9pm'},
            '2026-06-15', '7pm', '9pm',
        )

    def test_canonicalizes_24h_pair(self):
        # I Love Boosters cinema showtime
        self.assertOccurrence(
            {'start_date': '2026-05-22', 'start_time': '17:38', 'end_time': '19:23'},
            '2026-05-22', '5:38pm', '7:23pm',
        )

    def test_canonicalizes_12h_with_colon_zero(self):
        self.assertOccurrence(
            {'start_date': '2026-05-27', 'start_time': '6:30 PM', 'end_time': '8:00 PM'},
            '2026-05-27', '6:30pm', '8pm',
        )

    def test_canonicalizes_bare_24h(self):
        # Greenmarket-style
        self.assertOccurrence(
            {'start_date': '2026-06-04', 'start_time': '08', 'end_time': '15'},
            '2026-06-04', '8am', '3pm',
        )

    def test_rejects_sentinel_time(self):
        self.assertOccurrence(
            {'start_date': '2026-05-01', 'start_time': 'allday'},
            '2026-05-01', None, None,
        )

    def test_rejects_date_in_time_field(self):
        self.assertOccurrence(
            {'start_date': '2026-04-14', 'end_time': '2026-06-30'},
            '2026-04-14', None, None,
        )

    def test_rejects_hallucinated_text_time(self):
        # Real string Gemini emitted: end_time='pulitzerprizewinning'
        self.assertOccurrence(
            {'start_date': '2026-05-15', 'start_time': '7pm', 'end_time': 'pulitzerprizewinning'},
            '2026-05-15', '7pm', None,
        )

    def test_rejects_typo_time(self):
        # Zinc Bar end_time='2:am' (typo for '2am')
        self.assertOccurrence(
            {'start_date': '2026-05-02', 'start_time': '2pm', 'end_time': '2:am'},
            '2026-05-02', '2pm', None,
        )

    def test_rejects_concatenated_text_time(self):
        # Real string: '7pmsign-ups'
        self.assertOccurrence(
            {'start_date': '2026-05-22', 'start_time': '7pmsign-ups'},
            '2026-05-22', None, None,
        )

    def test_rejects_ambiguous_bare_time(self):
        # Film Forum '7:10' could be 7:10am or 7:10pm; reject so Gemini gets coaxed
        # to include AM/PM next time, and downstream cleanup can find it.
        self.assertOccurrence(
            {'start_date': '2026-05-26', 'start_time': '7:10'},
            '2026-05-26', None, None,
        )

    def test_rejects_integer_time(self):
        self.assertOccurrence(
            {'start_date': '2026-05-15', 'start_time': 1900},
            '2026-05-15', None, None,
        )

    def test_rejects_garbage_start_date(self):
        # Whole-paragraph hallucination Gemini emitted as start_date
        self.assertOccurrence(
            {'start_date': 'Join Dr. Huei Sears to explore the cosmos', 'start_time': '7pm'},
            None, '7pm', None,
        )

    def test_accepts_null_start_date(self):
        self.assertOccurrence(
            {'start_date': None, 'start_time': '7pm'},
            None, '7pm', None,
        )

    def test_strips_tz_suffix(self):
        self.assertOccurrence(
            {'start_date': '2026-01-23', 'start_time': '10am', 'end_time': '1pmest'},
            '2026-01-23', '10am', '1pm',
        )


class TestSimpleOccurrenceValidator(unittest.TestCase):
    """SimpleOccurrence has no end_date but should otherwise behave like EventOccurrence."""

    def test_canonicalizes(self):
        occ = SimpleOccurrence.model_validate(
            {'start_date': '2026-05-22', 'start_time': '17:38', 'end_time': '19:23'}
        )
        self.assertEqual(occ.start_date, '2026-05-22')
        self.assertEqual(occ.start_time, '5:38pm')
        self.assertEqual(occ.end_time, '7:23pm')

    def test_rejects_garbage(self):
        occ = SimpleOccurrence.model_validate(
            {'start_date': '2026-05-15', 'start_time': '7pm', 'end_time': 'pulitzerprizewinning'}
        )
        self.assertEqual(occ.end_time, None)


if __name__ == '__main__':
    unittest.main()
