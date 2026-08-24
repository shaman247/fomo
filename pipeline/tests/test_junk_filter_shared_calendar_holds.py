"""Tests for the three library / shared-calendar junk-filter arms added 2026-08-24.

The 2026-08-24 `/run-pipeline` event-type classification pass returned three of
550 newly-typed events as UNKNOWN — i.e. they were not events at all and had
reached the public map:

    231355  Closing: Labor Day Weekend 2026   (w2014 New York Society Library)
    231327  HOLD Kitchen Lithography          (w716  NYC Resistor)
    231431  Community Sponsored: RMA Book Group (w5242 Greenwich Library)

Each is the visible tip of a class, and each was measured DB-wide before the arm
shipped. Counts below are from 2026-08-24 over all 199,916 `events` and, for the
description arm, all 1,130,648 `crawl_events`.

1. `^Closing<sep>` -> `_CLOSURE_NOTICE_NAME_RE`
   4 matches, all four w2014 holiday closures (28631, 75335, 132286, 231355),
   0 false positives. The ANCHORING is the whole rule: 33 of the 37 events whose
   name merely starts with "Closing" are real ("Closing Reception", "Closing
   Party for IDENTITIES", "Closing Night With Juilliard Music", "Closing the Gap:
   Investor Breakfast"), and an unanchored "Closing:" adds "Summer Reading
   Closing: Myron the Magnificent", "Gallery Closing: …", "Early Closing: 2PM".

2. `^HOLD<sep>` / `^HOLD <lowercase-word>` -> `_HOLD_PLACEHOLDER_NAME_RE`
   40 matches out of the 54 events whose name starts with "hold", every one a
   booking placeholder, 0 false positives; 77 more rows over 60 days of
   crawl_events. The dozen `^hold` rows the arm deliberately does NOT take are
   real events and are pinned below.

3. `not open to the (general) public` in the BODY -> `_is_not_public_notice`
   10 crawl_events rows all-time / 7 distinct, 100% junk, two of which reached
   the map unsuppressed (e57177 Orchestra of St. Luke's private youth recital,
   e43668 Urban Bush Women's private engagement). Promoted to a single-signal
   rule because a library community-room booking never calls itself a "private
   event" — it just says this.

REFUTED in the same measurement and pinned below as a regression guard:

  * `neither sponsored nor endorsed by <library>` — the other half of the same
    Greenwich Library boilerplate. It is a blanket disclaimer stapled onto EVERY
    outside-group booking, public ones included: its 2-row hit set contains
    e228086 "Community Sponsored: Little Readers, Big Creators", a real, live
    children's storytime. Do not add it.
  * `closed to the (general) public` as a single signal — 152 crawl rows, and
    BCPC's real, public TGNC Swim Night is described as "swimming in a pool
    closed to the public".
  * `invitation only` / `invite-only` as a single signal — 256 crawl rows,
    including Downtown Music Gallery's anniversary in-store series and Fabrik's
    "Breakfast With Friends", all real listed events.
  * `^hold for <thing>` — 2 rows DB-wide, both already suppressed, against a
    live collision with film titles of the "Hold for Ransom" shape.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import is_obvious_non_event

BLANK = 'No description available.'


class TestClosingColonNotices(unittest.TestCase):
    def test_the_four_nysl_holiday_closures(self):
        for name, desc in (
                ('Closing: Labor Day Weekend 2026',
                 'The Library is closed Saturday, September 5, Sunday, '
                 'September 6, and Monday, September 7, for Labor Day weekend.'),
                ('Closing: Easter 2026', 'The Library is closed all day for the Easter holiday.'),
                ('Closing: Memorial Day Weekend 2026', 'The Library is closed for Memorial Day weekend.'),
                ('Closing: Presidents Day 2026',
                 'The Library will be closed all day in observance of the Presidents Day holiday.')):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, desc))

    def test_dash_and_blank_body_variants(self):
        self.assertTrue(is_obvious_non_event('Closing - Thanksgiving 2026', BLANK))
        self.assertTrue(is_obvious_non_event('Closing: Winter Break', ''))

    def test_closing_receptions_and_parties_survive(self):
        """The word "Closing" leading a real occasion, without the separator."""
        for name, desc in (
                ('Closing Reception with DJ Pagan',
                 'Closing reception for the It Takes a Village exhibition featuring music by DJ Pagan.'),
                ('Closing Party for IDENTITIES',
                 "Join us to celebrate the closing of Hidemi Takagi's show IDENTITIES."),
                ('Closing Night With Juilliard Music, Dance, and Drama', BLANK),
                ('Closing Ceremony', 'Lady Ludd guides us into the future.'),
                ('Closing the Gap: Investor Breakfast with Fund Her Network',
                 'An investor breakfast aimed at addressing the funding gap for female founders.'),
                ('Closing Tour of _Larry Bell_',
                 'Join us for a private tour of Larry Bell at Dia Beacon before the exhibition closes.')):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_mid_name_closing_colon_is_not_anchored(self):
        """"Summer Reading Closing: …" is a real library party, not a closure."""
        for name, desc in (
                ('Summer Reading Closing: Myron the Magnificent',
                 'Help us celebrate our Summer Reading Closing at the Library as Myron the '
                 'Magnificent brings an unforgettable magic show for children and families.'),
                ('Gallery Closing: Reynaldo García Pantaleón • Color de Dolor',
                 "The closing event for the art exhibition 'Color de Dolor'."),
                ('WAN Season Closing: Katy Concert – Last Chance to Name Your Price',
                 'A WAN season closing featuring a Katy concert.')):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))


class TestSharedCalendarHoldPlaceholders(unittest.TestCase):
    def test_the_rows_hand_suppressed_on_2026_08_24(self):
        for name in ('HOLD Kitchen Lithography', 'HOLD: Disengineering',
                     'Hold: Kari', 'Hold: Trees'):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, BLANK))

    def test_hold_prefix_fires_even_with_a_real_looking_body(self):
        """The prefix is the booker's own "not confirmed" marker; the body is
        whatever the eventual session would be, so it cannot be a gate."""
        self.assertTrue(is_obvious_non_event(
            'Hold: Synth Night',
            'An evening for synthesizer enthusiasts to bring their gear and share '
            'their love for electronic sound.'))
        self.assertTrue(is_obvious_non_event(
            'HOLD: Laser Cutting Class',
            'Harness the power of an Epilog 60 Watt Laser! In this class you will '
            'learn everything you need.'))
        self.assertTrue(is_obvious_non_event(
            'HOLD: Indian Harbor Condo Association Meeting',
            'Please contact May Reilly with any questions'))

    def test_dash_separated_library_room_holds(self):
        for name, desc in (('Hold-Peggy Belles', 'meeting'),
                           ('Hold-Devon', 'Weekly community meeting.'),
                           ('Hold-Mt St Ursula', 'A community meeting event held at the Will Library.'),
                           ('Hold - Itp Showcase', BLANK)):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, desc))

    def test_real_events_whose_name_starts_with_hold(self):
        """The separator is what keeps these alive — do not drop it."""
        for name, desc in (
                ('Hold It Down Nyc',
                 'Hold It Down NYC is a celebration of New York City music, DJs, and culture.'),
                ('Hold Me Tight (Serre-moi fort)',
                 'A screening of the dramatic film "Hold Me Tight (Serre-moi fort)".'),
                ('Hold On To Your Butts',
                 'A live, shot-for-shot parody of Jurassic Park.'),
                ('Hold Up Movie Club',
                 'A regular film screening event hosted by the Hold Up Movie Club.'),
                ('Hold Em In Harlem',
                 'An annual fundraiser for The Classical Theatre of Harlem featuring a poker tournament.'),
                ('Hold The Phone! & Some Beers',
                 'A traveling education series focused on reframing the narrative around '
                 "children's smartphone use."),
                ("Hold On To Your Music: A Mother's Legacy",
                 'This film chronicles the story of the Kindertransport.')):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_all_caps_title_is_not_a_hold(self):
        """A feed that upper-cases every name must not donate its H-titles."""
        for name in ('HOLD YOUR BREATH', 'HOLD ME TIGHT', 'HOLD THE DARK'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, BLANK))

    def test_hold_inside_a_word_or_mid_name(self):
        self.assertFalse(is_obvious_non_event('Holdfast: A New Play', BLANK))
        self.assertFalse(is_obvious_non_event('Household Hazardous Waste Drop-Off', BLANK))
        self.assertFalse(is_obvious_non_event(
            'Threshold: Chamber Music', 'An evening of chamber music.'))

    def test_hold_for_thing_deliberately_not_taken(self):
        """Measured and left out — 2 rows DB-wide vs. a "Hold for Ransom" film
        title collision. If this ever starts firing, the arm was widened."""
        self.assertFalse(is_obvious_non_event('Hold for Ransom', BLANK))


class TestNotOpenToThePublicBody(unittest.TestCase):
    def test_greenwich_library_community_room_booking(self):
        self.assertTrue(is_obvious_non_event(
            'Community Sponsored: RMA Book Group',
            'This event is not open to the public. This event and the content thereof '
            'are neither sponsored nor endorsed by Greenwich Library. Event Contact: '
            'Gerald Stinson Contact Email: jstinoiii@gmail.com'))

    def test_the_seven_distinct_corpus_rows(self):
        for name, desc in (
                ('FAB5 @ The Jacob Javits Center',
                 'FAB5 is honored to be performing for the 40th Anniversary celebration of '
                 'the Jacob Javits Center. Private event, not open to the public.'),
                ('Spring Recital',
                 "The Spring Recital is a private youth recital event featuring students "
                 "from the Youth Orchestra of St. Luke's. This event is not open to the "
                 "general public."),
                ('BOLD: Collab Lab',
                 'Urban Bush Women facilitates artistic creation through the Collaboration '
                 'Lab. This event is a private engagement and not open to the public.'),
                ('Ubw Ebx: Entering, Building, and Exiting Community',
                 "This workshop is rooted in Urban Bush Women's value-centered approach to "
                 'working with communities. Please note that this is a private engagement '
                 'and not open to the public.'),
                ('Recirculation Closed',
                 'Notification indicating that the Recirculation space is currently not '
                 'open to the public. Please check back for updated operating hours.')):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, desc))

    def test_a_private_portion_of_a_public_event_survives(self):
        """The veto shape the corpus does not yet contain but easily could."""
        for name, desc in (
                ('Spring Gala Concert',
                 'The concert is free and open to all. The reception afterwards is not '
                 'open to the public.'),
                ('Open Studios Weekend',
                 'Tour the artist studios all afternoon. Note that the second half of the '
                 'day is not open to the public while judging takes place.'),
                ('Community Film Night',
                 'A free screening for all ages. The director talkback is not open to the '
                 'public.')):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))


class TestRefutedDescriptionArms(unittest.TestCase):
    """Regression guards for the three phrases measured and REFUTED."""

    def test_neither_sponsored_nor_endorsed_is_not_a_junk_signal(self):
        """e228086, a real live children's storytime carrying the disclaimer."""
        self.assertFalse(is_obvious_non_event(
            'Community Sponsored: Little Readers, Big Creators',
            'This event, and the content thereof, is neither sponsored nor endorsed by '
            'Greenwich Library. Event contact: Meredith Barth'))

    def test_closed_to_the_public_alone_is_not_a_junk_signal(self):
        """BCPC's real, public TGNC Swim Night."""
        self.assertFalse(is_obvious_non_event(
            'TGNC Swim Night',
            "BCPC's monthly TGNC Swim Nights provide folks of trans experience safe and "
            'affirming spaces to connect and swim as their authentic selves. The event '
            'includes a social hour followed by swimming in a pool closed to the public.'))

    def test_invite_only_alone_is_not_a_junk_signal(self):
        for name, desc in (
                ('DMG 31st Anniversary Celebration',
                 'An invite-only celebration featuring solo guitar sets, book signings, and '
                 'a jam session, which will be filmed for a future online broadcast.'),
                ('Breakfast With Friends: Everything Is Marketing',
                 'A monthly invite-only series bringing together women and non-binary folks '
                 'working across creative fields to discuss our relationship to our work.')):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_rental_prefix_is_still_not_junk(self):
        """Documented false-positive shape — none of the three arms may take it."""
        for name in ('RENTAL: Birthday Party', 'RENTAL: Corporate Offsite',
                     'Rental: Wedding Reception'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, BLANK))


if __name__ == '__main__':
    unittest.main()
