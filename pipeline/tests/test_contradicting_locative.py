"""Tests for `processor.strip_contradicting_locative`.

NYPL listing pages repeat one house sentence per record — "This event will take
place in person at the <Branch> Library." Chunked extraction regularly staples
one record's sentence onto a sibling record, so the description names a branch
the event is not at. Measured 2026-08-24: 33 of 173 active w3 events with that
phrasing named a branch contradicting their own pin, and on every one of them
all of the event's crawl_events agreed on the CORRECT branch — the pin is right
and the prose is wrong.

The guard drops the whole sentence rather than rewriting the venue name inside
it, because the sentence belongs to another record: patching only the name would
make a foreign sentence look correct.

It is deliberately narrow. A loose `takes place ... at <X>` rule backtested over
the 9,132 crawl_events containing "take(s) place" fired on 1,272 rows, only 488
of them w3, and shredded legitimate prose elsewhere — date tails ("reception will
take place on Saturday, April 11 at 2pm"), real multi-venue copy under a
neighborhood pin ("Performances take place at BAM, Roulette, Public Records"),
and a named venue under a generic pin ("takes place at the historic Cipriani").
Requiring the event itself as the subject plus an explicit in-person/online
modality took the same backtest to 447 hits, all w3, with no spillover.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import strip_contradicting_locative as strip


class ContradictingLocativeTests(unittest.TestCase):

    def test_drops_sibling_branch_sentence(self):
        self.assertEqual(
            strip('This event will take place in person at the Parkchester '
                  'Library. Do you have trouble with your email?',
                  'Stavros Niarchos Foundation Library (SNFL)'),
            'Do you have trouble with your email?')

    def test_drops_trailing_sentence_too(self):
        self.assertEqual(
            strip('Come compete on the Switch and PS5. This event will take '
                  'place in person at the St. George Library Teen Center.',
                  'Riverside Library'),
            'Come compete on the Switch and PS5.')

    def test_clipped_leading_character_still_matches(self):
        # Extraction sometimes eats the leading "T" (observed on event 224496).
        self.assertEqual(
            strip("his event will take place in person at the Macomb's Bridge "
                  'Library. Join us for an afternoon movie.',
                  'George Bruce Library'),
            'Join us for an afternoon movie.')

    def test_whole_description_becomes_none_not_a_wrong_venue(self):
        # A NULL description is recoverable (detail crawl / merger backfill);
        # a confidently wrong venue name is not.
        self.assertIsNone(
            strip('This event will take place IN PERSON at the Stavros '
                  'Niarchos Foundation Library, 6th floor, Room 602.',
                  'Parkchester Library'))

    def test_keeps_matching_branch(self):
        desc = ('This event will take place IN PERSON at the Great Kills '
                'Library. INTERMEDIATE English Conversation')
        self.assertEqual(strip(desc, 'Great Kills Library'), desc)

    def test_keeps_sublocation_within_the_same_branch(self):
        desc = ('This event will take place in person at the St. George '
                'Library Center in the TechConnect Lab. Learn Windows.')
        self.assertEqual(strip(desc, 'St. George Library Center'), desc)

    # The cosmetic naming variants the scheduled task calls out explicitly:
    # these are the SAME branch spelled differently and must never be dropped.
    def test_keeps_cosmetic_naming_variants(self):
        for desc_branch, pin in (
            ("Throgs Neck Library", "Throg's Neck Library"),
            ("Woodstock Branch Library", "Woodstock Library"),
            ("Sedgwick Branch", "Sedgwick Library"),
        ):
            desc = f'This event will take place in person at {desc_branch}. Crafts!'
            with self.subTest(pin=pin):
                self.assertEqual(strip(desc, pin), desc)

    # --- the false positives that forced the narrow form ---

    def test_ignores_date_and_time_tail(self):
        desc = ('An exhibition in the orangerie. A special opening reception '
                'will take place on Saturday, April 11 at 2pm.')
        self.assertEqual(strip(desc, 'Bartow-Pell Mansion Museum'), desc)

    def test_ignores_genuine_multi_venue_copy(self):
        desc = ('A dense network of 50+ concerts. Performances take place at '
                'BAM, Roulette, Public Records.')
        self.assertEqual(strip(desc, 'Downtown Brooklyn'), desc)

    def test_ignores_real_venue_under_a_generic_pin(self):
        desc = ('An annual awards ceremony. The event takes place at the '
                'historic Cipriani.')
        self.assertEqual(strip(desc, 'Manhattan, New York'), desc)

    def test_missing_inputs_pass_through(self):
        self.assertIsNone(strip(None, 'Inwood Library'))
        self.assertEqual(strip('Some blurb.', None), 'Some blurb.')
        self.assertEqual(strip('Some blurb.', '  '), 'Some blurb.')


if __name__ == '__main__':
    unittest.main()
