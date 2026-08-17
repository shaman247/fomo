"""Tests for the room-booking-calendar rules (block 5) in is_obvious_non_event.

Some venues publish their internal room-reservation calendar on the same feed
as their public programming, so staff meetings, third-party private bookings,
maintenance blocks and hours notices reach the extractor looking like events.
BCCLS Libraries (w3530, 77 member libraries on LibCal) produced 13 of the 14
rows the event-type classifier could only label UNKNOWN on 2026-08-08:
213954 Summer Hours (2 PM Close), 213958 Summer Saturday Hours, 213967 No
Storytime, 213986 [Outside Org] Imani, 213991 Repair Work, 213997 [Outside Org]
Aging in Montclair, 214016 Wedding, 214085 Booked for Staff, 214118 Summer
Reading Ends!, 214168 Patron Reservation, 214250 Dept Head Mtg., 214264
Opportunity Center, 214313 Soccer Private Meeting.

Measured over all 188,480 events (.scratch/rb_precision2.py before shipping,
.scratch/rb_verify.py after): 66 rows caught, 53 of them net-new, **53 true
junk / 0 false positives**, and exactly one live — 186516 "Baby Shower" at Glow
Cultural Center (w3009), itself a booking calendar.

Deliberately NOT shipped, each with its own test class below:
  - the `[Outside Org]` bracket-prefix arm (TestBracketPrefixStaysUnfiltered),
  - a bare `^Booked` prefix arm (TestBookedPrefixStaysUnfiltered),
  - "Opportunity Center" and other bare room names (no signal at all),
  - the general `^No <noun>` / `[CANCELLED]` family, still deferred by
    test_junk_filter_closure_notices.TestNegationArmNotImplemented.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import (  # noqa: E402
    is_obvious_non_event,
    _is_org_room_booking,
    _is_private_booking_name,
    _is_room_reservation,
    _is_seasonal_hours_notice,
)


class TestPrivateBookings(unittest.TestCase):
    """(5a) "Private <meeting|event|session|function|use|hire>" titles."""

    def test_bccls_private_meeting_rows(self):
        # e214313, e118296, e133089, e210911, e95570, e119615, e130051.
        for name, desc in (
                ('Soccer Private Meeting', 'Soccer Private Meeting'),
                ('Private Meeting',
                 'A private meeting held at the Roseland Free Public Library.'),
                ('Private Meeting', 'No description available.'),
                ('Private Session', 'Private Session'),
                ('Private Session - Up Lift', 'No description available.'),
                ('Private Event', 'No description available.'),
                ('Private Event - Girl Scouts',
                 'A private event for the Girl Scouts held at the Roseland '
                 'Free Public Library.')):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, desc))

    def test_studio_invitation_only_parties(self):
        """ArteVino-style private hires — the biggest corpus family (24 rows)."""
        self.assertTrue(is_obvious_non_event(
            "Julia O'Connors Bridal Shower - Private Event",
            "A private in-studio bridal shower celebration for Julia "
            "O'Connor. This 3-hour event is by invitation only."))
        self.assertTrue(is_obvious_non_event(
            "Kiaan's 6th Birthday - VIP Private Event",
            'A VIP private 6th birthday celebration in-studio for Kiaan and '
            'his invited friends.'))

    def test_venue_marketing_for_private_hire(self):
        # e34344, e90993 — the venue selling its space, not hosting anything.
        self.assertTrue(is_obvious_non_event(
            'SUMMIT Private Events',
            'Explore a premier private event space curated by world-renowned '
            'Chef Daniel Boulud, perfect for hosting exclusive gatherings.'))
        self.assertTrue(is_obvious_non_event(
            'Private Event – Yours Could Be Next!',
            'Book a birthday, corporate event, or special celebration at The '
            'RAT NYC theater.'))

    def test_rezclick_private_party_bookings(self):
        """`party` arm, added 2026-08-17 for the class-booking calendars.

        Painting Lounge (w1190) and w28 publish every reserved slot in the same
        rezclick feed as the public classes, carrying the client's name and the
        painting they booked — so the merger used to fold them into the public
        class of that painting. Measured over all 191,070 events: 80 net-new
        rows caught, all bookings, zero live.
        """
        for name in (
                'Private Party',
                'private party (Tori)',
                'Private Party - Ryan W. / NYU - Starry Night Over Manhattan',
                'Private Party - Mohamed T. / CUNY - Brooklyn College Students '
                '(2hr:Midtown:Front)',
                "Private Party - Amber P. / Galentine's Event - Big Sunflower "
                '- (2hr:Off-Site)',
                # The payment stub the same calendar emits for a booking.
                'Remaining Balance - Private Party - Amber B. / BSNBCS Father',
                'Remaining Balance for Private Party - Scott G. / Hudson Yards'):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, 'No description available.'))

    def test_public_events_containing_private_survive(self):
        """The words are common in real, live listings — only the booking nouns match."""
        for name in (
                'Private Crochet Lessons by the Hour',   # e220633, live
                'Private Collection Tour of the Gochman Family Collection',
                'Private Acting Lessons with Justin',
                'Private Brooklyn Seltzer Museum and Factory Tour',
                'Private Equity and Health Care'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, 'A real public listing.'))

    def test_partly_public_night_survives(self):
        """The measured veto: e73111 is `reviewed=1, suppressed=0`.

        St. Mazie books the room privately for the early evening and opens to
        the public afterwards, so the row IS a real public listing. A human
        looked at it and kept it; the rule must not reverse that.
        """
        for name, desc in (
                ('Private Event from 7-9pm + Open to the Public at 9:30pm!',
                 'This venue hosts a private event followed by an evening open '
                 'to the general public.'),
                ('Private Event 4-9pm • Open to the public at 9:30pm!',
                 'The venue is hosting a private function until 9:00 PM. '
                 'Following the event, the bar will open to the general '
                 'public for late-night cocktails.')):
            with self.subTest(name=name):
                self.assertFalse(_is_private_booking_name(name, desc))
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_public_event_that_merely_mentions_private_hire_survives(self):
        self.assertFalse(is_obvious_non_event(
            'Jazz Night at the Loft',
            'Live jazz every Thursday. The back room is also available for '
            'private events — ask at the bar.'))


class TestStaffOnlyBlocks(unittest.TestCase):
    """(5b) The whole name is an internal staff marker."""

    def test_bccls_staff_rows(self):
        # e109470, e214085, e88759, e214250.
        for name, desc in (
                ('Staff event', 'No description available.'),
                ('Booked for Staff', 'Please see Justin for more info.'),
                ('Dept Head Mtg.', 'Dept Head Mtg.'),
                ('Dept Head Mtg.',
                 'A recurring meeting for department heads held at the Oakland '
                 'Public Library.')):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, desc))

    def test_staff_marker_variants(self):
        for name in ('Staff Meeting', 'Staff Development', 'Staff In-Service',
                     'STAFF ONLY', 'Department Head Meeting'):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, ''))

    def test_real_programming_naming_staff_survives(self):
        """e112534 / e149844 / e211197 — a real one-on-one tech class."""
        self.assertFalse(is_obvious_non_event(
            'Tech Assistance with Library Staff',
            'Come in for a half hour, one-on-one tech class to learn about '
            'general Internet and device use.'))
        self.assertFalse(is_obvious_non_event(
            'Meet the Staff Open House',
            'Drop by and meet the librarians over coffee.'))

    def test_public_friends_meeting_survives(self):
        """e100626 is LIVE — a `* Mtg` rule without the staff anchor kills it."""
        self.assertFalse(is_obvious_non_event(
            'Friends Tuesday Mtg',
            'The Friends of the Library group holds their regular Tuesday '
            'meeting at the library.'))


class TestBareprivateOccasions(unittest.TestCase):
    """(5c) The whole name is a private life occasion and the body says nothing."""

    def test_wedding_and_baby_shower(self):
        # e214016 (w3530) and e186516 (w3009) — the one live row this removed.
        self.assertTrue(is_obvious_non_event('Wedding', 'No description available.'))
        self.assertTrue(is_obvious_non_event('Baby Shower', ''))
        self.assertTrue(is_obvious_non_event('Bridal Shower', None))

    def test_church_sacraments_are_excluded(self):
        """e141704 "Communion" (First Presbyterian) is a real weekly service.

        Sacraments are published exactly like a booking — bare name, no body —
        so they were deliberately kept out of the occasion list rather than
        vetoed after the fact.
        """
        for name in ('Communion', 'Baptism', 'Christening', 'Memorial Service'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, 'No description available.'))

    def test_described_occasion_survives(self):
        """A real public event built on the occasion word keeps its body."""
        self.assertFalse(is_obvious_non_event(
            'Wedding',
            'A staged reading of the Chekhov one-act, followed by a Q&A with '
            'the director. Free admission, no reservation needed.'))
        self.assertFalse(is_obvious_non_event(
            'Community Baby Shower',
            'Free diapers and a nurse Q&A for expecting parents. Register '
            'online.'))


class TestMaintenanceBlocks(unittest.TestCase):
    """(5d) The whole name is a maintenance phrase plus a work/project noun."""

    def test_repair_work(self):
        # e213991.
        self.assertTrue(is_obvious_non_event(
            'Repair Work', 'Community room unavailable for some repair work.'))
        self.assertTrue(is_obvious_non_event('Building Maintenance Work', ''))
        self.assertTrue(is_obvious_non_event('Carpet Cleaning Day', None))

    def test_real_painting_and_repair_programming_survives(self):
        """"Painting" is the single most common real BCCLS craft word."""
        for name in ('Rock Painting', 'Watercolor Painting for Adults',
                     'Adult Craft -- Rock Painting', 'Repair Cafe',
                     'Bike Repair Workshop', 'Sand Painting',
                     'Summer Painting Workshop'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, ''))


class TestBareNoProgramNotices(unittest.TestCase):
    """(5e) The narrowest slice of the deferred `^No <noun>` family."""

    def test_no_storytime(self):
        # e213967.
        self.assertTrue(is_obvious_non_event('No Storytime', 'No description available.'))
        self.assertTrue(is_obvious_non_event('No Story Time', ''))
        self.assertTrue(is_obvious_non_event('No Classes', None))
        self.assertTrue(is_obvious_non_event('No Baby Storytime', ''))

    def test_real_events_starting_with_no_survive(self):
        for name in ('No Kidding! Comedy', 'No Lights No Lycra',
                     'No Pants Subway Ride', 'No Show'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, ''))

    def test_described_no_row_survives(self):
        """A body means somebody wrote the row up; the notice shape is bare.

        ("No Classes" is deliberately not used here — the pre-existing academic
        milestone rule catches that string regardless of the body.)
        """
        self.assertFalse(is_obvious_non_event(
            'No Storytime',
            'A parody storytelling night where nobody reads a book. Improvised '
            'tales from the audience, hosted by the Teen Advisory Board.'))


class TestSeasonalHoursNotices(unittest.TestCase):
    """(5f) "<season/weekday> Hours" with the clock time in the BODY."""

    def test_bccls_summer_hours(self):
        # e213954, e213958.
        self.assertTrue(is_obvious_non_event(
            'Summer Hours (2 PM Close)',
            'The Library closes at 2 pm on Saturdays in July and August.'))
        self.assertTrue(is_obvious_non_event(
            'Summer Saturday Hours',
            'Saturday Summer hours are 10am - 2pm June: 20th & 27th July: '
            '11th, 18th & 25th.'))

    def test_extended_and_member_hours_are_real_programming(self):
        """31 of 33 hits on the loose draft were rows like these.

        This is the "Extended Hours gallery night" the scheduled task warned a
        global `* Hours` rule would eat.
        """
        for name, desc in (
                ('Extended Museum Hours',
                 'During the month of February, enjoy extended museum hours '
                 'every Thursday evening with the galleries staying open until '
                 '8 pm.'),
                ('Member Morning Hours',
                 'Museum members and their guests are invited to explore the '
                 'exhibitions before the building opens to the general public.'),
                ('Friday Extended Hours',
                 'Celebrate summer by visiting the Hudson River Museum after '
                 'hours to experience exhibitions and outdoor courtyard games.'),
                ('Winter Recess Hours',
                 'The museum offers extended hours during the school winter '
                 'break to provide families with a creative space for play.'),
                ('Open Studio Hours',
                 'Open Studio Hours provide an unstructured, freeform space '
                 'for creatives of all levels to work on projects.'),
                ('Museum Operations - Saturday Hours',
                 'The museum will be open from 2 - 5 pm on Saturday, April 11.'),
                ('Garden Hours with a Garden Educator',
                 'Greenpoint Library is pleased to open up our Rooftop '
                 'Demonstration Garden for conversation with a Garden '
                 'Educator.')):
            with self.subTest(name=name):
                self.assertFalse(_is_seasonal_hours_notice(name, desc))
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_office_hours_survive(self):
        """"Social Worker Office Hours" is a real recurring BCCLS service."""
        for name in ('Social Worker Office Hours', 'Social Work Office Hours',
                     'Rep. LaMonica McIver Office Hours', 'Teen: Library After Hours'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, ''))

    def test_hours_shaped_name_with_a_programming_body_survives(self):
        self.assertFalse(is_obvious_non_event(
            'Summer Friday Hours',
            'Join us every summer Friday for live music on the plaza. '
            'Registration required.'))


class TestRoomReservationEcho(unittest.TestCase):
    """The reservation rule now also accepts a body that is another booking line."""

    def test_patron_reservation_with_an_activity_suffix(self):
        """e214168 — body "Patron Reservation - Mahjong" is not an exact echo."""
        self.assertTrue(_is_room_reservation('Patron Reservation',
                                             'Patron Reservation - Mahjong'))
        self.assertTrue(is_obvious_non_event('Patron Reservation',
                                             'Patron Reservation - Mahjong'))

    def test_previously_covered_shapes_still_fire(self):
        for name, desc in (
                ("Patron Reservation - O'Connor", "Patron Reservation - O'Connor"),
                ('Patron Reservation - Furbacher.', 'No description available.'),
                ('Room Reservation', '')):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, desc))

    def test_described_reservation_programming_survives(self):
        self.assertFalse(is_obvious_non_event(
            'Room Reservation Workshop',
            'Learn how to book a study room online. Bring your library card '
            'and a laptop; staff will walk you through the booking system.'))


class TestProgramEndsEcho(unittest.TestCase):
    """"<program> Ends!" corroborated by a body that adds nothing."""

    def test_summer_reading_ends(self):
        # e214118 (echo body) and e211149 (blank body).
        self.assertTrue(is_obvious_non_event('Summer Reading Ends!',
                                             'SUMMER READING ENDS!'))
        self.assertTrue(is_obvious_non_event('Summer Reading Ends',
                                             'No description available.'))

    def test_end_of_program_party_survives(self):
        self.assertFalse(is_obvious_non_event(
            'Summer Reading Ends!',
            'Join us for the wrap-up party — prizes awarded and ice cream '
            'for every reader.'))


class TestBracketPrefixStaysUnfiltered(unittest.TestCase):
    """The `[Outside Org]` arm was measured and REJECTED.

    The scheduled task proposed it, but the corpus says the prefix is a HOST
    marker, not a junk marker: of 32 bracket-prefixed BCCLS rows the large
    majority are real public programming hosted at the library by somebody
    else. Only the description-less stubs are junk, and "blank description" is
    not enough on its own — plenty of real rows are also description-less.
    """

    def test_outside_org_rows_are_real_programming(self):
        for name in ('[Outside Org] AARP Monthly Meeting',
                     '[Outside Org] Write Group Reads',
                     '[Outside Org] American Red Cross Blood Drive',
                     '[Outside Org] Literacy Volunteers of America ESL',
                     '[Outside Group] Write Group Open Mic',
                     '[Outside Org] Girl Scout Troop 33923',
                     '[MILL Senior Friday] Chair Yoga for Everyone with Pammi',
                     '[Hybrid] Just the Facts: the Nonfiction Only Book Club'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, ''))
                self.assertFalse(is_obvious_non_event(
                    name, 'No description available.'))


class TestBookedPrefixStaysUnfiltered(unittest.TestCase):
    """A bare `^Booked` prefix arm was measured and REJECTED.

    8 false positives against 2 true hits: "Booked for the Movies" is a real
    monthly book-and-film club (6 rows) and "Booked & …" is a common real
    reading-event title. Only "Booked for Staff" is caught, by the staff arm.
    """

    def test_booked_titled_reading_events_survive(self):
        for name, desc in (
                ('Booked for the Movies: Inside Out',
                 "Unwind with a kids' movie and join a monthly book and film "
                 "club to compare a book to its film adaptation."),
                ('Booked & Busy: A Book Bingo Experience',
                 'Join Adanne Bookshop for a unique Book Bingo night.'),
                ('Booked & Brewed: A Teen Reading Hangout',
                 'A cafe-inspired library space for teens to unwind and read.'),
                ('Booked & Unbothered: A Community Read-In NYC',
                 'A Sunday afternoon dedicated to slowing down and turning '
                 'the page.')):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_all_caps_booked_marker_also_survives(self):
        """e102000 — junk, but not separable from the real rows above."""
        self.assertFalse(is_obvious_non_event(
            'BOOKED BCCLS Friends Committee Event', 'No description available.'))


class TestOrgNameRoomBookings(unittest.TestCase):
    """Block (5g) — the row is titled with the ORGANIZATION holding the room.

    e222076 "Historical Society" (w3530 Oakland Public Library, no description,
    single occurrence) reached the map and could only be caught downstream by
    the event-type classifier labelling it UNKNOWN on 2026-08-17. Same feed and
    same shape as e210304 (an earlier "Historical Society"), e214224 "Saddle
    River Valley Lions Club" and e169811 "Girl Scouts".

    Measured over all 190,989 events: name gate alone 14 rows, 5 after the
    blank-description gate, 5/5 true junk, 0 live, 0 reviewed-and-kept.
    """

    def test_the_row_that_had_to_be_hand_suppressed(self):
        self.assertTrue(is_obvious_non_event(
            'Historical Society', 'No description available.'))

    def test_sibling_bookings_on_the_same_feed(self):
        for name in ('Saddle River Valley Lions Club',
                     'Girl Scouts',
                     'Cancelled Girl Scouts',
                     'Bergen County Historical Society',
                     'Hawthorne Rotary Club',
                     'Boy Scouts Troop 47',
                     'Wyckoff Chamber of Commerce',
                     'American Legion Post 170'):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, ''))
                self.assertTrue(is_obvious_non_event(
                    name, 'No description available.'))

    def test_a_title_echoed_into_the_body_still_counts_as_blank(self):
        self.assertTrue(_is_org_room_booking(
            'Historical Society', 'Historical Society'))

    def test_a_described_row_is_a_real_program_and_survives(self):
        """The description gate is what keeps the org's actual programming."""
        cases = [
            ('Yonkers Historical Society', 'Monthly meeting'),
            ('Yonkers Historical Society',
             'Monthly meeting of the Yonkers Historical Society.'),
            ('Girl Scouts',
             'Join the Girl Scouts for an afternoon gathering held at the '
             "Oakland Public Library's Makerspace."),
            ('Hawthorne Rotary Club Meeting',
             'Monthly Meeting for the Rotary Club. Interested in joining? '
             'Come find out more.'),
            ('Cub Scouts Meeting', 'Meeting for Haworth Cub Scouts Troop # 373.'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_a_content_word_in_the_title_vetoes_the_drop(self):
        """The org is PRESENTING something, so the row is a real program."""
        for name in ('Lecture: Bergen County Historical Society',
                     'Bronx County Historical Society Walking Tour',
                     'Book Sale: Friends of the Historical Society',
                     'Girl Scouts Cookie Sale',
                     'Lions Club Pancake Breakfast'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(
                    name, 'No description available.'))

    def test_org_types_deliberately_excluded_after_measurement(self):
        """Garden clubs, guilds, PTAs and boards are real public programming.

        "Our Garden Club" is a live BPL children's program (8 rows), "Kids
        Garden Club" a w3530 one, and a bare "Scout"/"Troop N" would take
        e193225 "The Scout" — a Film Forum SCREENING whose description is just
        its showtime.
        """
        for name in ('Our Garden Club',
                     'Kids Garden Club',
                     'The Scout',
                     'Troop 3200',
                     'PTA',
                     'Board of Education',
                     'Quilters Guild',
                     'Friends of the Library'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(
                    name, 'No description available.'))


class TestBareRoomNamesStayUnfiltered(unittest.TestCase):
    """e214264 "Opportunity Center" — a room booked under the room's own name.

    Nothing in the text distinguishes it from a real program at a venue of the
    same name, so it stays on the human-review path. Missing junk is the right
    failure direction for this function.
    """

    def test_bare_room_name(self):
        self.assertFalse(is_obvious_non_event(
            'Opportunity Center', 'No description available.'))


if __name__ == '__main__':
    unittest.main()
