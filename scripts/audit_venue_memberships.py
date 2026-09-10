#!/usr/bin/env python3
"""Preview/apply reviewed venue-use assignments and retirement of generic filters.

The city config records exact identities and reviewed assignments. Existing
keyword memberships survive retirement. No inference from names/event topics.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
import db
from city_config import get_config
from constants import get_active_date_window
from dblock import write_lock
from tag_hierarchy_policy import validate_hierarchy, promote_tag
from tag_scopes import public_tag_key


def read(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def project_graph(tags, policy, cfg):
    graph = {t['name']: {**t, 'parents': list(t.get('parents', []))} for t in tags}
    key = lambda name: public_tag_key(name, 'venue')
    retired = {key(n) for n in policy.get('retire', [])}
    for spec in policy.get('promote', []):
        graph.setdefault(key(spec['name']), dict(name=key(spec['name']), scope='venue', parents=[], emoji=spec['emoji']))
    graph = {n: {**t, 'parents': [p for p in t['parents'] if p not in retired]}
             for n, t in graph.items() if n not in retired}
    for child, parents in policy.get('parents', {}).items():
        if key(child) not in graph or any(key(p) not in graph for p in parents):
            raise ValueError(f'Unknown curated venue relationship: {child} → {parents}')
        graph[key(child)]['parents'] = [key(p) for p in parents]
    validate_hierarchy(list(graph.values()), cfg)
    return list(graph.values())


def venue_type_parents(graph):
    """Return venue-use identities, excluding the geographic hierarchy."""
    parents = {t['name'].removeprefix('venue:'): [p.removeprefix('venue:') for p in t['parents']]
               for t in graph if t.get('scope') == 'venue'}
    # Geography has its own audit. Preserve its existing memberships without
    # expanding that hierarchy during a review of venue use.
    geographic = {'Neighborhood'}
    while True:
        expanded = geographic | {n for n, ps in parents.items() if set(ps) & geographic}
        if expanded == geographic:
            break
        geographic = expanded
    return {n: ps for n, ps in parents.items() if n not in geographic}


def project_memberships(before, graph, reviews, affected):
    """Apply exact reviewed changes, then inherit same-scope venue ancestors."""
    parents = venue_type_parents(graph)
    result = set(before)
    prohibited = set()
    for review in reviews:
        lid = review['location_id']
        for name in review.get('add', []):
            if name not in parents:
                raise ValueError(f'Review target is not a curated venue identity: {name}')
            result.add((lid, name))
        for name in review.get('remove', []):
            result.discard((lid, name))
            prohibited.add((lid, name))
    for lid, name in list(result):
        if lid not in affected or name not in parents:
            continue
        seen, queue = set(), list(parents[name])
        while queue:
            parent = queue.pop()
            if parent in seen:
                continue
            seen.add(parent)
            if (lid, parent) in prohibited:
                raise ValueError(f'Removal conflicts with a retained child: {lid}:{parent}')
            result.add((lid, parent))
            queue.extend(parents.get(parent, []))
    return result


def audit_other_memberships(memberships, graph, policy):
    """Flag unreviewed catch-all assignments and redundant Other memberships."""
    if not policy:
        return set(), set()
    parents = venue_type_parents(graph)
    other = policy['tag']
    descendants = {other}
    while True:
        expanded = descendants | {n for n, ps in parents.items() if set(ps) & descendants}
        if expanded == descendants:
            break
        descendants = expanded
    other_locations = {lid for lid, name in memberships if name == other}
    reviewed = {r['location_id'] for r in policy.get('retain', [])}
    precise = {lid for lid, name in memberships if name in parents and name not in descendants}
    return other_locations - reviewed, other_locations & precise


def prepare(cur, cfg):
    policy = cfg['venue_taxonomy']['membership_review']
    tags = db.get_tag_hierarchy_for_export(cur)
    graph = project_graph(tags, policy, cfg)
    identities = {r['name']: r for r in read(cur, "SELECT id,name,type,emoji,is_quick_filter FROM tags WHERE scope='venue'")}
    locations = {r['id']: r for r in read(cur, 'SELECT id,name,short_name,very_short_name,description FROM locations')}
    reviews = policy.get('locations', [])
    renamed = {r['location_id']: r for r in policy.get('names', [])}
    for review in [*reviews, *policy.get('descriptions', [])]:
        accepted = {review['expected_name']}
        if review['location_id'] in renamed:
            accepted.add(renamed[review['location_id']]['name'])
        if locations.get(review['location_id'], {}).get('name') not in accepted:
            raise ValueError(f'Location identity changed: {review}')
    rows = read(cur, "SELECT lt.location_id,t.name FROM location_tags lt JOIN tags t ON t.id=lt.tag_id WHERE t.scope='venue'")
    before = {(r['location_id'], r['name']) for r in rows}
    affected = {r['location_id'] for r in reviews} | {lid for lid, name in before if name in policy['retire']}
    # Reparenting must backfill every existing member of the changed subtree,
    # including locations that were never part of the generic-venue review.
    affected_types = set(policy.get('parents', {})) | {s['name'] for s in policy.get('promote', [])}
    type_parents = venue_type_parents(graph)
    while True:
        expanded = affected_types | {n for n, ps in type_parents.items() if set(ps) & affected_types}
        if expanded == affected_types:
            break
        affected_types = expanded
    affected |= {lid for lid, name in before if name in affected_types}
    if policy.get('other_review'):
        affected |= {lid for lid, name in before if name == policy['other_review']['tag']}
    after = project_memberships(before, graph, reviews, affected)
    venue_types = venue_type_parents(graph)
    classified = {lid for lid, name in after if name in venue_types}
    unclassified = [{'location_id': lid, 'name': locations[lid]['name']}
                    for lid in sorted(affected - classified)]
    unreviewed_other, redundant_other = audit_other_memberships(after, graph, policy.get('other_review'))
    other_findings = {kind: [{'location_id': lid, 'name': locations[lid]['name']} for lid in sorted(ids)]
                      for kind, ids in [('unreviewed', unreviewed_other), ('redundant', redundant_other)]}
    # A retained catch-all needs another tenant/source review when programming
    # appears. Report current DB assignments even when taxonomy has no drift;
    # activity alone is not permission to invent a more specific venue type.
    other_findings['active_events'] = []
    if policy.get('other_review'):
        today, future = get_active_date_window()
        other_findings['active_events'] = read(cur, """
            SELECT e.id AS event_id, e.name AS event_name,
                   l.id AS location_id, l.name AS location_name, l.address,
                   CAST(MIN(o.start_date) AS CHAR) AS next_start_date
            FROM events e JOIN locations l ON l.id=e.location_id
            JOIN location_tags lt ON lt.location_id=l.id
            JOIN tags t ON t.id=lt.tag_id
            JOIN event_occurrences o ON o.event_id=e.id
            WHERE t.scope='venue' AND t.name=%s
              AND e.archived=FALSE AND e.suppressed=FALSE
              AND o.start_date<=%s AND COALESCE(o.end_date,o.start_date)>=%s
            GROUP BY e.id,e.name,l.id,l.name,l.address
            ORDER BY next_start_date,e.id
        """, (policy['other_review']['tag'], future, today))
    edge_set = lambda ts: {(p.removeprefix('venue:'), t['name'].removeprefix('venue:'))
                           for t in ts if t.get('scope') == 'venue' for p in t.get('parents', [])}
    old_edges, new_edges = edge_set(tags), edge_set(graph)
    descriptions = []
    names = []
    for fix in renamed.values():
        actual = locations[fix['location_id']]['name']
        if actual == fix['name']:
            continue
        if actual != fix['expected_name']:
            raise ValueError(f'Name changed; re-review location {fix["location_id"]}')
        names.append({**fix, 'before': locations[fix['location_id']]})
    for fix in policy.get('descriptions', []):
        actual = locations[fix['location_id']]['description']
        if actual == fix['description']:
            continue
        if actual != fix['expected_description']:
            raise ValueError(f'Description changed; re-review location {fix["location_id"]}')
        descriptions.append(fix)
    promotions = [s for s in policy.get('promote', []) if identities.get(s['name'], {}).get('type') != 'tag']
    retirements = [n for n in policy['retire'] if identities.get(n, {}).get('type') == 'tag']
    fingerprint = hashlib.sha256(json.dumps({'policy': policy, 'graph': tags,
        'roots': cfg['frontend']['filter_roots'], 'memberships': sorted((lid,n) for lid,n in before if lid in affected),
        'locations': {lid: locations[lid] for lid in sorted(affected)}}, sort_keys=True).encode()).hexdigest()
    return dict(config_hash=fingerprint, identities=identities, graph=graph,
        add_edges=sorted(new_edges-old_edges), remove_edges=sorted(old_edges-new_edges),
        additions=sorted(after-before), removals=sorted(before-after), promotions=promotions,
        retirements=retirements, descriptions=descriptions, names=names, unclassified=unclassified,
        other_findings=other_findings,
        summary=dict(affected_locations=len(affected), membership_additions=len(after-before),
                     membership_removals=len(before-after), edges_added=len(new_edges-old_edges),
                     edges_removed=len(old_edges-new_edges), promotions=len(promotions),
                     retirements=len(retirements), descriptions=len(descriptions), names=len(names),
                     unclassified_locations=len(unclassified), unreviewed_other=len(unreviewed_other),
                     redundant_other=len(redundant_other)))


def apply(cur, plan, cfg):
    # The promotion helper validates each new root while existing roots still
    # exist. The final graph below must pass the final (stricter) root policy.
    transitional = deepcopy(cfg)
    old_graph = db.get_tag_hierarchy_for_export(cur)
    transitional['frontend']['filter_roots']['venue'] += [t['name'].removeprefix('venue:')
        for t in old_graph if t.get('scope') == 'venue' and not t.get('parents')]
    ids = {n: r['id'] for n, r in plan['identities'].items()}
    for spec in plan['promotions']:
        if spec['name'] not in ids:
            cur.execute("INSERT INTO tags(name,type,scope) VALUES(%s,'keyword','venue')", (spec['name'],))
            ids[spec['name']] = cur.lastrowid
        promote_tag(cur, spec['name'], 'venue', cfg['venue_taxonomy']['membership_review'].get('parents', {}).get(spec['name'], []),
                    spec['emoji'], transitional)
    for parent, child in plan['remove_edges']:
        cur.execute('DELETE FROM tag_hierarchy WHERE parent_tag_id=%s AND child_tag_id=%s', (ids[parent], ids[child]))
    for parent, child in plan['add_edges']:
        cur.execute('INSERT IGNORE INTO tag_hierarchy(parent_tag_id,child_tag_id) VALUES(%s,%s)', (ids[parent], ids[child]))
    for name in plan['retirements']:
        cur.execute("UPDATE tags SET type='keyword',is_quick_filter=0 WHERE id=%s", (ids[name],))
    for lid, name in plan['removals']:
        cur.execute('DELETE FROM location_tags WHERE location_id=%s AND tag_id=%s', (lid, ids[name]))
    if plan['additions']:
        cur.executemany('INSERT IGNORE INTO location_tags(location_id,tag_id) VALUES(%s,%s)',
                        [(lid, ids[n]) for lid,n in plan['additions']])
    for fix in plan['descriptions']:
        cur.execute('UPDATE locations SET description=%s WHERE id=%s', (fix['description'], fix['location_id']))
    for fix in plan['names']:
        cur.execute('UPDATE locations SET name=%s,short_name=NULL,very_short_name=NULL WHERE id=%s',
                    (fix['name'], fix['location_id']))
    validate_hierarchy(db.get_tag_hierarchy_for_export(cur), cfg)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--expect-config')
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    backup = args.output.with_suffix('.backup.json')
    if args.output.exists() or (args.apply and backup.exists()):
        ap.error('Use new output/backup paths')
    if args.apply and not args.expect_config:
        ap.error('--apply requires the reviewed preview hash')
    cfg = get_config()
    conn = db.create_connection()
    if conn is None:
        raise SystemExit('Database unavailable')
    def run():
        cur = conn.cursor(dictionary=True)
        plan = prepare(cur, cfg)
        if args.expect_config and args.expect_config != plan['config_hash']:
            raise ValueError('Data/config changed; review a new preview')
        report = {k: plan[k] for k in ['config_hash','summary','add_edges','remove_edges','additions','removals','promotions','retirements','descriptions','names','unclassified','other_findings']}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.apply:
            with backup.open('x') as f:
                json.dump({**report, 'before_identities': plan['identities']}, f, ensure_ascii=False, indent=2)
            apply(cur, plan, cfg)
            final = prepare(cur, cfg)
            if any(v for k,v in final['summary'].items() if k != 'affected_locations'):
                raise ValueError(f'Repair did not converge: {final["summary"]}')
            conn.commit()
            report['remaining'] = final['summary']
            report['backup'] = str(backup)
        with args.output.open('x') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(json.dumps({k:v for k,v in report.items() if k not in ['additions','removals']}, indent=2))
        return int(any(v for k,v in report.get('remaining', report['summary']).items()
                       if k != 'affected_locations'))
    try:
        if args.apply:
            with write_lock(conn, timeout=45, label='venue_membership_review'):
                try:
                    result = run()
                except Exception:
                    conn.rollback()
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
