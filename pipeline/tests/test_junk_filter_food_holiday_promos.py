"""Tests for the "National <food/drink> Day" promo rule in is_obvious_non_event.

e221838 "National Fajita Day - Come grab some sizzling goodness for National
Fajita Day!" (w868 Hudson Blue Bar & View) reached the map and could only be
caught downstream, by the event-type classifier labelling it UNKNOWN on
2026-08-17. A bar or restaurant hangs a hashtag food holiday on its normal
service: nothing is programmed, nothing starts, you just eat there that day.

**A NAME-ONLY version of this rule was measured and REFUTED on 2026-07-27**
(test_processor.TestJunkFilterGaps20260727
.test_national_food_day_deliberately_not_dropped): a bare "National Chicken Wing
Day" with no body is a coin flip on intent, because venues do host real themed
nights on the same food holidays. **That ruling stands.** This rule adds the
second signal the refuted one was missing — the body has to read as dining
marketing ("Come grab…", "Buy one, get one", "$5 pours") — and it therefore
still lets a bare marker through untouched. It also picks up e200728, the row
that pass had to suppress by hand, whose body was "Come grab some wings…" all
along.

**Why this was automated when the weekday-special family next door was not.**
The refutation in
test_junk_filter_calendar_non_events.TestWeekdayFoodSpecialsStayUnfiltered turns
on a human having reviewed "Whiskey Wednesday" and deliberately KEPT it, which
makes that class a venue-by-venue product judgment. The national-food-day rows
measure the other way round: of the nine matches a human has reviewed, all nine
were SUPPRESSED by hand (e17988, e116045, e134431, e187192, e191335, e191337,
e191340, e200728, e218856), and none was kept.

Measured over all 190,989 events: 30 name matches, all 30 bar/restaurant promos
from five venues (w868, w1348, w1349, w1199, w5057), ZERO real events, ZERO
reviewed-and-kept; 23 also clear the description gate and are what the rule
drops. The one still live (e191338 "National Drink Beer Day") is a correct kill
the suppression pass has not reached.

The name gate is that the title is EXACTLY "National <food/drink> Day" with the
qualifier from a closed food/drink list. The national-day family at large is
overwhelmingly real programming, so nothing but the food/drink axis may decide
it.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import is_obvious_non_event  # noqa: E402


class TestFoodHolidayPromos(unittest.TestCase):
    def test_the_row_that_had_to_be_hand_suppressed(self):
        """e221838 — the extractor glued the body onto the title."""
        self.assertTrue(is_obvious_non_event(
            'National Fajita Day - Come grab some sizzling goodness for '
            'National Fajita Day!',
            'Come grab some sizzling goodness for National Fajita Day!'))

    def test_the_bare_title_form(self):
        self.assertTrue(is_obvious_non_event(
            'National Fajita Day', 'Come grab some sizzling goodness!'))

    def test_the_corpus_rows_from_the_five_promo_venues(self):
        cases = [
            ('National Margarita Day',
             "Come celebrate National Margarita Day at Rosa's At Park."),
            ('National Margarita Day',
             'Celebrate National Margarita Day with specialty drinks and food '
             'while enjoying panoramic views.'),
            ('National Bourbon Day',
             'Join us on National Bourbon Day! Sit back, relax and sip on your '
             'favorite bourbon!'),
            ('National Pretzel Day',
             'Buy one pretzel, get one free, while supplies last.'),
            ('National French Fry Day',
             'Join us on National French Fry Day July 12th and grab a bite '
             '(with a side of fries)!'),
            ('National Mojito Day',
             "Grab a cold refreshing Mojito because it's National Mojito Day!"),
            ('National Chicken Wing Day',
             'Come grab some wings on National Chicken Wing Day on July 29th!'),
            ('National IPA Day', 'Come grab a beer with us on National IPA Day!'),
            ('National Whiskey Sour Day',
             "It's National Whiskey Sour Day! Come down and let our awesome "
             'bartenders make you a great one.'),
            ('National Red Wine Day',
             "It's National Red Wine Day! Come enjoy a glass from our "
             'excellent selection!'),
            ('National Cheeseburger Day',
             'Come grab a giant juicy cheeseburger for National Cheeseburger '
             'Day Sept 18th!'),
            ('National Pina Colada Day',
             'Join us on National Pina Colada Day and grab an icy cold one!'),
            ('National Drink Beer Day',
             'Join us for National Drink Beer Day on Sept 28th and try one of '
             'our many craft brews!'),
            ('National Dessert Day',
             'Indulge in dinner and a dessert on National Dessert Day!'),
        ]
        for name, desc in cases:
            with self.subTest(name=name, desc=desc[:30]):
                self.assertTrue(is_obvious_non_event(name, desc))

    def test_the_2026_07_27_refutation_is_honoured(self):
        """A bare marker with no body stays editorial — the refuted rule's case."""
        self.assertFalse(is_obvious_non_event('National Chicken Wing Day'))
        self.assertFalse(is_obvious_non_event('National Taco Day', ''))
        self.assertFalse(is_obvious_non_event(
            'National Taco Day', 'No description available.'))
        self.assertFalse(is_obvious_non_event('National Margarita Day Party'))

    def test_a_body_with_no_marketing_language_survives(self):
        """Yield deliberately given up to keep the bar high."""
        for name, desc in (
                ('National Rum Day', 'Join us on National Rum Day on August 16th!'),
                ('National Pasta Day', 'Because life is better with pasta!'),
                ('National Martini Day',
                 'In case you needed an excuse, join us for National Martini Day.'),
                ('National Vanilla Ice Cream Day',
                 'The classic. The original. The best.'),
                ('National Prosecco Day',
                 'Start your night with some bubbly for National Prosecco Day!'),
                ('National Wine and Cheese Day',
                 'Join us on National Wine & Cheese Day July 25th!')):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))


class TestRealNationalDaysSurvive(unittest.TestCase):
    """The national-day family at large is real programming."""

    def test_non_food_national_days(self):
        cases = [
            ('National Trails Day',
             'Explore the eight miles of beautiful trails in Fort Tryon Park.'),
            ('National Cleanup Day',
             'Join the movement to keep our planet clean and green.'),
            ('National Zoo Day',
             "Come learn about our nation's zoos and color your favorite zoo "
             'animal.'),
            ('National Superhero Day', 'Come color your favorite Superhero picture!'),
            ('National Scrabble Day',
             'Join us for a fun afternoon of playing Scrabble.'),
            ('National Seed Swap Day',
             'Join an interactive program celebrating the joys of gardening.'),
            ('National Honey Bee Day!',
             'An exciting celebration of honey and pollinator friends!'),
            ('National Youth Takeover Day',
             'A day for young people to lead, create, and share.'),
            ('National Letters to Elders Day',
             'Harness some creativity to share a smile by writing letters.'),
            ('National Take A Walk in the Park Day',
             'Celebrate by joining a hike at the Big Bend property.'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_a_real_occasion_built_on_the_holiday_survives(self):
        """Anything appended to the title means somebody programmed something."""
        cases = [
            ('National Ice Cream Day at the Carousel',
             'Join Prospect Park Alliance for a ride on our historic Carousel, '
             'and get a free ice cream.'),
            ('National Pizza Day Dinner',
             'Celebrate National Pizza Day by grabbing a slice or a pie with '
             'fellow pizza lovers in Brooklyn.'),
            ('Whispering Angel Rosé Tasting – National Rosé Day',
             "Sip, swirl, and celebrate National Rosé Day with Whispering "
             "Angel's finest."),
            ('National Chicken Finger Day Challenge',
             'HEATONIST is back at Brooklyn Brewery, turning up the heat.'),
            ('Paradise Sunset Rooftop Day Party -National Tequila Day Party',
             'A signature rooftop day party featuring curated sounds.'),
            ('National Challah Day Pop-up with Challah Days!',
             "Celebrate National Challah Day at Susan Alexandra's Madison Ave "
             'store.'),
            ('National Dive Bar Day Screening of Bloody Nose Empty Pockets',
             'National Dive Bar Day screening of the film.'),
            ('ASN National Ice Cream Day!', 'No description available.'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_foods_off_the_list_are_spared_by_omission(self):
        """The intended failure direction: miss junk rather than kill events."""
        cases = [
            ('National Oreo Day',
             'Celebrate the birthplace of the OREO cookie at the old Nabisco '
             'Factory with special OREO treats.'),
            ('National "Tziki" Day',
             'A food-focused celebration dedicated to the creamy Mediterranean '
             'staple, Tzatziki.'),
            ('National Eat Outside Day',
             'Celebrate National Eat Outside Day at Fort Tryon Park!'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_programming_language_vetoes_the_drop(self):
        """The realistic failure mode: a venue makes the holiday a real party."""
        cases = [
            ('National Margarita Day',
             'Live music, a DJ and a tequila tasting all night long.'),
            ('National Taco Day',
             'Tickets are $25 and include a cooking class with our guest chef.'),
            ('National Beer Day',
             'A brewery tour followed by trivia; RSVP required.'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))


class TestWeekdaySpecialsUnaffected(unittest.TestCase):
    """The refuted weekday-special family must stay untouched by this arm.

    Cross-check of test_junk_filter_calendar_non_events
    .TestWeekdayFoodSpecialsStayUnfiltered — "Whiskey Wednesday" is
    `reviewed=1, suppressed=0`, a row a human deliberately kept.
    """

    def test_weekday_specials_still_survive(self):
        cases = [
            ('Taco Tuesdays',
             '$5 tacos and half-price margaritas are offered every Tuesday.'),
            ('Whiskey Wednesday',
             'Every Wednesday features a different selection of whiskeys.'),
            ('Martini Monday',
             'Start your week at Mosaic with special pricing on signature '
             'martinis.'),
            ('Burger Mondays', 'Buy any burger and get a free beer on Mondays.'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))


if __name__ == '__main__':
    unittest.main()
