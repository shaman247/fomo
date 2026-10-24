"""Step 6 (source-site fallback) must not let a BRANCH name stand for the brand.

BL12 delivery follow-up (2026-10-23): Commonpoint w3027 rows with an empty
location reached Step 6, where the global alias "Commonpoint Bronx" on l2897
normalizes to the bare brand "commonpoint" and squashes equal to the site name
"Commonpoint". Every venue-less Commonpoint row (Queens camps, a casino trip)
landed on the Bronx center. The key's area qualifier now travels with it, and
the collapsed bare key is declined by the brand-family guard, so the row falls
to Step 7/7b (organizer home venue on name evidence, else unmapped). Virtual
strings keep resolving through the reviewed w3027 → l6046 aliases.

Run: ./venv/bin/python pipeline/tests/test_source_site_bare_brand.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import processor
from processor import build_locations_map, get_location_id


def _map(locations, website_linked=None, website_names=None):
    """A real locations_map from (id, name, short_name, alts, scoped) tuples."""
    rows = [{'id': lid, 'name': name, 'short_name': short, 'address': '',
             'lat': 1.0, 'lng': 1.0, 'emoji': 'X', 'alternate_names': list(alts or []),
             'website_scoped_names': dict(scoped or {})}
            for lid, name, short, alts, scoped in locations]
    db = processor.db
    saved = (db.get_all_locations, db.get_website_locations_map,
             db.get_roving_organizer_websites, db.get_website_names)
    db.get_all_locations = lambda cursor: rows
    db.get_website_locations_map = lambda cursor: dict(website_linked or {})
    db.get_roving_organizer_websites = lambda cursor: set()
    db.get_website_names = lambda cursor: dict(website_names or {})
    try:
        return build_locations_map(None)
    finally:
        (db.get_all_locations, db.get_website_locations_map,
         db.get_roving_organizer_websites, db.get_website_names) = saved


def _linked(m, *ids):
    out = []
    for rec in m['names'].values():
        for r in (rec if isinstance(rec, list) else [rec]):
            if r['id'] in ids and all(o['id'] != r['id'] for o in out):
                out.append(r)
    return out


class TestCommonpointBareBrand(unittest.TestCase):

    def setUp(self):
        locs = [
            (2897, 'Commonpoint Bronx Center', None, ['Commonpoint Bronx'], {}),
            (3286, 'Commonpoint Queens Bay Terrace Center', None, [], {}),
            (4392, 'Commonpoint Queens Central Queens', None, [], {}),
            (6046, 'Sam Field Center (Commonpoint Queens)', None, [],
             {3027: ['Online', 'Virtual', 'Zoom']}),
        ]
        m = _map(locs, website_names={3027: 'Commonpoint'})
        m['website_linked'] = {3027: _linked(m, 2897, 3286, 4392, 6046)}
        self.m = m

    def _id(self, loc):
        res = get_location_id(loc, '', 'commonpoint', 'CQ Mini Camp', self.m,
                              website_id=3027)
        return (res or {}).get('id')

    def test_empty_location_no_longer_lands_on_the_bronx(self):
        self.assertNotEqual(self._id(''), 2897)

    def test_virtual_strings_keep_the_reviewed_home_venue(self):
        self.assertEqual(self._id('Online'), 6046)
        self.assertEqual(self._id('Zoom'), 6046)

    def test_named_branch_still_resolves(self):
        self.assertEqual(self._id('Commonpoint Bronx Center'), 2897)


class TestCommonpointReviewedHomeVenue(unittest.TestCase):
    """User ruling 2026-10-23 (BL12): a w3027 row with an EMPTY or placeholder
    location, or naming only the organizer, maps to the reviewed home l6046.
    Data only, no code: `website_locations.is_primary` on the w3027 → l6046
    link (Step 7b arm 4, 6 links ≤ HOME_VENUE_MAX_LINKED) and a w3027-scoped
    `portable=0` alias "Commonpoint" on l6046 (Step 1, ahead of the fuzzy tier
    that sent the bare brand to the Bronx alias)."""

    def setUp(self):
        locs = [
            (2897, 'Commonpoint Bronx Center', None, ['Commonpoint Bronx'], {}),
            (3286, 'Commonpoint Queens Bay Terrace Center', None, [], {}),
            (4392, 'Commonpoint Queens Central Queens', None, [], {}),
            (6046, 'Sam Field Center (Commonpoint Queens)', None, [],
             {3027: ['Online', 'Commonpoint']}),
        ]
        m = _map(locs, website_names={3027: 'Commonpoint'})
        m['website_linked'] = {3027: [dict(r, is_primary=(r['id'] == 6046))
                                      for r in _linked(m, 2897, 3286, 4392, 6046)]}
        self.m = m

    def _id(self, loc, site='commonpoint'):
        res = get_location_id(loc, '', site, 'Membership Casino Trip', self.m,
                              website_id=3027)
        return (res or {}).get('id')

    def test_empty_location_takes_the_home_venue(self):
        self.assertEqual(self._id(''), 6046)
        # Detail path: no site name, so Step 6 cannot fire; Step 7b answers.
        self.assertEqual(self._id('', site=''), 6046)

    def test_placeholder_takes_the_home_venue(self):
        self.assertEqual(self._id('Not specified'), 6046)

    def test_bare_brand_takes_the_home_venue(self):
        self.assertEqual(self._id('Commonpoint'), 6046)

    def test_bronx_branch_is_not_captured_by_the_bare_alias(self):
        # "Commonpoint Bronx" collapses to the same "commonpoint" key; the
        # area guard on the scoped tier refuses the Queens home venue.
        self.assertEqual(self._id('Commonpoint Bronx'), 2897)

    def test_other_websites_unaffected(self):
        res = get_location_id('', '', 'some other org', 'Talk', self.m, website_id=99)
        self.assertIsNone(res)


class TestSourceSiteStillMatchesItsOwnVenue(unittest.TestCase):

    def test_site_naming_the_same_area(self):
        # w3479 "Kadampa Meditation Center NYC": the site and its venue carry
        # the same qualifier, so the branch family does not stop Step 6.
        m = _map([
            (4727, 'Kadampa Meditation Center NYC', None, [], {}),
            (9043, 'Kadampa Meditation Center Upper West Side', None, [], {}),
            (5966, 'Kadampa Meditation Center Harlem', None, [], {}),
        ])
        res = get_location_id('', '', 'kadampa meditation center nyc', 'Class', m,
                              website_id=None)
        self.assertEqual((res or {}).get('id'), 4727)
        self.assertEqual(res.get('step'), 'source_site')

    def test_plain_brand_venue(self):
        m = _map([(10, 'Book Club Bar', None, [], {}),
                  (11, 'Other Venue', None, [], {})])
        res = get_location_id('', '', 'book club bar', 'Reading', m, website_id=None)
        self.assertEqual((res or {}).get('id'), 10)

    def test_shared_short_name_does_not_outrank_the_one_link(self):
        # w685: both St. Joseph's campuses carry the short_name; the site's
        # one linked campus (Step 7) must win, not the last-written claimant.
        m = _map([
            (2180, "St. Joseph's University (Brooklyn)", "St. Joseph's University", [], {}),
            (2181, "St. Joseph's University (Long Island)", "St. Joseph's University", [], {}),
        ])
        m['website_linked'] = {685: _linked(m, 2180)}
        res = get_location_id('', '', 'st josephs university', 'Info Session', m,
                              website_id=685)
        self.assertEqual((res or {}).get('id'), 2180)


if __name__ == '__main__':
    unittest.main()
