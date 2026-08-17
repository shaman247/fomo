"""Tests for the facility-closure rule in is_obvious_non_event.

Essex County Parks republishes "Hendricks Field Golf Course Closed" /
"Francis A Byrne Golf Course Closed" (168761 / 168762) every run, and a human
re-suppresses them every run. Nothing here ever reached the map — the whole
class is a CHURN cost, not a correctness bug.

The pre-existing closure family in `_NON_EVENT_NAME_RE` only knows a fixed list
of venue nouns ("museum|library|park|gallery|office|…") and the punctuated
"Closed: …" / "Closed for …" shapes, so a facility it has never heard of (a golf
course, a taproom, "BCM", "Recirculation") slips through. This rule generalises
it to the word anywhere in the name, paid for with a corroborating description.

Measured over all 185,947 events (`.scratch/closure_precision.py`):
    name-gate matches                    199
    vetoed (early-closing / registration) 11
    spared by the description gate        26
    WOULD FIRE                           162
      of those, currently live             0
    of the 162, not caught by any
    pre-existing rule (the new yield)     90

**The description gate is keyed on `closed|closure` and deliberately NOT on
`closing`/`closes`.** That is exactly what spares the real events below: an
early-closing notice's body says the venue "will close early", never "closed".

**`closed(?!\\s*caption)` is required, not decoration** — BCCLS runs a real
"Closed Captioning Film Club". The same false positive was hit and fixed on
2026-08-05 in the w3530 admin-marker regex.

The `^no <noun>` / `^[CANCELLED]` sibling arm ("No Public Sessions Today",
"[CANCELLED] ESL Conversation Class") is NOT implemented here: it is much
riskier ("No Kidding! Comedy", "No Lights No Lycra" are real events) and must be
measured separately before it ships.

Do not loosen this rule without re-running `.scratch/closure_precision.py`.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import is_obvious_non_event, _is_closure_notice


class TestClosureNoticesAreJunk(unittest.TestCase):
    """The rows that actually churn, plus the shapes the old rule missed."""

    def test_essex_county_golf_course_closures(self):
        """168761 / 168762 — the pair that raised this task. Blank body."""
        self.assertTrue(is_obvious_non_event(
            'Hendricks Field Golf Course Closed', 'No description available.'))
        self.assertTrue(is_obvious_non_event(
            'Francis A Byrne Golf Course Closed', 'No description available.'))

    def test_blank_and_empty_descriptions_both_corroborate(self):
        self.assertTrue(_is_closure_notice('Hendricks Field Golf Course Closed', ''))
        self.assertTrue(_is_closure_notice('Hendricks Field Golf Course Closed', None))

    def test_closure_language_in_the_description_corroborates(self):
        self.assertTrue(is_obvious_non_event(
            'Heckscher WILD! Summer Closure Week',
            'Heckscher WILD! is closed to the public for annual end-of-summer '
            'maintenance.'))

    def test_facilities_the_old_venue_noun_list_never_knew(self):
        cases = [
            ('BCM Closed', "Brooklyn Children's Museum is closed Thursday, December 25."),
            ('Taprooms Closed',
             'The Strong Rope Brewery taprooms will be closed all day.'),
            ('Recirculation Closed',
             'Please note that the Recirculation project site will be closed to '
             'the public on this date.'),
            ('OS Nyc Closed', 'The venue is closed for this date.'),
            ('Monday Closure', 'No description available.'),
            ('Special Closure',
             'The museum will be closed on this day in observance of the holiday.'),
            ('Spring Break (Bms Closed)',
             'The music school is completely closed for the spring break holiday.'),
            ('All NYPL locations closed',
             'All branches of the New York Public Library will be closed for the day.'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, desc))


class TestRealEventsWithClosedOrClosureInTheName(unittest.TestCase):
    """Frozen from the corpus audit — every one of these is a REAL event."""

    def test_closed_curtain_the_panahi_film(self):
        """e8452. A bare `closed` name gate with no description gate eats this."""
        self.assertFalse(is_obvious_non_event(
            'Closed Curtain',
            'Two fugitives—a man with a dog and a young woman—take refuge in a '
            'villa by the Caspian Sea. This allegorical drama explores isolation '
            'and artistic freedom.'))

    def test_saidah_gets_closure_is_a_solo_show(self):
        """e42435."""
        self.assertFalse(is_obvious_non_event(
            'Saidah Gets Closure',
            'Saidah Arrika Ekulona stars in this hilarious solo exploration of '
            'the lengths we go to for emotional resolution.'))

    def test_poetic_closure_is_a_writing_workshop(self):
        """e50432."""
        self.assertFalse(is_obvious_non_event(
            'Remote 3-Hour Workshop: Megan Pinto: Poetic Closure',
            'An exploration of strategies for how fixed and free verse poems '
            'operate, with a focus on writing effective endings.'))

    def test_closed_captioning_film_club_survives(self):
        """BCCLS runs this for real — the `(?!\\s*caption)` lookahead earns its keep."""
        for desc in ('', 'No description available.',
                     'A monthly film club screening with closed captions on.'):
            with self.subTest(desc=desc):
                self.assertFalse(_is_closure_notice('Closed Captioning Film Club', desc))
        self.assertFalse(_is_closure_notice('Closed Caption Screening: Wicked', ''))

    def test_other_real_events_that_merely_contain_the_word(self):
        cases = [
            ('Behind Closed Doors: An Intimate Lebanese Speakeasy Dinner',
             'A hidden Lebanese dinner featuring candlelight and soulful flavors.'),
            ('Why is the Beach Closed?',
             'An introduction to identifying Harmful Algal Blooms (HABs) and '
             'other hazards.'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))


class TestEarlyClosingHoursNoticesAreSpared(unittest.TestCase):
    """An early closure changes the HOURS; the venue is open, just for less time.

    These are a different family from "the facility is shut", and the scheduled
    task pins them as must-survive. Two independent things spare them: the name
    veto, and the description gate ignoring "closing"/"closes".
    """

    def test_early_closure_with_a_clock_time(self):
        """e21019."""
        self.assertFalse(is_obvious_non_event(
            'Early Closure: 2 PM Saturday, January 31',
            'The museum will be closing early for the public on Saturday, '
            'January 31. Please plan your visit accordingly as regular hours are '
            'shortened.'))

    def test_early_closure_survives_even_with_a_blank_description(self):
        """The name veto, not the description, is doing the work here."""
        self.assertFalse(_is_closure_notice('Early Closure: 2 PM Saturday, January 31', ''))
        self.assertFalse(_is_closure_notice('Bookstore Early Closure', ''))
        self.assertFalse(_is_closure_notice("Closed Early for New Year's Eve", ''))

    def test_closing_early_language_alone_does_not_corroborate(self):
        """e63713 — the body says "close early", which must not read as closure."""
        self.assertFalse(is_obvious_non_event(
            'Early Closure: 11:00am-3:00pm',
            'The museum will close early to prepare for a special musical '
            'performance event.'))

    def test_a_real_event_whose_signup_closed_survives(self):
        """e34944 / e144899 — "(Registration Closed)" is about the sign-up."""
        self.assertFalse(_is_closure_notice(
            'Drag Story Hour: Celebrating Community (Registration Closed)', ''))
        self.assertFalse(_is_closure_notice('Storytime Chess (Registration Closed)', ''))


class TestAcceptedMisses(unittest.TestCase):
    """Junk that stays unfiltered on purpose. Missing junk is the safe direction.

    Both bodies avoid the words "closed"/"closure" entirely, so the description
    gate cannot corroborate. Widening it to catch these would cost the real
    events pinned above.
    """

    def test_closed_for_private_event(self):
        """38318 / 60244 — bodies say "unavailable" / "not open".

        THIS rule spares them; the pre-existing `closed\\s+(for|to the public…)`
        name pattern in `_NON_EVENT_NAME_RE` is what actually catches them, which
        is why `is_obvious_non_event` still returns True.
        """
        self.assertFalse(_is_closure_notice(
            'Closed For a Private Event',
            'The venue is hosting a private event and is not open to the '
            'general public tonight.'))
        self.assertTrue(is_obvious_non_event(
            'Closed For a Private Event',
            'The venue is hosting a private event and is not open to the '
            'general public tonight.'))

    def test_school_recess_with_a_paused_classes_body(self):
        self.assertFalse(is_obvious_non_event(
            'Mid-Winter Recess (Bms Closed, Open for Makeups)',
            'Regular classes are paused for the mid-winter break. However, the '
            'building remains open for makeup lessons.'))


class TestNegationArmNotImplemented(unittest.TestCase):
    """The `^no <noun>` / `^[CANCELLED]` sibling is deliberately NOT in this rule.

    It was raised in the same scheduled task and explicitly deferred for its own
    measurement — plenty of real events start with "No". These assertions pin
    the current scope so a future change has to confront the decision rather
    than fold the arm in unmeasured.
    """

    def test_negation_shaped_closures_still_pass_through(self):
        for name in ('No Public Sessions Today',
                     'NO Public Session Skating (**NO SESSIONS TODAY)',
                     '[CANCELLED] ESL Conversation Class'):
            with self.subTest(name=name):
                self.assertFalse(_is_closure_notice(name, ''))

    def test_real_events_starting_with_no_are_untouched(self):
        for name in ('No Kidding! Comedy', 'No Lights No Lycra', 'No Pants Subway Ride'):
            with self.subTest(name=name):
                self.assertFalse(_is_closure_notice(name, ''))


if __name__ == '__main__':
    unittest.main()
