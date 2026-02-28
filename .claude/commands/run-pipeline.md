---
name: run-pipeline
description: Run the full pipeline, investigate findings, apply fixes, and review events
---

# Run Pipeline Command

Run the full event processing pipeline, investigate any issues, apply fixes, and review flagged events.

## Coverage Area

Our coverage area is the **NYC metro region**, which includes:
- **New York City** (all five boroughs)
- **Long Island** (Nassau and Suffolk counties, including the Hamptons)
- **Westchester County** and **Rockland County**
- **Hudson Valley** (Dutchess, Orange, Ulster, and Putnam counties)
- **Northern New Jersey** (Bergen, Hudson, Essex, Passaic, Union, Middlesex, Monmouth, Ocean counties and nearby)
- **Southern Connecticut** (Fairfield County and nearby)

Events from touring companies performing at venues **outside** this area (e.g., in Europe, the Midwest, the Deep South) should be archived. Events at venues **within** this area should be kept and mapped to locations.

## Step 1: Run the Pipeline

```bash
./venv/bin/python pipeline/main.py
```

This runs the full pipeline: crawl → extract → process → merge → export → upload. It typically takes 30-60 minutes depending on the number of websites due for crawling.

Monitor the output for:
- **Crawl failures** (`ERR_ABORTED`, `Timeout`, `failed`)
- **Archival warnings** (`⚠️ WARNING: N upcoming event(s) archived`)
- **Total counts** (websites crawled, events processed, events archived)

## Step 2: Triage Findings

After the pipeline completes, triage ALL issues from the output.

### 2a: Crawl Failures and Timeouts

For each failed/timed-out website, check recent crawl history:

```sql
SELECT cr.id, cr.crawled_at, cr.status,
       LENGTH(cr.crawled_content) as content_size,
       SUBSTRING(cr.error_message, 1, 100) as error_msg,
       cr.event_count
FROM crawl_results cr
WHERE cr.website_id = {id}
ORDER BY cr.id DESC LIMIT 5;
```

**Quick triage:**

| Pattern | Action |
|---------|--------|
| `ERR_ABORTED` with recent successes | Intermittent — no action needed |
| `Timeout` with partial content saved (large size) | Working as designed — no action needed |
| `ERR_ABORTED` with 4+ consecutive failures | Needs fix |
| `Timeout` with `scan_full_page=1` following subpages | Disable `scan_full_page` |
| `Timeout` with no/tiny content | Needs fix |

For simple, obvious fixes (disabling `scan_full_page`, increasing `max_batches`), apply them directly. For anything requiring deeper investigation (alternative URLs, stealth mode, JS navigation, broken widgets), refer to the `optimize-crawls` command which has comprehensive troubleshooting patterns.

### 2b: Archival Warnings

For websites with multiple upcoming events archived, check whether it's correct:

```sql
SELECT e.id, e.name, e.location_name,
       MIN(eo.start_date) as first_date, MAX(eo.start_date) as last_date
FROM events e
JOIN event_occurrences eo ON e.id = eo.event_id
WHERE e.website_id = {id} AND e.archived = TRUE
  AND eo.start_date >= CURDATE()
GROUP BY e.id ORDER BY first_date;
```

**Legitimate archival** (no action): events removed from website, multi-location site showing other cities, festival replacing regular programming, event name changed.

**Problematic archival** (needs fix): events still on website but crawler missed them (content truncation from low `max_batches`), or crawl failure caused blanket archival.

## Step 3: Apply Quick Fixes

Apply straightforward database fixes identified during triage:

```sql
-- Disable scan_full_page (timeout from subpage crawling)
UPDATE websites SET scan_full_page = 0 WHERE id = {id};

-- Increase max_batches (content truncation — each chunk is ~30K chars, default is 3)
UPDATE websites SET max_batches = {n} WHERE id = {id};

-- Increase timeout
UPDATE websites SET crawl_timeout = {seconds} WHERE id = {id};
```

For complex crawl issues (stealth mode, alternative URLs, JS navigation, broken widgets, venue closures), use the `optimize-crawls` command instead.

## Step 4: Hide Uninteresting Events

Run the review candidate finder to check for non-events:

```bash
./venv/bin/python scripts/find_review_candidates.py --count
```

If there are candidates, fetch them:

```bash
./venv/bin/python scripts/find_review_candidates.py --limit 50
```

Review each candidate against the suppress/keep criteria in the `hide-uninteresting-events` command. Then apply decisions:

```sql
-- Suppress non-events
UPDATE events SET reviewed = 1, suppressed = 1 WHERE id IN (...);

-- Keep real events
UPDATE events SET reviewed = 1, suppressed = 0 WHERE id IN (...);
```

Repeat until `--count` shows 0.

### Suppress/Keep Quick Reference

**Suppress:** Generic food/drink (no performers), closures, private/invite-only, religious services, closed auditions, school schedule notices, TBA/TBD placeholders, service office hours, store promos, cancelled notices, virtual events unrelated to the NYC metro area.

**Keep:** Named performers, workshops/classes, community gatherings, themed events, open mics, volunteer ops, museum member events, civic meetings, support groups, open rehearsals, student shows at public venues, sold-out events.

**Watch for false positives:** Movie titles matching patterns ("A Private Life", "Snow Day", "Maintenance Artist"), venue series names ("Office Hours" at a music venue), musical residencies (not school residencies), comedy audition shows (public entertainment).

## Step 5: Fix Imprecise Location Mappings

Find active events mapped to generic Borough, Neighborhood, or City locations that could be mapped more precisely:

```sql
SELECT e.id, e.name, e.location_name, e.sublocation, l.name as mapped_to,
       w.name as website_name, e.description
FROM events e
JOIN locations l ON e.location_id = l.id
JOIN location_tags lt ON l.id = lt.location_id
JOIN tags t ON lt.tag_id = t.id
LEFT JOIN websites w ON e.website_id = w.id
WHERE t.name IN ('Borough', 'Neighborhood', 'City')
  AND e.archived = FALSE AND e.suppressed = FALSE
ORDER BY l.name, e.location_name;
```

Events fall into two categories:

### Events with specific venue names (fixable)

These have a recognizable venue in `location_name` but the processor couldn't match it to a location in our database (e.g., "Palladium Times Square" → Times Square, "Staten Island Children's Museum" → Staten Island).

For each one:
1. Check if the venue already exists in our `locations` table under a different name
2. If it exists, add an alternate name so it matches in future runs:
   ```sql
   INSERT INTO location_alternate_names (location_id, alternate_name) VALUES ({id}, '{name}');
   ```
3. If it doesn't exist, create the location with all required fields. Research the venue first (web search) to write an accurate description:
   ```sql
   INSERT INTO locations (name, short_name, address, lat, lng, emoji, description)
   VALUES ('{name}', '{short_name}', '{address}', {lat}, {lng}, '{emoji}', '{description}');
   ```
   - **emoji**: See `add-locations` command for the emoji guide (🎭 theatre, 🍺 bar, 🏛️ museum, etc.)
   - **description**: 1-2 concise sentences about what the venue is and what events it hosts. Research the venue to write an accurate description.
   - **tags**: Add borough/county, neighborhood/town, and venue type tags via `location_tags`. Create new tags for towns outside NYC as needed.
   - Also add alternate names for any variant spellings the extractor might produce
4. Then update the event: `UPDATE events SET location_id = {location_id} WHERE id = {event_id}`
5. While researching, check if the venue has permanently closed — if so, archive the event instead of remapping it

### Events with only generic/private locations (sometimes fixable)

These have location names like "Private Residence", "Bushwick", "Online via Zoom", "TBA - Brooklyn". Common sources:
- **Groupmuse** — private residence concerts, address revealed after RSVP
- **Walking tours** (Bowery Boys, Turnstile Tours) — neighborhood-level meeting points
- **CocuSocial** — cooking classes at rotating venues
- **DSA** — branch meetings at undisclosed locations (Action Network hides addresses behind RSVP), but some events reference known venues (e.g., "Cortelyou Greenmarket Tabling" → Cortelyou Greenmarket, "Chinatown Office Loop" → NYC-DSA Office)
- **NYC Events** (nyc.gov) — sometimes extracts generic "Lower Manhattan" when the crawl data has a specific address. Check the crawled content for the actual location.
- **Partiful** — private parties

For most, the source website genuinely doesn't provide a specific venue — skip them. But scan event names and descriptions for recognizable venue names that exist in our database (greenmarkets, parks, offices, etc.).

## Step 6: Fix Unmapped Events

Find active events with no location at all (`location_id IS NULL`) that have a specific venue name:

```sql
SELECT e.id, e.name, e.location_name, w.name as website_name
FROM events e
LEFT JOIN websites w ON e.website_id = w.id
WHERE e.location_id IS NULL AND e.archived = FALSE AND e.suppressed = FALSE
  AND e.location_name IS NOT NULL AND e.location_name != ''
  AND e.location_name NOT IN ('Online', 'Virtual', 'Zoom', 'TBA', 'TBD',
    'New York', 'New York City', 'NYC', 'Brooklyn', 'Manhattan', 'Queens', 'Bronx')
  AND e.location_name NOT LIKE '%online%' AND e.location_name NOT LIKE '%virtual%'
  AND e.location_name NOT LIKE '%TBA%' AND e.location_name NOT LIKE '%Various%'
ORDER BY w.name, e.location_name;
```

For each event, determine:

### 1. Is the venue within our coverage area?
- If **outside** coverage area (touring company at a distant venue) → archive the event
- Many websites list tours alongside local shows (e.g., Imani Winds, The Knights, JACK Quartet, Literature to Life). Archive events at venues in Europe, the Midwest, etc.

### 2. Can the venue be matched to an existing location?
- Batch-check venue names against `locations.name`, `locations.short_name`, and `location_alternate_names.alternate_name`
- Watch for spelling variants (e.g., "Peoples Improv Theatre" vs "The Peoples Improv Theater (PIT)")

### 3. Should a new location be created?
- In general, yes; if an event doesn't have a mapped location, then it will never be shown to users. If the event is taking place at a location within the NYC metro area, we should ensure that the location exists in our database.

### Common patterns for NULL-location events
- **Online/Virtual/Zoom** (~40%) — no location to map; skip
- **Generic city/borough** (~20%) — no specific venue; skip
- **TBA/TBD** (~10%) — venue not yet announced; skip
- **Touring companies** — archive events outside coverage area, create locations for in-area venues
- **Specific NYC venues** — create locations and remap
- **Long Island/Westchester/Hudson Valley/NJ/CT venues** — create locations with appropriate regional tags

## Step 7: Re-export and Upload

After applying fixes and reviewing events, re-export the data so changes are reflected on the live site:

```python
import sys
sys.path.insert(0, 'pipeline')
from db import create_connection
from exporter import export_events, classify_event_sections

conn = create_connection()
cursor = conn.cursor(buffered=True)

classify_event_sections(cursor, conn)
export_events(cursor)

cursor.close()
conn.close()
```

Then upload:

```bash
python scripts/upload_public_html.py
```

## Summary Format

After completing all steps, provide a summary:

```
=== PIPELINE RUN SUMMARY ===

Pipeline Results:
- Websites crawled: N
- Events processed: N (X new, Y merged)
- Events archived: N
- Upcoming events archived: N (with details)

Issues Found & Fixed:
- [Website]: [Issue] → [Fix applied]
- ...

Event Review:
- Candidates found: N
- Suppressed: N (list categories)
- Kept: N

Location Fixes (generic locations):
- Events on generic locations: N
- Remapped to specific venues: N
- Unfixable (private/TBA/neighborhood): N

Unmapped Events (NULL location):
- Total unmapped: N
- Archived (out of area): N
- Matched to existing locations: N
- New locations created: N
- Remaining (online/TBA/generic/private): N

Data re-exported and uploaded: ✓/✗
```
