"""Tests for the operational-calendar and standing-promo rules added 2026-08-20.

Six non-events reached the event-type classifier as UNKNOWN in the 2026-08-20
run and had to be hand-suppressed. Four are NJ public-library OPERATIONAL rows
leaking out of the same BCCLS feed (w3530) — the building opens late, a program
ends, the AV gets upgraded, a staffer sets up a craft — and two are marketing:
an attraction's BOGO ticket offer and a bar's permanent happy hour.

    225218  Delayed Opening - Staff Development     (Bergenfield PL)
    225219  Summer Reading Programs End             (Garfield PL)
    225249  AV upgrade                              (Wyckoff PL)
    225259  Kindergarten Kick-Off Craft Setup       (Oakland PL)
    225309  Kids' Night on Broadway at Top of the Rock  (Rockefeller Center)
    225510  Happy Hour & Live Music                 (Don't Tell Mama)

Measured over all 193,874 events (`.scratch/extractor0820/`): the five rules
below newly catch 26 rows, **0 of them live**, and drop nothing the filter
caught before. Per pattern: delayed-opening 6 name matches / 0 live;
"<program> Ends" widened 3 → 4 matches / 0 live; the equipment-maintenance arm
1 match / 0 live; the tail-anchored "… Setup" name gate 5 matches of which the
description gate spares 4 real events, leaving 1; the anchored BOGO body 4
matches / 0 live; the standing happy hour 14 matches / 0 live.

Two patterns were deliberately kept NARROW and the tests below pin the margin:

* **"Setup" alone is far too broad.** Four of the five tail matches are real —
  "Tech Help: Libby Set-Up" is a library class, "… Unpacking & Store Setup" and
  "Picnic Set-up" are volunteer shifts. Only a blank/echo body fires.
* **"Happy hour" alone must NEVER be a junk signal.** 50 live events are named
  one. The discriminator is the body's FREQUENCY — daily/nightly/every-day is a
  venue amenity; weekly and monthly happy hours are real recurring events and
  are deliberately out of reach.

Do not loosen either without re-measuring against the live `events` table.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import (
    is_obvious_non_event,
    _is_delayed_opening_notice,
    _is_standing_happy_hour,
)

BLANK = 'No description available.'


class TestLibraryOperationalRows(unittest.TestCase):
    """The four BCCLS rows and their shapes."""

    def test_delayed_opening_for_staff_development(self):
        """225218 — body states the later opening time."""
        self.assertTrue(is_obvious_non_event(
            'Delayed Opening - Staff Development',
            'Due to staff development, the library will be opening at 1:00pm. '
            'Thank you for your understanding.'))

    def test_delayed_opening_variants_across_the_corpus(self):
        for name, desc in (
            ('Delayed Opening',
             'The museum will open to the public later than its standard '
             'scheduled time for operational requirements.'),
            ('Library late opening',
             'Please note that all NYPL locations will open at 12 PM on '
             'Wednesday, June 10.'),
            ('General NYPL Branch Delayed Opening',
             'Please note that all NYPL locations will have a delayed opening '
             'at 12 PM on Wednesday, June 10.'),
            ('Library wide delayed opening', BLANK),
        ):
            with self.subTest(name=name):
                self.assertTrue(_is_delayed_opening_notice(name, desc))

    def test_attendable_openings_are_spared(self):
        """The hours-notice veto is what keeps real openings alive."""
        for name in ('Late Opening Reception', 'Late Opening Party',
                     'Delayed Opening Concert', 'Gallery Late Opening Tour'):
            with self.subTest(name=name):
                self.assertFalse(_is_delayed_opening_notice(name, BLANK))

    def test_opening_words_without_the_delay_phrase_are_spared(self):
        for name in ('Grand Opening', 'Opening Night', 'Exhibition Opening',
                     'Open House', 'Opening Reception: New Work'):
            with self.subTest(name=name):
                self.assertFalse(_is_delayed_opening_notice(name, BLANK))

    def test_summer_reading_programs_end(self):
        """225219 — plural noun, no "s" on the verb, no "!"."""
        self.assertTrue(is_obvious_non_event('Summer Reading Programs End', BLANK))

    def test_singular_program_end_forms_still_fire(self):
        for name in ('Summer Reading Ends', 'Summer Reading Ends!',
                     'Registration Ends', 'Reading Challenge Ends!'):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, BLANK))

    def test_bare_ends_is_still_not_a_junk_signal(self):
        """The program noun is load-bearing — "It Ends" is a film."""
        for name in ('It Ends', 'It Ends With Us', 'The World Ends',
                     'Where the Sidewalk Ends'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, BLANK))

    def test_av_upgrade_maintenance_block(self):
        """225249 — equipment work, no work/project noun to close the name."""
        self.assertTrue(is_obvious_non_event('AV upgrade', BLANK))
        for name in ('HVAC Replacement', 'Elevator Maintenance',
                     'Network Outage', 'A/V Upgrade'):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, BLANK))

    def test_programming_built_on_the_same_words_survives(self):
        for name in ('Sound Bath', 'Lighting Design Workshop', 'Computer Class',
                     'Sound Healing Meditation', 'Security Awareness Talk',
                     'Elevator Pitch Workshop'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, BLANK))

    def test_craft_setup_staff_block(self):
        """225259 — a room held while a staffer preps a later program."""
        self.assertTrue(is_obvious_non_event('Kindergarten Kick-Off Craft Setup', BLANK))
        self.assertTrue(is_obvious_non_event('Craft Set-Up', ''))

    def test_described_setup_rows_are_real_events_and_survive(self):
        """The four real corpus rows the description gate spares."""
        for name, desc in (
            ('Tech Help: Libby Set-Up',
             'Need help accessing eBooks and eAudiobooks on your device? '
             'We can help you set-up Libby.'),
            ('BKO Volunteer Day: Asiyah Women’s Center Free Store – '
             'Unpacking & Store Setup',
             "Help organize the Asiyah Women's Center Free Store by unpacking "
             'donations and setting up the store.'),
            ('Picnic Set-up',
             "We'll be helping the Cambridge Co-op set up for their annual "
             'picnic by assisting with tables and tents.'),
        ):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_setup_mid_name_is_not_enough(self):
        """The word must CLOSE the name — "setup" is common inside real titles."""
        for name in ('Setup Your First Website',
                     'Set Up a Small Business: Free Legal Clinic',
                     'Setup and Sew: Beginner Machine Basics'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, BLANK))


class TestPromoRowsAreJunk(unittest.TestCase):

    def test_bogo_ticket_promotion(self):
        """225309 — the body IS the offer, there is no event to describe."""
        self.assertTrue(is_obvious_non_event(
            'Kids’ Night on Broadway at Top of the Rock',
            'Buy one full-price adult Timed Admission ticket and receive one '
            'complimentary youth ticket for Kids’ Night on Broadway, valid '
            'August 25–26.'))

    def test_other_anchored_bogo_promos(self):
        for name, desc in (
            ('Best Friend Promo!',
             'Buy one ticket and get one 50% off using code BESTIE50.'),
            ('July 4 Weekend BOGO!',
             'Buy one get one ticket promotion running through the weekend '
             'with code USA, plus $10 slushie and hot dog.'),
        ):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, desc))

    def test_bogo_mentioned_inside_a_real_event_is_untouched(self):
        """53 events carry a BOGO phrase; 6 are live. Only the ANCHOR is junk."""
        for name, desc in (
            ('DUMBO After Dark [18+]',
             'An adults-only event featuring happy hour BOGO deals and '
             'unlimited laser tag and mini bowling.'),
            ('Karaoke Tuesday with the Fabulous LaMaria',
             'Join the Fabulous LaMaria for an evening of karaoke in Brooklyn. '
             'Enjoy the weekly happy hour with 2-for-1 drinks.'),
            ('Missing Movies Double Feature: The Kill-Off + My New Gun',
             'A 2-for-1 35mm double feature of two New Jersey–set noirs, '
             'followed by a panel discussion with the filmmakers.'),
        ):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_bogo_veto_spares_an_offer_that_leads_a_real_writeup(self):
        self.assertFalse(is_obvious_non_event(
            'Comedy Night',
            'Buy one ticket and get one free! Join us for a night of standup '
            'with six comics, doors open at 7pm.'))

    def test_standing_daily_happy_hour(self):
        """225510 — a permanent venue amenity published as a dated row."""
        self.assertTrue(is_obvious_non_event(
            'Happy Hour & Live Music',
            'The venue advertises daily happy hour deals on drinks and food '
            'along with live music.'))
        for name, desc in (
            ('Happy Hour at Cubbyhole',
             'Enjoy daily happy hour at Cubbyhole with drink specials from '
             '4:00 PM to 7:00 PM.'),
            ('Yatenga French Bistro & Bar Happy Hour',
             'Happy hour 7 days a week featuring discounted drinks, wings, '
             'and fries.'),
            ('$10 After 10 Happy Hour',
             'Nightly late-night specials featuring $10 espresso martinis.'),
        ):
            with self.subTest(name=name):
                self.assertTrue(_is_standing_happy_hour(name, desc))

    def test_named_happy_hour_programming_is_kept(self):
        """50 live events are named "happy hour". None may be touched."""
        for name, desc in (
            ('Poetry Happy Hour',
             'Explore the poetry stacks with a small group, find something '
             'worth reading aloud, and talk about it over light refreshments.'),
            ('[happy hour] ✽ she.they.dj ✽',
             'Join Mood Ring for a happy hour event featuring music by '
             'she.they.dj.'),
            ('Art History Happy Hour: Sculpting the Senses',
             'Explore the worlds of designer Iris van Herpen in this '
             'installment of Art History Happy Hour.'),
            ('Happy Hour Live Music 5-7pm + Jazz with David Bailis!', BLANK),
        ):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_weekly_and_monthly_happy_hours_are_real_events(self):
        """Only the every-single-day form is an amenity."""
        for name, desc in (
            ('Sunday Football Happy Hour',
             'NFL Happy Hour runs every Sunday from 12 to 4 p.m. during '
             'football season, with games on the big screen and $10 buckets.'),
            ('Weekly Happy Hour',
             'A casual weekly happy hour at a dive bar to socialize and meet '
             'new people, with drink specials.'),
            ('Dumbo Happy Hour',
             'On the first Wednesday of every month, enjoy neighborhood-wide '
             'happy hour specials at over 12 bars.'),
        ):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_daily_body_without_a_happy_hour_name_is_untouched(self):
        self.assertFalse(_is_standing_happy_hour(
            'Live Jazz Trio',
            'Daily drink specials are available during the performance.'))


if __name__ == '__main__':
    unittest.main()
