"""
Summarize and triage client-side errors reported by the frontend ErrorReporter.

src/js/core/errorReporter.js beacons uncaught errors, unhandled rejections and
console.error calls to src/api/client_errors.php, which appends JSON lines to
~/client_errors/client_errors.log (outside the web root) on the server. This
reads that log over SSH (.env SSH_HOST/SSH_USER/SSH_PORT/SSH_KEY) — or a local
copy with --file — and prints one row per distinct error with its device spread.

Each distinct error gets a short signature that survives redeploys (numbers in
the message and the bundle hash/line:col are normalized away). Verdicts are kept
in a local triage file (default .claude/client-error-triage.json):

    ignored  noise we accept (extensions, ancient browsers, network flakes)
    backlog  real, filed for later — `--note` names the backlog item
    fixed    fixed; every bundle already in the log (from any error) counts as
             pre-fix, except --fixed-in <bundle>, so a report from the fixed
             bundle or any bundle first seen later resurfaces it as RECURRED

Untriaged and recurred errors are shown by default; --all shows everything.

Reports from automated traffic (crawlers, webdriver, link-preview renderers
borrowing a phone UA at desktop size) are kept but tagged; only real traffic is
shown unless --traffic automated|all. Lines logged before the tag existed are
classified here with the same rule as beacon_traffic() in src/api/beacon_lib.php.
The weekly review procedure lives in .claude/recurring-checks.md.

Usage:
    ./venv/bin/python scripts/client_errors.py                  # last 7 days, needs-attention only
    ./venv/bin/python scripts/client_errors.py --days 30 --all
    ./venv/bin/python scripts/client_errors.py --bundle 631d680d
    ./venv/bin/python scripts/client_errors.py --traffic automated   # what crawlers and renderers hit
    ./venv/bin/python scripts/client_errors.py --show 3f2a9c1b0d    # stacks + bundle code around the frame
    ./venv/bin/python scripts/client_errors.py --mark 3f2a9c1b0d --verdict fixed --fixed-in 897bb182 --note "e421e41"
    ./venv/bin/python scripts/client_errors.py --file path/to/client_errors.log

Exit status: 0 nothing needs attention, 1 new or recurred errors, 2 read failure.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REMOTE_LOGS = '~/client_errors/client_errors.log.1 ~/client_errors/client_errors.log'
DEFAULT_TRIAGE = os.path.join(PROJECT_ROOT, '.claude', 'client-error-triage.json')
VERDICTS = ('ignored', 'backlog', 'fixed')


def fetch_remote():
    load_dotenv(os.path.join(PROJECT_ROOT, '.env'))
    host, user = os.getenv('SSH_HOST'), os.getenv('SSH_USER')
    if not host or not user:
        print('SSH_HOST/SSH_USER missing from .env (or pass --file)', file=sys.stderr)
        sys.exit(2)
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=20', '-p', os.getenv('SSH_PORT', '22')]
    if os.getenv('SSH_KEY'):
        command += ['-i', os.path.join(PROJECT_ROOT, os.getenv('SSH_KEY'))]
    command += [f'{user}@{host}', f'cat {REMOTE_LOGS} 2>/dev/null; true']
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f'ssh failed: {result.stderr.strip()}', file=sys.stderr)
        sys.exit(2)
    return result.stdout


def signature(entry):
    """Stable id for 'the same error': numbers in the message, the bundle hash and
    line:col change across DPRs and deploys, so normalize them away."""
    message = re.sub(r'\d+(\.\d+)?', 'N', entry.get('message', ''))
    source = re.sub(r'(:\d+)+$', '', entry.get('source', ''))
    source = re.sub(r'^app\.[0-9a-f]{8}\.js$', 'app.js', source)
    key = f"{entry.get('kind', '')}|{message}|{source}"
    return hashlib.sha1(key.encode()).hexdigest()[:10]


BOT_UA = re.compile(r'(?<!cu)bot\b|bot/|crawl|spider|slurp|headless|lighthouse|phantomjs|puppeteer|playwright|selenium|'
                    r'python|curl|wget|httpclient|preview|facebookexternalhit|bytespider', re.I)


def width_of(size):
    match = re.fullmatch(r'(\d{1,5})x\d{1,5}', size or '')
    return int(match.group(1)) if match else 0


def traffic_of(entry):
    """(class, reason) — the logged tag, or the beacon_traffic() rule for older lines."""
    if entry.get('traffic'):
        return entry['traffic'], entry.get('traffic_reason', '')
    ua = entry.get('ua', '')
    if not ua:
        return 'automated', 'no-ua'
    if BOT_UA.search(ua):
        return 'automated', 'bot-ua'
    phone = re.search(r'iPhone|iPod', ua) or re.search(r'Android.*Mobile', ua)
    if phone and max(width_of(entry.get('viewport')), width_of(entry.get('screen'))) >= 1024:
        return 'automated', 'phone-ua-desktop-size'
    return 'real', ''


def browser_of(ua):
    """Coarse 'Browser/OS' label from a user agent."""
    os_name = next((name for pattern, name in (
        (r'iPhone|iPad|iPod', 'iOS'), (r'Android', 'Android'), (r'Windows', 'Windows'),
        (r'Mac OS X|Macintosh', 'macOS'), (r'CrOS', 'ChromeOS'), (r'Linux', 'Linux'),
    ) if re.search(pattern, ua)), '?')
    browser = next((name for pattern, name in (
        (r'Edg/', 'Edge'), (r'OPR/', 'Opera'), (r'SamsungBrowser', 'Samsung'), (r'Firefox|FxiOS', 'Firefox'),
        (r'Chrome|CriOS', 'Chrome'), (r'Safari', 'Safari'),
    ) if re.search(pattern, ua)), '?')
    if re.search(r'; wv\)|FBAN|Instagram', ua):
        browser += '(webview)'
    return f'{browser}/{os_name}'


def top(counter, n=3):
    return ', '.join(f'{k}×{v}' if v > 1 else str(k) for k, v in counter.most_common(n)) + (
        f' +{len(counter) - n}' if len(counter) > n else '')


def load_triage(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def status_of(entries, verdict):
    """'new', 'recurred', or the stored verdict."""
    if not verdict:
        return 'new'
    if verdict['verdict'] == 'fixed':
        seen_at_fix = set(verdict.get('bundles', []))
        if any(e.get('bundle') not in seen_at_fix for e in entries):
            return 'recurred'
    return verdict['verdict']


def site_domain():
    """frontend.domain from the active city config, for fetching deployed bundles."""
    city = os.getenv('FOMO_CITY', 'nyc')
    with open(os.path.join(PROJECT_ROOT, 'config', f'{city}.yaml'), encoding='utf-8') as f:
        match = re.search(r'^\s+domain:\s*"?([^"\s#]+)', f.read(), re.MULTILINE)
    return match.group(1) if match else None


def show_bundle_context(entry, width=240):
    """Print the minified bundle code around the first app-bundle frame."""
    bundle = entry.get('bundle', '')
    if not re.fullmatch(r'[0-9a-f]{8}', bundle):
        print(f'       (bundle {bundle!r} is not a deployed build; no code context)')
        return
    frames = [entry.get('source', '')] + entry.get('stack', '').splitlines()
    position = next((m for m in (re.search(r'app\.[0-9a-f]{8}\.js:(\d+):(\d+)', f) for f in frames) if m), None)
    if not position:
        print('       (no app-bundle frame in source/stack — the error is in vendor or eval code)')
        return
    url = f'https://{site_domain()}/app.{bundle}.js'
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            lines = response.read().decode('utf-8', 'replace').split('\n')
    except Exception as exc:
        print(f'       (could not fetch {url}: {exc})')
        return
    line, col = int(position.group(1)), int(position.group(2))
    text = lines[line - 1] if 0 < line <= len(lines) else ''
    start = max(0, col - 1 - width // 2)
    print(f'       code at app.{bundle}.js:{line}:{col}:')
    print(f'         …{text[start:col - 1]}⟦{text[col - 1:col + 39]}⟧{text[col + 39:start + width]}…')


def main():
    parser = argparse.ArgumentParser(description='Summarize and triage distinct client-side errors')
    parser.add_argument('--file', help='Read a local log instead of fetching over SSH')
    parser.add_argument('--days', type=float, default=7, help='Only reports from the last N days (default 7)')
    parser.add_argument('--bundle', help='Only reports from this bundle hash')
    parser.add_argument('--traffic', choices=('real', 'automated', 'all'), default='real',
                        help='Which traffic to show (default real; automated = crawlers and renderers)')
    parser.add_argument('--all', action='store_true', help='Include ignored, backlog and fixed errors')
    parser.add_argument('--show', metavar='SIG', help='Details for one signature: sample stacks + bundle code')
    parser.add_argument('--mark', metavar='SIG', help='Record a verdict for a signature (with --verdict)')
    parser.add_argument('--verdict', choices=VERDICTS)
    parser.add_argument('--note', default='', help='Why / where (backlog item, fixing commit)')
    parser.add_argument('--fixed-in', metavar='BUNDLE', help='With --verdict fixed: the bundle carrying the fix (never counted as pre-fix)')
    parser.add_argument('--triage-file', default=DEFAULT_TRIAGE, help='Verdict store (default %(default)s)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show a sample stack for each error')
    args = parser.parse_args()
    if bool(args.mark) != bool(args.verdict):
        parser.error('--mark and --verdict go together')

    text = open(args.file, encoding='utf-8').read() if args.file else fetch_remote()
    # Marking looks at the whole log so a fix records every bundle that ever hit it.
    since = datetime.now(timezone.utc) - timedelta(days=36500 if args.mark else args.days)
    groups = defaultdict(list)
    skipped = 0
    by_traffic = Counter()
    for line in text.splitlines():
        try:
            entry = json.loads(line)
            seen_at = datetime.strptime(entry['t'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        except (ValueError, KeyError):
            skipped += 1
            continue
        if seen_at < since or (args.bundle and entry.get('bundle') != args.bundle):
            continue
        entry['_traffic'], entry['_reason'] = traffic_of(entry)
        by_traffic[entry['_traffic']] += 1
        if args.traffic != 'all' and entry['_traffic'] != args.traffic and not args.mark:
            continue
        entry['_at'] = seen_at
        groups[signature(entry)].append(entry)

    triage = load_triage(args.triage_file)

    if args.mark:
        entries = groups.get(args.mark)
        if not entries and args.mark not in triage:
            print(f'No reports with signature {args.mark}', file=sys.stderr)
            return 2
        entries = entries or []
        triage[args.mark] = {
            'verdict': args.verdict,
            'note': args.note,
            'date': date.today().isoformat(),
            **({'fixed_in': args.fixed_in} if args.fixed_in else {}),
            'message': entries[-1]['message'] if entries else triage[args.mark].get('message', ''),
            # For a fix, every bundle already in the log (from any error) runs pre-fix code,
            # except the one named by --fixed-in; only that bundle or a later one can recur.
            'bundles': sorted((
                ({e.get('bundle', '') for group in groups.values() for e in group} if args.verdict == 'fixed'
                 else {e.get('bundle', '') for e in entries})
                | set(triage.get(args.mark, {}).get('bundles', []))) - {args.fixed_in}),
        }
        os.makedirs(os.path.dirname(os.path.abspath(args.triage_file)), exist_ok=True)
        with open(args.triage_file, 'w', encoding='utf-8') as f:
            json.dump(triage, f, indent=2, sort_keys=True)
            f.write('\n')
        print(f"{args.mark}: {args.verdict}" + (f" ({args.note})" if args.note else '')
              + f" — bundles seen so far: {', '.join(triage[args.mark]['bundles']) or 'none'}")
        return 0

    rows = []
    for sig, entries in groups.items():
        state = status_of(entries, triage.get(sig))
        if args.show and sig != args.show:
            continue
        if not (args.all or args.show) and state not in ('new', 'recurred'):
            continue
        rows.append((sig, state, entries))
    rows.sort(key=lambda r: (r[1] not in ('new', 'recurred'), -len(r[2]), r[0]))

    total = sum(len(v) for v in groups.values())
    attention = sum(1 for sig, entries in groups.items() if status_of(entries, triage.get(sig)) in ('new', 'recurred'))
    print(f"{args.traffic if args.traffic != 'all' else 'all'} traffic: "
          f'{total} reports, {len(groups)} distinct errors in the last {args.days:g} days'
          + (f' (bundle {args.bundle})' if args.bundle else '')
          + f'; {attention} need attention' + (f'; {skipped} unparseable lines' if skipped else ''))
    other = {'real': 'automated', 'automated': 'real'}.get(args.traffic)
    if other and by_traffic[other]:
        print(f'  ({by_traffic[other]} {other}-traffic reports hidden; --traffic {other} or all to see them)')
    if args.show and not rows:
        print(f'No reports with signature {args.show} in that window')

    for sig, state, entries in rows:
        dprs = Counter(f"{e['dpr']:g}" if isinstance(e.get('dpr'), (int, float)) else '?' for e in entries)
        zones = Counter(e.get('tz') or '?' for e in entries)
        bundles = Counter(e.get('bundle') or '?' for e in entries)
        browsers = Counter(browser_of(e.get('ua', '')) for e in entries)
        sources = Counter(e.get('source') for e in entries if e.get('source'))
        first, last = min(e['_at'] for e in entries), max(e['_at'] for e in entries)
        verdict = triage.get(sig, {})
        label = state.upper() if state in ('new', 'recurred') else state
        print(f"\n{sig} {label:<8} {len(entries):>4}× [{entries[-1].get('kind', '')}] {entries[-1].get('message', '')[:150]}")
        if verdict.get('note'):
            print(f"       note: {verdict['note']} ({verdict.get('date', '')})")
        if sources:
            print(f'       at {top(sources, 2)}')
        print(f"       {first:%m-%d %H:%M} → {last:%m-%d %H:%M} UTC | dpr {top(dprs)} | tz {top(zones)}")
        print(f"       {top(browsers)} | bundle {top(bundles)}")
        if args.traffic != 'real':
            reasons = Counter(e['_reason'] or 'real' for e in entries)
            print(f"       traffic {top(reasons)}")
        if args.show:
            viewports = Counter(e.get('viewport') or '?' for e in entries)
            print(f"       viewport {top(viewports, 5)}")
            for ua, count in Counter(e.get('ua', '') for e in entries).most_common(3):
                print(f'       ua ×{count}: {ua}')
            show_bundle_context(entries[-1])
        if (args.verbose or args.show) and entries[-1].get('stack'):
            for frame in entries[-1]['stack'].splitlines()[:6]:
                print(f'         {frame}')
    return 1 if attention else 0


if __name__ == '__main__':
    sys.exit(main())
