import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from audit_venue_memberships import project_graph, project_memberships, audit_other_memberships


def venue(name, parents=()):
    return {'name': 'venue:' + name, 'scope': 'venue', 'parents': ['venue:' + p for p in parents]}


class VenueMembershipReviewTests(unittest.TestCase):
    def test_activity_parent_preserves_outdoor_and_community_paths(self):
        tags = [{'name': 'Art', 'scope': 'event', 'parents': []},
                venue('Other'), venue('Gym'), venue('Outdoor'), venue('Park', ['Outdoor']),
                venue('Community Center'), venue('Recreation Center', ['Community Center']),
                venue('Indoor Skydiving', ['Other'])]
        policy = {'promote': [{'name': 'Fitness & Recreation', 'emoji': '🏃'},
                              {'name': 'Skatepark', 'emoji': '🛹'}],
                  'parents': {'Gym': ['Fitness & Recreation'], 'Skatepark': ['Fitness & Recreation'],
                              'Indoor Skydiving': ['Fitness & Recreation'],
                              'Recreation Center': ['Community Center', 'Fitness & Recreation']}}
        cfg = {'frontend': {'filter_roots': {'tag': ['Art'], 'venue': ['Other', 'Outdoor', 'Community Center', 'Fitness & Recreation']}}}
        graph = project_graph(tags, policy, cfg)
        before = {(1, 'Indoor Skydiving'), (1, 'Other'), (2, 'Skatepark'), (2, 'Park'),
                  (3, 'Skatepark'), (3, 'Other'), (4, 'Recreation Center')}
        result = project_memberships(before, graph,
            [{'location_id': 1, 'remove': ['Other']}, {'location_id': 3, 'remove': ['Other']}], {1,2,3,4})
        self.assertTrue(all((lid, 'Fitness & Recreation') in result for lid in range(1,5)))
        self.assertIn((2, 'Outdoor'), result)
        self.assertNotIn((3, 'Outdoor'), result)
        self.assertIn((4, 'Community Center'), result)
        self.assertNotIn((1, 'Other'), result)

    def test_other_audit_distinguishes_reviewed_children_from_redundant_assignments(self):
        graph = [venue('Other'), venue('Indoor Skydiving', ['Other']), venue('Shop'),
                 venue('Neighborhood'), venue('Manhattan', ['Neighborhood'])]
        memberships = {(1, 'Other'), (1, 'Indoor Skydiving'), (1, 'Manhattan'),
                       (2, 'Other'), (2, 'Shop'), (3, 'Other')}
        policy = {'tag': 'Other', 'retain': [{'location_id': 1}, {'location_id': 2}]}
        self.assertEqual(audit_other_memberships(memberships, graph, policy), ({3}, {2}))

    def test_retirement_reparents_children_without_demoting_same_name_event(self):
        tags = [{'name': 'Venue', 'scope': 'event', 'parents': []},
                venue('Venue'), venue('Event Space'), venue('Warehouse'),
                venue('Nightclub', ['Event Space']), venue('Ballroom', ['Event Space'])]
        policy = {'promote': [{'name': 'Event Hall', 'emoji': '🏛️'}],
                  'retire': ['Venue', 'Event Space', 'Warehouse'],
                  'parents': {'Nightclub': [], 'Ballroom': ['Event Hall']}}
        cfg = {'frontend': {'filter_roots': {'tag': ['Venue'], 'venue': ['Event Hall', 'Nightclub']}}}
        result = {t['name']: t for t in project_graph(tags, policy, cfg)}
        self.assertIn('Venue', result)
        self.assertNotIn('venue:Venue', result)
        self.assertEqual(result['venue:Ballroom']['parents'], ['venue:Event Hall'])
        self.assertEqual(result['venue:Nightclub']['parents'], [])

    def test_review_preserves_keywords_and_does_not_expand_geography_or_topics(self):
        graph = [venue('Arts'), venue('Music Venue', ['Arts']),
                 venue('Neighborhood'), venue('Borough', ['Neighborhood']), venue('Street', ['Borough']),
                 {'name': 'Jazz', 'scope': 'event', 'parents': []}]
        before = {(1, 'Warehouse'), (1, 'Jazz'), (1, 'Street'), (2, 'Music Venue')}
        reviews = [{'location_id': 1, 'add': ['Music Venue']}]
        after = project_memberships(before, graph, reviews, {1})
        self.assertEqual(after - before, {(1, 'Music Venue'), (1, 'Arts')})
        self.assertTrue(before <= after)
        self.assertEqual(project_memberships(after, graph, reviews, {1}), after)

    def test_generic_keyword_does_not_automatically_mean_event_hall_or_other(self):
        graph = [venue('Event Hall'), venue('Other')]
        before = {(1, 'Event Space'), (2, 'Venue'), (3, 'Warehouse')}
        self.assertEqual(project_memberships(before, graph, [], {1,2,3}), before)

    def test_retained_child_prevents_removing_required_ancestor(self):
        graph = [venue('Studio'), venue('Dance Studio', ['Studio'])]
        with self.assertRaisesRegex(ValueError, 'retained child'):
            project_memberships({(1, 'Dance Studio'), (1, 'Studio')}, graph,
                                [{'location_id': 1, 'remove': ['Studio']}], {1})

    def test_review_cannot_promote_event_topic_into_venue_membership(self):
        graph = [venue('Studio'), {'name': 'Jazz', 'scope': 'event', 'parents': []}]
        with self.assertRaisesRegex(ValueError, 'curated venue identity'):
            project_memberships(set(), graph, [{'location_id': 1, 'add': ['Jazz']}], {1})


if __name__ == '__main__':
    unittest.main()
