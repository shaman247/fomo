"""Tests for the area-qualifier guard on collapsed neighborhood names.

`_normalize_location_name` strips a trailing borough/city qualifier, which is
what lets a source that only said "Midtown" reach the "Midtown Manhattan"
geotag. The collapse is lossy on BOTH sides, though, so it also fuses
qualifiers that name genuinely different places:

    "Downtown Brooklyn"  -> "downtown"
    "Downtown NYC"       -> "downtown"
    "Downtown Manhattan" -> "downtown"
    "Downtown New York"  -> "downtown"

Only one location owns the bare key, so every one of those strings landed on
the Downtown Brooklyn geotag — Painting Lounge's Williamsburg/Midtown painting
classes (e207874), AIA's "Walking Tour: Downtown New York Architecture in 1776"
(e191723) and "The Rise of the Skyscraper in Downtown New York" (e200070), and
NY Adventure Club's Downtown Manhattan newspaper tour (e190852).

The prefix/fuzzy tier cannot use the brand-family guard to reject these — see
the note at that tier, where adding it un-pinned 2,971 correctly-matched rows,
because by then a spelled-out branch is indistinguishable from a bare brand.
So `_area_qualifier_conflict` restores the discarded bit instead: it fires ONLY
when both sides carried a qualifier and the two name different areas.

A/B over all 272,768 distinct crawl_event (location_name, sublocation,
website_id, name) quads, 2026-08-20 — 50 quads / 117 rows change, every one a
mis-pin, and nothing correct is lost:

    repinned  41 rows  MAS's "Downtown Brooklyn" off Lower Manhattan (36, a
                       LATENT break — its curated per-website "Downtown
                       Manhattan" alias also answers to the collapsed key), and
                       "St. Joseph's University (Brooklyn)" off the Long Island
                       campus (5)
    unpinned  76 rows  Downtown Manhattan/New York/NYC -> Downtown Brooklyn
                       (23); Central Brooklyn + Central Manhattan -> Commonpoint
                       Queens in Forest Hills (22); Commonpoint Queens ->
                       Commonpoint Bronx (10); Pregones (Bronx) -> Pregones
                       Manhattan (8); NYU NYC -> NYU Brooklyn (4); and the TD
                       Five Boro Bike Tour (1), whose "Lower Manhattan to Staten
                       Island" names two boroughs and keeps neither

Two supporting changes fell out of the measurement and are tested here too:
the guard also runs on the website-scoped tier (Step 1) — the only thing
curation cannot speak for is a key it never wrote — and the prefix/fuzzy tier
rejects a conflicting candidate DURING scoring rather than only at the end, so
the runner-up still gets its turn.

Rejected on measurement: giving Lower Manhattan global "Downtown Manhattan" /
"Downtown NYC" aliases to re-home the unpinned rows. That puts Lower Manhattan
on the bare "downtown" key, where it outranks Downtown Brooklyn for any source
whose borough is not in trailing position — it moved Bang on a Can's Long Play
Festival ("Downtown Brooklyn", sublocation "BAM, Roulette, BRIC, …") to
Manhattan, 11 rows. The unpinned rows are better surfaced by
/fix-unmapped-events than answered by a key that means two places.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import (
    _area_qualifier_class,
    _area_qualifier_conflict,
    _normalize_location_name,
    _normalize_location_name_parts,
)

BROOKLYN = {'name': 'Downtown Brooklyn', 'address': 'Downtown Brooklyn, NY'}
MIDTOWN = {'name': 'Midtown Manhattan', 'address': 'Midtown Manhattan, New York, NY, USA'}


class TestNormalizerReportsWhatItStripped(unittest.TestCase):
    """The normalized string is unchanged; the second element is new."""

    def test_borough_qualifier_is_reported(self):
        self.assertEqual(_normalize_location_name_parts('Downtown Brooklyn'),
                         ('downtown', 'brooklyn'))

    def test_city_qualifier_is_reported(self):
        self.assertEqual(_normalize_location_name_parts('Downtown NYC'),
                         ('downtown', 'nyc'))

    def test_new_york_is_consumed_by_the_state_branch_but_still_reported(self):
        """' new york' is both a state suffix and the city's own name."""
        self.assertEqual(_normalize_location_name_parts('Downtown New York'),
                         ('downtown', 'new york'))

    def test_state_only_suffix_names_no_area(self):
        self.assertEqual(_normalize_location_name_parts('Brooklyn Museum NY'),
                         ('brooklyn museum', None))

    def test_innermost_qualifier_wins(self):
        self.assertEqual(_normalize_location_name_parts('Downtown Brooklyn New York'),
                         ('downtown', 'brooklyn'))

    def test_no_qualifier_reports_none(self):
        self.assertEqual(_normalize_location_name_parts('Midtown'), ('midtown', None))
        self.assertEqual(_normalize_location_name_parts('Downtown Bay Shore'),
                         ('downtown bay shore', None))

    def test_normalized_half_is_byte_identical_to_the_old_api(self):
        for raw in ('Downtown Brooklyn', 'Downtown NYC', 'Café Erzulie, Brooklyn',
                    'The Conference House', 'Midtown', 'St.Albans Library',
                    'Virtual', 'Gallery Brooklyn', 'Elsewhere - Brooklyn'):
            self.assertEqual(_normalize_location_name(raw),
                             _normalize_location_name_parts(raw)[0], raw)


class TestQualifierClasses(unittest.TestCase):
    def test_the_bronx_and_bronx_are_one_place(self):
        self.assertEqual(_area_qualifier_class('the bronx'), _area_qualifier_class('bronx'))

    def test_city_spellings_collapse_together(self):
        city = _area_qualifier_class('nyc')
        self.assertEqual(_area_qualifier_class('new york'), city)
        self.assertEqual(_area_qualifier_class('new york city'), city)

    def test_boroughs_stay_distinct(self):
        self.assertNotEqual(_area_qualifier_class('brooklyn'), _area_qualifier_class('queens'))
        self.assertNotEqual(_area_qualifier_class('brooklyn'), _area_qualifier_class('nyc'))

    def test_absent_qualifier_has_no_class(self):
        self.assertIsNone(_area_qualifier_class(None))
        self.assertIsNone(_area_qualifier_class(''))


class TestConflictFires(unittest.TestCase):
    """The reported mis-pins, each against the geotag that captured them."""

    def test_downtown_nyc_is_not_downtown_brooklyn(self):
        self.assertTrue(_area_qualifier_conflict('Downtown NYC', BROOKLYN))

    def test_downtown_manhattan_is_not_downtown_brooklyn(self):
        self.assertTrue(_area_qualifier_conflict('Downtown Manhattan', BROOKLYN))

    def test_downtown_new_york_is_not_downtown_brooklyn(self):
        self.assertTrue(_area_qualifier_conflict('Downtown New York', BROOKLYN))

    def test_conflict_is_detected_in_any_comma_segment(self):
        self.assertTrue(_area_qualifier_conflict('Some Room, Downtown Manhattan', BROOKLYN))


class TestCityWideCandidateAcceptsAnyBorough(unittest.TestCase):
    """A row curated only as "<Name> New York" claims the whole city.

    Measured: without this, four venues lost their pin because a global alias
    happened to spell the city rather than the borough — The Meadows (loc 869,
    17 Meadow St, Brooklyn, aliased "The Meadows New York"), Success Garden
    (3680, East New York — where the NEIGHBORHOOD name ends in "New York"),
    Fabrik Tribeca (2074, aliased "Fabrik NYC") and Asia Society (51).
    """

    MEADOWS = {'id': 869, 'name': 'The Meadows'}          # alias: The Meadows New York
    CITY_CLASSES = {869: {'\x00city'}}

    def test_borough_source_matches_city_wide_row(self):
        self.assertFalse(_area_qualifier_conflict(
            'The Meadows Brooklyn', self.MEADOWS, self.CITY_CLASSES))

    def test_neighborhood_ending_in_new_york_is_not_a_state_tail(self):
        self.assertFalse(_area_qualifier_conflict(
            'Success Garden - East New York Brooklyn', self.MEADOWS, self.CITY_CLASSES))

    def test_the_reverse_is_not_symmetric(self):
        """A vague source must not claim a row named for one specific borough."""
        self.assertTrue(_area_qualifier_conflict('Downtown NYC', BROOKLYN))


class TestAddressSegmentsAreNotQualifiers(unittest.TestCase):
    """A segment with a house number is a postal tail, not a venue qualifier.

    Loc 3497 is "Manhattan Meditation Center - Brahma Kumaris" at 306 5th Ave.
    Its own source string is "306 5th Ave., 2nd floor (between 31st & 32nd
    Streets) New York, New York 10001" — the parenthetical defeats the comma
    split, so the "… Streets) New York" segment looked like a qualifier.
    """

    # The real row claims 'manhattan' via its short_name "Brahma Kumaris
    # Manhattan"; its primary name carries no TRAILING qualifier, so the class
    # is supplied the way build_locations_map supplies it.
    ROW = {'id': 3497, 'name': 'Manhattan Meditation Center - Brahma Kumaris'}
    CLASSES = {3497: {'manhattan'}}

    def test_numbered_address_segment_is_ignored(self):
        self.assertFalse(_area_qualifier_conflict(
            '306 5th Ave., 2nd floor (between 31st & 32nd Streets) New York, New York 10001',
            self.ROW, self.CLASSES))

    def test_plain_name_segment_still_counts(self):
        self.assertTrue(_area_qualifier_conflict(
            'Some Room, Downtown Brooklyn', self.ROW, self.CLASSES))


class TestConflictStaysQuiet(unittest.TestCase):
    """Everything the collapse is FOR must keep resolving."""

    def test_bare_short_form_still_resolves(self):
        """"Downtown"/"Midtown" name no borough, so they are not in conflict."""
        self.assertFalse(_area_qualifier_conflict('Downtown', BROOKLYN))
        self.assertFalse(_area_qualifier_conflict('Midtown', MIDTOWN))

    def test_agreeing_qualifiers_are_not_a_conflict(self):
        self.assertFalse(_area_qualifier_conflict('Downtown Brooklyn', BROOKLYN))
        self.assertFalse(_area_qualifier_conflict('Midtown Manhattan', MIDTOWN))

    def test_candidate_without_a_qualifier_is_never_rejected(self):
        """Most locations aren't "<Name> <Borough>"; the guard must not touch them."""
        self.assertFalse(_area_qualifier_conflict(
            'Prospect Park Brooklyn', {'name': 'Prospect Park'}))

    def test_address_tail_naming_the_city_is_not_a_qualifier(self):
        """"…, New York" is an address segment, not "<Name> New York"."""
        self.assertFalse(_area_qualifier_conflict(
            'The Roxy Hotel, Cellar Level, 2 6th Ave, New York', BROOKLYN))

    def test_missing_candidate_is_safe(self):
        self.assertFalse(_area_qualifier_conflict('Downtown NYC', None))
        self.assertFalse(_area_qualifier_conflict('', BROOKLYN))


if __name__ == '__main__':
    unittest.main()
