"""Junk filter: one-on-one help desks and card-member-only meals (BL26, 2026-10-12).

Rows are real events from the 2026-10-09 hide-uninteresting pass and the
corpus measurement (see the regex blocks in processor.py). Homework Help is
deliberately review-only (find_review_candidates #40): reviewers kept 13 of 30.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import processor


def rule(name, description):
    return processor.which_junk_rule(name, description)


class ServiceDeskTests(unittest.TestCase):

    def test_tech_help_desks_are_dropped(self):
        self.assertEqual(rule(
            'Tech Time (Point Lookout)',
            'Are you stumped by a tech issue? Do you need someone to walk you through how to '
            'use a new phone or laptop? Never fear, Long Beach Public Library is offering '
            'one-on-one tech help monthly at our Point Lookout Branch.'), 'one_on_one_service_desk')
        self.assertEqual(rule(
            'Tech Tuesdays - Dix Hills',
            'Need cell phone help? Want assistance with your tablet or laptop? Tech Tuesday '
            'offers one on one assistance with your device.'), 'one_on_one_service_desk')
        self.assertEqual(rule(
            'One-On-One Medicare Counseling', 'A volunteer from HIICAP will answer your '
            'questions about Medicare in a one-on-one appointment.'), 'one_on_one_service_desk')

    def test_name_alone_or_body_alone_is_not_enough(self):
        self.assertIsNone(rule('Tech Help', 'Bring your questions about email and apps.'))
        self.assertIsNone(rule('Teen Tech Time', 'Enjoy gaming and tech exploration!'))
        self.assertIsNone(rule('Portfolio Review Night', 'One-on-one feedback from art directors.'))

    def test_vetoes(self):
        # A volunteer shift, a class and a disclaimed tutoring room are not desks.
        self.assertIsNone(rule(
            'Provide Tech Support for Food Access Programming',
            'Support pantry guests with technical help on their devices, one-on-one.'))
        self.assertIsNone(rule(
            'Computer Class: Tech Help for Beginners',
            'A small class with one-on-one attention from the instructor.'))
        self.assertIsNone(rule(
            'Tech Help Drop-In', 'Group troubleshooting; not one-on-one tutoring.'))

    def test_homework_help_is_left_for_review(self):
        self.assertIsNone(rule(
            'QPL Homework Help: South Hollis',
            'Drop-in homework help for students in grades 1-5 with personalized assistance '
            'from staff and volunteers. No enrollment required.'))


class CardMemberExclusiveTests(unittest.TestCase):

    def test_tier_member_meals_are_dropped(self):
        self.assertEqual(rule(
            'NYCWFF: Dinner Hosted By Flynn McGarry',
            'Chef Flynn McGarry of the restaurant Cove makes his NYCWFF debut with a '
            'multi-course dinner. The dinner is reserved exclusively for Bank of America '
            'Rewards Premier tier members.'), 'card_member_exclusive')
        self.assertEqual(rule(
            'NYCWFF: Fried Chicken & Champagne Brunch Hosted By COQODAQ',
            'An exclusive brunch for BofA Rewards Premier tier members at COQODAQ with a '
            'special festival menu.'), 'card_member_exclusive')

    def test_library_card_rules_and_craft_cardholders_survive(self):
        self.assertIsNone(rule('Paint By Numbers',
                               'Teens in Grades 6-12 NENPL cardholders only. Enjoy a project.'))
        self.assertIsNone(rule('Sew Amazing', 'Learn the basics of using a sewing machine. '
                                              'Repurpose fabrics to create cardholders.'))

    def test_card_term_and_exclusivity_must_share_a_sentence(self):
        self.assertIsNone(rule(
            'Harvest Dinner', 'Open to everyone, only $40. Bank of America cardholders '
            'get a welcome cocktail.'))


if __name__ == '__main__':
    unittest.main()
