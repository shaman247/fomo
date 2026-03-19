#!/usr/bin/env python3
"""
Analyze tag correlations to find tags closely associated with a category
but not in its hierarchy.

For each quick filter category (Art, Music, etc.), computes P(C|T) — the
probability an event is in category C given it has tag T — for all tags
not already in the category's hierarchy.

Usage:
    ./venv/bin/python scripts/analyze_tag_correlations.py
    ./venv/bin/python scripts/analyze_tag_correlations.py --category Art
    ./venv/bin/python scripts/analyze_tag_correlations.py --threshold 0.8 --min-events 10
"""

import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pipeline'))
from db import create_connection


def load_hierarchy():
    """Load tag hierarchy and build descendants map for each tag."""
    hierarchy_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'data', 'tag_hierarchy.json')
    with open(hierarchy_path) as f:
        data = json.load(f)

    # Build parent -> children map
    parent_children = defaultdict(set)
    quick_filters = []
    for t in data['tags']:
        name = t['name']
        for p in t.get('parents', []):
            parent_children[p].add(name)
        if t.get('quickFilter'):
            quick_filters.append((t.get('order', 999), name))

    quick_filters.sort()
    quick_filter_names = [name for _, name in quick_filters]

    # Build transitive descendants
    def get_descendants(name, visited=None):
        if visited is None:
            visited = set()
        if name in visited:
            return set()
        visited.add(name)
        result = set()
        for child in parent_children.get(name, set()):
            result.add(child)
            result.update(get_descendants(child, visited))
        return result

    descendants_of = {}
    for cat in quick_filter_names:
        descendants_of[cat] = get_descendants(cat)

    return quick_filter_names, descendants_of


def analyze(category_filter=None, threshold=0.7, min_events=5, show_missing=3):
    conn = create_connection()
    if not conn:
        print("Failed to connect to database")
        return
    cursor = conn.cursor()

    quick_filters, descendants_of = load_hierarchy()

    if category_filter:
        quick_filters = [c for c in quick_filters if c.lower() == category_filter.lower()]
        if not quick_filters:
            print(f"Category '{category_filter}' not found")
            return

    # Get tag IDs for quick filter categories
    cat_name_to_id = {}
    for cat in quick_filters:
        cursor.execute("SELECT id FROM tags WHERE name = %s", (cat,))
        row = cursor.fetchone()
        if row:
            cat_name_to_id[cat] = row[0]

    cat_ids = list(cat_name_to_id.values())
    cat_id_to_name = {v: k for k, v in cat_name_to_id.items()}

    # Build tag name -> id mapping for hierarchy exclusion
    cursor.execute("SELECT id, name FROM tags")
    tag_id_to_name = {r[0]: r[1] for r in cursor.fetchall()}
    tag_name_to_id = {r[1]: r[0] for r in tag_id_to_name.items()}

    # Query 1: total events per tag (active events only)
    print("Loading event counts per tag...")
    cursor.execute("""
        SELECT et.tag_id, COUNT(DISTINCT et.event_id) as total
        FROM event_tags et
        JOIN events e ON et.event_id = e.id
        WHERE e.archived = 0 AND e.suppressed = 0
        GROUP BY et.tag_id
        HAVING total >= %s
    """, (min_events,))
    tag_totals = {r[0]: r[1] for r in cursor.fetchall()}

    # Total active events (for base rate / lift calculation)
    cursor.execute("SELECT COUNT(*) FROM events WHERE archived = 0 AND suppressed = 0")
    total_events = cursor.fetchone()[0]
    print(f"Total active events: {total_events}")
    print(f"Tags with >= {min_events} events: {len(tag_totals)}")

    # Query 2: co-occurrence counts for (tag, category) pairs
    print("Computing co-occurrences...")
    placeholders = ','.join(['%s'] * len(cat_ids))
    cursor.execute(f"""
        SELECT et1.tag_id, et2.tag_id as cat_tag_id, COUNT(DISTINCT et1.event_id) as co_count
        FROM event_tags et1
        JOIN event_tags et2 ON et1.event_id = et2.event_id
        JOIN events e ON et1.event_id = e.id
        WHERE e.archived = 0 AND e.suppressed = 0
          AND et2.tag_id IN ({placeholders})
          AND et1.tag_id != et2.tag_id
        GROUP BY et1.tag_id, et2.tag_id
    """, cat_ids)

    # co_counts[tag_id][cat_id] = count
    co_counts = defaultdict(dict)
    for tag_id, cat_id, count in cursor.fetchall():
        co_counts[tag_id][cat_id] = count

    # Compute base rates for each category
    cat_base_rates = {}
    for cat_name, cat_id in cat_name_to_id.items():
        cat_base_rates[cat_name] = tag_totals.get(cat_id, 0) / total_events

    # Analyze each category
    for cat_name in quick_filters:
        cat_id = cat_name_to_id.get(cat_name)
        if not cat_id:
            continue

        # Tags in this category's hierarchy (to exclude)
        hierarchy_tags = descendants_of.get(cat_name, set()) | {cat_name}
        hierarchy_tag_ids = {tag_name_to_id[t] for t in hierarchy_tags if t in tag_name_to_id}

        base_rate = cat_base_rates[cat_name]

        # Compute P(C|T) for each non-hierarchy tag
        candidates = []
        for tag_id, total in tag_totals.items():
            if tag_id in hierarchy_tag_ids:
                continue
            co = co_counts.get(tag_id, {}).get(cat_id, 0)
            p_ct = co / total
            lift = p_ct / base_rate if base_rate > 0 else 0
            missing = total - co

            if p_ct >= threshold:
                tag_name = tag_id_to_name.get(tag_id, f"id:{tag_id}")
                candidates.append((p_ct, lift, co, total, missing, tag_name, tag_id))

        if not candidates:
            continue

        candidates.sort(key=lambda x: (-x[0], -x[3]))

        print(f"\n{'='*70}")
        print(f"  {cat_name} (base rate: {base_rate:.1%}, {tag_totals.get(cat_id, 0)} events)")
        print(f"{'='*70}")

        # Split into tiers
        tier1 = [c for c in candidates if c[0] >= 0.9 and c[3] >= 10]
        tier2 = [c for c in candidates if not (c[0] >= 0.9 and c[3] >= 10)]

        if tier1:
            print(f"\n  TIER 1 — High confidence (P >= 0.9, n >= 10):")
            for p_ct, lift, co, total, missing, tag_name, tag_id in tier1:
                print(f"    {tag_name}: P={p_ct:.0%} ({co}/{total}), lift={lift:.1f}x, {missing} missing")
                if missing > 0 and show_missing > 0:
                    _show_missing_events(cursor, tag_id, cat_id, show_missing)

        if tier2:
            print(f"\n  TIER 2 — Worth investigating (P >= {threshold:.0%}):")
            for p_ct, lift, co, total, missing, tag_name, tag_id in tier2:
                print(f"    {tag_name}: P={p_ct:.0%} ({co}/{total}), lift={lift:.1f}x, {missing} missing")
                if missing > 0 and show_missing > 0:
                    _show_missing_events(cursor, tag_id, cat_id, show_missing)

    cursor.close()
    conn.close()


def _show_missing_events(cursor, tag_id, cat_id, limit):
    """Show events that have the tag but NOT the category."""
    cursor.execute("""
        SELECT e.id, e.name
        FROM events e
        JOIN event_tags et ON e.id = et.event_id
        WHERE et.tag_id = %s
          AND e.archived = 0 AND e.suppressed = 0
          AND e.id NOT IN (
              SELECT et2.event_id FROM event_tags et2 WHERE et2.tag_id = %s
          )
        LIMIT %s
    """, (tag_id, cat_id, limit))
    rows = cursor.fetchall()
    for eid, ename in rows:
        print(f"      → [{eid}] {ename}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Analyze tag correlations with quick filter categories')
    parser.add_argument('--category', '-c', help='Analyze only this category')
    parser.add_argument('--threshold', '-t', type=float, default=0.7, help='Minimum P(C|T) threshold (default: 0.7)')
    parser.add_argument('--min-events', '-n', type=int, default=5, help='Minimum events per tag (default: 5)')
    parser.add_argument('--show-missing', '-m', type=int, default=3, help='Missing events to show per candidate (default: 3)')
    args = parser.parse_args()

    analyze(
        category_filter=args.category,
        threshold=args.threshold,
        min_events=args.min_events,
        show_missing=args.show_missing,
    )
