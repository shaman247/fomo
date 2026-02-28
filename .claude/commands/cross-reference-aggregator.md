---
name: cross-reference-aggregator
description: Cross-reference events from an aggregator website against our database to find coverage gaps
args: <url>
---

# Cross-Reference Aggregator

Cross-reference events from an aggregator website against our database to find coverage gaps and fix crawl issues.

## Overview

Aggregator sites list events from many venues. By comparing their listings against our database, we can:
- Find venues we're missing entirely
- Find events we should have but don't (crawl gaps)
- Diagnose and fix crawl issues (wrong URLs, stale crawls, missing pages)

## Instructions

### Phase 1: Load & Extract Events

Navigate to the aggregator URL and extract all events.

**Step 1: Load the page**

Use Playwright to navigate to the URL:
```
browser_navigate → <url>
```

**Step 2: Inspect the page structure**

Use `browser_snapshot` to understand the page layout. Look for:
- Event containers (repeated elements with title, date, venue)
- Pagination controls (numbered pages, "load more" buttons, infinite scroll)
- Any filters that need to be set (date range, category)

**Step 3: Handle pagination**

Before extracting, ensure ALL events are accessible:
- **Client-side pagination** (all events in DOM, hidden pages): Extract directly — all data is present
- **"Load more" / infinite scroll**: Click the button repeatedly until all events are loaded
- **Server-side pagination** (separate page loads): Use `browser_run_code` to navigate all pages and collect events (see template below)
- **Date-range filters**: Ensure the date range covers upcoming events (not just today)

**Step 4: Extract events**

Use `browser_evaluate` to extract events from a single page. Adapt selectors to the specific site:

```javascript
// Template — adapt selectors per site
() => {
    const events = [];
    document.querySelectorAll('<event-container-selector>').forEach(el => {
        const title = el.querySelector('<title-selector>')?.textContent?.trim();
        const venue = el.querySelector('<venue-selector>')?.textContent?.trim();
        const date = el.querySelector('<date-selector>')?.textContent?.trim();
        const time = el.querySelector('<time-selector>')?.textContent?.trim();
        if (title) events.push({ title, venue, date, time });
    });
    return events;
}
```

**For server-side pagination**, use `browser_run_code` to iterate all pages:

```javascript
// Template — adapt URL pattern and selectors per site
async (page) => {
    const allEvents = [];
    const baseUrl = '<base_url>';   // e.g., 'https://example.com/events'
    const pageParam = '<param>';     // e.g., '?page=' or '?tribe_paged='
    const totalPages = <N>;          // Determine from pagination controls on first page

    for (let p = 1; p <= totalPages; p++) {
        const url = p === 1 ? baseUrl : `${baseUrl}${pageParam}${p}`;
        await page.goto(url, { waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(1000);

        const pageEvents = await page.evaluate(() => {
            // Same extraction logic as Step 4
            const events = [];
            document.querySelectorAll('<selector>').forEach(el => {
                // ... extract fields
                events.push({ title, venue, date, time });
            });
            return events;
        });
        allEvents.push(...pageEvents);
    }
    return allEvents;
}
```

**Important**: `browser_run_code` returns data directly — no need for `require('fs')` (not available in browser context). The returned array can be used directly in Python.

**Step 5: Normalize dates**

Aggregator date formats vary widely ("February 28, 2026", "Sat Feb 28", "2/28/26"). Normalize all dates to `YYYY-MM-DD` format for database comparison. Use Python after extraction:

```python
from datetime import datetime
import re

def parse_date(date_str):
    """Try common date formats used by aggregator sites."""
    for fmt in ['%Y-%m-%d', '%B %d, %Y', '%b %d, %Y', '%m/%d/%Y', '%m/%d/%y']:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return date_str  # Return as-is if unparseable
```

**Step 6: Save and report**

Save to file for reuse:
```python
import json
events = <extracted_events>
with open('/tmp/aggregator_events.json', 'w') as f:
    json.dump(events, f, indent=2)
print(f"Saved {len(events)} events")
```

Report: total events extracted, unique venues found.

### Phase 2: Venue Coverage Check

Check which aggregator venues exist in our database.

**Step 1: Get unique venue names**

```python
import json
events = json.load(open('/tmp/aggregator_events.json'))
venues = sorted(set(e.get('venue', '') for e in events if e.get('venue')))
print(f"{len(venues)} unique venues")
for v in venues:
    print(f"  - {v}")
```

**Step 2: Batch-check against locations**

Build a single query with all venue names. Use distinctive substrings for LIKE matching (avoid common words like "The", "New York", "NYC"):

```sql
SELECT id, name, address FROM locations WHERE
  name LIKE '%Venue A%' OR
  name LIKE '%Venue B%' OR
  name LIKE '%Venue C%'
ORDER BY name;
```

Also check alternate names:
```sql
SELECT l.id, l.name, lan.alternate_name
FROM locations l
JOIN location_alternate_names lan ON l.id = lan.location_id
WHERE
  lan.alternate_name LIKE '%Venue A%' OR
  lan.alternate_name LIKE '%Venue B%'
ORDER BY l.name;
```

**IMPORTANT: Verify matches manually.** LIKE matching can return wrong venues (e.g., `%Baby%` matches "Baby Grand" when you want "Baby's All Right"). When a LIKE query returns multiple results, pick the correct one. When building the venue_to_location mapping, use the exact location_id — don't rely on automated LIKE matching in the cross-reference script.

**Step 2.5: Deduplicate venue aliases**

Aggregators often list the same venue under multiple names (e.g., "Baby's All Right", "Baby's All Right – Brooklyn", "Baby's All Right Brooklyn"). Before proceeding:
1. Group obvious aliases (same venue, different suffixes/formatting)
2. Map ALL aliases to the same location_id in the venue_to_location dict
3. Skip generic/non-venue entries (street addresses without venue names, library branches, etc.)

Common alias patterns:
- Venue name with/without borough suffix: "Brooklyn Bowl" vs "Brooklyn Bowl – NY" vs "Brooklyn Bowl: Brooklyn"
- Venue name with/without "The": "Bell House" vs "The Bell House"
- Abbreviations: "BAM" vs "Brooklyn Academy of Music"
- Formatting differences: "ShapeShifter Lab" vs "ShapeShifter Plus" (same venue, different programming)

**Step 3: Check which matched locations have active crawl URLs**

```sql
SELECT l.id, l.name, w.id as website_id, w.name as website_name,
       wu.url as crawl_url, w.crawl_frequency
FROM locations l
JOIN website_locations wl ON l.id = wl.location_id
JOIN websites w ON wl.website_id = w.id
LEFT JOIN website_urls wu ON w.id = wu.website_id
WHERE l.id IN (<matched_location_ids>)
  AND w.disabled = 0
ORDER BY l.name;
```

**Step 4: Report coverage**

Categorize venues into:
- **Crawled**: Location exists AND has active crawl URL(s) — we should have their events
- **Uncrawled**: Location exists but no crawl URL — informational only
- **Missing**: Not in our database at all

```
Venue Coverage:
  XX/YY venues matched (ZZ with active crawls)
  AA venues not in database
```

### Phase 3: Event Cross-Reference

For events at venues we crawl, check if we have them in our database.

Write a Python script that connects to the database and checks each event.

**Important**: Deduplicate events before checking. Aggregators often list the same event multiple times (different dates for recurring events, or duplicate listings). Deduplicate by (title, venue, date) tuple so each unique event is only checked once.

Also map ALL venue aliases to the same location_id. The `venue_to_location` dict should include every name variant from the aggregator.

```python
import json, sys
sys.path.insert(0, 'pipeline')
from db import create_connection

conn = create_connection()
cursor = conn.cursor(dictionary=True)

events = json.load(open('/tmp/aggregator_events.json'))

# Map ALL aggregator venue name variants → location IDs (from Phase 2)
# Include aliases! e.g., both "Brooklyn Bowl" and "Brooklyn Bowl – NY" → same ID
venue_to_location = {
    'Aggregator Venue Name': 123,  # location_id
    'Venue Name Variant': 123,     # same location, different aggregator name
    # ... fill in from Phase 2 matches
}

# Also track which locations have active crawl URLs (from Phase 2, Step 3)
crawled_location_ids = {123, 456}  # location IDs that have active crawl URLs

# Deduplicate by (title, venue, date)
seen = set()
unique_events = []
for event in events:
    key = (event.get('title', ''), event.get('venue', ''), event.get('date', ''))
    if key not in seen:
        seen.add(key)
        unique_events.append(event)

found = []
missing = []
skipped = []

for event in unique_events:
    venue = event.get('venue', '')
    loc_id = venue_to_location.get(venue)

    if not loc_id:
        skipped.append(event)
        continue

    title = event['title']
    date = event.get('date', '')
    # Fuzzy match: check if any event at this location has a similar name
    # Use the first significant word(s) from the title for matching
    # Avoid matching on generic words like "The", "A", "Live", "DJ"
    search_words = title.split(":")[0].split(" - ")[0].strip()[:30]
    cursor.execute('''
        SELECT e.id, e.name, eo.start_date
        FROM events e
        JOIN event_occurrences eo ON e.id = eo.event_id
        WHERE e.location_id = %s
          AND e.archived = 0
          AND eo.start_date = %s
          AND (e.name LIKE %s OR e.name LIKE %s)
        LIMIT 1
    ''', (loc_id, date, f'%{search_words}%', f'%{title[:20]}%'))

    result = cursor.fetchone()
    if result:
        found.append({**event, 'db_id': result['id'], 'db_name': result['name']})
    else:
        missing.append(event)

print(f"Found: {len(found)}, Missing: {len(missing)}, Skipped (no venue match): {len(skipped)}")

# Show missing events grouped by venue, separated by crawled vs uncrawled
from collections import defaultdict
crawled_missing = defaultdict(list)
uncrawled_missing = defaultdict(list)
for e in missing:
    venue = e.get('venue', 'Unknown')
    loc_id = venue_to_location.get(venue)
    bucket = crawled_missing if loc_id in crawled_location_ids else uncrawled_missing
    bucket[venue].append(e['title'])

print("\nMissing events at CRAWLED venues (actionable):")
for venue, titles in sorted(crawled_missing.items()):
    print(f"\n  {venue} ({len(titles)} missing):")
    for t in titles[:5]:
        print(f"    - {t}")
    if len(titles) > 5:
        print(f"    ... and {len(titles) - 5} more")

print(f"\nMissing events at UNCRAWLED venues ({sum(len(t) for t in uncrawled_missing.values())} total):")
for venue, titles in sorted(uncrawled_missing.items()):
    print(f"  {venue}: {len(titles)} events")

conn.close()
```

### Phase 3.5: Verify Missing Events

Before proceeding to gap analysis, **manually verify a sample of "missing" events**. Fuzzy name matching produces many false positives:

- **Name format differences**: "Sofaygo: Mania Tour" vs "SoFaygo", "John Oliver & Seth Meyers" vs "John Oliver, Seth Meyers"
- **Different naming conventions**: Aggregators often abbreviate or rephrase event titles
- **Venue mapping errors**: LIKE matching may have matched the wrong location

For each "missing" event, run a direct search:
```sql
SELECT e.id, e.name, eo.start_date
FROM events e
JOIN event_occurrences eo ON e.id = eo.event_id
WHERE e.name LIKE '%<distinctive_word>%'
  AND e.archived = 0
  AND eo.start_date >= CURDATE()
LIMIT 5;
```

Only proceed with events confirmed as genuinely absent from the database.

### Phase 4: Gap Analysis

Focus on missing events at venues we actively crawl. These are actionable gaps.

**Step 1: Get crawl details for venues with missing events**

```sql
SELECT w.id, w.name, w.crawl_frequency, w.max_batches, w.notes,
       wu.url as crawl_url, wu.js_code,
       cr.crawl_run_id, cr.created_at as last_crawl,
       LENGTH(cr.crawled_content) as content_size,
       (SELECT COUNT(*) FROM events e
        JOIN event_occurrences eo ON e.id = eo.event_id
        WHERE e.website_id = w.id AND e.archived = 0
        AND eo.start_date >= CURDATE()) as upcoming_events
FROM websites w
LEFT JOIN website_urls wu ON w.id = wu.website_id
LEFT JOIN crawl_results cr ON w.id = cr.website_id
  AND cr.id = (SELECT MAX(id) FROM crawl_results WHERE website_id = w.id)
WHERE w.id IN (<website_ids_with_missing_events>)
ORDER BY w.name;
```

**Step 2: Diagnose root causes**

For each website with missing events, check:

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Crawl URL is homepage, not events page | Wrong URL | Update to events/calendar page |
| Last crawl is old (> 2x frequency) | Stale crawl | Re-run pipeline |
| Content size is very small (<1000 chars) | Crawl failure | Check optimize-crawls patterns |
| Event count is 0 or very low | Extraction issue | Check notes, js_code, max_batches |
| Events page has pagination/AJAX | Missing future events | Add js_code for navigation |
| Site uses images/flyers not text | Vision extraction needed | Enable process_images |
| Bowery Presents venue (Brooklyn Steel, MHOW, etc.) | Defaults to "Just Announced" tab, not "All Shows" | Add js_code: click `#all` tab + expand "Show More" buttons |
| Ticketing platform (eventim, dice.fm) | Short event horizon (3-4 weeks) | Not fixable — ticketing platforms only show near-term. Consider supplementary source (Songkick, Bandsintown) |
| Venue events page says "no events" | Events genuinely not listed (aggregator sources from different platform) | Not a crawl issue — skip |
| Site has "Show More" / "Load More" button | Only first page of events visible | Add js_code to click expand button in a loop |

**Bowery Presents venues** (Brooklyn Steel, Music Hall of Williamsburg, Warsaw, Rough Trade, etc.) share the same site template. The default tab is "Just Announced" (random ~10 events). The fix is:
```javascript
// js_code for Bowery Presents venues
const allTab = document.querySelector("#all");
if (allTab) { allTab.click(); await new Promise(r => setTimeout(r, 2000)); }
for (let i = 0; i < 10; i++) {
  const more = document.querySelector(".show-more");
  if (!more) break;
  more.click();
  await new Promise(r => setTimeout(r, 1500));
}
```

**Step 3: Investigate specific gaps**

For the top venues with the most missing events, use WebFetch to check:
- Does the crawl URL actually show events?
- Are there events listed that our crawler should find?
- Is the URL behind JavaScript rendering?
- Are events in a format the AI can parse?

**Step 3.5: Classify gap types**

Not all missing events are fixable. Classify each gap:
- **Fixable**: Wrong crawl URL, missing js_code, stale crawl — apply fix and re-crawl
- **Timing**: Events not yet announced on venue's own site but listed on aggregator (common for concert venues with short horizons) — note but don't action
- **Not our source**: Aggregator pulls from a different platform than what we crawl — not a crawl issue
- **Venue not crawled**: Location exists but has no crawl URL — candidate for Phase 4.5

### Phase 4.5: Uncrawled Venue Analysis

For locations that exist in the database but have no crawl URLs (or no website at all), evaluate whether they're worth adding:

**Step 1: Research each uncrawled venue**

For each uncrawled venue with missing events, check:
- Does the venue have a dedicated events/calendar page?
- Is the page crawlable (text-based events, not just images/flyers)?
- How many events does the aggregator list for this venue?

Use WebFetch to inspect the venue's website. Good candidates have:
- Dedicated `/events`, `/calendar`, or `/shows` page
- Text-based event listings (not PDF flyers or Instagram-only)
- Regular programming (not just occasional rentals)

**Step 2: Add crawl URLs for good candidates**

For venues that already have a website entry but no crawl URL:
```sql
INSERT INTO website_urls (website_id, url, sort_order) VALUES (<website_id>, '<events_url>', 1);
UPDATE websites SET crawl_frequency = 7 WHERE id = <website_id>;
```

For venues with no website entry at all, use `/discover-venues` to add the location and website together.

**Step 3: Skip low-value venues**

Don't add crawl URLs for:
- Venues with no events page (e.g., bars that just have Instagram for event announcements)
- Venues primarily used for private rentals (BKLOFT26, etc.)
- Generic spaces (libraries, churches) unless they have strong programming
- Venues far outside core coverage area

### Phase 5: Fix Issues

For each identified issue, apply the appropriate fix. Common fixes:

**Wrong crawl URL:**
```sql
UPDATE website_urls SET url = '<correct_events_url>' WHERE id = <url_id>;
DELETE FROM crawl_results WHERE website_id = <website_id>;
```

**Missing events page (add crawl URL):**
```sql
INSERT INTO website_urls (website_id, url, sort_order)
VALUES (<website_id>, '<events_url>', <next_sort_order>);
```

**Needs JS interaction (load more, pagination):**
```sql
UPDATE website_urls SET js_code = '<javascript>' WHERE id = <url_id>;
```

**Noisy page (too many irrelevant events):**
```sql
UPDATE websites SET notes = '<guidance for AI extraction>' WHERE id = <website_id>;
```

**Too many events capped by batches:**
```sql
UPDATE websites SET max_batches = <higher_limit> WHERE id = <website_id>;
```

**After fixes, re-run the pipeline:**
```bash
source venv/bin/activate
python pipeline/main.py --ids <comma_separated_website_ids>
```

Verify events are extracted and the missing events from the aggregator now appear.

### Phase 6: Report

Present a summary of findings and actions:

```
=== CROSS-REFERENCE SUMMARY ===

Source: <aggregator_url>
Events extracted: XXX (YYY unique after deduplication)
Unique venues: ZZ

Venue Coverage:
  Matched with crawls: XX
  Matched without crawls: YY
  Not in database: ZZ

Event Coverage (at crawled venues):
  Found in DB: XX / YY (ZZ%)
  Missing (confirmed): XX (actionable)
  Missing (timing/not fixable): XX

Crawl Issues Found & Fixed:
| Website | Issue | Fix | Events After |
|---------|-------|-----|-------------|
| Name | Description | What was done | Count |

Uncrawled Venues — Crawl URLs Added:
| Venue | Website | Events URL | Events After |
|-------|---------|-----------|-------------|
| Name | website_id | URL added | Count |

New Venues Added (via /discover-venues):
  - Venue Name 1 (location_id, with/without crawl)
  - Venue Name 2 (location_id, with/without crawl)

Venues Not in Database (not added — low value):
  - Venue Name (reason: private rentals / no events page / etc.)
```

## Key Principles

1. **Aggregators are for cross-referencing, not crawling** — We use primary sources, not aggregators, as crawl targets
2. **Focus on actionable gaps** — Missing events at venues we already crawl are the highest priority
3. **Batch database checks** — Use single queries with multiple OR conditions, not one query per venue
4. **Adapt to each site** — DOM structure varies; inspect before extracting
5. **Save intermediate data** — Write extracted events to `/tmp/aggregator_events.json` for reuse
6. **Fix root causes** — Update crawl URLs and settings rather than manually adding individual events
7. **Use existing commands** — Invoke `/discover-venues` for adding new locations, `/optimize-crawls` for fixing crawl failures
8. **Deduplicate venue aliases** — Aggregators list the same venue under multiple name variants; map all to one location_id
9. **Verify before declaring missing** — Fuzzy name matching has false negatives; verify a sample of "missing" events with broader DB searches
10. **Not all gaps are fixable** — Concert venues with short ticketing horizons, venues that only announce on social media — note these but don't waste time trying to fix them
