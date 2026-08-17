"""Tests for the "On this Day:" archival-post rule in is_obvious_non_event.

Park conservancies publish historical anniversary posts alongside real
programming. Four reached `events` from w82 Fort Tryon Park Conservancy and
were only caught downstream, by the event-type classifier labelling them
UNKNOWN (190778 "On this Day: Park Dedication", 190779 "On this Day: Park
Opening"); 173043 was still live and unsuppressed when this rule shipped.

Verified over all 180,262 events: 5 name matches, 5 suppressed, 0 false
positives. Its sibling — the awareness-observance titles that were filed in
the same task — was REJECTED; see TestObservanceTitlesStayUnfiltered.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import is_obvious_non_event


class TestArchivalOnThisDayPosts(unittest.TestCase):
    def test_park_dedication_anniversary(self):
        self.assertTrue(is_obvious_non_event(
            'On this Day: Park Dedication',
            'On October 12, 1935, Fort Tryon Park was officially dedicated to '
            'the public in a ceremony attended by philanthropist John D. '
            'Rockefeller Jr. and New York City Parks Commissioner Robert Moses.'))

    def test_landmark_dedication_anniversary(self):
        self.assertTrue(is_obvious_non_event(
            'On this Day: NYC Landmark Dedication',
            'On September 20, 1983, the New York City Landmarks Preservation '
            'Commission officially designated Fort Tryon Park as a Scenic '
            'Landmark.'))

    def test_colonial_era_year_is_historical(self):
        """e218929 slipped through when the year range started at 1800:
        Margaret Corbin was born in 1751. The range now starts at 1500."""
        self.assertTrue(is_obvious_non_event(
            'On this Day: Margaret Corbin’s Birthday',
            'Margaret Cochran Corbin was born on November 12, 1751, in '
            'Franklin County, Pennsylvania. Orphaned at the age of five after '
            'her father was killed in an Indian raid, Margaret faced '
            'hardships early in life.'))

    def test_commemoration_wording_without_a_bare_year(self):
        """The historical gate accepts commemoration language, not just a year."""
        self.assertTrue(is_obvious_non_event(
            'On this Day: Met Cloisters Opening',
            'A historical commemoration of the anniversary of the opening of '
            'The Met Cloisters museum.'))

    def test_separator_variants(self):
        for name in ('On This Day - Park Opening',
                     'On this day — Bridge Completed',
                     'ON THIS DAY: Museum Founded'):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(
                    name, 'Commemorating the 1935 opening of the park.'))

    def test_a_real_anniversary_gathering_survives(self):
        """The veto is what spares a conservancy that runs an actual walk."""
        self.assertFalse(is_obvious_non_event(
            'On this Day: Park Dedication',
            'On October 12, 1935, Fort Tryon Park was dedicated. Join us for a '
            'guided anniversary walk retracing the ceremony route; free '
            'admission, no registration required.'))

    def test_requires_the_historical_gate(self):
        """Without a past date or commemoration language it is not an archival post."""
        self.assertFalse(is_obvious_non_event(
            'On this Day: Poetry Reading',
            'An evening of new work from Washington Heights poets.'))

    def test_needs_a_description(self):
        """Blank-description rows fall through rather than being guessed at."""
        self.assertFalse(is_obvious_non_event('On this Day: Park Opening', ''))

    def test_phrase_elsewhere_in_the_name_is_untouched(self):
        for name in ('Reflections on This Day',
                     'On This Day We Rise: A Community Celebration'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(
                    name, 'Commemorating the 1965 march with music and speakers.'))


class TestObservanceTitlesStayUnfiltered(unittest.TestCase):
    """The sibling shape deliberately NOT automated must still pass through.

    "National/World/International … Day/Week/Month" was prototyped as an
    automatic rule and rejected: 75 matches over the whole events table, the
    large majority real programming. Scoping it to the Parks source that raised
    it does not rescue it either. These tests pin that decision so a future
    change has to confront it.
    """

    def test_real_observance_programming_is_not_auto_suppressed(self):
        cases = [
            ('World Tai Chi Day',
             "Celebrate World Tai Chi Day at Bryant Park with free instruction "
             "and continuous demonstrations of T'ai chi ch'uan and Qigong."),
            ('National Trails Day',
             'Explore the eight miles of beautiful trails in Fort Tryon Park '
             'designed by the Olmsted Brothers.'),
            ('World Fish Migration Day',
             "Wade into the Hudson River to collect and count local fish "
             "species. This community science event is held in partnership "
             "with local scientists."),
            ('National Scrabble Day',
             'Join us for a fun afternoon of playing Scrabble to celebrate '
             'National Scrabble Day.'),
            ("International Women's Day",
             'A global day celebrating the achievements of women. This local '
             'gathering honors them with speakers and community.'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_the_parks_junk_observances_also_pass_through(self):
        """Documents the accepted miss: these two ARE junk but stay unfiltered.

        190775 / 190776 — the rows that motivated the rejected rule. They differ
        from the real ones only by inviting a solo visit rather than a gathering,
        which is too fuzzy for is_obvious_non_event. They are routed to
        scripts/find_review_candidates.py instead.
        """
        self.assertFalse(is_obvious_non_event(
            'National Walk Your Dog Week',
            'Fort Tryon Park is the perfect place to celebrate National Walk '
            'Your Dog Week with your furry friend!'))
        self.assertFalse(is_obvious_non_event(
            'World Mental Health Day',
            'On World Mental Health Day, take a moment to recharge and '
            'reconnect with nature at Fort Tryon Park.'))


if __name__ == '__main__':
    unittest.main()
