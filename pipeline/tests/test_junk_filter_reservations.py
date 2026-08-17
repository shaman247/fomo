"""Tests for the room-reservation rule added to is_obvious_non_event.

Public library calendars (LibCal / EventKeeper) expose patron room bookings
alongside real programming. Two reached `events` — e210295 "Patron Reservation -
Furbacher." and e169812 "Patron Reservation - Calvin Cello Quartet Rehearsal" —
and were only caught downstream when the event-type classifier labelled them
UNKNOWN on 2026-08-05.

Precision audit over all 179,767 events: exactly 2 matches, both genuine junk,
0 currently live. That is why this one is safe to automate while its two
siblings from the same batch (ticket giveaways, standing food/drink features)
were rejected and routed to scripts/find_review_candidates.py instead — see the
rejection note in `processor.is_obvious_non_event`.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import is_obvious_non_event


class TestRoomReservationPlaceholders(unittest.TestCase):
    def test_patron_reservation_with_no_description(self):
        self.assertTrue(is_obvious_non_event(
            'Patron Reservation - Furbacher.', 'No description available.'))

    def test_patron_reservation_naming_an_activity_is_still_a_booking(self):
        """The room's purpose in the title doesn't make it public programming."""
        self.assertTrue(is_obvious_non_event(
            'Patron Reservation - Calvin Cello Quartet Rehearsal',
            'No description available.'))

    def test_other_reservation_prefixes(self):
        for name in ('Room Reservation - Community Group',
                     'Study Room Reservation',
                     'Meeting Room Reservation - Book Club',
                     'Space Reservation - Tenants Association'):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, ''))

    def test_a_described_reservation_event_survives(self):
        """A real programme that merely mentions reservation is not junk."""
        self.assertFalse(is_obvious_non_event(
            'Room Reservation Workshop',
            'Learn how to book meeting rooms at the branch. Staff will walk '
            'attendees through the online system; bring your library card.'))

    def test_unrelated_names_are_untouched(self):
        for name in ('Reservations Recommended: Chef Tasting',
                     'Preservation Society Lecture',
                     'Patron Appreciation Night'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, ''))


class TestRejectedSiblingsStayUnfiltered(unittest.TestCase):
    """The two shapes deliberately NOT automated must still pass through.

    Both were prototyped as automatic rules and rejected on measured precision;
    they live in find_review_candidates.py (human review) instead. These tests
    pin that decision so a future change has to confront it.
    """

    def test_ticket_giveaway_is_not_auto_suppressed(self):
        # e191251 — a real, attendable in-person distribution event.
        self.assertFalse(is_obvious_non_event(
            'Free Shakespeare in the Park Ticket Giveaway: The Winter’s Tale',
            'Snug Harbor is partnering with The Public Theater for an in-person '
            'borough ticket distribution.'))

    def test_multi_course_meal_inside_a_real_event_is_not_auto_suppressed(self):
        # e21790 "Speakeasy, Die Softly" — a three-course meal is a COMPONENT.
        self.assertFalse(is_obvious_non_event(
            'Speakeasy, Die Softly',
            'A comedic immersive murder mystery experience that features a '
            'three-course dinner.'))
        self.assertFalse(is_obvious_non_event(
            'Soul Supper - Live Motown & Soul Dining Experience',
            'Enjoy a unique dining experience paired with live performances of '
            'legendary Motown hits.'))


if __name__ == '__main__':
    unittest.main()
