#!/usr/bin/env python3
"""Separate event and venue identities, preserving misplaced tags as keywords.

Default is read-only preview. --apply requires a new --backup path. DDL in
MariaDB commits implicitly: the backup is written before DDL; data changes are
transactional, and rerunning completes an interrupted migration idempotently.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from city_config import get_config
from db import create_connection, build_tag_ancestor_map, upsert_event_tags
from dblock import write_lock
from tag_scopes import migration_plan


def rows(cur, sql):
    cur.execute(sql)
    return cur.fetchall()


def install_guards(cur):
    for table, scope in [('event_tags', 'event'), ('event_tag_blocks', 'event'), ('location_tags', 'venue')]:
        for operation in ['INSERT', 'UPDATE']:
            name = f'{table}_scope_{operation.lower()}'
            cur.execute(f'''CREATE OR REPLACE TRIGGER {name} BEFORE {operation} ON {table}
                FOR EACH ROW BEGIN
                IF (SELECT scope FROM tags WHERE id=NEW.tag_id) <> '{scope}' THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{table} requires {scope} tags';
                END IF; END''')
    for operation in ['INSERT', 'UPDATE']:
        cur.execute(f'''CREATE OR REPLACE TRIGGER tag_hierarchy_scope_{operation.lower()}
            BEFORE {operation} ON tag_hierarchy FOR EACH ROW BEGIN
            IF (SELECT scope FROM tags WHERE id=NEW.parent_tag_id) <>
               (SELECT scope FROM tags WHERE id=NEW.child_tag_id) THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Tag hierarchy cannot cross scopes';
            END IF; END''')
        cur.execute(f'''CREATE OR REPLACE TRIGGER tag_aliases_scope_{operation.lower()}
            BEFORE {operation} ON tag_aliases FOR EACH ROW BEGIN
            IF (SELECT scope FROM tags WHERE id=NEW.tag_id) <> NEW.scope THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Alias scope must match target';
            END IF; END''')
    cur.execute('''CREATE OR REPLACE TRIGGER tags_scope_update BEFORE UPDATE ON tags FOR EACH ROW BEGIN
        IF NEW.scope <> OLD.scope AND (
            EXISTS(SELECT 1 FROM event_tags WHERE tag_id=OLD.id) OR
            EXISTS(SELECT 1 FROM location_tags WHERE tag_id=OLD.id) OR
            EXISTS(SELECT 1 FROM event_tag_blocks WHERE tag_id=OLD.id) OR
            EXISTS(SELECT 1 FROM tag_hierarchy WHERE parent_tag_id=OLD.id OR child_tag_id=OLD.id) OR
            EXISTS(SELECT 1 FROM tag_aliases WHERE tag_id=OLD.id)) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cannot change scope of a referenced tag';
        END IF; END''')


def run(conn, apply=False, backup=None):
    cur = conn.cursor(dictionary=True)
    columns = {r['Field'] for r in rows(cur, 'SHOW COLUMNS FROM tags')}
    scoped = 'scope' in columns
    tags = rows(cur, "SELECT * FROM tags" + (" WHERE scope='event'" if scoped else ''))
    edges = {(r['parent_tag_id'], r['child_tag_id']) for r in rows(cur,
        "SELECT h.* FROM tag_hierarchy h JOIN tags t ON t.id=h.parent_tag_id" + (" WHERE t.scope='event'" if scoped else ''))}
    cfg = get_config()
    venue_names = set(cfg['frontend']['venue_selector']['tags'])
    if scoped:
        venue_names.update(r['name'] for r in rows(cur, "SELECT name FROM tags WHERE scope='venue' AND type='tag'"))
    plan = migration_plan(tags, edges, venue_names,
                          cfg.get('tag_scopes', {}).get('event_parents', {}))
    memberships = rows(cur, "SELECT l.* FROM location_tags l JOIN tags t ON t.id=l.tag_id" + (" WHERE t.scope='event'" if scoped else ''))
    byid = {t['id']: t for t in tags}
    print(json.dumps(dict(location_memberships=len(memberships),
        location_keywords=sum(byid[r['tag_id']]['name'] not in plan['venue_names'] for r in memberships),
        venue_types=len(plan['venue_names']), event_tags_to_demote=sum(t['id'] in plan['demote'] and t['type']=='tag' for t in tags))))
    if not apply:
        return
    if not backup:
        raise ValueError('--apply requires --backup')
    backup.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {table: rows(cur, 'SELECT * FROM ' + table) for table in
                ['tags', 'location_tags', 'tag_hierarchy', 'tag_aliases']}
    snapshot['schema'] = {table: rows(cur, 'SHOW CREATE TABLE ' + table) for table in snapshot.copy()}
    changed_children = {child for _, child in plan['event_edges'] - edges}
    affected_events = set()
    for child in changed_children:
        cur.execute('SELECT event_id FROM event_tags WHERE tag_id=%s', (child,))
        affected_events.update(r['event_id'] for r in cur.fetchall())
    snapshot['event_tags_for_new_ancestors'] = []
    for event_id in sorted(affected_events):
        cur.execute('SELECT * FROM event_tags WHERE event_id=%s', (event_id,))
        snapshot['event_tags_for_new_ancestors'].extend(cur.fetchall())
    with backup.open('x') as output:
        json.dump(snapshot, output, ensure_ascii=False, default=str)
    if not scoped:
        cur.execute("ALTER TABLE tags ADD COLUMN scope ENUM('event','venue') NOT NULL DEFAULT 'event', DROP INDEX unique_tag_name, ADD UNIQUE KEY unique_tag_name_scope(name,scope)")
    alias_columns = {r['Field'] for r in rows(cur, 'SHOW COLUMNS FROM tag_aliases')}
    if 'scope' not in alias_columns:
        cur.execute("ALTER TABLE tag_aliases ADD COLUMN scope ENUM('event','venue') NOT NULL DEFAULT 'event', DROP PRIMARY KEY, ADD PRIMARY KEY(scope,alias)")
    conn.commit()  # End the metadata-read transaction when resuming after DDL.
    conn.start_transaction()
    # Include every referenced location keyword and every curated venue node.
    needed = {r['tag_id'] for r in memberships} | {t['id'] for t in tags if t['name'] in plan['venue_names']}
    existing_venues = {r['name'] for r in rows(cur, "SELECT name FROM tags WHERE scope='venue'")}
    for tid in sorted(needed):
        tag = byid[tid]
        if tag['name'] in existing_venues:
            continue
        kind = 'tag' if tag['name'] in plan['venue_names'] else 'keyword'
        cur.execute('''INSERT INTO tags(name,scope,type,emoji,alt_emoji,icon_id,is_quick_filter,display_order)
            VALUES(%s,'venue',%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE id=id''',
            (tag['name'], kind, tag['emoji'], tag['alt_emoji'], tag.get('icon_id'), tag['is_quick_filter'], tag['display_order']))
    venue = {r['name']:r['id'] for r in rows(cur, "SELECT id,name FROM tags WHERE scope='venue'")}
    cur.execute("""UPDATE location_tags l JOIN tags old ON old.id=l.tag_id
        JOIN tags scoped ON scoped.name=old.name AND scoped.scope='venue'
        SET l.tag_id=scoped.id WHERE old.scope='event'""")
    for p,c in edges - plan['event_edges']:
        cur.execute('DELETE FROM tag_hierarchy WHERE parent_tag_id=%s AND child_tag_id=%s', (p,c))
    for tid in plan['demote']:
        cur.execute("UPDATE tags SET type='keyword',is_quick_filter=0 WHERE id=%s", (tid,))
    for p,c in plan['event_edges'] - edges:
        cur.execute('INSERT IGNORE INTO tag_hierarchy VALUES(%s,%s)', (p,c))
    for p,c in plan['venue_edges']:
        cur.execute('INSERT IGNORE INTO tag_hierarchy VALUES(%s,%s)', (venue[byid[p]['name']],venue[byid[c]['name']]))
    for alias in snapshot['tag_aliases']:
        tag = byid.get(alias['tag_id'])
        if tag and tag['name'] in venue and tag['name'] in plan['venue_names']:
            cur.execute("INSERT IGNORE INTO tag_aliases(scope,alias,tag_id) VALUES('venue',%s,%s)", (alias['alias'],venue[tag['name']]))
    for table,scope in [('event_tags','event'),('location_tags','venue')]:
        bad = rows(cur, f"SELECT COUNT(*) n FROM {table} l JOIN tags t ON t.id=l.tag_id WHERE t.scope <> '{scope}'")[0]['n']
        if bad:
            raise ValueError(f'{bad} invalid {table} memberships')
    # New event parent links must be reflected in explicit memberships. The
    # helper respects existing audit blocks and resolves event IDs only.
    plain = conn.cursor()
    ancestor_map, _ = build_tag_ancestor_map(plain)
    for event_id in sorted(affected_events):
        plain.execute('SELECT t.name FROM event_tags et JOIN tags t ON t.id=et.tag_id WHERE et.event_id=%s', (event_id,))
        names = [r[0] for r in plain.fetchall()]
        ancestors = {parent for name in names for parent in ancestor_map.get(name.lower().replace(' ', ''), set())}
        upsert_event_tags(plain, event_id, ancestors)
    plain.close()
    conn.commit()
    install_guards(cur)
    print('Migration complete; database scope guards installed.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--backup',type=Path)
    args=parser.parse_args()
    if args.apply and (not args.backup or args.backup.exists()):
        parser.error('--apply requires a new --backup path')
    conn=create_connection()
    if conn is None:
        raise SystemExit('Database unavailable')
    try:
        if args.apply:
            with write_lock(conn,timeout=30):
                run(conn,True,args.backup)
        else:
            run(conn)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
