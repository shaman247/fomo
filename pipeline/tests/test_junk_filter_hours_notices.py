"""Tests for the opening-hours-notice rule in is_obvious_non_event.

Library and museum calendars publish their own operating hours as calendar rows —
e216504 "Library open 9 AM - 5 PM", body "Library will be open 9 AM to 5 PM for
Columbus Day". Nothing is happening; the building is merely unlocked. It reached
the map and was only caught downstream when the event-type classifier labelled it
UNKNOWN on 2026-08-11.

This is the mirror image of the CLOSURE family, which was already filtered: a
holiday that changes the hours gets published either way round, and only the
"closed" half was covered.

**Why the clock time is the load-bearing gate.** "open" is a very live word. A
first draft accepted `open … (until|from|for)` and the precision audit over all
185,367 events immediately caught real events: "Open for Bowling!" (a Brooklyn
Bowl session, 6 rows), "Open for cocktails" (Zinc Bar), "Open for Ops", and
"Open Forum" — where `for` matched the first three letters of "Forum". Requiring
an explicit clock time, plus an attendable-word veto, takes it to exactly 2
matches corpus-wide, both genuine junk.

The negative cases below are that audit, frozen. Do not loosen this rule without
re-running the corpus audit (`.scratch/junkfilter_precision.py` is the pattern).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import is_obvious_non_event, _is_hours_notice, _description_adds_nothing


class TestHoursNoticeIsJunk(unittest.TestCase):
    """The shape that actually reached the map."""

    def test_library_open_hours_row(self):
        self.assertTrue(is_obvious_non_event(
            'Library open 9 AM - 5 PM',
            'Library will be open 9 AM to 5 PM for Columbus Day'))

    def test_museum_variant(self):
        self.assertTrue(_is_hours_notice('Museum open 10 AM to 6 PM', ''))

    def test_no_space_before_meridiem(self):
        self.assertTrue(_is_hours_notice('Library Open 9AM-5PM', ''))

    def test_fires_without_a_description(self):
        """These rows are usually description-less or restate the hours."""
        self.assertTrue(_is_hours_notice('Library open 9 AM - 5 PM', ''))


class TestRealEventsWithOpenInTheName(unittest.TestCase):
    """Frozen from the corpus audit — every one of these is a REAL event.

    The first four are verbatim names of live/historical rows that an earlier
    draft of this rule wrongly matched.
    """

    def test_open_for_bowling_is_a_real_session(self):
        self.assertFalse(_is_hours_notice('Open for Bowling!', ''))
        self.assertFalse(is_obvious_non_event(
            'Open for Bowling!',
            'The bowling lanes are open to the public. Come enjoy a classic game.'))

    def test_open_for_cocktails_is_a_real_bar_night(self):
        self.assertFalse(_is_hours_notice('Open for cocktails', ''))

    def test_open_forum_is_not_an_hours_notice(self):
        """`for` must not match the first three letters of "Forum"."""
        self.assertFalse(_is_hours_notice('Open Forum', ''))

    def test_open_for_ops(self):
        self.assertFalse(_is_hours_notice('Open for Ops', ''))

    def test_attendable_open_events_with_clock_times_are_spared(self):
        for name in ('Open Mic 8 PM',
                     'Open House 10 AM - 2 PM',
                     'Opening Reception 6 PM',
                     'Open Studios 12 PM',
                     'Open Play 3 PM',
                     'Doors open 7 PM — The Hold Steady',
                     'Gallery open 11 AM, artist talk 2 PM'):
            with self.subTest(name=name):
                self.assertFalse(_is_hours_notice(name, ''))


class TestTitleEchoDescription(unittest.TestCase):
    """A description that merely repeats the title carries no information.

    e216438 "Patron Reservation - O'Connor" carried the description
    "Patron Reservation - O'Connor" and so slipped the room-reservation rule,
    which was gated on the description being BLANK.
    """

    def test_room_reservation_with_title_echo_is_junk(self):
        self.assertTrue(is_obvious_non_event(
            "Patron Reservation - O'Connor", "Patron Reservation - O'Connor"))

    def test_title_echo_detected_case_and_space_insensitively(self):
        self.assertTrue(_description_adds_nothing('Room Reservation', ' room   RESERVATION '))

    def test_blank_still_counts(self):
        self.assertTrue(_description_adds_nothing('Anything', 'No description available.'))
        self.assertTrue(_description_adds_nothing('Anything', ''))

    def test_a_description_that_merely_starts_with_the_title_is_real_content(self):
        """Strictly exact — a prefix match must NOT be treated as blank."""
        self.assertFalse(_description_adds_nothing(
            "Patron Reservation - O'Connor",
            "Patron Reservation - O'Connor. Join us for a cello recital at 7pm."))

    def test_real_event_with_a_real_description_is_untouched(self):
        self.assertFalse(_description_adds_nothing(
            'Jazz Night', 'A weekly jazz session with the house trio.'))


if __name__ == '__main__':
    unittest.main()
