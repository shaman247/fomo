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
- **Provider split** (`pipeline/llm_providers.py`): five AI paths are individually provider-selectable via `EXTRACTION_PROVIDER` (`gemini` | `openai`, default `gemini`), or `EXTRACTION_PROVIDER_<PATH>` for one path. Measured 2026-08-03 against real crawl results:

  | path | verdict | on `openai` |
  |---|---|---|
  | single | tie | ✅ switchable — 8/10 sites gave identical (name, date) sets |
  | enrichment | tie | ✅ switchable — same enriched counts, no-desc rate, emoji coverage |
  | detail | tie | ✅ switchable — identical descriptions/tags/emoji/occurrences on sample |
  | chunked | tie *(after the name-budget fix)* | ✅ switchable — 57 names / 185 name-date pairs from both |
  | vision | **regression** | ❌ **pinned to Gemini** |

  **vision** is pinned in `llm_providers.GEMINI_PINNED`, which the blanket `EXTRACTION_PROVIDER` switch deliberately does not reach (a per-path override still does). Luna misreads stylized flyer typography: on Lucky 13 Saloon (crawl 109123) it read a FUNGBLADE flyer as "Fungicide", took the promoter as the event name on a Circus of Power bill, and invented a band on a Crashing Wayward flyer — three of three flyers checked against the images, all three of which Gemini read correctly. This path carries the Instagram-first venues, where the event name exists *only* on the flyer. **Verify any vision change by downloading the flyers and reading them, not by diffing the two models' outputs.**

  `--batch` is Gemini-only and does NOT go through `llm_providers` (it builds `InlinedRequest`s directly), so a batch run and a sync run can extract the same page with different models. Batch is not the default.
- **The `max_batches` budget counts DISTINCT EVENT NAMES, not extracted records** (`_execute_chunked_sync`). Enrichment is name-keyed — `_combine_chunked_results` looks it up by `event['name']` — so N records sharing a name cost one enrichment slot between them, not N. Counting raw records made the cap sensitive to a model's *grouping style* rather than a page's size: a model emitting one record per date instead of one record with many occurrences tripped the cap early and **skipped whole chunks** (Prospect Park: 5 of 7 chunks, 34 distinct names vs 57), while auto-bumping the site's `max_batches` on growth that never happened. Names are matched exactly, since that is the enrichment lookup key. This also cuts real enrichment calls on Gemini (same page: 110 records → 57 names, 4 batches → 2). `CHUNK_RECORD_CEILING` (default 5000) is the runaway guard on raw records, which the name budget no longer bounds.
- **Reasoning effort** (`OPENAI_REASONING_EFFORT`, default `low`): `low` is the floor. It matches `medium` exactly across the sites tested at ~half the latency, but `none` collapsed Muhlenberg Library from 19 events to 2 while looking fine on three other pages. Never calibrate this on one page.
- `websites.max_batches` overrides the default limit per-website (default: 3 batches = 90 events)
- **Auto-bump**: when a chunked extraction exceeds the cap, the sync path raises `websites.max_batches` in place to `ceil(N/30)+1` (ceiling 40) and persists it (`extractor._maybe_auto_bump_max_batches`) — unless the site was deliberately throttled below the default of 3, which is respected. Chunk extraction stops early at the old cap's budget, so coverage converges over a couple of runs.
- **Variance guard**: if a sync extraction yields < half the website's trailing-median event count while the crawled content size is within ±20% of its median, the extraction is retried once and the better result kept (`extractor._variance_retry_reason`). Protects against Gemini per-run yield swings (observed 4→24 on identical content) cascading into false archivals.
- **Per-site extraction directives**: a line `[[extraction: force-chunked]] <optional rationale>` in `websites.notes` (or a plugin's `extraction_notes`) forces chunked extraction regardless of the automatic heuristic. `extractor.parse_extraction_directives` strips the whole line before the notes reach any prompt. Use it for sites that sit just under the mode-selection cliff — estimate under `LARGE_PAGE_THRESHOLD` (50) on content over `MAX_CHUNK_CHARS` (30K) — where a single call's output budget can't hold the page's real event count and the yield collapses non-deterministically (w950 Nook: 30 → 12 → 14 on byte-stable 43 KB). Prefer naming the site over nudging the heuristic's inputs, which moves the cliff for everyone.
- **`[[extraction: max-records-per-chunk=N]]`** (same directive line, comma-separable with `force-chunked`) subdivides any chunk holding more than N record headings, splitting only AT a heading (`extractor.cap_records_per_chunk`, a post-pass over whichever chunker ran, so it can't sever a record or exceed `MAX_CHUNK_CHARS`). A chunk's *response* size scales with its record COUNT, not its char count, so a compact 8K chunk of 50 dated showtime cards can overrun the output budget while a 30K chunk of 10 records is fine. **Opt-in on purpose**: measured A/B over the 10 densest real crawls, a global cap of 30 moved distinct extracted events +0.1% while chunk count rose +83% (corpus-wide +47% Gemini calls). Only Film Forum w50 measurably benefits (63 → 66 distinct, reproducible), and it is the only site with the directive set. Measure before adding another — same method as `.scratch/cap_experiment.py`.
- **Occurrence budget per chunk** (`extractor.OCCURRENCE_BUDGET_PER_CHUNK`, default 250, env-overridable; `cap_occurrences_per_chunk`). Every other chunk budget measures the INPUT — chars, record headings — and is blind to the OUTPUT a chunk demands. Those track each other on an ordinary listing (one card, one or two dates) but come apart on a card carrying an **enumerated date list**, where one 3 KB record demands 60 occurrence objects. Measured on w944 The Tiny Cupboard, same content and prompt with only the number of dates the response had to carry changing: 130→130 ok, 480→480 ok, **600→233**, 660→660 ok, **780→493**, **780→60 with `occurrences: null` on 12 of 13 records**. Not a cliff — stochastic degradation past ~500, severe by ~800 — and the model degrades by taking the nullable-`occurrences` exit, so the records come back well-formed and date-less: the event count stays healthy, nothing raises, and the events vanish from the map as undated. The cap subdivides at heading boundaries (repeating a short page preamble onto each piece, so split pieces keep the venue/address header) and is **global, unlike `max-records-per-chunk`**, because it is inert: over 10 days of crawls only 19 of 1,431 chunks exceed it, corpus-wide +2.0% chunks, and every affected site is in the at-risk shape (BAM 684 date tokens in one chunk, GrowNYC 648, Arts Society of Kingston 528, Alamo Drafthouse 504, Alvin Ailey 438). Verified: the reconstructed pre-fix w944 page went 973 → **1,980 of 1,980** occurrences with 0 nulls. The single-call path needs no equivalent — `estimate_event_count` halves the same date count, so any page dense enough to be at risk is already routed to chunked.
- **Dropped-date warning** (`extractor._report_dropped_dates`): after each chunk, a record that came back with `occurrences: null` while its own source text lists ≥ 2 dates is reported as `⚠️ DATE DROP`, with a per-page summary. This is the detector for the failure above, kept because the cap cannot split a *single* record that enumerates too many dates and because the degradation is stochastic. It warns rather than fails — the rest of the chunk is good data, and failing the crawl would trade a date loss for an archival cascade.
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
- `extractor.py`: `extract_single_event()` — Gemini structured output via `SingleEventExtraction` schema. Receives the site's `websites.notes` (directive lines stripped, same as `prepare_extraction`) and the page's own URL, so a per-site directive that shapes the listing extraction shapes this one too — until 2026-08-24 it did not, and a detail page printing a series' whole season re-derived the union of dates the listing pass had been told to split
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
- `extractor.py` — AI event extraction (full pages + single event detail crawl); prompt city-bits from `city_config`
- `llm_providers.py` — provider-agnostic structured JSON generation for the **single-call path only** (see Provider split above); translates any provider error into `ProviderCallFailure`, which `extractor` re-raises as `ExtractionCallFailure` so a failed call is stored as `status='failed'` (content preserved) rather than an events-less zero
- `processor.py` — Markdown parsing, text utilities, tag processing, detail crawl orchestration (Step 5); location/tag token lists from `city_config`
- `merger.py` — Event deduplication
- `exporter.py` — JSON export to per-day chunks (`events.day0..day3.json` + `events.remainder.json`, matching `locations.*.json` and `events.*.desc.json` description companions, plus `organizers.json` and `manifest.json` mapping day index → calendar date). Also the weekly public NDJSON dataset (see below).
- `uploader.py` — FTP upload (`upload()` for the frontend data files; `upload_public_dataset()` for the NDJSON export, which uses the `PUBLIC_HTML_FTP_USER` account since the data account is chrooted away from `public_html/`)
- `db.py` — Database connection and all DB operations
- `frequency_analyzer.py` — Crawl frequency analysis

## Public NDJSON dataset export (weekly)

Two consumer-facing datasets served at `https://fomo.nyc/exports/`:

- **`events-upcoming.ndjson`** — the active event window (today → +90d), same eligibility as the frontend export. Dated snapshots `events-upcoming-YYYY-MM-DD.ndjson` alongside (last 8 kept, locally and remotely).
- **`events-past.ndjson`** — occurrences that **ended** within the last 28 days (`PUBLIC_EXPORT_PAST_DAYS`), **archived events included** (ended events get archived once sources stop listing them — they're the point of this file). Stable file only, no dated snapshots. An event straddling today appears in both files with its occurrences split; an ongoing span (ends in the future) is upcoming, never past.
- **`manifest.json`** — schema_version, generated_at, per-dataset file/event_count/window.

One JSON object per line: `event_id, name, [short_name], [event_type], [emoji], [description], location{location_id, name, [address], [sublocation], lat, lng}, occurrences[{start_date, start_time, end_date, end_time}], urls[], tags[], [organizers[{name, url}]]`.

- Runs automatically in the pipeline tail (Step 8b, also in `--merge-only`) when the newest dated upcoming snapshot in local `exports/` is ≥ 7 days old — **the local dated files are the scheduling state**; a failed upload deletes the fresh snapshot so the next run retries. Non-fatal to the pipeline.
- Force anytime: `./venv/bin/python pipeline/main.py --export-dataset`.
- Eligibility (both datasets): not suppressed, mapped location with coordinates, ≥ 1 URL, aggregator trust gate; upcoming additionally requires not archived. Organizer attribution resolves to roots and drops aggregators, like `organizers.json`. Occurrences are deduped (exact + contained same-time spans).
- **The schema only changes additively** — bump `exporter.PUBLIC_EXPORT_SCHEMA_VERSION` on any breaking change. Tests: `pipeline/tests/test_public_export.py`.
- The pre-existing one-off `june_events.ndjson` / `june_events.csv` also live in remote `exports/` — unrelated to this pipeline, left in place.
