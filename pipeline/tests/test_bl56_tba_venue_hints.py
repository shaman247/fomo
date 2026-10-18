"""BL56: "TBA"/"TBA - <area>" venue strings must never land on a specific venue.

2026-10-18: RA (w388, a roving organizer linked to ARTSPACE) listed three
parties at "TBA - Brooklyn". The extraction shortened that to "Brooklyn", which
normalizes to nothing, so Step 7 (website-linked fallback) read it as
venue-less and pinned all three to ARTSPACE. Separately, "TBA - <hint>" strings
reached the prefix/fuzzy tiers ("TBA - Bakery" -> The Bakery).
"""
import unittest
from unittest.mock import patch

import processor

RA = 388          # roving organizer, linked to ARTSPACE
OFFICE_SITE = 50  # ordinary single-venue website
AGGREGATOR = 60   # no linked venue


def loc(id, name, short_name='', address='', alternate_names=(), scoped=None,
        generic=False):
    return dict(id=id, name=name, short_name=short_name, address=address,
                lat=40.7, lng=-73.9, emoji='X',
                alternate_names=list(alternate_names),
                website_scoped_names=scoped or {},
                nonportable_scoped_names={}, ambiguous_bare_names=[],
                generic_location=generic)


ARTSPACE = loc(2660, 'ARTSPACE', address='269 Meserole St, Brooklyn, NY 11206')
OFFICE = loc(70, 'Some Gallery', address='1 Main St, Brooklyn, NY 11201, USA')
LOCATIONS = [
    loc(2208, 'Brooklyn (exact location unspecified)', 'Brooklyn',
        'Brooklyn, NY, USA', scoped={RA: ['TBA Brooklyn']}, generic=True),
    loc(2209, 'Queens (exact location unspecified)', 'Queens',
        'Queens, NY, USA', generic=True),
    loc(9751, 'East Williamsburg', address='East Williamsburg, Brooklyn, NY, USA',
        generic=True),
    ARTSPACE,
    OFFICE,
    loc(4158, 'The Bakery', address='538 Johnson Ave, Brooklyn, NY 11237, USA'),
    loc(8282, 'Brooklyn Warehouse', address='153 26th St, Brooklyn, NY 11232, USA'),
    loc(3882, 'Rockbar NYC', address='185 Christopher St, New York, NY 10014',
        scoped={RA: ['TBA - Rock Bar - 185 Christopher Street, New York Ny 10014']}),
    loc(11709, 'Little Shop of Soil', address='10 Grand St, Brooklyn, NY 11249',
        alternate_names=['TBA - Little Shop of Soil']),
]


def build():
    linked = {RA: [dict(ARTSPACE, is_primary=1)], OFFICE_SITE: [dict(OFFICE, is_primary=1)]}
    with patch.object(processor.db, 'get_all_locations', return_value=LOCATIONS), \
         patch.object(processor.db, 'get_website_locations_map', return_value=linked), \
         patch.object(processor.db, 'get_website_names', return_value={}), \
         patch.object(processor.db, 'get_roving_organizer_websites', return_value={RA}):
        return processor.build_locations_map(None)


def resolve(m, name, sub='', website=None, event='Merge Halloween'):
    result = processor.get_location_id(name, sub, 'source', event, m, website_id=website)
    return result and result['id']


class ArtspaceIncident(unittest.TestCase):
    """The 2026-10-18 rows: a bare borough under a roving organizer."""

    @classmethod
    def setUpClass(cls):
        cls.m = build()

    def test_bare_borough_is_the_borough_pin_not_the_linked_venue(self):
        for event in ('Merge Halloween', 'bumpy!', 'Book Club Radio Meeting #39 Maneater'):
            self.assertEqual(resolve(self.m, 'Brooklyn', website=RA, event=event), 2208)
        self.assertEqual(resolve(self.m, 'Queens, NY', website=RA), 2209)

    def test_area_without_a_pin_stays_unmapped(self):
        self.assertIsNone(resolve(self.m, 'Manhattan', website=RA))

    def test_tba_brooklyn_is_the_borough_pin(self):
        self.assertEqual(resolve(self.m, 'TBA - Brooklyn', website=RA), 2208)
        self.assertEqual(resolve(self.m, 'TBA - Brooklyn', website=AGGREGATOR), 2208)
        self.assertEqual(resolve(self.m, 'TBA - BROOKLYN NY', website=RA), 2208)

    def test_venueless_placeholders_still_reach_the_organizer(self):
        # Product policy (virtual/placeholder -> organizer's venue) is untouched.
        self.assertEqual(resolve(self.m, 'Online', website=RA), 2660)
        self.assertEqual(resolve(self.m, 'New York', website=RA), 2660)

    def test_non_roving_single_venue_site_unchanged(self):
        self.assertEqual(resolve(self.m, 'Brooklyn', website=OFFICE_SITE), 70)


class BareTba(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.m = build()

    def test_curated_site_alias_still_answers(self):
        # w388's curated "TBA Brooklyn" alias collapses onto the bare key.
        self.assertEqual(resolve(self.m, 'TBA', website=RA), 2208)

    def test_no_alias_no_link_stays_unmapped(self):
        self.assertIsNone(resolve(self.m, 'TBA', website=AGGREGATOR))
        self.assertIsNone(resolve(self.m, 'TBD', website=AGGREGATOR, event='The Bakery Night'))

    def test_single_venue_site_keeps_the_venueless_policy(self):
        self.assertEqual(resolve(self.m, 'TBA', website=OFFICE_SITE), 70)

    def test_area_sublocation_is_the_hint(self):
        self.assertEqual(resolve(self.m, 'TBA', 'Queens', website=AGGREGATOR), 2209)


class TbaHints(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.m = build()

    def test_neighbourhood_hint(self):
        self.assertEqual(resolve(self.m, 'TBA - East Williamsburg', website=RA), 9751)

    def test_area_hint_beats_a_collapsed_alias(self):
        # "TBA (Queens)" normalizes to "tba", RA's alias key for Brooklyn.
        self.assertEqual(resolve(self.m, 'TBA (Queens)', website=RA), 2209)

    def test_no_prefix_or_fuzzy_on_the_hint(self):
        # Fuzzy-matched the "TBA - Little Shop of Soil" alias before BL56.
        self.assertIsNone(resolve(self.m, 'TBA - Little Shop of Soils', website=RA))
        self.assertIsNone(resolve(self.m, 'TBA - Bakery', website=RA))
        self.assertIsNone(resolve(self.m, 'TBA - Brooklyn Warehouses', website=RA))
        self.assertIsNone(resolve(self.m, 'TBA - Secret Location', website=RA))
        self.assertIsNone(resolve(self.m, 'TBA - Bushwick / Ridgewood', website=RA))

    def test_exact_venue_name_and_curated_aliases(self):
        self.assertEqual(resolve(self.m, 'TBA - The Bakery', website=RA), 4158)
        self.assertEqual(resolve(
            self.m, 'TBA - Rock Bar - 185 Christopher Street, New York Ny 10014',
            website=RA), 3882)
        self.assertEqual(resolve(self.m, 'TBA - Little Shop of Soil', website=AGGREGATOR), 11709)

    def test_hint_parser(self):
        self.assertEqual(processor._tba_venue_hint('TBA - Brooklyn'), 'Brooklyn')
        self.assertEqual(processor._tba_venue_hint('TBA'), '')
        self.assertEqual(processor._tba_venue_hint('To Be Announced!'), '')
        self.assertEqual(processor._tba_venue_hint('TBA (Queens)'), 'Queens')
        self.assertIsNone(processor._tba_venue_hint('Tbilisi House'))
        self.assertIsNone(processor._tba_venue_hint('Brooklyn'))


if __name__ == '__main__':
    unittest.main()
