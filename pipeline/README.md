# Event Processing Pipeline

This directory contains scripts for processing event data through a complete pipeline.

## Pipeline Overview

The `run_pipeline.py` script orchestrates the following steps in order:

1. **Crawl Sites** (`crawl_sites.py`) - Crawls configured websites to collect event information
2. **Extract Events** (`extract_events.py`) - Uses Gemini AI to extract structured event data from crawled content
3. **Process Responses** (`process_responses.py`) - Enriches event data with location coordinates and additional metadata
4. **Export Events** (`export_events.py`) - Deduplicates and exports events to JSON files
5. **Upload Data** (`upload_data.py`) - Uploads the exported JSON files to a configured FTP server

## Setup

### Prerequisites

- Python 3.8 or higher
- Required Python packages (install with `pip install -r requirements.txt`):
  - `crawl4ai`
  - `google-generativeai`
  - `python-dotenv`
  - `regex`

### Configuration

Configure the following environment variables in `.env`:

```env
# Gemini AI API Key (required for event extraction)
GEMINI_API_KEY="your-gemini-api-key"

# FTP Configuration (required for uploading)
FTP_HOST="your-ftp-server.com"
FTP_USER="your-username"
FTP_PASSWORD="your-password"
FTP_REMOTE_DIR="data"  # Optional: remote directory path
```

## Usage

### Run the Complete Pipeline

To run all steps in sequence and upload data:

```bash
python run_pipeline.py
```

### Run Individual Steps

You can also run each script individually:

```bash
# Step 1: Crawl websites
python crawl_sites.py

# Step 2: Extract events
python extract_events.py

# Step 3: Process responses
python process_responses.py

# Step 4: Export events
python export_events.py

# Step 5: Upload data
python upload_data.py
```

## Directory Structure

```
pipeline/
├── run_pipeline.py          # Main pipeline orchestration script
├── crawl_sites.py           # Website crawler
├── extract_events.py        # AI-powered event extraction
├── process_responses.py     # Data enrichment and processing
├── export_events.py         # Event deduplication and export
├── upload_data.py           # Data upload to server
├── data/
│   ├── websites.json        # Configuration for sites to crawl
│   ├── locations.json       # Location database for enrichment
│   └── tags.json           # Tag processing rules
└── README.md               # This file

../event_data/
├── crawled/                # Raw crawled content (markdown)
├── extracted/              # AI-extracted event tables (markdown)
├── processed/              # Processed event data (JSON)
└── archived/               # Archived old files

../public_html/data/
├── events.init.json        # Initial event set (NYC core area, 7 days)
├── locations.init.json     # Locations for initial events
├── events.full.json        # Full event set (all areas, 90 days)
└── locations.full.json     # Locations for full events
```

## Data Upload Details

The pipeline uploads the following files from `public_html/data/`:
- `events*.json` (events.init.json, events.full.json)
- `locations*.json` (locations.init.json, locations.full.json)

Note: Other files like `tags.json` are not uploaded as they change infrequently.

### Upload Options

- **Standard FTP**: Default, uses plain FTP connection
- **FTPS (FTP over TLS)**: To use encrypted connection, modify `run_pipeline.py` and set `use_tls=True` in the `upload_data.main()` call

## Troubleshooting

### Data Upload Issues

- **Connection Refused**: Check that FTP_HOST is correct and the server is accessible
- **Authentication Failed**: Verify FTP_USER and FTP_PASSWORD are correct
- **Directory Not Found**: The script will attempt to create the remote directory if it doesn't exist
- **Use FTPS**: If your server requires TLS/SSL, set `use_tls=True` in the upload function

### Pipeline Errors

- **Missing API Key**: Ensure GEMINI_API_KEY is set in `.env`
- **Import Errors**: Install required packages with `pip install -r requirements.txt`
- **File Not Found**: Ensure the pipeline is run from the `pipeline` directory

## Notes

- The pipeline includes deduplication logic to prevent duplicate events
- Events are filtered to only include those in the NYC area
- Date filtering excludes past events and events more than 90 days in the future
- Old crawled data is automatically archived before re-crawling
