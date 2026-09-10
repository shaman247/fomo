"""Offline tag icon editing. No runtime name matching or hierarchy inheritance.

Dry run by default. --apply --init-schema --export installs the optional column,
applies the initial explicit associations and exports local tag data. Existing
non-null assignments are preserved. --tag NAME --icon ID|fallback explicitly
edits one tag. All writes/exports use the shared lock. Nothing is uploaded.
"""
import argparse
import json
from pathlib import Path
from event_icons import ROOT, ICON_IDS

# One-time editorial seed; never consulted by the frontend or ordinary exports.
INITIAL = {
    'game-go': ['Go', 'Baduk'],
    'game-dominoes': ['Dominoes'],
    'game-scrabble': ['Scrabble'],
    'game-mtg': ['MTG'],
    'tabletop-rpg': ['Dungeons and Dragons', 'D&D', 'Tabletop RPG'],
    'bingo': ['Bingo', 'Bingo Night'],
    'music-bingo': ['Music Bingo', 'Musical Bingo'],
    'trivia': ['Trivia', 'Bar Trivia'],
    'machine-sewing': ['Machine Sewing', 'Sewing Machine'],
    '3d-printing': ['3D Printing'],
    'game-backgammon': ['Backgammon'],
    'game-rummikub': ['Rummikub'],
    'pole-dance': ['Pole Dance', 'Pole Dancing', 'Pole Fitness'],
    'chair-yoga': ['Chair Yoga'],
    'glassblowing': ['Glassblowing', 'Glass Blowing'],
}


def planned_changes(tags, tag=None, icon=None):
    by_name = {t['name']: t for t in tags}
    if tag is not None:
        if tag not in by_name:
            raise ValueError('Tag does not exist: ' + tag)
        if icon is not None and icon not in ICON_IDS:
            raise ValueError('Unknown icon ID: ' + icon)
        targets = {tag: icon}
    else:
        targets = {name: icon_id for icon_id, names in INITIAL.items() for name in names}
    changes = []
    for name, icon_id in targets.items():
        row = by_name.get(name)
        if row is None or row.get('icon_id') == icon_id:
            continue
        if tag is None and row.get('icon_id') is not None:
            continue  # preserve subsequent editorial changes
        changes.append(dict(row, previous_icon_id=row.get('icon_id'), icon_id=icon_id))
    return changes


def read_tags(cursor, scope='event'):
    try:
        cursor.execute('SELECT id,name,emoji,icon_id,type FROM tags WHERE scope=%s ORDER BY name', (scope,))
    except Exception as exc:
        if getattr(exc, 'errno', None) != 1054:
            raise
        cursor.execute('SELECT id,name,emoji,NULL AS icon_id,type FROM tags WHERE scope=%s ORDER BY name', (scope,))
    return [dict(zip(('id','name','emoji','icon_id','type'), row)) for row in cursor.fetchall()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--init-schema', action='store_true')
    parser.add_argument('--export', action='store_true')
    parser.add_argument('--tag')
    parser.add_argument('--scope', choices=['event','venue'], default='event')
    parser.add_argument('--icon')
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    if (args.init_schema or args.export) and not args.apply:
        parser.error('--init-schema / --export require --apply')
    if (args.tag is None) != (args.icon is None):
        parser.error('--tag and --icon must be provided together')
    from db import create_connection
    from dblock import write_lock
    from contextlib import nullcontext
    conn = create_connection()
    if conn is None:
        raise RuntimeError('Database unavailable')
    try:
        with write_lock(conn, label='tag_icon_assignments') if args.apply else nullcontext():
            cursor = conn.cursor()
            if args.init_schema:
                cursor.execute((ROOT/'database/migrations/20260908_tag_icons.sql').read_text())
            tags = read_tags(cursor, args.scope)
            changes = planned_changes(tags, args.tag, None if args.icon == 'fallback' else args.icon)
            if args.backup:
                args.backup.parent.mkdir(parents=True, exist_ok=True)
                args.backup.write_text(json.dumps(tags, ensure_ascii=False, indent=2))
            if args.apply:
                cursor.executemany('UPDATE tags SET icon_id=%s WHERE id=%s', [(r['icon_id'], r['id']) for r in changes])
                conn.commit()
            print(json.dumps({'applied':args.apply, 'changes':changes}, ensure_ascii=False, indent=2))
            if args.export:
                from exporter import export_tag_hierarchy
                export_tag_hierarchy(cursor)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    main()
