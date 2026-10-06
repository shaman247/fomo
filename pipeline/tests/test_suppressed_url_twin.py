"""A source the matcher gives to a SUPPRESSED twin moves to the VISIBLE event
holding the same event URL.

Climate Cafe w489, 2026-10-03: Luma renamed e200908 "Fall of Freedom: Erasure
Poetry Workshop" to "Excavating the Future: Erasure in the Past, Present, &
Poetic". A merge-created row under the new title (e242112) had been hidden as
the dedupe loser, but the venue tier still matched it by exact name, and the
visible canonical (old title, reachable only through the shared Luma URL)
received nothing and was archived. Untapped NY (e170841 vs e215907) is the
venue-pin variant: the loser sat at the source's home pin, the canonical at
Grand Central, so the venue tier never saw the canonical at all.

These tests drive the whole `merge_crawl_events` path over a fake cursor
(`test_dsa_detail_identity` pattern), so the index builders, the tier ladder
and the cross-location guard all run for real.
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

CLIMATE_URL = 'https://luma.com/36g32qr5'
NEW_TITLE = 'Excavating the Future: Erasure in the Past, Present, & Poetic'
OLD_TITLE = 'Fall of Freedom: Erasure Poetry Workshop'
UNTAPPED_URL = 'https://fareharbor.com/untappednewyork/items/667341/'


class SuppressedUrlTwinMergeTests(unittest.TestCase):

    def run_merge(self, *, ce_name=NEW_TITLE, url=CLIMATE_URL, website=489,
                  ce_venue=4659, hidden=(242112, NEW_TITLE, 4659),
                  visible=(200908, OLD_TITLE, 4659), visible_url=None,
                  visible_days=0, roster_extra=(), dismissed=(), redirects=(),
                  reviewed_owners=(), reviewed_match=None, website_pins=()):
        today = date.today()
        ce = 1512995
        hidden_id, hidden_name, hidden_venue = hidden
        visible_id, visible_name, visible_venue = visible
        venues = {hidden_id: hidden_venue, visible_id: visible_venue}
        cursor = MagicMock(lastrowid=999999)

        def execute(query, params=None):
            rows, one = [], None
            if 'SELECT ce.id, ce.name' in query:
                rows = [(ce, ce_name, None, 'Workshop.', '📝', 'Venue', None,
                         ce_venue, url, website, None, None, 128000)]
            elif 'SELECT DISTINCT e.id, e.name, e.location_id' in query:
                # Hidden first deliberately: ordering must not decide the result.
                rows = [(hidden_id, hidden_name, hidden_venue, None, None, 'Venue', website, 1),
                        (visible_id, visible_name, visible_venue, None, None, 'Venue', website, 0)]
            elif 'SELECT event_id, start_date, start_time, end_date' in query:
                rows = [(hidden_id, today, '11:30am', None), (hidden_id, today, '1pm', None),
                        (visible_id, today + timedelta(days=visible_days), '1pm', None)]
            elif 'SELECT eu.event_id, eu.url, e.name' in query:
                rows = [(hidden_id, url, hidden_name, website, hidden_venue, 1),
                        (visible_id, visible_url or url, visible_name, website, visible_venue, 0)]
            elif 'SELECT crawl_result_id, id, name FROM crawl_events' in query:
                rows = [(128000, ce, ce_name)] + [(128000, 1600000 + i, n)
                                                  for i, n in enumerate(roster_extra)]
            elif 'FROM website_locations' in query:
                rows = list(website_pins)
            elif 'FROM dedupe_dismissed_pairs' in query:
                rows = list(dismissed)
            elif 'FROM event_merge_redirects' in query:
                rows = list(redirects)
            elif 'SELECT DISTINCT event_id FROM event_source_identities' in query:
                rows = [(eid,) for eid in reviewed_owners]
            elif 'SELECT id, name, emoji, lat, lng FROM locations' in query:
                rows = [(v, f'Venue {v}', '📍', None, None) for v in set(venues.values()) | {ce_venue}]
            elif 'FROM crawl_event_occurrences' in query:
                rows = [(ce, today, '11:30am', None, '2pm', 0)]
            elif 'SELECT location_id FROM events WHERE id' in query:
                one = (venues.get(params[0]),)
            elif 'SELECT location_name, location_id FROM events WHERE id' in query:
                one = ('Venue', venues.get(params[0]))
            elif 'SELECT description, emoji, name, short_name, event_type' in query:
                one = ('Existing.', '📝', visible_name if params[0] == visible_id else hidden_name,
                       None, None)
            cursor.fetchall.return_value = rows
            cursor.fetchone.return_value = one

        cursor.execute.side_effect = execute
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(patch.object(merger, 'EditLogger', None))
            stack.enter_context(patch.object(merger.reviewed_event_identity, 'load_index', return_value={}))
            if reviewed_match is not None:
                stack.enter_context(patch.object(merger.reviewed_event_identity, 'match',
                                                 return_value=reviewed_match))
            stack.enter_context(patch.object(merger.venue_overrides, 'load_rules', return_value=[]))
            stack.enter_context(patch.object(merger, 'get_active_date_window',
                                            return_value=(today, today + timedelta(days=90))))
            database = stack.enter_context(patch.object(merger, 'db'))
            database.build_tag_ancestor_map.return_value = ({}, set())
            database.archive_dead_source_events.return_value = (0, [])
            for helper in ('_merge_occurrences_into_event', '_merge_grouped_event_urls',
                           'refresh_source_metadata', 'refresh_source_session_details'):
                stack.enter_context(patch.object(merger, helper))
            result = merger.merge_crawl_events(cursor, MagicMock(), website_ids=[website])
        calls = cursor.execute.call_args_list
        links = [c.args[1] for c in calls if 'INSERT IGNORE INTO event_sources' in c.args[0]]
        relocations = [c.args[1] for c in calls
                       if c.args[0].startswith('UPDATE events SET location_id')]
        self.assertEqual(result, (0, 1))
        self.assertFalse(any('INSERT INTO events (' in c.args[0] for c in calls))
        return links, relocations

    # ── The live shapes ──
    def test_renamed_event_source_feeds_visible_url_twin_not_hidden_exact_name(self):
        self.assertFalse(merger.are_names_similar(NEW_TITLE, OLD_TITLE))
        links, _ = self.run_merge()
        self.assertEqual(links, [(200908, 1512995)])

    def test_venue_pin_twin_feeds_visible_canonical_and_keeps_its_venue(self):
        name = 'Grand Central Nightcap Tour'
        links, relocations = self.run_merge(
            ce_name=name, url=UNTAPPED_URL, website=4998, ce_venue=6729,
            hidden=(215907, name, 6729), visible=(170841, name, 5753),
            website_pins=[(4998, 6729)])
        self.assertEqual(links, [(170841, 1512995)])
        # The dedupe kept Grand Central; the source's home pin must not undo it.
        self.assertEqual(relocations, [])

    def test_templated_series_sibling_in_capture_does_not_block_handoff(self):
        # Tri-State Bi+ w3709: the same pass lists the 2nd-Tuesday group, which
        # is fuzzy-similar to (but not) the visible 4th-Tuesday canonical.
        name = 'VIRTUAL Westchester 4th Tuesday Bisexual+ Discussion & Support Group'
        links, _ = self.run_merge(
            ce_name=name, url='https://www.meetup.com/bisexual-nyc/events/mnxfbvyjcnbkc/',
            website=3709, ce_venue=1427, hidden=(255561, name, 1427),
            visible=(101241, name + ' at the LOFT', 10803),
            roster_extra=['VIRTUAL Westchester 2nd Tuesday Bisexual Group'])
        self.assertEqual(links, [(101241, 1512995)])

    # ── Explicit decisions and missing evidence keep the hidden match ──
    def assertStaysHidden(self, **kwargs):
        links, _ = self.run_merge(**kwargs)
        self.assertEqual(links, [(242112, 1512995)])

    def test_dismissed_pair_is_binding(self):
        self.assertStaysHidden(dismissed=[(200908, 242112)])

    def test_reviewed_source_owner_keeps_editorial_suppression(self):
        self.assertStaysHidden(reviewed_owners=[242112])

    def test_reviewed_identity_match_is_never_overridden(self):
        self.assertStaysHidden(reviewed_match=242112)

    def test_redirect_to_another_survivor_or_from_the_twin_declines(self):
        self.assertStaysHidden(redirects=[(242112, 777)])
        self.assertStaysHidden(redirects=[(200908, 242112)])

    def test_redirect_naming_this_twin_allows_handoff(self):
        links, _ = self.run_merge(redirects=[(242112, 200908)])
        self.assertEqual(links, [(200908, 1512995)])

    def test_visible_row_without_the_url_or_dates_is_not_a_twin(self):
        self.assertStaysHidden(visible_url='https://luma.com/other-event')
        self.assertStaysHidden(visible_days=5)

    def test_capture_that_also_lists_the_twin_is_a_shared_page_not_a_rename(self):
        # Two gallery shows on one exhibition URL: the pass speaks for both.
        self.assertStaysHidden(roster_extra=[OLD_TITLE])


class VisibleUrlTwinUnitTests(unittest.TestCase):
    def twin(self, holders, **kw):
        args = dict(suppressed_id=1, name='New Title', url='https://site.test/e/1',
                    website_id=7, crawl_event_id=50, dates_overlap=lambda eid: True,
                    existing_by_url={(7, merger.normalize_url_for_identity('https://site.test/e/1')): holders},
                    url_name_counts={}, listing_url_keys=set(), roster=(),
                    dismissed_pairs=set(), redirect_survivors={}, reviewed_owner_ids=set())
        args.update(kw)
        return merger._visible_url_twin(**args)

    def test_two_visible_twins_fail_closed(self):
        hidden = {'id': 1, 'name': 'New Title', 'suppressed': True}
        a = {'id': 2, 'name': 'Old Title', 'suppressed': False}
        b = {'id': 3, 'name': 'Other Title', 'suppressed': False}
        self.assertEqual(self.twin([hidden, a]), 2)
        self.assertIsNone(self.twin([hidden, a, b]))

    def test_listing_url_and_hidden_not_holding_url_decline(self):
        hidden = {'id': 1, 'name': 'New Title', 'suppressed': True}
        a = {'id': 2, 'name': 'Old Title', 'suppressed': False}
        key = (7, merger.normalize_url_for_identity('https://site.test/e/1'))
        self.assertIsNone(self.twin([hidden, a], listing_url_keys={key}))
        self.assertIsNone(self.twin([hidden, a], url_name_counts={key: 3}))
        self.assertIsNone(self.twin([a]))


if __name__ == '__main__':
    unittest.main()
