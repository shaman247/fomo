---
paths:
  - "pipeline/**"
---

# Pipeline Details

## Orchestration

`main.py` orchestrates: crawl → extract → process → detail crawl → merge → export → upload

All intermediate data lives in the database (not files).

- The merge→export→upload tail runs under the advisory write lock (`dblock.py`); acquisition retries 3 × 600s before aborting with exit code 1 and printing the `--merge-only` recovery command.
- `python pipeline/main.py --merge-only [--ids ...]` runs ONLY the tail (merge → classify → export → upload) — picks up crawl_results that were processed but never merged (interrupted run / lost lock race) without re-crawling or re-paying extraction. Step 0 of a normal run also reports such stranded results (`db.get_stranded_merge_summary`); `crawl_results.merged_at` records when a result's events went through a merge (`status='processed' AND merged_at IS NULL` = stranded).

## Extraction & Enrichment

- Small pages are extracted in a single AI call
- Large pages are chunked, events extracted per chunk, then enriched in batches of 30
- `websites.max_batches` overrides the default limit per-website (default: 3 batches = 90 events)
- **Auto-bump**: when a chunked extraction exceeds the cap, the sync path raises `websites.max_batches` in place to `ceil(N/30)+1` (ceiling 40) and persists it (`extractor._maybe_auto_bump_max_batches`) — unless the site was deliberately throttled below the default of 3, which is respected. Chunk extraction stops early at the old cap's budget, so coverage converges over a couple of runs.
- **Variance guard**: if a sync extraction yields < half the website's trailing-median event count while the crawled content size is within ±20% of its median, the extraction is retried once and the better result kept (`extractor._variance_retry_reason`). Protects against Gemini per-run yield swings (observed 4→24 on identical content) cascading into false archivals.
- Per-URL `js_code` in `website_urls` runs in-browser before scraping — use this to trim historical content from pages with years of past events
- Run pipeline for specific websites: `python pipeline/main.py --ids 123,456`

## Archival guards (merge step)

`db.archive_outdated_events` archives an event only when no source website's latest crawl references it. Events with **future occurrences** additionally require ALL THREE of:
1. last supporting crawl ≥ 14 days old (grace period),
2. ≥ 2 successful crawls of the website since the event was last seen (protects monthly/annual-cadence sites from one-missed-extraction archival),
3. no `start_too_future` rejection matching the event's name from that website in the last 14 days — an extraction rejected only for being beyond `FUTURE_WINDOW_DAYS` means the event is still listed on the page (e.g. Storm King's September program crawled in June).

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
- `exporter.py` — JSON export to per-day chunks (`events.day0..day3.json` + `events.remainder.json`, matching `locations.*.json` and `events.*.desc.json` description companions, plus `organizers.json` and `manifest.json` mapping day index → calendar date)
- `uploader.py` — FTP upload
- `db.py` — Database connection and all DB operations
- `frequency_analyzer.py` — Crawl frequency analysis
