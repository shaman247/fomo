import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import audit_venue_taxonomy as audit


class VenueTaxonomyTests(unittest.TestCase):
    def setUp(self):
        self.tags = {n: {'id': i, 'type': 'tag'} for i, n in enumerate(
            ['Bar', 'Cocktail Bar', 'Nightlife', 'Music Venue', 'Concert Hall', 'Performance Space'], 1)}

    def test_reverses_wrong_parent_without_changing_unreviewed_edges(self):
        before = {(3, 2), (5, 4), (1, 3)}
        desired = {'Cocktail Bar': ['Bar'], 'Music Venue': ['Performance Space'], 'Concert Hall': ['Music Venue']}
        result = audit.parent_plan(self.tags, before, desired)
        self.assertEqual(result, {(1, 2), (6, 4), (4, 5), (1, 3)})
        self.assertEqual(audit.parent_plan(self.tags, result, desired), result)

    def test_rejects_cycles_and_unreviewed_noncurated_identities(self):
        with self.assertRaises(ValueError):
            audit.parent_plan(self.tags, {(1, 2)}, {'Bar': ['Cocktail Bar']})
        with self.assertRaises(ValueError):
            audit.parent_plan(self.tags, set(), {'Bar': ['Missing']})
        with self.assertRaises(ValueError):
            audit.parent_plan(self.tags, set(), {'Bar': ['Bar']})

    def test_transitive_ancestors_are_complete_and_do_not_include_self(self):
        self.assertEqual(audit.ancestors({(1, 2), (2, 3), (4, 3)})[3], {1, 2, 4})

    def test_memberships_preserve_blocks_and_do_not_inherit_topics_to_locations(self):
        tags = {'Venue': {'id': 1, 'type': 'tag'}, 'Bar': {'id': 2, 'type': 'tag'},
                'Topic': {'id': 3, 'type': 'tag'}}
        def read(cur, sql, params=()):
            if 'FROM location_tags' in sql:
                return [{'location_id': 10, 'tag_id': 20}]
            if 'FROM event_tags' in sql:
                return [{'event_id': 11, 'tag_id': 2}, {'event_id': 12, 'tag_id': 2}]
            if 'FROM event_tag_blocks' in sql:
                return [{'event_id': 11, 'tag_id': 1}]
            raise AssertionError(sql)
        with patch.object(audit.synonyms, 'read', side_effect=read):
            locs, events = audit.membership_additions(None, tags, {(1, 2), (3, 1)},
                ['Venue', 'Bar'], {20: 2}, [])
        self.assertEqual(locs, [(10, 1)])
        self.assertEqual(events, [(11, 3), (12, 1), (12, 3)])


if __name__ == '__main__':
    unittest.main()
