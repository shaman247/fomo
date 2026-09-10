"""Read-only similarity artifact and current-event coverage audit.

Exit 0: healthy; 1: refresh/review needed; 2: invalid artifacts or failed audit.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import re

import numpy as np

from similarity import ROOT, normalize, read_snapshot


def inspect_artifacts(output, domain):
    """Validate every referenced shard before trusting coverage or publication."""
    output = Path(output)
    manifest = json.loads((output / 'manifest.json').read_text())
    size = manifest.get('dimensions')
    if (manifest.get('schemaVersion') not in (1, 2) or type(size) is not int or not 2 <= size <= 256
            or not re.fullmatch(r'[a-f0-9]{16}', str(manifest.get('generation', '')))
            or manifest.get('domain') != domain):
        raise ValueError('Incompatible model manifest')
    generated = datetime.fromisoformat(manifest['generatedAt'])
    if generated.tzinfo is None:
        raise ValueError('Model timestamp must include a timezone')
    directory = output / manifest['generation']

    def block(value):
        ids = value['ids']
        if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
            raise ValueError('Invalid or duplicate vector IDs')
        raw = base64.b64decode(value['vectors'], validate=True)
        offsets = value.get('offsets', list(range(len(ids) + 1)))
        if (not isinstance(offsets, list) or len(offsets) != len(ids) + 1 or offsets[0] != 0
                or any(type(n) is not int or n < 0 for n in offsets)
                or offsets != sorted(offsets) or len(raw) != offsets[-1] * size):
            raise ValueError('Invalid vector dimensions')
        matrix = np.frombuffer(raw, dtype=np.int8).reshape(offsets[-1], size)
        usable = [bool(np.any(matrix[start:end] != 0)) for start, end in zip(offsets, offsets[1:])]
        counts = value.get('support')
        if counts is not None and (len(counts) != len(ids) or any(type(n) is not int or n < 0 for n in counts)):
            raise ValueError('Invalid support counts')
        return dict(zip(ids, usable))

    core = json.loads((directory / 'core.json').read_text())
    if any(core.get(key) != manifest[key] for key in ('schemaVersion', 'domain', 'dimensions')):
        raise ValueError('Core does not match manifest')
    if 'affinityThresholds' in core:
        thresholds = core['affinityThresholds']
        if (thresholds != manifest.get('affinityThresholds')
                or any(type(thresholds.get(k)) not in (int, float) or not 0 <= thresholds[k] < 1
                       for k in ('positive', 'negative'))):
            raise ValueError('Invalid affinity thresholds')
    core_blocks = {kind: block(core['blocks'][kind]) for kind in ('event', 'place', 'tag')}
    if manifest['schemaVersion'] == 2:
        for kind, chunk_size, field, prefix in [('place', 128, 'placeShards', 'places'), ('tag', 64, 'tagShards', 'tags')]:
            if kind == 'tag' and field not in manifest:
                continue
            shards = manifest.get(field)
            ids = core['blocks'][kind]['ids']
            expected = list(range((len(ids) + chunk_size - 1) // chunk_size))
            if shards != expected:
                raise ValueError('Invalid aggregate shard list')
            for shard in shards:
                decoded = block(json.loads((directory / f'{prefix}-{shard}.json').read_text()))
                if list(decoded) != ids[shard * chunk_size:(shard + 1) * chunk_size]:
                    raise ValueError('Invalid aggregate shard membership')
    active, history = dict(core_blocks['event']), {}
    for key, prefix, target in [('activeShards', 'active', active), ('historyShards', 'events', history)]:
        shards = manifest.get(key)
        if (not isinstance(shards, list) or any(type(s) is not int or s < 0 for s in shards)
                or len(set(shards)) != len(shards)):
            raise ValueError('Invalid shard list')
        for shard in shards:
            decoded = block(json.loads((directory / f'{prefix}-{shard}.json').read_text()))
            if any(not re.fullmatch(r'\d+', i) for i in decoded):
                raise ValueError('Invalid event ID')
            if target.keys() & decoded.keys():
                raise ValueError('Duplicate event across shards')
            if prefix == 'events' and any(int(i) // 2048 != shard for i in decoded):
                raise ValueError('Event in wrong history shard')
            target.update(decoded)
    if active.keys() & history.keys():
        raise ValueError('Event appears in active and historical shards')
    return manifest, active, history, core_blocks['tag']


def audit(data, output, domain, *, now=None, max_age_days=7, min_coverage=.95):
    manifest, active, history, tags = inspect_artifacts(output, domain)
    now = now or datetime.now(timezone.utc)
    captured = manifest.get('snapshotCapturedAt') or manifest['generatedAt']
    age = (now - datetime.fromisoformat(captured)).total_seconds() / 86400
    current = set(map(str, data['active_ids']))
    learned = current & {i for i, usable in active.items() if usable}
    missing = current - learned
    names = {t['id']: normalize(t['name']) for t in data['tags'] if t['type'] == 'tag'}
    fallback = set()
    for row in data['event_tags']:
        eid = str(row['event_id'])
        if eid in missing and tags.get(names.get(row['tag_id'])):
            fallback.add(eid)
    coverage = len(learned) / len(current) if current else 1
    reasons = []
    if age < -1 / 24:
        reasons.append('Model timestamp is in the future')
    if age >= max_age_days:
        reasons.append(f'Model is at least {max_age_days} days old')
    if coverage < min_coverage:
        reasons.append(f'Active vector coverage is below {min_coverage:.0%}')
    # A zero trained vector does not currently use the browser tag fallback.
    exact_only = missing - {i for i in fallback if i not in active}
    if exact_only:
        reasons.append(f'{len(exact_only)} current events lack usable similarity vectors')
    return {'status': 'review' if reasons else 'healthy', 'reasons': reasons,
            'generation': manifest['generation'], 'generatedAt': manifest['generatedAt'],
            'snapshotCapturedAt': manifest.get('snapshotCapturedAt'),
            'checkedAt': now.isoformat(), 'ageDays': round(age, 2),
            'currentEvents': len(current), 'activeVectorEvents': len(learned),
            'activeVectorCoverage': round(coverage, 5),
            'tagFallbackEvents': len(missing - exact_only), 'exactOnlyEvents': len(exact_only),
            'currentEventsInHistory': len(missing & history.keys()),
            'eventsAbsentFromModel': len(current - active.keys() - history.keys()),
            'exactOnlySample': sorted(exact_only, key=int)[:25]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, default=ROOT / 'src/data/similarity')
    parser.add_argument('--snapshot', type=Path, help='Audit against this snapshot instead of the live DB')
    parser.add_argument('--report', type=Path, help='Also save the JSON result')
    parser.add_argument('--max-age-days', type=float, default=7)
    parser.add_argument('--min-coverage', type=float, default=.95)
    args = parser.parse_args()
    if not 0 < args.max_age_days or not 0 <= args.min_coverage <= 1:
        parser.error('Age must be positive and coverage between 0 and 1')
    from city_config import get_config
    try:
        if args.snapshot:
            with gzip.open(args.snapshot, 'rt', encoding='utf-8') as stream:
                data = json.load(stream)
        else:
            data = read_snapshot()
        report = audit(data, args.model, get_config().get('frontend', {}).get('domain'),
                       max_age_days=args.max_age_days, min_coverage=args.min_coverage)
        code = 0 if report['status'] == 'healthy' else 1
    except Exception as error:
        report, code = {'status': 'error', 'error': str(error)}, 2
    encoded = json.dumps(report, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding='utf-8')
    print(encoded, end='')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
