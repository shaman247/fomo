"""A permanently closed venue keeps its row but stops capturing new events (BL54).

The Freehold (loc 845, 45 S 3rd St) closed November 2024, yet every bare
"45 S 3rd St" and every "The Freehold" from any website still resolved to it.
`location_match_policies.closed` removes such a row from the address, name,
alias, short-name, brand-family and prefix/fuzzy tiers; only its
website-scoped aliases (a reviewed per-source decision) still reach it.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db
import processor


def place(id, name, address, closed=False, short_name='', alternate_names=(),
          website_scoped_names=None):
    return dict(id=id, name=name, short_name=short_name, address=address,
                lat=40.7, lng=-73.9, emoji='X', alternate_names=list(alternate_names),
                website_scoped_names=website_scoped_names or {},
                nonportable_scoped_names={}, ambiguous_bare_names=[], closed=closed)


FREEHOLD = place(845, 'The Freehold', '45 S 3rd St, Brooklyn, NY 11249, USA', closed=True,
                 short_name='Freehold', alternate_names=['Freehold Brooklyn'],
                 website_scoped_names={6017: ['Freehold Garden']})
OPEN_BAR = place(901, 'Open Bar Williamsburg', '354 Metropolitan Ave, Brooklyn, NY 11211, USA')


def make_map(*places, linked=None):
    with patch.object(processor.db, 'get_all_locations', return_value=list(places)), \
         patch.object(processor.db, 'get_website_locations_map', return_value=linked or {}), \
         patch.object(processor.db, 'get_website_names', return_value={}), \
         patch.object(processor.db, 'get_roving_organizer_websites', return_value=set()):
        return processor.build_locations_map(None)


def resolve(m, loc, sub='', site=None, event='Saturday Party'):
    result = processor.get_location_id(loc, sub, 'source', event, m, website_id=site)
    return result and result['id']


class ClosedLocationMatchingTests(unittest.TestCase):
    def test_bare_address_no_longer_resolves_to_closed_venue(self):
        m = make_map(FREEHOLD, OPEN_BAR)
        self.assertEqual(m['closed_ids'], {845})
        for site in (None, 1, 6017):
            self.assertIsNone(resolve(m, '45 S 3rd St', site=site))
            self.assertIsNone(resolve(m, '45 S 3rd St, Brooklyn, NY 11249', site=site))
        self.assertIsNone(resolve(m, 'Backyard', sub='45 S 3rd St'))

    def test_closed_venue_names_are_not_matched_globally(self):
        m = make_map(FREEHOLD, OPEN_BAR)
        for name in ('The Freehold', 'Freehold', 'Freehold Brooklyn',
                     'The Freehold Williamsburg', 'The Freehld'):
            self.assertIsNone(resolve(m, name), name)

    def test_scoped_alias_on_closed_venue_still_resolves_for_its_source(self):
        m = make_map(FREEHOLD, OPEN_BAR)
        self.assertEqual(resolve(m, 'Freehold Garden', site=6017), 845)
        self.assertIsNone(resolve(m, 'Freehold Garden', site=1))

    def test_open_address_match_is_unaffected(self):
        m = make_map(FREEHOLD, OPEN_BAR)
        result = processor.get_location_id('354 Metropolitan Ave', '', 'source', 'Party', m)
        self.assertEqual((result['id'], result['step']), (901, 'address'))
        self.assertEqual(resolve(m, 'Open Bar Williamsburg'), 901)

    def test_successor_tenant_owns_a_shared_address(self):
        # Before: two rows on one address marked it AMBIGUOUS, so the new
        # tenant lost its address match to the closed predecessor.
        successor = place(902, 'The Successor', '45 S 3rd St, Brooklyn, NY 11249')
        self.assertIsNone(resolve(make_map(dict(FREEHOLD, closed=False), successor), '45 S 3rd St'))
        self.assertEqual(resolve(make_map(FREEHOLD, successor), '45 S 3rd St'), 902)

    def test_closed_venue_does_not_join_a_brand_family_or_short_name_claim(self):
        open_branch = place(910, 'Smokehouse Brooklyn', '1 Main St, Brooklyn, NY 11201',
                            short_name='Smokehouse')
        closed_branch = place(911, 'Smokehouse Queens', '2 Main St, Queens, NY 11101',
                              short_name='Smokehouse', closed=True)
        m = make_map(open_branch, closed_branch)
        self.assertNotIn(911, m['brand_family'].get('smokehouse', set()))
        self.assertNotIn('smokehouse', m['shared_short_names'])
        self.assertEqual(resolve(m, 'Smokehouse Queens'), None)
        self.assertEqual(resolve(m, 'Smokehouse Brooklyn'), 910)

    def test_website_link_still_reaches_closed_venue(self):
        # A website_locations link is curated per source, like a scoped alias.
        m = make_map(FREEHOLD, linked={77: [dict(id=845, name='The Freehold',
                                                 address=FREEHOLD['address'], lat=40.7,
                                                 lng=-73.9, emoji='X')]})
        self.assertEqual(resolve(m, 'The Freehold', site=77), 845)


class GetAllLocationsClosedFlagTests(unittest.TestCase):
    def test_closed_policy_is_loaded(self):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [(845, 'The Freehold', None, '45 S 3rd St', 40.7, -73.9, 'X', '[]', 1),
             (901, 'Open Bar', None, '354 Metropolitan Ave', 40.7, -73.9, 'X', None, 0)],
            [],
        ]
        rows = {row['id']: row for row in db.get_all_locations(cursor)}
        self.assertTrue(rows[845]['closed'])
        self.assertFalse(rows[901]['closed'])
        self.assertIn('COALESCE(p.closed, 0)', cursor.execute.call_args_list[0][0][0])


if __name__ == '__main__':
    unittest.main()
