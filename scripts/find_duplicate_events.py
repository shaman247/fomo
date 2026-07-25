"""Find potential duplicate events.

Detection methods:
1. Same location + overlapping dates, classified by name similarity
2. Shared URLs (ignoring query params) — catches re-extractions with different names
3. Same location + matching date AND start_time — catches cross-source dupes
   where names diverge completely (e.g. organizer name vs venue name)
4. Cross-location shared URL — two events at DIFFERENT locations that share a
   specific event URL. Catches the "location scatter" bug where one real event
   ends up as two rows at different location_ids (e.g. a SummerStage concert
   listed once at "Central Park SummerStage" and once at generic "Central
   Park"), so it renders twice on the map. Tiers 1 and 3 both require the same
   location_id and are structurally blind to this. Review-only — NEVER
   auto-suppressed, because the same name/URL across genuinely different venues
   is often legitimate (a library program at many branches, a touring show).

Pairs reviewed and decided NOT-a-duplicate are recorded in
`dedupe_dismissed_pairs` and filtered out of all review tiers on future
runs, so the same false positives don't keep resurfacing.

Reusable helpers (importable):
    apply_field_overrides(cursor, event_id, ...) — update scalar fields after review
    merge_pair(cursor, keep_id, delete_id) — merge collections + suppress
    record_dismissal(cursor, id1, id2, reason) — mark a pair as not-a-dup
    get_dismissed_pairs(cursor) — set of (lower_id, higher_id) tuples

Usage:
    ./venv/bin/python scripts/find_duplicate_events.py [--suppress] [--review]
"""
import argparse
import sys
sys.path.insert(0, 'pipeline')

from collections import defaultdict
from urllib.parse import urlparse

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


def find_shared_url_pairs(cursor):
    """Find active event pairs that share a specific URL (ignoring query params).

    Filters out generic venue/calendar URLs by requiring 2+ path segments
    and only counting URLs shared by at most 3 events (venue homepages
    are shared by many more).
    """
    cursor.execute("""
        SELECT eu.event_id, eu.url
        FROM event_urls eu
        JOIN events e ON eu.event_id = e.id
        WHERE e.archived = 0 AND e.suppressed = 0
    """)
    url_to_events = defaultdict(set)
    for event_id, url in cursor.fetchall():
        base_url = url.split('?')[0].rstrip('/')
        path = urlparse(base_url).path.strip('/')
        # Skip generic URLs (homepages, single-segment paths like /events)
        segments = [s for s in path.split('/') if s]
        if len(segments) < 2:
            continue
        url_to_events[base_url].add(event_id)

    pairs = set()
    for event_ids in url_to_events.values():
        # URLs shared by 4+ events are likely venue/series pages, not specific events
        if 2 <= len(event_ids) <= 3:
            ids = sorted(event_ids)
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    pairs.add((ids[i], ids[j]))
    return pairs


def find_same_time_pairs(cursor):
    """Find active event pairs at same location with matching date AND start_time.

    Catches cross-source duplicates where names diverge completely (e.g. organizer
    title on Luma vs venue title on its own site). Multi-room venues (museums,
    cultural centers) can produce false positives — flagged for manual review.
    """
    cursor.execute("""
        SELECT DISTINCT e1.id, e2.id
        FROM events e1
        JOIN events e2 ON e1.id < e2.id
            AND e1.location_id = e2.location_id
            AND e1.location_id IS NOT NULL
        JOIN event_occurrences eo1 ON eo1.event_id = e1.id
        JOIN event_occurrences eo2 ON eo2.event_id = e2.id
            AND eo1.start_date = eo2.start_date
            AND eo1.start_time = eo2.start_time
            AND eo1.start_time IS NOT NULL
            AND eo1.start_time != ''
        WHERE e1.archived = 0 AND e1.suppressed = 0
          AND e2.archived = 0 AND e2.suppressed = 0
    """)
    return {(id1, id2) for id1, id2 in cursor.fetchall()}


def find_cross_location_url_pairs(cursor, dismissed_pairs=None):
    """Find active event pairs that share a specific URL but sit at DIFFERENT locations.

    This is the "location scatter" tier: one real event that got split into two
    rows with different location_ids (usually one specific venue + one generic /
    wrong one), so it appears twice on the map. The existing same-location tiers
    can't see it. A shared specific event URL is the "same event" signal; the
    2-3-events-per-URL cap (as in find_shared_url_pairs) screens out generic
    calendar/venue URLs.

    Returns a list of entry dicts sorted strongest-first (same name AND same
    date+time first). Each entry carries both events' names, locations, and
    websites plus `same_name` / `same_dt` flags for review triage. Dismissed
    pairs are filtered out. Never auto-suppressed — surfaced for holistic review
    only, because a shared name/URL across genuinely different venues is often
    legitimate (multi-branch library programs, touring shows).
    """
    dismissed_pairs = dismissed_pairs or set()

    cursor.execute("""
        SELECT e.id, e.name, e.location_id, l.name, e.website_id
        FROM events e
        LEFT JOIN locations l ON l.id = e.location_id
        WHERE e.archived = 0 AND e.suppressed = 0 AND e.location_id IS NOT NULL
    """)
    meta = {}
    for eid, name, loc_id, loc_name, ws in cursor.fetchall():
        meta[eid] = {'name': name, 'loc_id': loc_id, 'loc_name': loc_name,
                     'ws': ws, 'norm': normalize_name_for_dedup(name), 'dt': set()}

    cursor.execute("""
        SELECT eo.event_id, eo.start_date, eo.start_time
        FROM event_occurrences eo
        JOIN events e ON e.id = eo.event_id
        WHERE e.archived = 0 AND e.suppressed = 0
    """)
    for eid, sd, st in cursor.fetchall():
        if eid in meta:
            meta[eid]['dt'].add((str(sd), st or ''))

    cursor.execute("""
        SELECT eu.event_id, eu.url
        FROM event_urls eu
        JOIN events e ON eu.event_id = e.id
        WHERE e.archived = 0 AND e.suppressed = 0
    """)
    url_to_events = defaultdict(set)
    for event_id, url in cursor.fetchall():
        if event_id not in meta:
            continue
        base_url = url.split('?')[0].rstrip('/')
        segments = [s for s in urlparse(base_url).path.strip('/').split('/') if s]
        if len(segments) < 2:
            continue
        url_to_events[base_url].add(event_id)

    entries = {}  # (a, b) -> entry, deduped across the multiple URLs a pair may share
    for base_url, event_ids in url_to_events.items():
        # Same generic-URL guard as find_shared_url_pairs: URLs shared by 4+
        # events are series/venue pages, not a single event.
        if not (2 <= len(event_ids) <= 3):
            continue
        ids = sorted(event_ids)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                if meta[a]['loc_id'] == meta[b]['loc_id']:
                    continue  # same location — the existing tiers already cover it
                if (a, b) in dismissed_pairs:
                    continue
                if (a, b) in entries:
                    continue
                A, B = meta[a], meta[b]
                entries[(a, b)] = {
                    'id1': a, 'id2': b,
                    'name1': A['name'], 'name2': B['name'],
                    'loc1': A['loc_id'], 'loc1_name': A['loc_name'],
                    'loc2': B['loc_id'], 'loc2_name': B['loc_name'],
                    'ws1': A['ws'], 'ws2': B['ws'],
                    'url': base_url,
                    'same_name': A['norm'] == B['norm'],
                    'same_dt': bool(A['dt'] & B['dt']),
                }

    # Strongest first: same name + same datetime, then same name, then same datetime.
    return sorted(entries.values(),
                  key=lambda e: (not (e['same_name'] and e['same_dt']),
                                 not e['same_name'], not e['same_dt'],
                                 e['id1'], e['id2']))


def record_dismissal(cursor, id1, id2, reason):
    """Mark a pair as reviewed-not-duplicate so it won't be re-flagged.

    Pair is normalized to (lower_id, higher_id) so order doesn't matter.
    Re-recording an existing pair updates the reason.
    """
    a, b = sorted([id1, id2])
    cursor.execute("""
        INSERT INTO dedupe_dismissed_pairs (event_id_a, event_id_b, reason)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE reason = VALUES(reason),
                                dismissed_at = CURRENT_TIMESTAMP
    """, (a, b, reason))


def get_dismissed_pairs(cursor):
    """Return set of (lower_id, higher_id) tuples of previously-dismissed pairs."""
    cursor.execute("SELECT event_id_a, event_id_b FROM dedupe_dismissed_pairs")
    return {(a, b) for a, b in cursor.fetchall()}


def classify_pairs(pairs, shared_url_pair_ids, same_time_pair_ids,
                   dismissed_pairs=None):
    """Classify pairs into confidence tiers.

    Returns: (exact_dupes, shared_url_dupes, cross_source_time_dupes,
              same_source_time_dupes, similar_dupes)
        exact_dupes: Identical normalized names — safe to auto-suppress
        shared_url_dupes: Different names but shared event URL — needs review
        cross_source_time_dupes: Different websites, same date+start_time — high signal
        same_source_time_dupes: Same website, same date+start_time — usually multi-room
            venue noise, gated behind --review
        similar_dupes: are_names_similar() match — needs manual review
    """
    exact_dupes = []
    shared_url_dupes = []
    cross_source_time_dupes = []
    same_source_time_dupes = []
    similar_dupes = []
    dismissed_pairs = dismissed_pairs or set()

    for row in pairs:
        id1, id2, name1, name2, loc_id, loc_name, ws1, ws2 = row
        # Skip pairs reviewed and dismissed in a previous run. Exact-name pairs
        # bypass dismissal because they're auto-suppressed without review.
        norm1 = normalize_name_for_dedup(name1)
        norm2 = normalize_name_for_dedup(name2)
        if norm1 != norm2:
            pair_key = (min(id1, id2), max(id1, id2))
            if pair_key in dismissed_pairs:
                continue

        entry = {
            'id1': id1, 'id2': id2,
            'name1': name1, 'name2': name2,
            'location_id': loc_id, 'location_name': loc_name,
            'ws1': ws1, 'ws2': ws2,
        }

        if norm1 == norm2:
            exact_dupes.append(entry)
        elif (id1, id2) in shared_url_pair_ids:
            shared_url_dupes.append(entry)
        elif (id1, id2) in same_time_pair_ids:
            if ws1 != ws2:
                cross_source_time_dupes.append(entry)
            else:
                same_source_time_dupes.append(entry)
        elif are_names_similar(name1, name2):
            similar_dupes.append(entry)

    return (exact_dupes, shared_url_dupes, cross_source_time_dupes,
            same_source_time_dupes, similar_dupes)


def collect_suppress_ids(pairs):
    """Collect the higher ID from each pair (the duplicate to suppress)."""
    to_suppress = set()
    for entry in pairs:
        to_suppress.add(entry['id2'])
    return to_suppress


def apply_field_overrides(cursor, event_id, name=None, description=None,
                          emoji=None, short_name=None, sublocation=None):
    """Update scalar fields on event_id with provided non-None values.

    Used after holistic review of a duplicate pair, when the reviewer (Claude)
    has decided what the merged event's fields should be. Pass only the fields
    that should change — None values are skipped.
    """
    updates = []
    if name is not None:
        updates.append(('name', name))
    if description is not None:
        updates.append(('description', description))
    if emoji is not None:
        updates.append(('emoji', emoji))
    if short_name is not None:
        updates.append(('short_name', short_name))
    if sublocation is not None:
        updates.append(('sublocation', sublocation))
    if not updates:
        return []
    set_clause = ', '.join(f'{k} = %s' for k, _ in updates)
    values = [v for _, v in updates] + [event_id]
    cursor.execute(f'UPDATE events SET {set_clause} WHERE id = %s', values)
    return [k for k, _ in updates]


def merge_pair(cursor, keep_id, delete_id):
    """Merge delete_id into keep_id: occurrences, URLs, tags, sources, then suppress.

    Does NOT touch scalar fields (name, description, emoji, etc.) on keep_id —
    update those separately via apply_field_overrides if needed.

    Dedupes occurrences on the kept event after merge.
    """
    cursor.execute("""
        INSERT IGNORE INTO event_occurrences (event_id, start_date, start_time, end_date, end_time)
        SELECT %s, start_date, start_time, end_date, end_time
        FROM event_occurrences WHERE event_id = %s
    """, (keep_id, delete_id))
    cursor.execute("""
        INSERT INTO event_urls (event_id, url)
        SELECT %s, eu_src.url FROM event_urls eu_src
        WHERE eu_src.event_id = %s
          AND NOT EXISTS (
            SELECT 1 FROM event_urls eu_dst
            WHERE eu_dst.event_id = %s AND eu_dst.url = eu_src.url
          )
    """, (keep_id, delete_id, keep_id))
    cursor.execute("""
        INSERT IGNORE INTO event_tags (event_id, tag_id)
        SELECT %s, et.tag_id FROM event_tags et
        WHERE et.event_id = %s
          AND NOT EXISTS (
            SELECT 1 FROM event_tag_blocks b
            WHERE b.event_id = %s AND b.tag_id = et.tag_id
          )
    """, (keep_id, delete_id, keep_id))
    cursor.execute("""
        INSERT IGNORE INTO event_sources (event_id, crawl_event_id)
        SELECT %s, crawl_event_id FROM event_sources WHERE event_id = %s
    """, (keep_id, delete_id))
    cursor.execute("""
        INSERT IGNORE INTO event_tag_blocks (event_id, tag_id, reason)
        SELECT %s, tag_id, reason FROM event_tag_blocks WHERE event_id = %s
    """, (keep_id, delete_id))
    # reviewed=1 alongside suppressed=1: a suppressed row left reviewed=0 is indistinguishable
    # from a real event that some automated pass hid by mistake. On 2026-07-18 that ambiguity had
    # accumulated to 923 suppressed+unreviewed events with FUTURE dates, which took a full audit to
    # resolve (76 turned out to be wrongly hidden). Merging away a duplicate IS a review decision.
    cursor.execute("UPDATE events SET suppressed = 1, reviewed = 1 WHERE id = %s", (delete_id,))
    cursor.execute("""
        DELETE o1 FROM event_occurrences o1
        INNER JOIN event_occurrences o2
        ON o1.event_id = o2.event_id
           AND o1.start_date = o2.start_date
           AND COALESCE(o1.start_time, '') = COALESCE(o2.start_time, '')
           AND o1.id > o2.id
        WHERE o1.event_id = %s
    """, (keep_id,))


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


def print_xloc_pairs(pairs, label):
    """Print cross-location shared-URL pairs (two different locations per pair)."""
    if not pairs:
        return
    print(f"\n{'='*60}")
    print(f" {label} ({len(pairs)} pairs)")
    print(f"{'='*60}")
    for e in pairs:
        conf = ('name+time' if e['same_name'] and e['same_dt']
                else 'name' if e['same_name']
                else 'time' if e['same_dt'] else 'url-only')
        print(f"\n  {e['id1']} vs {e['id2']}  [{conf}]")
        print(f"    \"{e['name1']}\" @ {e['loc1_name']} (loc:{e['loc1']}, ws:{e['ws1']})")
        print(f"    \"{e['name2']}\" @ {e['loc2_name']} (loc:{e['loc2']}, ws:{e['ws2']})")
        print(f"    shared URL: {e['url']}")


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

    print("Checking for shared URLs...")
    shared_url_pair_ids = find_shared_url_pairs(cursor)

    print("Checking for same-time pairs...")
    same_time_pair_ids = find_same_time_pairs(cursor)

    dismissed_pairs = get_dismissed_pairs(cursor)
    print(f"Loaded {len(dismissed_pairs)} previously-dismissed pairs")

    print("Checking for cross-location shared-URL pairs...")
    cross_location_all = find_cross_location_url_pairs(cursor, dismissed_pairs)
    # High-confidence (same name AND same date+time) shown by default; the weaker
    # ones (name-or-time-only, or url-only) are noisier and gated behind --review,
    # mirroring how same-source-time and similar-name tiers are gated.
    cross_location_strong = [e for e in cross_location_all if e['same_name'] and e['same_dt']]
    cross_location_weak = [e for e in cross_location_all if not (e['same_name'] and e['same_dt'])]

    (exact_dupes, shared_url_dupes, cross_source_time_dupes,
     same_source_time_dupes, similar_dupes) = classify_pairs(
        pairs, shared_url_pair_ids, same_time_pair_ids, dismissed_pairs
    )

    print_pairs(exact_dupes, "EXACT NAME DUPLICATES (safe to auto-suppress)")
    print_pairs(shared_url_dupes, "SHARED URL DUPLICATES (review needed)")
    print_pairs(cross_source_time_dupes,
                "CROSS-SOURCE SAME DATE+TIME DUPLICATES (review needed)")
    print_xloc_pairs(cross_location_strong,
                     "CROSS-LOCATION SHARED-URL DUPLICATES — same name+time (scatter bug, review needed)")

    if args.review:
        print_xloc_pairs(cross_location_weak,
                         "CROSS-LOCATION SHARED-URL PAIRS — weaker (name-or-time-only; more false positives)")
        print_pairs(same_source_time_dupes,
                    "SAME-SOURCE SAME DATE+TIME PAIRS (often multi-room venue noise)")
        print_pairs(similar_dupes, "SIMILAR NAME PAIRS (review needed)")

    # Summary
    print(f"\n--- Summary ---")
    print(f"Exact name dupes: {len(exact_dupes)} pairs")
    print(f"Shared URL dupes: {len(shared_url_dupes)} pairs")
    print(f"Cross-source same date+time dupes: {len(cross_source_time_dupes)} pairs")
    print(f"Cross-location shared-URL dupes (same name+time): {len(cross_location_strong)} pairs")
    print(f"Cross-location shared-URL pairs (weaker): {len(cross_location_weak)} pairs (use --review to see)")
    print(f"Same-source same date+time pairs: {len(same_source_time_dupes)} pairs (use --review to see)")
    print(f"Similar name pairs: {len(similar_dupes)} pairs (use --review to see)")

    if exact_dupes:
        to_suppress = collect_suppress_ids(exact_dupes)
        print(f"Events to auto-suppress: {len(to_suppress)}")
        print(f"IDs: {sorted(to_suppress)}")

        if args.suppress:
            # Serialize against other sessions' writes (see pipeline/dblock.py).
            from dblock import write_lock
            placeholders = ','.join(['%s'] * len(to_suppress))
            with write_lock(conn, label="find_duplicate_events --suppress"):
                # reviewed=1 too — see the note in merge_pair(); an exact-name auto-suppress is a
                # decision, and leaving reviewed=0 makes it look like an unexplained hidden event.
                cursor.execute(
                    f'UPDATE events SET suppressed = 1, reviewed = 1 WHERE id IN ({placeholders})',
                    tuple(to_suppress)
                )
                conn.commit()
            print(f"\nSuppressed {cursor.rowcount} events.")
        else:
            print("\nRun with --suppress to auto-suppress exact-name duplicates.")
    else:
        print("\nNo exact-name duplicates found.")

    if cross_source_time_dupes or cross_location_strong:
        print("\nCross-source and cross-location pairs need holistic review before merging.")
        print("Follow the workflow in .claude/commands/dedupe-events.md to review and merge each pair.")
        if cross_location_strong:
            print("Cross-location pairs: when merging, keep the row at the MORE SPECIFIC "
                  "location (drop the generic/wrong one) and re-point via merge_pair(keep, delete).")

    cursor.close()
    conn.close()


if __name__ == '__main__':
    main()
