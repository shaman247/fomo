"""Tests for the operational-notice and housing-corp rules in is_obvious_non_event.

Added 2026-08-22. The event-type classification pass produced 10 UNKNOWN rows —
junk that reached the map and was only caught downstream when the classifier
could not assign it a type. Four gates were added for the three recurring shapes
among them; the other UNKNOWNs were deliberately left alone (see the NOT COVERED
class at the bottom).

Every rule below was precision-audited over the full 198,068-event corpus before
being shipped, exactly as `test_junk_filter_hours_notices.py` describes. The
counts quoted in each docstring are that audit, frozen. **Do not loosen any of
these without re-running the corpus audit** — the housing-corp rule in particular
started far wider and had to be cut down after the audit caught real events.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import (is_obvious_non_event, _is_early_close_notice,
                       _is_admin_deadline, _is_maintenance_tail_block,
                       _is_housing_corp_booking)


class TestEarlyCloseNotice(unittest.TestCase):
    """17 corpus matches, all genuine closure notices, 0 false positives.

    Name-only by design: the body is always a real sentence explaining the early
    close, so a description gate would spare every one of them.
    """

    def test_the_row_that_reached_the_map(self):
        self.assertTrue(is_obvious_non_event(
            'Greenwich Library Early Close (5pm ET)',
            'The Greenwich Library will close at 5 pm today due to Summer hours'))

    def test_closing_early_variants(self):
        for name in ('Bookstore Closing Early',
                     "Shops Closing Early for New Year's Eve",
                     'New Year’s Eve: Early Closing',
                     'Early Closing: 2PM',
                     'Library Closing at 2:00PM',
                     'Main Library Closing Early'):
            with self.subTest(name=name):
                self.assertTrue(_is_early_close_notice(name))

    def test_a_described_body_does_not_rescue_it(self):
        # The explanatory body is the norm for this shape, not a signal of realness.
        self.assertTrue(is_obvious_non_event(
            'Top of the Rock and The Rink Early Closing',
            'Information regarding limited hours for the observation deck'))

    def test_real_events_are_kept(self):
        for name in ('Closing Night Party', 'Closing Reception: Ash Allen',
                     'Early Bird Yoga', 'The Closer', 'Closing Arguments: A Play'):
            with self.subTest(name=name):
                self.assertFalse(_is_early_close_notice(name))


class TestAdminDeadline(unittest.TestCase):
    """38 corpus matches, all genuine deadlines, 0 false positives.

    Anchored at the START of the name so a real program that merely mentions a
    deadline downstream survives.
    """

    def test_the_rows_that_reached_the_map(self):
        self.assertTrue(is_obvious_non_event(
            'Last Day to Turn in Reading Logs',
            'Ages 0-12. For every 5 books your child reads, they will have a chance to win'))
        self.assertTrue(is_obvious_non_event(
            'Photography Show Registration Closes', 'No description available.'))

    def test_deadline_variants(self):
        for name in ('Last Day to Apply for Spring 2026 Graduation',
                     'DEADLINE: NYU Startup Bootcamp',
                     'Teen Council Spring 2026 Application Deadline',
                     'Young Poets Submissions Due',
                     'Writing on Race and Immigration: Applications Due',
                     'Last Day to Complete Spring 2026 Residency'):
            with self.subTest(name=name):
                self.assertTrue(_is_admin_deadline(name))

    def test_start_anchor_spares_a_real_program(self):
        # A real event that merely mentions a deadline is not a deadline row.
        for name in ('Poetry Workshop (registration closes Friday)',
                     'Open Studio — sign up by the deadline',
                     'Application Workshop: How to Apply for Grants'):
            with self.subTest(name=name):
                self.assertFalse(_is_admin_deadline(name))


class TestMaintenanceTailBlock(unittest.TestCase):
    """1 corpus match, 0 false positives.

    Tail-anchoring alone is NOT safe, which is why the description gate exists.
    """

    def test_the_row_that_reached_the_map(self):
        self.assertTrue(is_obvious_non_event(
            'Discovery Lab Maintenance', 'Dicovery Lab Closed till 10am'))

    def test_blank_body_also_fires(self):
        self.assertTrue(_is_maintenance_tail_block('Community Room Maintenance', ''))
        self.assertTrue(_is_maintenance_tail_block(
            'Community Room Maintenance', 'No description available.'))

    def test_real_maintenance_classes_are_kept(self):
        # These are the false positives the description gate exists to prevent.
        for name, desc in (
                ('Bike Maintenance', 'Learn to fix a flat and tune your derailleur with our mechanic.'),
                ('Car Maintenance', 'A hands-on intro to checking your oil, tires and brakes.'),
                ('Home Maintenance', 'A workshop on seasonal upkeep for new homeowners.')):
            with self.subTest(name=name):
                self.assertFalse(_is_maintenance_tail_block(name, desc))
                self.assertFalse(is_obvious_non_event(name, desc))


class TestHousingCorpBooking(unittest.TestCase):
    """1 corpus match, 0 false positives — deliberately narrow.

    An earlier draft keyed on a generic "association|inc|corp" tail and produced
    7 false positives out of 10 corpus matches. Those are frozen below as
    negative cases; they are the reason this rule lists only housing/condo
    entity types.
    """

    def test_the_row_that_reached_the_map(self):
        self.assertTrue(is_obvious_non_event(
            'Huntington Village Coop / Nathan Hale Owners Corp',
            'No description available.'))

    def test_housing_entity_variants(self):
        for name in ('Nathan Hale Owners Corp', 'Parkview Condominium Association',
                     'Riverside Tenants Association', 'Sunnyside Co-op Board'):
            with self.subTest(name=name):
                self.assertTrue(_is_housing_corp_booking(name, ''))

    def test_the_false_positives_that_forced_the_narrowing(self):
        # Real programs that an "association|inc" tail rule wrongly matched.
        for name in ('Street Tree Care w/ Decatur Block Association',
                     'Street Tree Care w/ 95th Street Block Association',
                     'Celebrate Lunar New Year with the New York Hua Xia Arts Association',
                     'Music Storytime With Intersection Music and Arts, Inc.'):
            with self.subTest(name=name):
                self.assertFalse(_is_housing_corp_booking(name, ''))
                self.assertFalse(is_obvious_non_event(name, ''))

    def test_civic_associations_are_kept(self):
        # The review doc is explicit that civic engagement stays on the map.
        self.assertFalse(is_obvious_non_event('RVC Civic Association', 'No description available.'))
        self.assertFalse(is_obvious_non_event('Decatur Block Association', ''))

    def test_a_described_program_survives(self):
        self.assertFalse(_is_housing_corp_booking(
            'Nathan Hale Owners Corp',
            'Open to the public: a panel on co-op governance with Q&A and refreshments.'))


class TestDeliberatelyNotCovered(unittest.TestCase):
    """UNKNOWN rows from the same 2026-08-22 batch that were LEFT ALONE.

    Each was judged too risky to filter for the yield of a single row. They are
    asserted here so that a future widening of these rules is a deliberate,
    visible change to this file rather than a silent side effect.
    """

    def test_ambiguous_bare_names_are_not_filtered(self):
        # Could each be a real show; only a missing description argues otherwise.
        self.assertFalse(is_obvious_non_event("That's Weird!", 'No description available.'))
        self.assertFalse(is_obvious_non_event('New Horizons', 'No description available.'))

    def test_bare_holiday_observance_is_not_filtered(self):
        # Blocking bare holiday names risks "Indigenous People's Day Celebration".
        self.assertFalse(is_obvious_non_event(
            'Columbus Day / Indigenous People’s Day', 'No description available.'))

    def test_exhibit_installation_is_not_filtered(self):
        # Filtering this shape risks suppressing genuine exhibition openings.
        self.assertFalse(is_obvious_non_event(
            'Art Gallery Exhibit INSTALLATION - Artist: Alex Tric',
            'Art exhibit installation will take place in the Main Art Gallery'))

    def test_nonprofit_service_orgs_are_not_filtered(self):
        # Narrower than the housing-corp rule on purpose: these are service
        # organisations, and a room booking is indistinguishable by name alone
        # from a program they host.
        self.assertFalse(is_obvious_non_event(
            "(FCA) Family & Children's Association", 'No description available.'))
        self.assertFalse(is_obvious_non_event(
            'The Center for Developmental Disabilities, Inc.',
            'Individuals from the Center for Developmental Disabilities, Inc. visit weekly.'))


if __name__ == '__main__':
    unittest.main()
