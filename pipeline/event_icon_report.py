"""Read-only assignment report and local preview using the site's real card renderer.
Run: ./venv/bin/python pipeline/event_icon_report.py --input snapshot.json --output .scratch/event-icons
Or:  ./venv/bin/python pipeline/event_icon_report.py --database --output .scratch/event-icons
"""
import argparse
from collections import Counter
from datetime import date, timedelta
import html
import json
import shutil
from pathlib import Path
from event_icons import ROOT, RULE_VERSION, propose


def read_database(start, end):
    from db import create_connection
    from exporter import _PUBLISHABLE_WEBSITE_GATE
    conn = create_connection()
    if conn is None:
        raise RuntimeError('Database unavailable')
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        cursor.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
        cursor.execute(f'''SELECT e.id,e.name,e.description,e.emoji,e.event_type,l.name AS venue
            FROM events e JOIN locations l ON l.id=e.location_id
            LEFT JOIN websites w ON w.id=e.website_id
            WHERE e.archived=FALSE AND e.suppressed=FALSE
            AND l.lat IS NOT NULL AND l.lng IS NOT NULL AND ({_PUBLISHABLE_WEBSITE_GATE})
            AND EXISTS (SELECT 1 FROM event_occurrences o WHERE o.event_id=e.id
              AND COALESCE(o.end_date,o.start_date)>=%s AND o.start_date<=%s)
            ORDER BY e.id''', (start, end))
        events = cursor.fetchall()
        lookup = {e['id']: e for e in events}
        for event in events:
            event['tags'] = []
        cursor.execute('SELECT et.event_id,t.name FROM event_tags et JOIN tags t ON t.id=et.tag_id')
        for row in cursor.fetchall():
            if row['event_id'] in lookup:
                lookup[row['event_id']]['tags'].append(row['name'])
        return events
    finally:
        conn.rollback()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--input', type=Path)
    source.add_argument('--database', action='store_true')
    parser.add_argument('--start', type=date.fromisoformat, default=date.today())
    parser.add_argument('--days', type=int, default=90)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.days < 1:
        parser.error('--days must be positive')
    events = read_database(args.start, args.start + timedelta(days=args.days)) if args.database else json.loads(args.input.read_text())
    rows = [dict(event=event, **propose(event)) for event in events]
    summary = dict(total=len(rows), decisions=dict(Counter(r['decision'] for r in rows)),
                   icons=dict(Counter(r['icon_id'] for r in rows if r['icon_id'])), rule_version=RULE_VERSION,
                   source='database' if args.database else str(args.input),
                   window=[str(args.start), str(args.start + timedelta(days=args.days))] if args.database else None)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'report.json').write_text(json.dumps(dict(summary=summary, rows=rows), ensure_ascii=False, default=str))
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    # Include every record in the review UI, but bound preview text and DOM work.
    preview_rows = [dict(r, event={k: (v[:800] if k == 'description' and isinstance(v, str) else v)
                    for k, v in r['event'].items() if k in ('id','name','description','emoji','venue')}) for r in rows]
    data = json.dumps(dict(summary=summary, rows=preview_rows), ensure_ascii=False).replace('<', '\\u003c')
    template = (ROOT / 'config/event-icons/preview.html').read_text()
    base = 'assets/'
    # A narrowly scoped, self-contained preview; never serve the repository root.
    assets = args.output / 'assets'
    scripts = ['core/constants', 'core/themes', 'core/utils', 'core/colorUtils',
               'core/emojiTransforms', 'tags/tagColorManager', 'map/mapManager',
               'core/eventIconCatalog', 'ui/iconManager', 'ui/popupContentBuilder']
    for name in scripts:
        target = assets / 'js' / (name + '.js')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / 'src/js' / (name + '.js'), target)
    for directory in ['css', 'images/event-icons', 'fonts/inter']:
        shutil.copytree(ROOT / 'src' / directory, assets / directory, dirs_exist_ok=True)
    (args.output / 'index.html').write_text(template.replace('{{BASE}}', html.escape(base, quote=True)).replace('{{DATA}}', data))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
