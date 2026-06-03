# Event Processing Pipeline

Scripts for crawling event websites, extracting structured data, and exporting to JSON.

## Pipeline Overview

The `main.py` script orchestrates the following steps:

1. **Crawl** - Query `websites` table for sites due for crawling, store content in `crawl_results`
2. **Extract** - Use Gemini AI to extract structured event data from crawled content
3. **Process** - Parse extracted events, enrich with location data, store in `crawl_events`
4. **Merge** - Deduplicate crawl_events into final `events` table
5. **Export** - Generate JSON files from events table for the website
6. **Upload** - Push JSON files to FTP server

## Module Structure

```
pipeline/
├── main.py              # Main orchestrator
├── db.py                # Database connection and operations
├── crawler.py           # Web crawling with Crawl4AI
├── extractor.py         # Gemini AI event extraction
├── processor.py         # Markdown parsing, text utilities, and enrichment
├── merger.py            # Event deduplication
├── exporter.py          # JSON export
├── uploader.py          # FTP upload
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
tags                  - Normalized tag names
tag_rules             - Tag rewrite/exclude/remove rules
```

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
GEMINI_MODEL="gemini-3-flash-preview"
GEMINI_TIMEOUT=120

# FTP Upload
FTP_HOST="your-ftp-server.com"
FTP_USER="your-username"
FTP_PASSWORD="your-password"
FTP_REMOTE_DIR="data"
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
[Merge] → events + occurrences + urls + tags + sources
     ↓
[Export] → events.day{0..3}.json + events.remainder.json + manifest.json
     ↓
[Upload] → FTP server
```

## Deduplication

Events are deduplicated by:
- **Location**: Same lat/lng (rounded to 5 decimals)
- **Date**: Same first occurrence start date
- **Name**: Similar after normalization (punctuation/case removed)

Duplicates are merged: URLs combined, shorter name kept, sources tracked.

## Output Files

Events are split into per-day chunks so the frontend can load just today's events on startup:

- `events.day0.json` … `events.day3.json` - Events occurring on each of the next 4 calendar days. Multi-day events appear in every chunk they touch; the frontend dedupes by backend `id`.
- `events.remainder.json` - Events with at least one occurrence past day 3 (within the 90-day future window).
- `locations.day0.json` … `locations.day3.json`, `locations.remainder.json` - Venues referenced by events in each chunk.
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
