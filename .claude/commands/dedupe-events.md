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
- **Summary** of similar-name pairs (use `--review` to see them)

### Auto-suppress exact-name duplicates

If exact-name duplicates are found, suppress them:

```bash
./venv/bin/python scripts/find_duplicate_events.py --suppress
```

This suppresses the higher-ID event from each exact-name pair.

### Review shared URL duplicates

Shared URL pairs are always shown (no flag needed). These are events at the same location with overlapping dates that share a specific event URL (filtered to URLs with 2+ path segments, shared by at most 3 events — excludes venue homepages).

Review each pair. Common false positives:
- **Lecture/workshop series**: Different installments sharing the series URL (e.g., "Winter Lecture: Speaker A" vs "Winter Lecture: Speaker B")
- **Community board meetings**: Different committees sharing the board calendar URL
- **Late show variants**: Same show at different times sharing the event page

For confirmed duplicates, suppress the higher ID:

```sql
UPDATE events SET suppressed = 1 WHERE id IN (...);
```

### Review similar-name pairs

```bash
./venv/bin/python scripts/find_duplicate_events.py --review
```

Review each similar-name pair manually. The script uses the merger's `are_names_similar()` logic, which catches accent variations, suffix variations, word subsets, substring matches, and presenter-prefix patterns. But it can still produce false positives (e.g., "Festival Night 1" vs "Festival Night 2", "Letterpress I" vs "Letterpress II").

For confirmed duplicates, suppress the higher ID:

```sql
UPDATE events SET suppressed = 1 WHERE id IN (...);
```

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
UPDATE events SET suppressed = 1 WHERE id IN (...);
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
UPDATE events SET suppressed = 1 WHERE id = <delete_id>;
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
