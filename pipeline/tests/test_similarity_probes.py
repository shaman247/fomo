"""Cold text stays outside training; mixed profiles and scoped tags are explicit."""
import copy
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from similarity_probes import probe_cases
from similarity_eval import EvaluationModel, evaluate


class ProbeTests(unittest.TestCase):
    def test_scoped_tags_and_mixed_profiles_use_distinct_constituents(self):
        model = EvaluationModel.__new__(EvaluationModel)
        model.report = {}
        model.thresholds = {'positive': .35, 'negative': .55}
        model.constituents = True
        model.matrix = np.eye(3, dtype=np.float32)
        model.parts = [[0], [1], [2]]
        model.positions = {'tag:1': 0, 'tag:2': 1, 'tag:3': 2}
        data = {'tags': [{'id': 1, 'name': 'Jazz', 'scope': 'event', 'type': 'tag'},
                         {'id': 2, 'name': 'Clay', 'scope': 'event', 'type': 'tag'},
                         {'id': 3, 'name': 'Jazz', 'scope': 'venue', 'type': 'tag'}]}
        spec = {'probes': [{'id': 'music', 'topic': 'Jazz'}, {'id': 'clay', 'topic': 'Clay'},
                           {'id': 'unrelated'}],
                'profiles': [{'id': 'mixed', 'probes': ['music', 'clay']}],
                'queries': [{'id': 'both', 'positive': ['profile:mixed'],
                             'judgments': {'probe:music': 2, 'probe:clay': 2, 'probe:unrelated': 0}},
                            {'id': 'scoped', 'positive': ['tag:venue:Jazz'],
                             'judgments': {'probe:music': 0, 'probe:unrelated': 2}}]}
        original = copy.deepcopy(model.parts)
        cases = probe_cases(model, data, spec, np.eye(3, dtype=np.float32))
        self.assertEqual(model.parts[:3], original)
        self.assertEqual(cases['queries'][1]['positive'], ['tag:1'])
        self.assertEqual(model.parts[model.positions['profile:mixed']], [3, 4])
        self.assertEqual(cases['queries'][-1]['positive'], ['tag:3'])
        result = evaluate(model, cases)
        self.assertEqual(result['summary']['ndcgAt5'], 1)
        self.assertEqual(result['summary']['wrongTop1'], 0)


if __name__ == '__main__':
    unittest.main()
