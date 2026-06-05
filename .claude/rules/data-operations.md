---
paths:
  - "scripts/add_locations.php"
  - "scripts/add_websites.php"
  - "scripts/geocode.php"
  - "scripts/ai_tag_events.py"
---

# Data Operations

## Adding Locations

```bash
php scripts/add_locations.php --help
```
- Requires: name, address, emoji, tags, description
- Use `scripts/geocode.php` to get coordinates: `php scripts/geocode.php --json "Venue Name"`
- Geocode by venue name first; fall back to address if name returns just a neighborhood
- **Verify against existing entries by address, not just name** — DB sometimes has wrong addresses on existing locations (e.g., Cherry on Top was listed at 671 Union St / Park Slope; actually at 379 Suydam St / Bushwick). When the same venue name turns up in cross-reference but the geocoded address doesn't match the DB entry, fix the DB entry rather than creating a duplicate.

## Adding Websites

```bash
php scripts/add_websites.php --help
```
- Supports `location` field to auto-link via `website_locations` table
- Always navigate the website first to find the correct events/calendar URL
- Check for external platforms (Eventbrite, Ovation Tix, Dice)
- **Informational-only websites are valid**: omit `urls` and `crawl_frequency` for venues without crawlable event pages — they still serve as the popup link for the location.

## Linking Tables

- `website_locations` — links websites to locations
- `location_alternate_names` — alternate names scoped to `website_id` or global (`NULL`)
- `location_instagram` — links locations to `instagram_accounts` — venue's IG link in popup comes from here automatically; manually-inserted events don't need their own URL

## Manually Inserting Events

For events at Instagram-only venues or one-offs that didn't come through a crawl, insert directly into `events` + `event_occurrences`. The popup link comes from the venue's existing `website_locations` row, so set `events.website_id` to the venue's primary website.

- **Time format** in `event_occurrences.start_time`: compact lowercase, no spaces — `7pm`, `7:30pm`, `11am`. `end_time` often empty string.
- **Recurring events**: ONE event row, MULTIPLE occurrence rows. Don't create 30 separate events for a weekly series.
- **Smart dedup before insert**: at the same `location_id`, find existing events whose names share significant words (filtering out common queer-event boilerplate: "queer", "lesbian", "sapphic", "trans", "party", "night", "the", etc.). Append occurrences to the match instead of creating duplicates. Different aggregators title the same event differently.
- The `/cross-reference-aggregator` skill, Phase 5.5, has a working template.

## AI-Tagging Events

Manually-inserted events have no `event_tags` and won't show in the filter UI without them.

```bash
./venv/bin/python scripts/ai_tag_events.py --min-id <first_new_id>
```

- Uses Gemini on `(title, description, location_name)` → hashtags + emoji, then runs through `process_tags()` so rewrites/aliases/ancestor propagation match what crawled events get
- Additive: INSERT IGNORE on tag links, COALESCE on emoji
- Supports `--ids`, `--limit`, `--min-id`, `--dry-run`, `--concurrency`

## After Adding

Run pipeline for new websites: `./venv/bin/python pipeline/main.py --ids <id>`

**Clean up the script.** As the final step of any add-locations or add-websites task, REMOVE the entries you just added from `$new_locations` / `$new_websites` so the array goes back to empty (`= [];`). Stale entries pile up across sessions, clutter every subsequent dry-run with "already exists" warnings, and make it harder to see what's actually being added next time. The cleanup is part of the task — don't ship it as "done" until the array is empty.

For pure data updates (no crawls needed) re-export and upload directly:
```python
import sys; sys.path.insert(0, 'pipeline')
import exporter, uploader
from db import create_connection
conn = create_connection()
exporter.export_events(conn.cursor()); conn.close()
uploader.upload(use_tls=False)
```
