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
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pipeline'))
from db import create_connection, build_tag_ancestor_map


def backfill(apply=False, verbose=False):
    conn = create_connection()
    if not conn:
        print("Failed to connect to database")
        return

    cursor = conn.cursor(dictionary=True)

    # Load ancestor map from database hierarchy
    ancestor_map, root_tags = build_tag_ancestor_map(cursor)
    print(f"Loaded hierarchy: {len(ancestor_map)} tags with ancestors, {len(root_tags)} root tags")

    # Get all active events with their tags
    cursor.execute("""
        SELECT e.id, e.name,
               GROUP_CONCAT(t.name SEPARATOR '|||') as tags
        FROM events e
        LEFT JOIN event_tags et ON e.id = et.event_id
        LEFT JOIN tags t ON et.tag_id = t.id
        WHERE e.archived = FALSE AND e.suppressed = FALSE
        GROUP BY e.id
    """)
    events = cursor.fetchall()

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
                cursor.execute("SELECT id FROM tags WHERE name = %s", (tag_name,))
                tag_row = cursor.fetchone()
                if tag_row:
                    tag_id = tag_row['id']
                else:
                    cursor.execute("INSERT INTO tags (name) VALUES (%s)", (tag_name,))
                    tag_id = cursor.lastrowid

                cursor.execute(
                    "INSERT IGNORE INTO event_tags (event_id, tag_id) VALUES (%s, %s)",
                    (event['id'], tag_id)
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
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Backfill ancestor tags for existing events')
    parser.add_argument('--apply', action='store_true', help='Actually write to database (default: dry run)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show per-event details')
    args = parser.parse_args()

    backfill(apply=args.apply, verbose=args.verbose)
