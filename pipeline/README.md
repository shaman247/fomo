# Event Processing Pipeline

Scripts for crawling event websites, extracting structured data, and exporting to JSON.

## Pipeline Overview

The `run_pipeline.py` script orchestrates the following steps:

1. **Crawl** - Query `websites` table for sites due for crawling, store content in `crawl_results`
2. **Extract** - Use Gemini AI to extract structured event data from crawled content
3. **Process** - Parse markdown tables, enrich with location data, store in `crawl_events`
4. **Merge** - Deduplicate crawl_events into final `events` table
5. **Export** - Generate JSON files from events table for the website
6. **Upload** - Push JSON files to FTP server

## Module Structure

```
pipeline/
├── run_pipeline.py      # Main orchestrator
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
FOMO_ENV=local

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

Database credentials are in `db.py` based on `FOMO_ENV`.

## Usage

### Run Complete Pipeline

```bash
python run_pipeline.py
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
[Export] → events.init.json, events.full.json
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

- `events.init.json` - Core NYC area, 7-day window
- `events.full.json` - Extended area, 90-day window
- `locations.init.json` - Locations for init events
- `locations.full.json` - Locations for full events

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
