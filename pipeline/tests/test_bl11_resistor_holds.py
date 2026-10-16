"""BL11 (2026-10-16): NYC Resistor (w716) HOLD-titled calendar entries.

Measured over every w716 capture (194 distinct HOLD entries): none links to its
own event page (3 link only to the Eventbrite organizer page), and the parties
the backlog worried about are published separately once confirmed: "HOLD:
HALLOWEEN PARTY!!!" (Oct 31) became "NYC Resistor Halloween Party 2026" with its
own ticket link (cr-132883). So HOLD entries keep being omitted, with no keep
exception; the confirmed listing carries the event. These titles are real
captures.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extractor
import processor


class ResistorHoldTests(unittest.TestCase):

    def test_separated_hold_bookings_are_dropped(self):
        for name in ('HOLD: HALLOWEEN PARTY!!!', 'Hold: Halloween Party!!!', 'HOLD - ITP SHOWCASE [all day]',
                     'HOLD Kitchen Lithography', 'Hold:Finger Crochet',
                     'HOLD: Intro to Soldering Workshop: Make an LED Tile'):
            with self.subTest(name=name):
                self.assertEqual(processor.which_junk_rule(name, 'A party with DJs and costumes.'),
                                 'hold_placeholder')

    def test_confirmed_listings_are_kept(self):
        for name in ('NYC Resistor Halloween Party 2026', 'Synthesizer Night @ NYC Resistor',
                     'All Decked Out: A Cyberdeck Open Mic', 'Halloween Potions Make Along'):
            with self.subTest(name=name):
                self.assertIsNone(processor.which_junk_rule(name, 'No description available.'))

    def test_prompt_has_no_hold_keep_exception(self):
        rule = extractor.EVENT_STATUS_RULE
        self.assertIn('Calendar reservations marked "HOLD:"', rule)
        self.assertIn('omit them from event lists', rule)
        self.assertIn('Never remove a HOLD', rule)


if __name__ == '__main__':
    unittest.main()
