#!/usr/bin/env python3
"""
Find events that may need suppression based on pattern rules.

Scans unreviewed, non-archived events and flags candidates for human review.
Outputs candidates sorted by number of matching patterns (most suspicious first).

Usage:
    ./venv/bin/python scripts/find_review_candidates.py              # Show first 50
    ./venv/bin/python scripts/find_review_candidates.py --limit 100  # Show 100
    ./venv/bin/python scripts/find_review_candidates.py --offset 50  # Skip first 50
    ./venv/bin/python scripts/find_review_candidates.py --pattern 13 # Only pattern 13
    ./venv/bin/python scripts/find_review_candidates.py --count      # Summary counts
"""

import argparse
import sys

sys.path.insert(0, 'pipeline')
from db import create_connection

# Each pattern: id, name, and SQL WHERE clause (applied to events e)
# JOINs are specified separately for patterns that need them
PATTERNS = [
    {
        'id': 1,
        'name': 'Generic brunch/happy hour',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND e.name REGEXP '(brunch|happy hour)'
        """,
    },
    {
        'id': 2,
        'name': 'Closures and non-events',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP '(^Closed|Closed$|^CLOSED|\\\\bClosed for\\\\b|\\\\bClosure\\\\b|\\\\bOffice Closed\\\\b)'
                OR e.name REGEXP 'Venue Closed|We Are Closed|Closed Due'
                OR e.name LIKE '%Private Party%'
                OR (e.name LIKE '%Recess%' AND (e.name LIKE '%Closed%' OR e.name LIKE '%No Programming%' OR e.description LIKE '%closed%'))
                OR (e.name LIKE '%Recess%' AND e.location_name LIKE '%Public Schools%')
              )
        """,
    },
    {
        'id': 3,
        'name': 'Invite-only and non-public',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name LIKE '%Invite-Only%'
                OR e.name LIKE '%Invite Only%'
                OR e.description LIKE '%invite-only%'
                OR e.description LIKE '%invited guests only%'
              )
        """,
    },
    {
        'id': 4,
        'name': 'Religious services and study groups',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP '(Bible Study|Prayer Group|Sunday School|Worship Service|Torah Study|Shabbat Service)'
                OR e.name REGEXP '^(Sunday|Weekly|Morning|Evening) (Service|Worship|Prayer|Mass)$'
              )
        """,
    },
    {
        'id': 5,
        'name': 'Auditions and rehearsals',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name LIKE '%Audition%'
                OR e.name LIKE '%Rehearsal%'
              )
        """,
    },
    {
        'id': 6,
        'name': 'In-school programs',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                (e.name REGEXP '(Residency|Workshop)' AND e.name REGEXP '(PS |P\\\\.S\\\\.|School)')
                OR e.description LIKE '%in-school%'
                OR (e.description LIKE '%grade%' AND e.description LIKE '%residency%')
                OR (e.description LIKE '%curriculum%' AND e.description LIKE '%student%')
              )
        """,
    },
    {
        'id': 7,
        'name': 'Non-NYC virtual events',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND e.location_name IN ('Online', 'Virtual', 'Online Event', 'Virtual Event', 'ZOOM', 'Online via Zoom', 'Webex')
              AND (
                e.name LIKE '%Region %' AND e.name NOT LIKE '%Region 2%'
                OR e.description LIKE '%DC/DE/MD%'
                OR e.description LIKE '%Scotland%'
                OR e.description LIKE '%UK %'
                OR e.description REGEXP 'for (the )?[A-Z][a-z]+ region'
                OR e.name REGEXP '^[^a-zA-Z0-9]*[À-ÿ]'
              )
        """,
    },
    {
        'id': 8,
        'name': 'Members-only / exclusive access',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name LIKE '%Member Exclusive%'
                OR e.name LIKE '%Members Only%'
                OR e.description LIKE '%member-exclusive%'
                OR e.description LIKE '%members only%'
                OR e.description LIKE '%donors and subscribers%'
                OR e.description LIKE '%invited guests only%'
              )
        """,
    },
    {
        'id': 9,
        'name': 'Registration dates and non-events',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name LIKE '%Registration Start%'
                OR e.name LIKE '%Registration Opens%'
                OR e.name LIKE '%Application Deadline%'
                OR e.name LIKE '%Availability%'
                OR e.name LIKE '%Now Open%'
              )
        """,
    },
    {
        'id': 10,
        'name': 'Price-focused (no programming)',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.description REGEXP '\\\\$[0-9]+ (drinks|cocktails|beers|wines|mimosas)'
                OR e.description REGEXP '(drinks|cocktails|beers) (starting at|for just|from) \\\\$[0-9]+'
              )
              AND e.description NOT REGEXP '(dj|live|perform|comedy|class|workshop|fundrais|benefit)'
        """,
    },
    {
        'id': 11,
        'name': '"Every week" without programming',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND e.description REGEXP 'every (day|week|weekend|saturday|sunday)'
              AND e.description NOT REGEXP '(dj|live|perform|artist|musician|comedy|comedian|host|featuring|present|trivia|karaoke|open mic)'
        """,
    },
    {
        'id': 12,
        'name': 'Food/drink-only tags',
        'query': """
            SELECT e.id FROM events e
            JOIN event_tags et ON e.id = et.event_id
            JOIN tags t ON et.tag_id = t.id
            WHERE e.archived = 0 AND e.reviewed = 0
            GROUP BY e.id
            HAVING GROUP_CONCAT(t.name SEPARATOR ', ')
              REGEXP '^(Dining|Brunch|Food|Cocktails|Happy Hour|Weekend|Sunday|Saturday|Bottomless|Drinks|Bar|Restaurant|Eats|,| )+$'
        """,
    },
    {
        'id': 13,
        'name': 'High-occurrence (30+ occurrences or 60+ day span)',
        'query': """
            SELECT e.id FROM events e
            LEFT JOIN event_occurrences eo ON e.id = eo.event_id
            WHERE e.archived = 0 AND e.reviewed = 0
            GROUP BY e.id
            HAVING COUNT(eo.id) >= 30
              OR DATEDIFF(MAX(eo.start_date), MIN(eo.start_date)) >= 60
        """,
    },
    {
        'id': 14,
        'name': 'Shopping center promotions',
        'query': """
            SELECT DISTINCT e.id FROM events e
            JOIN websites w ON e.website_id = w.id
            WHERE e.archived = 0 AND e.reviewed = 0
              AND w.name IN ('Hudson Yards', 'The Shops at Columbus Circle',
                             'Brookfield Place', 'Industry City', 'Olly Olly Market')
        """,
    },
    {
        'id': 15,
        'name': 'Shops, sales, and permanent attractions',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP '(Sale|Shop|Store|Boutique)$'
                OR e.name LIKE '%Grand Opening%'
                OR e.name LIKE '%Now Open%'
                OR e.name LIKE '%% Off%'
                OR (e.description LIKE '%shop %' AND e.description LIKE '%save %')
              )
        """,
    },
    {
        'id': 16,
        'name': 'Zoo/aquarium daily activities',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name LIKE '%Feeding%'
                OR e.name LIKE '%Daily %'
                OR (e.description LIKE '%daily %' AND e.description LIKE '%scheduled%')
              )
        """,
    },
    {
        'id': 17,
        'name': 'School schedule notices',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP '^Flex Day'
                OR e.name REGEXP '(Professional Development|PD Day|Staff Development|Teacher).*Day'
                OR e.name REGEXP '^No (School|Classes|Programming)'
                OR e.name LIKE '%School Closed%'
                OR e.name LIKE '%Classes Canceled%'
                OR e.name LIKE '%Classes Cancelled%'
                OR e.name REGEXP '^(Spring|Winter|Summer|Fall|Holiday|Thanksgiving|Christmas) (Break|Recess|Vacation)$'
              )
        """,
    },
    {
        'id': 18,
        'name': 'TBA/placeholder events',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP '^TBA$'
                OR e.name REGEXP '^TBD$'
                OR e.name LIKE '%Coming Soon%'
                OR e.name LIKE '%To Be Announced%'
                OR e.name LIKE '%To Be Determined%'
                OR e.name LIKE '%Stay Tuned%'
              )
        """,
    },
    {
        'id': 19,
        'name': 'Cancelled/postponed notices',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name LIKE '%CANCELLED%'
                OR e.name LIKE '%CANCELED%'
                OR e.name LIKE '%Cancelled%'
                OR e.name LIKE '%Canceled%'
                OR e.name LIKE '%POSTPONED%'
                OR e.name LIKE '%Postponed%'
                OR e.name REGEXP 'postponed$'
              )
        """,
    },
    {
        'id': 20,
        'name': 'Service office hours (non-events)',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name LIKE '%Office Hours%'
                OR e.name LIKE '%Office hours%'
              )
              AND e.description NOT REGEXP '(perform|music|comedy|dj|live|concert|show)'
        """,
    },
    {
        'id': 21,
        'name': 'Internal campus events',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP 'Class of 20[0-9]{2}'
                OR e.name LIKE '%Student Legacy%'
                OR e.name LIKE '%Commencement%'
                OR e.name LIKE '%Convocation%'
              )
        """,
    },
]


def collect_candidates(cursor, pattern_filter=None):
    """Run all patterns and collect {event_id: [pattern_names]}."""
    candidates = {}  # event_id -> list of pattern dicts

    for p in PATTERNS:
        if pattern_filter is not None and p['id'] != pattern_filter:
            continue

        cursor.execute(p['query'])
        for (event_id,) in cursor.fetchall():
            if event_id not in candidates:
                candidates[event_id] = []
            candidates[event_id].append(p)

    return candidates


def print_counts(cursor, pattern_filter=None):
    """Print match counts per pattern."""
    total_ids = set()

    print(f"{'#':>3}  {'Pattern':<50} {'Matches':>7}")
    print("─" * 64)

    for p in PATTERNS:
        if pattern_filter is not None and p['id'] != pattern_filter:
            continue

        cursor.execute(p['query'])
        ids = {row[0] for row in cursor.fetchall()}
        total_ids |= ids

        count = len(ids)
        if count > 0:
            print(f"{p['id']:>3}. {p['name']:<50} {count:>7}")

    print("─" * 64)
    print(f"     {'Total unique candidates':<50} {len(total_ids):>7}")

    # Also show total unreviewed for context
    cursor.execute("SELECT COUNT(*) FROM events WHERE archived = 0 AND reviewed = 0")
    (total_unreviewed,) = cursor.fetchone()
    print(f"     {'Total unreviewed events':<50} {total_unreviewed:>7}")


def fetch_event_details(cursor, event_ids):
    """Fetch full details for a list of event IDs."""
    if not event_ids:
        return {}

    placeholders = ','.join(['%s'] * len(event_ids))
    cursor.execute(f"""
        SELECT e.id, e.name, e.location_name, LEFT(e.description, 250) as description,
               w.name as website_name,
               (SELECT GROUP_CONCAT(t.name SEPARATOR ', ')
                FROM event_tags et JOIN tags t ON et.tag_id = t.id
                WHERE et.event_id = e.id) as tags,
               (SELECT COUNT(*) FROM event_occurrences eo WHERE eo.event_id = e.id) as occ_count,
               (SELECT DATEDIFF(MAX(eo2.start_date), MIN(eo2.start_date))
                FROM event_occurrences eo2 WHERE eo2.event_id = e.id) as span_days
        FROM events e
        LEFT JOIN websites w ON e.website_id = w.id
        WHERE e.id IN ({placeholders})
    """, event_ids)

    details = {}
    for row in cursor.fetchall():
        details[row[0]] = {
            'id': row[0],
            'name': row[1],
            'location_name': row[2],
            'description': row[3],
            'website_name': row[4],
            'tags': row[5],
            'occ_count': row[6],
            'span_days': row[7],
        }
    return details


def print_candidates(candidates, details, offset, limit):
    """Print formatted candidate list."""
    # Sort: most matching patterns first, then by event name
    sorted_ids = sorted(
        candidates.keys(),
        key=lambda eid: (-len(candidates[eid]), details.get(eid, {}).get('name', ''))
    )

    page = sorted_ids[offset:offset + limit]
    total = len(sorted_ids)

    print(f"=== Review Candidates ({offset + 1}-{min(offset + len(page), total)} of {total}) ===\n")

    for i, eid in enumerate(page, start=offset + 1):
        d = details.get(eid)
        if not d:
            continue

        pattern_labels = ', '.join(f"#{p['id']} {p['name']}" for p in candidates[eid])

        print(f"[{i}] ID {d['id']}: {d['name']}")
        print(f"    Location: {d['location_name'] or '(none)'}")
        if d['website_name']:
            print(f"    Website: {d['website_name']}")
        if d['tags']:
            print(f"    Tags: {d['tags']}")
        if d['occ_count'] and d['occ_count'] > 1:
            print(f"    Occurrences: {d['occ_count']} (span: {d['span_days'] or 0} days)")
        print(f"    Patterns: {pattern_labels}")
        print(f"    Desc: {d['description']}")
        print()


def main():
    parser = argparse.ArgumentParser(description='Find events that may need suppression')
    parser.add_argument('--limit', type=int, default=50, help='Number of candidates to show (default: 50)')
    parser.add_argument('--offset', type=int, default=0, help='Skip first N candidates')
    parser.add_argument('--pattern', type=int, help='Only show matches for this pattern number (1-21)')
    parser.add_argument('--count', action='store_true', help='Just show match counts per pattern')
    args = parser.parse_args()

    conn = create_connection()
    if not conn:
        print("Failed to connect to database")
        sys.exit(1)

    cursor = conn.cursor(buffered=True)

    try:
        if args.count:
            print_counts(cursor, args.pattern)
        else:
            candidates = collect_candidates(cursor, args.pattern)
            if not candidates:
                print("No candidates found.")
                return

            event_ids = list(candidates.keys())
            details = fetch_event_details(cursor, event_ids)
            print_candidates(candidates, details, args.offset, args.limit)
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    main()
