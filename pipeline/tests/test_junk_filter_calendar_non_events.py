"""Tests for the calendar-non-event rules in is_obvious_non_event.

Two shapes reached the map and were only caught downstream, by the event-type
classifier labelling them UNKNOWN:

  * Academic / registrar calendar milestones — seven Long Island University rows
    hand-suppressed on 2026-08-06 (211669-211675) and e214913 on 2026-08-09.
    NYU (w590) and Bronx Community College (w2952) emit the same shape
    continuously. Measured over all 183,900 events: 71 matches, all of them
    registrar/school-calendar markers, exactly ONE currently live (117776 "Last
    Day of Summer 2026 5W1 Instruction / Final Exams", itself junk), zero false
    positives. Only 1 of the 408 live events from academic-named websites fires.

  * Dark-night notices — e214750 "No Shows - Labor Day Weekend" (w60 Brooklyn
    Comedy Collective), an extension of the existing "No <program noun> Today"
    pattern to performance nouns and holiday temporal markers. Adds exactly one
    match over the whole table and loses none of the ten the pattern already had.

  * Month-CALENDAR placeholders — a venue's own monthly calendar page
    extracted as an event ("The Stone at The New School: September Calendar",
    e221887, hand-suppressed 2026-08-17; the June and July rows preceded it,
    and the Bronx community boards emit the mirrored word order continuously).
    Measured over all 190,989 events: 16 matches, 16 placeholders, 0 real
    events. Added 2026-08-17 after the first two shapes missed it.

The food/drink weekday-special family raised in the same task was DELIBERATELY
NOT automated here; see TestWeekdayFoodSpecialsStayUnfiltered. The separate
"National <food> Day" marketing-post family WAS automated — for the measured
reason that every reviewed row in it was suppressed rather than kept — and
lives in test_junk_filter_food_holiday_promos.py.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import is_obvious_non_event


class TestAcademicRegistrarMilestones(unittest.TestCase):
    def test_liu_rows_that_had_to_be_hand_suppressed(self):
        """The seven LIU rows from the 2026-08-06 classification pass."""
        for name in ('Weekday classes begin',
                     'Labor Day Holiday - No Classes',
                     'Weekend session A: Classes begin',
                     'Weekend session A: Last classes/Final examinations',
                     'Weekend session B: Classes begin'):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, 'No description available.'))

    def test_liu_drop_add_and_withdrawal_deadlines(self):
        self.assertTrue(is_obvious_non_event(
            'Registration and drop/add ends for full-term courses',
            'Enrollment in Lab courses requires permission after Jan 26.'))
        self.assertTrue(is_obvious_non_event(
            'Last day for withdrawal/Opt Pass/Fail for full-semester classes',
            'No description available.'))

    def test_nyu_academic_calendar_shapes(self):
        cases = [
            ('Spring 2026 Classes Begin',
             'The start of classes for the Spring 2026 semester.'),
            ('Spring 2026 Add/Drop Deadline',
             'The deadline for students to add or drop courses.'),
            ('First 7-Week Session Drop/Add Withdrawal Period Begins',
             'The start of the withdrawal period for the First 7-Week Session.'),
            ('Request Pass/Fail Grade Option Deadline: 10-Week',
             'The deadline for eligible students to submit a request.'),
            ('Final Exam Period',
             'Final examination schedule for various NYU schools.'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, desc))

    def test_community_college_refund_and_withdrawal_deadlines(self):
        cases = [
            'Last day to drop Summer 2026 3W1 courses with 100% Tuition Refund',
            'Last day to add a Summer 2026 8W1 course',
            'Last Day to withdraw from a Summer 2026 3W1 course with a grade of W',
            'Last Day of Summer 2026 5W1 Instruction / Final Exams',
            'Final Examinations',
            'College Closed (No Classes Scheduled)',
        ]
        for name in cases:
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(
                    name, 'Consult with an advisor before dropping a class.'))

    def test_fires_without_any_description(self):
        """These rows are usually description-less, so the rule is name-only."""
        self.assertTrue(is_obvious_non_event('Classes Resume', ''))
        self.assertTrue(is_obvious_non_event('Classes Resume', None))


class TestAcademicVetoSparesRealProgramming(unittest.TestCase):
    """The attendable-occasion veto over the NAME is the precision guard."""

    def test_recital_plural_spares_a_real_event(self):
        """e78067 — the singular `recital` missed this; the plural is required."""
        self.assertFalse(is_obvious_non_event(
            'Classes Resume, Town Hall (Dance and Music Recitals)',
            'Mind-Builders Creative Arts Center hosts this event featuring the '
            'resumption of classes alongside dance and music recitals.'))

    def test_attendable_occasions_built_on_registrar_words(self):
        cases = [
            'Last Class Celebration Party',
            'Final Examinations Study Break',
            'No Classes Day Camp',
            'Classes Begin Open House',
            'Drop/Add Help Workshop',
        ]
        for name in cases:
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, ''))

    def test_singular_final_exam_is_not_matched(self):
        """e154254 — a real NYChorror trivia night. Only the plural form matches.

        The veto catches this one too, but the singular form is deliberately
        absent from the pattern so the rule does not lean on the veto alone.
        """
        self.assertFalse(is_obvious_non_event(
            'Final Exam Horror Trivia, No. 39', ''))
        self.assertFalse(is_obvious_non_event(
            'Final Exam Cram Jam', 'An evening of last-minute studying.'))

    def test_registration_begins_is_deliberately_not_matched(self):
        """Dropped arm: it hits real library sign-up programming.

        Accepted miss: LIU's "Spring/Summer 2027 Registration Begins
        (tentative)" (211673) stays unfiltered. Missing junk is the right
        failure direction here.
        """
        self.assertFalse(is_obvious_non_event(
            '2026 Summer Reading Program Registration Begins',
            'Children and teens ages 3-17 are welcome to join the Summer Reading Club.'))
        self.assertFalse(is_obvious_non_event(
            'Adult Summer Reading Registration Begins!',
            'Come in to sign up for Adult Summer Reading Bingo for 2026 with prizes.'))
        self.assertFalse(is_obvious_non_event(
            'Spring/Summer 2027 Registration Begins (tentative)',
            'No description available.'))

    def test_session_start_is_deliberately_not_matched(self):
        """Dropped arm: e39357 is a real children's music program's first day."""
        self.assertFalse(is_obvious_non_event(
            'Bronx Bops Weekday Session Start',
            'This session marks the official start of our weekday music program '
            'for young children.'))

    def test_real_university_public_programming_survives(self):
        cases = [
            ('Fall Faculty Lecture: The Physics of Climate',
             'A free public lecture in the Kimmel Center.'),
            ('LIU Post Wind Symphony Fall Concert',
             'The Wind Symphony performs works by Holst and Grainger.'),
            ('Bronx Community College Open House',
             'Meet faculty, tour the campus, and learn about admissions.'),
            ('Commencement Ceremony 2026',
             'The undergraduate commencement ceremony.'),
            ('Student Art Exhibition Opening Reception',
             'Work by graduating studio-art majors.'),
            ('Writing Workshop: Personal Essays',
             'A hands-on workshop open to the public.'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))


class TestDarkNightNotices(unittest.TestCase):
    def test_no_shows_over_a_holiday_weekend(self):
        """e214750 — Brooklyn Comedy Collective's dark Labor Day weekend."""
        self.assertTrue(is_obvious_non_event(
            'No Shows - Labor Day Weekend', 'it’s a party.'))

    def test_other_performance_noun_and_temporal_combinations(self):
        cases = [
            'No Shows Tonight',
            'No Performances This Weekend',
            'No Screenings - Thanksgiving',
            'No Matinee Today',
            'No Shows Christmas',
        ]
        for name in cases:
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, ''))

    def test_a_real_show_titled_no_show_survives(self):
        """e20967 — 54 Below's cabaret. The temporal marker is what spares it."""
        self.assertFalse(is_obvious_non_event(
            'No Show',
            'A meta-theatrical cabaret experience that explores the humor and '
            'heartbreak behind the scenes of the entertainment industry.'))
        self.assertFalse(is_obvious_non_event('No Show', ''))

    def test_the_existing_no_program_today_rule_is_unchanged(self):
        for name in ('No Walk-In Class Today',
                     'No Drop-in Open Gym This Week',
                     'No Story Time Tonight'):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, ''))
        self.assertFalse(is_obvious_non_event(
            'No Pants Subway Ride', 'The annual no-pants ride returns.'))


class TestMonthCalendarPlaceholders(unittest.TestCase):
    """A venue's own monthly CALENDAR page extracted as if it were an event.

    e221887 "The Stone at The New School: September Calendar" (w653) — venue
    boilerplate for a description, one occurrence spanning the whole month
    (2026-09-01 → 2026-09-30) — reached the map and was only caught by the
    event-type classifier labelling it UNKNOWN on 2026-08-17. **The shape
    recurs every month**: the June (e158041) and July (e178870) rows are
    already in the table, and the Bronx community-board feeds emit it
    continuously in the mirrored word order.

    Measured over all 190,989 events: 16 matches, 16 calendar-page
    placeholders, zero real events, zero reviewed-and-kept.
    """

    def test_the_stone_monthly_calendar_rows(self):
        boilerplate = (
            'The Stone at The New School serves as an artist-centric home and '
            'community for experimental and avant-garde artists, where they '
            'can perform what they want without any interference.')
        for month in ('June', 'July', 'September'):
            with self.subTest(month=month):
                self.assertTrue(is_obvious_non_event(
                    f'The Stone at The New School: {month} Calendar',
                    boilerplate))

    def test_community_board_calendar_rows_in_both_word_orders(self):
        cases = [
            ('Bronx Community Board 8 January 2026 Calendar',
             'This is the official calendar for Bronx Community Board 8 for '
             'January 2026.'),
            ('Bronx Community Board 11 Calendar - April 2026',
             'The April 2026 calendar for Bronx Community Board 11 lists all '
             'pertinent board and committee meetings.'),
            ('Bronx Community Board 11 Monthly Calendar - May 2026',
             'Stay updated on all community board hearings and public '
             'sessions scheduled for May 2026.'),
            ('May 2026 Meeting Calendar',
             'The official guide to all public sessions and board meetings.'),
            ('June 2026 Monthly Calendar',
             'Stay informed about local government meetings and public '
             'hearings happening throughout the month.'),
            ('June 2026 Calendar',
             'The official schedule of meetings and public events hosted by '
             'Bronx Community Board 10.'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, desc))

    def test_the_month_qualifier_is_the_whole_gate(self):
        """A bare `calendar$` rule kills three real rows; the month spares them.

        e217078 (LIVE) is a Queens Library craft program, e143159 a real panel
        at Printed Matter, and e17132 is Atom Egoyan's FILM "Calendar" at w986.
        """
        cases = [
            ('Back-to-School: Design you Own Calendar',
             'Get organized for the new school year by making your own '
             'calendars at Arverne Library!'),
            ('What Are You Doing Tonight? How to Start Your Own Events Calendar',
             'Panel discussion and one-on-one conversations with editors and '
             'publishers of low-tech New York listings.'),
            ('Calendar',
             "Atom Egoyan's meditative film about a photographer traveling "
             'through Armenia while his marriage unravels.'),
            ('Summer at the Library Wonder Wednesday: DIY Moon Phases '
             'Calendar/Calculator',
             'Teens will learn about the different moon phases.'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_a_calendar_someone_makes_is_a_real_program(self):
        """The craft veto, for the month-shaped titles the gate would take."""
        for name in ('Make Your Own December Calendar',
                     'Craft Club: 2027 January Calendar',
                     'Advent Calendar Workshop',
                     'Photo Contest Calendar Exhibit'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(
                    name, 'A hands-on program for all ages.'))

    def test_month_less_venue_listing_placeholders_stay_unfiltered(self):
        """A DIFFERENT shape, deliberately left alone.

        "Chelsea Studio Calendar" (w1190, 20 rows) and "Event Calendar"
        (w1979) really are junk, but the only name gate that takes them also
        takes the film and the two craft programs above. They stay on the
        human-review path.
        """
        for name in ('Chelsea Studio Calendar',
                     'Event Calendar',
                     'Brooklyn Music Kitchen Entertainment Calendar',
                     'New York City Condensed Matter Physics Calendar'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(
                    name, 'A schedule of upcoming classes at the studio.'))


class TestWeekdayFoodSpecialsStayUnfiltered(unittest.TestCase):
    """The food/drink family raised alongside these was NOT automated.

    Re-measured 2026-08-09 in its tightest form (whole name is
    "<menu-item> <Weekday>", description is a bare price offer, no programming
    word): 3 hits over 183,900 events, one of which — "Whiskey Wednesday"
    (e18533) — is live and `reviewed=1`, i.e. a human deliberately kept it. The
    review record shows the class is a venue-by-venue judgment rather than a
    fact, so `/hide-uninteresting-events` owns it (find_review_candidates.py
    patterns 1 and 31). These tests pin that decision.
    """

    def test_greenwood_park_rows_are_not_auto_dropped(self):
        cases = [
            ('Taco Tuesdays', '$5 tacos and half-price margaritas are offered every Tuesday.'),
            ('Burger Mondays', 'Buy any burger and get a free beer on Mondays.'),
            ('Sunday Funday', 'No description available.'),
            ('Bottomless Brunch', 'Bottomless brunch is offered every Saturday from 12–3pm.'),
            ('Happy Hour', 'Happy hour runs from 3–7pm Monday through Friday.'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_reviewed_and_kept_lookalikes_survive(self):
        cases = [
            ('Whiskey Wednesday',
             'Every Wednesday features a different selection of whiskeys with '
             '$2 off neat/rocks pours and $3 off whiskey cocktails.'),
            ('Martini Monday',
             'Start your week at Mosaic with special pricing on a curated '
             'selection of signature martinis.'),
            ('Taco Tuesday', '$5 Tacos & Margarita Pitchers + Bingo Night!'),
            ('Happy Hour Friday',
             'Every Friday this summer, the Museum stays open late until 7 pm '
             'for Happy Hour Fridays.'),
            ('Soup Sunday',
             'A monthly free communal meal to nourish yourself and meet your '
             'neighbors.'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))


if __name__ == '__main__':
    unittest.main()
