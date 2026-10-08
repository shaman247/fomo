"""Outlier-only aspect suppression (BL16): an example whose neighbors lack its topic."""
from collections import defaultdict
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from similarity import (OUTLIER_ASPECTS, fit, outlier_examples, strengthen_outlier_context,
                        suppress_incidental_aspects, tagged_neighbor_shares, topic_context, topic_tags, unit)
from test_similarity import fixture

SETTINGS = dict(OUTLIER_ASPECTS, neighbors=5, minActiveMembers=5)


def geometry():
    """Axis 0 = the topic, axis 1 = a language, axis 2 = noise.

    Rows 0-3 are typical topic examples; row 4 is a legitimate topic example
    dominated by its language. Rows 5-14 are tagged active topic events and
    rows 15-24 untagged active events in that language.
    """
    rng = np.random.default_rng(3)
    vectors = np.zeros((25, 3))
    vectors[:4] = [1, .1, 0]
    vectors[4] = [.25, 1, 0]
    vectors[5:15] = [1, .05, 0]
    vectors[15:] = [.05, 1, 0]
    vectors[:, 2] = rng.normal(scale=.05, size=25)
    rows = [('event', {'id': i, 'name': f'event {i}'}) for i in range(25)]
    tag_vectors = np.array([[1., 0, 0]])
    tag_parts = [[0, 1, 2, 3, 4, 25]]
    return rows, unit(vectors), tag_vectors, tag_parts, {0: set(range(5, 15))}, list(range(5, 25))


class OutlierExampleTests(unittest.TestCase):
    def test_shares_exclude_the_example_itself(self):
        active = np.arange(4)
        vectors = unit(np.array([[1., 0], [1., .1], [0, 1.], [.1, 1.]]))
        shares = tagged_neighbor_shares(vectors[[0]], [0], active, vectors, {0}, 1)
        self.assertEqual(shares, [0.])  # its own row would have counted as tagged
        self.assertEqual(tagged_neighbor_shares(vectors[[0]], [0], active, vectors, {1}, 1), [1.])

    def test_flags_only_the_example_far_below_its_siblings(self):
        rows, vectors, tag_vectors, tag_parts, members, active = geometry()
        found = outlier_examples(rows, vectors, tag_vectors, tag_parts, {}, members, {0}, .5, active, SETTINGS)
        self.assertEqual(list(found), [0])
        self.assertEqual(list(found[0]), [4])
        share, median = found[0][4]
        self.assertEqual(share, 0.)
        self.assertEqual(median, 1.)

    def test_scope_and_coherence_limits(self):
        rows, vectors, tag_vectors, tag_parts, members, active = geometry()
        def run(**changes):
            arguments = dict(contexts={}, members=members, topics={0}, settings=SETTINGS)
            arguments.update(changes)
            return outlier_examples(rows, vectors, tag_vectors, tag_parts, arguments['contexts'],
                                    arguments['members'], arguments['topics'], .5, active, arguments['settings'])
        self.assertEqual(run(topics=set()), {})  # not a content topic
        self.assertEqual(run(settings=dict(SETTINGS, minActiveMembers=11)), {})
        self.assertEqual(run(settings=dict(SETTINGS, minExamples=6)), {})
        # Siblings that rarely find the topic either give no norm to compare with.
        self.assertEqual(run(settings=dict(SETTINGS, minMedianShare=1.01)), {})
        # The share is measured on the vector as exported, including its context.
        self.assertEqual(run(contexts={0: {4: unit(np.array([1., .1, 0]))}}), {})

    def test_strengthened_context_keeps_the_example_and_its_topic(self):
        rows, vectors, tag_vectors, _, _, _ = geometry()
        # Language anchor at cosine .2 with the topic: above the ordinary .15 cutoff.
        language = unit(np.array([.2, np.sqrt(1 - .04), 0]))
        data = {'tags': [{'id': 10, 'name': 'Topic', 'type': 'tag'},
                         {'id': 11, 'name': 'Language', 'type': 'tag'}]}
        all_vectors = np.vstack([tag_vectors, language])
        attached = {'event': defaultdict(set, {4: {10, 11}, 0: {10, 11}})}
        ordinary = topic_context(data, rows, vectors, all_vectors, [[0, 4, 25], [26]], attached, set(), {})
        self.assertEqual(ordinary, {})
        other_context = {1: {0: vectors[0]}}
        contexts = {**ordinary, **other_context}
        result = strengthen_outlier_context(data, rows, vectors, all_vectors, contexts,
                                            {0: {4: (0., 1.)}}, attached, set(), {})
        self.assertEqual(set(result[0]), {4})  # only the outlier, never its siblings
        changed = result[0][4]
        np.testing.assert_allclose(changed, suppress_incidental_aspects(
            vectors[4], tag_vectors[0], language[None], strength=1., max_topic_cosine=.3))
        self.assertLess(changed @ vectors[15], vectors[4] @ vectors[15] - .3)  # off-topic pull removed
        self.assertGreater(changed @ tag_vectors[0], vectors[4] @ tag_vectors[0])  # topic kept
        self.assertGreater(changed @ vectors[4], 2 * changed @ vectors[15])  # own event beats language-only
        np.testing.assert_array_equal(result[1][0], vectors[0])
        self.assertEqual(contexts, {**ordinary, **other_context})  # input not mutated

    def test_related_or_hierarchical_co_topics_are_never_suppressed(self):
        rows, vectors, tag_vectors, _, _, _ = geometry()
        related = unit(np.array([.5, 1., 0]))  # cosine .45 with the topic
        data = {'tags': [{'id': 10, 'name': 'Topic', 'type': 'tag'},
                         {'id': 11, 'name': 'Parent', 'type': 'tag'},
                         {'id': 12, 'name': 'Related', 'type': 'tag'}]}
        all_vectors = np.vstack([tag_vectors, [[0, 1., 0]], related])
        attached = {'event': defaultdict(set, {4: {10, 11, 12}})}
        result = strengthen_outlier_context(data, rows, vectors, all_vectors, {}, {0: {4: (0., 1.)}},
                                            attached, set(), {10: {11}})
        self.assertEqual(result, {})

    def test_topic_tags_follow_content_roots_only(self):
        data = {'tags': [{'id': 1, 'name': 'Art', 'type': 'tag', 'scope': 'event'},
                         {'id': 2, 'name': 'Architecture', 'type': 'tag', 'scope': 'event'},
                         {'id': 3, 'name': 'Free', 'type': 'tag', 'scope': 'event'},
                         {'id': 4, 'name': 'Free Comedy', 'type': 'tag', 'scope': 'event'},
                         {'id': 5, 'name': 'Museum', 'type': 'tag', 'scope': 'venue'},
                         {'id': 6, 'name': 'Art Walk', 'type': 'keyword', 'scope': 'event'},
                         {'id': 7, 'name': 'Chelsea', 'type': 'tag', 'scope': 'event'}]}
        ancestors = {2: {1}, 4: {3}, 5: {1}, 6: {1}, 7: {1}}
        self.assertEqual(topic_tags(data, ancestors, {7}, ['Art']), {0, 1})


class FitIntegrationTests(unittest.TestCase):
    def test_rule_is_reported_and_off_without_topic_roots(self):
        plain = fit(fixture(), dimensions=6, min_df=1)
        ruled = fit(fixture(), dimensions=6, min_df=1, topic_roots=['Music'])
        self.assertNotIn('outliers', plain[4]['aspectSuppression'])
        self.assertNotIn('outlierExamples', plain[4])
        summary = ruled[4]['aspectSuppression']['outliers']
        self.assertEqual(summary['topicRoots'], ['Music'])
        self.assertEqual((summary['tags'], summary['examples']), (0, 0))  # far below minActiveMembers
        self.assertEqual(ruled[4]['outlierExamples'], [])
        self.assertEqual(plain.topic_context.keys(), ruled.topic_context.keys())
        for ti, group in plain.topic_context.items():
            for part, vector in group.items():
                np.testing.assert_array_equal(ruled.topic_context[ti][part], vector)


if __name__ == '__main__':
    unittest.main()
