"""Relevance gates must reject empty evaluations and measured regressions."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from similarity_eval import evaluate, check_gate


class EvaluationTests(unittest.TestCase):
    def test_gate_rejects_worse_ranking_and_more_wrong_first_results(self):
        baseline = {'summary': {'ndcgAt5': .8, 'pairwiseAccuracy': .9, 'wrongTop1': 0}}
        check_gate(baseline, baseline)
        for field, value in [('ndcgAt5', .6), ('pairwiseAccuracy', .7), ('wrongTop1', .1)]:
            candidate = {'summary': {**baseline['summary'], field: value}}
            with self.assertRaises(ValueError):
                check_gate(candidate, baseline)

    def test_empty_cases_do_not_pass_a_release_gate(self):
        with self.assertRaises(ValueError):
            evaluate(None, {'queries': []})

    def test_metrics_measure_judgments_and_not_the_model_own_order(self):
        class Model:
            report = {'generation': 'test'}
            def score(self, *_):
                return np.array([.1, .9])
        result = evaluate(Model(), {'queries': [{'id': 'test', 'positive': ['tag:1'],
            'judgments': {'event:1': 2, 'event:2': 0}}]})
        self.assertEqual(result['summary']['wrongTop1'], 1)
        self.assertEqual(result['summary']['pairwiseAccuracy'], 0)
        self.assertLess(result['summary']['ndcgAt5'], 1)


if __name__ == '__main__':
    unittest.main()
