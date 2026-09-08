"""Import a pinned Noto subset from a saved DB inventory and local upstream checkout.

No downloads, database writes, or automatic approval of future emoji. Existing
entries are retained so normal data churn cannot invalidate cached clients.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import unicodedata
import regex

ROOT = Path(__file__).resolve().parent

def canonical(value):
    return value.strip().replace('\ufe0f', '').replace('\ufe0e', '')

def run(upstream, inventory, reviewed=None):
    revision = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    used = set()
    if reviewed:
        approved = json.loads(reviewed.read_text())
        if not isinstance(approved, list) or not all(isinstance(e, str) for e in approved):
            raise ValueError('Reviewed input must be a JSON array of emoji strings')
        used.update(approved)
    else:
        for counts in json.loads(inventory.read_text()).values():
            used.update(counts)
    # UI constants and fallback pictograms must have the same artwork coverage.
    ui = set(['📅', '📍', '🏷️', '🎟️', '🔎', '❓'])
    for folder in (() if reviewed else ('src/js', 'src/css', 'src/index.html', 'config')):
        path = ROOT.parent.parent / folder
        files = path.rglob('*') if path.is_dir() else [path]
        for p in files:
            if p.is_file() and p.suffix in ('.js', '.css', '.html', '.yaml'):
                ui.update(g for g in regex.findall(r'\X', p.read_text())
                          if regex.search(r'\p{Extended_Pictographic}|\p{Regional_Indicator}|\u20e3', g))
    used.update(ui)
    aliases = {}
    for filename in ('emoji_aliases.txt', 'unknown_flag_aliases.txt'):
        for line in (upstream / filename).read_text().splitlines():
            line = line.split('#')[0].strip()
            if ';' in line:
                a, b = line.split(';'); aliases[a.strip()] = b.strip()
    existing_path = ROOT / 'noto.json'
    existing = json.loads(existing_path.read_text()) if existing_path.exists() else {'icons': []}
    entries = {e['emoji']: e for e in existing['icons']}
    missing = []
    for raw in sorted(used):
        emoji = canonical(raw)
        if not emoji or emoji in entries: continue
        key = '_'.join(f'{ord(c):04x}' for c in emoji)
        target = key
        seen = set()
        while target in aliases and target not in seen:
            seen.add(target); target = aliases[target]
        # The pinned upstream now provides waved SVG flags as well.
        flag = regex.fullmatch(r'\p{Regional_Indicator}{2}', emoji) is not None or '\U000e0067' in emoji
        candidates = [('third_party/region-flags/waved-svg', 'svg'), ('png/128', 'png'), ('svg', 'svg')] if flag else [('svg', 'svg'), ('png/128', 'png')]
        found = next(((upstream / folder / f'emoji_u{target}.{ext}', ext)
                      for folder, ext in candidates if (upstream / folder / f'emoji_u{target}.{ext}').exists()), None)
        if not found:
            missing.append({'emoji': raw, 'codepoints': key, 'reason': 'No exact upstream artwork/alias'})
            continue
        source, ext = found
        rel = f'noto/emoji_u{target}.{ext}'
        (ROOT/'noto').mkdir(exist_ok=True)
        shutil.copyfile(source, ROOT/rel)
        entries[emoji] = dict(id='noto-'+key.replace('_','-'), emoji=emoji,
            label=' '.join(unicodedata.name(c, f'U+{ord(c):04X}') for c in emoji if ord(c) not in (0x200d,)),
            source=rel, provider='noto', upstream_path=str(source.relative_to(upstream)),
            upstream_revision=revision, sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    doc = {'schema_version':1,'upstream':'https://github.com/googlefonts/noto-emoji',
           'icons':sorted(entries.values(),key=lambda e:e['id'])}
    existing_path.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')
    shutil.copyfile(upstream/'svg/LICENSE', ROOT/'noto/LICENSE')
    shutil.copyfile(upstream/'third_party/region-flags/README.md', ROOT/'noto/REGION-FLAGS-README.txt')
    (ROOT/'noto/NOTICE').write_text(f'Noto Emoji artwork, Copyright Google LLC and contributors.\n'
        f'Upstream https://github.com/googlefonts/noto-emoji at {revision}.\n'
        'SVG/PNG artwork is distributed under Apache-2.0; see LICENSE.\n'
        'Region flag designs originate in upstream third_party/region-flags; see upstream README.\n')
    report = {'catalog_entries':len(entries),'database_and_ui_strings':len(used),'unmatched':missing,
              'upstream_revision':revision}
    ((inventory or reviewed).parent/'import-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='unmatched'},indent=2))
    print('Unmatched:',len(missing))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--upstream',type=Path,required=True)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--inventory',type=Path,help='Initial authorized historical database inventory')
    group.add_argument('--reviewed',type=Path,help='Explicitly reviewed JSON array for subsequent additions')
    a=p.parse_args();run(a.upstream,a.inventory,a.reviewed)
