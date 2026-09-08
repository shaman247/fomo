"""Model invariants and artifact compatibility, without a live database."""
import base64
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from similarity import documents, fit, normalize, pack, place_key, write_model


def fixture():
    tags = [{'id': i, 'name': name, 'type': 'tag', 'emoji': emoji} for i, name, emoji in [
        (1, 'Music', '🎵'), (2, 'Jazz', '🎷'), (3, 'Pottery', '🏺'),
        (4, 'Neighborhood', '📍'), (5, 'Somewhere', None), (6, 'Children', '🧒')]]
    events = [{'id': i, 'name': name, 'description': desc, 'location_id': pid,
               'archived': i == 1, 'suppressed': i == 5} for i, name, desc, pid in [
        (1, 'Jazz quartet', 'Saxophone trumpet live music', 1),
        (2, 'Jazz trio', 'Saxophone trumpet live music', 1),
        (3, 'Pottery studio', 'Clay wheel ceramics sculpture', 2),
        (4, 'Pottery workshop', 'Clay wheel ceramics sculpture', 2),
        (5, 'Suppressed listing', 'Garbage should never teach the model', 1)]]
    return {'events': events,
            'places': [{'id': i, 'name': name, 'address': str(i), 'description': '', 'lat': 1, 'lng': 1}
                       for i, name in [(1, 'Music hall'), (2, 'Clay studio')]],
            'tags': tags, 'event_tags': [{'event_id': i, 'tag_id': tid}
                                       for i, tid in [(1, 1), (1, 2), (1, 5), (2, 2), (3, 3), (4, 3), (5, 6)]],
            'place_tags': [{'location_id': 1, 'tag_id': 6}],
            'hierarchy': [{'parent_tag_id': 1, 'child_tag_id': 2}, {'parent_tag_id': 4, 'child_tag_id': 5}],
            'active_ids': [2, 3, 4]}


class SimilarityTests(unittest.TestCase):
    def test_history_included_suppressed_excluded_and_geography_not_learned(self):
        rows, attached, features, excluded = documents(fixture(), set())
        ids = [e['id'] for k, e in rows if k == 'event']
        self.assertEqual(ids, [1, 2, 3, 4])
        self.assertEqual(excluded, {4, 5})
        event_features = features(*rows[0])
        self.assertIn('t:2', event_features)
        self.assertNotIn('t:1', event_features)  # redundant ancestor
        self.assertNotIn('t:5', event_features)
        self.assertNotIn('t:6', event_features)  # venue audience is not event audience

    def test_shared_space_retrieves_related_events_and_places(self):
        rows, vectors, tags, support, report = fit(fixture(), dimensions=6, min_df=1)
        self.assertGreater(float(vectors[0] @ vectors[1]), float(vectors[0] @ vectors[2]) + .3)
        self.assertGreater(float(tags[1] @ vectors[4]), float(tags[1] @ vectors[5]))
        self.assertEqual(report['trainingEvents'], 4)
        self.assertEqual(report['historicalTrainingEvents'], 1)
        self.assertEqual(support[5], 1)  # place only; suppressed event did not vote
        np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
        repeated = fit(fixture(), dimensions=6, min_df=1)
        np.testing.assert_allclose(vectors, repeated[1], atol=1e-5)

    def test_normalization_matches_frontend_contract(self):
        self.assertEqual(normalize('  ＪＡＺＺ—Café! '), 'jazz café')
        self.assertEqual(place_key({'name': 'A Hall', 'address': '10 Main St.'}), 'a hall|10 main st')

    def test_signed_quantization_preserves_cosine(self):
        original = np.array([[.6, -.8], [-.8, -.6]], dtype=np.float32)
        block = pack(['1', '2'], original)
        decoded = np.frombuffer(base64.b64decode(block['vectors']), dtype=np.int8).reshape(2, 2) / 127
        self.assertLess(abs(float(decoded[0] @ decoded[1])), .01)
        np.testing.assert_allclose(decoded, original, atol=1/127)

    def test_artifacts_separate_history_and_change_generation_on_active_change(self):
        data = fixture()
        fitted = fit(data, dimensions=6, min_df=1)
        with tempfile.TemporaryDirectory() as directory:
            output, workspace = Path(directory) / 'public', Path(directory) / 'private'
            report = write_model(data, fitted, output, workspace)
            manifest = json.loads((output / 'manifest.json').read_text())
            generation = output / manifest['generation']
            core = json.loads((generation / 'core.json').read_text())
            self.assertEqual(core['blocks']['event']['ids'], [])
            self.assertEqual(json.loads((generation / 'events-0.json').read_text())['ids'], ['1'])
            self.assertEqual(json.loads((generation / 'active-0.json').read_text())['ids'], ['2', '3', '4'])
            data = copy.deepcopy(data)
            data['active_ids'] = [1, 3, 4]  # same place counts, different active IDs
            next_report = write_model(data, fitted, output, workspace)
            self.assertNotEqual(report['generation'], next_report['generation'])
            self.assertTrue((generation / 'core.json').exists())


if __name__ == '__main__':
    unittest.main()
