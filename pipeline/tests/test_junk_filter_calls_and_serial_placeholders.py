"""Tests for the two is_obvious_non_event gaps found on 2026-09-02.

Seven non-events reached event-type classification that day and had to be
hand-suppressed. Two of them were fixable shapes:

1. A call for submissions whose marker sits INSIDE the title rather than in
   front of it. The prefix rules were never the problem -- the noun list after
   "call for" was. e238812 "Arts on Terry - Call for Street Artists & Live
   Painters" and e238813 "CALL FOR MUSIC ... Spotlight Stage @ Arts on Terry"
   (both w1970 Patchogue Arts Council) both failed on the words after the
   preposition: "Street Artists" has a qualifier in the way, and "Music" was
   not in the list at all. Corpus-checked over all 208,019 events: 33 -> 50
   matches, and every one of the 17 added rows is a genuine call for entries.

2. Sequential placeholder rows. e239284/5/6 -- "Nyc #2174", "Nyc #2175",
   "Nyc #2176" (w5147 Hash House Harriers) -- are hash runs whose start venue
   has not been announced, so the hareline gives the extractor a kennel name, a
   run number, and nothing else. Corpus-checked over all 208,019 events: 26
   matches, every one a venue-TBA run from that one website.

The serial-placeholder rule is a conjunction of three legs and each one spares
real events on its own, so every leg has a negative test below. The standing
guardrail for this filter -- "RENTAL: is NOT junk" -- is pinned too.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import is_obvious_non_event


class TestCallForInsideTheTitle(unittest.TestCase):
    def test_call_for_with_a_qualifier_before_the_noun(self):
        # e238812 — "Street" sat between the preposition and "Artists".
        self.assertTrue(is_obvious_non_event(
            'Arts on Terry - Call for Street Artists & Live Painters',
            'CALL FOR STREET ARTISTS & LIVE PAINTERS Arts on Terry returns '
            'Sunday, September 13, 2026 and we are looking for artists.'))

    def test_call_for_a_discipline_that_was_missing_from_the_list(self):
        # e238813 — "Music" was not a solicited noun.
        self.assertTrue(is_obvious_non_event(
            'CALL FOR MUSIC \U0001f3a4 Spotlight Stage @ Arts on Terry',
            'We are looking for original musicians, bands, singers, and '
            'songwriters to take over the Spotlight Stage.'))

    def test_call_to_artisan_vendors(self):
        # e116078 — the "to" arm needs the qualifier slot as well.
        self.assertTrue(is_obvious_non_event(
            'Call to Artisan Vendors – Hoshyla Farms Lavender Festival',
            'Vendor applications are open.'))

    def test_call_for_mural_artists(self):
        self.assertTrue(is_obvious_non_event(
            'Call for Mural Artists: Haverstraw Riverside Arts', ''))

    def test_call_for_applications_after_the_programme_name(self):
        self.assertTrue(is_obvious_non_event(
            'Playwright Intensive Workshop Call for Applications', ''))


class TestCallForDoesNotEatRealEvents(unittest.TestCase):
    def test_a_call_for_an_abstract_noun_is_not_a_submission_call(self):
        # The qualifier slot is bounded and the noun list is a closed set, so a
        # title that merely contains "call for" survives.
        self.assertFalse(is_obvious_non_event(
            'A Call for Peace: Chamber Concert',
            'An evening of chamber music.'))

    def test_curtain_call_is_untouched(self):
        self.assertFalse(is_obvious_non_event(
            'Curtain Call: Closing Night Party',
            'Join the cast for the closing celebration.'))


class TestSerialPlaceholderRows(unittest.TestCase):
    def test_hash_run_with_no_title_body_or_venue(self):
        # e239284 — the row that motivated the rule.
        self.assertTrue(is_obvious_non_event(
            'Nyc #2174', 'No description available.',
            'Manhattan (exact location unspecified)'))

    def test_borough_prefixed_sibling(self):
        # e225349.
        self.assertTrue(is_obvious_non_event(
            'Brooklyn #1197', 'No description available.',
            'Brooklyn (exact location unspecified)'))

    def test_bare_borough_location_counts_as_unspecified(self):
        # e177111 — the older rows carried the bare borough, without the
        # extractor's "(exact location unspecified)" marker.
        self.assertTrue(is_obvious_non_event(
            'Brooklyn #1186', 'No description available.', 'Brooklyn'))

    def test_empty_description_and_absent_location(self):
        self.assertTrue(is_obvious_non_event('Nyc #2175', '', None))


class TestSerialPlaceholderLegsSpareRealEvents(unittest.TestCase):
    def test_a_published_start_venue_saves_the_same_title(self):
        # e182739 / e193689 — identical names, real start points, attendable.
        self.assertFalse(is_obvious_non_event(
            'Nyc #2157', 'No description available.', 'Tompkins Square Park'))
        self.assertFalse(is_obvious_non_event(
            'Brooklyn #1187', 'No description available.', 'Alligator Lounge'))

    def test_a_real_description_saves_the_row(self):
        # e177128 — same shape, but the trail is described.
        self.assertFalse(is_obvious_non_event(
            'Nyc #2164',
            'A midtown trail featuring special eggs and a Wednesday night '
            'on-in.',
            'Manhattan (exact location unspecified)'))

    def test_a_non_generic_prefix_saves_the_row(self):
        # A "<anything> #<n>" rule would eat all of these: they are real
        # numbered events that happen to carry a blank description.
        for name in ('SideQuest IRL #47', 'Beer Mile Special #255',
                     'Queens Black Knights #73', 'Bklyn Mile Track Workout #2',
                     'Naww #394', 'Lil #152'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(
                    name, 'No description available.',
                    'Manhattan (exact location unspecified)'))

    def test_a_titled_run_survives(self):
        # The number is there, but so is a title.
        self.assertFalse(is_obvious_non_event(
            'Brooklyn #1196: Marathon Recovery R*n', '',
            'Brooklyn (exact location unspecified)'))
        self.assertFalse(is_obvious_non_event(
            'NAWW #396: Friendsgiving 2026', '',
            'Manhattan (exact location unspecified)'))


class TestGuardrailsHold(unittest.TestCase):
    def test_rental_listings_are_still_not_junk_by_these_rules(self):
        # Standing guardrail: "RENTAL:" is NOT junk. Neither new rule may
        # start eating rental listings.
        self.assertFalse(is_obvious_non_event(
            'RENTAL: Main Hall', '', 'Manhattan (exact location unspecified)'))
        self.assertFalse(is_obvious_non_event(
            'RENTAL: Studio 3 #2', '',
            'Manhattan (exact location unspecified)'))

    def test_location_argument_is_optional(self):
        # Every existing caller and test passes two arguments.
        self.assertFalse(is_obvious_non_event('Jazz Night', 'Live jazz.'))


if __name__ == '__main__':
    unittest.main()
