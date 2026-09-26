"""A broad festival span cannot be donated to one explicitly numbered night."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from festival_identity import numbered_festival_span_mismatch as mismatch, numbered_member_pair
from test_merger_suppressed_match import _MatcherHarness, _rebuild

UMBRELLA = 'City Of Gods Halloween Festival 2026'
NIGHT = 'City of Gods Festival: Night 1'
SPAN = [('2026-10-23', '', '2026-10-25', '')]
SLOT = [('2026-10-23', '9pm', None, '5am')]


class FestivalIdentityTests(unittest.TestCase):
    def test_actual_repaired_case_and_reverse_arrival(self):
        self.assertTrue(mismatch(UMBRELLA, SPAN, NIGHT, SLOT))
        self.assertTrue(mismatch(NIGHT, SLOT, UMBRELLA, SPAN))

    def test_second_night_and_explicit_overnight_member(self):
        rows = [('2026-10-24', '9pm', '2026-10-25', '5am')]
        self.assertTrue(mismatch(UMBRELLA, SPAN, NIGHT.replace('1', '2'), rows))

    def test_timed_festival_envelope_also_stays_separate(self):
        rows = [('2026-10-23', '9pm', '2026-10-25', '5am')]
        self.assertTrue(mismatch(UMBRELLA, rows, NIGHT, SLOT))

    def test_numeric_and_word_ordinals_with_explicit_separators(self):
        for label in [': Night 2', ' — Night One', ' - Day 1', ' (Day Three)']:
            self.assertTrue(mismatch(UMBRELLA, SPAN, 'City of Gods Festival' + label, SLOT))

    def test_same_member_names_and_unnumbered_listings_are_unaffected(self):
        self.assertFalse(mismatch(NIGHT, SPAN, NIGHT, SLOT))
        self.assertFalse(mismatch(UMBRELLA, SPAN, UMBRELLA, SLOT))
        self.assertFalse(mismatch(UMBRELLA, SPAN, 'City of Gods Festival: Opening Night', SLOT))

    def test_grouped_and_ambiguous_ordinals_decline(self):
        for name in ['Festival: Night 1 & 2', 'Festival: Nights 1–2',
                     'Festival: Night 1/2', 'Festival: Night 1: Night 2',
                     'Festival: Night I: Night 2', 'Festival: Nights I–II — Night 2',
                     'Festival Night 1', 'Festival: Night 1+']:
            self.assertFalse(numbered_member_pair(UMBRELLA, name), name)

    def test_nonfestival_titles_and_missing_titles_decline(self):
        for name in [None, '', 'City of Gods: Night 1', 'The Night 1 Movie']:
            self.assertFalse(mismatch(UMBRELLA, SPAN, name, SLOT))

    def test_missing_or_short_umbrella_span_declines(self):
        for rows in [[], [('2026-10-23', '', None, '')],
                     [('2026-10-23', '', '2026-10-23', '')],
                     [('2026-10-23', '', '2026-10-24', '')]]:
            self.assertFalse(mismatch(UMBRELLA, rows, NIGHT, SLOT))

    def test_multisession_umbrella_or_member_declines(self):
        extra = [('2026-10-24', '9pm', None, '5am')]
        self.assertFalse(mismatch(UMBRELLA, SPAN, NIGHT, SLOT + extra))
        self.assertFalse(mismatch(UMBRELLA, SPAN + extra, NIGHT, SLOT))

    def test_member_must_be_timed_and_at_most_one_day(self):
        for time in ['', None, '9', 'TBA']:
            self.assertFalse(mismatch(UMBRELLA, SPAN, NIGHT, [('2026-10-23', time, None, '')]))
        self.assertFalse(mismatch(UMBRELLA, SPAN, NIGHT,
                                 [('2026-10-23', '9pm', '2026-10-25', '5am')]))

    def test_disjoint_or_malformed_dates_decline(self):
        for rows in [[('2026-10-22', '9pm', None, '')],
                     [('2026-10-25', '9pm', None, '')],
                     [('2026-10-24', '9pm', '2026-10-26', '')],
                     [('not-a-date', '9pm', None, '')]]:
            self.assertFalse(mismatch(UMBRELLA, SPAN, NIGHT, rows))

    def test_explicit_next_day_member_must_not_exceed_twenty_four_hours(self):
        for end_time in ['10am', '', '5']:
            self.assertFalse(mismatch(UMBRELLA, SPAN, NIGHT,
                [('2026-10-23', '9am', '2026-10-24', end_time)]))
        self.assertTrue(mismatch(UMBRELLA, SPAN, NIGHT,
            [('2026-10-23', '9am', '2026-10-24', '9am')]))

    def test_duplicate_rows_and_equivalent_clock_format_are_not_extra_sessions(self):
        self.assertTrue(mismatch(UMBRELLA, SPAN * 2, NIGHT,
                                 SLOT + [('2026-10-23', '21:00', None, '5:00 AM')]))


class FestivalMatcherTests(unittest.TestCase):
    def harness(self, name, incoming, schedules):
        class Cursor:
            calls = []
            def execute(self, query, params):
                self.event_id = params[0]
                self.calls.append(self.event_id)
            def fetchall(self):
                return schedules[self.event_id]
        cursor = Cursor()
        slots = {eid: {(r[0], r[1] or '') for r in rows} for eid, rows in schedules.items()}
        veto = _rebuild('_sibling_veto', dict(
            name=name, valid_occurrences=incoming, cursor=cursor,
            ce_url_key='shotgun.live/en/festivals/cityofgods2026', website_id=244,
            crawl_event_slots={(r[0], r[1] or '') for r in incoming}, ce_id=1456594,
            event_slots=slots, crawl_result_roster=[], listing_url_keys=set(),
            url_key_name_counts={}, merge_event_url_keys={}))
        harness = _MatcherHarness(name, schedules, location_id=410, slots=slots)
        original = harness._common_freevars
        harness._common_freevars = lambda: dict(original(), _sibling_veto=veto)
        return harness, cursor

    def test_umbrella_chooses_its_hidden_exact_record_over_visible_numbered_nights(self):
        events = [dict(id=220462, name=NIGHT, location_id=410),
                  dict(id=220464, name=NIGHT.replace('1', '2'), location_id=410),
                  dict(id=226017, name=UMBRELLA, location_id=410, suppressed=True)]
        rows = {220462:SLOT, 220464:[('2026-10-24','9pm',None,'5am')], 226017:SPAN}
        # This is the previous live reproduction, before the schedule veto.
        self.assertEqual(_MatcherHarness(UMBRELLA, rows).find_best_match(events), 220462)
        for incoming in [SPAN, [('2026-10-23','9pm','2026-10-25','5am')]]:
            for order in [events, events[::-1]]:
                harness, _ = self.harness(UMBRELLA, incoming, rows)
                self.assertEqual(harness.find_best_match(order), 226017)
                self.assertEqual(harness.safe_website_match(order), 226017)

    def test_numbered_source_cannot_attach_to_only_umbrella_candidate(self):
        harness, _ = self.harness(NIGHT, SLOT, {226017:SPAN})
        candidate = dict(id=226017,name=UMBRELLA,location_id=410,suppressed=True)
        self.assertIsNone(harness.find_best_match([candidate]))
        self.assertIsNone(harness.safe_website_match([candidate]))

    def test_unrelated_visible_partial_preference_is_preserved_without_extra_query(self):
        harness, cursor = self.harness('Ballet Storytime', SLOT, {1:SLOT, 2:SLOT})
        candidates = [dict(id=1,name='Ballet Storytime',suppressed=True),
                      dict(id=2,name='Ballet Storytime with West Jersey Youth Ballet')]
        self.assertEqual(harness.find_best_match(candidates), 2)
        self.assertEqual(cursor.calls, [])


if __name__ == '__main__':
    unittest.main()
