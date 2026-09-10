"""Evaluate reviewed relevance cases against an offline model, without DB access.

Cases are independent judgments, never inferred from model scores or tag labels.
Use --baseline to compare a candidate to a previous generation on identical cases.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from similarity import unit


class EvaluationModel:
    def __init__(self, workspace):
        workspace = Path(workspace)
        self.report = json.loads((workspace / 'report.json').read_text())
        self.thresholds = self.report.get('affinityThresholds', {'positive': 0, 'negative': 0})
        with np.load(workspace / 'vectors.npz', allow_pickle=False) as saved:
            self.matrix = unit(np.concatenate([saved['vectors'], saved['tag_vectors']]))
            keys = list(saved['entity_ids']) + ['tag:' + value for value in saved['tag_ids']]
            self.positions = {str(key): i for i, key in enumerate(keys)}
            self.constituents = 'part_offsets' in saved
            if self.constituents:
                offsets, indices = saved['part_offsets'], saved['part_indices']
                self.parts = [indices[a:b].copy() for a, b in zip(offsets, offsets[1:])]
            else:
                self.parts = [[i] for i in range(len(keys))]

    def score(self, positive, negative, candidates, browser=False):
        matrix = unit(np.rint(self.matrix * 127) / 127) if browser else self.matrix
        def profile(keys):
            indices = [i for key in keys for i in self.parts[self.positions[key]]]
            if not indices:
                return matrix[:0]
            if self.constituents:
                return matrix[sorted(set(indices))]
            return unit(matrix[indices].sum(axis=0, keepdims=True))
        liked, disliked = profile(positive), profile(negative)
        scores = []
        for key in candidates:
            members = matrix[self.parts[self.positions[key]]]
            def closest(query):
                return max(0., float((members @ query.T).max())) if len(query) and len(members) else 0.
            def strength(value, stance):
                threshold = self.thresholds.get(stance, 0)
                return max(0., (value - threshold) / (1 - threshold))
            scores.append(strength(closest(liked), 'positive') - strength(closest(disliked), 'negative'))
        return np.array(scores)


def evaluate(model, cases):
    if not cases.get('queries') or len({q['id'] for q in cases['queries']}) != len(cases['queries']):
        raise ValueError('Evaluation requires nonempty, uniquely identified queries')
    results = []
    for case in cases['queries']:
        judgments = case['judgments']
        if any(type(value) is not int or value not in (0, 1, 2) for value in judgments.values()):
            raise ValueError('Relevance grades must be 0, 1, or 2')
        candidates = list(judgments)
        scores = model.score(case.get('positive', []), case.get('negative', []), candidates)
        grades = np.array([judgments[key] for key in candidates])
        if not np.any(grades > 0) or not np.any(grades == 0):
            raise ValueError(f'Case {case["id"]} needs both relevant and irrelevant candidates')
        order = sorted(range(len(candidates)), key=lambda i: (-scores[i], candidates[i]))
        top = order[:5]
        discounts = np.log2(np.arange(len(top)) + 2)
        dcg = float(np.sum((2 ** grades[top] - 1) / discounts))
        ideal = float(np.sum((2 ** np.sort(grades)[::-1][:len(top)] - 1) / discounts))
        pairs = [float(scores[i] > scores[j]) + .5 * float(scores[i] == scores[j])
                 for i in range(len(candidates)) for j in range(len(candidates)) if grades[i] > grades[j]]
        results.append({'id': case['id'], 'split': case.get('split', 'regression'),
                        'judgments': len(judgments), 'ndcgAt5': dcg / ideal,
                        'pairwiseAccuracy': float(np.mean(pairs)),
                        'wrongTop1': int(grades[order[0]] == 0),
                        'meanRelevantScore': float(scores[grades > 0].mean()),
                        'meanIrrelevantScore': float(scores[grades == 0].mean()),
                        'top5': [{'key': candidates[i], 'score': round(float(scores[i]), 4),
                                  'grade': int(grades[i])} for i in top]})
    summary = {'queries': len(results), 'judgments': sum(r['judgments'] for r in results)}
    for key in ('ndcgAt5', 'pairwiseAccuracy', 'wrongTop1'):
        summary[key] = float(np.mean([r[key] for r in results]))
    return {'generation': model.report.get('generation'), 'summary': summary, 'queries': results}


def check_gate(candidate, baseline=None):
    """Reject measured regressions; this is not a claim of universal relevance."""
    current = candidate['summary']
    if baseline:
        previous = baseline['summary']
        failed = (current['ndcgAt5'] + .005 < previous['ndcgAt5']
                  or current['pairwiseAccuracy'] + .005 < previous['pairwiseAccuracy']
                  or current['wrongTop1'] > previous['wrongTop1'])
    else:
        failed = current['ndcgAt5'] < .9 or current['wrongTop1'] > 0
    if failed:
        raise ValueError('Relevance gate failed; the public manifest was not changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--gate', action='store_true')
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text())
    result = {'candidate': evaluate(EvaluationModel(args.workspace), cases)}
    if args.baseline:
        result['baseline'] = evaluate(EvaluationModel(args.baseline), cases)
        result['delta'] = {key: result['candidate']['summary'][key] - result['baseline']['summary'][key]
                           for key in ('ndcgAt5', 'pairwiseAccuracy', 'wrongTop1')}
    encoded = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded)
    print(json.dumps({key: value.get('summary', value) for key, value in result.items()}, indent=2))
    if args.gate:
        check_gate(result['candidate'], result.get('baseline'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
