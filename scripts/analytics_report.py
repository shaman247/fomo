"""
Summarize the site's first-party analytics.

src/js/core/analytics.js beacons a page view on load and engagement (visible
seconds, feature-use counts) when the page is hidden; src/api/analytics.php
adds them to one JSON file of daily totals per city-timezone day in
~/analytics/ on the server (outside the web root). This reads those files over
SSH (.env SSH_HOST/SSH_USER/SSH_PORT/SSH_KEY) — or a local copy with --dir —
and prints the current window against the one before it.

There are no visitor counts by design: views are page loads, and "views with X"
counts page loads in which X happened at least once.

Usage:
    ./venv/bin/python scripts/analytics_report.py              # last 7 days vs the 7 before
    ./venv/bin/python scripts/analytics_report.py --days 28
    ./venv/bin/python scripts/analytics_report.py --html            # + write the local dashboard
    ./venv/bin/python scripts/analytics_report.py --html --note "Search use doubled after the chip change"
    ./venv/bin/python scripts/analytics_report.py --json out.json   # raw dataset
    ./venv/bin/python scripts/analytics_report.py --dir path/to/analytics

Exit status: 0 on success, 2 when the data can't be read.
"""

import argparse
import html
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REMOTE_DIR = '~/analytics'
# Local only (.claude/ is gitignored): the dashboard page and the review notes it shows.
DEFAULT_DASHBOARD = os.path.join(PROJECT_ROOT, '.claude', 'analytics-dashboard.html')
NOTES_FILE = os.path.join(PROJECT_ROOT, '.claude', 'analytics-notes.json')
HISTORY_DAYS = 120

# Feature-use actions, in display order, with the label the report and dashboard show.
ACTIONS = {
    'event_link': 'Event link clicks',
    'popup_open': 'Venue popups opened',
    'list_event_open': 'Events opened from the list',
    'list_toggle': 'List opened/closed',
    'search': 'Searches',
    'filter_topic': 'Topic filter changes',
    'filter_venue': 'Venue filter changes',
    'filter_format': 'Format filter changes',
    'filter_area': 'Area filter changes',
    'date_change': 'Date range changes',
    'tag_click': 'Tag clicks',
    'share': 'Share-view clicks',
    'feedback_open': 'Feedback form opened',
    'theme_change': 'Theme changes',
    'outbound': 'Other outbound links',
}
MILESTONES = {'engaged_10s': '10 s', 'engaged_60s': '1 min', 'engaged_5m': '5 min'}
BREAKDOWNS = ['platform', 'device', 'browser', 'os', 'referrer', 'utm_source', 'shared_link',
              'dpr', 'tz', 'lang', 'hour', 'bundle', 'path']


def fetch_remote():
    load_dotenv(os.path.join(PROJECT_ROOT, '.env'))
    host, user = os.getenv('SSH_HOST'), os.getenv('SSH_USER')
    if not host or not user:
        print('SSH_HOST/SSH_USER missing from .env (or pass --dir)', file=sys.stderr)
        sys.exit(2)
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=20', '-p', os.getenv('SSH_PORT', '22')]
    if os.getenv('SSH_KEY'):
        command += ['-i', os.path.join(PROJECT_ROOT, os.getenv('SSH_KEY'))]
    # One day file per line: "<name>\t<json>".
    script = (f'for f in {REMOTE_DIR}/20??-??-??.json; do [ -f "$f" ] || continue; '
              'printf "%s\\t" "$(basename "$f")"; tr -d "\\n" < "$f"; echo; done')
    result = subprocess.run(command + [f'{user}@{host}', script], capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f'ssh failed: {result.stderr.strip()}', file=sys.stderr)
        sys.exit(2)
    days = {}
    for line in result.stdout.splitlines():
        name, _, body = line.partition('\t')
        try:
            days[name[:10]] = json.loads(body)
        except ValueError:
            print(f'skipping unreadable {name}', file=sys.stderr)
    return days


def read_local(directory):
    days = {}
    for name in sorted(os.listdir(directory)):
        if len(name) == 15 and name.endswith('.json') and name[:4].isdigit():
            with open(os.path.join(directory, name), encoding='utf-8') as f:
                days[name[:10]] = json.load(f)
    return days


def empty_totals():
    return {'views': 0, 'bots': 0, 'seconds': 0, 'actions': Counter(), 'views_with': Counter(),
            'dims': {name: Counter() for name in BREAKDOWNS + ['seconds_by_platform']}}


def add_day(totals, day):
    totals['views'] += day.get('views', 0)
    totals['bots'] += day.get('bots', 0)
    totals['seconds'] += day.get('seconds', 0)
    totals['actions'].update(day.get('actions', {}).get('all', {}))
    totals['views_with'].update(day.get('views_with', {}).get('all', {}))
    for name, values in day.get('dims', {}).items():
        totals['dims'].setdefault(name, Counter()).update(values)


def summarize(days, start, end):
    totals = empty_totals()
    for key in sorted(days):
        if start <= key <= end:
            add_day(totals, days[key])
    return totals


def rate(part, whole):
    return part / whole if whole else 0.0


def headline(totals):
    views = totals['views']
    with_ = totals['views_with']
    filters = sum(totals['actions'][a] for a in ACTIONS if a.startswith('filter_'))
    return {
        'views': views,
        'engaged_10s_rate': rate(with_['engaged_10s'], views),
        'engaged_60s_rate': rate(with_['engaged_60s'], views),
        'avg_engaged_seconds': rate(totals['seconds'], views),
        'event_link_clicks': totals['actions']['event_link'],
        'event_link_view_rate': rate(with_['event_link'], views),
        'popups_per_view': rate(totals['actions']['popup_open'], views),
        'search_view_rate': rate(with_['search'], views),
        'filter_changes': filters,
        'shared_link_arrivals': totals['dims'].get('shared_link', Counter())['yes'],
        'app_views': sum(totals['dims'].get('platform', Counter())[p] for p in ('ios-app', 'android-app')),
        'bots': totals['bots'],
    }


def delta(now, before):
    if not before:
        return '   new' if now else '     —'
    change = (now - before) / before * 100
    return f'{change:+5.0f}%'


def site_domain():
    city = os.getenv('FOMO_CITY', 'nyc')
    try:
        with open(os.path.join(PROJECT_ROOT, 'config', f'{city}.yaml'), encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith('domain:'):
                    return stripped.split(':', 1)[1].split('#')[0].strip().strip('"')
    except OSError:
        pass
    return city


def load_notes():
    try:
        with open(NOTES_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def add_note(text):
    notes = load_notes()
    notes.append({'date': date.today().isoformat(), 'note': text})
    os.makedirs(os.path.dirname(NOTES_FILE), exist_ok=True)
    with open(NOTES_FILE, 'w', encoding='utf-8') as f:
        json.dump(notes, f, indent=2)
        f.write('\n')


def render_dashboard(dataset, history, notes, site):
    """A self-contained page (inline CSS + SVG, no network) for the local dashboard."""
    esc = html.escape
    h, prev = dataset['headline'], dataset['previous_headline']

    def change(key, pct=False):
        now, before = h[key], prev[key]
        if pct:
            diff = (now - before) * 100
            return ('flat', '±0 pts') if abs(diff) < 0.5 else (('up' if diff > 0 else 'down'), f'{diff:+.0f} pts')
        if not before:
            return ('flat', 'new') if now else ('flat', '—')
        diff = (now - before) / before * 100
        return ('flat', '±0%') if abs(diff) < 0.5 else (('up' if diff > 0 else 'down'), f'{diff:+.0f}%')

    tiles = [
        ('Page views', f"{h['views']:,}", change('views'), 'page loads, not people'),
        ('Engaged ≥10 s', f"{h['engaged_10s_rate']:.0%}", change('engaged_10s_rate', True), 'of views'),
        ('Avg engaged time', f"{h['avg_engaged_seconds']:.0f} s", change('avg_engaged_seconds'), 'visible time per view'),
        ('Event link clicks', f"{h['event_link_clicks']:,}", change('event_link_clicks'), f"{h['event_link_view_rate']:.0%} of views click one"),
        ('Views with a search', f"{h['search_view_rate']:.0%}", change('search_view_rate', True), 'of views'),
        ('App views', f"{h['app_views']:,}", change('app_views'), 'iOS + Android'),
    ]
    tile_html = ''.join(
        f'<div class="tile"><div class="label">{esc(label)}</div><div class="value">{esc(value)}</div>'
        f'<div class="meta"><span class="chg {cls}">{esc(text)}</span> {esc(sub)}</div></div>'
        for label, value, (cls, text), sub in tiles)

    # Daily trend: views as bars, event-link clicks as a line, window shaded.
    width, height, pad_l, pad_b, pad_t = 720, 200, 36, 22, 10
    n = max(len(history), 1)
    # Round the axis up to 2, 5 or 10 × 10^k so the half-way gridline is a whole number.
    peak, top = max([d['views'] for d in history] + [1]), 2
    while top < peak:
        top = top * 5 // 2 if str(top)[0] == '2' else top * 2
    step = (width - pad_l) / n
    y = lambda v: pad_t + (height - pad_t - pad_b) * (1 - v / top)
    bars, labels, points = [], [], []
    for i, d in enumerate(history):
        x = pad_l + i * step
        in_window = dataset['window']['start'] <= d['date'] <= dataset['window']['end']
        bars.append(f'<rect x="{x + step * 0.15:.1f}" y="{y(d["views"]):.1f}" width="{step * 0.7:.1f}" '
                    f'height="{height - pad_b - y(d["views"]):.1f}" class="{"bar win" if in_window else "bar"}">'
                    f'<title>{d["date"]}: {d["views"]} views, {d["event_link_clicks"]} event clicks</title></rect>')
        points.append(f'{x + step / 2:.1f},{y(d["event_link_clicks"]):.1f}')
        every = max(1, n // 8)
        if i == n - 1 or (i % every == 0 and n - 1 - i >= every):
            anchor = 'end' if i == n - 1 else 'middle'
            labels.append(f'<text x="{min(x + step / 2, width):.1f}" y="{height - 6}" class="axis" text-anchor="{anchor}">{d["date"][5:]}</text>')
    grid = ''.join(f'<line x1="{pad_l}" x2="{width}" y1="{y(top * f):.1f}" y2="{y(top * f):.1f}" class="grid"/>'
                   f'<text x="{pad_l - 6}" y="{y(top * f) + 4:.1f}" class="axis" text-anchor="end">{round(top * f):,}</text>'
                   for f in (0, 0.5, 1))
    trend = (f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Daily page views and event link clicks">'
             f'{grid}{"".join(bars)}<polyline points="{" ".join(points)}" class="line"/>{"".join(labels)}</svg>')

    def bar_rows(rows, total):
        if not rows:
            return '<p class="empty">No data in this window.</p>'
        return '<table class="rows">' + ''.join(
            f'<tr><td class="k" title="{esc(str(k))}">{esc(str(k))}</td><td class="bar-cell"><span style="width:{rate(v, total) * 100:.1f}%"></span></td>'
            f'<td class="n">{v:,}</td><td class="n pct">{rate(v, total):.0%}</td></tr>' for k, v in rows) + '</table>'

    views = h['views']
    funnel = [('All views', views)] + [(f"Engaged ≥{e['milestone']}", e['views']) for e in dataset['engagement']]
    funnel += [('Clicked an event link', next(a['views_with'] for a in dataset['actions'] if a['action'] == 'event_link'))]
    feature_rows = [(a['label'], a['events'], a['views_with']) for a in dataset['actions'] if a['events'] or a['views_with']]
    feature_html = ('<table class="rows"><tr><th>Feature</th><th></th><th class="n">Uses</th><th class="n">Views using it</th></tr>' + ''.join(
        f'<tr><td class="k">{esc(label)}</td><td class="bar-cell"><span style="width:{rate(vw, views) * 100:.1f}%"></span></td>'
        f'<td class="n">{ev:,}</td><td class="n pct">{rate(vw, views):.0%}</td></tr>' for label, ev, vw in feature_rows)
        + '</table>') if feature_rows else '<p class="empty">No feature use recorded in this window.</p>'

    hours = dict((b['value'], b['views']) for b in dataset['breakdowns'].get('hour', []))
    hour_top = max(list(hours.values()) + [1])
    hour_html = '<div class="hours">' + ''.join(
        f'<div class="hour" title="{hh}:00 — {hours.get(hh, 0)} views"><span style="height:{rate(hours.get(hh, 0), hour_top) * 100:.0f}%"></span>'
        f'<em>{int(hh) if int(hh) % 3 == 0 else ""}</em></div>' for hh in (f'{i:02d}' for i in range(24))) + '</div>'

    titles = {'platform': 'Platform', 'device': 'Device', 'browser': 'Browser', 'os': 'Operating system',
              'referrer': 'Referring site', 'utm_source': 'Campaign (utm_source)', 'shared_link': 'Arrived on a shared link',
              'dpr': 'Pixel density', 'tz': 'Device time zone', 'lang': 'Language', 'bundle': 'App bundle'}
    breakdown_html = ''.join(
        f'<section class="card"><h3>{esc(title)}</h3>{bar_rows([(b["value"], b["views"]) for b in dataset["breakdowns"].get(name, [])[:8]], views)}</section>'
        for name, title in titles.items())
    notes_html = ''.join(f'<li><time>{esc(n["date"])}</time> {esc(n["note"])}</li>' for n in reversed(notes[-12:])) \
        or '<li class="empty">No review notes yet. Add one with <code>--note</code>.</li>'

    win, pw = dataset['window'], dataset['previous_window']
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(site)} analytics</title>
<style>
/* Internal report: one column of cards on the site's teal accent. */
:root {{
  --bg: #f4f2ee; --card: #fffdf9; --fg: #1f2421; --muted: #5d6662; --line: #e2ddd4;
  --accent: #2d7a6a; --accent-soft: #cfe5df; --up: #2d7a4a; --down: #b4472f;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
  color-scheme: light;
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg: #111413; --card: #1a1e1c; --fg: #e9ece9; --muted: #9aa49f; --line: #2b302d;
    --accent: #74b3a5; --accent-soft: #23423b; --up: #7cc596; --down: #ee8f78; color-scheme: dark; }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--fg); font: 14px/1.5 var(--font); }}
main {{ max-width: 1100px; margin: 0 auto; padding-block: 28px 48px; padding-inline: max(16px, 3vw); display: grid; gap: 18px; }}
header h1 {{ margin: 0; font-size: 22px; letter-spacing: -0.01em; }}
header p {{ margin: 4px 0 0; color: var(--muted); }}
.tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }}
.tile, .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; min-width: 0; }}
.label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; }}
.value {{ font-size: 28px; font-weight: 650; font-variant-numeric: tabular-nums; margin-top: 2px; }}
.meta {{ color: var(--muted); font-size: 12px; }}
.chg {{ font-weight: 600; }} .chg.up {{ color: var(--up); }} .chg.down {{ color: var(--down); }}
h2 {{ font-size: 15px; margin: 0 0 10px; }} h3 {{ font-size: 13px; margin: 0 0 8px; color: var(--muted); font-weight: 600; }}
svg {{ width: 100%; height: auto; display: block; }}
.bar {{ fill: var(--accent-soft); }} .bar.win {{ fill: var(--accent); }}
.line {{ fill: none; stroke: var(--down); stroke-width: 2; }}
.grid {{ stroke: var(--line); }} .axis {{ fill: var(--muted); font-size: 11px; }}
.legend {{ color: var(--muted); font-size: 12px; margin-top: 6px; }}
.legend b {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; vertical-align: -1px; margin-right: 4px; }}
.cols {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 18px; }}
.grid3 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }}
.grid3 .rows .k {{ width: 58%; }} .grid3 .bar-cell {{ width: 12%; }}
table.rows {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }}
.rows td, .rows th {{ padding: 4px 0; vertical-align: middle; }}
.rows th {{ text-align: left; color: var(--muted); font-weight: 500; font-size: 12px; }}
.rows .k {{ max-width: 0; width: 42%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding-right: 8px; }}
.rows .n {{ text-align: right; width: 14%; padding-left: 8px; white-space: nowrap; }} .rows .pct {{ color: var(--muted); }}
.bar-cell span {{ display: block; height: 8px; border-radius: 4px; background: var(--accent); min-width: 2px; }}
.hours {{ display: grid; grid-template-columns: repeat(24, 1fr); gap: 3px; align-items: end; height: 120px; }}
.hour {{ height: 100%; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; }}
.hour span {{ width: 100%; background: var(--accent); border-radius: 3px 3px 0 0; min-height: 1px; }}
.hour em {{ font-style: normal; font-size: 10px; color: var(--muted); height: 14px; }}
.notes {{ margin: 0; padding-left: 18px; }} .notes time {{ color: var(--muted); font-variant-numeric: tabular-nums; margin-right: 6px; }}
.empty {{ color: var(--muted); }}
footer {{ color: var(--muted); font-size: 12px; }}
code {{ font-size: 12px; }}
</style>
</head>
<body>
<main>
<header>
  <h1>{esc(site)} analytics</h1>
  <p>{esc(win['start'])} → {esc(win['end'])} ({win['days']} days) compared with {esc(pw['start'])} → {esc(pw['end'])} · data since {esc(dataset['data_since'])} · generated {esc(dataset['generated_at'])}</p>
</header>
<section class="tiles">{tile_html}</section>
<section class="card">
  <h2>Daily views</h2>{trend}
  <div class="legend"><b style="background:var(--accent)"></b>views in this window <b style="background:var(--accent-soft);margin-left:12px"></b>earlier days <b style="background:var(--down);margin-left:12px;height:3px"></b>event link clicks</div>
</section>
<div class="cols">
  <section class="card"><h2>Engagement</h2>{bar_rows(funnel, views)}</section>
  <section class="card"><h2>Views by hour ({esc(h.get('timezone', '') or 'city time')})</h2>{hour_html}</section>
</div>
<section class="card"><h2>Feature use</h2>{feature_html}</section>
<section><h2>Who and where</h2><div class="grid3">{breakdown_html}</div></section>
<section class="card"><h2>Review notes</h2><ul class="notes">{notes_html}</ul></section>
<footer>Views are page loads; there are no visitor counts by design. Bot beacons ignored in this window: {h['bots']:,}.
Regenerate with <code>./venv/bin/python scripts/analytics_report.py --html</code>.</footer>
</main>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description='Summarize first-party analytics')
    parser.add_argument('--dir', help='Read day files from a local directory instead of over SSH')
    parser.add_argument('--days', type=int, default=7, help='Window length in days (default 7)')
    parser.add_argument('--end', help='Last day of the window, YYYY-MM-DD (default: latest day with data)')
    parser.add_argument('--json', metavar='PATH', help='Also write the raw dataset here')
    parser.add_argument('--html', metavar='PATH', nargs='?', const=DEFAULT_DASHBOARD,
                        help='Also write the local dashboard page (default %(const)s)')
    parser.add_argument('--note', help='Record a dated review note (shown on the dashboard)')
    parser.add_argument('--top', type=int, default=6, help='Values per breakdown (default 6)')
    args = parser.parse_args()
    if args.note:
        add_note(args.note)

    days = read_local(args.dir) if args.dir else fetch_remote()
    if not days:
        print('No analytics data yet.')
        return 0
    end = date.fromisoformat(args.end) if args.end else date.fromisoformat(max(days))
    start = end - timedelta(days=args.days - 1)
    prev_end, prev_start = start - timedelta(days=1), start - timedelta(days=args.days)
    current = summarize(days, start.isoformat(), end.isoformat())
    previous = summarize(days, prev_start.isoformat(), prev_end.isoformat())
    now_h, prev_h = headline(current), headline(previous)
    first_day = min(days)

    print(f'Analytics {start} → {end} ({args.days} days; data since {first_day}) vs {prev_start} → {prev_end}\n')
    rows = [
        ('Page views', 'views', '{:,.0f}'),
        ('Views engaged ≥10 s', 'engaged_10s_rate', '{:.0%}'),
        ('Views engaged ≥1 min', 'engaged_60s_rate', '{:.0%}'),
        ('Avg engaged time / view', 'avg_engaged_seconds', '{:.0f} s'),
        ('Event link clicks', 'event_link_clicks', '{:,.0f}'),
        ('Views with an event click', 'event_link_view_rate', '{:.0%}'),
        ('Venue popups / view', 'popups_per_view', '{:.2f}'),
        ('Views with a search', 'search_view_rate', '{:.0%}'),
        ('Filter changes', 'filter_changes', '{:,.0f}'),
        ('Shared-link arrivals', 'shared_link_arrivals', '{:,.0f}'),
        ('App views (iOS + Android)', 'app_views', '{:,.0f}'),
        ('Bot beacons (ignored)', 'bots', '{:,.0f}'),
    ]
    for label, key, fmt in rows:
        print(f'  {label:<28} {fmt.format(now_h[key]):>10}   prev {fmt.format(prev_h[key]):>10}  {delta(now_h[key], prev_h[key])}')

    print(f"\n  {'day':<10} {'views':>6} {'≥10s':>5} {'avg s':>6} {'events':>7} {'popups':>7} {'search':>7}")
    daily = []
    for offset in range(args.days):
        key = (start + timedelta(days=offset)).isoformat()
        totals = summarize(days, key, key)
        h = headline(totals)
        daily.append({'date': key, **h, 'popup_opens': totals['actions']['popup_open'],
                      'searches': totals['actions']['search']})
        print(f"  {key:<10} {h['views']:>6} {h['engaged_10s_rate']:>5.0%} {h['avg_engaged_seconds']:>6.0f} "
              f"{h['event_link_clicks']:>7} {totals['actions']['popup_open']:>7} {totals['actions']['search']:>7}")

    print('\n  Feature use              events   views with it')
    for action, label in ACTIONS.items():
        count, viewed = current['actions'][action], current['views_with'][action]
        if count or viewed:
            print(f"  {label:<28} {count:>6}   {rate(viewed, current['views']):>5.0%}")

    print('\n  Breakdown of views')
    for name in BREAKDOWNS:
        counter = current['dims'].get(name, Counter())
        if not counter:
            continue
        total = sum(counter.values())
        items = sorted(counter.items(), key=lambda kv: kv[0]) if name == 'hour' else counter.most_common(args.top)
        shown = ', '.join(f'{k} {rate(v, total):.0%}' for k, v in items)
        print(f'  {name}: {shown}' + ('' if name == 'hour' or len(counter) <= args.top else f' (+{len(counter) - args.top} more)'))

    if args.json or args.html:
        dataset = {
            'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'window': {'start': start.isoformat(), 'end': end.isoformat(), 'days': args.days},
            'previous_window': {'start': prev_start.isoformat(), 'end': prev_end.isoformat()},
            'data_since': first_day,
            'headline': now_h,
            'previous_headline': prev_h,
            'daily': daily,
            'actions': [{'action': a, 'label': label, 'events': current['actions'][a],
                         'views_with': current['views_with'][a], 'view_rate': rate(current['views_with'][a], current['views'])}
                        for a, label in ACTIONS.items()],
            'engagement': [{'milestone': label, 'views': current['views_with'][m], 'view_rate': rate(current['views_with'][m], current['views'])}
                           for m, label in MILESTONES.items()],
            'breakdowns': {name: [{'value': k, 'views': v} for k, v in
                                  (sorted(current['dims'][name].items()) if name == 'hour' else current['dims'][name].most_common(20))]
                           for name in BREAKDOWNS if current['dims'].get(name)},
        }
        dataset['headline']['timezone'] = next((d.get('timezone') for d in days.values() if d.get('timezone')), '')
        if args.json:
            with open(args.json, 'w', encoding='utf-8') as f:
                json.dump(dataset, f, indent=2)
            print(f'\nWrote dataset to {args.json}')
        if args.html:
            history_start = min(start, max(date.fromisoformat(first_day), end - timedelta(days=HISTORY_DAYS - 1)))
            history = []
            for offset in range((end - history_start).days + 1):
                key = (history_start + timedelta(days=offset)).isoformat()
                history.append({'date': key, **headline(summarize(days, key, key))})
            os.makedirs(os.path.dirname(os.path.abspath(args.html)), exist_ok=True)
            with open(args.html, 'w', encoding='utf-8') as f:
                f.write(render_dashboard(dataset, history, load_notes(), site_domain()))
            print(f'\nWrote dashboard to {args.html}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
