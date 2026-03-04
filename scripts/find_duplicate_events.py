"""Find potential duplicate events at the same location with overlapping dates.

Checks both start_date matches and date range overlaps. Uses the merger's
name similarity logic to classify pairs by confidence level.

Usage:
    ./venv/bin/python scripts/find_duplicate_events.py [--suppress] [--review]
"""
import argparse
import sys
sys.path.insert(0, 'pipeline')

from db import create_connection
from merger import normalize_name_for_dedup, are_names_similar


def find_duplicates(cursor):
    """Find active event pairs at the same location with overlapping dates."""
    cursor.execute("""
        SELECT e1.id as id1, e2.id as id2,
               e1.name as name1, e2.name as name2,
               e1.location_id, l.name as location_name,
               e1.website_id as ws1, e2.website_id as ws2
        FROM events e1
        JOIN events e2 ON e1.id < e2.id
            AND e1.location_id = e2.location_id
            AND e1.location_id IS NOT NULL
        LEFT JOIN locations l ON e1.location_id = l.id
        WHERE e1.archived = 0 AND e1.suppressed = 0
          AND e2.archived = 0 AND e2.suppressed = 0
          AND EXISTS (
              SELECT 1 FROM event_occurrences eo1
              JOIN event_occurrences eo2 ON (
                  eo1.start_date = eo2.start_date
                  OR (eo1.end_date IS NOT NULL
                      AND eo2.start_date BETWEEN eo1.start_date AND eo1.end_date)
                  OR (eo2.end_date IS NOT NULL
                      AND eo1.start_date BETWEEN eo2.start_date AND eo2.end_date)
              )
              WHERE eo1.event_id = e1.id AND eo2.event_id = e2.id
          )
        ORDER BY e1.id
    """)
    return cursor.fetchall()


def classify_pairs(pairs):
    """Classify pairs into confidence tiers.

    Returns: (exact_dupes, similar_dupes)
        exact_dupes: Identical normalized names — safe to auto-suppress
        similar_dupes: are_names_similar() match — needs manual review
    """
    exact_dupes = []
    similar_dupes = []

    for row in pairs:
        id1, id2, name1, name2, loc_id, loc_name, ws1, ws2 = row
        norm1 = normalize_name_for_dedup(name1)
        norm2 = normalize_name_for_dedup(name2)

        entry = {
            'id1': id1, 'id2': id2,
            'name1': name1, 'name2': name2,
            'location_id': loc_id, 'location_name': loc_name,
            'ws1': ws1, 'ws2': ws2,
        }

        if norm1 == norm2:
            exact_dupes.append(entry)
        elif are_names_similar(name1, name2):
            similar_dupes.append(entry)

    return exact_dupes, similar_dupes


def collect_suppress_ids(pairs):
    """Collect the higher ID from each pair (the duplicate to suppress)."""
    to_suppress = set()
    for entry in pairs:
        to_suppress.add(entry['id2'])
    return to_suppress


def print_pairs(pairs, label):
    """Print pairs in a readable format."""
    if not pairs:
        return
    print(f"\n{'='*60}")
    print(f" {label} ({len(pairs)} pairs)")
    print(f"{'='*60}")
    for entry in pairs:
        print(f"\n  {entry['id1']} vs {entry['id2']}:")
        print(f"    \"{entry['name1']}\"")
        if entry['name1'] != entry['name2']:
            print(f"    \"{entry['name2']}\"")
        print(f"    @ {entry['location_name']} (loc:{entry['location_id']}, ws:{entry['ws1']} vs {entry['ws2']})")


def main():
    parser = argparse.ArgumentParser(description='Find duplicate events')
    parser.add_argument('--suppress', action='store_true',
                        help='Auto-suppress exact-name duplicates')
    parser.add_argument('--review', action='store_true',
                        help='Also show similar-name pairs that need manual review')
    args = parser.parse_args()

    conn = create_connection()
    cursor = conn.cursor()

    print("Searching for potential duplicates...")
    pairs = find_duplicates(cursor)
    print(f"Found {len(pairs)} event pairs at same location with overlapping dates")

    exact_dupes, similar_dupes = classify_pairs(pairs)

    print_pairs(exact_dupes, "EXACT NAME DUPLICATES (safe to auto-suppress)")

    if args.review:
        print_pairs(similar_dupes, "SIMILAR NAME PAIRS (manual review needed)")

    # Summary
    print(f"\n--- Summary ---")
    print(f"Exact name dupes: {len(exact_dupes)} pairs")
    print(f"Similar name pairs: {len(similar_dupes)} pairs (use --review to see)")

    if exact_dupes:
        to_suppress = collect_suppress_ids(exact_dupes)
        print(f"Events to auto-suppress: {len(to_suppress)}")
        print(f"IDs: {sorted(to_suppress)}")

        if args.suppress:
            placeholders = ','.join(['%s'] * len(to_suppress))
            cursor.execute(
                f'UPDATE events SET suppressed = 1 WHERE id IN ({placeholders})',
                tuple(to_suppress)
            )
            conn.commit()
            print(f"\nSuppressed {cursor.rowcount} events.")
        else:
            print("\nRun with --suppress to auto-suppress exact-name duplicates.")
    else:
        print("\nNo exact-name duplicates found.")

    cursor.close()
    conn.close()


if __name__ == '__main__':
    main()
