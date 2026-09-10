#!/usr/bin/env python3
"""Preview/apply an explicit synonym migration, including curated identities.

Retires source chips by demoting their tag rows, retaining IDs for audit history.
Backs up all touched memberships/config before writing under the shared lock.
Use --apply only with --expect-config from a reviewed dry run and a new --backup.
"""
import argparse
from collections import Counter
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
import db
from dblock import write_lock
from event_types import EVENT_TYPES, CATEGORY_TAG, FORMAT_ROOT_TAG
from tag_canonicalization import normalize_tag_key, resolve_aliases


def read(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def remap_edges(edges, mapping):
    result = {(mapping.get(a, a), mapping.get(b, b)) for a, b in edges}
    result = {(a, b) for a, b in result if a != b}
    children = {}
    for a, b in result:
        children.setdefault(a, []).append(b)
    visited, visiting = set(), set()
    def visit(node):
        if node in visiting:
            raise ValueError('Consolidation would create a hierarchy cycle')
        if node in visited:
            return
        visiting.add(node)
        for child in children.get(node, []):
            visit(child)
        visiting.remove(node)
        visited.add(node)
    for node in children:
        visit(node)
    return result


def prepare(cur, mapping, scope='event'):
    if scope not in ('event','venue'):
        raise ValueError('Unknown tag scope')
    tags = read(cur, 'SELECT * FROM tags WHERE scope=%s ORDER BY id', (scope,))
    byname = {t['name']: t for t in tags}
    protected = set(EVENT_TYPES) | {x[0] for x in CATEGORY_TAG.values()} | {FORMAT_ROOT_TAG}
    if scope == 'event' and set(mapping) & protected:
        raise ValueError('Formats require a separate taxonomy migration')
    if set(mapping) & set(mapping.values()):
        raise ValueError('Mappings must point directly to terminal names')
    missing = (set(mapping) | set(mapping.values())) - set(byname)
    if missing:
        raise ValueError(f'Unknown names: {missing}')
    ids = {byname[a]['id']: byname[b]['id'] for a, b in mapping.items()}
    aliases = read(cur, 'SELECT * FROM tag_aliases WHERE scope=%s ORDER BY alias', (scope,))
    proposed = {a['alias']: ids.get(a['tag_id'], a['tag_id']) for a in aliases}
    proposed.update({a: byname[b]['id'] for a, b in mapping.items()})
    byid = {t['id']: t for t in tags}
    resolve_aliases([(a, byid[i]['name']) for a, i in proposed.items()])
    edges = read(cur, 'SELECT h.* FROM tag_hierarchy h JOIN tags t ON t.id=h.parent_tag_id WHERE t.scope=%s ORDER BY parent_tag_id,child_tag_id', (scope,))
    next_edges = remap_edges([(r['parent_tag_id'], r['child_tag_id']) for r in edges], ids)
    disambiguations = read(cur, 'SELECT * FROM tag_disambiguations ORDER BY id')
    rules = read(cur, 'SELECT * FROM tag_rules ORDER BY id')
    config = {'scope': scope, 'mapping': mapping, 'tags': [t for t in tags if t['id'] in set(ids) | set(ids.values())],
              'aliases': aliases, 'edges': edges, 'disambiguations': disambiguations, 'rules': rules}
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest()
    counts = Counter()
    for source, target in mapping.items():
        src, dst = byname[source]['id'], byname[target]['id']
        for table in ['event_tags', 'location_tags']:
            counts[table] += read(cur, f'SELECT COUNT(*) n FROM {table} WHERE tag_id=%s', (src,))[0]['n']
        for table in (['crawl_event_tags', 'website_tags'] if scope == 'event' else []):
            counts[table] += read(cur, f'SELECT COUNT(*) n FROM {table} WHERE tag=%s AND BINARY tag=BINARY %s', (source, source))[0]['n']
        counts['curated_sources'] += byname[source]['type'] == 'tag'
    return {'config_hash': config_hash, 'mapping': mapping, 'ids': ids, 'summary': dict(counts),
            'config': config, 'next_edges': sorted(next_edges)}


def backup(cur, plan):
    result = dict(plan['config'])
    scope = plan['config'].get('scope','event')
    ids = sorted(set(plan['ids']) | set(plan['ids'].values()))
    if not ids:
        return result
    ph = ','.join(['%s'] * len(ids))
    for table in ['event_tags', 'location_tags', 'event_tag_blocks']:
        result[table] = read(cur, f'SELECT * FROM {table} WHERE tag_id IN ({ph})', ids)
    names = sorted(set(plan['mapping']) | set(plan['mapping'].values()))
    ph = ','.join(['%s'] * len(names))
    for table in (['crawl_event_tags', 'website_tags'] if scope == 'event' else []):
        result[table] = read(cur, f'SELECT * FROM {table} WHERE tag IN ({ph})', names)
    return result


def apply(cur, plan):
    scope = plan['config'].get('scope','event')
    counts = Counter()
    byname = {t['name']: t for t in plan['config']['tags']}
    for source, target in plan['mapping'].items():
        src, dst = byname[source]['id'], byname[target]['id']
        # Keep original judgments and carry them to the canonical identity.
        cur.execute('''INSERT IGNORE INTO event_tag_blocks(event_id,tag_id,reason,created_at)
            SELECT event_id,%s,reason,created_at FROM event_tag_blocks WHERE tag_id=%s''', (dst, src))
        counts['blocks_copied'] += cur.rowcount
        cur.execute('''INSERT IGNORE INTO event_tags(event_id,tag_id)
            SELECT et.event_id,%s FROM event_tags et WHERE et.tag_id=%s
            AND NOT EXISTS (SELECT 1 FROM event_tag_blocks b WHERE b.event_id=et.event_id AND b.tag_id=%s)''', (dst, src, dst))
        counts['event_memberships_added'] += cur.rowcount
        cur.execute('DELETE FROM event_tags WHERE tag_id=%s', (src,))
        counts['event_memberships_retired'] += cur.rowcount
        cur.execute('''DELETE et FROM event_tags et JOIN event_tag_blocks b
            ON b.event_id=et.event_id AND b.tag_id=et.tag_id WHERE et.tag_id=%s''', (dst,))
        counts['blocked_memberships_removed'] += cur.rowcount
        cur.execute('INSERT IGNORE INTO location_tags(location_id,tag_id) SELECT location_id,%s FROM location_tags WHERE tag_id=%s', (dst, src))
        counts['location_memberships_added'] += cur.rowcount
        cur.execute('DELETE FROM location_tags WHERE tag_id=%s', (src,))
        counts['location_memberships_retired'] += cur.rowcount
        for table in (['crawl_event_tags', 'website_tags'] if scope == 'event' else []):
            cur.execute(f'UPDATE {table} SET tag=%s WHERE tag=%s AND BINARY tag=BINARY %s', (target, source, source))
            counts[table] += cur.rowcount
        if scope == 'event':
            cur.execute('UPDATE tag_rules SET replacement=%s WHERE BINARY replacement=BINARY %s', (target, source))
        cur.execute('UPDATE tag_aliases SET tag_id=%s WHERE tag_id=%s', (dst, src))
        db.upsert_tag_alias(cur, source, dst)
        for column in ['context_tag_id', 'target_tag_id']:
            cur.execute(f'UPDATE tag_disambiguations SET {column}=%s WHERE {column}=%s', (dst, src))
        cur.execute("UPDATE tags SET type='keyword',is_quick_filter=0,display_order=NULL WHERE id=%s", (src,))
    old_edges = {(e['parent_tag_id'], e['child_tag_id']) for e in plan['config']['edges']}
    new_edges = set(map(tuple, plan['next_edges']))
    for edge in old_edges - new_edges:
        cur.execute('DELETE FROM tag_hierarchy WHERE parent_tag_id=%s AND child_tag_id=%s', edge)
    for edge in new_edges - old_edges:
        cur.execute('INSERT IGNORE INTO tag_hierarchy(parent_tag_id,child_tag_id) VALUES (%s,%s)', edge)
    counts['edges_removed'], counts['edges_added'] = len(old_edges-new_edges), len(new_edges-old_edges)
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=['event','venue'], default='event')
    parser.add_argument('--mapping', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expect-config')
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    if args.output.exists() or (args.backup and args.backup.exists()):
        parser.error('Output and backup must be new paths')
    if args.apply and (not args.expect_config or not args.backup):
        parser.error('--apply requires --expect-config and --backup')
    mapping = json.loads(args.mapping.read_text())
    conn = db.create_connection()
    if conn is None:
        raise SystemExit('Database unavailable')
    try:
        with write_lock(conn, timeout=45, label='tag_synonym_consolidation') if args.apply else nullcontext():
            cur = conn.cursor(dictionary=True)
            if not args.apply:
                cur.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
            plan = prepare(cur, mapping, args.scope)
            if args.expect_config and args.expect_config != plan['config_hash']:
                raise ValueError('Configuration changed: review a fresh preview')
            if args.apply:
                with args.backup.open('x') as f:
                    json.dump(backup(cur, plan), f, ensure_ascii=False, default=str)
                plan['applied'] = apply(cur, plan)
                final = prepare(cur, mapping, args.scope)
                if any(final['summary'].values()):
                    raise ValueError(f'Migration did not converge: {final["summary"]}')
                if final['next_edges'] != sorted((r['parent_tag_id'],r['child_tag_id']) for r in final['config']['edges']):
                    raise ValueError('Hierarchy did not converge')
                plan['remaining'] = final['summary']
            report = {k:v for k,v in plan.items() if k not in ('config','next_edges')}
            with args.output.open('x') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            if args.apply:
                conn.commit()
            else:
                conn.rollback()
            print(json.dumps(report, indent=2))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
