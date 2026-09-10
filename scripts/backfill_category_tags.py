#!/usr/bin/env python3
"""
Backfill ancestor tags for all existing events using the database tag hierarchy.

Iterates over all active events, checks their existing tags, derives ancestor
tags from the tag_hierarchy table, and adds any missing ancestor tags.

Usage:
    ./venv/bin/python scripts/backfill_category_tags.py            # Dry run (default)
    ./venv/bin/python scripts/backfill_category_tags.py --apply    # Actually write to DB
    ./venv/bin/python scripts/backfill_category_tags.py --verbose  # Show per-event details
"""

import argparse
from contextlib import nullcontext
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pipeline'))
from db import create_connection, build_tag_ancestor_map, get_tag_hierarchy_for_export
from dblock import write_lock
from tag_hierarchy_policy import validate_hierarchy


def backfill(apply=False, verbose=False, event_ids=None):
    conn = create_connection()
    if not conn:
        print("Failed to connect to database")
        return

    try:
        with write_lock(conn, timeout=45, label='backfill_category_tags') if apply else nullcontext():
            try:
                return _backfill(conn, apply, verbose, event_ids)
            except Exception:
                conn.rollback()
                raise
    finally:
        conn.close()


def _backfill(conn, apply, verbose, event_ids):
    cursor = conn.cursor(dictionary=True)

    validate_hierarchy(get_tag_hierarchy_for_export(cursor))

    # Load ancestor map from database hierarchy
    ancestor_map, root_tags = build_tag_ancestor_map(cursor)
    print(f"Loaded hierarchy: {len(ancestor_map)} tags with ancestors, {len(root_tags)} root tags")

    # Get all active events with their tags (optionally scoped to explicit ids)
    scope_sql = ""
    params = []
    if event_ids:
        scope_sql = " AND e.id IN (%s)" % ','.join(['%s'] * len(event_ids))
        params = list(event_ids)
    cursor.execute("""
        SELECT e.id, e.name,
               GROUP_CONCAT(t.name SEPARATOR '|||') as tags
        FROM events e
        LEFT JOIN event_tags et ON e.id = et.event_id
        LEFT JOIN tags t ON et.tag_id = t.id
        WHERE e.archived = FALSE AND e.suppressed = FALSE
    """ + scope_sql + """
        GROUP BY e.id
    """, params)
    events = cursor.fetchall()
    if event_ids:
        print(f"Scoped to {len(event_ids)} requested event id(s); {len(events)} matched (active, unsuppressed)")

    total_events = len(events)
    events_updated = 0
    tags_added_total = 0
    events_no_category = []

    for event in events:
        existing_tags = event['tags'].split('|||') if event['tags'] else []
        existing_normalized = set(t.lower().replace(' ', '') for t in existing_tags)

        # Derive ancestor tags from existing tags
        ancestors_to_add = set()
        for tag in existing_tags:
            key = tag.lower().replace(' ', '')
            for ancestor in ancestor_map.get(key, set()):
                if ancestor.lower().replace(' ', '') not in existing_normalized:
                    ancestors_to_add.add(ancestor)

        # Check if event already has or is getting a root-level tag
        has_root = any(
            t.lower().replace(' ', '') in root_tags for t in existing_tags
        ) or any(
            a.lower().replace(' ', '') in root_tags for a in ancestors_to_add
        )

        # Add "Other" fallback if no root tag
        if not has_root:
            if 'other' not in existing_normalized:
                ancestors_to_add.add('Other')
            events_no_category.append((event['id'], event['name'], existing_tags[:5]))

        if not ancestors_to_add:
            continue

        if verbose:
            print(f"  [{event['id']}] {event['name']}: +{', '.join(sorted(ancestors_to_add))}")

        if apply:
            for tag_name in ancestors_to_add:
                # Get or create tag
                cursor.execute("SELECT id FROM tags WHERE name = %s AND scope='event'", (tag_name,))
                tag_row = cursor.fetchone()
                if tag_row:
                    tag_id = tag_row['id']
                else:
                    # A fallback such as Other is search-only. Real ancestors
                    # already exist; backfill must never invent curated roots.
                    cursor.execute("INSERT INTO tags (name, type, scope) VALUES (%s, 'keyword', 'event')", (tag_name,))
                    tag_id = cursor.lastrowid

                # Judged audit removals (event_tag_blocks) are binding — never
                # re-add a blocked tag via ancestor propagation.
                cursor.execute(
                    """INSERT IGNORE INTO event_tags (event_id, tag_id)
                       SELECT %s, %s FROM DUAL
                       WHERE NOT EXISTS (
                           SELECT 1 FROM event_tag_blocks b
                           WHERE b.event_id = %s AND b.tag_id = %s
                       )""",
                    (event['id'], tag_id, event['id'], tag_id)
                )

        events_updated += 1
        tags_added_total += len(ancestors_to_add)

    if apply:
        conn.commit()

    mode = 'APPLIED' if apply else 'DRY RUN'
    print(f"\n{'=' * 50}")
    print(f"Backfill {mode}")
    print(f"{'=' * 50}")
    print(f"  Total events scanned:          {total_events}")
    print(f"  Events needing ancestor tags:  {events_updated}")
    print(f"  Ancestor tags to add:          {tags_added_total}")
    print(f"  Events with no root category:  {len(events_no_category)} (assigned 'Other')")

    if events_no_category and verbose:
        print(f"\nEvents assigned 'Other' (no root category match):")
        for eid, name, tags in events_no_category[:50]:
            print(f"  [{eid}] {name} — tags: {', '.join(tags)}")
        if len(events_no_category) > 50:
            print(f"  ... and {len(events_no_category) - 50} more")

    if not apply:
        print(f"\nRun with --apply to write changes to database.")

    cursor.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Backfill ancestor tags for existing events')
    parser.add_argument('--apply', action='store_true', help='Actually write to database (default: dry run)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show per-event details')
    parser.add_argument('--ids', help='Comma-separated event ids to scope the backfill to (default: all active events)')
    args = parser.parse_args()

    ids = [int(x) for x in args.ids.split(',') if x.strip()] if args.ids else None
    backfill(apply=args.apply, verbose=args.verbose, event_ids=ids)
