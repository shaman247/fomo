"""Tests for the ticketing-upsell-product rule in is_obvious_non_event.

A venue's ticket store publishes its packages and bundles on the same feed as
its programming, so a thing you BUY reaches the extractor looking like a thing
you ATTEND. The 2026-08-17 classification pass could only label two ARTECHOUSE
(w1166) rows UNKNOWN: e222525 "VIP & Date Night Packages" and e222526
"ARTECHOUSE x Color Factory Experience Bundle". The venue's genuine exhibitions
already exist as their own rows, so these add nothing but a duplicate pin.

Measured over all 191,070 events plus 134,254 crawl_events from the last 21
days: 8 net-new events, 2 net-new crawl_events, every one a purchase product or
a private-hire package. ZERO live, ZERO reviewed-and-kept, ZERO false positives.

Two real events clear both gates and are saved only by the veto — they are the
reason the veto exists, and TestRealProgrammesSurvive pins both.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import is_obvious_non_event


class TestTicketProductPackages(unittest.TestCase):
    def test_artechouse_vip_and_date_night_packages(self):
        # e222525 — one of the two rows that motivated the rule.
        self.assertTrue(is_obvious_non_event(
            'VIP & Date Night Packages',
            'VIP and Date Night Packages provide access to the ARTECHOUSE NYC '
            'experience during the listed availability window.'))

    def test_artechouse_color_factory_bundle(self):
        # e222526 — the other one.
        self.assertTrue(is_obvious_non_event(
            'ARTECHOUSE x Color Factory Experience Bundle',
            'The bundle includes one anytime ticket to ARTECHOUSE NYC and one '
            'anytime ticket to Color Factory New York. Both tickets must be '
            'redeemed within 30 days of purchase.'))

    def test_private_hire_birthday_packages(self):
        # e60559 / e37160 (Empire State Building, w838).
        self.assertTrue(is_obvious_non_event(
            'Birthday Celebration Packages',
            "Host a private birthday celebration in the world's most famous "
            'building. Packages include admission for up to ten guests.'))

    def test_membership_bundle(self):
        # e33731 (SUMMIT One Vanderbilt, w182).
        self.assertTrue(is_obvious_non_event(
            'Spring Bundle',
            'Visiting NYC this spring? Become a SUMMIT Insider to get '
            'exclusive early access — the bundle includes two general '
            'admission tickets.'))

    def test_preorder_food_package(self):
        # e72503 (Russ & Daughters, w121).
        self.assertTrue(is_obvious_non_event(
            'Russ & Daughters’ Passover Deluxe Package',
            'A pre-order event offering a Passover Deluxe Package provided by '
            'Russ & Daughters for pickup during the holiday.'))


class TestRealProgrammesSurvive(unittest.TestCase):
    """The veto is measured, not decorative.

    Only 17 titles in 191,070 events end on package/bundle, and TWO of them are
    real. A bare name-tail rule would have killed both.
    """

    def test_cinema_shorts_programme(self):
        # e21299 — a "shorts package" is a cinema programme, not a product.
        self.assertFalse(is_obvious_non_event(
            'Buster Keaton Shorts Package',
            'A family-friendly collection of silent comedy shorts featuring '
            'Buster Keaton. The package includes admission to all four films.'))

    def test_care_package_packing_drive(self):
        # e23209 — people show up and pack the packages.
        self.assertFalse(is_obvious_non_event(
            'LIU Cares Week: Care in Every Package',
            'Students and faculty come together to participate in this '
            'service drive; each package includes toiletries donated by the '
            'campus community.'))


class TestNameTailAnchorIsLoadBearing(unittest.TestCase):
    """"VIP package" appears INSIDE plenty of real listings. Only a title that
    ENDS on the product noun is the product."""

    def test_real_event_offering_an_optional_vip_package(self):
        # e216690 (Bear Mountain Inn) — a genuine ticketed themed brunch.
        self.assertFalse(is_obvious_non_event(
            'Magical Princess Brunch',
            'Our Princess Brunch is back by popular demand! This special '
            'brunch experience will feature two seatings, plus an optional VIP '
            'package for children who want an extra touch of princess magic.'))

    def test_package_word_mid_title_does_not_fire(self):
        self.assertFalse(is_obvious_non_event(
            'Package Deal: An Evening of New Plays',
            'The evening includes admission to three staged readings.'))


class TestDescriptionGateRequired(unittest.TestCase):
    """A bare product-shaped title with no purchase language stays editorial —
    the same fail-safe direction as the rest of this block."""

    def test_blank_description_does_not_fire(self):
        self.assertFalse(is_obvious_non_event('Family Package', ''))
        self.assertFalse(is_obvious_non_event(
            'Family Package', 'No description available.'))

    def test_marketing_copy_without_a_purchase_term_is_an_accepted_miss(self):
        # e205218 — the February ARTECHOUSE bundle. Documents the miss.
        self.assertFalse(is_obvious_non_event(
            'ARTECHOUSE x Color Factory Experience Bundle',
            'Ignite your senses with the ARTECHOUSE x Color Factory '
            'Experience.'))


if __name__ == '__main__':
    unittest.main()
