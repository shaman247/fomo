# Triage Pipeline Issues Command

Diagnose **both** crawl failures and upcoming-events-archived warnings from a pipeline run, apply durable fixes, and verify via re-crawl. Designed to be invoked by `/run-pipeline` after the pipeline log is written, or stand-alone after any pipeline run.

## When to use

The pipeline emits two kinds of post-run signals worth investigating:

1. **Crawl failures / timeouts** — `crawl_results.status` is `failed`, `timeout`, or `ERR_ABORTED`, and recent crawls produced zero or tiny content. Distinct from in-run cap warnings (which are extraction issues, not crawl issues).
2. **Archival warnings** — `⚠️ WARNING: N upcoming event(s) archived` lines. The merger archived events that still have future occurrences. Could be legitimate (event genuinely off the page) or a regression (extractor/crawler/merger bug).

Both share the same diagnostic loop: pull recent crawl history, read js_code / max_batches / notes, WebFetch the source, classify, apply allowed fix, verify. So one sub-agent handles both.

## How to invoke

Spawn a single `general-purpose` sub-agent with a self-contained brief — it does not have access to the parent conversation. Pass:

- Path to the pipeline log (`/tmp/pipeline_run.log` by default).
- The "Allowed durable fixes" allow-list (below) and the explicit deny-list.
- Empirical priors below so the agent doesn't waste cycles re-validating them.

## Empirical priors

Findings from previous /triage-pipeline-issues runs that should shape the agent's behavior:

- **Single-event archival warnings have a ~43% regression rate on fetchable sources** (audited 2026-05-16 on 18 sites). Do not skip the long tail. Only sites whose own crawl failed in the same run, or whose source URL returns 403 / Cloudflare / login, are unverifiable.
- **Squarespace `?format=json` js_code injection sometimes silently fails** (intermittent fetch error). When this happens, the native eventlist markdown is still in the crawl content — the extractor *should* pick those up, but Gemini variance sometimes drops events. Un-archive false positives; no code fix.
- **Tribe Events API js_code is a common regression source.** Slug regexes assume `/events/category/<slug>/` URLs and fail open (returning ALL events) when the page URL differs. Hardcode the category slug, looking it up via `/wp-json/tribe/events/v1/categories`.
- **Extractor's geographic rule was a silent filter** (fixed 2026-05-16, but watch for regression). If a metro-edge venue (Hudson Valley, Long Island, North *or Central* NJ, Fairfield CT) suddenly drops to 1-2 events extracted from a healthy-sized page, check `pipeline/extractor.py` `get_prompt()` for "NYC area" instead of the full metro list. That prose now lives in `config/nyc.yaml` as `extraction.region_rule`, and it must stay in sync with the `coverage:` block in the same file — a county in `coverage:` but missing from `region_rule` is a silent coverage loss.
- **Multi-venue parent-and-child clusters are duplicate-of-parent** (e.g. BPCA child sites whose events all live under the parent Battery Park City crawl). Archival warnings on the children are usually noise; the events stay active under the parent's website_id. Don't unarchive the child events — confirm the parent has them, then leave them archived.
- **Merger recurring-event duplicates were fixed 2026-05-16** via `allow_no_date_overlap=True` on the location_id tier. If a same-name same-location duplicate still appears post-fix, location_name drift is the cause (AI mis-extracted the venue) — handle via `merge_pair` not by reverting the merger change.
- **Cap warnings include the website name** (since 2026-05-18). The log line format is `WARNING: [<website name>] N events would need M batches, capping at X`. Match on `[<name>]` to attribute, look up the `website_id` via `SELECT id FROM websites WHERE name = ?`, and apply the allow-list bump.

## Allowed durable fixes (apply without confirmation)

| Symptom | Durable fix |
|---|---|
| `Timeout` with `scan_full_page = 1` following many subpages | `UPDATE websites SET scan_full_page = 0 WHERE id = X` |
| `ERR_ABORTED` with 4+ consecutive failures on a single URL | Check `website_urls.url`; if the page returns 404/410 to WebFetch, propose a replacement URL but report rather than apply |
| Cap warning `WARNING: [<name>] N events would need M batches, capping at X` (website name now in log) with `max_batches IS NULL` | Look up `website_id` via `SELECT id FROM websites WHERE name = ?`, then `UPDATE websites SET max_batches = ROUND(N/30) + 1 WHERE id = X` |
| Tribe API js_code returning leaked events (regex doesn't match URL → `catParam = ''`) | Hardcode the category slug after verifying via `/wp-json/tribe/events/v1/categories` |
| Squarespace `?format=json` js_code injection silently failed this run, source still has events in markdown | Un-archive false-positive archivals; no code fix |
| Events still listed on the source page, extractor missed them this run (Gemini variance, content size healthy, prompt rules look correct) | `UPDATE events SET archived = 0 WHERE id IN (...)` |
| Same-name recurring event re-extracted as duplicate, but with a *different* location_name (AI venue drift) | Manual `merge_pair(cur, keep_id, delete_id)` from `scripts/find_duplicate_events.py` |
| Source page exists at a different path than crawled (`/our-events` vs `/events`) | Verify the new path returns events via WebFetch, then `UPDATE website_urls SET url = '<new>' WHERE id = X`. Re-crawl to confirm |
| Multi-venue parent-and-child cluster archival | Confirm parent has the same events active under its `website_id`. Leave the child events archived. No action |
| Touring / regional venue drops to 1-2 of N extracted events on a healthy-sized page | Check `pipeline/extractor.py` `get_prompt()` for over-narrow geographic filter; broaden the rule with the full metro region |

## NOT allowed without user confirmation

- Disabling a website (`UPDATE websites SET disabled = 1`)
- Deleting rows of any kind
- Force-pushing or amending commits
- Modifying merger.py / extractor.py logic beyond clearly-localized prompt strings or the existing `allow_no_date_overlap` pattern. Bigger changes should be discussed first.
- Touching authentication / Cloudflare / stealth-mode flags (`stealth`, `text_mode`, `light_mode`, `user_agent`) — defer to `/optimize-crawls`

## Sub-agent brief (paste this verbatim when invoking)

```
You are triaging post-run signals from a fomo.nyc pipeline run. Both crawl failures and upcoming-events-archived warnings are in scope. The pipeline already completed; log is at /tmp/pipeline_run.log. Apply durable fixes from the allow-list in .claude/commands/triage-pipeline-issues.md and verify via re-crawl. Report findings.

WORKING DIRECTORY: /Applications/XAMPP/xamppfiles/htdocs/fomo
PYTHON: ./venv/bin/python
DB connect: `import sys; sys.path.insert(0, 'pipeline'); from db import create_connection`

## Step 1 — Build the issue list

A) Crawl failures from this run:
```
./venv/bin/python <<'EOF'
import sys; sys.path.insert(0, 'pipeline')
from db import create_connection
conn = create_connection(); cur = conn.cursor()
cur.execute("""
  SELECT cr.website_id, w.name, cr.status, LENGTH(cr.crawled_content) AS sz,
         cr.event_count, SUBSTRING(cr.error_message,1,120)
  FROM crawl_results cr JOIN websites w ON cr.website_id = w.id
  WHERE cr.crawled_at >= (NOW() - INTERVAL 12 HOUR)
    AND (cr.status IN ('failed','timeout') OR cr.event_count = 0)
  ORDER BY cr.website_id
""")
for r in cur.fetchall():
    print(f"  w={r[0]:5} status={r[2]:8} sz={r[3] or 0:>7} events={r[4]:>3} | {r[1][:40]:40} | {r[5] or ''}")
cur.close(); conn.close()
EOF
```

B) Archival warnings from the log:
```
./venv/bin/python <<'EOF'
import re
with open('/tmp/pipeline_run.log') as f: log = f.read()
# NOTE: main.py prefixes every line with a "[HH:MM:SS] " timestamp, so each line break must
# tolerate an optional timestamp before the leading whitespace. Without TS, this silently
# matches nothing and the whole archival-warning arm looks clean (seen 2026-07-18).
TS = r'(?:\[\d\d:\d\d:\d\d\]\s*)?'
pat = re.compile(
    r'Archived (\d+) outdated event\(s\) from (.+?)\n'
    + TS + r'\s*⚠️\s+WARNING:\s+(\d+) upcoming event\(s\) archived[^\n]*\n'
    r'((?:' + TS + r'\s*- Event \d+:.*\n)+)', re.M)
for m in pat.finditer(log):
    eids = re.findall(r'Event (\d+):', m.group(4))
    print(f"  upcoming={int(m.group(3)):3}  {m.group(2).strip()}  events={eids}")
EOF
```

## Step 2 — Filter out unverifiable cases

Skip up front:
- Sites where the latest crawl_result has `status` `failed`/`timeout` AND `event_count = 0` AND the issue list shows them under crawl failures. Those are crawl failures (handled in Step 4), not archival regressions — diagnose once, not twice.
- Sites whose URL returns 403 / Cloudflare challenge / login wall to WebFetch. Note them in the report but don't try to verify.

**Before declaring any URL 404 / broken / "needs replacement", you MUST `SELECT url FROM website_urls WHERE website_id = ?` and WebFetch that exact URL.** Never infer the crawl URL from the website's name or `base_url` — they often differ from the actual `website_urls.url` (e.g. `/weekly-meditation-classes-this-month` rather than `/weekly-meditation-classes`). A "URL is 404" finding is invalid if you didn't fetch the actual DB URL.

## Step 3 — Per-issue diagnosis (parallelize if 5+ issues)

For each site:

1. **Pull state:**
```sql
SELECT w.id, w.name, w.max_batches, w.crawl_timeout, w.scan_full_page, w.notes,
       w.disabled, w.skip_reenrichment
FROM websites w WHERE w.id = ?;

SELECT id, url, js_code FROM website_urls WHERE website_id = ?;

SELECT id, crawled_at, status, LENGTH(crawled_content) AS sz, event_count,
       SUBSTRING(error_message,1,120)
FROM crawl_results WHERE website_id = ? ORDER BY id DESC LIMIT 5;
```

2. **For archival warnings**, also pull the archived events and check the source:
```sql
SELECT e.id, e.name, e.location_id, e.location_name, MIN(eo.start_date)
FROM events e JOIN event_occurrences eo ON e.id = eo.event_id
WHERE e.website_id = ? AND e.archived = 1
GROUP BY e.id HAVING MIN(eo.start_date) >= CURDATE() LIMIT 30;
```
Then `WebFetch` the crawl URL and look for the archived events' names. Recurring events may have slight date drift — accept the next instance.

3. **Check for duplicate-of-parent pattern:**
```sql
SELECT e2.id, w2.name, e2.archived FROM events e2
JOIN websites w2 ON e2.website_id = w2.id
WHERE e2.name IN (...archived names...) AND e2.archived = 0;
```
If a parent website has the same events active, do not unarchive on the child.

4. **Classify** the issue and pick an action from the allow-list in `triage-pipeline-issues.md`. If no allowed fix applies, mark as a finding for the user.

## Step 4 — Apply and verify

Apply allowed fixes. For every site you touched js_code or extractor logic on, re-crawl:
```
./venv/bin/python pipeline/main.py --ids <id1>,<id2>
```

Then confirm:
- The new crawl extracted a sensible event count (compare to neighboring sites or older successful crawls).
- The previously-archived events did not get re-archived (`SELECT id, archived FROM events WHERE id IN (...)`).

If a fix causes re-archival or no improvement, REVERT it and report.

## Step 5 — Re-export + upload

If anything changed in the DB, re-export + upload:
```python
import sys; sys.path.insert(0, 'pipeline')
from db import create_connection
from exporter import export_events
conn = create_connection(); cur = conn.cursor(buffered=True)
export_events(cur); cur.close(); conn.close()
```
Then `./venv/bin/python scripts/upload_public_html.py`.

## Step 6 — Report (under 400 words)

```
## Triage Summary
- Crawl failures investigated: N
- Archival warnings investigated: M
- Durable fixes applied: K
- Un-archivals applied: J events
- Findings requiring user approval: F

## Per-site outcomes
- <Website>: <type> — <classification> — <action taken | finding>

## Findings requiring user approval
(if any) <site>: <description of needed change>
```

DO NOT apply fixes outside the allowed list. Err on the side of un-archiving and reporting rather than touching code.
```
