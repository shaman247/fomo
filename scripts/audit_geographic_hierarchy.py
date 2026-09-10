#!/usr/bin/env python3
"""Audit geography; --apply runs reviewed city-config repairs under the DB lock.

Writes a JSON report/back-up to --output (default .scratch/neighborhood-audit).
Never deletes neighborhoods or events. Rerunning --apply is idempotent.
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from city_config import get_config
from db import create_connection
from dblock import write_lock
from geographic_hierarchy import descendants, plan_repairs, load_event_counts
from constants import get_active_date_window
from exporter import _PUBLISHABLE_WEBSITE_GATE


def snapshot(cursor):
    cursor.execute("SELECT id,name,type FROM tags WHERE scope='venue'")
    tags = {name: {'id': i, 'type': kind} for i, name, kind in cursor.fetchall()}
    cursor.execute("SELECT p.name,c.name FROM tag_hierarchy h JOIN tags p ON p.id=h.parent_tag_id JOIN tags c ON c.id=h.child_tag_id WHERE p.scope='venue' AND c.scope='venue'")
    return tags, set(cursor.fetchall())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--output', default='.scratch/neighborhood-audit')
    args = ap.parse_args()
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    conn = create_connection()
    if conn is None:
        raise SystemExit('Database connection unavailable')
    cfg = get_config().get('geographic_hierarchy', {})
    def run():
        cur = conn.cursor()
        tags, edges = snapshot(cur)
        plan = plan_repairs(tags, edges, cfg)
        fixes = []
        for fix in cfg.get('location_tags', []):
            cur.execute('SELECT name FROM locations WHERE id=%s', (fix['location_id'],))
            if cur.fetchone() != (fix['expected_name'],):
                raise ValueError(f'Location identity changed: {fix}')
            cur.execute('SELECT 1 FROM location_tags WHERE location_id=%s AND tag_id=%s', (fix['location_id'], tags[fix['tag']]['id']))
            if not cur.fetchone():
                fixes.append(fix)
        report = {'before_edges': sorted(e for e in edges if e[0] in descendants(edges)),
                  'before_types': {n: tags[n]['type'] for n in descendants(edges)},
                  'plan': plan, 'location_tags_to_add': fixes}
        backup = output / ('before-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
        backup.write_text(json.dumps(report, indent=2))
        print(json.dumps({'plan_counts': {k:len(v) for k,v in plan.items()}, 'location_tags': fixes, 'backup':str(backup)},indent=2))
        if args.apply:
            for n in plan['create']:
                cur.execute("INSERT INTO tags(name,type,emoji,scope) VALUES(%s,'tag','📍','venue')", (n,))
                tags[n] = {'id':cur.lastrowid, 'type':'tag'}
            for n in plan['promote']:
                cur.execute("UPDATE tags SET type='tag',emoji=COALESCE(emoji,'📍') WHERE id=%s", (tags[n]['id'],))
            for p,c in plan['remove']:
                cur.execute('DELETE FROM tag_hierarchy WHERE parent_tag_id=%s AND child_tag_id=%s',(tags[p]['id'],tags[c]['id']))
            for p,c in plan['add']:
                cur.execute('INSERT IGNORE INTO tag_hierarchy(parent_tag_id,child_tag_id) VALUES(%s,%s)',(tags[p]['id'],tags[c]['id']))
            for f in fixes:
                cur.execute('INSERT IGNORE INTO location_tags(location_id,tag_id) VALUES(%s,%s)',(f['location_id'],tags[f['tag']]['id']))
            tags,edges=snapshot(cur)
            if any(plan_repairs(tags,edges,cfg).values()):
                raise ValueError('Post-apply validation failed')
            from db import get_tag_hierarchy_for_export
            from tag_hierarchy_policy import validate_hierarchy
            validate_hierarchy(get_tag_hierarchy_for_export(cur))
            conn.commit()
        counts=load_event_counts(cur,edges,_PUBLISHABLE_WEBSITE_GATE,get_active_date_window())
        geo=descendants(edges)
        report['event_counts']=counts
        report['empty_areas']=sorted(n for n,v in counts.items() if v==0)
        report['noncurated']=sorted(n for n in geo if tags[n]['type']!='tag')
        report['configured_geotags_outside_tree'] = sorted(set(get_config().get('geotags', [])) - geo)
        # Address matches are review candidates, never automatic geographic truth:
        # postal localities can cross borders and names can have non-place meanings.
        cur.execute("SELECT l.id,l.name,l.address,t.name FROM locations l JOIN location_tags lt ON lt.location_id=l.id JOIN tags t ON t.id=lt.tag_id WHERE l.address IS NOT NULL")
        candidates = {}
        for lid, venue, address, tag in cur.fetchall():
            if tag in geo:
                continue
            locality = re.sub(r', [A-Z]{2}$', '', tag)
            if re.search(r',\s*' + re.escape(locality) + r',\s*[A-Z]{2}\b', address, re.I):
                candidates.setdefault(tag, []).append({'location_id':lid,'name':venue,'address':address})
        report['address_backed_candidates'] = candidates
        report['multiple_geographic_parents'] = {n: sorted(p for p,c in edges if c==n and p in geo) for n in geo if sum(c==n and p in geo for p,c in edges)>1}
        report['large_branches']={n:sum(p==n for p,c in edges) for n in sorted(geo) if sum(p==n for p,c in edges)>20}
        (output/'audit.json').write_text(json.dumps(report,indent=2))
        print(json.dumps({k:report[k] for k in ['noncurated','large_branches']}))
        print(f'{len(geo)} geographic nodes; {len(report["empty_areas"])} empty branches; report: {output / "audit.json"}')
    try:
        if args.apply:
            with write_lock(conn):
                run()
        else:
            run()
    finally:
        conn.close()

if __name__ == '__main__':
    main()
