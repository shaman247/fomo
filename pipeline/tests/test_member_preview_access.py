"""Member access needs corroboration; public membership benefits remain public."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from processor import is_obvious_non_event


class MemberPreviewAccessTests(unittest.TestCase):
    def test_member_program_before_public_admission(self):
        for title, description in (
            ('Member Mornings', 'Museum members of all levels are invited to '
             'explore the museum before the general public. No reservations are required.'),
            ('Member Preview Days', 'Exclusive days for museum members to view '
             'exhibitions before the general public.'),
        ):
            with self.subTest(title=title):
                self.assertTrue(is_obvious_non_event(title, description))

    def test_public_event_with_member_benefits_survives(self):
        self.assertFalse(is_obvious_non_event(
            'First Friday', 'Free admission for everyone. Members may explore '
            'the museum before the general public.'))

    def test_member_title_without_access_evidence_survives(self):
        for description in ('No description available.', 'Members receive free coffee.',
                            'Members perform before the general public.',
                            'An exclusive evening of art and conversation.'):
            with self.subTest(description=description):
                self.assertFalse(is_obvious_non_event('Member Appreciation Night', description))

    def test_public_and_nonmember_admission_vetoes(self):
        for public in ('Open to the public from noon.', 'Non-members are welcome.',
                       'Public welcome!', 'Open to public visitors.'):
            with self.subTest(public=public):
                self.assertFalse(is_obvious_non_event(
                    'Member Preview Days', 'Members view exhibitions before the general public. ' + public))

    def test_member_and_access_signals_do_not_cross_sentences(self):
        self.assertFalse(is_obvious_non_event(
            'Member Film Club', 'Members receive a discount. Curators explore '
            'the museum before the general public.'))

    def test_private_opening_and_closing_parties(self):
        for name in ('Private Opening Party: Fall Exhibitions',
                     'Private Closing Party: Spring Exhibitions'):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, 'Members and invited guests.'))

    def test_public_portion_of_private_party_survives(self):
        self.assertFalse(is_obvious_non_event(
            'Private Opening Party from 7–9pm; open to the public at 9:30pm',
            'Music continues after the opening reception.'))

    def test_public_opening_and_private_view_survive(self):
        self.assertFalse(is_obvious_non_event('Opening Party: Fall Exhibitions', 'Everyone welcome.'))
        self.assertFalse(is_obvious_non_event('Private View: New Paintings', 'Book a viewing appointment.'))


if __name__ == '__main__':
    unittest.main()
