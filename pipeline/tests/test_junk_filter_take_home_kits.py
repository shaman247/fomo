"""Tests for the take-home-kit and program-deadline rules in is_obvious_non_event.

Libraries publish "Grab & Go" / "Take-Home" kit rows (patrons pick up a craft
kit and do it at home) and "<program> Ends!" submit-your-logs reminders as
calendar events. Nobody attends either. Three kit rows (219397, 219412,
219497) and one deadline row (219452) reached `events` from w3530 (BCCLS) on
2026-08-14 and were only caught downstream by the event-type classifier.

Verified over all 188,480 events: the kit rule fires 105 times, every one a
genuine kit distribution, 0 false positives; the deadline rule fires exactly
once (219452 itself). A third pattern from the same batch — names ending in
"Room <n>" for library room-booking rows — was REJECTED; see
TestRoomSuffixStaysUnfiltered.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import is_obvious_non_event


class TestTakeHomeKitDistributions(unittest.TestCase):
    def test_teen_grab_and_go_craft(self):
        # e219397 — the row that motivated the rule.
        self.assertTrue(is_obvious_non_event(
            'TEEN Grab & Go: Books Paint by Numbers',
            'Beat the summer heat with an easy paint by numbers craft to the '
            'theme of the library with cute books designs! Due to limited '
            'supplies please register for this craft! We only hold kits for a '
            'week.'))

    def test_adult_take_home_craft(self):
        # e219412.
        self.assertTrue(is_obvious_non_event(
            'Adult Take-Home Craft',
            'Relax and have fun with a craft kit provided by your pals at the '
            'library! Registration required.'))

    def test_take_home_kit_pickup(self):
        # e219497.
        self.assertTrue(is_obvious_non_event(
            'J Summer Take Home Kit #4: Bead Bracelet',
            'Stop by the Youth Services Desk to pick up a kit while supplies '
            'last.'))

    def test_grab_and_go_spelling_variants(self):
        for name in ('Grab and Go Crafts', 'Kids Create: Grab n Go',
                     'Grab & Go: Origami Stars'):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(
                    name, 'Pick up a craft kit at the desk, available while '
                          'supplies last.'))

    def test_real_class_that_sends_plants_home_survives(self):
        """The veto spares in-person programming that ends with a takeaway.

        e69813 "Indoor Spring: Learn Grow and Take Home Plants" is a real
        4-session class; `session` / `join us` veto the drop.
        """
        self.assertFalse(is_obvious_non_event(
            'Indoor Spring: Learn Grow and Take Home Plants',
            'To celebrate the arrival of spring, we invite you to join us for '
            'this 4-session series on houseplant care. Take home a plant kit '
            'at the final session.'))

    def test_needs_pickup_corroboration_in_description(self):
        """A kit-named row whose body is just the activity blurb falls through."""
        self.assertFalse(is_obvious_non_event(
            'Grab & Go: Blackout Poetry Kits',
            'Celebrate National Poetry Month by composing a poem of your own!'))

    def test_needs_a_kit_or_craft_word_somewhere(self):
        """The pickup idiom alone is not enough (puzzles, lunches, ...)."""
        self.assertFalse(is_obvious_non_event(
            'Crestwood Month Long Puzzle Grab & Go',
            'Visit the Crestwood Library anytime during March to pick up a '
            'jigsaw or word puzzle.'))

    def test_needs_a_description(self):
        self.assertFalse(is_obvious_non_event('Adult Take-Home Craft', ''))


class TestTakeHomeKitWidening20260817(unittest.TestCase):
    """The 2026-08-16 classification pass found e221467 "Take-n-Make!" (w3,
    Roosevelt Island Library) slipping the arm two different ways.

    (a) The name idiom list could not match a HYPHENATED separator, so the whole
        "Take-n-Make" / "Grab-and-Go" / "Grab 'n Go" family fell through, as did
        "Take & Make" / "Take & Create" — the same libraries' other house style.
    (b) `join us` was an absolute veto, and e221467's body opens with the
        branch's stock invitation before describing a plain kit pickup.

    Re-measured over all 191,070 events + 134,254 crawl_events (21d): 14 net-new
    events (1 live, a correct kill), 4 net-new crawl_events, every one a library
    kit pickup. 0 false positives, 0 reviewed-and-kept. Nothing the previous arm
    caught is lost.
    """

    def test_take_n_make_the_row_that_motivated_the_widening(self):
        # e221467.
        self.assertTrue(is_obvious_non_event(
            'Take-n-Make!',
            'Join us at the Roosevelt Island Library World Cup Celebration to '
            'pick up some fun craft materials to take home while supplies '
            'last!'))

    def test_hyphenated_and_take_verb_name_variants(self):
        cases = [
            'Take-n-Make!',
            'Take & Make: Mini Plushie',
            'Take and Make: Seashell Tic Tac Toe',
            'Take n Make: Adult Craft',
            'Take & Create: D.I.Y. Postcard Kits',
            "Grab 'n Go: Edible Olympic Torches",
            'Grab-and-Go Craft: 3-D Paper Frogs',
            'Kids Create Grab-and-Go: Sticker by Number',
        ]
        for name in cases:
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(
                    name, 'Pick up a craft kit at the desk while supplies '
                          'last.'))

    def test_join_us_is_only_a_soft_veto(self):
        """`join us` alone no longer rescues a plain pickup..."""
        self.assertTrue(is_obvious_non_event(
            'Take & Make Craft Kit',
            'Join us! Pick up a craft kit at the Reference Desk, first come '
            'first served.'))

    def test_join_us_still_vetoes_without_distribution_language(self):
        """...but it still does when the body names no distribution phrase."""
        self.assertFalse(is_obvious_non_event(
            'Take Home a Craft',
            'Join us for an afternoon of crafting; each attendee gets a kit.'))

    def test_hard_veto_still_absolute(self):
        """The 4-session class the arm was originally tuned around survives even
        though its body now also says "pick up a kit"."""
        self.assertFalse(is_obvious_non_event(
            'Indoor Spring: Learn Grow and Take Home Plants',
            'To celebrate the arrival of spring, we invite you to join us for '
            'this 4-session series on houseplant care. Pick up a plant kit at '
            'the final session while supplies last.'))

    def test_take_verb_family_does_not_overreach(self):
        """The take-<verb> alternation must not match unrelated titles."""
        for name, desc in (
            ('Take Note: Make Music Together',
             'Pick up an instrument and join the community band.'),
            ('Takeout Tuesday',
             'Pick up a craft kit while supplies last.'),
        ):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))


class TestProgramDeadlineNotices(unittest.TestCase):
    def test_summer_reading_logs_deadline(self):
        # e219452 — the row that motivated the rule.
        self.assertTrue(is_obvious_non_event(
            'Kids Summer Reading Ends!',
            "Thank you to all that participated in our 2026 Youth Summer "
            "Reading Program! If you haven't already: Please SUBMIT all "
            "Summer Reading logs by AUGUST 17! (even if they aren't fully "
            "completed)."))

    def test_a_film_titled_it_ends_survives(self):
        """The program-noun name gate is load-bearing: `ends$` alone matched
        the film "It Ends" seven times over the events table."""
        self.assertFalse(is_obvious_non_event(
            'It Ends',
            'A group of recent grads head out on a late night drive for grub. '
            'Submit to the terror. Last day to catch it on the big screen.'))

    def test_end_of_program_party_survives(self):
        self.assertFalse(is_obvious_non_event(
            'Summer Reading Ends!',
            'Celebrate the end of summer reading! Join us for an ice cream '
            'party — submit your logs at the door and prizes awarded.'))

    def test_echo_description_now_fires(self):
        """REVERSED 2026-08-15 by the room-booking batch (block 5).

        This assertion used to pin e214118 "Summer Reading Ends!" / "SUMMER
        READING ENDS!" as an accepted miss, on the grounds that an echoed body
        carries no deadline signal. The room-booking work re-measured the name
        gate over all 188,480 events and found only 2 rows where it matches and
        the body adds nothing — e214118 and e211149, both w3530, both junk — so
        `_description_adds_nothing` was added as a second corroboration path
        alongside the deadline-language gate.
        """
        self.assertTrue(is_obvious_non_event(
            'Summer Reading Ends!', 'SUMMER READING ENDS!'))
        self.assertTrue(is_obvious_non_event(
            'Summer Reading Ends', 'No description available.'))


class TestRoomSuffixStaysUnfiltered(unittest.TestCase):
    """Room-booking rows named after the room were considered and REJECTED.

    e219431 "Historical Society Room II" (a w3530 room booking) motivated a
    "name ends in Room <n>" pattern. Audited over all 188,480 events: 248 name
    matches, overwhelmingly REAL events — "... in the Listening Room"
    performances, "Rosa Perreo at The Onyx Room" (blank description, would
    have fired), "Marvin's Room" (film), escape rooms. Bare-org-name bookings
    ("Historial Society") are shapeless. Both stay manual suppressions; these
    tests pin the rejection so a future change has to confront it.
    """

    def test_real_events_ending_in_room_pass_through(self):
        cases = [
            ('Rosa Perreo At The Onyx Room',
             'An intimate reggaeton and perreo party inside the Onyx Room.'),
            ('Live Operator Hours: Featuring Laraaji in the Listening Room',
             'Musician and mystic Laraaji activates the immersive sound '
             'installation.'),
            ('Rosa Perreo at The Onyx Room', ''),
            ('Teen Escape Room',
             'Work together with other teens to solve puzzles and unlock '
             'clues.'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_the_actual_room_booking_rows_also_pass_through(self):
        """Documents the accepted miss: these ARE junk but stay unfiltered."""
        self.assertFalse(is_obvious_non_event(
            'Historical Society Room II', 'Historical Society Room II'))
        self.assertFalse(is_obvious_non_event(
            'Historial Society', 'No description available.'))


if __name__ == '__main__':
    unittest.main()
