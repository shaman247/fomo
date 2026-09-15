"""Tests for the retail discount-window rule (`retail_sale_window`).

A shop's markdown period published as a dated row — "Storewide Sale!", "30% off
Used Books", "Member Shopping Days", "Winter Member Shopping Week", "Valentino
Sample Sale - Up to 80% Off". Nothing is programmed; the store's normal
merchandise is cheaper for a while. Raised by the 2026-09-15 pass, which found
~26 of these handled inconsistently — the same MoMA "Member Shopping Days" row
typed `Market` one month and `Party` another, two left UNKNOWN, nine suppressed
by hand and two still live.

The measurement that shapes the rule is the REFUTATION of a `\\bsales?\\b` gate:
over the 37,129 active events a broad name regex (percent-off | sale | discount
| shopping day/week | markdown | clearance | black friday) returns 70 hits and
the great majority are REAL — 14 library Friends book sales, plant sales, bake
sales, yard/stoop/sidewalk sales, juried arts-&-crafts sales, holiday pottery
shows-and-sales, "Discount Philosophy (Live Comedy)", "Yard Sale Comedy Open
Mic", and two workshops about building a SALES FUNNEL. So the shipped rule never
looks at the bare word "sale"; `TestSaleWordIsNotASignal` below is the guard on
that ruling.

What shipped: 27 hits over all 223,966 events, 27 retail discount windows, 0
false positives, 0 previously reviewed-and-KEPT rows, and none already caught by
another junk rule.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import is_obvious_non_event, which_junk_rule


class TestSelfDescribingWindows(unittest.TestCase):
    """Name-only arm: the title IS the offer, no other reading exists.

    Name-only is required, not lazy — the live MoMA row's body is literally
    "No description available.", so a description gate would spare the one row
    most in need of the rule.
    """

    def test_storewide_sale(self):
        # e251280, The Nonbinarian Bookstore.
        self.assertEqual('retail_sale_window', which_junk_rule(
            'Storewide Sale!',
            'The Nonbinarian is making way for new books ahead of the holiday '
            'season by offering a storewide discount all day Saturday.'))

    def test_member_shopping_days_with_no_body(self):
        # e251841, MoMA Design Store — live, and bodyless.
        self.assertEqual('retail_sale_window', which_junk_rule(
            'Member Shopping Days', 'No description available.'))
        self.assertTrue(is_obvious_non_event('Member Shopping Days', ''))

    def test_member_shopping_week(self):
        # e255498 (Guggenheim) and e114919 (Summer, MoMA).
        self.assertTrue(is_obvious_non_event(
            'Winter Member Shopping Week',
            'Members enjoy 25% discount on in-store and online purchases '
            'during the biannual Member Shopping Week, December 8-15, 2026.'))
        self.assertTrue(is_obvious_non_event(
            'Summer Member Shopping Week',
            'Members receive a 25% discount on in-store and online purchases '
            'during this special week.'))

    def test_discount_week(self):
        # e247386, Mind-Builders — live, typed `Market`.
        self.assertTrue(is_obvious_non_event(
            'Families: Dance Uniform Discount Week',
            'Dance uniforms and supplies will be available at clearance '
            'prices while quantities last.'))


class TestOfferTitlesNeedCorroboration(unittest.TestCase):
    """Percent-off / sample-sale arm: name signal plus a markdown body."""

    def test_percent_off_used_books(self):
        # e251693 and six sibling rows, Word Up Community Bookshop.
        self.assertTrue(is_obvious_non_event(
            '30% off Used Books',
            'Every last weekend of the month, all used books at Word Up '
            'Community Bookshop are 30% off!'))

    def test_percent_off_with_a_promo_code(self):
        # e238349 / e238354.
        self.assertTrue(is_obvious_non_event(
            '15% Off Back 2 School Special!',
            'Get in the school spirit and enjoy 15% off using code SCHOOL15!'))

    def test_ticket_discount_for_a_real_show_is_still_the_offer(self):
        """e220671 — the musical is real; THIS row is the discount on it."""
        self.assertTrue(is_obvious_non_event(
            '50% Off - "Brooklyn\'s Bridge" Musical',
            'Get 50% off tickets to the limited-run musical Brooklyn\'s '
            'Bridge, inspired by the life of Emily Roebling.'))

    def test_sample_sales(self):
        for name, desc in (
            ('Valentino Sample Sale - Up to 80% Off in New York, Long Island',
             'Discover a curated selection of Valentino collections at deep '
             'discounts.'),
            ('Mackage Sample Sale - New York',
             'Shop premium luxury outerwear at a fraction of the cost during '
             'this exclusive Mackage sample sale.'),
            ('Sweater Sample Sale', 'Ladies and mens sweaters $5 & up'),
            ('Artbook | D.A.P. Sample Sale',
             "A sample sale of books pulled from Artbook's New York offices, "
             'with books priced at $5, $10, $20, $40.'),
        ):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, desc))

    def test_sample_sale_with_no_markdown_language_falls_through(self):
        """Accepted fail-safe miss (e16543, e142306, e216402)."""
        self.assertFalse(is_obvious_non_event(
            'Moose Knuckles Sample Sale - New York',
            'A major sample sale featuring luxury outerwear and apparel from '
            'Moose Knuckles at the Metropolitan Pavilion.'))

    def test_percent_off_with_no_body_falls_through(self):
        self.assertFalse(is_obvious_non_event('30% off Used Books', ''))


class TestSaleWordIsNotASignal(unittest.TestCase):
    """Guard on the refuted `\\bsales?\\b` gate — these are all real events."""

    def test_real_sales_pass_through(self):
        cases = [
            ('Friends of Greenpoint Library Fall Book Sale',
             'Books starting at $1, discounted media; proceeds support the '
             'library.'),
            ('Hazlet Fall Book Sale!',
             'Come shop the sale hosted by the Friends of the Library! Browse '
             'a great selection of books starting at just $0.50.'),
            ('NJBG Fall Plant Sale',
             'The sale offers fall flowers, shrubs, perennials and native '
             'plants at discounted prices.'),
            ('Our Little Bake Sale',
             'Participating bakers and shops include Caffe Panna and Cove.'),
            ('Saxon Woods Garage Sale',
             'Browse second-hand treasures like clothing, household items, '
             'furniture, toys and books.'),
            ('Sidewalk Sale!',
             'Join the bookstore outside for its first fall sidewalk sale, as '
             'it makes room for new books.'),
            ('Fine Arts & Crafts Sale at Anderson Park',
             'Each show features juried fine artists and craft artisans '
             'displaying and selling their hand-crafted work.'),
            ('Holiday Pottery Show & Sale',
             'A holiday pottery show and sale; December 4 is a members-only '
             'preview day.'),
            ('Electrix Vintage Fill-a-Bag Sale (LI)',
             'Fill a bag with vintage for just $10!'),
            ('Record Store Day',
             'Celebrate with exclusive vinyl releases, 15% off all used '
             'records, and live DJ sets all afternoon.'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertIsNone(which_junk_rule(name, desc))

    def test_sales_as_a_subject_of_real_programming(self):
        cases = [
            ('Discount Philosophy (Live Comedy)',
             'A comedy show where comedians interrogate questions that have '
             'plagued humanity for ages.'),
            ('Yard Sale Comedy Open Mic',
             'FREE comedy open mic every Monday, hosted by the Yard Sale '
             'Girls.'),
            ('AI Incubator | Session 3: The Sales Funnel, Built with AI',
             'A hands-on session on building an AI-assisted sales funnel.'),
            ('Getting on Shelf: Building a Sales Strategy that Drives Retail '
             'Success',
             'An interactive panel discussion featuring industry veterans.'),
        ]
        for name, desc in cases:
            with self.subTest(name=name):
                self.assertIsNone(which_junk_rule(name, desc))


class TestSaleWindowVetoes(unittest.TestCase):
    def test_attendable_noun_in_the_name_vetoes(self):
        """Measured near misses: a league, a benefits enrollment event, a party."""
        self.assertFalse(is_obvious_non_event(
            'Your Social Summer Starts Here 20% Off for NEW Bowlers!',
            'A 6-week summer social bowling league featuring cold drinks, '
            'weekly trivia, and social networking. The league is discounted '
            'for new bowlers.'))
        self.assertFalse(is_obvious_non_event(
            '50% OFF OMNY (Metro) Cards with Fair Fares',
            'The Literacy Zone Team is hosting a Fair Fares OMNY Card '
            'Enrollment Event with the Department of Social Services, where '
            'riders get a 50% discount on fares.'))
        self.assertFalse(is_obvious_non_event(
            'Sample Sale Party with Open Bar',
            'Shop discounted samples with drinks all evening.'))

    def test_programming_around_the_markdown_vetoes(self):
        """e70851, e224755 and e158946 — an occasion built on the sale."""
        self.assertFalse(is_obvious_non_event(
            'Spring Sample Sale',
            'Celebrate Spring with a sample sale featuring discounted books, '
            'an ARC giveaway, and food popups from Sisi\'s Little Tarts.'))
        self.assertFalse(is_obvious_non_event(
            'Late Summer Sample Sale',
            'Liz\'s Book Bar hosts another late summer sample sale with '
            'anticipated discounts, drink specials, and possibly a giveaway.'))
        self.assertFalse(is_obvious_non_event(
            'Pop-Up Sample Sale',
            'Score leather varsity jackets and fine knit shirts at deep '
            'discounts.'))


if __name__ == '__main__':
    unittest.main()
