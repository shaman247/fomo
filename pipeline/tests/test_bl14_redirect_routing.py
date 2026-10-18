"""BL14 source routing: a source matched to a REDIRECTED suppressed duplicate
follows `event_merge_redirects` to the visible survivor.

Before 2026-10-16 the redirect map was read only by the suppressed URL-twin
handoff, which needs both rows to hold the source's own event URL. A renamed
survivor without that URL (NYPL w3 "Craft Circle: Knitting and Crocheting"
270151 -> "Knit, Purl, or Crochet Blankets of Love" 194082) kept losing every
fresh listing to the hidden duplicate: 122 sources on 74 redirected duplicates
in the 10 days to 2026-10-16.

The merge tests drive the whole `merge_crawl_events` path over a fake cursor
(the `test_suppressed_url_twin` pattern).
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

DUP, SURVIVOR = 270151, 194082
DUP_NAME = 'Craft Circle: Knitting and Crocheting'
SURVIVOR_NAME = 'Knit, Purl, or Crochet Blankets of Love'
VENUE = 400
CE = 1533823


class RedirectRoutingMergeTests(unittest.TestCase):

    def run_merge(self, *, redirects=((DUP, SURVIVOR),), dismissed=(), reviewed_owners=(),
                  reviewed_match=None, survivor_venue=VENUE, survivor_state=None,
                  survivor_days=0, extra_events=(), url='https://www.nypl.org/events/calendar'):
        today = date.today()
        states = {SURVIVOR: (0, 0, survivor_venue, SURVIVOR_NAME)}
        states.update(survivor_state or {})
        venues = {DUP: VENUE, SURVIVOR: survivor_venue}
        for eid, name, venue, suppressed in extra_events:
            venues[eid] = venue
            states.setdefault(eid, (suppressed, 0, venue, name))
        names = {DUP: DUP_NAME, SURVIVOR: SURVIVOR_NAME}
        names.update({eid: name for eid, name, _v, _s in extra_events})
        cursor = MagicMock(lastrowid=999999)

        def execute(query, params=None):
            rows, one = [], None
            if 'SELECT ce.id, ce.name' in query:
                rows = [(CE, DUP_NAME, None, 'Knitting.', '🧶', 'Library', None,
                         VENUE, url, 3, None, None, 128000)]
            elif 'SELECT DISTINCT e.id, e.name, e.location_id' in query:
                rows = [(DUP, DUP_NAME, VENUE, None, None, 'Library', 3, 1)]
                if survivor_days is not None:
                    rows.append((SURVIVOR, SURVIVOR_NAME, survivor_venue, None, None,
                                 'Library', 3, states[SURVIVOR][0]))
                rows += [(eid, name, venue, None, None, 'Library', 3, suppressed)
                         for eid, name, venue, suppressed in extra_events]
            elif 'SELECT event_id, start_date, start_time, end_date' in query:
                rows = [(DUP, today, '2pm', None)]
                if survivor_days is not None:
                    rows.append((SURVIVOR, today + timedelta(days=survivor_days), '2pm', None))
                rows += [(eid, today, '2pm', None) for eid, *_ in extra_events]
            elif 'SELECT crawl_result_id, id, name FROM crawl_events' in query:
                rows = [(128000, CE, DUP_NAME)]
            elif 'FROM dedupe_dismissed_pairs' in query:
                rows = list(dismissed)
            elif 'FROM event_merge_redirects' in query:
                # (duplicate_id, survivor_id[, source_identities JSON])
                rows = [tuple(r) + (None,) * (3 - len(r)) for r in redirects]
            elif 'SELECT DISTINCT event_id FROM event_source_identities' in query:
                rows = [(eid,) for eid in reviewed_owners]
            elif 'SELECT id, name, emoji, lat, lng FROM locations' in query:
                rows = [(v, f'Venue {v}', '📍', None, None) for v in set(venues.values())]
            elif 'FROM crawl_event_occurrences' in query:
                rows = [(CE, today, '2pm', None, '4pm', 0)]
            elif 'SELECT suppressed, archived, location_id, name FROM events WHERE id' in query:
                one = states.get(params[0])
            elif 'SELECT location_id FROM events WHERE id' in query:
                one = (venues.get(params[0]),)
            elif 'SELECT location_name, location_id FROM events WHERE id' in query:
                one = ('Library', venues.get(params[0]))
            elif 'SELECT name FROM events WHERE id' in query:
                one = (names.get(params[0], ''),)
            elif 'SELECT description, emoji, name, short_name, event_type' in query:
                one = ('Existing.', '🧶', names.get(params[0], ''), None, None)
            cursor.fetchall.return_value = rows
            cursor.fetchone.return_value = one

        cursor.execute.side_effect = execute
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(patch.object(merger, 'EditLogger', None))
            stack.enter_context(patch.object(merger.reviewed_event_identity, 'load_index',
                                             return_value={}))
            if reviewed_match is not None:
                stack.enter_context(patch.object(merger.reviewed_event_identity, 'match',
                                                 return_value=reviewed_match))
            stack.enter_context(patch.object(merger.venue_overrides, 'load_rules', return_value=[]))
            stack.enter_context(patch.object(merger, 'get_active_date_window',
                                             return_value=(today, today + timedelta(days=90))))
            stack.enter_context(patch.object(merger, '_empty_latest_archival_websites',
                                             return_value={}))
            database = stack.enter_context(patch.object(merger, 'db'))
            database.build_tag_ancestor_map.return_value = ({}, set())
            database.archive_dead_source_events.return_value = (0, [])
            database.prune_superseded_dates.return_value = (0, [])
            database.archive_sourceless_events.return_value = (0, [])
            database.archive_outdated_events.return_value = (0, [])
            for helper in ('_merge_occurrences_into_event', '_merge_grouped_event_urls',
                           'refresh_source_metadata', 'refresh_source_session_details'):
                stack.enter_context(patch.object(merger, helper))
            result = merger.merge_crawl_events(cursor, MagicMock(), website_ids=[3])
        calls = cursor.execute.call_args_list
        links = [c.args[1] for c in calls if 'INSERT IGNORE INTO event_sources' in c.args[0]]
        relocations = [c.args[1] for c in calls
                       if c.args[0].startswith('UPDATE events SET location_id')]
        unarchived = [c.args[1] for c in calls
                      if c.args[0].startswith('UPDATE events SET archived = FALSE')]
        self.assertEqual(result, (0, 1))
        return links, relocations, unarchived

    def assertStaysOnDuplicate(self, **kwargs):
        links, _, _ = self.run_merge(**kwargs)
        self.assertEqual(links, [(DUP, CE)])

    # ── The live shape ──
    def test_renamed_survivor_without_the_url_takes_the_source(self):
        self.assertFalse(merger.are_names_similar(DUP_NAME, SURVIVOR_NAME))
        links, relocations, _ = self.run_merge()
        self.assertEqual(links, [(SURVIVOR, CE)])
        self.assertEqual(relocations, [])

    def test_without_a_redirect_plain_suppression_still_absorbs(self):
        """Editorial suppression without a duplicate decision is unchanged (2026-09-11)."""
        self.assertStaysOnDuplicate(redirects=())

    def test_chain_is_followed_to_its_live_end(self):
        links, _, _ = self.run_merge(
            redirects=((DUP, 5001), (5001, SURVIVOR)),
            extra_events=((5001, 'Craft Circle', VENUE, 1),),
            survivor_state={5001: (1, 0, VENUE, 'Craft Circle')})
        self.assertEqual(links, [(SURVIVOR, CE)])

    def test_survivor_outside_the_window_is_reached_when_visible(self):
        links, _, _ = self.run_merge(survivor_days=None)
        self.assertEqual(links, [(SURVIVOR, CE)])

    def test_starved_archived_survivor_with_overlapping_dates_is_revived(self):
        links, _, unarchived = self.run_merge(
            survivor_state={SURVIVOR: (0, 1, VENUE, SURVIVOR_NAME)})
        self.assertEqual(links, [(SURVIVOR, CE)])
        self.assertIn((SURVIVOR,), unarchived)

    # ── Explicit decisions and missing evidence keep the duplicate ──
    def test_dismissed_pair_is_binding(self):
        self.assertStaysOnDuplicate(dismissed=[(SURVIVOR, DUP)])

    def test_dismissed_link_inside_a_chain_is_binding(self):
        self.assertStaysOnDuplicate(
            redirects=((DUP, 5001), (5001, SURVIVOR)), dismissed=[(5001, SURVIVOR)],
            extra_events=((5001, 'Craft Circle', VENUE, 1),),
            survivor_state={5001: (1, 0, VENUE, 'Craft Circle')})

    def test_reviewed_source_owner_keeps_editorial_suppression(self):
        self.assertStaysOnDuplicate(reviewed_owners=[DUP])

    def test_reviewed_identity_match_is_never_overridden(self):
        self.assertStaysOnDuplicate(reviewed_match=DUP)

    def test_suppressed_survivor_declines(self):
        self.assertStaysOnDuplicate(survivor_state={SURVIVOR: (1, 0, VENUE, SURVIVOR_NAME)})

    def test_archived_survivor_without_overlapping_dates_declines(self):
        # "Giants v Cardinals Watch Party" must not take next week's NFL Sunday listing.
        self.assertStaysOnDuplicate(survivor_state={SURVIVOR: (0, 1, VENUE, SURVIVOR_NAME)},
                                    survivor_days=7)
        self.assertStaysOnDuplicate(survivor_state={SURVIVOR: (0, 1, VENUE, SURVIVOR_NAME)},
                                    survivor_days=None)

    def test_survivor_at_another_venue_declines(self):
        """BL38: a cross-venue decision does not bypass the cross-location guard."""
        self.assertStaysOnDuplicate(survivor_venue=9999)

    def test_cycle_declines(self):
        self.assertStaysOnDuplicate(redirects=((DUP, 5001), (5001, DUP)),
                                    extra_events=((5001, 'Craft Circle', VENUE, 1),))


class RedirectHelperTests(unittest.TestCase):
    def test_resolve_chain(self):
        resolve = merger.resolve_redirect_survivor
        self.assertEqual(resolve(1, {}), (None, []))
        self.assertEqual(resolve(1, {1: 2}), (2, [2]))
        self.assertEqual(resolve(1, {1: 2, 2: 3}), (3, [2, 3]))
        self.assertEqual(resolve(1, {1: 2, 2: 1})[0], None)
        long_chain = {i: i + 1 for i in range(1, 10)}
        self.assertIsNone(resolve(1, long_chain)[0])
        self.assertEqual(resolve(1, long_chain, max_hops=20)[0], 10)

    def route(self, **kw):
        args = dict(duplicate_id=1, redirect_survivors={1: 2},
                    survivor_state=lambda eid: {'suppressed': False, 'archived': False,
                                                'location_id': 10, 'in_window': True},
                    dismissed_pairs=set(), reviewed_owner_ids=set(), location_id=10,
                    same_place_fn=lambda a, b: a == b)
        args.update(kw)
        return merger.redirect_route_target(**args)

    def test_route_target_rules(self):
        self.assertEqual(self.route(), 2)
        self.assertEqual(self.route(location_id=None), 2)
        self.assertIsNone(self.route(location_id=11))
        self.assertIsNone(self.route(reviewed_owner_ids={1}))
        self.assertIsNone(self.route(dismissed_pairs={(1, 2)}))
        self.assertIsNone(self.route(survivor_state=lambda eid: None))
        archived = lambda eid: {'suppressed': False, 'archived': True, 'location_id': 10,
                                'in_window': True}
        self.assertIsNone(self.route(survivor_state=archived))
        self.assertEqual(self.route(survivor_state=archived, dates_overlap=lambda e: True), 2)
        self.assertIsNone(self.route(survivor_state=archived, dates_overlap=lambda e: True,
                                     dateless=True))
        self.assertIsNone(self.route(survivor_state=archived, dates_overlap=lambda e: False))


if __name__ == '__main__':
    unittest.main()
