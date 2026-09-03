# Fix Undated Events Command

Investigate and fix events that were extracted without date information.

## Background

When the extraction AI encounters event listings without explicit dates on the page, it returns null occurrences instead of fabricating dates. These events are stored as `crawl_events` with zero rows in `crawl_event_occurrences` — they won't appear on the site until fixed, but they're preserved for investigation.

Common causes:
- **Catalog/archive pages**: Past events, class catalogs, show listings without performance dates
- **Ongoing programs**: "Ongoing" items like apps, virtual tours, permanent exhibits
- **Missing calendar data**: JS widgets that didn't render, Eventbrite embeds not captured

## Step 1: Find Undated Events

```sql
SELECT w.id as website_id, w.name as website_name,
       COUNT(*) as undated_events
FROM crawl_events ce
JOIN crawl_results cr ON ce.crawl_result_id = cr.id
JOIN websites w ON cr.website_id = w.id
LEFT JOIN crawl_event_occurrences ceo ON ce.id = ceo.crawl_event_id
WHERE cr.status = 'processed'
  AND ceo.id IS NULL
  AND ce.created_at >= cr.crawled_at   -- see "stale rows" note below
GROUP BY w.id, w.name
ORDER BY undated_events DESC;
```

This shows websites with undated events, ordered by count.

> **Always keep the `ce.created_at >= cr.crawled_at` predicate.** `crawl_results`
> rows are **UPDATEd in place** on re-crawl (`crawled_content` / `crawled_at` are
> overwritten) while the old `crawl_events` keep pointing at the same row. Without
> the predicate the query counts undated rows from a *pre-fix* extraction against a
> `crawl_result` whose current content no longer contains them — so sites you already
> fixed keep resurfacing as problems. On 2026-07-19 this inflated the count by 35
> rows (184 → 149) and manufactured two entirely phantom "problem" sites (w4867
> Edgemere Farm, w425 Brooklyn CB16) that had already been fixed by earlier js_code.

> **Synthetic source rows are a false positive.** Some monthly backfill scripts
> (`scripts/split_lectures_on_tap_*.py`, `scripts/morgan_to_pipeline.py`) write the
> `events` / `event_occurrences` rows directly and then create a synthetic
> `crawl_results` + one `crawl_event` per event purely as an `event_sources` anchor,
> so archival can fire later. Those crawl_events deliberately have **no**
> `crawl_event_occurrences` and show up here as a large "problem" site (w731 Lectures
> on Tap, 22 rows, on 2026-09-03). Tell them apart by `raw_data IS NULL` — a real
> extraction always fills it — or by checking whether the crawl_event already has an
> `event_sources` row pointing at a live, dated event. Skip them.

## Step 2: Investigate Per Website

For each website with undated events, examine what was extracted:

```sql
SELECT ce.id, ce.name, ce.location_name, ce.url,
       SUBSTRING(ce.description, 1, 100) as description
FROM crawl_events ce
JOIN crawl_results cr ON ce.crawl_result_id = cr.id
WHERE cr.website_id = {website_id}
  AND cr.status = 'processed'
  AND NOT EXISTS (
    SELECT 1 FROM crawl_event_occurrences ceo WHERE ceo.crawl_event_id = ce.id
  )
ORDER BY ce.name;
```

Then check the crawled content to understand why dates were missing:

```sql
SELECT SUBSTRING(cr.crawled_content, 1, 5000)
FROM crawl_results cr
WHERE cr.website_id = {website_id}
ORDER BY cr.id DESC LIMIT 1;
```

## Step 3: Determine the Fix

For each website, determine which category the undated events fall into:

### Category A: Non-event content (suppress via js_code)

The source page has non-event content mixed with real events (catalogs, archives, hotel listings, contest entries, ongoing programs). Fix by adding `js_code` to the `website_urls` entry to trim the non-event content before crawling.

```sql
-- Add js_code to trim non-event content
UPDATE website_urls SET js_code = '...' WHERE id = {url_id};
```

Common js_code patterns:
- **Remove section by heading**: Remove a heading and all following siblings
  ```javascript
  const headings = document.querySelectorAll('h2');
  for (const h of headings) {
    if (h.textContent.includes('Past Events')) {
      let el = h;
      while (el.nextElementSibling) el.nextElementSibling.remove();
      el.remove();
      break;
    }
  }
  ```
- **Remove "Ongoing" items**: Remove list items marked as ongoing
  ```javascript
  document.querySelectorAll('a[href*="/event/"]').forEach(a => {
    if (a.textContent.includes('Ongoing')) {
      const li = a.closest('li');
      if (li) li.remove();
    }
  });
  ```
- **Click filter tab**: Activate an "Upcoming" filter
  ```javascript
  const links = document.querySelectorAll('a');
  for (const a of links) {
    if (a.textContent.trim() === 'Upcoming') { a.click(); break; }
  }
  ```
- **Remove past seasons**: Remove content from past years
  ```javascript
  // Remove nav duplication and past season content
  document.querySelectorAll('nav').forEach(n => n.remove());
  ```

### Category B: Dates exist elsewhere (fix crawl or add notes)

The source page has dates but they're in a format the AI couldn't parse (JS widget, iframe, shadow DOM). Options:
- Add `js_code` to extract shadow DOM content into regular DOM
- Add website `notes` to guide the AI on where to find dates
- Switch to `scan_full_page` to follow links to individual event pages with dates

### Category C: No dates available anywhere (accept or disable)

The source genuinely provides no date information for these listings (show catalogs, venue directories). Options:
- If the website has no useful events at all, disable it: `UPDATE websites SET disabled = 1 WHERE id = {id}`
- If the website has a mix of dated and undated events, the undated ones will be naturally filtered out (no action needed)

**IMPORTANT:** Never instruct the extractor to use approximate dates (first-of-month, mid-month, season-based guesses). The AI must only return dates that are explicitly present on the page. Approximate dates are worse than no dates because they appear authoritative on the map.

### Category D: Notable events worth researching externally

Some undated events are major recurring/annual events worth showing on the map even though the source page doesn't list a specific date (e.g. Atlantic Antic, US Open Tennis, NYC Restaurant Week, Mermaid Parade, Lucille Lortel Awards, BAM Next Wave Festival). For these, research the actual date and venue from the official event website or a reliable secondary source, then insert occurrences directly.

Research workflow:
1. Identify which undated events look notable (well-known recurring events vs niche/ongoing items).
2. Use WebFetch/WebSearch on the event's official site or organizer to find the specific 2026 date and venue.
3. Insert a `crawl_event_occurrences` row linking the researched date to the existing `crawl_event` row. Optionally update `location_name` if the page had it as "Various locations" but you found the actual venue.

Example:
```sql
-- Lucille Lortel Awards on 2026-05-03 at NYU Skirball Center (researched)
INSERT INTO crawl_event_occurrences (crawl_event_id, start_date, sort_order)
VALUES ({event_id}, '2026-05-03', 0);

UPDATE crawl_events
SET location_name = 'NYU Skirball Center'
WHERE id = {event_id};
```

After inserting, the merger will pick these up on the next run (or call `merge_events` directly), and the event will appear on the map with its real date.

## Step 4: Clean Up Old Undated Events

After applying fixes, the old undated crawl_events can be left in place — they'll be ignored by the merger (which requires occurrences). New pipeline runs will produce properly dated events from the fixed crawls.

To verify fixes worked, re-run the pipeline for the fixed websites:

```bash
./venv/bin/python pipeline/main.py --ids {website_ids}
```

**Run this as a FOREGROUND (blocking) call and wait for it to exit — never as a background task, and never end your turn while it runs.** A sub-agent's background processes are killed the moment its turn ends, which strands extracted events unmerged (this exact mistake happened on 2026-06-10 AND 2026-06-11; recovery needs the parent to run `main.py --merge-only`). Do not arm monitors/wakeups to "wait" for it — just block on the call with a generous timeout.

Then re-check for undated events (Step 1). The count should decrease.

## Step 5: Re-export

After fixing, re-export so changes are reflected on the live site:

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
