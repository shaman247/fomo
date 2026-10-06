"""Enriched DSA listings must feed their reviewed offsite canonicals."""
import io
import sys
import unittest
from contextlib import ExitStack, redirect_stdout
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger


class DsaDetailMergeTests(unittest.TestCase):
    CASES = (
        (1491512, 242736, 245576, 7974,
         'NYC-DSA Pedalers Union — Bronx River Ride October 2026',
         'NYC-DSA Pedalers Union — Bronx River Ride October 2026',
         'José Julián Martí Statue'),
        (1491513, 242737, 268903, 415,
         'Trash Cleanup in Greater Inwood', 'Trash Cleanup in Greater Inwood',
         'Inwood Hill Park'),
        (1491508, 252764, 268899, 1944,
         'NYC-DSA Coffee With Comrades (2026-10-17)',
         'Coffee with Comrades - Prospect Heights (2026-10-17)', 'Bon Tree'),
    )

    def test_enriched_sources_choose_visible_canonicals_without_new_events(self):
        for ce, survivor, hidden, venue, source_name, canonical_name, venue_name in self.CASES:
            with self.subTest(source=ce):
                self.check_merge(ce, survivor, hidden, venue, source_name, canonical_name, venue_name)

    def check_merge(self, ce, survivor, hidden, venue, source_name, canonical_name, venue_name):
        today = date.today()
        url = f'https://actionnetwork.org/events/regression-{ce}'
        cursor = MagicMock(lastrowid=999999)

        def execute(query, params=None):
            rows, one = [], None
            if 'SELECT ce.id, ce.name' in query:
                rows = [(ce, source_name, None, 'Detail page description.', '📅',
                         venue_name, None, venue, url, 591, None, None, 127495)]
            elif 'SELECT DISTINCT e.id, e.name, e.location_id' in query:
                # Hidden first deliberately: ordering must not rescue a bad match.
                rows = [(hidden, source_name, 1940, None, None, 'NYC-DSA', 591, 1),
                        (survivor, canonical_name, venue, None, None, venue_name, 591, 0)]
            elif 'SELECT event_id, start_date, start_time, end_date' in query:
                rows = [(eid, today, '10am', None) for eid in (hidden, survivor)]
            elif 'SELECT eu.event_id, eu.url, e.name' in query:
                rows = [(hidden, url, source_name, 591, 1940, 1),
                        (survivor, url, canonical_name, 591, venue, 0)]
            elif 'SELECT id, name, emoji, lat, lng FROM locations' in query:
                rows = [(1940, 'NYC-DSA Office', '📅', None, None),
                        (venue, venue_name, '📅', None, None)]
            elif 'FROM crawl_event_occurrences' in query:
                rows = [(ce, today, '10am', None, '1pm', 0)]
            elif 'SELECT location_id FROM events WHERE id' in query:
                one = (venue if params[0] == survivor else 1940,)
            elif 'SELECT location_name, location_id FROM events WHERE id' in query:
                one = (venue_name, venue)
            elif 'SELECT description, emoji, name, short_name, event_type' in query:
                one = ('Existing description.', '📅', canonical_name, None, None)
            cursor.fetchall.return_value = rows
            cursor.fetchone.return_value = one

        cursor.execute.side_effect = execute
        # Explicitly reviewed title alias. It only applies after detail venue
        # resolution and at the reviewed source slot; it grants no general
        # URL/name or cross-venue equivalence.
        index = {}
        if ce == 1491508:
            index[(591, url, merger.reviewed_event_identity.name_key(source_name), venue)] = {
                survivor: {(str(today), '10am', str(today))}}
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(patch.object(merger, 'EditLogger', None))
            stack.enter_context(patch.object(merger.reviewed_event_identity, 'load_index', return_value=index))
            stack.enter_context(patch.object(merger.venue_overrides, 'load_rules', return_value=[]))
            stack.enter_context(patch.object(merger, 'get_active_date_window',
                                            return_value=(today, today + timedelta(days=90))))
            database = stack.enter_context(patch.object(merger, 'db'))
            database.build_tag_ancestor_map.return_value = ({}, set())
            database.archive_dead_source_events.return_value = (0, [])
            for helper in ('_merge_occurrences_into_event', '_merge_grouped_event_urls',
                           'refresh_source_metadata', 'refresh_source_session_details'):
                stack.enter_context(patch.object(merger, helper))
            self.assertEqual(merger.merge_crawl_events(cursor, MagicMock(), website_ids=[591]), (0, 1))
        links = [call.args[1] for call in cursor.execute.call_args_list
                 if 'INSERT IGNORE INTO event_sources' in call.args[0]]
        self.assertEqual(links, [(survivor, ce)])
        self.assertFalse(any('INSERT INTO events (' in call.args[0]
                             for call in cursor.execute.call_args_list))

    def test_reviewed_title_alias_cannot_bypass_venue_or_session_evidence(self):
        identity = merger.reviewed_event_identity
        name = self.CASES[-1][4]
        url = 'https://actionnetwork.org/events/coffee-with-comrades-prospect-heights'
        index = {(591, url, identity.name_key(name), 1944): {
            252764: {('2026-10-17', '11am', '2026-10-17')}}}
        args = dict(website_id=591, name=name, url=url, location_id=1944,
                    occurrences=[('2026-10-17', '11am', None)])
        self.assertEqual(identity.match(index, **args), 252764)
        for change in (dict(location_id=1940), dict(location_id=None),
                       dict(website_id=592), dict(name='Coffee with Comrades'),
                       dict(url=url+'?branch=other'),
                       dict(occurrences=[('2026-10-17', '', None)]),
                       dict(occurrences=[('2026-10-18', '11am', None)]),
                       dict(occurrences=args['occurrences']+[('2026-10-18', '11am', None)])):
            with self.subTest(change=change):
                self.assertIsNone(identity.match(index, **dict(args, **change)))


if __name__ == '__main__':
    unittest.main()
