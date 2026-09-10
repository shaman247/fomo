#!/usr/bin/env python3
"""Audit stored/public tag graphs; optionally apply the city config's reviewed repairs.

Read-only by default; exit 1 means findings. Apply requires the preview hash,
backs up changed relationships/memberships, and validates before committing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
import db
from city_config import get_config
from dblock import write_lock
from tag_hierarchy_policy import hierarchy_findings, has_findings, validate_hierarchy
from tag_scopes import public_tag_key


def read(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def prepare(cur, cfg):
    tags = db.get_tag_hierarchy_for_export(cur)
    identities = read(cur, 'SELECT id,name,scope,type,is_quick_filter FROM tags')
    bykey = {public_tag_key(t['name'], t['scope']): t for t in identities}
    policy = cfg.get('tag_hierarchy', {})
    before = {t['name']: t for t in tags}
    after = {n: {**t, 'parents': list(t['parents'])} for n, t in before.items()}
    for scope, children in policy.get('parents', {}).items():
        for name, parents in children.items():
            child = public_tag_key(name, scope)
            wanted = [public_tag_key(p, scope) for p in parents]
            if child not in after or any(p not in after for p in wanted):
                raise ValueError(f'Repair requires existing curated identities: {scope}:{name}')
            after[child]['parents'] = wanted
    demote = []
    for scope, names in policy.get('demote', {}).items():
        for name in names:
            key = public_tag_key(name, scope)
            if key not in after:
                continue
            if any(key in t['parents'] for t in after.values()):
                raise ValueError(f'Reparent children before demoting {key}')
            after.pop(key)
            demote.append(key)
    edges = lambda graph: {(p, n) for n, t in graph.items() for p in t['parents']}
    old_edges, new_edges = edges(before), edges(after)
    removed, added = sorted(old_edges - new_edges), sorted(new_edges - old_edges)
    changed = sorted({c for p, c in removed + added} | set(demote))
    fingerprint = hashlib.sha256(json.dumps({'tags': tags, 'policy': policy,
        'roots': cfg['frontend']['filter_roots']}, sort_keys=True).encode()).hexdigest()
    # Keyword children intentionally map search terms to curated ancestors.
    # They are not browse nodes; only cross-scope links are invalid here.
    invalid = read(cur, """SELECT h.parent_tag_id,h.child_tag_id FROM tag_hierarchy h
        JOIN tags p ON p.id=h.parent_tag_id JOIN tags c ON c.id=h.child_tag_id
        WHERE p.scope<>c.scope""")
    return dict(tags=tags, after=list(after.values()), identities=bykey,
                added=added, removed=removed, demote=demote, changed=changed,
                config_hash=fingerprint, findings=hierarchy_findings(tags, cfg),
                invalid_stored_edges=invalid)


def membership_additions(cur, plan):
    """Backfill only descendants of changed nodes; honor event tag blocks."""
    graph = {t['name']: t['parents'] for t in plan['after']}
    def ancestors(name):
        found, queue = set(), list(graph.get(name, []))
        while queue:
            parent = queue.pop()
            if parent not in found:
                found.add(parent)
                queue.extend(graph.get(parent, []))
        return found
    changed = {c for _, c in plan['added']}
    additions = {'event': set(), 'venue': set()}
    for name in graph:
        parents = ancestors(name)
        if name not in changed and not parents & changed:
            continue
        tag = plan['identities'][name]
        scope = tag['scope']
        table, owner = ('event_tags', 'event_id') if scope == 'event' else ('location_tags', 'location_id')
        for parent in parents:
            pid = plan['identities'][parent]['id']
            extra = ("AND NOT EXISTS (SELECT 1 FROM event_tag_blocks b WHERE b.event_id=m.event_id AND b.tag_id=%s)"
                     if scope == 'event' else '')
            params = (tag['id'], pid, pid) if extra else (tag['id'], pid)
            rows = read(cur, f'''SELECT m.{owner} owner_id FROM {table} m
                WHERE m.tag_id=%s AND NOT EXISTS
                (SELECT 1 FROM {table} existing WHERE existing.{owner}=m.{owner} AND existing.tag_id=%s)
                {extra}''', params)
            additions[scope].update((r['owner_id'], pid) for r in rows)
    return {k: sorted(v) for k, v in additions.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--expect-config')
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    backup = args.output.with_suffix('.backup.json')
    if args.output.exists() or (args.apply and backup.exists()):
        ap.error('Use new report/backup paths')
    if args.apply and not args.expect_config:
        ap.error('--apply requires the preview --expect-config hash')
    cfg = get_config()
    conn = db.create_connection()
    if conn is None:
        raise SystemExit('Database unavailable')

    def run():
        cur = conn.cursor(dictionary=True)
        plan = prepare(cur, cfg)
        if args.expect_config and args.expect_config != plan['config_hash']:
            raise ValueError('Hierarchy changed; review a new preview')
        additions = membership_additions(cur, plan)
        report = {k: plan[k] for k in ('config_hash', 'findings', 'invalid_stored_edges', 'added', 'removed', 'demote')}
        report['membership_additions'] = {k: len(v) for k, v in additions.items()}
        report['after_repairs'] = hierarchy_findings(plan['after'], cfg)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.apply:
            validate_hierarchy(plan['after'], cfg)
            if plan['invalid_stored_edges']:
                raise ValueError('Review invalid stored edges before applying')
            saved = {'tags': [plan['identities'][n] for n in plan['changed']],
                     'before': [t for t in plan['tags'] if t['name'] in plan['changed']],
                     'added': plan['added'], 'removed': plan['removed'],
                     'membership_additions': additions}
            with backup.open('x') as f:
                json.dump(saved, f, indent=2)
            for parent, child in plan['removed']:
                cur.execute('DELETE FROM tag_hierarchy WHERE parent_tag_id=%s AND child_tag_id=%s',
                            (plan['identities'][parent]['id'], plan['identities'][child]['id']))
            for parent, child in plan['added']:
                cur.execute('INSERT IGNORE INTO tag_hierarchy(parent_tag_id,child_tag_id) VALUES(%s,%s)',
                            (plan['identities'][parent]['id'], plan['identities'][child]['id']))
            for name in plan['demote']:
                cur.execute("UPDATE tags SET type='keyword',is_quick_filter=0 WHERE id=%s", (plan['identities'][name]['id'],))
            for scope, table, owner in [('event', 'event_tags', 'event_id'), ('venue', 'location_tags', 'location_id')]:
                if additions[scope]:
                    cur.executemany(f'INSERT IGNORE INTO {table}({owner},tag_id) VALUES(%s,%s)', additions[scope])
            final = prepare(cur, cfg)
            if has_findings(final['findings']) or final['added'] or final['removed'] or final['demote']:
                raise ValueError('Repair did not converge')
            conn.commit()
            report['backup'] = str(backup)
        with args.output.open('x') as f:
            json.dump(report, f, indent=2)
        print(json.dumps(report, indent=2))
        return 1 if not args.apply and (has_findings(plan['findings']) or plan['invalid_stored_edges']) else 0
    try:
        if args.apply:
            with write_lock(conn, timeout=45, label='tag_hierarchy_audit'):
                try:
                    result = run()
                except Exception:
                    conn.rollback()  # before lock metadata commits on exit
                    raise
        else:
            conn.cursor().execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
            result = run()
            conn.rollback()
    finally:
        conn.close()
    return result


if __name__ == '__main__':
    raise SystemExit(main())
