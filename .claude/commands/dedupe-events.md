# Dedupe Events Command

Find and clean up duplicate events in the fomo.nyc database.

## Instructions

You are helping the user identify and remove duplicate events. Run each pattern, show results to the user, and merge confirmed duplicates.

---

## Pattern 1: Exact Name Match (Same Location)

Events with identical names at the same location. Always duplicates.

```sql
SELECT
    e.location_id,
    LOWER(TRIM(e.name)) as norm_name,
    COUNT(DISTINCT e.id) as event_count,
    GROUP_CONCAT(DISTINCT e.id ORDER BY e.id) as event_ids,
    MIN(l.name) as location_name
FROM events e
LEFT JOIN locations l ON e.location_id = l.id
WHERE e.location_id IS NOT NULL
GROUP BY e.location_id, LOWER(TRIM(e.name))
HAVING COUNT(DISTINCT e.id) > 1
ORDER BY event_count DESC
LIMIT 30;
```

**Action**: Always duplicates. Merge occurrences into lowest ID, delete the rest.

---

## Pattern 2: Same Location + Same Time

Events at the same location with overlapping date+time. Very likely duplicates unless different rooms/stages.

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
GROUP BY e1.id, e1.name, e2.id, e2.name, l.name
ORDER BY overlap_count DESC, e1.location_id
LIMIT 50;
```

**Action**: Review manually. Look for:
- **DUPLICATE**: Names share significant words, one is subset of other, or minor formatting differences
- **NOT DUPLICATE**: Completely different events (multi-room venues like 92NY, zoos, museums with concurrent programs)

---

## Pattern 3: Same Name + Overlapping Dates (Different Locations or Sources)

Events with identical names that overlap in time, regardless of location or source.

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
WHERE LOWER(e1.name) NOT IN (
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

---

## Pattern 4: Same Location + Overlapping Dates (Any Names)

Events at same location with overlapping dates, regardless of name similarity. Very permissive - will have false positives but catches edge cases.

```sql
SELECT
    e1.id as id1, e1.name as name1,
    e2.id as id2, e2.name as name2,
    l.name as location,
    COUNT(DISTINCT eo1.start_date) as overlapping_dates
FROM events e1
JOIN events e2 ON e1.location_id = e2.location_id
    AND e1.id < e2.id
    AND LOWER(TRIM(e1.name)) != LOWER(TRIM(e2.name))
JOIN event_occurrences eo1 ON e1.id = eo1.event_id
JOIN event_occurrences eo2 ON e2.id = eo2.event_id AND eo1.start_date = eo2.start_date
LEFT JOIN locations l ON e1.location_id = l.id
WHERE e1.location_id IS NOT NULL
GROUP BY e1.id, e1.name, e2.id, e2.name, l.name
HAVING overlapping_dates >= 2
ORDER BY overlapping_dates DESC
LIMIT 50;
```

**Action**: Review manually. Many false positives expected (different events at same venue on same dates). Look for:
- **DUPLICATE**: Names refer to same event (director prefix, subtitle variations, typos)
- **NOT DUPLICATE**: Genuinely different events at same venue

---

## Cleanup Procedure

For confirmed duplicates:

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

3. **Delete the duplicate**:
```sql
DELETE FROM event_occurrences WHERE event_id = <delete_id>;
DELETE FROM event_urls WHERE event_id = <delete_id>;
DELETE FROM event_tags WHERE event_id = <delete_id>;
DELETE FROM event_sources WHERE event_id = <delete_id>;
DELETE FROM events WHERE id = <delete_id>;
```

4. **Remove duplicate occurrences** (after merging):
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

- Pattern 2 catches 316/4669 (same location, same time, NULL vs non-NULL website_id)
- Pattern 3 catches 10200/2273 (same name, different locations)
- Pattern 4 catches 3344/3345 (similar names, same location)
- 8213 case (director-prefixed name) is hard to catch automatically - requires manual review
- Always merge occurrences/URLs before deleting to preserve data
- Prefer keeping the event with a location over one without
- Prefer keeping the event with website_id over one without
