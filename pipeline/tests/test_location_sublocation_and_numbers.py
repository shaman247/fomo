"""Two `get_location_id` bugs found by the 2026-08-31 run, both about a venue
whose identity lives in a part of the string the matcher was throwing away.

1. **A sublocation-qualified name never got its turn.** `location_keys` already
   contains `full_loc` (location_name + sublocation), but Step 2 looped TIERS on
   the outside, so `names['brooklyn bridge park']` — the whole 85-acre park —
   answered before `alternate_names['brooklyn bridge park pier 6']` — the actual
   pier — was ever consulted. Every multi-venue park/campus/complex is in that
   shape, because a parent's name is always a primary `name` while a child
   feature's "<parent> <feature>" form is almost always an ALTERNATE name.
   Same TIERS-before-KEYS family as the 2026-07-29 fix, one level finer.

2. **A trailing digit was treated as a typo.** Bare "Pier 6" fuzzy-matched
   "Pier 66 at Hudson River Park" (Levenshtein 0.923, over the 0.90 threshold)
   and pinned seven NYC Parks crawl_events four miles away in the wrong borough.
   A number in a venue name is an IDENTIFIER: the live corpus holds 22 numbered
   families (Pier N, Studio N, <Borough> Community Board N, P.S. N, Beach N,
   Building N, Gallery N, Bar N, American Legion Post N) and 816 same-stem pairs
   that are fuzzy-reachable from each other.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import (
    _normalize_location_name,
    _numeric_identity_conflict,
    get_location_id,
)


def _tier(pairs):
    return {
        _normalize_location_name(n): {'id': lid, 'emoji': 'X', 'name': n}
        for n, lid in (pairs or [])
    }


def _make_locations_map(names=None, alternate_names=None, short_names=None,
                        website_scoped=None):
    """Minimal locations_map for get_location_id, from (name, id) pairs."""
    return {
        'names': _tier(names),
        'alternate_names': _tier(alternate_names),
        'short_names': _tier(short_names),
        'addresses': {},
        'website_scoped': {wid: _tier(alts)
                           for wid, alts in (website_scoped or {}).items()},
        'website_linked': {},
        'city_states': {},
    }


def _id(locmap, loc, sub=None, event_name='Some Event', website_id=None):
    res = get_location_id(loc, sub, 'site', event_name, locmap,
                          website_id=website_id)
    return res['id'] if res else None


# The Brooklyn Bridge Park family as it exists in `locations` on 2026-08-31:
# one parent plus nine child features, reachable by twelve distinct name forms.
BBP_NAMES = [
    ('Brooklyn Bridge Park', 140),
    ('Brooklyn Bridge Park Environmental Education Center', 286),
    ('Harbor View Lawn (Brooklyn Bridge Park)', 10217),
    ('Pier 2 at Brooklyn Bridge Park', 10218),
    ('Pier 3 at Brooklyn Bridge Park', 10219),
    ('Pier 4 Beach (Brooklyn Bridge Park)', 10220),
    ('Liberty Lawn (Brooklyn Bridge Park)', 10221),
    ('The Vale (Brooklyn Bridge Park)', 10316),
    ('Pier 1 at Brooklyn Bridge Park', 10391),
    ('Pier 6 at Brooklyn Bridge Park', 10398),
    ('Pier 3 Greenway Terrace at Brooklyn Bridge Park', 10399),
]
BBP_ALTS = [
    ('Environmental Education Center at Brooklyn Bridge Park', 286),
    ('Brooklyn Bridge Park Environmental Education Center', 286),
    ('Pier 2 at Brooklyn Bridge Park', 10218),
    ('Brooklyn Bridge Park - The Vale Pier 1', 10316),
    ('Brooklyn Bridge Park Pier 6', 10398),
    ('Pier 6 in Brooklyn Bridge Park', 10398),
    ('Brooklyn Bridge Park Pier 3 Greenway Terrace', 10399),
]


def _bbp_map():
    return _make_locations_map(names=BBP_NAMES, alternate_names=BBP_ALTS)


class TestSublocationQualifiedAlternateName(unittest.TestCase):
    """A `name + sublocation` composite that exactly matches a curated alternate
    name must beat the bare parent name, whichever tier each of them lives in."""

    def test_composite_alt_beats_parent_primary_name(self):
        """The reported bug: BBP + "Pier 6" landed on the whole park (140)."""
        self.assertEqual(_id(_bbp_map(), 'Brooklyn Bridge Park', 'Pier 6'), 10398)

    def test_composite_alt_beats_parent_for_a_second_feature(self):
        self.assertEqual(
            _id(_bbp_map(), 'Brooklyn Bridge Park', 'Pier 3 Greenway Terrace'),
            10399)

    def test_composite_reaches_a_primary_name_too(self):
        """Composite-first must not lose the hits it already made."""
        self.assertEqual(
            _id(_bbp_map(), 'Pier 2', 'at Brooklyn Bridge Park'), 10218)

    def test_parent_without_a_sublocation_is_untouched(self):
        self.assertEqual(_id(_bbp_map(), 'Brooklyn Bridge Park'), 140)

    def test_unknown_sublocation_still_falls_back_to_the_parent(self):
        """No composite row for Pier 5 — coarsening to the park is correct."""
        self.assertEqual(_id(_bbp_map(), 'Brooklyn Bridge Park', 'Pier 5'), 140)

    def test_composite_only_fires_on_an_exact_full_string_hit(self):
        """"Pier 6 Plaza" is not "Pier 6": no exact composite, so the parent
        answers rather than a near-miss picking a pier by resemblance."""
        self.assertEqual(
            _id(_bbp_map(), 'Brooklyn Bridge Park', 'Pier 6 Plaza'), 140)

    def test_sibling_is_not_hijacked_by_a_bare_feature_name(self):
        """The reverse risk. The sublocation alone is deliberately NOT a search
        key, so a feature name that belongs to another venue cannot pull the
        event off its parent."""
        m = _make_locations_map(
            names=BBP_NAMES + [('Pier 6 at Some Other Park', 99999)],
            alternate_names=BBP_ALTS)
        # Composite wins, and it names the BBP pier, not the same-named sibling.
        self.assertEqual(_id(m, 'Brooklyn Bridge Park', 'Pier 6'), 10398)
        # With no composite row, the parent keeps its events.
        self.assertEqual(_id(m, 'Prospect Park', 'Pier 6'), None)

    def test_prospect_park_features(self):
        """The other two live instances found by the blast-radius sweep."""
        m = _make_locations_map(
            names=[('Prospect Park', 682),
                   ('Prospect Park Boathouse & Audubon Center', 60),
                   ('Prospect Park (Grand Army Plaza Entrance)', 683)],
            alternate_names=[('Prospect Park Audubon Center', 60),
                             ('Prospect Park GAP Entrance', 683)])
        self.assertEqual(_id(m, 'Prospect Park', 'Audubon Center'), 60)
        self.assertEqual(_id(m, 'Prospect Park', 'GAP Entrance'), 683)
        self.assertEqual(_id(m, 'Prospect Park'), 682)


class TestTwelveBrooklynBridgeParkNameForms(unittest.TestCase):
    """Landmark: every BBP name form must resolve to its own feature."""

    def test_each_primary_name_resolves_to_itself(self):
        m = _bbp_map()
        for name, lid in BBP_NAMES:
            with self.subTest(name=name):
                self.assertEqual(_id(m, name), lid)

    def test_each_alternate_name_resolves_to_its_feature(self):
        m = _bbp_map()
        for name, lid in BBP_ALTS:
            with self.subTest(name=name):
                self.assertEqual(_id(m, name), lid)


class TestBushTerminalPierSix(unittest.TestCase):
    """`Bush Terminal Pier 6` names Bush Terminal Piers Park (Sunset Park,
    loc 164), NOT Pier 6 at Brooklyn Bridge Park (loc 10398).

    It survives the numeric guard because the number is ONE-SIDED — the Bush
    Terminal rows carry no digits at all, so there is nothing to conflict with.
    """

    def _map(self):
        return _make_locations_map(
            names=[('Bush Terminal Piers Park', 164),
                   ('Pier 6 at Brooklyn Bridge Park', 10398),
                   ('Brooklyn Bridge Park', 140)],
            alternate_names=[('Bush Terminal Pier Park', 164),
                             ('Bush Terminal Park', 164),
                             ('Brooklyn Bridge Park Pier 6', 10398)],
            short_names=[('Bush Terminal Park', 164)])

    def test_resolves_to_bush_terminal(self):
        self.assertEqual(_id(self._map(), 'Bush Terminal Pier 6'), 164)

    def test_does_not_resolve_to_the_brooklyn_bridge_park_pier(self):
        self.assertNotEqual(_id(self._map(), 'Bush Terminal Pier 6'), 10398)


class TestNumericIdentifierIsNotATypo(unittest.TestCase):
    """A digit is an identifier, not a spelling. Different numbers, different
    venue — no matter how close the edit distance."""

    def test_pier_6_does_not_match_pier_66(self):
        """The reported bug: 7 NYRR Open Run rows pinned across the river."""
        m = _make_locations_map(
            names=[('Pier 66 at Hudson River Park', 4867)],
            alternate_names=[('Pier 66', 4867)])
        self.assertIsNone(_id(m, 'Pier 6'))

    def test_pier_66_itself_still_resolves(self):
        m = _make_locations_map(
            names=[('Pier 66 at Hudson River Park', 4867)],
            alternate_names=[('Pier 66', 4867)])
        self.assertEqual(_id(m, 'Pier 66'), 4867)
        self.assertEqual(_id(m, 'Pier 66 at Hudson River Park'), 4867)

    def test_pier_6_prefers_the_brooklyn_pier_over_the_manhattan_one(self):
        m = _make_locations_map(
            names=[('Pier 66 at Hudson River Park', 4867),
                   ('Pier 6 at Brooklyn Bridge Park', 10398)],
            alternate_names=[('Pier 66', 4867), ('Pier 6', 10398)])
        self.assertEqual(_id(m, 'Pier 6'), 10398)

    def test_sibling_piers_do_not_fuse(self):
        m = _make_locations_map(
            names=[('Pier 57', 663), ('Pier 17', 662)],
            alternate_names=[('Pier 57', 663), ('Pier 17', 662)])
        self.assertEqual(_id(m, 'Pier 17'), 662)
        self.assertEqual(_id(m, 'Pier 57'), 663)
        self.assertIsNone(_id(m, 'Pier 27'))

    def test_studio_number_is_not_a_typo(self):
        m = _make_locations_map(names=[('Studio 54', 1000)])
        self.assertIsNone(_id(m, 'Studio 5'))
        self.assertEqual(_id(m, 'Studio 54'), 1000)

    def test_community_board_number_is_not_a_typo(self):
        m = _make_locations_map(
            names=[('Manhattan Community Board 12', 2142)],
            alternate_names=[('Manhattan CB12', 2142)])
        self.assertIsNone(_id(m, 'Manhattan Community Board 1'))
        self.assertEqual(_id(m, 'Manhattan Community Board 12'), 2142)

    def test_public_school_number_is_not_a_typo(self):
        m = _make_locations_map(names=[('P.S. 155', 3663)])
        self.assertIsNone(_id(m, 'P.S. 15'))

    def test_prefix_score_branch_is_guarded_too(self):
        """The fuzzy tier has a second scoring branch: a key that PREFIXES the
        source at >= PREFIX_MATCH_COVERAGE is scored 0.9+ outright, no
        Levenshtein involved. "beach 9" covers 7/8 of "beach 97", so without the
        guard there the digit rule would be bypassed entirely."""
        m = _make_locations_map(short_names=[('Beach 9', 5001)])
        self.assertIsNone(_id(m, 'Beach 97'))


class TestNumericIdentityConflictHelper(unittest.TestCase):
    """The guard is deliberately narrow: it refuses DIVERGENT number sets only."""

    def test_different_numbers_conflict(self):
        self.assertTrue(_numeric_identity_conflict('pier 6', 'pier 66'))
        self.assertTrue(_numeric_identity_conflict('ps 15', 'ps 155'))
        self.assertTrue(_numeric_identity_conflict('beach 67', 'beach 97'))

    def test_same_number_does_not_conflict(self):
        self.assertFalse(_numeric_identity_conflict(
            'pier 6', 'pier 6 at brooklyn bridge park'))

    def test_a_one_sided_number_does_not_conflict(self):
        """"Bush Terminal Pier 6" vs "Bush Terminal Pier Park" — nothing to
        contradict, so the existing fuzzy behaviour is untouched."""
        self.assertFalse(_numeric_identity_conflict(
            'bush terminal pier 6', 'bush terminal pier park'))
        self.assertFalse(_numeric_identity_conflict('brooklyn bowl', 'brooklyn bowl'))

    def test_a_superset_does_not_conflict(self):
        """A source that adds a street number to a numbered venue still matches."""
        self.assertFalse(_numeric_identity_conflict(
            'pier 17 at 89 south street', 'pier 17'))

    def test_zero_padding_is_not_an_identity_difference(self):
        """P.S. 006 and PS 6 are the same school."""
        self.assertFalse(_numeric_identity_conflict('ps 006', 'ps 6'))

    def test_an_ordinal_suffix_is_not_an_identity_difference(self):
        """"Beach 67 Street" and "Beach 67th Street" are the same street."""
        self.assertFalse(_numeric_identity_conflict(
            'beach 67 street', 'beach 67th street'))
        self.assertTrue(_numeric_identity_conflict(
            'beach 67th street', 'beach 97th street'))

    def test_empty_names_do_not_conflict(self):
        self.assertFalse(_numeric_identity_conflict('', 'pier 6'))
        self.assertFalse(_numeric_identity_conflict('pier 6', ''))


if __name__ == '__main__':
    unittest.main()
