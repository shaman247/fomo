"""Offline content similarity for events, places and tags; no DB mutations.

Run with the project venv. See similarity.md for the model and artifact contract.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import time
import unicodedata

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]
STOP = set('a an and are as at be been but by can do for from has have in into is it its of on or our that the their this to was we were will with you your'.split())


def normalize(value):
    value = unicodedata.normalize('NFKC', str(value or '')).lower()
    return ' '.join(''.join(c if c.isalpha() or c.isnumeric() else ' ' for c in value).split())


def place_key(place):
    return normalize(place['name']) + '|' + normalize(place.get('address'))


def unit(matrix):
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    return matrix / np.maximum(norms, 1e-12)


def read_snapshot():
    from db import create_connection
    from constants import get_active_date_window
    from exporter import _PUBLISHABLE_WEBSITE_GATE
    conn = create_connection()
    if conn is None:
        raise RuntimeError('Database unavailable; no model was changed')
    try:
        cur = conn.cursor(dictionary=True)
        # MariaDB advertises a 5.5.5 compatibility prefix; mysql.connector's
        # start_transaction(readonly=True) rejects that version before sending SQL.
        cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        cur.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
        def read(query, params=()):
            cur.execute(query, params)
            return cur.fetchall()
        # Canonical entities only: raw crawl rows repeat the same event many times.
        data = {name: read(query) for name, query in {
            'events': 'SELECT id,name,description,location_id,archived,suppressed FROM events ORDER BY id',
            'places': 'SELECT id,name,address,description,lat,lng FROM locations ORDER BY id',
            'tags': 'SELECT id,name,type,emoji FROM tags ORDER BY id',
            'event_tags': 'SELECT event_id,tag_id FROM event_tags ORDER BY event_id,tag_id',
            'place_tags': 'SELECT location_id,tag_id FROM location_tags ORDER BY location_id,tag_id',
            'hierarchy': 'SELECT parent_tag_id,child_tag_id FROM tag_hierarchy ORDER BY parent_tag_id,child_tag_id',
        }.items()}
        today, end = get_active_date_window()
        data['active_ids'] = [r['id'] for r in read(f'''
            SELECT e.id FROM events e JOIN locations l ON l.id=e.location_id
            LEFT JOIN websites w ON w.id=e.website_id
            WHERE e.archived=FALSE AND e.suppressed=FALSE
              AND l.lat IS NOT NULL AND l.lng IS NOT NULL
              AND ({_PUBLISHABLE_WEBSITE_GATE})
              AND EXISTS (SELECT 1 FROM event_urls u WHERE u.event_id=e.id)
              AND EXISTS (SELECT 1 FROM event_occurrences o WHERE o.event_id=e.id
                          AND o.start_date<=%s AND COALESCE(o.end_date,o.start_date)>=%s)
            ORDER BY e.id''', (end, today))]
        conn.rollback()
        return data
    finally:
        conn.close()


def ancestors_for(hierarchy):
    parents = defaultdict(set)
    for edge in hierarchy:
        parents[edge['child_tag_id']].add(edge['parent_tag_id'])
    def ancestors(tag):
        seen, todo = set(), list(parents[tag])
        while todo:
            item = todo.pop()
            if item not in seen and item != tag:
                seen.add(item)
                todo.extend(parents[item] - seen)
        return seen
    return {tag: ancestors(tag) for tag in list(parents)}


def documents(data, geotags):
    tags = {t['id']: t for t in data['tags']}
    excluded = {t['id'] for t in data['tags'] if normalize(t['name']) in geotags}
    ancestors = ancestors_for(data['hierarchy'])
    geographic_roots = {t['id'] for t in data['tags'] if t['name'] == 'Neighborhood' or t.get('emoji') == '📍'}
    excluded |= geographic_roots
    excluded |= {tid for tid, parents in ancestors.items() if parents & geographic_roots}
    attached = {'event': defaultdict(set), 'place': defaultdict(set)}
    for r in data['event_tags']:
        attached['event'][r['event_id']].add(r['tag_id'])
    for r in data['place_tags']:
        attached['place'][r['location_id']].add(r['tag_id'])
    rows = [('event', e) for e in data['events'] if not e['suppressed']]
    rows += [('place', p) for p in data['places']]

    def features(kind, item):
        ids = attached[kind][item['id']] - excluded
        inherited = set().union(*(ancestors.get(t, set()) for t in ids)) if ids else set()
        leaves = ids - inherited
        counts = Counter()
        def words(text, weight):
            for word in normalize(text).split():
                if len(word) > 2 and not word.isnumeric() and word not in STOP:
                    counts['w:' + word] += weight
        words(item['name'], 3)
        words((item.get('description') or '')[:1600], 1)
        for tid in leaves:
            tag = tags.get(tid)
            if not tag:
                continue
            if tag['type'] == 'tag':
                counts['t:' + str(tid)] = 1
            words(tag['name'], 2)
        return counts
    return rows, attached, features, excluded


def fit(data, geotags=(), dimensions=96, min_df=5, seed=17):
    rows, attached, features, excluded = documents(data, set(map(normalize, geotags)))
    if not rows:
        raise ValueError('No training entities')
    print(f'Analyzing {len(rows):,} canonical entities', flush=True)
    df = Counter()
    for kind, item in rows:
        df.update(features(kind, item).keys())
    vocabulary = sorted(k for k, n in df.items() if k.startswith('t:') or (n >= min_df and n < len(rows) * .65))
    # Keep all curated features, and the best-supported 30k text features.
    text = sorted((k for k in vocabulary if k.startswith('w:')), key=lambda k: (-df[k], k))[:30000]
    vocabulary = sorted([k for k in vocabulary if k.startswith('t:')] + text)
    if not vocabulary:
        raise ValueError('No usable features')
    columns = {k: i for i, k in enumerate(vocabulary)}
    idf = {k: math.log((1 + len(rows)) / (1 + df[k])) + 1 for k in vocabulary}
    values, indices, offsets = [], [], [0]
    for kind, item in rows:
        channels = [[], []]
        for key, count in features(kind, item).items():
            if key in columns:
                channels[key.startswith('w:')].append((columns[key], (1 + math.log(count)) * idf[key]))
        for channel, weight in zip(channels, [.8, .6]):
            norm = math.sqrt(sum(v*v for _, v in channel)) or 1
            for column, value in channel:
                indices.append(column)
                values.append(weight * value / norm)
        offsets.append(len(values))
    matrix = sparse.csr_matrix((np.asarray(values, dtype=np.float32), indices, offsets),
                               shape=(len(rows), len(vocabulary)))
    del values, indices, offsets
    print(f'Fitting latent space: {matrix.shape}, {matrix.nnz:,} nonzero features', flush=True)
    # Randomized truncated SVD with deterministic seed and two power iterations.
    # Only the thin projection is dense; never form an entity x entity matrix.
    rank = min(dimensions, min(matrix.shape))
    width = min(rank + 12, min(matrix.shape))
    random = np.random.default_rng(seed).standard_normal((matrix.shape[1], width), dtype=np.float32)
    q, _ = np.linalg.qr(matrix @ random, mode='reduced')
    for _ in range(2):
        z, _ = np.linalg.qr(matrix.T @ q, mode='reduced')
        q, _ = np.linalg.qr(matrix @ z, mode='reduced')
    small = np.asarray(matrix.T @ q).T
    _, singular, basis = np.linalg.svd(small, full_matrices=False)
    basis = basis[:rank].T
    vectors = unit(np.asarray(matrix @ basis))
    positions = {(kind, item['id']): i for i, (kind, item) in enumerate(rows)}

    # Place programming: mean of unique event-name profiles, not occurrence counts
    # or a venue's crawl volume. No reverse inheritance into event vectors.
    groups = defaultdict(list)
    for i, (kind, item) in enumerate(rows):
        if kind == 'event' and item['location_id']:
            groups[(item['location_id'], normalize(item['name']))].append(i)
    programming = defaultdict(list)
    for (pid, _), members in groups.items():
        programming[pid].append(unit(vectors[members].mean(axis=0)))
    for pid, programs in programming.items():
        pos = positions.get(('place', pid))
        if pos is not None:
            vectors[pos] = unit(.25 * vectors[pos] + .75 * unit(np.mean(programs, axis=0)))

    # All tags/keywords receive vectors offline; only curated chips ship eagerly.
    tag_vectors = np.zeros((len(data['tags']), rank), dtype=np.float32)
    tag_positions = {t['id']: i for i, t in enumerate(data['tags'])}
    support = np.zeros(len(data['tags']), dtype=np.int32)
    for i, (kind, item) in enumerate(rows):
        for tid in attached[kind][item['id']] - excluded:
            if tid in tag_positions:
                ti = tag_positions[tid]
                tag_vectors[ti] += vectors[i] * (1 if kind == 'event' else .25)
                support[ti] += 1
    tag_vectors = unit(tag_vectors)
    report = {
        'databaseEvents': len(data['events']), 'trainingEvents': sum(k == 'event' for k, _ in rows),
        'suppressedExcluded': sum(bool(e['suppressed']) for e in data['events']),
        'historicalTrainingEvents': sum(bool(e['archived']) and not e['suppressed'] for e in data['events']),
        'places': len(data['places']), 'tagsAndKeywords': len(data['tags']),
        'features': len(vocabulary), 'dimensions': rank, 'seed': seed,
        'retainedEnergy': float(np.sum(singular[:rank] ** 2) / matrix.multiply(matrix).sum()),
        'zeroEntityVectors': int(np.sum(np.linalg.norm(vectors, axis=1) < .01)),
        'zeroTagVectors': int(np.sum(np.linalg.norm(tag_vectors, axis=1) < .01)),
    }
    return rows, vectors, tag_vectors, support, report


def pack(ids, vectors):
    quantized = np.rint(np.clip(vectors, -1, 1) * 127).astype(np.int8)
    return {'ids': ids, 'vectors': base64.b64encode(quantized.tobytes()).decode('ascii')}


def write_model(data, fitted, output, workspace):
    from city_config import get_config
    rows, vectors, tag_vectors, support, report = fitted
    report = dict(report)
    output, workspace = Path(output), Path(workspace)
    output.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    active = set(data['active_ids'])
    positions = {k: [] for k in ['event', 'place']}
    for i, (kind, item) in enumerate(rows):
        if kind == 'place' or item['id'] in active:
            positions[kind].append(i)
    blocks = {}
    for kind, subset in positions.items():
        ids = [place_key(rows[i][1]) if kind == 'place' else str(rows[i][1]['id']) for i in subset]
        blocks[kind] = pack(ids, vectors[subset]) if kind == 'place' else pack([], vectors[:0])
        if kind == 'place':
            counts = Counter(e['location_id'] for e in data['events'] if e['id'] in active)
            blocks[kind]['support'] = [counts[rows[i][1]['id']] for i in subset]
    tag_indices = [i for i, tag in enumerate(data['tags']) if tag['type'] == 'tag' and support[i] > 0]
    blocks['tag'] = pack([normalize(data['tags'][i]['name']) for i in tag_indices], tag_vectors[tag_indices])
    blocks['tag']['support'] = [int(support[i]) for i in tag_indices]
    body = {'schemaVersion': 1, 'dimensions': vectors.shape[1],
            'domain': get_config().get('frontend', {}).get('domain'), 'blocks': blocks}
    payload = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode()
    # Generation digest covers historical vectors too: no mixed-version shards.
    identity = json.dumps({'entities': [(k, item['id']) for k, item in rows],
                           'active': sorted(active)}, separators=(',', ':')).encode()
    digest = hashlib.sha256(payload + identity + vectors.tobytes()).hexdigest()[:16]
    generation = output / digest
    generation.mkdir(exist_ok=True)
    (generation / 'core.json').write_bytes(payload)
    active_shards = defaultdict(list)
    active_bytes, active_gzip = 0, 0
    for index, i in enumerate(positions['event']):
        active_shards[index // 2048].append(i)
    for shard, subset in active_shards.items():
        block = pack([str(rows[i][1]['id']) for i in subset], vectors[subset])
        encoded = json.dumps(block, separators=(',', ':')).encode()
        (generation / f'active-{shard}.json').write_bytes(encoded)
        active_bytes += len(encoded)
        active_gzip += len(gzip.compress(encoded))
    shards = defaultdict(list)
    for i, (kind, item) in enumerate(rows):
        if kind == 'event' and item['id'] not in active:
            shards[item['id'] // 2048].append(i)
    for shard, subset in shards.items():
        block = pack([str(rows[i][1]['id']) for i in subset], vectors[subset])
        (generation / f'events-{shard}.json').write_text(json.dumps(block, separators=(',', ':')), encoding='utf-8')
    report.update({'activeEventVectors': len(positions['event']), 'publicTagVectors': len(tag_indices),
                   'coreBytes': len(payload), 'coreGzipBytes': len(gzip.compress(payload)),
                   'activeBytes': active_bytes, 'activeGzipBytes': active_gzip, 'generation': digest})
    # All entity/tag vectors and identifiers stay available for offline analysis.
    np.savez_compressed(workspace / 'vectors.npz', vectors=vectors, tag_vectors=tag_vectors,
                        entity_ids=np.array([f'{k}:{v["id"]}' for k, v in rows]),
                        tag_ids=np.array([str(t['id']) for t in data['tags']]))
    report['samples'] = sample_neighbors(data, rows, vectors, tag_vectors, support)
    (workspace / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    manifest = {'schemaVersion': 1, 'generation': digest, 'dimensions': vectors.shape[1],
                'generatedAt': datetime.now(timezone.utc).isoformat(), 'domain': body['domain'],
                'historyShards': sorted(shards), 'activeShards': sorted(active_shards)}
    # Publish the pointer last. Keep previous generations for cached clients.
    temporary = output / 'manifest.json.tmp'
    temporary.write_text(json.dumps(manifest, separators=(',', ':')), encoding='utf-8')
    temporary.replace(output / 'manifest.json')
    return report


def sample_neighbors(data, rows, vectors, tag_vectors, support):
    # Deterministic support-stratified diagnostics, not a relevance benchmark.
    tags = data['tags']
    eligible = [i for i, t in enumerate(tags) if t['type'] == 'tag' and support[i] >= 20]
    eligible.sort(key=lambda i: (-support[i], tags[i]['name']))
    sample = eligible[::max(1, len(eligible) // 12)][:12]
    active = set(data['active_ids'])
    event_indices = [i for i, (k, e) in enumerate(rows) if k == 'event' and e['id'] in active]
    result = []
    for ti in sample:
        similarities = vectors[event_indices] @ tag_vectors[ti]
        nearest = np.argsort(-similarities, kind='stable')[:5]
        result.append({'tag': tags[ti]['name'], 'events': [
            {'id': rows[event_indices[j]][1]['id'], 'name': rows[event_indices[j]][1]['name'],
             'similarity': round(float(similarities[j]), 3)} for j in nearest]})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'src/data/similarity')
    parser.add_argument('--workspace', type=Path, default=ROOT / '.scratch/similarity')
    parser.add_argument('--snapshot', type=Path, help='Reuse a local snapshot for reproducible experiments')
    parser.add_argument('--dimensions', type=int, default=96)
    args = parser.parse_args()
    if not 2 <= args.dimensions <= 256:
        parser.error('--dimensions must be between 2 and 256')
    from city_config import geotags
    start = time.monotonic()
    args.workspace.mkdir(parents=True, exist_ok=True)
    if args.snapshot:
        with gzip.open(args.snapshot, 'rt', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = read_snapshot()
        with gzip.open(args.workspace / 'snapshot.json.gz', 'wt', encoding='utf-8') as f:
            json.dump(data, f, default=str, ensure_ascii=False, separators=(',', ':'))
    report = write_model(data, fit(data, geotags(), args.dimensions), args.output, args.workspace)
    print(json.dumps({k: v for k, v in report.items() if k != 'samples'}, indent=2), flush=True)
    print(f'Completed in {time.monotonic() - start:.1f}s; diagnostics: {args.workspace / "report.json"}')


if __name__ == '__main__':
    main()
