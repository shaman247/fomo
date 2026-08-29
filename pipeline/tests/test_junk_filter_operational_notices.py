"""Tests for the operational-notice and housing-corp rules in is_obvious_non_event.

Added 2026-08-22. The event-type classification pass produced 10 UNKNOWN rows —
junk that reached the map and was only caught downstream when the classifier
could not assign it a type. Four gates were added for the three recurring shapes
among them; the other UNKNOWNs were deliberately left alone (see the NOT COVERED
class at the bottom).

Every rule below was precision-audited over the full 198,068-event corpus before
being shipped, exactly as `test_junk_filter_hours_notices.py` describes. The
counts quoted in each docstring are that audit, frozen. **Do not loosen any of
these without re-running the corpus audit** — the housing-corp rule in particular
started far wider and had to be cut down after the audit caught real events.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import (is_obvious_non_event, _is_early_close_notice,
                       _is_admin_deadline, _is_maintenance_tail_block,
                       _is_housing_corp_booking)


class TestEarlyCloseNotice(unittest.TestCase):
    """17 corpus matches, all genuine closure notices, 0 false positives.

    Name-only by design: the body is always a real sentence explaining the early
    close, so a description gate would spare every one of them.
    """

    def test_the_row_that_reached_the_map(self):
        self.assertTrue(is_obvious_non_event(
            'Greenwich Library Early Close (5pm ET)',
            'The Greenwich Library will close at 5 pm today due to Summer hours'))

    def test_closing_early_variants(self):
        for name in ('Bookstore Closing Early',
                     "Shops Closing Early for New Year's Eve",
                     'New Year’s Eve: Early Closing',
                     'Early Closing: 2PM',
                     'Library Closing at 2:00PM',
                     'Main Library Closing Early'):
            with self.subTest(name=name):
                self.assertTrue(_is_early_close_notice(name))

    def test_a_described_body_does_not_rescue_it(self):
        # The explanatory body is the norm for this shape, not a signal of realness.
        self.assertTrue(is_obvious_non_event(
            'Top of the Rock and The Rink Early Closing',
            'Information regarding limited hours for the observation deck'))

    def test_real_events_are_kept(self):
        for name in ('Closing Night Party', 'Closing Reception: Ash Allen',
                     'Early Bird Yoga', 'The Closer', 'Closing Arguments: A Play'):
            with self.subTest(name=name):
                self.assertFalse(_is_early_close_notice(name))


class TestAdminDeadline(unittest.TestCase):
    """38 corpus matches, all genuine deadlines, 0 false positives.

    Anchored at the START of the name so a real program that merely mentions a
    deadline downstream survives.
    """

    def test_the_rows_that_reached_the_map(self):
        self.assertTrue(is_obvious_non_event(
            'Last Day to Turn in Reading Logs',
            'Ages 0-12. For every 5 books your child reads, they will have a chance to win'))
        self.assertTrue(is_obvious_non_event(
            'Photography Show Registration Closes', 'No description available.'))

    def test_deadline_variants(self):
        for name in ('Last Day to Apply for Spring 2026 Graduation',
                     'DEADLINE: NYU Startup Bootcamp',
                     'Teen Council Spring 2026 Application Deadline',
                     'Young Poets Submissions Due',
                     'Writing on Race and Immigration: Applications Due',
                     'Last Day to Complete Spring 2026 Residency'):
            with self.subTest(name=name):
                self.assertTrue(_is_admin_deadline(name))

    def test_start_anchor_spares_a_real_program(self):
        # A real event that merely mentions a deadline is not a deadline row.
        for name in ('Poetry Workshop (registration closes Friday)',
                     'Open Studio — sign up by the deadline',
                     'Application Workshop: How to Apply for Grants'):
            with self.subTest(name=name):
                self.assertFalse(_is_admin_deadline(name))


class TestMaintenanceTailBlock(unittest.TestCase):
    """1 corpus match, 0 false positives.

    Tail-anchoring alone is NOT safe, which is why the description gate exists.
    """

    def test_the_row_that_reached_the_map(self):
        self.assertTrue(is_obvious_non_event(
            'Discovery Lab Maintenance', 'Dicovery Lab Closed till 10am'))

    def test_blank_body_also_fires(self):
        self.assertTrue(_is_maintenance_tail_block('Community Room Maintenance', ''))
        self.assertTrue(_is_maintenance_tail_block(
            'Community Room Maintenance', 'No description available.'))

    def test_real_maintenance_classes_are_kept(self):
        # These are the false positives the description gate exists to prevent.
        for name, desc in (
                ('Bike Maintenance', 'Learn to fix a flat and tune your derailleur with our mechanic.'),
                ('Car Maintenance', 'A hands-on intro to checking your oil, tires and brakes.'),
                ('Home Maintenance', 'A workshop on seasonal upkeep for new homeowners.')):
            with self.subTest(name=name):
                self.assertFalse(_is_maintenance_tail_block(name, desc))
                self.assertFalse(is_obvious_non_event(name, desc))


class TestHousingCorpBooking(unittest.TestCase):
    """1 corpus match, 0 false positives — deliberately narrow.

    An earlier draft keyed on a generic "association|inc|corp" tail and produced
    7 false positives out of 10 corpus matches. Those are frozen below as
    negative cases; they are the reason this rule lists only housing/condo
    entity types.
    """

    def test_the_row_that_reached_the_map(self):
        self.assertTrue(is_obvious_non_event(
            'Huntington Village Coop / Nathan Hale Owners Corp',
            'No description available.'))

    def test_housing_entity_variants(self):
        for name in ('Nathan Hale Owners Corp', 'Parkview Condominium Association',
                     'Riverside Tenants Association', 'Sunnyside Co-op Board'):
            with self.subTest(name=name):
                self.assertTrue(_is_housing_corp_booking(name, ''))

    def test_the_false_positives_that_forced_the_narrowing(self):
        # Real programs that an "association|inc" tail rule wrongly matched.
        for name in ('Street Tree Care w/ Decatur Block Association',
                     'Street Tree Care w/ 95th Street Block Association',
                     'Celebrate Lunar New Year with the New York Hua Xia Arts Association',
                     'Music Storytime With Intersection Music and Arts, Inc.'):
            with self.subTest(name=name):
                self.assertFalse(_is_housing_corp_booking(name, ''))
                self.assertFalse(is_obvious_non_event(name, ''))

    def test_civic_associations_are_kept(self):
        # The review doc is explicit that civic engagement stays on the map.
        self.assertFalse(is_obvious_non_event('RVC Civic Association', 'No description available.'))
        self.assertFalse(is_obvious_non_event('Decatur Block Association', ''))

    def test_a_described_program_survives(self):
        self.assertFalse(_is_housing_corp_booking(
            'Nathan Hale Owners Corp',
            'Open to the public: a panel on co-op governance with Q&A and refreshments.'))


class TestDeliberatelyNotCovered(unittest.TestCase):
    """UNKNOWN rows from the same 2026-08-22 batch that were LEFT ALONE.

    Each was judged too risky to filter for the yield of a single row. They are
    asserted here so that a future widening of these rules is a deliberate,
    visible change to this file rather than a silent side effect.
    """

    def test_ambiguous_bare_names_are_not_filtered(self):
        # Could each be a real show; only a missing description argues otherwise.
        self.assertFalse(is_obvious_non_event("That's Weird!", 'No description available.'))
        self.assertFalse(is_obvious_non_event('New Horizons', 'No description available.'))

    def test_bare_holiday_observance_is_not_filtered(self):
        # Blocking bare holiday names risks "Indigenous People's Day Celebration".
        self.assertFalse(is_obvious_non_event(
            'Columbus Day / Indigenous People’s Day', 'No description available.'))

    def test_described_exhibit_installation_is_not_filtered(self):
        # Still not filtered, and now deliberately so: the 2026-08-29 exhibit-
        # logistics arm (TestExhibitLogistics) covers "installation" ONLY when
        # the body adds nothing, because filtering a described one risks
        # suppressing genuine exhibition openings.
        self.assertFalse(is_obvious_non_event(
            'Art Gallery Exhibit INSTALLATION - Artist: Alex Tric',
            'Art exhibit installation will take place in the Main Art Gallery'))

    def test_nonprofit_service_orgs_are_not_filtered(self):
        # Narrower than the housing-corp rule on purpose: these are service
        # organisations, and a room booking is indistinguishable by name alone
        # from a program they host.
        self.assertFalse(is_obvious_non_event(
            "(FCA) Family & Children's Association", 'No description available.'))
        self.assertFalse(is_obvious_non_event(
            'The Center for Developmental Disabilities, Inc.',
            'Individuals from the Center for Developmental Disabilities, Inc. visit weekly.'))


class TestExhibitLogistics(unittest.TestCase):
    """(5l) Exhibit teardown/installation logistics. Added 2026-08-29.

    Audited over all 204,375 events plus 102,518 crawl_events from the previous
    14 days: the teardown arm adds 8 event rows / 6 distinct names, every one a
    genuine logistics row (all archived or hand-suppressed), 0 false positives;
    the installation arm adds 1 row, 0 false positives. Nothing previously
    flagged was lost.
    """

    def test_the_row_that_reached_the_map(self):
        # e235700, w3530 BCCLS Libraries, hand-suppressed at classification.
        self.assertTrue(is_obvious_non_event(
            'Exhibit removal - Suzi Gerace', 'No description available.'))

    def test_teardown_family(self):
        for name in ('Exhibit removal - Suzi Gerace',
                     'HAFA - Art display breakdown',
                     'NAWA Art drop off',
                     'Photo Show Drop Off',
                     'Art Pickup',
                     'Exhibition Take-Down',
                     'Art De-Installation'):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, ''))

    def test_teardown_fires_even_with_a_real_body(self):
        # These rows routinely explain the move in a full sentence, so a
        # description gate would spare every one of them.
        self.assertTrue(is_obvious_non_event(
            'Art Pickup',
            "Pick up artwork following the conclusion of the 'Extremes' "
            'exhibition by Susan Kasson Sloan.'))

    def test_blank_bodied_installation_hold(self):
        self.assertTrue(is_obvious_non_event(
            'Hold for Art Exhibit Installation', 'No description available.'))

    def test_real_public_artwork_survives(self):
        # e199419, live and reviewed. Spared by the installation arm's body gate.
        self.assertFalse(is_obvious_non_event(
            'Illumination NYC\u2019s temporary art installation',
            'Illumination NYC\u2019s temporary art installation immerses visitors in an '
            'interactive journey through the rich history and diverse cultures '
            'of the United States.'))

    def test_art_hangs_and_strikes_are_not_filtered(self):
        # "hang" and "strike" are deliberately absent from the vocabulary.
        self.assertFalse(is_obvious_non_event(
            'Teen Art Hang',
            'An open and creative space for NYC teens to work on thematic art '
            'projects in a studio setting.'))
        self.assertFalse(is_obvious_non_event('Teen Art Hang', ''))
        self.assertFalse(is_obvious_non_event('Art Strike', ''))

    def test_unrelated_drop_offs_survive(self):
        # The logistics word must sit immediately after the art noun.
        self.assertFalse(is_obvious_non_event('Art Supply Drop-Off', ''))
        self.assertFalse(is_obvious_non_event('Art Drop-In Studio', ''))


class TestVenueSpaceDesignation(unittest.TestCase):
    """(5m) A venue room published as an event. Added 2026-08-29.

    Audited over the same 204,375-event + 102,518-crawl_event corpus: 2 matches
    ("Front Bar @ GP Midtown", "Rooftop @ Exchange Place"), both blank-bodied
    room rows, 0 false positives.
    """

    def test_the_row_that_reached_the_map(self):
        # e235378, w3574 The Grisly Pear Comedy Club.
        self.assertTrue(is_obvious_non_event(
            'Front Bar @ GP Midtown', 'No description available.'))

    def test_sibling_shapes(self):
        for name in ('Rooftop @ Exchange Place',
                     'Back Room at The Ace Hotel',
                     'The Patio @ Threes'):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, ''))

    def test_a_described_room_row_survives(self):
        # "The Rooftop at Pier 17 Halloween" is a real party.
        self.assertFalse(is_obvious_non_event(
            'The Rooftop at Pier 17 Halloween',
            'A Halloween party on the Rooftop at Pier 17 with DJs and costumes.'))

    def test_a_program_held_in_the_room_survives(self):
        # A colon or trailing program word breaks the whole-name anchor.
        self.assertFalse(is_obvious_non_event(
            'Studio at the Woods: Adult Ceramics', ''))
        self.assertFalse(is_obvious_non_event('Bar Trivia at The Long Room', ''))
        self.assertFalse(is_obvious_non_event('Comedy at the Basement', ''))


class TestBareGivenNameDeliberatelyNotFiltered(unittest.TestCase):
    """e235790 "Kyle" (w3530 BCCLS Libraries) is NOT filtered, on purpose.

    A bare given name with an empty body is a patron room booking at a library
    and junk in that context, but the shape is indistinguishable from a real
    listing anywhere else. Measured 2026-08-29 with a 250-name common-first-name
    list over the 102,518-row recent crawl corpus: 3 matches, and 2 of the 3 are
    real film screenings — "Laura" at Sag Harbor Cinema (e194372, LIVE) and
    "Michael" at Rooftop Cinema Club / Nitehawk / Stuart Cinema. Over all 204,375
    events it also takes "Emma" at Frigid New York. A rule that kills a live
    screening to catch one library room hold is the wrong trade, so it was not
    shipped.
    """

    def test_bare_given_names_survive(self):
        for name in ('Kyle', 'Laura', 'Michael', 'Emma', 'Carmen', 'Evita'):
            with self.subTest(name=name):
                self.assertFalse(
                    is_obvious_non_event(name, 'No description available.'))


class TestCallToArtists(unittest.TestCase):
    """The `call to artists` arm of `_NON_EVENT_NAME_PATTERNS`. Added 2026-08-29.

    Arts councils use "Call to Artists" and "Call for Artists" interchangeably;
    only the `for` spelling was matched. Audited over all 204,375 events: the
    `to` arm adds 6 rows / 5 distinct names, every one a genuine call for
    entries, 0 false positives.
    """

    def test_the_row_that_reached_the_map(self):
        # e235646, w1716 Huntington Arts Council.
        self.assertTrue(is_obvious_non_event(
            'The Art Guild presents Call to Artist: Abstract Perspectives: '
            'Juried Art & Competition',
            'Deadline: Monday, September 14, 2026 Exhibit Dates: October 4-24'))

    def test_sibling_spellings(self):
        for name in ('SOAPBOX: A Call To Artists & Performers',
                     'Call to Artists-The Long Island Fine Art Invitational',
                     'Huntington Arts Council CALL TO ARTISTS Field Notes',
                     'Calls for Submissions'):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, ''))

    def test_call_for_artists_still_matches(self):
        self.assertTrue(is_obvious_non_event('Call for Artists 2026', ''))

    def test_unrelated_calls_survive(self):
        self.assertFalse(is_obvious_non_event('A Call to Action Rally', ''))
        self.assertFalse(is_obvious_non_event('Curtain Call Cabaret', ''))



if __name__ == '__main__':
    unittest.main()
