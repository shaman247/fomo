"""Evaluate unseen authored text with the saved semantic projection; no retraining."""
import argparse
import gzip
import json
from pathlib import Path

import numpy as np

from similarity import ROOT, normalize, unit
from similarity_encoder import encode, MODEL, REVISION
from similarity_eval import EvaluationModel, evaluate, check_gate
from tag_scopes import public_tag_key


def probe_cases(model, data, specification, matrix):
    """Append held-out text and mixed profiles without fitting or changing aggregates."""
    probes = specification['probes']
    tags = {normalize(public_tag_key(tag['name'], tag.get('scope', 'event'))): tag['id']
            for tag in data['tags'] if tag['type'] == 'tag'}
    if len({probe['id'] for probe in probes}) != len(probes) or len(matrix) != len(probes):
        raise ValueError('Probes require unique IDs and one encoded vector per text')
    start = len(model.matrix)
    model.matrix = np.concatenate([model.matrix, matrix])
    for i, probe in enumerate(probes):
        model.positions['probe:' + probe['id']] = len(model.parts)
        model.parts.append([start + i])
    for profile in specification.get('profiles', []):
        key = 'profile:' + profile['id']
        if key in model.positions or not profile['probes']:
            raise ValueError('Profiles require unique IDs and nonempty constituents')
        parts = [model.parts[model.positions['probe:' + key]][0] for key in profile['probes']]
        model.positions[key] = len(model.parts)
        model.parts.append(parts)
    queries = [{'id': topic, 'positive': [f'tag:{tags[normalize(topic)]}'], 'negative': [],
                'split': 'new-text-probes', 'judgments': {
                    'probe:' + probe['id']: 2 if probe.get('topic') == topic else 0 for probe in probes}}
               for topic in sorted({probe['topic'] for probe in probes if probe.get('topic')})]
    for query in specification.get('queries', []):
        def resolve(key):
            return f'tag:{tags[normalize(key[4:])]}' if key.startswith('tag:') else key
        queries.append({**query, 'split': 'new-text-mixed-profiles',
                        'positive': [resolve(key) for key in query.get('positive', [])],
                        'negative': [resolve(key) for key in query.get('negative', [])]})
    return {'queries': queries}


def evaluate_probes(workspace, data, specification, encoded, *, browser=False):
    model = EvaluationModel(workspace)
    with np.load(Path(workspace) / 'projection.npz', allow_pickle=False) as projection:
        if str(projection.get('encoder')) != MODEL or str(projection.get('encoder_revision')) != REVISION:
            raise ValueError('Text probes require the pinned semantic encoder projection')
        basis = projection['basis']
        if basis.shape != (encoded.shape[1], model.matrix.shape[1]) or not np.isfinite(basis).all():
            raise ValueError('Invalid text probe projection')
        matrix = unit(encoded @ basis)
    return evaluate(model, probe_cases(model, data, specification, matrix), browser=browser)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--model-cache', type=Path, required=True)
    parser.add_argument('--cases', type=Path, default=ROOT / 'pipeline/tests/fixtures/similarity_probe_cases.json')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, help='Compare identical unseen texts against a saved model')
    parser.add_argument('--gate', action='store_true')
    parser.add_argument('--browser', action='store_true', help='Evaluate int8 browser precision')
    args = parser.parse_args()
    specification = json.loads(args.cases.read_text())
    probes = specification['probes']
    with gzip.open(args.snapshot, 'rt') as stream:
        data = json.load(stream)
    encoded = encode([probe['text'] for probe in probes], args.workspace / 'probes', args.model_cache)
    result = evaluate_probes(args.workspace, data, specification, encoded, browser=args.browser)
    if args.baseline:
        result['baseline'] = evaluate_probes(args.baseline, data, specification, encoded, browser=args.browser)
        result['delta'] = {key: result['summary'][key] - result['baseline']['summary'][key]
                           for key in ('ndcgAt5', 'pairwiseAccuracy', 'wrongTop1')}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['summary'], indent=2))
    if args.gate:
        check_gate(result, result.get('baseline'))


if __name__ == '__main__':
    main()
