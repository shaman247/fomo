# Event Processing Pipeline

Scripts for crawling event websites, extracting structured data, and exporting to JSON.

## Pipeline Overview

The `main.py` script orchestrates the following steps:

1. **Crawl** - Query `websites` table for sites due for crawling, store content in `crawl_results`
2. **Extract** - Use Gemini AI to extract structured event data from crawled content
3. **Process** - Parse extracted events, enrich with location data, store in `crawl_events`
4. **Detail Crawl** - Crawl individual event URLs to fill in missing descriptions/tags/emoji, updating `crawl_events`
5. **Merge** - Deduplicate crawl_events into final `events` table
6. **Export** - Generate JSON files from events table for the website
7. **Upload** - Push JSON files to FTP server

(It also runs an incomplete-results precheck before crawling and adjusts per-site crawl frequencies at the tail. The orchestrated, day-to-day entry point is the `/run-pipeline` slash command — `.claude/commands/run-pipeline.md` — which wraps `main.py` with review/fix steps.)

## Module Structure

```
pipeline/
├── main.py              # Main orchestrator
├── db.py                # Database connection and operations
├── crawler.py           # Web crawling with Crawl4AI
├── extractor.py         # Gemini AI event extraction
├── processor.py         # Markdown parsing, text utilities, enrichment, detail-crawl orchestration
├── merger.py            # Event deduplication
├── exporter.py          # JSON export
├── uploader.py          # FTP upload
├── city_config.py       # Loads config/<FOMO_CITY>.yaml (city/region/branding strings)
├── site_profiles.py     # Per-platform crawl registry; auto-discovers sources/*.py plugins
├── sources/             # Gitignored per-platform crawl plugins (committed *.example.py + README)
├── constants.py         # Shared constants + get_user_agent()
├── event_types.py       # event_type taxonomy labels
├── frequency_analyzer.py# Per-site crawl-frequency analysis
├── dblock.py            # Cross-worktree advisory write lock
├── logging_utils.py     # Logging helpers
└── tests/
    └── test_processor.py
```

## Database Schema

```
websites              - Sites to crawl
crawl_runs            - Pipeline execution records
crawl_results         - Crawled/extracted content per run
crawl_events          - Raw extracted events
crawl_event_occurrences
crawl_event_tags

events                - Final deduplicated events (source of truth)
event_occurrences
event_urls
event_tags
event_sources         - Links events to contributing crawl_events

locations             - Venue database
tags                  - Tag names; type='tag' (curated, in hierarchy) or 'keyword' (search-only)
tag_hierarchy         - DAG edges between curated tags (parent_tag_id, child_tag_id)
tag_aliases           - Keyword/synonym → canonical curated tag
tag_disambiguations   - Context rules for homonym tag variants (e.g. Drama / Film)
tag_rules             - Tag rewrite/exclude/remove rules
```

(This is a partial summary. Instagram tables, website link tables, and the full column lists live in `database/README.md` and `database/schema.sql`; the tag DAG is documented in `.claude/rules/tag-system.md`.)

## Setup

### Prerequisites

- Python 3.8+
- MariaDB/MySQL
- Required packages:
  - `crawl4ai`
  - `google-generativeai`
  - `mysql-connector-python`
  - `python-dotenv`
  - `regex`

### Configuration

Create a `.env` file:

```env
# Gemini AI
GEMINI_API_KEY="your-api-key"
GEMINI_MODEL="gemini-3.1-flash-lite"
GEMINI_TIMEOUT=120

# FTP Upload
FTP_HOST="your-ftp-server.com"
FTP_USER="your-username"
FTP_PASSWORD="your-password"
FTP_REMOTE_DIR="data"

# City selection + crawler identity (optional; defaults shown)
FOMO_CITY="nyc"            # selects config/<FOMO_CITY>.yaml
USER_AGENT="..."           # single crawler/extractor User-Agent (constants.get_user_agent())
```

Database credentials are in `db.py` (local database).

## Usage

### Run Complete Pipeline

```bash
python main.py
```

### Run Individual Modules

```python
import db
import exporter

connection = db.create_connection()
cursor = connection.cursor()

# Export events to JSON
exporter.export_events(cursor)

cursor.close()
connection.close()
```

## Data Flow

```
websites table
     ↓
[Crawl] → crawl_results.crawled_content
     ↓
[Extract] → crawl_results.extracted_content
     ↓
[Process] → crawl_events + occurrences + tags
     ↓
[Detail Crawl] → fills missing descriptions/tags/emoji on crawl_events
     ↓
[Merge] → events + occurrences + urls + tags + sources
     ↓
[Export] → events.day{0..3}.json + events.remainder.json + .desc.json companions
           + locations.*.json + organizers.json + manifest.json
     ↓
[Upload] → FTP server
```

## Deduplication

Events are matched on a combination of location (`location_id`), occurrence date/time slots, and normalized name (with several name-signal discriminators and occurrence-slot confirmation to avoid over-merging). Matched duplicates are merged: URLs combined, occurrences unioned, a best name/description chosen, and contributing `crawl_events` tracked via `event_sources`. The full logic lives in `merger.py`; see `.claude/rules/pipeline.md` and the merger-related entries in project memory for the nuances.

## Output Files

Events are split into per-day chunks so the frontend can load just today's events on startup:

- `events.day0.json` … `events.day3.json` - Events occurring on each of the next 4 calendar days. Multi-day events appear in every chunk they touch; the frontend dedupes by backend `id`.
- `events.remainder.json` - Events with at least one occurrence past day 3 (within the 90-day future window).
- `events.day0.desc.json` … `events.remainder.desc.json` - Per-chunk `{id: description}` companion files (descriptions split out to keep the event chunks small).
- `locations.day0.json` … `locations.day3.json`, `locations.remainder.json` - Venues referenced by events in each chunk.
- `organizers.json` - `{id: {name, url, emoji, description}}` map of event organizers.
- `manifest.json` - `{ "days": ["YYYY-MM-DD", …] }` mapping day index → calendar date.

## Troubleshooting

### Database Issues
- Check MariaDB is running
- Verify credentials in `db.py`

### Extraction Issues
- Ensure `GEMINI_API_KEY` is set
- Check API quota/limits

### Upload Issues
- Verify FTP credentials
- Use `use_tls=True` if server requires SSL
