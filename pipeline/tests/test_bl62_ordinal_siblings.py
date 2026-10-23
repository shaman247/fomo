"""BL62 (2026-10-23): bare Roman numerals, Roman levels and age bands are identity.

`merger.are_names_similar` fused sibling listings that differ by one cohort
marker, and the processor's substring grouping did the same inside one crawl:

* CMS w1539 "Beethoven Piano Sonatas II" is a raw substring of "... III", so
  the calendar's URL-less III rows were grouped into II's crawl_event and event
  246980 carried III's Dec 1-2 dates;
* MCPL w6058 "English Class: Basic - Level II" vs "... Level I" (293587);
* HPL w4080 "Musical Kids (Ages 1-2 years)" / "(Ages 2-4 years)" /
  "(Ages Birth-1 year)", Bridgeport w5241 "Anime And Manga Club for ages 9-13"
  / "13-17" (275599), Taste Buds w197 "Donut • Ages 4-8 • ..." / "Ages 9-13".

Run: ./venv/bin/python pipeline/tests/test_bl62_ordinal_siblings.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger
import processor
from remaining_name_identity import (explicit_disjoint_age_band_mismatch,
                                     trailing_roman_ordinal_mismatch)


DISTINCT = [
    ("Beethoven Piano Sonatas II", "Beethoven Piano Sonatas III"),
    ("CMS: Beethoven Piano Sonatas III", "Beethoven Piano Sonatas II"),
    ("MISE-EN Festival 2026: Concert II", "MISE-EN Festival 2026: Concert IV"),
    ("Bookbinding II", "Bookbinding III: Editioning"),
    ("English Class: Basic - Level II -(Thursdays)",
     "English Class: Basic - Level I - (Thursdays)"),
    ("English Level I with Greenburgh Evergreen Club",
     "English Level II with Greenburgh Evergreen Club"),
    ("Musical Kids (Ages 1-2 years)", "Musical Kids (Ages 2-4 years)"),
    ("Musical Kids (Ages 1-2 years)", "Musical Kids (Ages Birth-1 year)"),
    ("Anime And Manga Club for ages 9-13", "Anime And Manga Club for ages 13-17"),
    ("Donut • Ages 4-8 • Vegetarian • Sprinkle Donuts • Pizza Donuts",
     "Donut • Ages 9-13 • Vegetarian • Sprinkle Donuts • Pizza Donuts"),
    ("Make Your Own Trick-or-Treat Bag! (GRADES K - 2)",
     "Make Your Own Trick-or-Treat Bag! (GRADES 3 - 6)"),
    ("Watercolor Workshop (Ages 13-18)", "Watercolor Workshop (Ages 18+)"),
    ("Baby Signing (Ages 6-18 months)", "Baby Signing (Ages 18-36 months)"),
]

STILL_SIMILAR = [
    # Same numeral / same band written differently.
    ("Beethoven Piano Sonatas II", "Beethoven Piano Sonatas II - NEW DATE ADDED"),
    ("Musical Kids (Ages 2-4 years)", "Musical Kids (ages 2 to 4)"),
    # Only one side carries the marker: the ordinary fuller-title shape.
    ("Beethoven Piano Sonatas", "Beethoven Piano Sonatas II"),
    ("Anime And Manga Club", "Anime And Manga Club for ages 9-13"),
    # Overlapping audiences are not a cohort conflict.
    ("Family Art (Ages 7+)", "Family Art (Ages 9-12)"),
    # A combined or ranged level is not one level.
    ("Spanish Level I/II", "Spanish Level II"),
]


class OrdinalSiblingNames(unittest.TestCase):
    def test_distinct_siblings_do_not_match(self):
        for a, b in DISTINCT:
            with self.subTest(a=a, b=b):
                self.assertFalse(merger.are_names_similar(a, b))
                self.assertFalse(merger.are_names_similar(b, a))

    def test_unchanged_pairs_still_match(self):
        for a, b in STILL_SIMILAR:
            with self.subTest(a=a, b=b):
                self.assertTrue(merger.are_names_similar(a, b))
                self.assertTrue(merger.are_names_similar(b, a))

    def test_roman_tail_needs_matching_head_and_uppercase(self):
        self.assertTrue(trailing_roman_ordinal_mismatch('Act II: Arrival', 'Act III: Departure'))
        self.assertFalse(trailing_roman_ordinal_mismatch('Rocky II', 'Henry V'))
        self.assertFalse(trailing_roman_ordinal_mismatch('Tea and i', 'Tea and ii'))
        self.assertFalse(trailing_roman_ordinal_mismatch('WWII Talk', 'WWI Talk'))
        self.assertFalse(trailing_roman_ordinal_mismatch('Louis XIV', 'Louis XIV'))

    def test_age_band_shapes(self):
        m = explicit_disjoint_age_band_mismatch
        self.assertTrue(m('Baby Storytime for ages 0-2', 'Baby Storytime for ages 3-5'))
        # One-word programs are too generic to vouch for a shared parent.
        self.assertFalse(m('Storytime for ages 0-2', 'Storytime for ages 3-5'))
        self.assertTrue(m('Lego Club Grades K-2', 'Lego Club Grades 3-5'))
        self.assertTrue(m('Swim Lessons ages 5 and up', 'Swim Lessons ages 2-5'))
        # Different programs, two bands in one title, or a grade vs an age.
        self.assertFalse(m('Storytime for ages 0-2', 'Craft Hour for ages 3-5'))
        self.assertFalse(m('Camp (Ages 4-8 & 9-13)', 'Camp (Ages 9-13)'))
        self.assertFalse(m('Lego Club Grades K-2', 'Lego Club Ages 8-10'))

    def test_processor_keeps_url_less_roman_siblings_apart(self):
        rows = [dict(name=n, location='Daniel and Joanna S. Rose Studio', location_id=3364,
                     url=None, start_date=d, start_time='7:30pm', end_date='', end_time='')
                for n, d in (('Beethoven Piano Sonatas II', '2026-11-05'),
                             ('Beethoven Piano Sonatas II', '2026-11-06'),
                             ('Beethoven Piano Sonatas III', '2026-12-01'),
                             ('Beethoven Piano Sonatas III', '2026-12-02'))]
        for ordered in (rows, rows[::-1]):
            groups = processor.group_event_occurrences(ordered)
            self.assertEqual(len(groups), 2)

    def test_same_capture_relation_splits_cohorts(self):
        self.assertFalse(merger.same_capture_names_related(
            'English Class: Basic - Level I - (Thursdays)',
            'English Class: Basic - Level II -(Thursdays)'))
        self.assertFalse(merger.same_capture_names_related(
            'Make Your Own Trick-or-Treat Bag! (GRADES 3 - 6)',
            'Make Your Own Trick-or-Treat Bag! (GRADES K - 2)'))
        self.assertTrue(merger.same_capture_names_related(
            'Beethoven Piano Sonatas II', 'Beethoven Piano Sonatas II - SOLD OUT'))


if __name__ == '__main__':
    unittest.main()
