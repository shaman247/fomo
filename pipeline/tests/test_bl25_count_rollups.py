"""BL25 (2026-10-16 watch): roll-up listings whose leading count changes.

NYC-DSA w591 prints one row per canvass date, on a date-filter URL
(`canvass.socialists.nyc/?date=[...]`), titled by how many canvasses sit behind
it. When the count changed the title changed, and the URL tiers forked a new
event: "1 Candidate Canvass (2026-10-22)" 268913 -> "2 Candidate Canvasses
(2026-10-22)" 291358 and "1 Candidate Canvass (2026-10-31)" 273944 -> "3
Candidate Canvasses" 291372 (merged by hand 2026-10-16). The 10-15 rows came
back untimed, so the retitle rule (which demands the exact date + time slot)
never fired either.

The generic rule: same website + the same event-specific URL + a shared date,
and titles that differ only by a leading count (plus plural endings and a
trailing date suffix), count as the same name in both URL tiers.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger

WEBSITE = 591
OFFICE = 1940
GREENMARKET = 802
COORDS = {OFFICE: (40.7506, -73.9935), GREENMARKET: (40.7466, -73.9196)}  # ~6 km apart
URL_22 = 'https://canvass.socialists.nyc/?date=%5B%222026-10-22..2026-10-22%22%5D'
URL_31 = 'https://canvass.socialists.nyc/?date=%5B%222026-10-31..2026-10-31%22%5D'


def event(event_id, name, location_id, slots, suppressed=False):
    return {'id': event_id, 'name': name, 'location_id': location_id,
            'slots': set(slots), 'suppressed': suppressed}


def tiers(name, url, location_id, slots, events, *, fallback=False, listing=False,
          capture=()):
    key = (WEBSITE, merger.normalize_url_for_identity(url))
    names = {merger.normalize_name_for_dedup(e['name']) for e in events}
    by_url, counts = {key: list(events)}, {key: len(names)}
    count_free = merger.url_count_free_name_counts({key: names})
    listing_keys = {key} if listing else set()
    strict = merger._match_by_url_identity(
        name, url, WEBSITE, location_id, set(slots), by_url, counts, listing_keys, COORDS,
        count_free_name_counts=count_free)
    relaxed = merger._match_by_url_identity_relaxed(
        name, url, WEBSITE, location_id, set(slots), by_url, counts, listing_keys, COORDS,
        incoming_is_fallback=fallback,
        capture_names={merger.normalize_name_for_dedup(n) for n in capture},
        count_free_name_counts=count_free)
    return strict, relaxed


class LeadingCountKeyTests(unittest.TestCase):
    def test_count_variants(self):
        for a, b in [
            ('2 Candidate Canvasses (2026-10-22)', '1 Candidate Canvass (2026-10-22)'),
            ('3 Candidate Canvasses', '1 Candidate Canvass (2026-10-31)'),
            ('4 Candidate Canvasses (2026-10-17)', '2 Candidate Canvasses (2026-10-17)'),
            ('3 Candidate Canvasses (2026-10-04)', '3 Candidate Canvasses'),
            ('12 Phonebanks', 'Phonebank'),
        ]:
            with self.subTest(a=a, b=b):
                self.assertTrue(merger.leading_count_variants(a, b))

    def test_not_count_variants(self):
        for a, b in [
            ('Candidate Canvass', 'Candidate Canvass (2026-10-31)'),  # no count at all
            ('2 Candidate Canvasses', '2 Tenant Canvasses'),
            ('Part 1', 'Part 2'),
            ('Set 1: Trio', 'Set 2: Trio'),
            ('1 Candidate Canvass', ''),
        ]:
            with self.subTest(a=a, b=b):
                self.assertFalse(merger.leading_count_variants(a, b))

    def test_url_count_free_name_counts_folds_counts(self):
        key = (WEBSITE, 'u')
        names = {merger.normalize_name_for_dedup(n) for n in (
            '1 Candidate Canvass (2026-10-17)', '2 Candidate Canvasses (2026-10-17)',
            '4 Candidate Canvasses (2026-10-17)')}
        self.assertEqual(merger.url_count_free_name_counts({key: names}), {key: 1})


class RollupUrlTierTests(unittest.TestCase):
    def test_untimed_retitle_on_the_same_venue_matches(self):
        """268913 -> 291358: the 10-15 row came back untimed."""
        old = event(268913, '1 Candidate Canvass (2026-10-22)', OFFICE, [('2026-10-22', '6pm')])
        self.assertEqual(tiers('2 Candidate Canvasses (2026-10-22)', URL_22, OFFICE,
                               [('2026-10-22', '')], [old], fallback=True),
                         (None, 268913))

    def test_untimed_retitle_on_the_organizer_fallback_reaches_the_real_venue(self):
        """273944 -> 291372: the old row sits at Sunnyside Greenmarket, 6 km away."""
        old = event(273944, '1 Candidate Canvass (2026-10-31)', GREENMARKET,
                    [('2026-10-31', '11am')])
        self.assertEqual(tiers('3 Candidate Canvasses', URL_31, OFFICE, [('2026-10-31', '')],
                               [old], fallback=True), (None, 273944))
        # Not on the fallback: the venues really differ, so nothing matches.
        self.assertEqual(tiers('3 Candidate Canvasses', URL_31, OFFICE, [('2026-10-31', '')],
                               [old]), (None, None))

    def test_timed_retitle_matches_in_the_strict_tier(self):
        old = event(268913, '1 Candidate Canvass (2026-10-22)', OFFICE, [('2026-10-22', '6pm')])
        self.assertEqual(tiers('2 Candidate Canvasses (2026-10-22)', URL_22, OFFICE,
                               [('2026-10-22', '6pm')], [old])[0], 268913)

    def test_repeatedly_retitled_url_stays_an_event_url(self):
        """Three count variants on one URL used to exceed the 2-name limit."""
        url = 'https://canvass.socialists.nyc/?date=%5B%222026-10-17..2026-10-17%22%5D'
        rows = [event(268896, '1 Candidate Canvass (2026-10-17)', OFFICE, [('2026-10-17', '10am')],
                      suppressed=True),
                event(273928, '2 Candidate Canvasses (2026-10-17)', OFFICE, [('2026-10-17', '10am')])]
        self.assertEqual(tiers('4 Candidate Canvasses (2026-10-17)', url, OFFICE,
                               [('2026-10-17', '10am')], rows + [
                                   event(273999, '3 Candidate Canvasses (2026-10-17)', OFFICE,
                                         [('2026-10-17', '10am')], suppressed=True)])[0],
                         273928)

    def test_another_date_never_matches(self):
        old = event(268913, '1 Candidate Canvass (2026-10-22)', OFFICE, [('2026-10-22', '6pm')])
        self.assertEqual(tiers('2 Candidate Canvasses (2026-10-23)', URL_22, OFFICE,
                               [('2026-10-23', '')], [old], fallback=True), (None, None))

    def test_listing_url_is_never_identity(self):
        old = event(268913, '1 Candidate Canvass (2026-10-22)', OFFICE, [('2026-10-22', '6pm')])
        self.assertEqual(tiers('2 Candidate Canvasses (2026-10-22)', URL_22, OFFICE,
                               [('2026-10-22', '6pm')], [old], listing=True), (None, None))

    def test_a_different_program_on_the_url_is_not_a_count_variant(self):
        old = event(1, '1 Candidate Canvass (2026-10-22)', OFFICE, [('2026-10-22', '6pm')])
        self.assertEqual(tiers('2 Tenant Canvasses (2026-10-22)', URL_22, OFFICE,
                               [('2026-10-22', '')], [old], fallback=True), (None, None))

    def test_two_visible_count_variants_are_ambiguous_for_the_relaxed_tier(self):
        a = event(1, '1 Candidate Canvass (2026-10-22)', OFFICE, [('2026-10-22', '6pm')])
        b = event(2, '2 Candidate Canvasses (2026-10-22)', OFFICE, [('2026-10-22', '7pm')])
        self.assertEqual(tiers('3 Candidate Canvasses (2026-10-22)', URL_22, OFFICE,
                               [('2026-10-22', '')], [a, b], fallback=True), (None, None))

    def test_without_count_free_counts_the_strict_tier_is_unchanged(self):
        old = event(268913, '1 Candidate Canvass (2026-10-22)', OFFICE, [('2026-10-22', '6pm')])
        key = (WEBSITE, merger.normalize_url_for_identity(URL_22))
        self.assertIsNone(merger._match_by_url_identity(
            '2 Candidate Canvasses (2026-10-22)', URL_22, WEBSITE, OFFICE,
            {('2026-10-22', '6pm')}, {key: [old]}, {key: 1}, set(), COORDS))


if __name__ == '__main__':
    unittest.main()
