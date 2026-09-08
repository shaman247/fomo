#!/usr/bin/env python3
"""Preview/apply canonical alias repairs without deleting tag identities.

Dry run by default. --remove-alias is an explicit, reviewed resolution of an
existing invalid rule (for example the obsolete Benefit -> Fundraiser back-edge).
Application revalidates the plan under write_lock and saves affected rows first.
Active event tags and all crawl history are reconciled; curated and ambiguous
source tags are protected. Location metadata and archived event tags are untouched.
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
from tag_canonicalization import resolve_aliases, stored_tag_mapping, normalize_tag_key


def read(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def alias_plan(tags, aliases, removed):
    byid = {t['id']:t for t in tags}
    byname = {t['name']:t['id'] for t in tags}
    unknown = set(removed) - {a['alias'] for a in aliases}
    if unknown:
        raise ValueError(f'Requested aliases do not exist: {sorted(unknown)}')
    remaining = [a for a in aliases if a['alias'] not in removed]
    resolved = resolve_aliases([(a['alias'], byid[a['tag_id']]['name']) for a in remaining])
    changes = [{'alias':a['alias'], 'from_id':a['tag_id'],
                'to_id':byname[resolved[normalize_tag_key(a['alias'])]]}
               for a in remaining if byname[resolved[normalize_tag_key(a['alias'])]] != a['tag_id']]
    return resolved, changes


def select_in(cur, sql, values):
    values = list(values)
    result = []
    for start in range(0, len(values), 400):
        chunk = values[start:start+400]
        result.extend(read(cur, sql.format(placeholders=','.join(['%s'] * len(chunk))), chunk))
    return result


def prepare(cur, removed):
    tags = read(cur, 'SELECT id,name,type FROM tags ORDER BY id')
    aliases = read(cur, 'SELECT alias,tag_id FROM tag_aliases ORDER BY alias')
    ambiguity = read(cur, 'SELECT DISTINCT ambiguous_alias FROM tag_disambiguations ORDER BY ambiguous_alias')
    resolved, changes = alias_plan(tags, aliases, removed)
    mapping = stored_tag_mapping(tags, resolved, {r['ambiguous_alias'] for r in ambiguity})
    byname = {t['name']:t['id'] for t in tags}
    event_counts = select_in(cur, '''SELECT et.tag_id,COUNT(*) AS n FROM event_tags et
        JOIN events e ON e.id=et.event_id WHERE e.archived=0 AND e.suppressed=0
        AND et.tag_id IN ({placeholders}) GROUP BY et.tag_id''', [byname[n] for n in mapping])
    crawl_counts = select_in(cur, '''SELECT t.id AS tag_id,COUNT(*) AS n FROM tags t
        JOIN crawl_event_tags cet ON cet.tag=t.name
        WHERE t.id IN ({placeholders}) GROUP BY t.id''', [byname[n] for n in mapping])
    event_counts = {r['tag_id']:r['n'] for r in event_counts}
    crawl_counts = {r['tag_id']:r['n'] for r in crawl_counts}
    rows = [{'source':source, 'target':target, 'source_id':byname[source], 'target_id':byname[target],
             'active_event_rows':event_counts.get(byname[source],0), 'crawl_rows':crawl_counts.get(byname[source],0)}
            for source,target in mapping.items()]
    config = {'tags':tags, 'aliases':aliases, 'ambiguity':ambiguity, 'removed':sorted(removed)}
    fingerprint = hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    return {'config_hash':fingerprint, 'remove_aliases':sorted(removed), 'alias_changes':changes,
            'mappings':rows, 'summary':{'alias_updates':len(changes), 'alias_removals':len(removed),
            'keyword_mappings':len(rows), 'active_event_rows':sum(event_counts.values()),
            'crawl_rows':sum(crawl_counts.values())}}


def backup_rows(cur, plan):
    source_ids = [r['source_id'] for r in plan['mappings']]
    names = [r['source'] for r in plan['mappings']]
    return {
        'plan':plan,
        'aliases':read(cur,'SELECT alias,tag_id FROM tag_aliases ORDER BY alias'),
        'event_tags':select_in(cur, '''SELECT et.* FROM event_tags et JOIN events e ON e.id=et.event_id
            WHERE e.archived=0 AND e.suppressed=0 AND et.tag_id IN ({placeholders})''', source_ids),
        'crawl_event_tags':select_in(cur, 'SELECT * FROM crawl_event_tags WHERE tag IN ({placeholders})', names),
        'event_tag_blocks':read(cur,'SELECT * FROM event_tag_blocks'),
        # Capture pre-existing targets so a reversal can distinguish new memberships.
        'existing_targets':select_in(cur, '''SELECT event_id,tag_id FROM event_tags
            WHERE tag_id IN ({placeholders})''', {r['target_id'] for r in plan['mappings']}),
    }


def apply_plan(cur, plan):
    for alias in plan['remove_aliases']:
        cur.execute('DELETE FROM tag_aliases WHERE alias=%s',(alias,))
    for row in plan['alias_changes']:
        db.upsert_tag_alias(cur,row['alias'],row['to_id'])
    counts = Counter()
    for row in plan['mappings']:
        src, dst = row['source_id'], row['target_id']
        # Retain old blocks and copy their semantic decision to the canonical ID.
        cur.execute('''INSERT IGNORE INTO event_tag_blocks (event_id,tag_id,reason)
            SELECT event_id,%s,reason FROM event_tag_blocks WHERE tag_id=%s''',(dst,src))
        counts['blocks_added'] += cur.rowcount
        if row['active_event_rows']:
            cur.execute('''INSERT IGNORE INTO event_tags (event_id,tag_id)
                SELECT et.event_id,%s FROM event_tags et JOIN events e ON e.id=et.event_id
                WHERE et.tag_id=%s AND e.archived=0 AND e.suppressed=0
                AND NOT EXISTS (SELECT 1 FROM event_tag_blocks b WHERE b.event_id=et.event_id
                                AND b.tag_id IN (%s,%s))''',(dst,src,src,dst))
            counts['event_tags_added'] += cur.rowcount
            cur.execute('''DELETE et FROM event_tags et JOIN events e ON e.id=et.event_id
                WHERE et.tag_id=%s AND e.archived=0 AND e.suppressed=0''',(src,))
            counts['event_tags_removed'] += cur.rowcount
        if row['crawl_rows']:
            cur.execute('UPDATE crawl_event_tags SET tag=%s WHERE tag=%s',(row['target'],row['source']))
            counts['crawl_rows_updated'] += cur.rowcount
    return dict(counts)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--remove-alias',action='append',default=[])
    parser.add_argument('--output',type=Path,required=True,help='New plan/report file')
    parser.add_argument('--expect-config',help='Config hash from a reviewed dry run')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--backup',type=Path)
    args=parser.parse_args()
    if args.apply and (not args.backup or not args.expect_config):
        parser.error('--apply requires --backup and --expect-config from a reviewed dry run')
    if args.output.exists() or (args.backup and args.backup.exists()):
        parser.error('Output and backup paths must be new')
    conn=db.create_connection()
    if conn is None:
        raise SystemExit('Database unavailable')
    try:
        with write_lock(conn,timeout=45,label='tag_alias_reconciliation') if args.apply else nullcontext():
            cur=conn.cursor(dictionary=True)
            if not args.apply:
                cur.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
            plan=prepare(cur,args.remove_alias)
            if args.expect_config and plan['config_hash']!=args.expect_config:
                raise ValueError('Tag/alias configuration changed; review a fresh dry run')
            if args.apply:
                args.backup.parent.mkdir(parents=True,exist_ok=True)
                with args.backup.open('x') as f:
                    json.dump(backup_rows(cur,plan),f,ensure_ascii=False,default=str)
                plan['applied']=apply_plan(cur,plan)
                # Validate resolution and idempotence before committing any writes.
                remaining=prepare(cur,[])['summary']
                if any(remaining[k] for k in ('alias_updates','active_event_rows','crawl_rows')):
                    raise ValueError(f'Reconciliation did not converge: {remaining}')
                plan['remaining']=remaining
            else:
                conn.rollback()
            args.output.parent.mkdir(parents=True,exist_ok=True)
            with args.output.open('x') as f:
                json.dump(plan,f,ensure_ascii=False,indent=2)
            if args.apply:
                conn.commit()
            print(json.dumps({k:v for k,v in plan.items() if k not in ('mappings','alias_changes')},indent=2))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__=='__main__':
    main()
