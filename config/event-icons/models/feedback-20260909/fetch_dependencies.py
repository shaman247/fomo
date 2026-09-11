"""Fetch pinned Three.js modules into scratch; does not modify the project venv."""
from pathlib import Path
import hashlib,json,urllib.request
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
for item in json.loads((HERE/'dependencies.json').read_text()):
    folder=ROOT/('.scratch/jazz-trio-3d' if item['name'].startswith('three.') else '.scratch/icon-corrections-20260909/assets/three')
    path=folder/item['name']
    data=path.read_bytes() if path.exists() else urllib.request.urlopen(item['url'],timeout=30).read()
    if hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('Dependency checksum mismatch: '+item['name'])
    folder.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)
    print(item['name'])
