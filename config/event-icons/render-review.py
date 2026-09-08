"""Render a local, reproducible visual-critique packet. No model or DB calls.

Run with the project venv. Uses its existing Playwright/Chromium installation.
The agent must inspect the PNGs and write a critique; rendering is not approval.
"""
import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ids', nargs='+', required=True)
    parser.add_argument('--references', nargs='*', default=['game-dominoes', 'game-scrabble'])
    parser.add_argument('--reference-files', nargs='*', type=Path, default=[])
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--catalog', type=Path, default=ROOT / 'catalog.json',
                        help='Optional draft catalog; absolute source paths support unregistered prototypes')
    args = parser.parse_args()
    catalog = {i['id']: i for i in json.loads(args.catalog.read_text())['icons']}
    if len(set(args.ids)) != len(args.ids):
        parser.error('Duplicate candidate IDs')
    unknown = set(args.ids + args.references) - catalog.keys()
    if unknown:
        parser.error('Unknown IDs: ' + ', '.join(sorted(unknown)))
    entries = []
    for kind, ids in [('candidate', args.ids), ('reference', [i for i in args.references if i not in args.ids])]:
        for index, icon_id in enumerate(ids, 1):
            entry = catalog[icon_id]
            entries.append((f'{kind.title()} {index}', icon_id, entry['label'], ROOT / entry['source']))
    for index, path in enumerate(args.reference_files, 1):
        entries.append((f'External reference {index}', None, path.stem, path.resolve()))

    manifest, cards = [], []
    for key, icon_id, label, path in entries:
        raw = path.read_bytes()
        manifest.append(dict(key=key, id=icon_id, label=label, source=str(path),
                             sha256=hashlib.sha256(raw).hexdigest()))
        url = 'data:image/svg+xml;base64,' + base64.b64encode(raw).decode()
        rows = []
        for theme in ['light', 'dark']:
            cells = ''.join(f'<div><img src="{url}" width="{size}" height="{size}"><small>{size}px</small></div>'
                            for size in [128, 32, 24, 16])
            rows.append(f'<div class="row {theme}">{cells}</div>')
        cards.append(f'<article><h2>{html.escape(key)}<span class="meaning"> · {html.escape(label)}</span></h2>{"".join(rows)}</article>')
    document = '''<!doctype html><meta charset="utf-8"><title>Icon visual review</title>
<style>
*{box-sizing:border-box}body{margin:0;padding:24px;width:760px;background:#dfe3e8;font:14px Arial;color:#24272c}
h1{font-size:21px;margin:0 0 8px}p{margin:0 0 18px}article{margin:0 0 16px;border-radius:10px;overflow:hidden}
h2{font-size:15px;margin:0;padding:10px 16px;background:#cbd1d9}.row{display:grid;grid-template-columns:210px repeat(3,1fr);align-items:center;padding:10px 20px;gap:14px}
.row>div{height:153px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:8px}
.light{background:#fff;color:#333}.dark{background:#20242c;color:#eee}small{font-size:11px}img{display:block}.meaning{display:none}
</style><h1>Icon visual critique</h1><p>Identify each candidate before reading its label. Inspect at native display size.</p>''' + ''.join(cards)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'sheet.html').write_text(document)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 760, 'height': 900}, device_scale_factor=1)
        page.set_content(document)
        page.evaluate('async () => { await Promise.all([...document.images].map(i => i.decode())); }')
        page.screenshot(path=str(args.output / 'blind.png'), full_page=True)
        page.add_style_tag(content='.meaning{display:inline}')
        page.screenshot(path=str(args.output / 'labeled.png'), full_page=True)
        browser.close()
    (args.output / 'manifest.json').write_text(json.dumps(dict(
        sizes=[128, 32, 24, 16], device_scale_factor=1, backgrounds=['#ffffff', '#20242c'],
        entries=manifest), indent=2))
    print(f'Rendered {len(args.ids)} candidates and {len(entries)-len(args.ids)} references to {args.output}')


if __name__ == '__main__':
    main()
