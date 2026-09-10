"""Offline content similarity for events, places and tags; no DB mutations.

Run via scripts/build_similarity.py. See similarity.md for the artifact contract.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import tempfile
import time
import unicodedata

import numpy as np
from scipy import sparse
from tag_scopes import public_tag_key

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


class FittedModel(tuple):
    """Keep the five-value fitting API, with reusable projection and ragged parts."""


def feature_matrix(counters, vocabulary, idf):
    columns = {key: i for i, key in enumerate(vocabulary)}
    values, indices, offsets = [], [], [0]
    for counts in counters:
        channels = [[], []]
        for key, count in counts.items():
            if key in columns:
                column = columns[key]
                channels[key.startswith('w:')].append((column, (1 + math.log(count)) * idf[column]))
        for channel, weight in zip(channels, [.8, .6]):
            norm = math.sqrt(sum(value * value for _, value in channel)) or 1
            for column, value in channel:
                indices.append(column)
                values.append(weight * value / norm)
        offsets.append(len(values))
    return sparse.csr_matrix((np.asarray(values, dtype=np.float32), indices, offsets),
                             shape=(len(offsets) - 1, len(vocabulary)))


def closest_constituents(matrix, parts, query):
    """Exact maximum cosine over the retained constituents; never their mean."""
    if not len(query):
        return np.zeros(len(parts), dtype=np.float32)
    best = np.full(len(matrix), -1., dtype=np.float32)
    # Bound the temporary matrix even for a tag with thousands of descendants.
    for start in range(0, len(query), 32):
        best = np.maximum(best, (matrix @ query[start:start + 32].T).max(axis=1))
    return np.array([max(best[group], default=0.) for group in parts], dtype=np.float32)


def representatives(indices, vectors, limit):
    """Deterministic farthest-first actual examples, with no synthetic centroids.

    limit=0 retains every constituent. Near-identical examples need one vote.
    """
    if not indices or not limit or len(indices) <= limit:
        return list(indices)
    pool = vectors[indices]
    selected = [0]
    nearest = pool @ pool[0]
    for _ in range(limit - 1):
        next_index = int(np.argmin(nearest))
        if nearest[next_index] >= .985:
            break
        selected.append(next_index)
        nearest = np.maximum(nearest, pool @ pool[next_index])
        nearest[selected] = 1
    return [indices[i] for i in selected]


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
            'tags': 'SELECT id,name,type,emoji,scope FROM tags ORDER BY id',
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
        data['capturedAt'] = datetime.now(timezone.utc).isoformat()
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


def fit(data, geotags=(), dimensions=96, min_df=5, seed=17, max_constituents=12,
        encoder='lexical', workspace=None, model_cache=None):
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
    idf = np.array([math.log((1 + len(rows)) / (1 + df[k])) + 1 for k in vocabulary], dtype=np.float32)
    matrix = feature_matrix((features(kind, item) for kind, item in rows), vocabulary, idf)
    print(f'Fitting latent space: {matrix.shape}, {matrix.nnz:,} nonzero features', flush=True)
    rank = min(dimensions, min(matrix.shape))
    if encoder == 'lexical':
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
    semantic_tags, semantic_projection, semantic_energy = None, None, None
    if encoder == 'minilm':
        from similarity_encoder import content_vectors
        vectors, semantic_tags, semantic_projection, semantic_energy = content_vectors(
            data, rows, attached, excluded, dimensions,
            workspace or ROOT / '.scratch/similarity', model_cache or ROOT / '.scratch/similarity/encoder-cache')
        rank = vectors.shape[1]
    positions = {(kind, item['id']): i for i, (kind, item) in enumerate(rows)}

    # Each venue keeps actual programming examples. Prefer current/recent records
    # of a repeated series, and preserve distinct modes instead of averaging them.
    active = set(data['active_ids'])
    programming = defaultdict(dict)
    for i, (kind, item) in enumerate(rows):
        if kind == 'event' and item['location_id']:
            key = normalize(item['name'])
            programs = programming[item['location_id']]
            previous = programs.get(key)
            if previous is None or (item['id'] in active, item['id']) > (
                    rows[previous][1]['id'] in active, rows[previous][1]['id']):
                programs[key] = i
    entity_parts = [[i] for i in range(len(rows))]
    for pid, programs in programming.items():
        pos = positions.get(('place', pid))
        if pos is not None:
            indices = sorted(programs.values(), key=lambda i: (rows[i][1]['id'] not in active, -rows[i][1]['id']))
            entity_parts[pos] = representatives(indices, vectors, max_constituents)

    # Tag anchors describe the tag itself in the fitted space. Associated event
    # centroids used to erase the defining meaning of heterogeneous interests.
    tag_positions = {t['id']: i for i, t in enumerate(data['tags'])}
    support = np.zeros(len(data['tags']), dtype=np.int32)
    tag_members = defaultdict(dict)
    ancestors = ancestors_for(data['hierarchy'])
    for i, (kind, item) in enumerate(rows):
        direct = attached[kind][item['id']] - excluded
        inherited = set().union(*(ancestors.get(t, set()) for t in direct)) if direct else set()
        for tid in (direct | inherited) - excluded:
            if tid in tag_positions:
                ti = tag_positions[tid]
                support[ti] += 1
                if kind == 'event':
                    key = (item['location_id'], normalize(item['name']))
                    previous = tag_members[ti].get(key)
                    if previous is None or (item['id'] in active, item['id']) > (
                            rows[previous][1]['id'] in active, rows[previous][1]['id']):
                        tag_members[ti][key] = i
    def anchor(tag):
        if tag['id'] in excluded or not support[tag_positions[tag['id']]]:
            return Counter()
        result = Counter({'w:' + word: 3 for word in normalize(tag['name']).split()
                          if len(word) > 2 and word not in STOP and not word.isnumeric()})
        if tag['type'] == 'tag':
            result['t:' + str(tag['id'])] = 1
        return result
    tag_vectors = (semantic_tags if semantic_tags is not None else
                   unit(np.asarray(feature_matrix(map(anchor, data['tags']), vocabulary, idf) @ basis)))
    for i, tag in enumerate(data['tags']):
        if not support[i] or tag['id'] in excluded:
            tag_vectors[i] = 0
    tag_parts = [[len(rows) + i] if support[i] and data['tags'][i]['id'] not in excluded else []
                 for i in range(len(data['tags']))]
    for ti, members in tag_members.items():
        # An anchored topic and its actual member examples are separate ways to
        # match it. Mixed programming is never collapsed into one tag centroid.
        indices = sorted(members.values(), key=lambda i: (rows[i][1]['id'] not in active, -rows[i][1]['id']))
        tag_parts[ti].extend(representatives(indices, vectors, max_constituents))
    for tid, parents in ancestors.items():
        ti = tag_positions.get(tid)
        if ti is None or not tag_parts[ti]:
            continue
        for parent in sorted(parents - excluded):
            pi = tag_positions.get(parent)
            if pi is not None:
                tag_parts[pi].append(len(rows) + ti)
    tag_parts = [sorted(set(group)) for group in tag_parts]
    report = {
        'databaseEvents': len(data['events']), 'trainingEvents': sum(k == 'event' for k, _ in rows),
        'suppressedExcluded': sum(bool(e['suppressed']) for e in data['events']),
        'historicalTrainingEvents': sum(bool(e['archived']) and not e['suppressed'] for e in data['events']),
        'places': len(data['places']), 'tagsAndKeywords': len(data['tags']),
        'features': len(vocabulary), 'dimensions': rank, 'seed': seed,
        'retainedEnergy': (semantic_energy if semantic_energy is not None else
                           float(np.sum(singular[:rank] ** 2) / matrix.multiply(matrix).sum())),
        'zeroEntityVectors': int(np.sum(np.linalg.norm(vectors, axis=1) < .01)),
        'zeroTagVectors': int(np.sum(np.linalg.norm(tag_vectors, axis=1) < .01)),
        'representation': 'closest-constituent-v2', 'maxVenueConstituents': max_constituents,
        'encoder': encoder,
        'affinityThresholds': {'positive': .35, 'negative': .55},
        'venueConstituents': sum(len(entity_parts[i]) for i, (k, _) in enumerate(rows) if k == 'place'),
        'tagConstituents': sum(map(len, tag_parts)),
    }
    result = FittedModel((rows, vectors, tag_vectors, support, report))
    result.parts = entity_parts + tag_parts
    result.projection = semantic_projection or {'vocabulary': np.array(vocabulary), 'idf': idf, 'basis': basis}
    return result


def pack(ids, vectors):
    quantized = np.rint(np.clip(vectors, -1, 1) * 127).astype(np.int8)
    return {'ids': ids, 'vectors': base64.b64encode(quantized.tobytes()).decode('ascii')}


def pack_constituents(ids, parts, matrix, counts):
    """Coalescing browser aliases unions their constituents, never averages them."""
    groups, support = {}, Counter()
    for key, members, count in zip(ids, parts, counts):
        groups.setdefault(key, set()).update(members)
        support[key] += int(count)
    flat, offsets = [], [0]
    for members in groups.values():
        flat.extend(sorted(members))
        offsets.append(len(flat))
    return {**pack(list(groups), matrix[flat]), 'offsets': offsets,
            'support': [support[key] for key in groups]}


def split_block(block, dimensions, chunk_size):
    raw = base64.b64decode(block['vectors'])
    payloads = []
    for start in range(0, len(block['ids']), chunk_size):
        end = min(start + chunk_size, len(block['ids']))
        first, last = block['offsets'][start], block['offsets'][end]
        chunk = {'ids': block['ids'][start:end],
                 'vectors': base64.b64encode(raw[first * dimensions:last * dimensions]).decode('ascii'),
                 'offsets': [n - first for n in block['offsets'][start:end + 1]],
                 'support': block['support'][start:end]}
        payloads.append(json.dumps(chunk, ensure_ascii=False, separators=(',', ':')).encode())
    return payloads


def write_model(data, fitted, output, workspace, validate=None):
    from city_config import get_config
    rows, vectors, tag_vectors, support, report = fitted
    report = dict(report)
    if (vectors.ndim != 2 or not 2 <= vectors.shape[1] <= 256
            or vectors.shape[0] != len(rows)
            or tag_vectors.shape != (len(data['tags']), vectors.shape[1])
            or support.shape != (len(data['tags']),)
            or not np.isfinite(vectors).all() or not np.isfinite(tag_vectors).all()):
        raise ValueError('Invalid fitted model; existing generation was not changed')
    output, workspace = Path(output), Path(workspace)
    output.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    active = set(data['active_ids'])
    matrix = np.concatenate([vectors, tag_vectors])
    parts = getattr(fitted, 'parts', [[i] for i in range(len(matrix))])
    positions = {k: [] for k in ['event', 'place']}
    for i, (kind, item) in enumerate(rows):
        if kind == 'place' or item['id'] in active:
            positions[kind].append(i)
    blocks = {}
    for kind, subset in positions.items():
        ids = [place_key(rows[i][1]) if kind == 'place' else str(rows[i][1]['id']) for i in subset]
        if kind == 'place':
            counts = Counter(e['location_id'] for e in data['events'] if e['id'] in active)
            blocks[kind] = pack_constituents(ids, [parts[i] for i in subset], matrix,
                                              [counts[rows[i][1]['id']] for i in subset])
        else:
            blocks[kind] = pack([], vectors[:0])
    tag_indices = [i for i, tag in enumerate(data['tags']) if tag['type'] == 'tag' and support[i] > 0]
    blocks['tag'] = pack_constituents([normalize(public_tag_key(data['tags'][i]['name'], data['tags'][i].get('scope','event'))) for i in tag_indices],
                                     [parts[len(rows) + i] for i in tag_indices], matrix, support[tag_indices])
    # Venue programming is larger than the tag core. Load only the venue batches
    # used by preferences/suggestions, rather than downloading every program.
    place_block = blocks['place']
    place_payloads = split_block(place_block, vectors.shape[1], 128)
    blocks['place'] = {**place_block, 'vectors': '', 'offsets': [0] * (len(place_block['ids']) + 1)}
    tag_payloads = split_block(blocks['tag'], vectors.shape[1], 64)
    # Topic anchors and every branch are immediately usable. Concrete event
    # examples are fetched only for preferences or requested suggestion tags.
    blocks['tag'] = pack_constituents([normalize(public_tag_key(data['tags'][i]['name'], data['tags'][i].get('scope','event'))) for i in tag_indices],
        [[part for part in parts[len(rows) + i] if part >= len(rows)] for i in tag_indices],
        matrix, support[tag_indices])
    body = {'schemaVersion': 2, 'dimensions': vectors.shape[1],
            'affinityThresholds': report.get('affinityThresholds', {'positive': .35, 'negative': .55}),
            'domain': get_config().get('frontend', {}).get('domain'), 'blocks': blocks}
    payload = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode()
    # Generation digest covers historical vectors too: no mixed-version shards.
    identity = json.dumps({'entities': [(k, item['id']) for k, item in rows],
                           'active': sorted(active)}, separators=(',', ':')).encode()
    digest = hashlib.sha256(payload + identity + b''.join(place_payloads + tag_payloads) + vectors.tobytes()).hexdigest()[:16]
    # Never rewrite files inside an immutable generation, even on a repeat build.
    # Staging also keeps interrupted builds out of the deployable directory tree.
    with tempfile.TemporaryDirectory(prefix='similarity-', dir=workspace) as staging:
        generation = Path(staging)
        (generation / 'core.json').write_bytes(payload)
        for index, encoded in enumerate(place_payloads):
            (generation / f'places-{index}.json').write_bytes(encoded)
        for index, encoded in enumerate(tag_payloads):
            (generation / f'tags-{index}.json').write_bytes(encoded)
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
        report.update({'activeEventVectors': len(positions['event']), 'publicTagVectors': len(blocks['tag']['ids']),
                       'coreBytes': len(payload), 'coreGzipBytes': len(gzip.compress(payload)),
                       'placeBytes': sum(map(len, place_payloads)),
                       'placeGzipBytes': sum(len(gzip.compress(p)) for p in place_payloads),
                       'tagExampleBytes': sum(map(len, tag_payloads)),
                       'tagExampleGzipBytes': sum(len(gzip.compress(p)) for p in tag_payloads),
                       'activeBytes': active_bytes, 'activeGzipBytes': active_gzip, 'generation': digest})
        # All entity/tag vectors and identifiers stay available for offline analysis.
        offsets = np.cumsum([0] + list(map(len, parts)), dtype=np.int32)
        np.savez_compressed(workspace / 'vectors.npz', vectors=vectors, tag_vectors=tag_vectors,
                            part_offsets=offsets, part_indices=np.array([i for group in parts for i in group], dtype=np.int32),
                            entity_ids=np.array([f'{k}:{v["id"]}' for k, v in rows]),
                            tag_ids=np.array([str(t['id']) for t in data['tags']]))
        if hasattr(fitted, 'projection'):
            np.savez_compressed(workspace / 'projection.npz', **fitted.projection)
        report['samples'] = sample_neighbors(data, rows, vectors, tag_vectors, support, parts)
        (workspace / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        if validate is not None:
            validate(workspace)
        manifest = {'schemaVersion': 2, 'generation': digest, 'dimensions': vectors.shape[1],
                    'affinityThresholds': body['affinityThresholds'],
                    'generatedAt': datetime.now(timezone.utc).isoformat(), 'domain': body['domain'],
                    'snapshotCapturedAt': data.get('capturedAt'),
                    'placeShards': list(range(len(place_payloads))),
                    'tagShards': list(range(len(tag_payloads))),
                    'historyShards': sorted(shards), 'activeShards': sorted(active_shards)}
        destination = output / digest
        if destination.exists():
            if ({p.name for p in destination.iterdir()} != {p.name for p in generation.iterdir()}
                    or any(p.read_bytes() != (destination / p.name).read_bytes() for p in generation.iterdir())):
                raise ValueError('Existing immutable generation differs; refusing to overwrite it')
        else:
            generation.rename(destination)
    # Publish the pointer last. Keep previous generations for cached clients.
    with tempfile.NamedTemporaryFile(mode='w', dir=output, suffix='.tmp', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(json.dumps(manifest, separators=(',', ':')))
    try:
        temporary.replace(output / 'manifest.json')
    finally:
        temporary.unlink(missing_ok=True)
    return report


def sample_neighbors(data, rows, vectors, tag_vectors, support, parts=None):
    # Deterministic support-stratified diagnostics, not a relevance benchmark.
    tags = data['tags']
    eligible = [i for i, t in enumerate(tags) if t['type'] == 'tag' and support[i] >= 20]
    eligible.sort(key=lambda i: (-support[i], tags[i]['name']))
    sample = eligible[::max(1, len(eligible) // 12)][:12]
    active = set(data['active_ids'])
    event_indices = [i for i, (k, e) in enumerate(rows) if k == 'event' and e['id'] in active]
    result = []
    matrix = np.concatenate([vectors, tag_vectors])
    for ti in sample:
        query = matrix[parts[len(rows) + ti]] if parts is not None else tag_vectors[ti:ti + 1]
        similarities = closest_constituents(vectors[event_indices], [[i] for i in range(len(event_indices))], query)
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
    parser.add_argument('--max-constituents', type=int, default=12,
                        help='Actual event examples per aggregate; 0 retains all distinct series')
    parser.add_argument('--encoder', choices=['lexical', 'minilm'], default='minilm')
    parser.add_argument('--model-cache', type=Path, default=ROOT / '.scratch/similarity/encoder-cache')
    parser.add_argument('--cases', type=Path, help='Reviewed relevance cases; fail before publication if the gate regresses')
    parser.add_argument('--baseline', type=Path, help='Previous, separate workspace for the relevance gate')
    args = parser.parse_args()
    if not 2 <= args.dimensions <= 256:
        parser.error('--dimensions must be between 2 and 256')
    if args.max_constituents < 0:
        parser.error('--max-constituents must be nonnegative')
    if args.baseline and (not args.cases or args.baseline.resolve() == args.workspace.resolve()):
        parser.error('--baseline requires --cases and a separate workspace')
    from city_config import geotags
    start = time.monotonic()
    args.workspace.mkdir(parents=True, exist_ok=True)
    lock_stream = (args.workspace / 'build.lock').open('a')
    try:
        fcntl.flock(lock_stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.exit(2, 'Another similarity build is using this workspace\n')
    if args.snapshot:
        with gzip.open(args.snapshot, 'rt', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = read_snapshot()
        with gzip.open(args.workspace / 'snapshot.json.gz', 'wt', encoding='utf-8') as f:
            json.dump(data, f, default=str, ensure_ascii=False, separators=(',', ':'))
    def validate(workspace):
        if not args.cases:
            return
        from similarity_eval import EvaluationModel, evaluate, check_gate
        cases = json.loads(args.cases.read_text())
        candidate = evaluate(EvaluationModel(workspace), cases)
        baseline = evaluate(EvaluationModel(args.baseline), cases) if args.baseline else None
        result = {'candidate': candidate, 'baseline': baseline}
        (workspace / 'evaluation.json').write_text(json.dumps(result, indent=2) + '\n')
        check_gate(candidate, baseline)
    report = write_model(data, fit(data, geotags(), args.dimensions, max_constituents=args.max_constituents,
                                  encoder=args.encoder, workspace=args.workspace, model_cache=args.model_cache),
                         args.output, args.workspace, validate=validate)
    print(json.dumps({k: v for k, v in report.items() if k != 'samples'}, indent=2), flush=True)
    print(f'Completed in {time.monotonic() - start:.1f}s; diagnostics: {args.workspace / "report.json"}')
    lock_stream.close()


if __name__ == '__main__':
    main()
