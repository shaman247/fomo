"""Tests for the `open_call_contest` and `chainwide_promo` rules.

Both were raised by the 2026-09-06 classification pass, which could only label
two rows UNKNOWN and suppress them by hand:

  e245581 "Imagine a Better World Contest!" — "Submit your ideas from now until
          December! How do kids K-12 see a better world?"
  e245997 "National Lobster Day at Luke's Lobster" — "Luke's shacks nationwide
          are celebrating with $20 Quarter Pound Lobster Rolls."

**open_call_contest.** The pre-existing `submission_contest` rule requires a
creative-work qualifier immediately before "contest"/"competition" ("Photo
Contest", "Essay Competition"). That is high precision and blind to most of
these titles. The non-event property is not the word "contest" — it is that
participation is an ENTRY YOU SEND IN: nothing happens at a place, so there is
nothing to attend. The name gate is therefore broad and all three other gates
key on the submission shape (call-for-entries body, no attendable occasion in
the name, no attendance language in the body).

**The boundary with the `Self-Paced Challenge` event type** added the same day
(`event_types.py`) is deliberate and is what makes the filter and the taxonomy
agree. A library reading/film/decorating challenge is a real, dated program —
the venue supplies the log, sheet, prompt or pumpkin and you come get it. Those
rows say "Grab a challenge sheet at the Toms River Library" (e226887), "pick up
your reading log at the Children's Desk" (e235680), "Stop by the library every
day in October" (e241248), and they must survive the filter so they can be
typed. A submission call says "Submit your ideas from now until December".

**chainwide_promo.** The `national_food_day` rule cannot catch e245997: its name
anchor deliberately spares any "National <food> Day AT <venue>" title, because
"National Ice Cream Day at the Carousel" is a real Prospect Park occasion, and
that anchor stays. The property keyed here is different and is not about food:
the body says the offer runs at EVERY branch of a chain, so by its own
description nothing is programmed at this venue on this date. "At participating
restaurants" is NOT such a phrase — that is the Restaurant Week form, a genuine
multi-venue citywide occasion (e9006 Restaurant Week at Rockefeller Center).

Measured over all 214,370 events: `open_call_contest` matches 13 rows, 8 of
which existing rules already catch, adding e81689, e201551, e203999, e241883,
e245581; `chainwide_promo` matches 4 (e16474, e24311, e96150, e245997). Between
them, ZERO live, visible events are lost.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import is_obvious_non_event, which_junk_rule  # noqa: E402


class TestOpenCallContestsAreDropped(unittest.TestCase):
    def test_the_row_that_had_to_be_hand_suppressed(self):
        """e245581 — a contest whose qualifier ("World") is not a creative work,
        so the older `submission_contest` name gate could never see it."""
        self.assertEqual(which_junk_rule(
            'Imagine a Better World Contest!',
            'Submit your ideas from now until December! How do kids K-12 see a '
            'better world? We want to learn from the younger generations what '
            'inspires them and how they envision the future.'),
            'open_call_contest')

    def test_other_measured_open_calls(self):
        for name, desc in (
            ('Juvenile Spooky Story Halloween Contest (Grades 2-4 & Grades 5-8)',
             'Submit a spooky, horror or Halloween short story for a chance to '
             'win a prize. The contest is for students in grades 2-4 and 5-8.'),
            ('NYU Faculty Housing Pet Photo Contest',
             'Winning pictures will be featured on Instagram.'),
            ('Summer Adventure: Summer Poetry Challenge',
             'Can you write a poem based on our prompts? Submit your poem to '
             'the Summer Writing Contest.'),
        ):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, desc))

    def test_bare_deadline_line_is_a_call_for_entries(self):
        """Juried art calls publish a bare "Deadline: <date>" rather than the
        "submissions are due" phrasing the older desc gate knew."""
        self.assertTrue(is_obvious_non_event(
            'Call to Artists: Abstract Perspectives — Juried Art Competition',
            'Deadline: Monday, September 14, 2026. Entries are due by midnight.'))


class TestSelfPacedChallengesSurvive(unittest.TestCase):
    """The rows the `Self-Paced Challenge` event type exists to carry. Every one
    of these is real library/park programming with venue-side participation, and
    the filter must leave all of them for the classifier."""

    def test_venue_side_participation_keeps_the_row(self):
        for name, desc in (
            ('Teen Summer Reading Challenge',
             'Teens: Want to win cool prizes just for reading? Grab a challenge '
             'sheet at the Toms River Library to log books, pick from our box '
             'of fun prizes, and enter to win a big prize at the end of summer!'),
            ('(R) 1,000 Books Before Kindergarten',
             'This program encourages caregivers to read 1,000 books to their '
             'children before they enter Kindergarten. Register here and pick '
             'up your reading log at the Children’s Desk.'),
            ('Inktober - Drop in challenge',
             "Stop by the library every day in October to discover that day's "
             'prompt and participate in Inktober 2026. Ages 10+'),
            ('BPL Fall Film Challenge - For Teens and Adults - Begins!',
             'In recognition of Banned Book Week, we invite you to watch five '
             'films that were adapted from frequently banned books between '
             'September 1 and October 31.'),
            ('Literary Pumpkin Decorating Contest!',
             'Registered families will receive a call when their pumpkin is '
             'ready for pickup. They will take it home, transform it into a '
             'favorite literary character, and return it by October 19.'),
            ('Adult Summer Reading Challenge',
             'Log books you read to yourself, to your partner, or to others as '
             'part of the Adult Summer Reading Challenge.'),
            ('Teen Photography Challenge',
             'Teens can take & email photos of reflections in water to: '
             'vlimbo@theoceancountylibrary.org. Ages 13 - 18. Photos will be '
             'displayed in the Teen Zone.'),
        ):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))


class TestAttendableContestsSurvive(unittest.TestCase):
    """The over-filtering failure mode: a contest you go to and watch or enter
    in person. Real venue events legitimately mention contests and competitions."""

    def test_attendable_contests_are_not_junk(self):
        for name, desc in (
            ('Family Jigsaw Puzzle Competition',
             'Join us for our Family Jigsaw Puzzle Competition.'),
            ('Chess Challenge',
             'An hour of informal play. Participants will be paired with a '
             'partner. Submit your name at the desk to be entered in the draw.'),
            ('Strut Your Mutt: Canine Halloween Costume Contest',
             'Our annual costume contest for dog owners to show off their '
             'creative side. Registration required at 11am.'),
            ('Oktoberfest Bratwurst Chef Competition Fundraiser',
             'Six local chefs offer their take on German bratwurst, with '
             'ticket holders judging the entries.'),
            ('Major Problems Comedy Contest presented by Lil Mo',
             'Each comic hits the stage with 5 minutes, then the audience '
             'votes for their favorite.'),
        ):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))


class TestChainwidePromos(unittest.TestCase):
    def test_the_row_that_had_to_be_hand_suppressed(self):
        """e245997 — a "National <food> Day AT <venue>" title, which the
        national-food-day anchor spares on purpose. The body is what convicts it."""
        self.assertEqual(which_junk_rule(
            'National Lobster Day at Luke’s Lobster',
            'Luke’s shacks nationwide are celebrating with $20 Quarter '
            'Pound Lobster Rolls, served with potato chips. It’s a wicked '
            'good deal for lobsta mobstas in honor of our favorite holiday.'),
            'chainwide_promo')

    def test_all_locations_arcade_promo(self):
        """e96150 / e16474 — the same promo on two crawls."""
        self.assertTrue(is_obvious_non_event(
            'Win’s-Day Wednesday',
            'Enjoy half off arcade all day long at all of our stores.'))


class TestChainwidePromoDoesNotOverreach(unittest.TestCase):
    def test_restaurant_week_is_not_a_chainwide_promo(self):
        """e9006 — "participating restaurants" is the multi-venue citywide
        occasion form, deliberately excluded from the chain-wide phrase list."""
        self.assertFalse(is_obvious_non_event(
            'Restaurant Week at Rockefeller Center',
            'Indulge in specially curated prix-fixe lunch and dinner menus at '
            'participating restaurants like Le Rock, NARO and Jupiter. Menus '
            'include 2-course or 3-course options.'))

    def test_nationally_acclaimed_is_not_nationwide(self):
        """e85967 — the word "nationally" describes the poets, not the offer."""
        self.assertFalse(is_obvious_non_event(
            'Poetry Book Sale',
            'Join the Poetry Society of America for a pop-up poetry book sale '
            'featuring hundreds of books by nationally acclaimed poets '
            'available for $5 each.'))

    def test_a_chain_offer_with_real_programming_survives(self):
        self.assertFalse(is_obvious_non_event(
            'Free Cone Day',
            'All of our shops are giving away a free scoop, with live music '
            'from a DJ and a raffle from 2-5pm.'))

    def test_national_night_out_is_a_genuine_community_event(self):
        self.assertFalse(is_obvious_non_event(
            'National Night Out',
            'Join us for National Night Out, the annual community-building '
            'campaign, with free food, games and a $5 raffle for the FDNY.'))

    def test_rental_rows_are_untouched_by_both_rules(self):
        """`RENTAL:` is explicitly not junk (junk_filter_non_events)."""
        self.assertNotIn(which_junk_rule(
            'RENTAL: Community Room',
            'The community room is reserved. Rate is $50 per hour at all '
            'locations.'), ('open_call_contest', 'chainwide_promo'))


if __name__ == '__main__':
    unittest.main()
