"""BL52: a source fused from several same-titled permalinks must not carry a
dismissed partner's sessions onto the event the name tiers picked.

2026-10-14: ShapeShifter w88 listed six "New York Yoga Club — <date>" cards,
each with its own eventId page; the extraction gave all six the bare title, the
processor grouped them (right for a per-date series), and the fused source
landed on the generic e282191, which took the Oct 14/21/28 dates and pages of
the themed flows e275028/275033/275035 — even though each pair was dismissed.
Syosset w5494 (two book discussions) and QPL w172 (topic sessions) fused the
same way. The merge tests drive `merge_crawl_events` over a fake cursor, as in
test_dismissed_pair_home_20261005.
"""
import io
import json
import sys
import unittest
from contextlib import ExitStack, redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger
import processor

SS = 'https://www.shapeshifterplus.org/eventDetails.html?eventId='
SS_LISTING = 'https://www.shapeshifterplus.org/index.html'
SS_WEB, SS_LOC = 88, 740
CE_ID = 1574826
TODAY = date.today()


def day(n):
    return TODAY + timedelta(days=n)


def yoga_rows(ids_and_days):
    return [{'name': 'New York Yoga Club', 'location': 'ShapeShifter Lab', 'location_id': SS_LOC,
             'start_date': str(day(n)), 'start_time': '6:30pm', 'end_date': '', 'end_time': '8pm',
             'description': 'No description available.', 'url': SS + eid, 'tags': ['Yoga']}
            for eid, n in ids_and_days]


class GroupingRecordsUrlSessionsTests(unittest.TestCase):

    def test_fused_permalinks_keep_a_per_url_date_map(self):
        rows = yoga_rows([('A', 0), ('B', 7), ('C', 14)])
        [event] = processor.group_event_occurrences(rows, SS_LISTING)
        self.assertEqual(len(event['occurrences']), 3)  # grouping itself is unchanged
        self.assertEqual(event['url_sessions'], {
            SS + 'A': [[str(day(0)), '6:30pm', '', '8pm']],
            SS + 'B': [[str(day(7)), '6:30pm', '', '8pm']],
            SS + 'C': [[str(day(14)), '6:30pm', '', '8pm']],
        })

    def test_one_permalink_series_carries_no_map(self):
        rows = yoga_rows([('A', 0), ('A', 7)])
        [event] = processor.group_event_occurrences(rows, SS_LISTING)
        self.assertNotIn('url_sessions', event)


class SessionRoutingUnitTests(unittest.TestCase):

    def sessions(self, raw, listing=()):
        return merger.source_url_sessions(raw, lambda key: key in listing)

    def test_reads_url_sessions_then_session_details(self):
        raw = {'url_sessions': {SS + 'A': [['2026-10-14', '6:30pm', '', '8pm']],
                                SS + 'B': [['2026-10-21', '6:30pm', '', '8pm']]}}
        a, b = (merger.normalize_url_for_identity(SS + x) for x in 'AB')
        self.assertEqual(self.sessions(json.dumps(raw)), {a: {'2026-10-14'}, b: {'2026-10-21'}})
        legacy = {'session_details': [
            {'description': 'x', 'sessions': [{'start_date': '2026-10-27', 'url': SS + 'A'}]},
            {'description': 'y', 'sessions': [{'start_date': '2026-11-24', 'url': SS + 'B'}]}]}
        self.assertEqual(self.sessions(legacy), {a: {'2026-10-27'}, b: {'2026-11-24'}})

    def test_listing_pages_and_single_permalinks_carry_nothing(self):
        raw = {'url_sessions': {SS + 'A': [['2026-10-14']], SS_LISTING: [['2026-10-21']]}}
        listing = {merger.normalize_url_for_identity(SS_LISTING)}
        self.assertEqual(self.sessions(raw, listing), {})
        self.assertEqual(self.sessions({'urls': [SS + 'A']}), {})
        self.assertEqual(self.sessions('not json'), {})

    def test_routes_only_pages_a_partner_owns_and_the_target_does_not(self):
        url_dates = {'a': {'d1'}, 'b': {'d2'}, 'n': {'d3'}, 't': {'d4'}}
        owners = {'a': {2}, 'b': {3}, 't': {1, 2}}
        self.assertEqual(merger.route_dismissed_sessions(1, url_dates, owners, {}),
                         {'d1': 2, 'd2': 3})

    def test_a_page_held_by_two_partners_splits_by_their_own_dates(self):
        # QPL 005214 lists two topic sessions; 284599 has Oct 22, 284600 Oct 29.
        url_dates = {'p12': {'oct15'}, 'p14': {'oct22', 'oct29', 'nov5'}}
        owners = {'p12': {1}, 'p14': {2, 3}}
        routed = merger.route_dismissed_sessions(
            1, url_dates, owners, {2: {'oct22'}, 3: {'oct29'}})
        self.assertEqual(routed, {'oct22': 2, 'oct29': 3})  # nov5 is ambiguous: stays

    def test_a_date_two_pages_disagree_on_stays(self):
        self.assertEqual(merger.route_dismissed_sessions(
            1, {'a': {'d'}, 'b': {'d'}}, {'a': {2}, 'b': {3}}, {}), {})


def run_merge(*, events, ce_occurrences, raw, dismissed=(), event_urls=(), suppressed=()):
    """Merge the fused ShapeShifter source against `events` = [(id, name, [day offsets])].

    `event_urls` = [(event_id, url)]. Returns (links, merges, url_merges) where
    merges = {event_id: [start dates]} passed to _merge_occurrences_into_event.
    """
    names = {eid: name for eid, name, _ in events}
    cursor = MagicMock(lastrowid=999999)

    def execute(query, params=None):
        rows, one = [], None
        if 'SELECT ce.id, ce.name' in query:
            rows = [(CE_ID, 'New York Yoga Club', None, 'No description available.', '🧘',
                     'ShapeShifter Lab', None, SS_LOC, SS + 'A', SS_WEB, None, None, 132008)]
        elif 'SELECT DISTINCT e.id, e.name, e.location_id' in query:
            rows = [(eid, name, SS_LOC, None, None, 'ShapeShifter Lab', SS_WEB, 0)
                    for eid, name, _ in events]
        elif 'SELECT event_id, start_date, start_time, end_date' in query:
            rows = [(eid, day(n), '6:30pm', None) for eid, _, days in events for n in days]
        elif 'SELECT crawl_result_id, id, name FROM crawl_events' in query:
            rows = [(132008, CE_ID, 'New York Yoga Club')]
        elif 'SELECT id, raw_data FROM crawl_events' in query:
            rows = [(CE_ID, json.dumps(raw))]
        elif 'FROM dedupe_dismissed_pairs' in query:
            rows = list(dismissed)
        elif query.startswith('SELECT website_id, url FROM website_urls'):
            rows = [(SS_WEB, SS_LISTING)]
        elif params and query == merger.DISMISSED_SESSION_OWNERS_SQL.format(
                placeholders=','.join(['%s'] * len(params))):
            rows = [(eid, u) for eid, u in event_urls
                    if eid in params and eid not in suppressed]
        elif params and query == merger.DISMISSED_SESSION_DATES_SQL.format(
                placeholders=','.join(['%s'] * len(params))):
            rows = [(eid, day(n)) for eid, _, days in events if eid in params for n in days]
        elif 'SELECT id, name, emoji, lat, lng FROM locations' in query:
            rows = [(SS_LOC, 'ShapeShifter Lab', '📍', None, None)]
        elif 'FROM crawl_event_occurrences' in query:
            rows = [(CE_ID, day(n), '6:30pm', None, '8pm', i) for i, n in enumerate(ce_occurrences)]
        elif 'SELECT name FROM events WHERE id' in query:
            one = (names.get(params[0], ''),)
        elif 'SELECT location_id FROM events WHERE id' in query:
            one = (SS_LOC,)
        elif 'SELECT location_name, location_id FROM events WHERE id' in query:
            one = ('ShapeShifter Lab', SS_LOC)
        elif 'SELECT description, emoji, name, short_name, event_type' in query:
            one = ('Existing.', '🧘', names.get(params[0]), None, None)
        cursor.fetchall.return_value = rows
        cursor.fetchone.return_value = one

    cursor.execute.side_effect = execute
    with ExitStack() as stack:
        stack.enter_context(redirect_stdout(io.StringIO()))
        stack.enter_context(patch.object(merger, 'EditLogger', None))
        stack.enter_context(patch.object(merger.reviewed_event_identity, 'load_index', return_value={}))
        stack.enter_context(patch.object(merger.venue_overrides, 'load_rules', return_value=[]))
        stack.enter_context(patch.object(merger, 'get_active_date_window',
                                         return_value=(TODAY, TODAY + timedelta(days=90))))
        database = stack.enter_context(patch.object(merger, 'db'))
        database.build_tag_ancestor_map.return_value = ({}, set())
        database.archive_dead_source_events.return_value = (0, [])
        database.prune_superseded_dates.return_value = (0, [])
        database.archive_sourceless_events.return_value = (0, [])
        occ_merge = stack.enter_context(patch.object(
            merger, '_merge_occurrences_into_event', return_value=None))
        url_merge = stack.enter_context(patch.object(merger, '_merge_grouped_event_urls'))
        stack.enter_context(patch.object(merger, 'compute_voted_tags', return_value=[]))
        for helper in ('refresh_source_metadata', 'refresh_source_session_details'):
            stack.enter_context(patch.object(merger, helper))
        merger.merge_crawl_events(cursor, MagicMock(), website_ids=[SS_WEB])
    calls = cursor.execute.call_args_list
    links = [c.args[1] for c in calls if 'INSERT IGNORE INTO event_sources' in c.args[0]]
    merges = {c.args[1]: sorted(str(o[0]) for o in c.args[2]) for c in occ_merge.call_args_list}
    url_inserts = [c.args[1] for c in calls if c.args[0].startswith('INSERT INTO event_urls')]
    grouped = {c.args[1]: merger._grouped_event_urls(c.args[2]) for c in url_merge.call_args_list}
    return links, merges, url_inserts, grouped


GENERIC = (282191, 'New York Yoga Club', [21, 28, 35])
ITALO = (275028, 'Italo Disco Flow(Park Slope)', [0])
ZIMMER = (275033, 'Hans Zimmer Power Flow (Park Slope)', [7])
DOOM = (275035, 'Doom Yoga - Halloween Edition (Park Slope)', [14])
PAGES = {'A': 0, 'B': 7, 'C': 14, 'D': 21, 'E': 28, 'F': 35}
RAW = {'urls': [SS + p for p in PAGES] + [SS_LISTING],
       'url_sessions': {SS + p: [[str(day(n)), '6:30pm', '', '8pm']] for p, n in PAGES.items()}}
OWNED = [(275028, SS + 'A'), (275033, SS + 'B'), (275035, SS + 'C'),
         (282191, SS + 'D'), (282191, SS + 'E'), (282191, SS + 'F')]
DISMISSED = [(275028, 282191), (275033, 282191), (275035, 282191)]


class FusedSourceMergeTests(unittest.TestCase):

    def merge(self, **kw):
        args = dict(events=[GENERIC, ITALO, ZIMMER, DOOM], ce_occurrences=list(PAGES.values()),
                    raw=RAW, dismissed=DISMISSED, event_urls=OWNED)
        args.update(kw)
        return run_merge(**args)

    def test_themed_sessions_go_to_their_dismissed_rows(self):
        links, merges, url_inserts, grouped = self.merge()
        self.assertEqual(sorted(links), sorted([(282191, CE_ID), (275028, CE_ID),
                                                (275033, CE_ID), (275035, CE_ID)]))
        self.assertEqual(merges[282191], [str(day(n)) for n in (21, 28, 35)])
        self.assertEqual(merges[275028], [str(day(0))])
        self.assertEqual(merges[275033], [str(day(7))])
        self.assertEqual(merges[275035], [str(day(14))])
        # The source's own permalink (A) is Italo's page: the generic row must
        # not gain it, nor B/C through the grouped links.
        self.assertNotIn((282191, SS + 'A'), [tuple(u[:2]) for u in url_inserts])
        self.assertEqual(grouped[282191], [SS + p for p in 'DEF'] + [SS_LISTING])

    def test_without_dismissals_the_series_still_fuses(self):
        links, merges, _, grouped = self.merge(dismissed=[])
        self.assertEqual(links, [(282191, CE_ID)])
        self.assertEqual(len(merges[282191]), 6)
        self.assertEqual(len(grouped[282191]), 7)

    def test_a_suppressed_partner_does_not_take_sessions(self):
        links, merges, _, _ = self.merge(suppressed={275028})
        self.assertNotIn((275028, CE_ID), links)
        self.assertIn(str(day(0)), merges[282191])

    def test_new_permalinks_stay_with_the_series(self):
        # Nobody owns A-C yet (first sighting): ordinary series behaviour.
        links, merges, _, _ = self.merge(event_urls=OWNED[3:])
        self.assertEqual(links, [(282191, CE_ID)])
        self.assertEqual(len(merges[282191]), 6)

    def test_when_every_session_belongs_elsewhere_the_owner_of_its_page_takes_it(self):
        pages = {'A': 0, 'B': 7}
        raw = {'urls': [SS + p for p in pages],
               'url_sessions': {SS + p: [[str(day(n)), '6:30pm', '', '8pm']]
                                for p, n in pages.items()}}
        generic = (282191, 'New York Yoga Club', [0, 7])
        links, merges, _, grouped = self.merge(
            events=[generic, ITALO, ZIMMER], ce_occurrences=[0, 7], raw=raw,
            dismissed=DISMISSED[:2], event_urls=OWNED[:2])
        self.assertEqual(sorted(links), [(275028, CE_ID), (275033, CE_ID)])
        self.assertNotIn(282191, merges)
        self.assertEqual(merges[275028], [str(day(0))])
        self.assertEqual(merges[275033], [str(day(7))])
        self.assertEqual(grouped[275028], [SS + 'A'])  # B is Zimmer's page


if __name__ == '__main__':
    unittest.main()
