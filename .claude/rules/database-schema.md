---
paths:
  - "pipeline/**"
  - "scripts/**"
---

# Database Schema & Queries

## Key Tables

We use junction tables for fields with multiple values (e.g., event dates/times, tags).
- `locations` - Venues with coordinates, used for event enrichment
- `location_alternate_names` - Alternate names for locations (location_id, alternate_name, website_id)
  - `website_id = NULL` means the name applies globally across all websites
  - `website_id = <id>` scopes the alternate name to a specific website
- `websites` - Sites to crawl, with frequency and selectors. `base_url` is the main site URL.
  - `parent_website_id` points at the organizer ROOT website this site belongs to (e.g. each nycgovparks.org park page → the NYC Parks root, w2). Organizer = root (parent if set, else self); the exporter resolves all `organizer_ids` to roots, so sibling sites collapse into one organizer chip. Single-level by convention (`scripts/backfill_parent_websites.py --audit` enforces); may cross domains (a venue's Instagram/posh.vip row → the venue's main site). Never point a parent at a platform host (Instagram, Meetup, Eventbrite, …) or an aggregator.
- `website_urls` - Specific URLs to crawl for each website (website_id, url, sort_order). `js_code` runs in-browser before scraping (e.g., to trim historical content).
- `website_locations` - Links websites to locations (website_id, location_id)
- `instagram_accounts` - Instagram handles for venues (handle, name)
- `location_instagram` - Links locations to Instagram accounts (location_id, instagram_id)
- `events` - Events
- `event_occurrences` - Dates and times for events
- `tags` - Tags (name, emoji, type). `type` is either `'tag'` (curated, shown in filters) or `'keyword'` (search-only)
- `tag_hierarchy` - DAG edges (parent_tag_id, child_tag_id). A tag can have multiple parents.
- `event_tags` - Links events to tags. Stores **all ancestor tags explicitly** so filtering is a flat set intersection — no tree traversal at query time.
- `crawl_results` - Stores crawled_content and extracted_content per crawl. Lifecycle timestamps: `crawled_at` → `extracted_at` → `processed_at` → `merged_at` (`status='processed' AND merged_at IS NULL` = extraction succeeded but the merge tail never ran; recover with `main.py --merge-only`)
- `crawl_events` → `events` - Raw extracted events are deduplicated into final events
- `tag_rules` - Rewrite/exclude/remove rules for tag processing

## Query Patterns

Use `pipeline/db.py` to connect to the database:

```python
import sys
sys.path.insert(0, 'pipeline')
from db import create_connection

conn = create_connection()
cursor = conn.cursor(dictionary=True)

# Query events (note: field is 'name', not 'title')
cursor.execute('SELECT id, name, description, emoji, location_id, website_id FROM events WHERE id = %s', (123,))
event = cursor.fetchone()

# Get events with website info
cursor.execute('''
    SELECT e.id, e.name, e.emoji, w.name as website_name
    FROM events e
    LEFT JOIN websites w ON e.website_id = w.id
    WHERE e.website_id = %s
''', (456,))

# Get event occurrences
cursor.execute('''
    SELECT eo.event_id, eo.start_date, eo.start_time, eo.end_time
    FROM event_occurrences eo
    WHERE eo.event_id = %s
    ORDER BY eo.start_date
''', (123,))

conn.close()
```
