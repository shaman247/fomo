"""BL38: a reviewed cross-venue duplicate merge leaves a location bridge.

`record_merge` wrote no redirect when the two events sat at different venues,
so a source that kept naming the loser's venue landed on the hidden loser and
the visible survivor starved (35 such merges on 2026-10-11, 14 with future
dates). The bridge is keyed by the LOSER's venue: it routes only a source naming
that venue exactly, only for the reviewed slots, and only while both events
stay where the decision found them. The merger exempts exactly that match from
its cross-location guard and never re-pins the survivor to the loser's venue.
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
import reviewed_event_identity as identity

URL = 'https://parks.test/events/bodyweight-circuit-training'
NAME = 'Bodyweight Circuit Training'
LOSER_VENUE, SURVIVOR_VENUE = 1419, 3499
SLOT = ('2026-10-20', '6pm', '2026-10-20')


def bridge_index(target=209115):
    index = identity.IdentityIndex()
    index.location_bridges[(7, URL, identity.name_key(NAME), LOSER_VENUE)] = {target: {SLOT}}
    return index


class BridgeMatchTests(unittest.TestCase):

    def match(self, location_id=LOSER_VENUE, occurrences=(('2026-10-20', '6pm', None),),
              index=None):
        return identity.match(index or bridge_index(), 7, NAME, URL, location_id, list(occurrences))

    def test_source_naming_the_losers_venue_reaches_the_survivor(self):
        self.assertEqual(self.match(), 209115)
        self.assertTrue(identity.is_location_bridge(bridge_index(), 7, NAME, URL, LOSER_VENUE, 209115))

    def test_any_other_venue_or_none_declines(self):
        for venue in (SURVIVOR_VENUE, 555, None):
            with self.subTest(venue=venue):
                self.assertIsNone(self.match(location_id=venue))
                self.assertFalse(identity.is_location_bridge(bridge_index(), 7, NAME, URL, venue, 209115))

    def test_unreviewed_slots_decline(self):
        self.assertIsNone(self.match(occurrences=[('2026-10-27', '6pm', None)]))
        self.assertIsNone(self.match(occurrences=[('2026-10-20', '6pm', None),
                                                  ('2026-10-27', '6pm', None)]))

    def test_bridge_and_ordinary_redirect_together_are_ambiguous(self):
        index = bridge_index()
        index[(7, URL, identity.name_key(NAME), LOSER_VENUE)] = {300: {SLOT}}
        self.assertIsNone(self.match(index=index))


class BridgeLoadTests(unittest.TestCase):
    """load_index keeps a bridge only while both venues are unchanged."""

    def load(self, survivor_location, duplicate_location):
        scope = dict(website_id=7, url=URL, name=identity.name_key(NAME),
                     location_id=LOSER_VENUE, slots=[list(SLOT)],
                     policy=identity.LOCATION_BRIDGE_POLICY,
                     survivor_location_id=SURVIVOR_VENUE)
        rule = dict(duplicate_id=206764, survivor_id=209115, survivor_name=NAME,
                    current_name=NAME, location_id=survivor_location, reviewed=1,
                    duplicate_location_id=duplicate_location,
                    source_identities=json.dumps([scope]))
        occurrence = dict(event_id=209115, start_date=SLOT[0], start_time=SLOT[1],
                          end_date=None, end_time=None)

        def rows(_cursor, sql, _args=()):
            return [rule] if 'event_merge_redirects' in sql else [occurrence]

        with patch.object(identity, '_rows', side_effect=rows):
            return identity.load_index(MagicMock())

    def test_unchanged_venues_load_the_bridge(self):
        index = self.load(SURVIVOR_VENUE, LOSER_VENUE)
        self.assertEqual(identity.match(index, 7, NAME, URL, LOSER_VENUE,
                                        [('2026-10-20', '6pm', None)]), 209115)
        self.assertEqual(dict(index), {})  # never an ordinary same-venue rule

    def test_moved_survivor_or_loser_drops_the_bridge(self):
        for survivor, loser in ((555, LOSER_VENUE), (SURVIVOR_VENUE, 555), (None, LOSER_VENUE)):
            with self.subTest(survivor=survivor, loser=loser):
                self.assertEqual(self.load(survivor, loser).location_bridges, {})


class BridgeMergeTests(unittest.TestCase):
    """The merge path: guard exemption and no re-pin, for the bridged match only."""

    def run_merge(self, bridged):
        today = date.today()
        cursor = MagicMock(lastrowid=None)
        executed = []

        def execute(query, params=None):
            executed.append((query, params))
            rows, one = [], None
            if 'SELECT ce.id, ce.name' in query:
                rows = [(1, NAME, None, 'Desc.', '💪', 'Old Park', None, LOSER_VENUE, URL,
                         7, None, None, 55)]
            elif 'SELECT website_id, location_id FROM website_locations' in query:
                rows = [(7, LOSER_VENUE)]  # the loser's venue is the site's linked venue
            elif 'FROM crawl_event_occurrences' in query:
                rows = [(1, today + timedelta(days=8), '6pm', None, None, 0)]
            elif 'INSERT INTO events (' in query:
                cursor.lastrowid = 900001
            elif 'SELECT location_id FROM events WHERE id' in query:
                one = (SURVIVOR_VENUE,)
            elif 'SELECT location_name, location_id FROM events WHERE id' in query:
                one = ('New Park', SURVIVOR_VENUE)
            elif 'SELECT name FROM events WHERE id' in query:
                one = (NAME,)
            elif 'SELECT description, emoji, name, short_name, event_type' in query:
                one = ('Existing.', '💪', NAME, None, None)
            cursor.fetchall.return_value = rows
            cursor.fetchone.return_value = one

        cursor.execute.side_effect = execute
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(patch.object(merger, 'EditLogger', None))
            stack.enter_context(patch.object(merger.reviewed_event_identity, 'load_index',
                                             return_value={}))
            stack.enter_context(patch.object(merger.reviewed_event_identity, 'match',
                                             return_value=209115))
            stack.enter_context(patch.object(merger.reviewed_event_identity, 'is_location_bridge',
                                             return_value=bridged))
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
            merger.merge_crawl_events(cursor, MagicMock(), website_ids=[7])
        links = {p[1]: p[0] for q, p in executed if 'INSERT IGNORE INTO event_sources' in q}
        repins = [p for q, p in executed if q.startswith('UPDATE events SET location_id')]
        return links, repins

    def test_bridged_match_crosses_the_venue_guard_without_repinning(self):
        links, repins = self.run_merge(bridged=True)
        self.assertEqual(links, {1: 209115})
        self.assertEqual(repins, [])

    def test_an_ordinary_reviewed_match_still_meets_the_guard(self):
        links, _ = self.run_merge(bridged=False)
        self.assertNotEqual(links.get(1), 209115)


if __name__ == '__main__':
    unittest.main()
