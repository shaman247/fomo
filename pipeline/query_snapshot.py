"""Hash the complete published search inventory; contains no DB or model calls."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def write_query_snapshot(directory, city_id=None):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    chunks = [f'day{i}' for i in range(len(manifest['days']))] + manifest.get('remainderChunks', ['remainder'])
    names = {'manifest.json', 'tag_hierarchy.json', 'organizers.json'}
    for chunk in chunks:
        names.update((f'events.{chunk}.json', f'events.{chunk}.desc.json',
                      f"locations.{'remainder' if chunk.startswith('remainder') else chunk}.json"))
    files = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in sorted(names)}
    revision = hashlib.sha256(json.dumps(files, separators=(',', ':')).encode()).hexdigest()
    result = {'version': 1, 'cityId': city_id or os.getenv('FOMO_CITY', 'nyc'),
              'generatedAt': datetime.now(timezone.utc).isoformat(),
              'sourceExportedAt': manifest.get('exportedAt'), 'revision': revision, 'files': files}
    schema = Path(__file__).resolve().parent.parent / 'src/js/query/query.schema.json'
    (directory / 'query.schema.json').write_bytes(schema.read_bytes())
    temporary = directory / 'query-manifest.json.tmp'
    temporary.write_text(json.dumps(result, separators=(',', ':')))
    temporary.replace(directory / 'query-manifest.json')
    return result
