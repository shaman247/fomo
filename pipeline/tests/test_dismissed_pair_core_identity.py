"""Dismissed-pair veto for listings a posting board retitles on every repeat.

Park Slope Parents (w941) posted the same dads' meetup as "Dads Trivia Night",
"Dads Trivia Night at Sound & Fury" and "Dads Trivia Night 10/21 @ Sound & Fury
@ 6:30pm". The veto's exact listing identity never matched, so whenever no
Dads Trivia row was live each posting fused onto the venue's own Sound + Fury
Trivia Nights (510) despite the 510/253403 dismissed pair (BL13, 2026-10-07).
The core identity (same website, same venue, same words without date/time and
venue words) catches it; a dormant home (archived after its last date) can take
the source back. The merge tests drive merge_crawl_events over a fake cursor,
like test_dismissed_pair_home_20261005.
"""
import io
import sys
import unittest
from contextlib import ExitStack, redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger

CE_ID = 1700001
PSP = 941
VENUE = 1424
VENUE_NAME = 'Sound + Fury Brewery and Kitchen'
POSTING = 'Dads Trivia Night 10/21 @ Sound & Fury @ 6:30pm'
POSTING_URL = 'https://parkslopeparents.clubexpress.com/content.aspx?page_id=4091&item_id=3088729'
OLD_URL = 'https://parkslopeparents.clubexpress.com/content.aspx?page_id=4091&item_id=3043572'
VENUE_SERIES = (510, 'Sound + Fury Trivia Nights')
DADS = (253403, 'Dads Trivia Night')

norm = merger.normalize_name_for_dedup
core = merger._listing_core_words
VENUE_NORM = norm(VENUE_NAME)


def run_merge(*, live, dormant=(), sources=(), dismissed=(), dormant_state=None,
              ce_name=POSTING, ce_venue=VENUE):
    """Merge one PSP crawl_event. `live` events sit in the dedup index with a
    date today; `dormant` ones only exist in the database. `dormant_state`
    maps id -> (suppressed, location_id, is_redirect_duplicate)."""
    today = date.today()
    names = {eid: name for eid, name in list(live) + list(dormant)}
    dormant_state = dormant_state or {eid: (0, VENUE, 0) for eid, _ in dormant}
    cursor = MagicMock(lastrowid=999999)

    def execute(query, params=None):
        rows, one = [], None
        if 'SELECT ce.id, ce.name' in query:
            rows = [(CE_ID, ce_name, None, 'Desc.', '🧠', 'Sound & Fury', None,
                     ce_venue, POSTING_URL, PSP, None, None, 129000)]
        elif 'SELECT DISTINCT e.id, e.name, e.location_id' in query:
            rows = [(eid, name, VENUE, None, None, 'Sound & Fury', None, 0) for eid, name in live]
        elif 'SELECT event_id, start_date, start_time, end_date' in query:
            rows = [(eid, today, '7pm', None) for eid, _ in live]
        elif 'SELECT crawl_result_id, id, name FROM crawl_events' in query:
            rows = [(129000, CE_ID, ce_name)]
        elif 'FROM dedupe_dismissed_pairs' in query:
            rows = list(dismissed)
        elif params and query == merger.DISMISSED_HOME_SOURCES_SQL.format(
                placeholders=','.join(['%s'] * (len(params) - 1))):
            wanted = set(params[1:])
            assert params[0] == PSP
            rows = [s for s in sources if s[0] in wanted]
        elif 'SELECT id, name, emoji, lat, lng FROM locations' in query:
            rows = [(VENUE, VENUE_NAME, '🍺', None, None), (77, 'Elsewhere', '📍', None, None)]
        elif 'FROM crawl_event_occurrences' in query:
            rows = [(CE_ID, today, '6:30pm', None, None, 0)]
        elif 'SELECT e.suppressed, e.location_id' in query:
            one = dormant_state.get(params[0])
        elif 'SELECT name FROM events WHERE id' in query:
            one = (names.get(params[0], ''),)
        elif 'SELECT location_id FROM events WHERE id' in query:
            one = (VENUE,)
        elif 'SELECT location_name, location_id FROM events WHERE id' in query:
            one = ('Sound & Fury', VENUE)
        elif 'SELECT description, emoji, name, short_name, event_type' in query:
            one = ('Existing.', '🧠', names.get(params[0]), None, None)
        cursor.fetchall.return_value = rows
        cursor.fetchone.return_value = one

    cursor.execute.side_effect = execute
    with ExitStack() as stack:
        stack.enter_context(redirect_stdout(io.StringIO()))
        stack.enter_context(patch.object(merger, 'EditLogger', None))
        stack.enter_context(patch.object(merger.reviewed_event_identity, 'load_index', return_value={}))
        stack.enter_context(patch.object(merger.venue_overrides, 'load_rules', return_value=[]))
        stack.enter_context(patch.object(merger, 'get_active_date_window',
                                         return_value=(today, today + timedelta(days=90))))
        database = stack.enter_context(patch.object(merger, 'db'))
        database.build_tag_ancestor_map.return_value = ({}, set())
        database.archive_dead_source_events.return_value = (0, [])
        database.prune_superseded_dates.return_value = (0, [])
        database.archive_sourceless_events.return_value = (0, [])
        for helper in ('_merge_occurrences_into_event', '_merge_grouped_event_urls',
                       'refresh_source_metadata', 'refresh_source_session_details'):
            stack.enter_context(patch.object(merger, helper))
        merger.merge_crawl_events(cursor, MagicMock(), website_ids=[PSP])
    calls = cursor.execute.call_args_list
    links = [c.args[1] for c in calls if 'INSERT IGNORE INTO event_sources' in c.args[0]]
    created = any('INSERT INTO events (' in c.args[0] for c in calls)
    revived = [c.args[1][0] for c in calls
               if c.args[0].startswith('UPDATE events SET archived = FALSE')]
    return links, created, revived


PRIOR_DADS = [(DADS[0], OLD_URL, 'Dads Trivia Night', VENUE),
              (DADS[0], OLD_URL, 'Dads Trivia Night at Sound & Fury', VENUE)]


class DadsTriviaMergeTests(unittest.TestCase):
    def test_retitled_posting_goes_back_to_its_dormant_home(self):
        self.assertTrue(merger.are_names_similar(POSTING, VENUE_SERIES[1]))
        links, created, revived = run_merge(
            live=[VENUE_SERIES], dormant=[DADS], sources=PRIOR_DADS,
            dismissed=[(VENUE_SERIES[0], DADS[0])])
        self.assertEqual(links, [(DADS[0], CE_ID)])
        self.assertFalse(created)
        self.assertEqual(revived, [DADS[0]])

    def test_without_the_dismissal_the_bleed_still_happens(self):
        links, _, _ = run_merge(live=[VENUE_SERIES], dormant=[DADS], sources=PRIOR_DADS)
        self.assertEqual(links, [(VENUE_SERIES[0], CE_ID)])

    def test_live_home_still_takes_it(self):
        links, created, _ = run_merge(live=[VENUE_SERIES, DADS], sources=PRIOR_DADS,
                                      dismissed=[(VENUE_SERIES[0], DADS[0])])
        self.assertEqual(links, [(DADS[0], CE_ID)])
        self.assertFalse(created)

    def test_suppressed_or_redirected_dormant_home_gets_a_new_row_not_the_bleed(self):
        for state in ((1, VENUE, 0), (0, VENUE, 1), (0, 77, 0)):
            with self.subTest(state=state):
                links, created, _ = run_merge(
                    live=[VENUE_SERIES], dormant=[DADS], sources=PRIOR_DADS,
                    dismissed=[(VENUE_SERIES[0], DADS[0])], dormant_state={DADS[0]: state})
                self.assertTrue(created)
                self.assertEqual(links, [(999999, CE_ID)])

    def test_prior_postings_at_another_venue_are_not_this_listing(self):
        other = [(DADS[0], OLD_URL, 'Dads Trivia Night', 77)]
        links, _, _ = run_merge(live=[VENUE_SERIES], dormant=[DADS], sources=other,
                                dismissed=[(VENUE_SERIES[0], DADS[0])])
        self.assertEqual(links, [(VENUE_SERIES[0], CE_ID)])


class CoreIdentityUnitTests(unittest.TestCase):
    def veto(self, group, incoming=POSTING, candidate=VENUE_SERIES, partners=(DADS,),
             location_id=VENUE, venue_norm=VENUE_NORM, url_key=''):
        names = dict([candidate, *partners])
        return merger._dismissed_home_veto(
            candidate[0], {p[0] for p in partners}, group, url_key, norm(incoming),
            location_id, lambda eid: names.get(eid, 'Other'), venue_norm=venue_norm)

    def test_core_words_drop_only_date_time_and_venue_shapes(self):
        dads = {'dads', 'trivia', 'night'}
        for name in (POSTING, 'Dads Trivia Night at Sound & Fury', 'Dads Trivia Night',
                     'Dads Trivia Night Wed Oct 21 at 6:30 PM', 'Dads Trivia Night 10/21/2026 7pm'):
            self.assertEqual(core(norm(name), VENUE_NORM), dads, name)
        self.assertEqual(core(norm('Climate Imaginarium (Day 2)')), {'climate', 'imaginarium', 'day', '2'})
        self.assertEqual(core(norm('Level 2 Improv 10/12')), {'level', '2', 'improv'})

    def test_retitled_posting_is_vetoed_off_the_venue_series(self):
        group = {VENUE_SERIES[0]: [], DADS[0]: [('', norm('Dads Trivia Night'), VENUE)]}
        self.assertEqual(self.veto(group), (DADS[0],))
        # Without the venue name (core fallback off) the exact identity misses it.
        self.assertIsNone(self.veto(group, venue_norm=None))

    def test_candidate_whose_name_covers_the_core_is_never_skipped(self):
        """Common Ground's dismissed 10/30 vs 10/31 parties differ only by date."""
        oct30 = (208792, 'NYC Halloween Common Ground Halloween Party 10/30')
        oct31 = (208796, 'NYC Halloween Common Ground Halloween Party 10/31')
        group = {oct31[0]: [], oct30[0]: [('', norm('Common Ground NYC Halloween Party | Oct 30'), 4024)]}
        self.assertIsNone(self.veto(group, incoming='Common Ground NYC Halloween Party — Oct 31',
                                    candidate=oct31, partners=(oct30,), location_id=4024,
                                    venue_norm=norm('The Common Ground Bar')))

    def test_home_must_carry_the_core_in_its_own_name(self):
        """Five Azure Day Party postings bled onto RIVA 108035: RIVA is no home."""
        azure = (108021, 'Azure Day Party Sundays')
        riva = (108035, 'RIVA Sunset Saturday’s')
        group = {azure[0]: [],
                 riva[0]: [('', norm('Azure Day Party October 3RD | Arlo Williamsburg Rooftop'), 2596)]}
        self.assertIsNone(self.veto(group, incoming='Azure Day Party October 4th | Arlo Williamsburg Rooftop',
                                    candidate=azure, partners=(riva,), location_id=2596,
                                    venue_norm=norm('Arlo Williamsburg')))

    def test_numbered_siblings_stay_distinct(self):
        day1 = (226662, 'OHNY Weekend: Climate Imaginarium (Day 1)')
        day2 = (226663, 'Open House New York Weekend: The Climate Imaginarium (Day 2)')
        group = {day2[0]: [], day1[0]: [('', norm(day1[1]), 4659)]}
        self.assertIsNone(self.veto(group, incoming='OHNY Weekend: Climate Imaginarium (Day 2)',
                                    candidate=day2, partners=(day1,), location_id=4659,
                                    venue_norm=norm('Governors Island')))

    def test_core_needs_the_same_venue_and_two_words(self):
        group = {VENUE_SERIES[0]: [], DADS[0]: [('', norm('Dads Trivia Night'), 77)]}
        self.assertIsNone(self.veto(group))
        group = {VENUE_SERIES[0]: [], DADS[0]: [('', norm('Trivia 10/21'), VENUE)]}
        self.assertIsNone(self.veto(group, incoming='Trivia 10/28'))

    def test_exact_identity_decides_before_the_core(self):
        """An exact hit on the candidate (contested, more evidence) is not
        overridden by a partner's core-only evidence."""
        group = {VENUE_SERIES[0]: [('', norm(POSTING), VENUE)],
                 DADS[0]: [('', norm('Dads Trivia Night'), VENUE)] * 3}
        self.assertIsNone(self.veto(group))


if __name__ == '__main__':
    unittest.main()
