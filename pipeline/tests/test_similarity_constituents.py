"""Aggregate matching invariants, independent of the reviewed relevance corpus."""
import copy
import base64
import json
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from similarity import closest_constituents, fit, representatives, previous_constituents, write_model, topic_constituents, unit, suppress_incidental_aspects, load_topic_context, quantize, browser_vectors, dct_rotation, pack
from similarity_eval import EvaluationModel
from similarity_encoder import content_vectors, MODEL, REVISION
from test_similarity import fixture


class ConstituentTests(unittest.TestCase):
    def test_max_abs_quantization_improves_direction_without_extra_bytes(self):
        vectors = unit(np.random.default_rng(7).normal(size=(20, 96)).astype(np.float32))
        legacy, scaled = quantize(vectors), quantize(vectors, 'max-abs-int8')
        self.assertEqual(legacy.nbytes, scaled.nbytes)
        np.testing.assert_array_equal(np.max(np.abs(scaled), axis=1), 127)
        old_error = np.linalg.norm(browser_vectors(vectors) - vectors)
        new_error = np.linalg.norm(browser_vectors(vectors, 'max-abs-int8') - vectors)
        self.assertLess(new_error, old_error / 2)
        np.testing.assert_array_equal(legacy, np.rint(vectors * 127).astype(np.int8))
        np.testing.assert_array_equal(quantize(np.zeros((1, 96)), 'max-abs-int8'), 0)
        self.assertEqual(quantize(np.empty((0, 96)), 'max-abs-int8').shape, (0, 96))
        with self.assertRaises(ValueError):
            quantize(vectors, 'unknown')

    def test_dct_quantization_keeps_bytes_and_tracks_full_precision_cosines(self):
        # Uncentered projections share a dominant mean axis, which wastes the
        # per-vector byte scale of max-abs-int8 on every other axis.
        rng = np.random.default_rng(11)
        noise = rng.normal(size=(400, 96))
        noise[:, 0] += 6
        vectors = unit(noise.astype(np.float32))
        rotation = dct_rotation(96)
        np.testing.assert_allclose(rotation.T @ rotation, np.eye(96), atol=1e-12)
        legacy, rotated = quantize(vectors, 'max-abs-int8'), quantize(vectors, 'dct-int8')
        self.assertEqual((legacy.dtype, legacy.shape), (rotated.dtype, rotated.shape))
        self.assertLessEqual(int(np.abs(rotated.astype(np.int16)).max()), 127)
        true = vectors @ vectors.T
        legacy_error = np.abs(browser_vectors(vectors, 'max-abs-int8') @ browser_vectors(vectors, 'max-abs-int8').T - true)
        rotated_error = np.abs(browser_vectors(vectors, 'dct-int8') @ browser_vectors(vectors, 'dct-int8').T - true)
        self.assertLess(rotated_error.mean(), legacy_error.mean() / 1.5)
        # Packed bytes are exactly what the evaluator scores (one decoder).
        decoded = np.frombuffer(base64.b64decode(pack([str(i) for i in range(400)], vectors, 'dct-int8')['vectors']),
                                dtype=np.int8).reshape(400, 96)
        np.testing.assert_array_equal(decoded, rotated)
        np.testing.assert_array_equal(quantize(np.zeros((2, 96)), 'dct-int8'), 0)
        self.assertEqual(quantize(np.empty((0, 96)), 'dct-int8').shape, (0, 96))
        self.assertEqual(quantize(vectors[0], 'dct-int8').shape, (96,))

    def test_aspect_suppression_is_partial_preserves_topic_and_deduplicates_directions(self):
        vector = unit(np.array([1., 1., 1.], dtype=np.float32))
        anchor = np.array([1., 0., 0.], dtype=np.float32)
        other = np.array([[0., 1., 0.]], dtype=np.float32)
        changed = suppress_incidental_aspects(vector, anchor, other)
        expected = unit(np.array([1., .5, 1.], dtype=np.float32))
        np.testing.assert_allclose(changed, expected)
        np.testing.assert_allclose(suppress_incidental_aspects(vector, anchor, np.repeat(other, 3, axis=0)), expected)
        related = unit(np.array([[1., 1., 0.]], dtype=np.float32))
        np.testing.assert_array_equal(suppress_incidental_aspects(vector, anchor, related), vector)
        np.testing.assert_array_equal(suppress_incidental_aspects(vector, anchor, []), vector)

    def test_context_roundtrip_preserves_raw_membership_and_event_preferences(self):
        data = fixture()
        fitted = fit(data, dimensions=6, min_df=1)
        raw = fitted[1].copy()
        # Give one tag a visibly different, normalized contextual view of its
        # actual first event. The event/venue vectors must remain untouched.
        part = fitted.parts[len(fitted[0]) + 1][0]
        self.assertLess(part, len(fitted[0]))
        override = np.roll(raw[part], 2)
        fitted.topic_context = {1: {part: override}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            write_model(data, fitted, path/'public', path/'private')
            model = EvaluationModel(path/'private')
            np.testing.assert_array_equal(fitted[1], raw)
            np.testing.assert_allclose(model.matrix[:len(raw)], raw, atol=1e-6)
            np.testing.assert_array_equal(model.topic_context['tag:2'][part], override)
            prior, _ = previous_constituents(path/'private', data)
            self.assertIn((1, 'jazz trio'), prior['tag:2'])
            archive = path/'private/vectors.npz'
            with np.load(archive) as saved:
                fields = dict(saved)
            fields.pop('context_vectors')
            np.savez(archive, **fields)
            with self.assertRaisesRegex(ValueError, 'Missing topic context'):
                EvaluationModel(path/'private')

    def test_corrupt_context_is_rejected(self):
        base = {'context_vectors': np.array([[1., 0.]]), 'context_tag_ids': np.array(['2']),
                'context_part_indices': np.array([0]), 'entity_ids': np.array(['event:1']),
                'tag_ids': np.array(['2'])}
        for changes in [{'context_vectors': np.array([[np.nan, 0.]])},
                        {'context_part_indices': np.array([1])},
                        {'context_tag_ids': np.array(['missing'])}]:
            with self.assertRaises(ValueError):
                load_topic_context({**base, **changes}, 2)

    def test_topic_conditioning_reduces_incidental_transfer_without_collapsing_examples(self):
        examples = np.array([[.3, np.sqrt(.91), 0], [.3, 0, np.sqrt(.91)]], dtype=np.float32)
        original = examples.copy()
        conditioned = topic_constituents(examples, np.array([1., 0, 0]), .5)
        self.assertGreater(conditioned[0, 0], examples[0, 0])
        self.assertLess(conditioned[0, 1], examples[0, 1])
        self.assertGreater(conditioned[0, 1], conditioned[0, 2])
        self.assertGreater(conditioned[1, 2], conditioned[1, 1])
        np.testing.assert_array_equal(examples, original)
        np.testing.assert_allclose(np.linalg.norm(conditioned, axis=1), 1)
        for weight in [-1, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                topic_constituents(examples, np.array([1., 0, 0]), weight)

    def test_browser_artifacts_match_evaluator_for_tags_on_both_sides_and_mixed_profiles(self):
        data = fixture()
        fitted = fit(data, dimensions=6, min_df=1)
        with tempfile.TemporaryDirectory() as directory:
            public, workspace = Path(directory) / 'public', Path(directory) / 'private'
            report = write_model(data, fitted, public, workspace)
            model = EvaluationModel(workspace)
            generation = public / report['generation']
            block = json.loads((generation / 'tags-0.json').read_text())
            raw = unit(np.frombuffer(base64.b64decode(block['vectors']), dtype=np.int8)
                       .reshape(-1, 6).astype(np.float32) / 127)
            decoded = {key: raw[a:b] for key, a, b in zip(block['ids'], block['offsets'], block['offsets'][1:])}
            event = browser_vectors(model.matrix[model.positions['event:3']][None, :], report['quantization'])
            def strength(a, b, threshold):
                return max(0., (float((a @ b.T).max()) - threshold) / (1 - threshold))
            # The tag is also a candidate, as in tag suggestions. A disliked
            # constituent must use the same conditioned bytes as a liked one.
            expected = [strength(v, np.concatenate([decoded['jazz'], decoded['pottery']]), .35)
                        - strength(v, decoded['pottery'], .55) for v in [event, decoded['music']]]
            actual = model.score(['tag:2', 'tag:3'], ['tag:3'], ['event:3', 'tag:1'], browser=True)
            np.testing.assert_allclose(actual, expected, atol=2e-6)
            core = json.loads((generation / 'core.json').read_text())['blocks']['tag']
            core_raw = base64.b64decode(core['vectors'])
            # Initial anchors must be literal members of the later full shard.
            for key, a, b in zip(core['ids'], core['offsets'], core['offsets'][1:]):
                i = block['ids'].index(key)
                full = base64.b64decode(block['vectors'])[block['offsets'][i]*6:block['offsets'][i+1]*6]
                signatures = {full[j:j+6] for j in range(0, len(full), 6)}
                self.assertTrue(all(core_raw[j:j+6] in signatures for j in range(a*6,b*6,6)))

    def test_refresh_retains_distinct_modes_when_recency_order_changes(self):
        matrix = np.array([[1., 0., 0.], [0., 1., 0.], [.99, .1, 0.]], dtype=np.float32)
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
        self.assertEqual(representatives([2, 1, 0], matrix, 2, [0, 1]), [0, 1])

    def test_refresh_replaces_redundancy_to_cover_a_new_program(self):
        matrix = np.array([[1., 0., 0.], [.99, .1, 0.], [0., 0., 1.]], dtype=np.float32)
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
        selected = representatives([0, 1, 2], matrix, 2, [0, 1])
        self.assertIn(2, selected)
        self.assertEqual(len(selected), 2)
        self.assertEqual(representatives([1, 2], matrix, 1, [0]), [1])

    def test_refresh_does_not_evict_a_distinct_mode_for_a_marginal_floor_gain(self):
        # A and B are distinct retained modes. A cluster of outlying new
        # programs (one short repeated series) sits nearest to A. Swapping B
        # for the outlier raises the worst-covered program by well over 0.02
        # and gains more total coverage than B's series loses, yet B's own
        # coverage would fall by far more than the floor rises. The 2026-10-07
        # Architecture refresh evicted its only healthcare-design talk this way.
        a = [1., 0., 0.]
        b = [.6, .8, 0.]
        c = [.4, .075, np.sqrt(1 - .4 ** 2 - .075 ** 2)]
        rng = np.random.default_rng(3)
        cluster = np.array([c] * 4) + rng.normal(scale=.03, size=(4, 3))
        matrix = unit(np.array([a, b, c, *cluster], dtype=np.float32))
        indices = list(range(len(matrix)))
        before = (matrix @ matrix[[0, 1]].T).max(axis=1)
        after = np.maximum(matrix @ matrix[0], matrix @ matrix[2])
        self.assertGreater(after.min() - before.min(), .02)
        self.assertGreater((after - before)[after > before].sum(), (before - after)[before > after].sum())
        self.assertGreater((before - after).max(), after.min() - before.min())
        self.assertEqual(representatives(indices, matrix, 2, [0, 1]), [0, 1])

    def test_refresh_swap_evicts_only_redundant_coverage(self):
        # A2 duplicates A, so replacing it costs almost nothing and covers the
        # new program; distinct B is kept. Without a redundant slot, a new
        # program that would raise the floor by 0.32 still cannot evict a mode
        # whose own coverage would fall by 0.4.
        a, a2, b = [1., 0., 0.], [.995, .0999, 0.], [0., 1., 0.]
        matrix = unit(np.array([a, a2, b, [0., 0., 1.]], dtype=np.float32))
        selected = representatives([0, 1, 2, 3], matrix, 3, [0, 1, 2])
        self.assertEqual(len(set(selected) & {0, 1}), 1)
        self.assertEqual(set(selected) - {0, 1}, {2, 3})
        distinct = unit(np.array([a, b, [0., .6, .8], [0., -.6, .8]], dtype=np.float32))
        self.assertEqual(representatives([0, 1, 2, 3], distinct, 3, [0, 1, 2]), [0, 1, 2])

    def test_previous_model_returns_series_identities_not_stale_vector_indices(self):
        data = fixture()
        model = fit(data, dimensions=6, min_df=1)
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / 'private'
            report = write_model(data, model, Path(directory) / 'public', workspace)
            prior, generation = previous_constituents(workspace, data)
            self.assertEqual(generation, report['generation'])
            self.assertIn((1, 'jazz trio'), prior['place:1'])
            self.assertNotIn((1, 'suppressed listing'), prior['place:1'])

    def test_fixed_projection_preserves_old_vectors_and_rejects_incompatible_encoder(self):
        from similarity import documents
        data = fixture()
        rows, attached, _, excluded = documents(data, set())
        basis = np.eye(384, 3, dtype=np.float32)
        encoded = np.random.default_rng(7).normal(size=(len(rows) + len(data['tags']), 384)).astype(np.float32)
        with tempfile.TemporaryDirectory() as directory, patch('similarity_encoder.encode', return_value=encoded):
            path = Path(directory)
            np.savez(path / 'projection.npz', basis=basis, encoder=MODEL, encoder_revision=REVISION)
            vectors, _, projection, _ = content_vectors(data, rows, attached, excluded, 3, path, path, previous=path)
            expected = encoded[:len(rows), :3]
            expected /= np.linalg.norm(expected, axis=1, keepdims=True)
            np.testing.assert_allclose(vectors, expected, atol=1e-6)
            np.testing.assert_array_equal(projection['basis'], basis)
            with self.assertRaisesRegex(ValueError, 'dimensions'):
                content_vectors(data, rows, attached, excluded, 4, path, path, previous=path)
            np.savez(path / 'projection.npz', basis=basis, encoder=MODEL, encoder_revision='other')
            with self.assertRaisesRegex(ValueError, 'different encoder'):
                content_vectors(data, rows, attached, excluded, 3, path, path, previous=path)

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
