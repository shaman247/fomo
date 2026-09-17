"""A suppressed (hidden) event must never win the existing-event match.

`events.suppressed = 1` rows are dedupe losers: hidden from the map but still
loaded into the merger's matching index (1,946 of them on 2026-09-17). Before
this guard the first qualifying candidate won, so a suppressed twin could
capture fresh crawl_events — and because an exact name beat a partial one, it
did so *deterministically* when the hidden row's name was the exact string
("Ballet Storytime" vs the visible "Ballet Storytime with West Jersey Youth
Ballet", Hunterdon w5240). The visible canonical then lost all its sources and
was archived, and the series rendered nowhere.

`find_best_match` / `_safe_website_match` are closures inside
`merge_crawl_events`, so these tests rebuild them from the enclosing function's
code object with synthetic closure cells. That keeps the assertions on the real
matcher instead of a copy of it; if the closure's free variables change, the
rebuild fails loudly rather than silently testing nothing.
"""

import inspect
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import merger
from merger import normalize_name_for_dedup


def _cell(value):
    """A closure cell holding `value`."""
    return (lambda v: lambda: v)(value).__closure__[0]


def _nested_code(outer, name):
    for const in outer.__code__.co_consts:
        if isinstance(const, types.CodeType) and const.co_name == name:
            return const
    raise AssertionError(f'{name} is no longer a nested function of {outer.__name__}')


def _rebuild(name, freevars, argdefs=None):
    """Rebuild a closure of merge_crawl_events with the given free variables.

    Argument defaults live on the *function* object, not the code object, so
    they are restated here (and asserted below) rather than recovered.
    """
    code = _nested_code(merger.merge_crawl_events, name)
    missing = set(code.co_freevars) - set(freevars)
    assert not missing, f'{name} needs free variables not provided: {sorted(missing)}'
    closure = tuple(_cell(freevars[fv]) for fv in code.co_freevars)
    return types.FunctionType(code, merger.__dict__, name, argdefs, closure)


class _MatcherHarness:
    """Builds `find_best_match` / `_safe_website_match` over fake candidates."""

    def __init__(self, crawl_name, overlapping_ids, *, location_id=None,
                 strict_match=False, vetoed_ids=(), slots=None,
                 crawl_loc_norm='', crawl_loc_is_generic=True):
        self.crawl_name = crawl_name
        self.overlapping_ids = set(overlapping_ids)
        self.vetoed_ids = set(vetoed_ids)
        self.location_id = location_id
        self.strict_match = strict_match
        self.event_slots = slots or {}
        self.crawl_loc_norm = crawl_loc_norm
        self.crawl_loc_is_generic = crawl_loc_is_generic

    def _common_freevars(self):
        return {
            '_dates_overlap': lambda eid: eid in self.overlapping_ids,
            '_sibling_veto': lambda existing: existing['id'] in self.vetoed_ids,
            'crawl_event_slots': {('2026-09-20', '19:00')},
            'event_slots': self.event_slots,
            'location_id': self.location_id,
            'name': self.crawl_name,
            'norm_name': normalize_name_for_dedup(self.crawl_name),
            'strict_match': self.strict_match,
        }

    def find_best_match(self, candidates, **kwargs):
        # (require_location_id_match, allow_no_date_overlap) both default False
        # in merger.py; the signature check below fails if that ever changes.
        fn = _rebuild('find_best_match', self._common_freevars(),
                      argdefs=(False, False))
        assert fn.__code__.co_varnames[:3] == (
            'candidates', 'require_location_id_match', 'allow_no_date_overlap')
        return fn(candidates, **kwargs)

    def safe_website_match(self, candidates):
        freevars = dict(self._common_freevars())
        freevars.pop('location_id')
        freevars['crawl_loc_norm'] = self.crawl_loc_norm
        freevars['crawl_loc_is_generic'] = self.crawl_loc_is_generic
        freevars['generic_locs'] = {
            '', 'online', 'virtual', 'zoom', 'tba', 'tbd', 'in person',
            'various', 'multiple locations', 'not specified', 'na', 'n a'}
        fn = _rebuild('_safe_website_match', freevars)
        return fn(candidates)


def _candidate(event_id, name, suppressed=None, **extra):
    entry = {'id': event_id, 'name': name, 'website_id': 5240}
    if suppressed is not None:
        entry['suppressed'] = suppressed
    entry.update(extra)
    return entry


class TestIndexCarriesSuppressedFlag(unittest.TestCase):
    """_index_existing_event must stamp the flag onto every index entry."""

    def _index(self, suppressed=None):
        indexes = ({}, {}, {}, {})
        kwargs = {} if suppressed is None else {'suppressed': suppressed}
        merger._index_existing_event(
            indexes, 101, 'Ballet Storytime', 77, 40.7, -74.0,
            'Hunterdon Art Museum', 5240, **kwargs)
        return indexes

    def test_flag_reaches_all_four_indexes(self):
        by_loc_id, by_coords, by_location, by_website = self._index(suppressed=1)
        entries = [by_loc_id[77][0], by_coords[merger._coord_key(40.7, -74.0)][0],
                   by_location[normalize_name_for_dedup('Hunterdon Art Museum')][0],
                   by_website[5240][0]]
        for entry in entries:
            self.assertIs(entry['suppressed'], True)

    def test_default_is_unsuppressed(self):
        """Events the merge CREATES use the default and must stay visible."""
        by_loc_id, _, _, _ = self._index()
        self.assertIs(by_loc_id[77][0]['suppressed'], False)

    def test_loader_selects_and_forwards_the_column(self):
        source = inspect.getsource(merger.merge_crawl_events)
        self.assertIn('e.website_id, e.suppressed', source)
        self.assertIn('suppressed=bool(suppressed)', source)


class TestFindBestMatchPrefersVisible(unittest.TestCase):

    def test_unsuppressed_exact_wins_over_suppressed_exact_either_order(self):
        visible = _candidate(200, 'Ballet Storytime', suppressed=False)
        hidden = _candidate(201, 'Ballet Storytime', suppressed=True)
        harness = _MatcherHarness('Ballet Storytime', {200, 201})
        for candidates in ([hidden, visible], [visible, hidden]):
            with self.subTest(order=[c['id'] for c in candidates]):
                self.assertEqual(harness.find_best_match(candidates), 200)

    def test_unsuppressed_partial_beats_suppressed_exact(self):
        """The Hunterdon w5240 shape: exact-beats-partial must not reach a
        hidden row. The visible longer title is the canonical series."""
        hidden = _candidate(301, 'Ballet Storytime', suppressed=True)
        visible = _candidate(300, 'Ballet Storytime with West Jersey Youth Ballet',
                             suppressed=False)
        harness = _MatcherHarness('Ballet Storytime', {300, 301})
        for candidates in ([hidden, visible], [visible, hidden]):
            with self.subTest(order=[c['id'] for c in candidates]):
                self.assertEqual(harness.find_best_match(candidates), 300)

    def test_suppressed_only_candidate_is_still_returned(self):
        """No visible alternative — behaviour is unchanged, so a re-crawl still
        confirms the hidden row instead of creating a third duplicate."""
        hidden_exact = _candidate(401, 'Ballet Storytime', suppressed=True)
        harness = _MatcherHarness('Ballet Storytime', {401})
        self.assertEqual(harness.find_best_match([hidden_exact]), 401)

        hidden_partial = _candidate(
            402, 'Ballet Storytime with West Jersey Youth Ballet', suppressed=True)
        harness = _MatcherHarness('Ballet Storytime', {402})
        self.assertEqual(harness.find_best_match([hidden_partial]), 402)

    def test_entries_without_the_key_are_treated_as_visible(self):
        """Older/foreign entries (and anything built outside the indexer) must
        not be demoted just because the key is absent."""
        legacy = _candidate(500, 'Ballet Storytime')
        hidden = _candidate(501, 'Ballet Storytime', suppressed=True)
        harness = _MatcherHarness('Ballet Storytime', {500, 501})
        self.assertEqual(harness.find_best_match([hidden, legacy]), 500)
        self.assertEqual(harness.find_best_match([legacy]), 500)

    def test_no_overlap_exact_prefers_the_visible_twin(self):
        """allow_no_date_overlap tier (location_id path): a lapsed recurring
        program must re-attach to the visible row."""
        hidden = _candidate(601, 'Ballet Storytime', suppressed=True)
        visible = _candidate(600, 'Ballet Storytime', suppressed=False)
        harness = _MatcherHarness('Ballet Storytime', set())  # nothing overlaps
        for candidates in ([hidden, visible], [visible, hidden]):
            with self.subTest(order=[c['id'] for c in candidates]):
                self.assertEqual(
                    harness.find_best_match(candidates, allow_no_date_overlap=True), 600)
        self.assertEqual(
            harness.find_best_match([hidden], allow_no_date_overlap=True), 601)

    def test_visible_partial_with_overlap_still_beats_exact_no_overlap(self):
        """Pre-existing precedence (best_id before exact_no_overlap_id) is
        untouched by the suppression buckets."""
        overlapping_partial = _candidate(
            700, 'Ballet Storytime with West Jersey Youth Ballet', suppressed=False)
        lapsed_exact = _candidate(701, 'Ballet Storytime', suppressed=False)
        harness = _MatcherHarness('Ballet Storytime', {700})
        self.assertEqual(
            harness.find_best_match([lapsed_exact, overlapping_partial],
                                    allow_no_date_overlap=True), 700)

    def test_existing_guards_still_reject_suppressed_partials(self):
        """The sibling veto and the strict_match slot rule apply to suppressed
        partials exactly as before — a vetoed hidden row is not a fallback."""
        hidden_partial = _candidate(
            800, 'Ballet Storytime with West Jersey Youth Ballet', suppressed=True)
        vetoed = _MatcherHarness('Ballet Storytime', {800}, vetoed_ids={800})
        self.assertIsNone(vetoed.find_best_match([hidden_partial]))

        strict = _MatcherHarness('Ballet Storytime', {800}, strict_match=True,
                                 slots={800: set()})
        self.assertIsNone(strict.find_best_match([hidden_partial]))

    def test_location_id_guard_still_applies_to_suppressed_rows(self):
        hidden = _candidate(900, 'Ballet Storytime', suppressed=True, location_id=99)
        harness = _MatcherHarness('Ballet Storytime', {900}, location_id=77)
        self.assertIsNone(
            harness.find_best_match([hidden], require_location_id_match=True))


class TestSafeWebsiteMatchPrefersVisible(unittest.TestCase):

    def _candidates(self, *entries):
        return list(entries)

    def test_visible_wins_regardless_of_order(self):
        hidden = _candidate(1001, 'Ballet Storytime', suppressed=True,
                            location_name='Online')
        visible = _candidate(1000, 'Ballet Storytime', suppressed=False,
                             location_name='Online')
        harness = _MatcherHarness('Ballet Storytime', {1000, 1001})
        for candidates in ([hidden, visible], [visible, hidden]):
            with self.subTest(order=[c['id'] for c in candidates]):
                self.assertEqual(harness.safe_website_match(candidates), 1000)

    def test_visible_partial_beats_suppressed_exact(self):
        hidden = _candidate(1101, 'Ballet Storytime', suppressed=True,
                            location_name='Online')
        visible = _candidate(1100, 'Ballet Storytime with West Jersey Youth Ballet',
                             suppressed=False, location_name='Online')
        harness = _MatcherHarness('Ballet Storytime', {1100, 1101})
        self.assertEqual(harness.safe_website_match([hidden, visible]), 1100)

    def test_suppressed_only_candidate_is_still_returned(self):
        hidden = _candidate(1201, 'Ballet Storytime', suppressed=True,
                            location_name='Online')
        harness = _MatcherHarness('Ballet Storytime', {1201})
        self.assertEqual(harness.safe_website_match([hidden]), 1201)

    def test_entries_without_the_key_are_treated_as_visible(self):
        legacy = _candidate(1300, 'Ballet Storytime', location_name='Online')
        hidden = _candidate(1301, 'Ballet Storytime', suppressed=True,
                            location_name='Online')
        harness = _MatcherHarness('Ballet Storytime', {1300, 1301})
        self.assertEqual(harness.safe_website_match([hidden, legacy]), 1300)

    def test_location_guard_still_rejects_distinct_venues(self):
        hidden = _candidate(1401, 'Ballet Storytime', suppressed=True,
                            location_name='South Gallery')
        harness = _MatcherHarness('Ballet Storytime', {1401},
                                  crawl_loc_norm='north gallery',
                                  crawl_loc_is_generic=False)
        self.assertIsNone(harness.safe_website_match([hidden]))


if __name__ == '__main__':
    unittest.main()
