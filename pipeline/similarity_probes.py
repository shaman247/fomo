"""Evaluate unseen authored text with the saved semantic projection; no retraining."""
import argparse
import gzip
import json
from pathlib import Path

import numpy as np

from similarity import ROOT, normalize, unit
from similarity_encoder import encode
from similarity_eval import EvaluationModel, evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--model-cache', type=Path, required=True)
    parser.add_argument('--cases', type=Path, default=ROOT / 'pipeline/tests/fixtures/similarity_probe_cases.json')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    probes = json.loads(args.cases.read_text())['probes']
    with gzip.open(args.snapshot, 'rt') as stream:
        data = json.load(stream)
    tags = {normalize(tag['name']): tag['id'] for tag in data['tags'] if tag['type'] == 'tag'}
    model = EvaluationModel(args.workspace)
    with np.load(args.workspace / 'projection.npz', allow_pickle=False) as projection:
        if 'encoder' not in projection:
            raise ValueError('Text probes require a saved semantic encoder projection')
        matrix = unit(encode([probe['text'] for probe in probes], args.workspace / 'probes', args.model_cache)
                      @ projection['basis'])
    start = len(model.matrix)
    model.matrix = np.concatenate([model.matrix, matrix])
    for i, probe in enumerate(probes):
        model.positions['probe:' + probe['id']] = start + i
        model.parts.append([start + i])
    queries = [{'id': topic, 'positive': [f'tag:{tags[normalize(topic)]}'], 'negative': [],
                'split': 'new-text-probes', 'judgments': {
                    'probe:' + probe['id']: 2 if probe['topic'] == topic else 0 for probe in probes}}
               for topic in sorted({probe['topic'] for probe in probes})]
    result = evaluate(model, {'queries': queries})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    main()
