# Dedupe Events Command

Find and clean up duplicate events in the fomo.nyc database.

## Instructions

You are helping the user identify and remove duplicate events. Start with the automated script, then use manual SQL patterns for deeper investigation.

---

## Step 1: Automated Duplicate Detection

Run the duplicate finder script, which checks for active event pairs at the same location with overlapping dates (including date range overlaps for exhibitions/long-running events):

```bash
./venv/bin/python scripts/find_duplicate_events.py
```

This shows:
- **Exact-name duplicates**: Identical normalized names — safe to auto-suppress
- **Shared URL duplicates**: Different names but same event URL — review needed (catches re-extractions where the event name changed between crawls, e.g., "Wine Between the Lines: Fermentation is Magic" vs "Wine Between the Lines: A Deep Dive on Natural Wine" sharing the same Eventbrite URL)
- **Cross-source same date+time duplicates**: Same location, same date AND start_time, but from **different websites** — high signal for cross-source dupes where names diverge completely (e.g. organizer's Luma title vs venue's site title for the same event). Review needed.
- **Cross-location shared-URL duplicates**: two events that share a specific event URL but sit at **different `location_id`s** — the "location scatter" bug, where one real event became two rows at different venues and renders twice on the map (e.g. a SummerStage concert listed once at "Central Park SummerStage" (loc 3521) and once at generic "Central Park" (loc 192)). The same-location tiers are structurally blind to this. **Default shows only the high-confidence subset (same name AND same date+time); `--review` adds the weaker name-or-time-only pairs.** Review needed — NEVER auto-suppressed.
- **Summary** of same-source same-time pairs and similar-name pairs (use `--review` to see them)

**Cross-location tier — merge convention & known false positives.** When a cross-location pair IS a dup, merge toward the row at the **more specific** location and drop the generic/wrong one: `merge_pair(cursor, keep=<specific-loc row>, delete=<generic-loc row>)` (e.g. keep the SummerStage row, delete the generic Central Park row). Recurring offenders that are **NOT** dups (dismiss them with `record_dismissal`, they won't resurface):
- **Same film at different cinema branches** sharing a film-info URL — "Obsession (2026)" at Regal Times Square vs Regal New Roc, "Flow" at Alamo Brooklyn vs Staten Island. The film genuinely plays at both; the shared URL is a film page, not a showtime.
- **A recurring series that visits multiple venues** — "Queens Jazz Trail Concert: …" at Kupferberg vs a different park, a wellness-walk series at two adjacent park entrances.
- **Umbrella vs specific** — "BRIC Celebrate Brooklyn!" (the festival) vs "Benefit Show: Royel Otis" (one night of it) share a URL but are an umbrella/child relationship, not a dup — handle per the umbrella rules, don't blind-merge.

### Auto-suppress exact-name duplicates

Exact-name pairs are safe to auto-suppress without holistic review:

```bash
./venv/bin/python scripts/find_duplicate_events.py --suppress
```

This suppresses the higher-ID event from each exact-name pair. (The kept event preserves foreign-key references; if the higher ID had richer fields, fix manually after — exact-name pairs almost always have identical fields.)

### Holistic review for ALL review-needed tiers

The remaining tiers — **shared URL**, **cross-source same date+time**, **cross-location shared-URL**, and **similar-name** — must each be reviewed holistically by Claude. Do not skip any tier and do not use length-based heuristics. The mechanics are identical for all: fetch fields, decide, apply (merge OR record dismissal).

Pairs that have been reviewed and dismissed in a prior run are stored in `dedupe_dismissed_pairs` and automatically filtered out of these tiers, so the same false positives don't keep resurfacing. Every pair you review and decide is NOT a duplicate must be recorded so the next run skips it.

Run the script first (without `--review`) to get the cross-source and shared URL lists, then again with `--review` to also see similar-name pairs:

```bash
./venv/bin/python scripts/find_duplicate_events.py --review
```

#### Step A: Fetch full data for ALL review-needed pairs in one batch

To minimize round-trips, fetch field data for every pair across all three tiers in a single Python call. Pass the full pair list (collected from the script's printed output):

```python
import sys; sys.path.insert(0, 'pipeline')
from db import create_connection
conn = create_connection()
cur = conn.cursor(dictionary=True)

# Paste in pairs from each tier:
shared_url_pairs = [(<id1>, <id2>), ...]
cross_source_pairs = [(<id1>, <id2>), ...]
similar_name_pairs = [(<id1>, <id2>), ...]

for label, pairs in [('SHARED-URL', shared_url_pairs),
                     ('CROSS-SOURCE', cross_source_pairs),
                     ('SIMILAR-NAME', similar_name_pairs)]:
    for id1, id2 in pairs:
        print(f'\n=== [{label}] {id1} vs {id2} ===')
        for eid in [id1, id2]:
            cur.execute('''
                SELECT e.id, e.name, e.short_name, e.description, e.emoji, e.sublocation,
                       l.name AS location, w.name AS website
                FROM events e
                JOIN locations l ON e.location_id = l.id
                JOIN websites w ON e.website_id = w.id
                WHERE e.id = %s
            ''', (eid,))
            r = cur.fetchone()
            print(f"  [{r['id']}] '{r['name']}' [{r['website']}] sub={r['sublocation']!r} emoji={r['emoji']!r}")
            print(f"    desc: {(r['description'] or '')[:300]}")
            cur.execute('SELECT url FROM event_urls WHERE event_id = %s', (eid,))
            print(f"    urls: {[r2['url'] for r2 in cur.fetchall()]}")
            cur.execute('SELECT t.name FROM event_tags et JOIN tags t ON et.tag_id=t.id WHERE et.event_id=%s', (eid,))
            print(f"    tags: {[r2['name'] for r2 in cur.fetchall()]}")
            cur.execute('SELECT start_date, start_time, end_time FROM event_occurrences WHERE event_id=%s ORDER BY start_date LIMIT 5', (eid,))
            print(f"    occs: {[dict(r2) for r2 in cur.fetchall()]}")
conn.close()
```

#### Step B: Holistically review each pair

Read both events' name, description, emoji, sublocation, tags, URLs, occurrences, and source website together. For each pair, decide:

- **Are they the same event?** Look for:
  - Description content that describes the same thing (even if titled differently)
  - URLs pointing at the same Eventbrite/Luma/ticket page
  - Tags that overlap meaningfully
  - Occurrence date/time alignment

- **Common false-positive patterns to recognize**:
  - **Shared URL**: lecture/workshop series sharing a series URL (different installments); community-board meetings sharing the board calendar URL; multi-show events at the same venue sharing a "what's on" page; numbered nights (Night 1/2/3); lettered editions (I/II/III)
  - **Cross-source same-time**: concurrent walking tours at the Municipal Art Society; simultaneous museum exhibitions sharing daily hours; multi-stage theaters (Carnegie, BAM); multi-room cultural centers (JCC, 92NY); huge parks where two activities run at different physical spots
  - **Similar-name**: numbered series, men's vs women's sports, early vs late sets, same title at different theaters

- **If yes (it IS a duplicate), what are the best merged field values?**
  - **name**: pick the clearer, more specific title; or synthesize a better one. Don't just keep the lower-ID's. Avoid generic venue names if a more specific event title is available.
  - **description**: pick the more accurate/informative one. Don't pick a longer description if it's actually about a different event.
  - **emoji**: the more relevant one for the event type
  - **sublocation**: the more specific one (e.g. "Ground Floor", "Studio B"); null if neither helps
  - **short_name**: prefer non-null
  - tags, URLs, occurrences, sources: always merged as a union — handled by `merge_pair`

#### Step C: Apply the decisions in a batch

For each reviewed pair you must do exactly ONE of these:
- **Merge** — call `apply_field_overrides` (only with the scalar fields you want to change) followed by `merge_pair`.
- **Dismiss** — call `record_dismissal` so the pair won't be re-flagged in the next run.

Every pair must be one or the other. Don't silently skip pairs.

Wrap the whole apply batch in the cross-session **write lock** (`pipeline/dblock.py`) so a concurrent session can't mutate the same tables at once — this exact workflow has collided with a parallel dedupe before. See CLAUDE.md → Concurrent Sessions.

```python
import sys; sys.path.insert(0, 'pipeline')
sys.path.insert(0, 'scripts')
from db import create_connection
from dblock import write_lock
from find_duplicate_events import apply_field_overrides, merge_pair, record_dismissal
conn = create_connection()
cur = conn.cursor()

with write_lock(conn):   # blocks until no other session is writing; raises after 600s
    # Confirmed duplicate — apply chosen field values then merge collections + suppress:
    apply_field_overrides(cur, <keep_id>,
        name='<chosen name or omit>',
        description='<chosen description or omit>',
        emoji='<chosen emoji or omit>',
        sublocation='<chosen sublocation or omit>',
    )
    merge_pair(cur, <keep_id>, <delete_id>)

    # NOT a duplicate — record dismissal with a short reason
    # (the reason is stored alongside the pair so future maintainers know why):
    record_dismissal(cur, <id1>, <id2>, "concise reason — e.g. 'multi-room venue: different programs'")

    # ...repeat for each pair...

    conn.commit()
conn.close()
```

For pairs that are NOT duplicates but where one event clearly has corrupted data (e.g. URLs, tags, or descriptions belonging to a different event mixed in), still record the dismissal AND flag the corrupted event in your reply so the user can decide whether to clean it up.

#### Step D: After all pairs are processed, re-export

```python
import sys; sys.path.insert(0, 'pipeline')
from db import create_connection
import exporter
conn = create_connection()
exporter.export_events(conn.cursor())
conn.close()
```

Then ask the user whether to upload via `python scripts/upload_public_html.py`.

### Same-source same date+time pairs

Use `--review` to see these. Same-website same-time pairs are mostly noise from multi-tour or multi-room venues (Municipal Art Society's concurrent walking tours, museums with parallel programs, theaters with multiple stages). Skim for any that share descriptions or are clearly re-extractions and run the holistic-review workflow on those; ignore the rest.

---

## Step 2: Manual SQL Patterns (Deeper Investigation)

Use these patterns to catch duplicates the script might miss.

### Pattern A: Same Name + Overlapping Dates (Different Locations or Sources)

Events with identical names that overlap in time, regardless of location. Catches cross-source duplicates where one event has a location and the other doesn't.

```sql
SELECT
    e1.id as id1, l1.name as loc1, w1.name as web1,
    e2.id as id2, l2.name as loc2, w2.name as web2,
    e1.name,
    COUNT(DISTINCT eo1.start_date) as overlapping_dates
FROM events e1
JOIN events e2 ON LOWER(TRIM(e1.name)) = LOWER(TRIM(e2.name))
    AND e1.id < e2.id
JOIN event_occurrences eo1 ON e1.id = eo1.event_id
JOIN event_occurrences eo2 ON e2.id = eo2.event_id AND eo1.start_date = eo2.start_date
LEFT JOIN locations l1 ON e1.location_id = l1.id
LEFT JOIN locations l2 ON e2.location_id = l2.id
LEFT JOIN websites w1 ON e1.website_id = w1.id
LEFT JOIN websites w2 ON e2.website_id = w2.id
WHERE e1.archived = 0 AND e1.suppressed = 0
  AND e2.archived = 0 AND e2.suppressed = 0
  AND LOWER(e1.name) NOT IN (
    'open hours', 'trivia night', 'open mic', 'open mic night',
    'karaoke', 'karaoke night', 'bingo', 'bingo night', 'happy hour',
    'comedy night', 'jazz night', 'live music', 'dj night', 'market',
    'free', 'free admission', 'closed', 'holiday hours'
)
AND LENGTH(e1.name) > 10
GROUP BY e1.id, l1.name, w1.name, e2.id, l2.name, w2.name, e1.name
HAVING overlapping_dates >= 1
ORDER BY overlapping_dates DESC
LIMIT 50;
```

**Action**: Review each case:
- **DUPLICATE**: Same/related locations, or one missing location
- **NOT DUPLICATE**: Same movie at different theaters, same touring show at different venues

### Pattern B: Same Location + Same Time (Different Names)

Events at the same location with matching date+time but different names. Catches renaming/reformatting cases.

```sql
SELECT
    e1.id as id1, e1.name as name1,
    e2.id as id2, e2.name as name2,
    l.name as location,
    COUNT(*) as overlap_count
FROM events e1
JOIN events e2 ON e1.location_id = e2.location_id
    AND e1.id < e2.id
    AND LOWER(TRIM(e1.name)) != LOWER(TRIM(e2.name))
JOIN event_occurrences eo1 ON e1.id = eo1.event_id
JOIN event_occurrences eo2 ON e2.id = eo2.event_id
    AND eo1.start_date = eo2.start_date
    AND COALESCE(eo1.start_time, '') = COALESCE(eo2.start_time, '')
    AND eo1.start_time IS NOT NULL
LEFT JOIN locations l ON e1.location_id = l.id
WHERE e1.location_id IS NOT NULL
  AND e1.archived = 0 AND e1.suppressed = 0
  AND e2.archived = 0 AND e2.suppressed = 0
GROUP BY e1.id, e1.name, e2.id, e2.name, l.name
ORDER BY overlap_count DESC, e1.location_id
LIMIT 50;
```

**Action**: Review manually. Look for:
- **DUPLICATE**: Names share significant words, one is subset of other, or minor formatting differences
- **NOT DUPLICATE**: Completely different events (multi-room venues like 92NY, zoos, museums with concurrent programs)

---

## Cleanup Procedure

For simple duplicates (same data, just suppress the duplicate):

```sql
UPDATE events SET suppressed = 1, reviewed = 1 WHERE id IN (...);
```

For duplicates where you need to merge data (different occurrences, URLs, or tags):

1. **Merge occurrences** into the event to keep (usually lowest ID or one with location):
```sql
INSERT IGNORE INTO event_occurrences (event_id, start_date, start_time, end_date, end_time)
SELECT <keep_id>, start_date, start_time, end_date, end_time
FROM event_occurrences WHERE event_id = <delete_id>;
```

2. **Merge related data**:
```sql
INSERT IGNORE INTO event_urls (event_id, url) SELECT <keep_id>, url FROM event_urls WHERE event_id = <delete_id>;
INSERT IGNORE INTO event_tags (event_id, tag_id) SELECT <keep_id>, tag_id FROM event_tags WHERE event_id = <delete_id>;
INSERT IGNORE INTO event_sources (event_id, crawl_event_id) SELECT <keep_id>, crawl_event_id FROM event_sources WHERE event_id = <delete_id>;
```

3. **Suppress the duplicate**:
```sql
UPDATE events SET suppressed = 1, reviewed = 1 WHERE id = <delete_id>;
```

4. **Remove duplicate occurrences** on the kept event (after merging):
```sql
DELETE o1 FROM event_occurrences o1
INNER JOIN event_occurrences o2
ON o1.event_id = o2.event_id
   AND o1.start_date = o2.start_date
   AND COALESCE(o1.start_time, '') = COALESCE(o2.start_time, '')
   AND o1.id > o2.id;
```

---

## Notes

- The script (`find_duplicate_events.py`) only checks events at the **same location** — use Pattern A for cross-location/cross-source duplicates
- Shared URL detection filters out generic venue URLs (requires 2+ path segments, shared by ≤3 events) — venue homepages shared by many events are excluded
- Prefer suppressing over deleting — suppressed events won't appear in the export but the data is preserved
- Prefer keeping the event with a location over one without
- Prefer keeping the event with a website_id over one without
- False positive patterns to watch for: numbered series (Night 1/2/3), lettered editions (I/II/III), different showtimes, men's vs women's sports, early vs late sets
