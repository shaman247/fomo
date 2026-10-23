"""Tests for the BL60 in-store promotion rules (`instore_giveaway`,
`retail_personalization`).

Raised by the 2026-10-19 run: three w6018 (Dumbo Improvement District) rows
about the café maman were promotions, not events — a latte collaboration whose
first 50 guests get a complimentary drink, a sticker hidden under the cup that
wins a cookie, and a costume voucher for a croissant. The 2026-10-23 hide pass
added retail activations at The Shops at Columbus Circle (a Jo Malone
hand-painting service, a personalization station).

Precision over recall: the same freebie mechanics appear in real events (watch
parties, DJ mornings, singles walks, costume parties), and real tastings,
workshops and giveaway-with-program events must survive. Measured over all
267,846 events: `instore_giveaway` 4 hits, `retail_personalization` 4 hits, all
hand-suppressed promotions, none live.

Run: ./venv/bin/python pipeline/tests/test_junk_filter_instore_promos.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import is_obvious_non_event, which_junk_rule


class TestInstoreGiveaway(unittest.TestCase):

    def test_maman_rows(self):
        for name, desc in (
            ('Maelys x maman collaboration',
             'maman DUMBO serves a MAËLYS SO-SILKY Latte from October 21 to 23 '
             'in partnership with the body care brand. On October 21 the first '
             '50 guests receive a complimentary beverage plus a deluxe SO-SILKY '
             'sample.'),
            ('Find a Pumpkin, Find a Cookie at Maman',
             'All week, 5 hot cups each day have a pumpkin sticker hidden '
             'underneath; find one and bring it to the register for a '
             'complimentary cookie of your choice.'),
            ('Come in Costume, Leave With a Croissant at Maman',
             "On Halloween, guests who visit maman in costume receive a "
             "Halloween croissant card with a Hershey's Cookies 'n' Creme treat "
             "and a voucher for a complimentary croissant or pain au chocolat "
             "redeemable November 1-14."),
        ):
            with self.subTest(name=name):
                self.assertEqual('instore_giveaway', which_junk_rule(name, desc))

    def test_gift_with_purchase(self):
        # e18173, hand-suppressed.
        self.assertEqual('instore_giveaway', which_junk_rule(
            'Gift with Purchase at TUMI',
            'Visit TUMI at The Shops at Columbus Circle and receive an exclusive '
            'gift with your purchase for a limited time while supplies last.'))

    def test_freebies_at_real_events_survive(self):
        for name, desc in (
            # e146663 — a watch party.
            ('Knicks Watch Party! GAME 2!!',
             'First 15 people in a Knicks jersey get a SHOT!'),
            # e288821 — a live party; "in costume gets a free shot".
            ("Devil's Disco",
             "Devil's Disco at The Seneca on Devil's Night with food and drink "
             "specials; everyone in costume gets a free shot. 21+."),
            # e286277 — a DJ morning party with a free drink for the first 50.
            ('Coffeeandbeats X Nooly',
             'A Coffee & Beats morning party with NOOLY at Soft Bar Cafe with DJs. '
             'Free entry; the first 50 people get a free signature drink.'),
            # e232908 — free admission, not a café item.
            ('Singles walk - first 25 register',
             'An outdoor social walk for adult singles. The first 25 people to '
             'register receive free admission.'),
            # e251995 — brand activation WITH programming ("Join us").
            ('Ciele Nyc: Lipstick Roulette',
             'Join us for Lipstick Roulette — the first 500 guests get a free '
             'sample lipstick.'),
            # A tasting that hands out a freebie is still a tasting.
            ('Fall Cider Tasting',
             'Sample five ciders; the first 20 guests receive a complimentary '
             'glass to take home and a free cookie.'),
            # A workshop with a voucher.
            ('Latte Art Workshop',
             'Learn to pour hearts and rosettas. Every participant leaves with a '
             'voucher for a free latte.'),
            # Gift-with-purchase at a book signing.
            ('Author Signing: Jane Doe',
             'Meet the author; free tote gift with purchase of the book.'),
        ):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))

    def test_bare_mechanic_without_a_cafe_item_survives(self):
        # e282085 — live customization pop-up; no complimentary food/drink.
        self.assertFalse(is_obvious_non_event(
            'Roamstroll × Boris & Horton Pop-Up',
            'One-day customization pop-up where you can design a bandana for '
            'your pet. The first 30 guests get a patch.'))


class TestRetailPersonalization(unittest.TestCase):

    def test_hide_pass_rows(self):
        for name, desc in (
            ('Tartan Tales: Hand-Painted Keepsakes',
             'Make your gifting more personal with a hand-painted finishing '
             'touch. Choose initials, names, meaningful dates, or festive '
             'illustrations created by a local artist to transform your Jo '
             'Malone London gift into a one-of-a-kind keepsake.'),
            ('The Personalization Station',
             'A holiday personalization station on Saturdays and Sundays, '
             'November 14th through December 20th.'),
            ('Soccer Ball Monogramming',
             'Visit us for professional soccer ball monogramming services '
             'available for a limited time.'),
            ('Complimentary Classic Monogramming at Tumi', 'No description available.'),
        ):
            with self.subTest(name=name):
                self.assertEqual('retail_personalization', which_junk_rule(name, desc))

    def test_teaching_and_programming_survive(self):
        for name, desc in (
            # e91710 — a class that makes monogrammed designs.
            ('Intro to Embroidery: Tote Bags',
             'Learn the practical applications of embroidery by creating '
             'monogrammed designs on a unique tote bag. This beginner-friendly '
             'class covers fundamental stitches.'),
            # e295622 — a grand opening with a DJ and chainstitch monogramming.
            ('West Elm Williamsburg Grand Opening',
             "Celebrate West Elm's new Williamsburg store with free coffee and "
             'matcha, music from a local DJ and custom chainstitch monogramming.'),
            ('Monogramming Workshop',
             'A hands-on workshop on hand monogramming linen napkins.'),
        ):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, desc))


class TestOtherHidePassRowsUnchanged(unittest.TestCase):
    """The Oishii retail opening (e246953) has a one-off shape no narrow rule
    covers; it stays with the hide pass rather than a store-opening rule."""

    def test_oishii_pop_up_falls_through(self):
        self.assertIsNone(which_junk_rule(
            'Oishii Pop-Up at Chelsea Market',
            'Oishii opens its first-ever retail destination at Chelsea Market, '
            'introducing Connoisseur Grade Berries. Available Thursday-Sunday '
            'from 11AM-7PM.'))


if __name__ == '__main__':
    unittest.main()
