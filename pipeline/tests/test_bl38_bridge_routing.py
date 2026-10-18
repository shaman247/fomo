"""BL38: a reviewed cross-venue merge routes the loser's NEW listings too.

`reviewed_event_identity` matches a location bridge only for the URL and
date slots the dedupe decision reviewed. nyc.gov (w1) publishes a fresh
`id=` URL for every occurrence, so its 2026-10-16 listing of "Bodyweight
Circuit Training" (ce 1587376, East River Waterfront Esplanade 1419) missed
the bridge, landed on the suppressed loser 206764, and redirect routing
(BL14) refused the survivor 209115 because it sits at Pier 35 (3499).

`redirect_route_target` now follows a direct location bridge when the source
is from a website the bridge was recorded for, names the loser's venue
exactly, the loser is still there and the survivor still sits at the venue
the decision kept. Everything else about the cross-venue refusal stands.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import merger
import test_bl14_redirect_routing as bl14
from test_bl14_redirect_routing import CE, DUP, DUP_NAME, SURVIVOR, SURVIVOR_NAME, VENUE

OTHER_VENUE = 9999
WEBSITE = 3  # the fake merge's source website


def bridge(website=WEBSITE, loser=VENUE, survivor=OTHER_VENUE, policy='location_bridge_v1',
           name='craft circle'):
    return json.dumps([{'website_id': website, 'url': 'https://example.org/e/1',
                        'name': name, 'location_id': loser,
                        'slots': [['2026-10-03', '10am', '2026-10-03']],
                        'policy': policy, 'survivor_location_id': survivor}])


class BridgeRoutingMergeTests(unittest.TestCase):
    """Drives the BL14 fake merge; the survivor sits at OTHER_VENUE."""

    def run_merge(self, **kwargs):
        states = {DUP: (1, 0, VENUE, DUP_NAME)}
        states.update(kwargs.pop('survivor_state', None) or {})
        return bl14.RedirectRoutingMergeTests('test_cycle_declines').run_merge(
            survivor_state=states, **kwargs)

    def assertStaysOnDuplicate(self, **kwargs):
        links, _, _ = self.run_merge(**kwargs)
        self.assertEqual(links, [(DUP, CE)])

    def test_new_listing_at_the_losers_venue_follows_the_bridge(self):
        links, relocations, _ = self.run_merge(redirects=((DUP, SURVIVOR, bridge()),),
                                               survivor_venue=OTHER_VENUE)
        self.assertEqual(links, [(SURVIVOR, CE)])
        self.assertEqual(relocations, [], 'the survivor keeps the venue the review chose')

    def test_without_a_bridge_scope_the_cross_venue_refusal_stands(self):
        for payload in (None, '[]', 'not json', bridge(policy=None),
                        bridge(website=77, name='knitting night'),
                        bridge(loser=401), bridge(survivor=8888)):
            with self.subTest(payload=payload):
                self.assertStaysOnDuplicate(redirects=((DUP, SURVIVOR, payload),),
                                            survivor_venue=OTHER_VENUE)

    def test_dismissed_pair_still_binds(self):
        self.assertStaysOnDuplicate(redirects=((DUP, SURVIVOR, bridge()),),
                                    survivor_venue=OTHER_VENUE, dismissed=[(SURVIVOR, DUP)])

    def test_suppressed_survivor_still_declines(self):
        self.assertStaysOnDuplicate(
            redirects=((DUP, SURVIVOR, bridge()),), survivor_venue=OTHER_VENUE,
            survivor_state={SURVIVOR: (1, 0, OTHER_VENUE, SURVIVOR_NAME)})


class BridgeRouteTargetTests(unittest.TestCase):

    def route(self, *, redirects=None, location_id=VENUE, website_id=WEBSITE, bridges=None,
              duplicate_loc=VENUE, survivor_loc=OTHER_VENUE, name='Craft Circle'):
        states = {DUP: {'suppressed': True, 'archived': False, 'location_id': duplicate_loc},
                  SURVIVOR: {'suppressed': False, 'archived': False,
                             'location_id': survivor_loc}}
        return merger.redirect_route_target(
            DUP, redirects or {DUP: SURVIVOR}, states.get, set(), set(), location_id,
            lambda a, b: a == b, website_id=website_id, name=name,
            location_bridges=bridges if bridges is not None
            else {DUP: {(VENUE, OTHER_VENUE): ({WEBSITE}, {'craft circle'})}})

    def test_direct_bridge_routes(self):
        self.assertEqual(self.route(), SURVIVOR)

    def test_bridge_needs_the_losers_venue_and_the_survivors_venue(self):
        self.assertIsNone(self.route(location_id=402))
        self.assertIsNone(self.route(duplicate_loc=402))
        self.assertIsNone(self.route(survivor_loc=8888))
        self.assertIsNone(self.route(website_id=77, name='Knitting Night'))
        self.assertIsNone(self.route(bridges={}))

    def test_another_publisher_with_a_reviewed_title_follows_the_bridge(self):
        # nyc.gov (w1) lists the NYC Parks (w2) class the review merged.
        self.assertEqual(self.route(website_id=77, name='CRAFT  circle'), SURVIVOR)
        self.assertIsNone(self.route(website_id=77, name='Craft Circle Social'))

    def test_a_chain_never_crosses_venues(self):
        states = {DUP: {'location_id': VENUE, 'suppressed': True},
                  5001: {'location_id': VENUE, 'suppressed': True},
                  SURVIVOR: {'suppressed': False, 'archived': False, 'location_id': OTHER_VENUE}}
        self.assertIsNone(merger.redirect_route_target(
            DUP, {DUP: 5001, 5001: SURVIVOR}, states.get, set(), set(), VENUE,
            lambda a, b: a == b, website_id=WEBSITE,
            location_bridges={DUP: {(VENUE, OTHER_VENUE): ({WEBSITE}, set())},
                              5001: {(VENUE, OTHER_VENUE): ({WEBSITE}, set())}}))

    def test_same_venue_routing_is_unchanged(self):
        self.assertEqual(self.route(survivor_loc=VENUE, bridges={}), SURVIVOR)

    def test_bridge_index_reads_only_location_bridge_scopes(self):
        rows = [(1, bridge()), (2, bridge(policy=None)), (3, None), (4, '{bad'),
                (5, json.dumps([{'policy': 'location_bridge_v1', 'website_id': 3}]))]
        self.assertEqual(merger.redirect_location_bridges(rows),
                         {1: {(VENUE, OTHER_VENUE): ({WEBSITE}, {'craft circle'})}})


if __name__ == '__main__':
    unittest.main()
