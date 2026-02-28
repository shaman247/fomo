#!/usr/bin/env python3
"""Migrate tag_groups.json into the database tag hierarchy.

Reads the current tag_groups.json and populates:
  - tags table: emoji, is_quick_filter, display_order, type columns
  - tag_hierarchy table: parent-child relationships

Usage:
    python scripts/migrate_tag_hierarchy.py              # dry-run (default)
    python scripts/migrate_tag_hierarchy.py --apply      # apply changes
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pipeline'))
from db import create_connection


def find_or_create_tag(cursor, name, dry_run):
    """Find a tag by name, or create it. Returns tag id."""
    cursor.execute("SELECT id FROM tags WHERE name = %s", (name,))
    row = cursor.fetchone()
    if row:
        return row['id']
    if dry_run:
        # Return a placeholder for dry-run
        return None
    cursor.execute("INSERT INTO tags (name) VALUES (%s)", (name,))
    return cursor.lastrowid


def migrate(dry_run=True):
    json_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'data', 'tag_groups.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        groups = json.load(f)

    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    # Track all tags that appear in any group
    tags_in_groups = set()
    hierarchy_inserts = 0
    tag_updates = 0

    for order, group in enumerate(groups, start=1):
        primary_tag = group.get('primaryTag')
        emoji = group.get('emoji')
        is_quick_filter = 1 if group.get('quickFilter', False) else 0
        member_tags = group.get('tags', [])

        if not primary_tag:
            continue

        print(f"\n{'=' * 50}")
        print(f"Group: {primary_tag} {emoji}  (quickFilter={bool(is_quick_filter)}, order={order})")
        print(f"  {len(member_tags)} member tags")

        # Find or create the primary tag
        parent_id = find_or_create_tag(cursor, primary_tag, dry_run)
        tags_in_groups.add(primary_tag.lower().replace(' ', ''))

        # Update primary tag metadata
        if not dry_run and parent_id:
            cursor.execute("""
                UPDATE tags SET emoji = %s, is_quick_filter = %s, display_order = %s, type = 'tag'
                WHERE id = %s
            """, (emoji, is_quick_filter, order, parent_id))
            tag_updates += 1
        else:
            print(f"  [DRY-RUN] Would update {primary_tag}: emoji={emoji}, quick_filter={is_quick_filter}, order={order}")
            tag_updates += 1

        # Process member tags
        for tag_name in member_tags:
            tag_normalized = tag_name.lower().replace(' ', '')
            tags_in_groups.add(tag_normalized)

            child_id = find_or_create_tag(cursor, tag_name, dry_run)

            # Set type='tag' for all member tags
            if not dry_run and child_id:
                cursor.execute("UPDATE tags SET type = 'tag' WHERE id = %s", (child_id,))

            # Insert hierarchy relationship (skip self-references like Music -> Music)
            if tag_name == primary_tag:
                continue

            if not dry_run and parent_id and child_id:
                cursor.execute("""
                    INSERT IGNORE INTO tag_hierarchy (parent_tag_id, child_tag_id)
                    VALUES (%s, %s)
                """, (parent_id, child_id))
                if cursor.rowcount > 0:
                    hierarchy_inserts += 1
            else:
                print(f"  [DRY-RUN] {primary_tag} -> {tag_name}")
                hierarchy_inserts += 1

    # Mark tags not in any group as keywords
    print(f"\n{'=' * 50}")
    print("Classifying orphan tags as keywords...")

    cursor.execute("SELECT id, name FROM tags")
    all_tags = cursor.fetchall()
    keyword_count = 0
    for tag in all_tags:
        normalized = tag['name'].lower().replace(' ', '')
        if normalized not in tags_in_groups:
            keyword_count += 1
            if not dry_run:
                cursor.execute("UPDATE tags SET type = 'keyword' WHERE id = %s", (tag['id'],))
            else:
                print(f"  [DRY-RUN] keyword: {tag['name']}")

    # Validate no cycles
    print(f"\n{'=' * 50}")
    print("Validating hierarchy (checking for cycles)...")
    if not dry_run:
        cursor.execute("SELECT parent_tag_id, child_tag_id FROM tag_hierarchy")
        edges = cursor.fetchall()
        children_of = {}
        for edge in edges:
            children_of.setdefault(edge['parent_tag_id'], set()).add(edge['child_tag_id'])

        def has_cycle(start, visited=None):
            if visited is None:
                visited = set()
            if start in visited:
                return True
            visited.add(start)
            for child in children_of.get(start, set()):
                if has_cycle(child, visited.copy()):
                    return True
            return False

        cycle_found = False
        for node in children_of:
            if has_cycle(node):
                print(f"  CYCLE DETECTED starting from tag id {node}!")
                cycle_found = True
                break

        if not cycle_found:
            print("  No cycles detected.")
    else:
        print("  [DRY-RUN] Skipping cycle check.")

    # Summary
    print(f"\n{'=' * 50}")
    print("Summary:")
    print(f"  Tag metadata updates: {tag_updates}")
    print(f"  Hierarchy relationships: {hierarchy_inserts}")
    print(f"  Tags classified as keywords: {keyword_count}")
    print(f"  Total tags in groups: {len(tags_in_groups)}")

    if dry_run:
        print("\n  [DRY-RUN] No changes applied. Use --apply to apply changes.")
        conn.close()
    else:
        conn.commit()
        conn.close()
        print("\n  Changes applied successfully.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Migrate tag_groups.json into database hierarchy')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default is dry-run)')
    args = parser.parse_args()
    migrate(dry_run=not args.apply)
