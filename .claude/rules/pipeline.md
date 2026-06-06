---
paths:
  - "pipeline/**"
---

# Pipeline Details

## Orchestration

`main.py` orchestrates: crawl → extract → process → detail crawl → merge → export → upload

All intermediate data lives in the database (not files).

## Extraction & Enrichment

- Small pages are extracted in a single AI call
- Large pages are chunked, events extracted per chunk, then enriched in batches of 30
- `websites.max_batches` overrides the default limit per-website (default: 3 batches = 90 events)
- Per-URL `js_code` in `website_urls` runs in-browser before scraping — use this to trim historical content from pages with years of past events
- Run pipeline for specific websites: `python pipeline/main.py --ids 123,456`

## Detail Crawl (Step 5)

Some events get "No description available." because the listing page lacked details. The detail crawl step crawls their individual event URLs to extract descriptions, tags, and emoji — updating `crawl_events` before the merger reads them.

**Flow:** find candidates → filter → crawl individual URLs → extract via Gemini → process tags → update `crawl_events`/`crawl_event_tags`

**Code lives in four modules:**
- `db.py`: `get_detail_crawl_candidates()` — find and filter candidates; `get_website_crawl_settings()` — per-website settings
- `crawler.py`: `build_event_crawl_config()` / `crawl_event_url()` / `get_browser_key()` — crawl config, browser grouping
- `extractor.py`: `extract_single_event()` — Gemini structured output via `SingleEventExtraction` schema
- `processor.py`: `crawl_event_details()` — orchestration, parallelism; `apply_crawled_details()` — per-event DB updates

**Filtering (to avoid wasted crawls):**
- `websites.skip_reenrichment = 1` — skips websites whose event URLs consistently fail (bot-protected ticketing sites, JS-rendered pages with no content, etc.)
- Shared URL dedup — if multiple events from the same website point to the same URL, it's a listing page, not an individual event page; all are skipped
- Source URL match — event URLs matching `website_urls` entries are skipped

**Parallelism:** events for the same website are crawled sequentially (to avoid overloading a site), but different websites run concurrently. Controlled by `NUM_WORKERS` semaphore (shared with Steps 2 and 3). Websites are grouped by browser settings (text_mode, stealth, user_agent) so each group shares a browser instance.

**One-off script:** `scripts/fix_missing_descriptions.py` fixes already-merged events in the `events` table directly. Supports `--dry-run`, `--limit N`, `--ids`, `--min-id`.

## Module Roles

- `constants.py` — Shared constants (FUTURE_WINDOW_DAYS, MAX_PAGES_DEFAULT, match thresholds) + `get_user_agent()` (USER_AGENT env, the single UA for crawler/extractor/plugins)
- `city_config.py` — Loads `config/<FOMO_CITY>.yaml` (default `nyc`); all city-specific strings (extraction-prompt geography/intro, generic location names, processor token lists, scoring calibration examples). `import city_config`
- `site_profiles.py` — Generic per-platform registry; auto-discovers site-specific crawl plugins from `pipeline/sources/*.py`.
- `crawler.py` — Web crawling with Crawl4AI (listing pages + individual event URLs), browser config/grouping; consults `site_profiles` for skip/inject-js/custom-fetch
- `extractor.py` — Gemini AI event extraction (full pages + single event detail crawl); prompt city-bits from `city_config`
- `processor.py` — Markdown parsing, text utilities, tag processing, detail crawl orchestration (Step 5); location/tag token lists from `city_config`
- `merger.py` — Event deduplication
- `exporter.py` — JSON export to per-day chunks (`events.day0..day3.json` + `events.remainder.json`, matching `locations.*.json`, plus `manifest.json` mapping day index → calendar date)
- `uploader.py` — FTP upload
- `db.py` — Database connection and all DB operations
- `scorer.py` / `export_scores.py` — Event scoring (rubric calibration examples from `city_config`)
- `frequency_analyzer.py` — Crawl frequency analysis
