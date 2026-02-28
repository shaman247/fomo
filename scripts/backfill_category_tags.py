#!/usr/bin/env python3
"""
Backfill category tags for all existing events.

Reads tag_groups.json to build a reverse map from granular tags to category tags,
then iterates over all active events, checks their existing tags, and adds
any missing category tags.

Usage:
    ./venv/bin/python scripts/backfill_category_tags.py            # Dry run (default)
    ./venv/bin/python scripts/backfill_category_tags.py --apply    # Actually write to DB
    ./venv/bin/python scripts/backfill_category_tags.py --verbose  # Show per-event details
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pipeline'))
from db import create_connection

CROSS_CUTTING = {'free', 'virtual'}


def load_category_map():
    """Load tag_groups.json and build reverse map: normalized_tag -> [primaryTag, ...]."""
    path = os.path.join(os.path.dirname(__file__), '..', 'src', 'data', 'tag_groups.json')
    with open(path, 'r', encoding='utf-8') as f:
        groups = json.load(f)

    cat_map = {}
    main_primary_tags = set()

    for group in groups:
        primary = group.get('primaryTag')
        if not primary:
            continue
        primary_norm = primary.lower().replace(' ', '')

        if primary_norm not in CROSS_CUTTING and primary_norm != 'other':
            main_primary_tags.add(primary_norm)

        for tag in group.get('tags', []):
            key = tag.lower().replace(' ', '')
            if key not in cat_map:
                cat_map[key] = []
            if primary not in cat_map[key]:
                cat_map[key].append(primary)

    return cat_map, main_primary_tags


def backfill(apply=False, verbose=False):
    cat_map, main_primary_tags = load_category_map()
    print(f"Loaded {len(cat_map)} tag mappings across {len(main_primary_tags)} main categories")

    conn = create_connection()
    if not conn:
        print("Failed to connect to database")
        return

    cursor = conn.cursor(dictionary=True)

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

        # Derive category tags from existing granular tags
        cats_to_add = set()
        for tag in existing_tags:
            key = tag.lower().replace(' ', '')
            for primary in cat_map.get(key, []):
                if primary.lower().replace(' ', '') not in existing_normalized:
                    cats_to_add.add(primary)

        # Check if event already has or is getting a main category
        main_cats = {c for c in cats_to_add if c.lower().replace(' ', '') in main_primary_tags}
        has_main = bool(main_cats) or any(
            t.lower().replace(' ', '') in main_primary_tags for t in existing_tags
        )

        # Add "Other" fallback if no main category
        if not has_main:
            if 'other' not in existing_normalized:
                cats_to_add.add('Other')
            events_no_category.append((event['id'], event['name'], existing_tags[:5]))

        if not cats_to_add:
            continue

        if verbose:
            print(f"  [{event['id']}] {event['name']}: +{', '.join(sorted(cats_to_add))}")

        if apply:
            for cat_tag in cats_to_add:
                # Get or create tag
                cursor.execute("SELECT id FROM tags WHERE name = %s", (cat_tag,))
                tag_row = cursor.fetchone()
                if tag_row:
                    tag_id = tag_row['id']
                else:
                    cursor.execute("INSERT INTO tags (name) VALUES (%s)", (cat_tag,))
                    tag_id = cursor.lastrowid

                cursor.execute(
                    "INSERT IGNORE INTO event_tags (event_id, tag_id) VALUES (%s, %s)",
                    (event['id'], tag_id)
                )

        events_updated += 1
        tags_added_total += len(cats_to_add)

    if apply:
        conn.commit()

    mode = 'APPLIED' if apply else 'DRY RUN'
    print(f"\n{'=' * 50}")
    print(f"Backfill {mode}")
    print(f"{'=' * 50}")
    print(f"  Total events scanned:          {total_events}")
    print(f"  Events needing category tags:  {events_updated}")
    print(f"  Category tags to add:          {tags_added_total}")
    print(f"  Events with no main category:  {len(events_no_category)} (assigned 'Other')")

    if events_no_category and verbose:
        print(f"\nEvents assigned 'Other' (no main category match):")
        for eid, name, tags in events_no_category[:50]:
            print(f"  [{eid}] {name} — tags: {', '.join(tags)}")
        if len(events_no_category) > 50:
            print(f"  ... and {len(events_no_category) - 50} more")

    if not apply:
        print(f"\nRun with --apply to write changes to database.")

    cursor.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Backfill category tags for existing events')
    parser.add_argument('--apply', action='store_true', help='Actually write to database (default: dry run)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show per-event details')
    args = parser.parse_args()

    backfill(apply=args.apply, verbose=args.verbose)
