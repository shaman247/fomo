"""Tests for the library "NO <Program>" cancellation rule, the room-setup
blank-description form, and the widened org-booking affiliation tail.

Added 2026-08-23. The event-type classification pass produced 4 UNKNOWN rows —
junk that reached the map and was only caught downstream when the classifier
could not assign a type. Three of them are covered here; the fourth
("Agentics: TBD", a literal "under construction" placeholder) was left alone.

Every rule below was precision-audited over the full 199,302-event corpus before
being shipped, exactly as `test_junk_filter_hours_notices.py` describes. The
counts quoted in each docstring are that audit, frozen. **Do not loosen any of
these without re-running the corpus audit** — the bare `^NO ` form in particular
matched 12 rows of which 9 were real events, and only the description gate makes
it shippable.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import (  # noqa: E402
    is_obvious_non_event,
    _description_is_blank,
    _is_room_setup_only,
    _is_no_prefix_cancellation,
)


class TestNoPrefixCancellation(unittest.TestCase):
    """LibNet/LibCal branches announce a skipped session by prefixing the
    program's own title with a capitalised "NO". The pre-existing
    "No <thing> Today" rule cannot reach these — it requires a temporal marker
    and this convention carries none.

    Corpus audit: 2 matches (230422, 230474), 0 false positives.
    """

    def test_drops_the_two_corpus_notices(self):
        self.assertTrue(is_obvious_non_event('NO Senior Movie', 'Theatre Style, 40 chairs.'))
        self.assertTrue(is_obvious_non_event('NO Music & Movement', 'No description available.'))

    def test_described_no_titles_are_real_events(self):
        """The description gate is the whole reason this rule is safe.

        All four are live corpus rows a bare `^NO ` prefix would have taken.
        """
        for name, desc in (
            # A 1985 Philip Hartman film — 5 rows in the corpus.
            ('NO PICNIC Introduced by filmmaker Philip Hartman',
             'NO PICNIC is a 1985 film written and directed by Philip Hartman.'),
            # A Spanish-language warehouse party — 3 rows.
            ('NO TE ENAMORES FEST 3 - Corridos v Reggaeton Brooklyn Warehouse Party, 18+',
             'Dark vibes, heavy bass, corridos & reggaeton all night.'),
            ('NO CLASS WED, MAR 4 | Vajra Yoga with John Campbell',
             'This ongoing class series features yoga instruction rooted in Indo-Tibetan traditions.'),
            ('NO Saturday Morning Program This Week',
             'There is no Saturday Morning Program on April 18 due to the Closing Ceremony.'),
        ):
            # Either kept outright, or (the last one) dropped by the PRE-EXISTING
            # temporal rule — never by the new prefix rule.
            self.assertFalse(_is_no_prefix_cancellation(name, desc), name)

    def test_lowercase_no_is_not_the_convention(self):
        for name in ('No Strings Attached Puppet Show', 'No Pants Subway Ride'):
            self.assertFalse(_is_no_prefix_cancellation(name, ''), name)

    def test_all_caps_title_carries_no_signal(self):
        """A shouted title makes the leading "NO" styling, not a marker."""
        self.assertFalse(_is_no_prefix_cancellation('NO PICNIC SCREENING', ''))

    def test_nocturne_is_not_a_no_prefix(self):
        # "NO" must be a whole word; a word merely starting with those letters
        # must not match.
        self.assertFalse(_is_no_prefix_cancellation('Nocturne Concert', ''))


class TestRoomSetupDescriptionIsBlank(unittest.TestCase):
    """A booking system that exports the room's furniture layout into the
    description ("Theatre Style, 40 chairs.") has said nothing about the
    programming. Treated as BLANK, not as junk on its own.

    Corpus audit: 2 descriptions match, both the "Theatre Style, 40 chairs."
    shape, 0 false positives.
    """

    def test_setup_only_descriptions_count_as_blank(self):
        for desc in (
            'Theatre Style, 40 chairs.',
            'Classroom Style, 20 tables',
            'Boardroom setup',
            'U-Shape, 12 chairs, 6 tables.',
            'No setup',
        ):
            self.assertTrue(_is_room_setup_only(desc), desc)
            self.assertTrue(_description_is_blank(desc), desc)

    def test_a_real_description_that_opens_with_seating_survives(self):
        """This is the case the length cap and leftover check exist for."""
        desc = ('Theatre style seating. Tonight the quartet plays Brahms, '
                'with a discussion to follow in the community room.')
        self.assertFalse(_is_room_setup_only(desc))
        self.assertFalse(_description_is_blank(desc))
        self.assertFalse(is_obvious_non_event('Movie Night', desc))

    def test_setup_description_alone_does_not_condemn_a_real_program(self):
        """e214155 "Senior Movie" carries this exact body and is a real
        library screening. Only a name that ALSO carries a junk signal drops."""
        self.assertFalse(is_obvious_non_event('Senior Movie', 'Theatre Style, 40 chairs.'))

    def test_non_latin_descriptions_are_not_mistaken_for_empty(self):
        """The leftover test must be script-agnostic — an early draft using
        `[A-Za-z]` called every CJK/Bengali/Cyrillic description blank."""
        for desc in (
            '听故事、唱歌，一起动手做趣味小劳作！',
            'শিশুদের এবং তাদের অভিভাবকদের জন্য বাংলা গল্প ও গানের জন্য আমাদের সাথে যোগ দিন.',
            'Общество писателей Восточной Европы',
        ):
            self.assertFalse(_is_room_setup_only(desc), desc)
            self.assertFalse(_description_is_blank(desc), desc)


class TestOrgBookingAffiliationTail(unittest.TestCase):
    """The org-room-booking rule's tail stopped at an optional "meeting", so a
    national or council-level affiliation slipped it.

    Corpus audit of the widening: 3 newly dropped (214080, 216487, 230446), all
    genuine bare bookings, 0 false positives.
    """

    def test_affiliation_tail_is_still_a_bare_booking(self):
        for name in (
            'Girl Scouts of America',
            'Girl Scouts of Northern New Jersey',
        ):
            self.assertTrue(is_obvious_non_event(name, 'No description available.'), name)

    def test_setup_only_body_also_counts_as_bare(self):
        self.assertTrue(is_obvious_non_event('Girl Scouts of America',
                                             'Theatre Style, 40 chairs.'))

    def test_a_described_affiliation_row_is_a_real_program(self):
        """e98162 writes up its meetings and must survive."""
        self.assertFalse(is_obvious_non_event(
            'Girl Scouts of NJ',
            'The Girl Scouts of NJ host meetings at the Bergenfield Public Library monthly.'))

    def test_presenting_veto_still_applies_through_the_tail(self):
        self.assertFalse(is_obvious_non_event('Lecture: Bergen County Historical Society', ''))


if __name__ == '__main__':
    unittest.main()
