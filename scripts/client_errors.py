"""
Summarize client-side errors reported by the frontend ErrorReporter.

src/js/core/errorReporter.js beacons uncaught errors, unhandled rejections and
console.error calls to src/api/client_errors.php, which appends JSON lines to
~/client_errors/client_errors.log (outside the web root) on the server. This
reads that log over SSH (.env SSH_HOST/SSH_USER/SSH_PORT/SSH_KEY) — or a local
copy with --file — and prints one row per distinct error with its device spread.

Usage:
    ./venv/bin/python scripts/client_errors.py              # last 7 days
    ./venv/bin/python scripts/client_errors.py --days 1
    ./venv/bin/python scripts/client_errors.py --bundle 631d680d
    ./venv/bin/python scripts/client_errors.py --file path/to/client_errors.log
    ./venv/bin/python scripts/client_errors.py --verbose    # + a sample stack per error
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REMOTE_LOGS = '~/client_errors/client_errors.log.1 ~/client_errors/client_errors.log'


def fetch_remote():
    load_dotenv(os.path.join(PROJECT_ROOT, '.env'))
    host, user = os.getenv('SSH_HOST'), os.getenv('SSH_USER')
    if not host or not user:
        sys.exit('SSH_HOST/SSH_USER missing from .env (or pass --file)')
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=20', '-p', os.getenv('SSH_PORT', '22')]
    if os.getenv('SSH_KEY'):
        command += ['-i', os.path.join(PROJECT_ROOT, os.getenv('SSH_KEY'))]
    command += [f'{user}@{host}', f'cat {REMOTE_LOGS} 2>/dev/null; true']
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        sys.exit(f'ssh failed: {result.stderr.strip()}')
    return result.stdout


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


def main():
    parser = argparse.ArgumentParser(description='Summarize distinct client-side errors')
    parser.add_argument('--file', help='Read a local log instead of fetching over SSH')
    parser.add_argument('--days', type=float, default=7, help='Only reports from the last N days (default 7)')
    parser.add_argument('--bundle', help='Only reports from this bundle hash')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show a sample stack for each error')
    args = parser.parse_args()

    text = open(args.file, encoding='utf-8').read() if args.file else fetch_remote()
    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    groups = defaultdict(list)
    skipped = 0
    for line in text.splitlines():
        try:
            entry = json.loads(line)
            seen_at = datetime.strptime(entry['t'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        except (ValueError, KeyError):
            skipped += 1
            continue
        if seen_at < since or (args.bundle and entry.get('bundle') != args.bundle):
            continue
        entry['_at'] = seen_at
        groups[(entry.get('kind', ''), entry.get('message', ''), entry.get('source', ''))].append(entry)

    total = sum(len(v) for v in groups.values())
    print(f'{total} reports, {len(groups)} distinct errors in the last {args.days:g} days'
          + (f' (bundle {args.bundle})' if args.bundle else '') + (f'; {skipped} unparseable lines' if skipped else ''))
    if not groups:
        return 0

    rows = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    for (kind, message, source), entries in rows:
        dprs = Counter(f"{e['dpr']:g}" if isinstance(e.get('dpr'), (int, float)) else '?' for e in entries)
        zones = Counter(e.get('tz') or '?' for e in entries)
        bundles = Counter(e.get('bundle') or '?' for e in entries)
        browsers = Counter(browser_of(e.get('ua', '')) for e in entries)
        first, last = min(e['_at'] for e in entries), max(e['_at'] for e in entries)
        print(f"\n{len(entries):>4}× [{kind}] {message[:160]}")
        if source:
            print(f"       at {source}")
        print(f"       {first:%m-%d %H:%M} → {last:%m-%d %H:%M} UTC | dpr {top(dprs)} | tz {top(zones)}")
        print(f"       {top(browsers)} | bundle {top(bundles)}")
        if args.verbose and entries[-1].get('stack'):
            for frame in entries[-1]['stack'].splitlines()[:6]:
                print(f'         {frame}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
