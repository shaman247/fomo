---
name: run-pipeline
description: Run the full pipeline, investigate findings, apply fixes, and review events
---

# Run Pipeline Command

Run the full event processing pipeline, investigate any issues, apply fixes, and review flagged events.

## Coverage Area

Our coverage area is the **NYC metro region**, which includes:
- **New York City** (all five boroughs)
- **Long Island** (Nassau and Suffolk counties, including the Hamptons)
- **Westchester County** and **Rockland County**
- **Hudson Valley** (Dutchess, Orange, Ulster, and Putnam counties)
- **Northern New Jersey** (Bergen, Hudson, Essex, Passaic, Union, Middlesex, Monmouth, Ocean counties and nearby)
- **Southern Connecticut** (Fairfield County and nearby)

Events from touring companies performing at venues **outside** this area (e.g., in Europe, the Midwest, the Deep South) should be archived. Events at venues **within** this area should be kept and mapped to locations.

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
grep -E "Traceback|WARNING: .* events would need .* batches, capping|upcoming event\(s\) archived" /tmp/pipeline_run.log
```

The pipeline output to look for:
- **Cap warnings** (`WARNING: N events would need M batches, capping at X`) — high-yield sites that need `max_batches` bumped
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

## Step 3: Parallel Cleanup (5 sub-agents in one message)

After `/triage-pipeline-issues` finishes, fan out the per-domain cleanup commands as **five concurrent `general-purpose` sub-agents**. Send all five `Agent` tool calls in a single message.

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

### After the parallel batch returns

1. Read each agent's report. Surface any "findings requiring user approval" before continuing.
2. Run the out-of-area description scan (below) inline. The 2026-05-18 audit found 42 candidates and 1 real out-of-area event (the rest were films/touring performers); treat findings skeptically and require explicit "taking place in <city>" / "Join us in <city> for…" language before suppressing.

```sql
SELECT e.id, e.name, e.location_name, l.name as mapped_to,
       SUBSTRING(e.description, 1, 200) as description_preview,
       w.name as website_name
FROM events e
JOIN locations l ON e.location_id = l.id
LEFT JOIN websites w ON e.website_id = w.id
WHERE e.archived = FALSE AND e.suppressed = FALSE
  AND (
    e.description REGEXP '(^|[^a-zA-Z])(in|across|around|throughout) (Los Angeles|Chicago|San Francisco|Philadelphia|Miami|Seattle|Portland|Austin|Denver|Atlanta|Nashville|Washington D\\.?C\\.?|Houston|Dallas|Detroit|Minneapolis|New Orleans|San Diego|Phoenix|Salt Lake City|Richmond|Raleigh|Charlotte|Tampa|Orlando|Las Vegas|Honolulu|London|Paris|Berlin|Tokyo|Toronto|Montreal|Mexico City)([^a-zA-Z]|$)'
    OR e.description REGEXP '(Los Angeles|Chicago|San Francisco|Philadelphia|Miami|Seattle|Portland|Austin|Denver|Atlanta|Nashville|Houston|Dallas|Detroit|Minneapolis|New Orleans|San Diego|Phoenix|Salt Lake City|London|Paris|Berlin|Tokyo|Toronto|Montreal|Mexico City) (arts? district|community|creatives?|locals?|area|neighborhood|chapter|region)'
  )
ORDER BY w.name, e.id;
```

Suppress only events where the description explicitly says "Join us in Philadelphia for..." / "A gathering for Chicago fashion creatives in <Chicago neighborhood>". Keep films set elsewhere, touring performers, and similar references.

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
from exporter import export_events, classify_event_sections

conn = create_connection()
cursor = conn.cursor(buffered=True)

classify_event_sections(cursor, conn)
export_events(cursor)

cursor.close()
conn.close()
```

Then:
```bash
./venv/bin/python scripts/upload_public_html.py
```

## Summary Format

After all steps, provide a summary that combines the parent agent's work with each sub-agent's report:

```
=== PIPELINE RUN SUMMARY ===

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

Step 3 — Parallel Cleanup (5 sub-agents):
- Hide uninteresting: suppressed N (top categories), kept M
- Dedupe: auto-suppressed N, merged K pairs, dismissed J pairs
- Undated: total N, fixed K via js_code, flagged J for follow-up
- Unmapped: matched N, created M new locations, archived K, skipped J
- Address mismatches: scanned N, fixed K, left alone J
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
