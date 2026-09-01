---
name: run-pipeline
description: Run the full pipeline, investigate findings, apply fixes, and review events
---

# Run Pipeline Command

Run the full event processing pipeline, investigate any issues, apply fixes, and review flagged events.

## Coverage Area

**`config/nyc.yaml` (the `coverage:` block) is the authority — not this page, and not your sense of what "the NYC metro area" means.** It defines coverage in postal geography (ZIP3 per state, plus ZIP5 carve-outs for ZIP3s that straddle a county line) and is read by code via `city_config.coverage()`. When you are deciding whether a venue is in or out, **test its ZIP against that block**, don't reason from the county or region name:

```bash
./venv/bin/python -c "
import sys; sys.path.insert(0,'pipeline'); sys.path.insert(0,'scripts')
from find_out_of_area_events import CoverageArea
print(CoverageArea().classify_address('123 Main St, Edison, NJ 08817'))"
```

Region names are a poor proxy — "Northern New Jersey" reads as excluding Middlesex/Somerset, but ZIP3 088/089 are explicitly IN. Two suppression mistakes of exactly this shape have happened (Edison + South Brunswick NJ, 2026-08-19; see also the `out_of_area_scan_blind_to_mapped` lesson: test ZIPs, not names).

Non-authoritative human summary of what `coverage:` currently admits, to orient you before you check:
- **New York City** (all five boroughs)
- **Long Island** (Nassau and Suffolk, including the Hamptons)
- **Westchester** and **Rockland**
- **Hudson Valley** (Dutchess, Orange, Ulster, Putnam) plus **Sullivan** (Bethel Woods) and the kept Greene/Columbia strip near the Ulster/Dutchess line
- **Northern *and Central* New Jersey** — Bergen, Hudson, Essex, Passaic, Union, **Middlesex**, **Somerset**, **Hunterdon**, Monmouth, Ocean, and **Morris** (via the NJ 078/079 ZIP5 whitelists)
- **Southern Connecticut** (Fairfield County)

Anything not admitted by the `coverage:` block is out. If the summary above and the config ever disagree, the config wins and this summary is the bug — fix it here rather than editing `coverage:` to match.

Events from touring companies performing at venues **outside** this area (e.g., in Europe, the Midwest, the Deep South) should be archived. Events at venues **within** this area should be kept and mapped to locations.

## Step 0: Scheduled Tasks Due Today

Before crawling, check for date-triggered maintenance tasks that have come due:

```bash
./venv/bin/python scripts/due_tasks.py
```

This reads `.claude/scheduled-tasks.md` and lists tasks whose `Due` date has arrived (`Status: pending`, `Due` <= today). Exit code is 0 if any are due, 1 if none.

- **If none are due**, proceed to Step 1.
- **If tasks are due**, open `.claude/scheduled-tasks.md`, and for each due task carry out the actions in its block. These are self-contained (each names the website IDs, commands, SQL, and success criteria). Most are targeted recrawls + verification — run them here via `./venv/bin/python pipeline/main.py --ids <ids>` and confirm the success criteria. If a task adds a **new** crawl source (website or `website_urls` entry), add it now so the main Step 1 run picks it up.
- **After completing each task**, update its entry in `.claude/scheduled-tasks.md`:
  - `Recur: none` → mark `Status: done` and move the whole block to `.claude/completed-tasks.md` (newest at top).
  - `Recur: annual` → bump `Due` forward one year and **keep** `Status: pending` (also update any year literals inside the task's commands, e.g. a `crawl_after` value).
  - `Recur: <N>d` → bump `Due` forward by N days, keep `Status: pending`.
- If a task needs judgment beyond its documented actions (e.g. a source still isn't published), leave it `pending`, do **not** bump the date, and surface it under "Findings requiring user approval" in the summary.

Re-export + upload (Step 5) at the end of the run will publish any event changes these tasks produced.

## Step 1: Run the Pipeline

Run the pipeline in the background, logging to `/tmp/pipeline_run.log`:

```bash
caffeinate -i -m -s ./venv/bin/python pipeline/main.py 2>&1 | tee /tmp/pipeline_run.log
```

This runs the full pipeline: crawl → extract → process → merge → export → upload.

Wait for the background task's completion notification — the runtime fires it the moment `pipeline/main.py` exits. Stay idle (or work on unrelated tasks) until then. Grep the log post-hoc for actionable signals; the runtime already aggregates per-site signals into the final summary.

Once the task completes, extract the summary and any signals worth triaging from the log:

```bash
# Final summary
grep -E "PIPELINE COMPLETED|PIPELINE FAILED|^Summary:|Websites crawled:|Total events processed:|Total archived:|Total upcoming events archived" /tmp/pipeline_run.log

# Things worth triaging (all aggregated post-hoc, not per-site)
grep -E "Traceback|WARNING: .* events would need .* batches, capping|upcoming event\(s\) archived|lost most of their events|Content too large|injection skipped|chunk request\(s\) failed" /tmp/pipeline_run.log
```

The pipeline output to look for:
- **Cap warnings** (`WARNING: N events would need M batches, capping at X`) — high-yield sites that need `max_batches` bumped
- **Truncation warnings** (`Content too large (N chars), truncating to 300000`) — the payload was cut BEFORE chunking, so those events were never even offered to Gemini. This is a *silent* coverage loss: the site still reports a healthy event count, so nothing else flags it. Background is in `## MAX_CONTENT_CHARS silently truncates 13 high-volume sites before extraction` — now in **`.claude/completed-tasks.md`**, not scheduled-tasks.
  **The log line does not name the site** (extraction runs 10 workers, so the output interleaves). Find the offenders from the DB instead:
  ```sql
  SELECT cr.website_id, w.name, CHAR_LENGTH(cr.crawled_content) AS chars, cr.event_count
  FROM crawl_results cr JOIN websites w ON w.id = cr.website_id
  WHERE cr.crawled_at >= NOW() - INTERVAL 6 HOUR AND CHAR_LENGTH(cr.crawled_content) > 300000
  ORDER BY chars DESC;
  ```
  Then confirm the dropped tail actually holds events before acting — slice `crawled_content[300000:]` and look. The fix is `UPDATE websites SET max_content_chars = <N>` (resolution order: `websites.max_content_chars` → the source plugin's `SiteProfile.max_content_chars` → the global default; see `site_profiles.max_content_chars_for`). A plugin-backed site may already be covered by its profile and need nothing — w388 RA runs 697K chars and extracts 848 events fine.
- **Degraded js_code injections** — a site whose js_code fetches its data via a synchronous XHR can fall
  back to the raw server-rendered page. The crawl still reports `processed` with a healthy-looking count, so
  nothing else flags it: NYPL silently lost 80% of its coverage this way (915 → 178 events) because
  `text_mode` defaulted on and blocked the XHR; `text_mode=0, light_mode=0` restored it.
  **The `injection skipped` string in the grep above is a WEAK signal — only 6 of 34 sync-XHR injections
  write a fail-safe message at all** (audited 2026-08-04), so a silent no-op usually logs nothing.
  The reliable check is a **shape test**: extract each `js_code`'s own injected `<h1>` literal and assert it
  appears in `crawl_results.crawled_content`. That is mechanical and covers every site; see
  `## Audit sync-XHR js_code sites for silent text_mode degradation` in `.claude/scheduled-tasks.md`.
  **Do not flip `text_mode` without the symptom** — 33 of 34 sync-XHR sites work fine on the default, and
  the one structural candidate (w104) turned out to be byte-identical under both settings.
- **Chunk failures** (`N/M chunk request(s) failed`) — since 2026-08-04 a PARTIAL chunk failure fails
  closed (stored `failed`, content preserved) instead of silently storing a truncated extraction.
  A non-trivial count here is real signal about chunk reliability that used to be invisible; recover
  with `main.py --ids <ids>` and investigate the cause rather than reverting the guard.
- **Partial-crawl / collapse warnings** (`⚠️ WARNING: N website(s) lost most of their events vs. the previous crawl`) —
  emitted from `db.py` in the FINAL SUMMARY, not per-site during the merge, and it names the site plus both
  deltas: `w1970 Long Island Arts Alliance Events: 23 → 0 events (-100%), content 22,485 → 7,776 chars (-65%)`.
  **This is the signal that catches a source which MIGRATED PLATFORMS.** Such a site keeps reporting
  `status='processed'` while its content decays to nothing, so it appears in neither the crawl-failure list
  nor the archival warnings — its events are still active until a later merge archives them, with nothing
  explaining why. On 2026-09-01 this line correctly named w1970 (its calendar had moved to a Timely iframe)
  and was missed only because the grep above did not include it. **Read the line's own discriminator**:
  content collapsed too → partial crawl or a migration; content unchanged → extraction issue or a season that
  genuinely ended. Feed every site named here to Step 2 triage.
- **Archival warnings** (`⚠️ WARNING: N upcoming event(s) archived`) — review for crawl regressions vs legitimate site rotations
- **Tracebacks** — fatal errors that need investigation
- **Total counts** — sanity-check websites crawled, events processed, events archived

## Step 2: Triage Pipeline Issues

If the pipeline log shows any crawl failures (`status` `failed`/`timeout` with no/tiny content) or any `⚠️ WARNING: N upcoming event(s) archived` lines, delegate diagnosis + durable fixes + re-crawl verification to **`/triage-pipeline-issues`**. That command spawns a single `general-purpose` sub-agent that:

- Builds the issue list from `crawl_results` (failures from the last 12 hours) and from `/tmp/pipeline_run.log` (archival warnings).
- Skips only unverifiable cases up front: sites whose own crawl returned 0 events in this run (those are diagnosed once as crawl failures, not double-counted as archival regressions), and sites whose URL is 403/Cloudflare/login-walled to WebFetch.
- For each remaining site: pulls recent crawl history, reads `js_code` / `max_batches` / `notes`, WebFetches the source to check for live event listings, classifies the issue, and applies a fix from the command's allow-list (max_batches bumps, scan_full_page disable, js_code corrections, alt name additions, un-archivals, etc.).
- Re-crawls (`pipeline/main.py --ids ...`) to verify, then re-exports + uploads if anything changed.
- Reports findings that require user approval (anything outside the allow-list — disabling sites, deleting rows, deep code changes).

Single-event archival warnings are included in scope alongside larger ones — Squarespace/JS-widget extraction failures and misconfigured crawl URLs commonly surface as single-event archivals.

For complex crawl issues (stealth mode, Cloudflare bypass, JS navigation, broken widgets, venue closures), the command defers to `/optimize-crawls`.

## Step 3: Parallel Cleanup (6 sub-agents in one message)

After `/triage-pipeline-issues` finishes, fan out the per-domain cleanup commands as **six concurrent `general-purpose` sub-agents**. Send all six `Agent` tool calls in a single message.

### Sub-agent briefs

Spawn each as `subagent_type: general-purpose`. Use these briefs verbatim (substituting the actual path).

**Agent 1 — Hide uninteresting events**
```
Follow the workflow in .claude/commands/hide-uninteresting-events.md.

Completeness target: process every candidate from scripts/find_review_candidates.py until --count reports 0. For candidate counts in the hundreds, fan out inner sub-agents in batches of ~50 to classify them. Apply suppress OR keep to every candidate and set reviewed=1 on every row processed.

Leave the events export and upload to the parent.

Report: total candidates processed, suppressed N (group by reason category), kept M, unreviewed remaining (target: 0).
```

**Agent 2 — Deduplicate events**
```
Follow the workflow in .claude/commands/dedupe-events.md.

Completeness target: every pair in the shared-URL, cross-source same-time, and similar-name tiers ends in either a merge_pair() OR a record_dismissal() call. The same-source same-time tier is large (thousands) and most are venue-internal multi-room noise; for that tier, skim for cross-extraction duplicates (same description, near-identical names), apply merge_pair to those, and bulk-dismiss the rest with a templated reason. Every review-needed tier reaches a terminal decision on every pair.

Run scripts/find_duplicate_events.py --suppress first for exact-name dupes (auto-safe). Then holistic-review the rest.

Leave the events export and upload to the parent.

Report: auto-suppressed N, merged K pairs, dismissed J pairs (per tier), pairs deferred (target: 0).
```

**Agent 3 — Fix undated events**
```
Follow the workflow in .claude/commands/fix-undated-events.md.

Completeness target: investigate every website with ≥5 undated events from this run. For each: classify as Category A (suppress via js_code), B (extractor issue — flag and report), C (no dates available — leave; merger filters them out), or D (notable recurring event — research externally and insert occurrence). Apply Category A and D fixes inline. For B, document each in the report. Sites with <5 undated events get a single-pass classification with no per-site investigation.

**Re-crawl every site whose js_code you changed** via `./venv/bin/python pipeline/main.py --ids <id1>,<id2>,...` (one bundled call, not per-site). After it completes, verify each requested id has a row in `crawl_results` from the last 30 minutes with `status='processed'` and a non-zero `event_count`. If any id is missing or returned 0 events, retry it once individually — if it still fails, note it in the report.

Leave the events export and upload to the parent.

Report: total undated, sites investigated K (with per-site classification), js_code fixes applied, D-category occurrences inserted, B-category sites flagged, re-crawl results (sites verified / sites that failed re-crawl).
```

**Agent 4 — Fix unmapped events**
```
Follow the workflow in .claude/commands/fix-unmapped-events.md. Cover BOTH NULL-location events AND generic-location events (locations.generic_location = 1).

Completeness target: every venue with ≥2 unmapped events reaches a decision (matched / created / archived / explicitly-skipped with reason), as does every venue whose location_name is a specific building, address, or proper-noun establishment regardless of event count. For 10+ unique unmapped venues, fan out inner sub-agents in batches of 5–8 venues each.

Create new venues via scripts/add_locations.php (the helper enforces required fields; direct INSERTs are blocked by check_helpers.sh). Use the /geocode skill for any new venue's address.

Leave the events export and upload to the parent.

Report: total unmapped, matched-to-existing N (via alt names), created M new locations, archived K out-of-area, explicitly-skipped J with reason breakdown (online/TBA/private/etc.).
```

**Agent 5 — Fix address mismatches**
```
Follow the workflow in .claude/commands/fix-address-mismatches.md.

Completeness target: every candidate from the scan reaches a classification (DB-wrong-address / multi-branch / cross-street / generic-location / adjacent-building / other). Fix every Category 1 (DB-wrong-address) candidate. Record Categories 2-5 in the report with the location_id so the user can verify the "left alone" decision.

Use the /geocode skill for any address change.

Leave the events export and upload to the parent.

Report: candidates scanned N, fixed K (Category 1), classified-and-left J (Category 2-5 with breakdown), unclassified (target: 0).
```

**Agent 6 — Review newly-added recurring spans + single-occasion events**
```
Catch two date-shape bugs introduced by THIS run before they mislead on the map. Scope is just-added events, not the full backlog (the weekly /fix-recurring-spans and /fix-single-occasion-events tasks do the comprehensive sweeps).

PART A — recurring envelope spans (blanket every day on the map):
1. Run: ./venv/bin/python scripts/fix_recurring_spans.py --review --new
   (--new restricts to events created/updated in the last day — i.e. this run's merge.)
2. FIX_SPAN + COURSE_WEEKLY buckets = fixable after review. Review the listed ids with `--show <ids>` (FIX_SPAN: confirm periodic meetings, not exhibitions; COURSE_WEEKLY: confirm the same-weekday span really is a WEEKLY class by checking the event's source URL — quarterly PPV listings and daily summer programs are the known false positives), then apply scoped to the approved ids (COURSE_WEEKLY only ever applies via explicit --ids):
   ./venv/bin/python scripts/fix_recurring_spans.py --apply --ids <approved_ids>
3. RECURRING_RANGE / PROGRAM_RANGE / INVERSE buckets need source judgment — do NOT auto-fix. List them in your report (id + name + bucket) so the parent can decide whether to handle now or defer to the weekly full scan.
Follow .claude/commands/fix-recurring-spans.md for the bucket definitions and the exhibition-vs-meeting discriminator.

PART B — single-occasion events (a named reception/weekday-ticket carrying the PARENT festival/exhibition's whole schedule, so it shows misleading dates / wrong days):
1. Run: ./venv/bin/python scripts/fix_single_occasion_events.py --review --new
2. DROP_SPAN + COLLAPSE_WEEKDAY buckets = auto-fixable (the two unambiguous shapes). Glance at the ids with `--show <ids>`, then apply (default run already restricts to these buckets; --new keeps it to this run):
   ./venv/bin/python scripts/fix_single_occasion_events.py --apply --new
3. COLLAPSE_REVIEW / REVIEW buckets need source judgment — do NOT auto-fix. List them in your report (id + name + bucket).
Follow .claude/commands/fix-single-occasion-events.md for the bucket definitions.

Leave the events export and upload to the parent.

Report: Part A — new span-bearing events scanned N; FIX_SPAN/COURSE_WEEKLY auto-fixed K (ids); RECURRING_RANGE/PROGRAM_RANGE/INVERSE flagged (ids + bucket); LIKELY_OK count. Part B — single-occasion events scanned N; DROP_SPAN/COLLAPSE_WEEKDAY auto-fixed K (ids); COLLAPSE_REVIEW/REVIEW flagged (ids + bucket).
```

### After the parallel batch returns

1. Read each agent's report. Surface any "findings requiring user approval" before continuing.
2. Run the out-of-area scan:

```bash
./venv/bin/python scripts/find_out_of_area_events.py
```

It inspects `sublocation` / `location_name` / `name` against a gazetteer (US
states, out-of-area US and foreign cities, foreign countries) with an in-area
whitelist learned from the `locations` table. Read-only; it never suppresses
anything itself.

Findings come in three tiers:

- **HIGH** — a structured location field names an out-of-area place, or the
  event name carries an explicit "<City>, <ST|Country>" pair. Usually real
  (NYU away games, Boston harbor cruises, a Philadelphia club night). Confirm
  against the event URL, then suppress.
- **PROPAGATED** — same website + mapped location + suite number as a HIGH hit.
  This is how the Fabrik Tribeca / Chicago leak was caught: 3 of the 7 events
  named Chicago outright, the other 4 carried only a bare "Suite 630".
- **REVIEW** — description-only "taking place in <city>" framing. Weakest tier;
  read the event before acting.

Keep films set elsewhere, touring performers' bios, and artist origin notes —
they are not out-of-area. The scan deliberately ignores "based in <city>" in
descriptions for exactly this reason: on 2026-07-19 the old description-only
SQL scan returned 45 candidates and 0 real hits, all performer hometowns, while
missing both genuine clusters (a Mbale City, Uganda fundraiser and the 7 Fabrik
Chicago events).

## Step 4: Classify New Event Types

The merge (Step 1) and any re-crawls in Step 3 create new events with `event_type = NULL`. Classify them now — **after** dedupe/hide/merge cleanup so events that got suppressed or merged away aren't classified. Run this last among the data steps because it only needs the final event set.

```bash
# How many active events still need a type?
./venv/bin/python -c "
import sys; sys.path.insert(0,'pipeline')
from db import create_connection
conn=create_connection(); c=conn.cursor()
c.execute('SELECT COUNT(*) FROM events WHERE archived=0 AND suppressed=0 AND event_type IS NULL')
print('untyped active events:', c.fetchone()[0])
"
```

If the count is 0, skip this step. Otherwise delegate to one `general-purpose` sub-agent:

```
Follow the workflow in .claude/commands/classify-event-types.md (Mode A), but scope ONLY to active events with event_type IS NULL (the new events from this run). Do NOT touch already-typed events.

Pull every NULL-typed active event (id, name, short_name, description, location_name, sublocation, section, tags, occ_count, span_days) to a JSON file. If ≤600 rows, classify in a single pass; if more, split into ~600-row batches and fan out inner sub-agents. The valid label strings are defined in pipeline/event_types.py (VALID_EVENT_TYPES) — assign exactly one per event and validate every label against that set before writing.

Bulk-update events.event_type for each row. Then run:
  ./venv/bin/python scripts/audit_event_types.py --validate --drift
to confirm 0 invalid labels, 0 NULL active, and to spot-check for obvious name↔type drift.

Report: events classified N; type distribution (top 10); UNKNOWN rows with ids (these are non-events — suppress them, and note that any reaching here means the extractor junk filter has a gap worth a look); Other rows with ids (flag if 3+ share a shape — the taxonomy may need a new type); and audit results (invalid labels, drift mismatches).
```

UNKNOWN rows surfaced here are junk that slipped past the extractor's `is_obvious_non_event` filter — suppress them (`suppressed=1, reviewed=1`) and treat a recurring pattern as a signal to extend that filter.

After classification, mirror `event_type` into the **Format** tag family so the new events are filterable/searchable by type (idempotent; rebuilds membership from `event_type`):

```bash
./venv/bin/python scripts/sync_format_tags.py
```

> `event_type` is surfaced to the frontend via the `Format` curated-tag family (`Format › category › type`), driven by `pipeline/event_types.py`. The sync above keeps `event_tags` in step with `event_type`; the tag hierarchy + event_tags then export normally in Step 5. (See `.claude/rules/tag-system.md` → Format family.)

## Step 5: Re-export and Upload

After all sub-agents return, re-export the data and upload to production:

```python
import sys
sys.path.insert(0, 'pipeline')
from db import create_connection
from exporter import (export_events, export_organizers, export_tag_hierarchy,
                      classify_event_sections)

conn = create_connection()
cursor = conn.cursor(buffered=True)

classify_event_sections(cursor, conn)
export_stats = export_events(cursor)
export_tag_hierarchy(cursor)
# MUST pass export_stats['organizer_root_ids'] — this is what `main.py` does.
# Calling export_organizers(cursor) with no id set makes it RECOMPUTE from all
# active events, which is a looser SUPERSET: it lists organizers whose events
# were never exported (no URL, no location), so the published organizers.json
# disagrees with the published events. Measured 2026-07-26: 2510 organizers
# recomputed vs 1627 actually emitted.
export_organizers(cursor, export_stats['organizer_root_ids'])

cursor.close()
conn.close()
```

> Export the tag hierarchy and organizers too, not just events — otherwise any
> `event_type` / Format-tag changes from Step 4 never reach the frontend.

Then:
```bash
./venv/bin/python scripts/upload_public_html.py
```

## Summary Format

After all steps, provide a summary that combines the parent agent's work with each sub-agent's report:

```
=== PIPELINE RUN SUMMARY ===

Step 0 — Scheduled Tasks:
- Tasks due: N (titles) — completed K, deferred J (with reason)

Pipeline (Step 1):
- Websites crawled: N
- Events processed: N (X new, Y merged)
- Events archived: N
- Upcoming events archived: N

Step 2 — Triage Pipeline Issues:
- Crawl failures investigated: N
- Archival warnings investigated: M
- Durable fixes applied: K
- Un-archivals: J events
- Findings requiring user approval: F

Step 3 — Parallel Cleanup (6 sub-agents):
- Hide uninteresting: suppressed N (top categories), kept M
- Dedupe: auto-suppressed N, merged K pairs, dismissed J pairs
- Undated: total N, fixed K via js_code, flagged J for follow-up
- Unmapped: matched N, created M new locations, archived K, skipped J
- Address mismatches: scanned N, fixed K, left alone J
- New recurring spans: scanned N, FIX_SPAN auto-fixed K, flagged J for review (ids+bucket)
- Out-of-area inline review: scanned N, suppressed K

Step 4 — Classify New Event Types:
- New events classified: N (skipped if 0)
- UNKNOWN (junk) found + suppressed: K
- Other flagged for taxonomy review: J
- Audit: invalid labels (target 0), drift mismatches noted
- Format tags synced (event_type → tag family): ✓

Step 5 — Re-export and Upload:
- Events exported: N
- Data uploaded: ✓/✗

Findings requiring user approval:
- (if any) <site>: <description>
```
