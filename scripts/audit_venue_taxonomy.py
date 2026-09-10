#!/usr/bin/env python3
"""Preview/apply reviewed venue taxonomy policy from the city config.

Keeps retired IDs, redirects and tag blocks; validates the complete DAG and
backs up every changed relationship/membership before a locked transaction.
No network publishing. --apply requires a reviewed --expect-config hash.
"""
import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from city_config import get_config
from db import create_connection
from dblock import write_lock
import consolidate_tag_aliases as synonyms


def parent_plan(tags, edges, desired):
    """Replace only explicitly reviewed parent sets and validate the whole graph."""
    result = set(edges)
    for child, parents in desired.items():
        for name in [child, *parents]:
            if name not in tags or tags[name]['type'] != 'tag':
                raise ValueError(f'Reviewed hierarchy identity is not curated: {name}')
        child_id = tags[child]['id']
        result = {(p, c) for p, c in result if c != child_id}
        for parent in parents:
            if parent == child:
                raise ValueError(f'Self-parent: {child}')
            result.add((tags[parent]['id'], child_id))
    # Reuse the consolidation helper's cycle guard, including unrelated branches.
    return synonyms.remap_edges(result, {})


def ancestors(edges):
    parents = defaultdict(set)
    for parent, child in edges:
        parents[child].add(parent)
    result = {}
    for child in parents:
        seen, queue = set(), list(parents[child])
        while queue:
            parent = queue.pop()
            if parent in seen:
                continue
            seen.add(parent)
            queue.extend(parents.get(parent, set()) - seen)
        result[child] = seen
    return result


def membership_additions(cur, tags, edges, venue_names, mapping, fixes):
    """Project synonym moves first; preserve explicit memberships and judged blocks."""
    remap = lambda tag_id: mapping.get(tag_id, tag_id)
    venue_ids = {tags[n]['id'] for n in venue_names if n in tags and tags[n]['type'] == 'tag'}
    closure = ancestors(edges)
    location_rows = synonyms.read(cur, 'SELECT location_id,tag_id FROM location_tags')
    event_rows = synonyms.read(cur, '''SELECT et.event_id,et.tag_id FROM event_tags et
        JOIN events e ON e.id=et.event_id WHERE e.archived=0 AND e.suppressed=0''')
    blocked = {(r['event_id'], remap(r['tag_id'])) for r in synonyms.read(cur, 'SELECT event_id,tag_id FROM event_tag_blocks')}
    locations = {(r['location_id'], remap(r['tag_id'])) for r in location_rows}
    events = {(r['event_id'], remap(r['tag_id'])) for r in event_rows} - blocked
    location_additions, event_additions = set(), set()
    for fix in fixes:
        row = synonyms.read(cur, 'SELECT name FROM locations WHERE id=%s', (fix['location_id'],))
        if row != [{'name': fix['expected_name']}]:
            raise ValueError(f'Location identity changed: {fix}')
        pair = (fix['location_id'], tags[fix['tag']]['id'])
        if pair not in locations:
            location_additions.add(pair)
    for lid, tag_id in locations | location_additions.copy():
        if tag_id in venue_ids:
            location_additions.update((lid, parent) for parent in closure.get(tag_id, set()) & venue_ids
                                      if (lid, parent) not in locations)
    for eid, tag_id in events:
        if tag_id in venue_ids:
            event_additions.update((eid, parent) for parent in closure.get(tag_id, set())
                                  if (eid, parent) not in events and (eid, parent) not in blocked)
    return sorted(location_additions), sorted(event_additions)


def prepare(cur, cfg):
    policy = cfg['venue_taxonomy']
    tags = {r['name']: r for r in synonyms.read(cur, "SELECT id,name,type FROM tags WHERE scope='venue'")}
    # Historical policy also recorded event-only consolidations. Their location
    # copies are keywords now. Retired sources with no venue memberships may no
    # longer have a venue row; their existing scoped alias preserves lookup.
    mapping = {source: target for source, target in policy['aliases'].items()
               if source in tags and target in tags and tags[target]['type'] == 'tag'}
    synonym_plan = synonyms.prepare(cur, mapping, scope='venue')
    before = set(map(tuple, synonym_plan['next_edges']))
    after = parent_plan(tags, before, policy['parents'])
    aliases = {r['alias']: r['tag_id'] for r in synonym_plan['config']['aliases']}
    remove_aliases = []
    for alias, expected_target in policy.get('remove_aliases', {}).items():
        if alias not in aliases:
            continue
        if aliases[alias] != tags[expected_target]['id']:
            raise ValueError(f'Alias target changed: {alias}')
        remove_aliases.append(alias)
    venue_names = cfg['frontend']['venue_selector']['tags']
    locs, events = membership_additions(cur, tags, after, venue_names, synonym_plan['ids'], policy.get('location_tags', []))
    relevant_names = set(venue_names) | set(policy['parents']) | {p for ps in policy['parents'].values() for p in ps}
    identity = {'policy': policy, 'venue_names': venue_names, 'synonyms': synonym_plan['config_hash'],
                'tags': {n: tags.get(n) for n in sorted(relevant_names)}}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    byid = {r['id']: n for n, r in tags.items()}
    return {'config_hash': fingerprint, 'synonyms': synonym_plan, 'tags': tags,
            'add_edges': sorted(after-before), 'remove_edges': sorted(before-after),
            'remove_aliases': remove_aliases, 'location_additions': locs, 'event_additions': events,
            'summary': {'synonyms': synonym_plan['summary'],
                        'parent_links_added': len(after-before), 'parent_links_removed': len(before-after),
                        'conflicting_aliases_removed': len(remove_aliases),
                        'location_memberships_added': len(locs), 'event_memberships_added': len(events)},
            'parent_changes': {child: {'before': sorted(byid[p] for p,c in before if c == tags[child]['id']),
                                       'after': parents} for child,parents in policy['parents'].items()
                               if {byid[p] for p,c in before if c == tags[child]['id']} != set(parents)}}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--expect-config')
    ap.add_argument('--output', type=Path, required=True, help='New report path; adjacent .backup.json on apply')
    args = ap.parse_args()
    if args.apply and not args.expect_config:
        ap.error('--apply requires a reviewed --expect-config')
    backup_path = args.output.with_suffix('.backup.json')
    if args.output.exists() or (args.apply and backup_path.exists()):
        ap.error('Report and backup paths must be new')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    conn = create_connection()
    if conn is None:
        raise SystemExit('Database unavailable')
    cfg = get_config()
    def run():
        cur = conn.cursor(dictionary=True)
        plan = prepare(cur, cfg)
        if args.expect_config and args.expect_config != plan['config_hash']:
            raise ValueError('Taxonomy changed; review a fresh preview')
        report = {k: plan[k] for k in ['config_hash', 'summary', 'parent_changes', 'remove_aliases']}
        report['aliases'] = cfg['venue_taxonomy']['aliases']
        report['generated_at'] = datetime.now().astimezone().isoformat()
        if args.apply:
            backup = {'before': synonyms.backup(cur, plan['synonyms']),
                      'parent_edges_removed': plan['remove_edges'], 'parent_edges_added': plan['add_edges'],
                      'new_location_memberships': plan['location_additions'], 'new_event_memberships': plan['event_additions']}
            with backup_path.open('x') as f:
                json.dump(backup, f, ensure_ascii=False, default=str)
            report['applied_synonyms'] = synonyms.apply(cur, plan['synonyms'])
            for parent, child in plan['remove_edges']:
                cur.execute('DELETE FROM tag_hierarchy WHERE parent_tag_id=%s AND child_tag_id=%s', (parent, child))
            for parent, child in plan['add_edges']:
                cur.execute('INSERT IGNORE INTO tag_hierarchy(parent_tag_id,child_tag_id) VALUES(%s,%s)', (parent, child))
            for alias in plan['remove_aliases']:
                cur.execute("DELETE FROM tag_aliases WHERE alias=%s AND scope='venue'", (alias,))
            if plan['location_additions']:
                cur.executemany('INSERT IGNORE INTO location_tags(location_id,tag_id) VALUES(%s,%s)', plan['location_additions'])
            if plan['event_additions']:
                cur.executemany('INSERT IGNORE INTO event_tags(event_id,tag_id) VALUES(%s,%s)', plan['event_additions'])
            final = prepare(cur, cfg)
            flat = {k:v for k,v in final['summary'].items() if k != 'synonyms'}
            if any(flat.values()) or any(final['summary']['synonyms'].values()):
                raise ValueError(f'Repair did not converge: {final["summary"]}')
            report['remaining'] = final['summary']
            report['backup'] = str(backup_path)
            from db import get_tag_hierarchy_for_export
            from tag_hierarchy_policy import validate_hierarchy
            validate_hierarchy(get_tag_hierarchy_for_export(cur))
            conn.commit()
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(json.dumps(report, indent=2, ensure_ascii=False))
    try:
        if args.apply:
            with write_lock(conn, timeout=45, label='venue_taxonomy_audit'):
                # Roll back BEFORE the lock helper's bookkeeping commits on exit.
                try:
                    run()
                except Exception:
                    conn.rollback()
                    raise
        else:
            conn.cursor().execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
            run()
            conn.rollback()
    finally:
        conn.close()


if __name__ == '__main__':
    main()
