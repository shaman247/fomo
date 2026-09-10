"""Serve a local, read-only explorer of the complete offline similarity model."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import numpy as np

from similarity import closest_constituents, normalize, unit

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).with_name('similarity_viewer')


class ModelIndex:
    def __init__(self, workspace, snapshot=None):
        workspace = Path(workspace)
        with gzip.open(snapshot or workspace / 'snapshot.json.gz', 'rt', encoding='utf-8') as f:
            data = json.load(f)
        self.report = json.loads((workspace / 'report.json').read_text(encoding='utf-8'))
        places = {p['id']: p for p in data['places']}
        events = {e['id']: e for e in data['events']}
        tags = {t['id']: t for t in data['tags']}
        active = set(data['active_ids'])
        self.entities = []
        self.positions = {}
        self.attachments = defaultdict(list)
        with np.load(workspace / 'vectors.npz', allow_pickle=False) as model:
            if model['vectors'].shape[1] != model['tag_vectors'].shape[1]:
                raise ValueError('Entity and tag vector dimensions do not match')
            self.vectors = unit(np.concatenate([model['vectors'], model['tag_vectors']]).astype(np.float32))
            keys = list(model['entity_ids']) + ['tag:' + tid for tid in model['tag_ids']]
            if 'part_offsets' in model:
                offsets, indices = model['part_offsets'], model['part_indices']
                if len(offsets) != len(keys) + 1 or offsets[0] != 0 or offsets[-1] != len(indices):
                    raise ValueError('Invalid constituent offsets')
                if np.any(np.diff(offsets) < 0) or np.any(indices < 0) or np.any(indices >= len(keys)):
                    raise ValueError('Invalid constituent indices')
                self.parts = [indices[start:end].copy() for start, end in zip(offsets, offsets[1:])]
            else:
                self.parts = [[i] for i in range(len(keys))]
        if len(keys) != len(self.vectors):
            raise ValueError('Model identifiers and vectors do not match')
        for key in keys:
            kind, raw_id = str(key).split(':', 1)
            source = {'event': events, 'place': places, 'tag': tags}[kind][int(raw_id)]
            context = source.get('address', '') if kind == 'place' else (
                places.get(source.get('location_id'), {}).get('name', '') if kind == 'event' else '')
            item = {'key': str(key), 'id': int(raw_id), 'type': kind, 'name': source['name'],
                    'context': context or '', 'description': source.get('description') or '',
                    'subtype': source.get('type') if kind == 'tag' else None,
                    'active': int(raw_id) in active if kind == 'event' else None,
                    'archived': bool(source.get('archived')) if kind == 'event' else None,
                    'emoji': source.get('emoji') or {'event': '🎟️', 'place': '📍', 'tag': '🏷️'}[kind]}
            self.positions[str(key)] = len(self.entities)
            self.entities.append(item)
        usable = np.linalg.norm(self.vectors, axis=1) > .01
        self.has_vector = np.array([any(usable[group]) for group in self.parts])
        self.search_text = [normalize(item['name'] + ' ' + item['context']) for item in self.entities]
        self.names = [normalize(item['name']) for item in self.entities]
        self.groups = {kind: np.array([i for i, e in enumerate(self.entities) if e['type'] == kind], dtype=np.int32)
                       for kind in ['event', 'place', 'tag']}
        for relation, kind, field in [('event_tags', 'event', 'event_id'), ('place_tags', 'place', 'location_id')]:
            for row in data[relation]:
                key = f'{kind}:{row[field]}'
                if key in self.positions and row['tag_id'] in tags:
                    self.attachments[key].append(f'tag:{row["tag_id"]}')
        counts = Counter(key for values in self.attachments.values() for key in values)
        examples = sorted((e for e in self.entities if e['type'] == 'tag' and e['subtype'] == 'tag'
                           and self.has_vector[self.positions[e['key']]]),
                          key=lambda e: (-counts[e['key']], e['name']))[:8]
        self.metadata = {key: self.report.get(key) for key in [
            'generation', 'trainingEvents', 'historicalTrainingEvents', 'places', 'tagsAndKeywords', 'dimensions']}
        self.metadata.update({'entities': len(self.entities), 'supportedEntities': int(self.has_vector.sum()),
                              'examples': [self.summary(e) for e in examples]})
        # Use the same signed-int8 roundtrip as the browser when requested.
        self.quantized = unit(np.rint(self.vectors * 127).astype(np.float32) / 127)

    def summary(self, item):
        return {**{k: v for k, v in item.items() if k != 'description'},
                'hasVector': bool(self.has_vector[self.positions[item['key']]])}

    def detail(self, key):
        index = self.positions.get(key)
        if index is None:
            raise KeyError('Entity is not in this model snapshot')
        item = self.entities[index]
        return {**self.summary(item), 'description': item['description'],
                'constituentCount': len(self.parts[index]),
                'tags': [self.summary(self.entities[self.positions[tag]])
                         for tag in self.attachments[key] if tag in self.positions]}

    def search(self, query, kind='all', offset=0, limit=30):
        if kind not in ['all', 'event', 'place', 'tag', 'keyword']:
            raise ValueError('Invalid search type')
        query = normalize(query)
        if not query:
            return {'items': [], 'total': 0}
        matches = []
        for i, item in enumerate(self.entities):
            if kind == 'keyword' and item['subtype'] != 'keyword':
                continue
            if kind == 'tag' and item['subtype'] != 'tag':
                continue
            if kind in ['event', 'place'] and item['type'] != kind:
                continue
            if query in self.search_text[i] or query == str(item['id']) or query == normalize(item['key']):
                matches.append(i)
        matches.sort(key=lambda i: (self.names[i] != query, not self.names[i].startswith(query),
                                    not bool(self.has_vector[i]), self.names[i], self.entities[i]['key']))
        return {'items': [self.summary(self.entities[i]) for i in matches[offset:offset + limit]],
                'total': len(matches)}

    def neighbors(self, key, limit=100, events='active', tags='curated', precision='full', minimum=0):
        if events not in ['active', 'history', 'all'] or tags not in ['curated', 'keywords', 'all']:
            raise ValueError('Invalid candidate filter')
        if precision not in ['full', 'browser'] or not np.isfinite(minimum) or not -1 <= minimum <= 1:
            raise ValueError('Invalid score options')
        seed = self.detail(key)
        index = self.positions[key]
        groups = {}
        matrix = self.quantized if precision == 'browser' else self.vectors
        # Same maximum-over-constituents rule as the browser, over the full index.
        scores = np.clip(closest_constituents(matrix, self.parts, matrix[self.parts[index]]), -1, 1)
        for kind, candidates in self.groups.items():
            eligible = []
            if self.has_vector[index]:
                for i in candidates:
                    item = self.entities[i]
                    if i == index or not self.has_vector[i] or scores[i] < minimum:
                        continue
                    if kind == 'event' and events != 'all':
                        if events == 'active' and not item['active']:
                            continue
                        if events == 'history' and item['active']:
                            continue
                    if kind == 'tag' and tags != 'all' and item['subtype'] != ('tag' if tags == 'curated' else 'keyword'):
                        continue
                    eligible.append(int(i))
            eligible.sort(key=lambda i: (-float(scores[i]), self.entities[i]['key']))
            groups[kind] = {'total': len(eligible), 'items': [
                {**self.summary(self.entities[i]), 'score': round(float(scores[i]), 6)} for i in eligible[:limit]]}
        return {'seed': seed, 'groups': groups, 'precision': precision,
                'generation': self.report.get('generation')}


def handler_for(model):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, content_type='application/json; charset=utf-8'):
            encoded = json.dumps(body, ensure_ascii=False).encode() if not isinstance(body, bytes) else body
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(encoded)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            # Loopback-only service; do not expose the offline snapshot through a
            # rebinding hostname or serve arbitrary files from the workspace.
            hostname = urlsplit('http://' + self.headers.get('Host', '')).hostname
            if hostname not in ['127.0.0.1', 'localhost']:
                return self.send(403, {'error': 'Local access only'})
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            get = lambda key, default='': query.get(key, [default])[0]
            try:
                if parsed.path == '/api/meta':
                    return self.send(200, model.metadata)
                if parsed.path == '/api/search':
                    return self.send(200, model.search(get('q'), get('type', 'all'),
                                                      max(0, int(get('offset', '0'))), 30))
                if parsed.path == '/api/neighbors':
                    return self.send(200, model.neighbors(get('entity'), min(250, max(1, int(get('limit', '100')))),
                        get('events', 'active'), get('tags', 'curated'), get('precision', 'full'),
                        float(get('minimum', '0'))))
                static = {'/': ('index.html', 'text/html; charset=utf-8'),
                          '/viewer.js': ('viewer.js', 'text/javascript; charset=utf-8'),
                          '/viewer.css': ('viewer.css', 'text/css; charset=utf-8')}
                if parsed.path in static:
                    name, mime = static[parsed.path]
                    return self.send(200, (ASSETS / name).read_bytes(), mime)
                return self.send(404, {'error': 'Not found'})
            except (ValueError, KeyError) as error:
                return self.send(400, {'error': str(error).strip("'")})

        def log_message(self, *_):
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=ROOT / '.scratch/similarity')
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    print('Loading the offline model and entity names…', flush=True)
    try:
        model = ModelIndex(args.workspace, args.snapshot)
    except (OSError, KeyError, ValueError) as error:
        parser.exit(1, f'Cannot load model: {error}. Build it with ./venv/bin/python pipeline/similarity.py\n')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(model))
    print(f'Model explorer: http://127.0.0.1:{args.port}/ ({len(model.entities):,} entities)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
