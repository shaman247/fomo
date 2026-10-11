"""BL31 / BL33: bare names the location matcher resolved to the wrong row.

BL31 (2026-10-10 /fix-address-mismatches):
  * bare "Washington Park" fuzzy-matched SAPO block row 11433 (Fort Greene)
    through a `short_name` that Union City's row 7211 also claims;
  * bare "The Shop" fuzzy-matched loc 6934 "The Shope" (one letter off);
  * bare "Sunnyside" (a Queens neighbourhood) exact-matched the `short_name`
    of Washington Irving's Sunnyside in Irvington.
BL33 (2026-10-10 unmapped pass): a website-scoped alternate name "Manhattan"
never matched, because normalization collapses a bare borough to ''.
"""
import unittest
from unittest.mock import patch

import processor


def loc(id, name, short_name='', address='', alternate_names=(), scoped=None):
    return dict(id=id, name=name, short_name=short_name, address=address,
                lat=40.7, lng=-73.9, emoji='X',
                alternate_names=list(alternate_names),
                website_scoped_names=scoped or {},
                nonportable_scoped_names={}, ambiguous_bare_names=[])


def build(locations, linked=None):
    with patch.object(processor.db, 'get_all_locations', return_value=locations), \
         patch.object(processor.db, 'get_website_locations_map', return_value=linked or {}), \
         patch.object(processor.db, 'get_website_names', return_value={}), \
         patch.object(processor.db, 'get_roving_organizer_websites', return_value=set()):
        return processor.build_locations_map(None)


def resolve(m, name, sub='', website=None, event='Some Event'):
    result = processor.get_location_id(name, sub, 'source', event, m, website_id=website)
    return result and result['id']


class ScopedBareBoroughAlias(unittest.TestCase):
    """BL33: Step 1 must see the raw key when normalization empties it."""

    def setUp(self):
        self.m = build([
            loc(2211, 'Manhattan (exact location unspecified)', 'Manhattan',
                'Manhattan, New York, NY, USA', scoped={3614: ['Manhattan']}),
            loc(50, 'Some Office', address='1 Main St, Brooklyn, NY 11201, USA'),
        ], linked={3614: [dict(id=50, name='Some Office')]})

    def test_scoped_bare_borough_alias_resolves_for_its_site(self):
        self.assertEqual(resolve(self.m, 'Manhattan', website=3614), 2211)

    def test_sublocation_still_names_the_place(self):
        m = build([
            loc(2211, 'Manhattan (exact location unspecified)', 'Manhattan',
                'Manhattan, New York, NY, USA', scoped={3614: ['Manhattan']}),
            loc(192, 'Central Park', address='Central Park, New York, NY, USA'),
        ])
        self.assertEqual(resolve(m, 'Manhattan', 'Central Park', website=3614), 192)

    def test_other_sites_do_not_inherit_the_raw_key(self):
        # Step 5c (cross-site alias) must not start answering bare boroughs
        # for every website because Step 1 learned the raw key.
        self.assertIsNone(resolve(self.m, 'Manhattan', website=999))


class CollidingShortNameIsNotAnIdentity(unittest.TestCase):
    """BL31a: a short_name two rows claim cannot pick one of them in fuzzy."""

    def setUp(self):
        self.m = build([
            loc(7211, 'Washington Park (Union City)', 'Washington Park',
                'Washington Park, Union City, NJ 07087, USA'),
            loc(11433, 'Washington Park (Willoughby Ave–Dekalb Ave), Brooklyn',
                'Washington Park', 'Washington Park & Willoughby Ave, Brooklyn, NY 11201, USA'),
            loc(426, 'J.J. Byrne Playground', address='5th Ave, Brooklyn, NY 11215, USA',
                scoped={594: ['Washington Park']}),
            loc(953, 'Washington Square Park', 'Washington Sq Park',
                'Washington Square, New York, NY 10012, USA'),
        ])

    def test_bare_shared_short_name_declines(self):
        # Nor may a near-spelled key answer it: the source is ambiguous, not
        # misspelled ("washington sq park" scores 0.91).
        self.assertIsNone(resolve(self.m, 'Washington Park'))

    def test_curated_scoped_alias_still_wins(self):
        self.assertEqual(resolve(self.m, 'Washington Park', website=594), 426)

    def test_qualified_name_still_resolves(self):
        self.assertEqual(resolve(self.m, 'Washington Park (Union City)'), 7211)

    def test_area_qualifier_picks_the_claimant(self):
        # Only rows whose name/aliases carry an area qualifier can conflict.
        m = build([
            loc(1, 'Pratt Institute Brooklyn', 'Pratt', '200 Willoughby Ave, Brooklyn, NY 11205, USA'),
            loc(2, 'Pratt Institute Manhattan', 'Pratt', '144 W 14th St, New York, NY 10011, USA'),
        ])
        self.assertEqual(resolve(m, 'Pratt Manhattan', 'Room 201'), 2)
        self.assertIsNone(resolve(m, 'Pratt', 'Room 201'))

    def test_unshared_short_name_still_fuzzy_resolves(self):
        m = build([loc(1, 'Washington Park (Union City)', 'Washington Park',
                       'Washington Park, Union City, NJ 07087, USA')])
        self.assertEqual(resolve(m, 'Washington Park'), 1)


class MidWordContainment(unittest.TestCase):
    """BL31b: 'the shop' sits inside 'the shope' only by cutting a word."""

    def test_the_shop_is_not_the_shope(self):
        m = build([loc(6934, 'The Shope', address='420 Carroll St, Brooklyn, NY 11215, USA')])
        self.assertIsNone(resolve(m, 'The Shop'))

    def test_article_typo_still_resolves(self):
        m = build([loc(1, 'Le Petit Versailles', address='346 E Houston St, New York, NY 10002, USA')])
        self.assertEqual(resolve(m, 'La Petit Versailles'), 1)

    def test_glued_prefix_alias_still_resolves(self):
        # Normalization joins "PGML-Biblioteca" into one word.
        m = build([loc(7310, 'Priscilla Gardner Main Library',
                       address='472 Jersey Ave, Jersey City, NJ 07302, USA',
                       scoped={3898: ['PGML-Biblioteca Criolla']})])
        self.assertEqual(resolve(m, 'Biblioteca Criolla', '4th Floor', website=3898), 7310)

    def test_dropped_plural_still_resolves(self):
        m = build([loc(1, 'Nowadays', address='56-06 Cooper Ave, Ridgewood, NY 11385, USA')])
        self.assertEqual(resolve(m, 'Nowaday'), 1)


class BareMunicipalityShortName(unittest.TestCase):
    """BL31c: a bare place name is not a venue's short_name elsewhere."""

    def setUp(self):
        self.m = build([
            loc(10591, "Washington Irving's Sunnyside", 'Sunnyside',
                '3 W Sunnyside Ln, Irvington, NY 10533, USA'),
            loc(803, 'Sunnyside Library', address='43-06 Greenpoint Ave, Long Island City, NY 11104, USA',
                scoped={172: ['Sunnyside']}),
            loc(1361, 'Sunnyside Community Services', address='43-31 39th St, Sunnyside, NY 11104, USA'),
        ])

    def test_bare_neighbourhood_does_not_take_a_venue_short_name(self):
        self.assertIsNone(resolve(self.m, 'Sunnyside'))

    def test_curated_scoped_alias_still_wins(self):
        self.assertEqual(resolve(self.m, 'Sunnyside', website=172), 803)

    def test_full_venue_name_still_resolves(self):
        self.assertEqual(resolve(self.m, "Washington Irving's Sunnyside"), 10591)

    def test_short_name_that_is_not_a_municipality_still_resolves(self):
        m = build([loc(1, 'Books Are Magic (Montague St)', 'Montague',
                       '122 Montague St, Brooklyn, NY 11201, USA')])
        self.assertEqual(resolve(m, 'Montague'), 1)


if __name__ == '__main__':
    unittest.main()
