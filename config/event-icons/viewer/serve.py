"""Local custom-art gallery with per-icon feedback saved to a JSON file.

Run: ./venv/bin/python config/event-icons/viewer/serve.py
Only the viewer, registered SVGs, and selected theme/font files are served.
"""
import argparse
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from datetime import datetime, timezone
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ICONS = HERE.parent
REPO = ICONS.parent.parent
STATUSES = {'unreviewed', 'good', 'redo', 'unsure'}


def make_server(port, feedback_path):
    entries = [dict(i, kind='catalog') for i in json.loads((ICONS / 'catalog.json').read_text())['icons']
               if i.get('provider', 'custom') == 'custom']
    prototype = ICONS / 'prototypes/jazz-trio-projected.svg'
    if prototype.exists():
        entries.append(dict(id='prototype-jazz-trio-projected', label='Jazz trio · 3D prototype',
                            source='prototypes/jazz-trio-projected.svg', kind='prototype'))
    assets = {}
    for entry in entries:
        source = (ICONS / entry['source']).resolve()
        if not source.is_relative_to(ICONS) or source.suffix != '.svg':
            raise ValueError(f'Invalid icon source: {source}')
        raw = source.read_bytes()
        entry.update(sha256=hashlib.sha256(raw).hexdigest(), raw_bytes=len(raw),
                     gzip_bytes=len(gzip.compress(raw, compresslevel=6, mtime=0)),
                     url=f'/icons/{entry["id"]}.svg')
        assets[entry['url']] = ('image/svg+xml', raw)
    by_id = {i['id']: i for i in entries}
    token = secrets.token_urlsafe(32)
    lock = threading.Lock()
    # Invalid existing feedback is an error: never replace it with an empty file.
    state = json.loads(feedback_path.read_text()) if feedback_path.exists() else {
        'schema_version': 1, 'reviews': {}}
    if state.get('schema_version') != 1 or not isinstance(state.get('reviews'), dict):
        raise ValueError('Unsupported feedback file')
    static = {
        '/': (HERE / 'index.html', 'text/html; charset=utf-8'),
        '/viewer.css': (HERE / 'viewer.css', 'text/css'),
        '/viewer.js': (HERE / 'viewer.js', 'text/javascript'),
        '/variables.css': (REPO / 'src/css/variables.css', 'text/css'),
        '/inter.woff2': (REPO / 'src/fonts/inter/InterVariable.woff2', 'font/woff2'),
    }

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, data, content_type='application/json'):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self'; style-src 'self'; font-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def json_reply(self, status, data):
            self.reply(status, json.dumps(data).encode())

        def valid_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}',
                                               f'localhost:{self.server.server_port}'}

        def do_GET(self):
            if not self.valid_host():
                return self.json_reply(403, {'error': 'Invalid host'})
            path = urlsplit(self.path).path
            if path in static:
                file, mime = static[path]
                return self.reply(200, file.read_bytes(), mime)
            if path in assets:
                mime, raw = assets[path]
                return self.reply(200, raw, mime)
            if path == '/api/catalog':
                return self.json_reply(200, {'icons': entries, 'token': token})
            if path == '/api/feedback':
                with lock:
                    return self.json_reply(200, state)
            return self.json_reply(404, {'error': 'Not found'})

        def do_POST(self):
            if (not self.valid_host() or self.headers.get('X-Viewer-Token') != token
                    or self.headers.get('Content-Type') != 'application/json'):
                return self.json_reply(403, {'error': 'Invalid viewer request'})
            if self.path != '/api/feedback':
                return self.json_reply(404, {'error': 'Not found'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 50000:
                    raise ValueError('Invalid request length')
                data = json.loads(self.rfile.read(length))
                entry = by_id.get(data.get('id'))
                if not entry or data.get('status') not in STATUSES:
                    raise ValueError('Unknown icon or review status')
                if not isinstance(data.get('notes'), str) or len(data['notes']) > 10000:
                    raise ValueError('Notes must be text, at most 10,000 characters')
                if data.get('sha256') != entry['sha256']:
                    raise ValueError('Artwork changed; reload before reviewing')
                record = dict(icon_id=entry['id'], label=entry['label'], source=entry['source'],
                              source_sha256=entry['sha256'], status=data['status'], notes=data['notes'],
                              updated_at=datetime.now(timezone.utc).isoformat())
                with lock:
                    updated = dict(state, reviews={**state['reviews'], entry['id']: record})
                    feedback_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = feedback_path.with_suffix('.json.tmp')
                    temporary.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + '\n')
                    temporary.replace(feedback_path)
                    state.update(updated)
                self.json_reply(200, record)
            except (ValueError, TypeError, AttributeError) as error:
                self.json_reply(400, {'error': str(error)})
            except OSError:
                self.json_reply(500, {'error': 'Could not save feedback to disk'})

        def log_message(self, format, *args):
            if args and str(args[1]) not in {'200', '304'}:
                super().log_message(format, *args)

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--feedback', type=Path, default=REPO / '.scratch/icon-viewer/feedback.json')
    args = parser.parse_args()
    server = make_server(args.port, args.feedback.resolve())
    print(f'Icon viewer: http://127.0.0.1:{server.server_port}', flush=True)
    print(f'Feedback: {args.feedback.resolve()}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
