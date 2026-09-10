"""Aggregate matching invariants, independent of the reviewed relevance corpus."""
import copy
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from similarity import closest_constituents, fit, representatives
from test_similarity import fixture


class ConstituentTests(unittest.TestCase):
    def test_aggregate_uses_closest_member_on_both_sides(self):
        matrix = np.eye(3, dtype=np.float32)
        parts = [[0], [1], [2], [0, 1]]
        scores = closest_constituents(matrix, parts, matrix[[1]])
        np.testing.assert_allclose(scores, [0, 1, 0, 1])
        mixed = closest_constituents(matrix, parts, matrix[[0, 1]])
        np.testing.assert_allclose(mixed, [1, 1, 0, 1])

    def test_rare_program_survives_many_repeated_programs(self):
        matrix = np.array([[1., 0.]] * 100 + [[0., 1.]], dtype=np.float32)
        chosen = representatives(list(range(len(matrix))), matrix, 12)
        self.assertIn(100, chosen)
        self.assertEqual(len(chosen), 2)
        self.assertEqual(len(representatives(list(range(len(matrix))), matrix, 0)), 101)

    def test_mixed_venue_keeps_both_event_constituents_and_parent_keeps_both_branches(self):
        data = fixture()
        data['events'][2]['location_id'] = 1
        data['tags'].append({'id': 8, 'name': 'Creative Activities', 'type': 'tag', 'emoji': None})
        data['hierarchy'] += [{'parent_tag_id': 8, 'child_tag_id': 2}, {'parent_tag_id': 8, 'child_tag_id': 3}]
        model = fit(data, dimensions=6, min_df=1)
        rows, vectors, tags, support, _ = model
        positions = {(kind, value['id']): i for i, (kind, value) in enumerate(rows)}
        venue = model.parts[positions['place', 1]]
        self.assertIn(positions['event', 2], venue)
        self.assertIn(positions['event', 3], venue)
        parent = model.parts[len(rows) + 6]
        self.assertIn(len(rows) + 1, parent)
        self.assertIn(len(rows) + 2, parent)
        self.assertGreater(support[6], 0)  # derived even without stored ancestor edges
        self.assertEqual(model.parts[len(rows) + 3], [])  # geography stays excluded

    def test_repeated_series_prefers_active_record_and_does_not_create_a_centroid(self):
        data = fixture()
        old = copy.deepcopy(data['events'][1])
        old.update(id=99, archived=True)
        data['events'].append(old)
        model = fit(data, dimensions=6, min_df=1)
        rows = model[0]
        positions = {(kind, value['id']): i for i, (kind, value) in enumerate(rows)}
        self.assertIn(positions['event', 2], model.parts[positions['place', 1]])
        self.assertNotIn(positions['event', 99], model.parts[positions['place', 1]])


if __name__ == '__main__':
    unittest.main()
