# Fix Recurring Spans Command

Find and fix recurring meetings (weekly classes, monthly socials) that were extracted as a single long contiguous date range, so they stop blanketing every day on the map.

## Background

Some recurring events get extracted with **both** their real per-meeting occurrences **and** a single long "envelope span" occurrence covering the whole series (e.g. SpeakEasier Language Exchange: discrete monthly Saturdays *plus* a `2026-03-28 → 2026-11-28` span). Because the exporter's `_event_covers_day` treats any day inside an occurrence's `[start, end]` range as a hit, that envelope span makes the event render on the map **every single day** of the range instead of only on its actual meeting dates. A >14-day span also flips `section` to "Ongoing", though `section` only controls popup tab grouping — the every-day map bug is the real damage.

The fix: regenerate the discrete series at the detected cadence up to the export window (repairing any gaps), delete the envelope span, and reset `section` so the exporter reclassifies.

**The hard part is telling periodic meetings from exhibitions.** Continuously-on-view exhibitions *also* have a long span plus a few discrete dates (openings/receptions) — but for them the span is **correct**, and deleting it would hide the exhibition on every day except those markers. The script auto-excludes obvious exhibitions, but **ambiguous cases need manual review** (see Step 2).

The logic lives in `scripts/fix_recurring_spans.py`.

## Step 1: Broad review scan

Start with the wide net — it buckets **every** active span-bearing event by what's wrong and the action each needs:

```bash
./venv/bin/python scripts/fix_recurring_spans.py --review
```

Buckets (only the first three are printed in full; the rest are `LIKELY_OK`):

| Bucket | What it is | Action |
| --- | --- | --- |
| **FIX_SPAN** | Regular cadence (≥3 discrete, same weekday, 7/14/~30-day gaps) with an **envelope** span. | Auto-fixable — Steps 2–3. |
| **RECURRING_RANGE** | A recurring meeting **flattened into a range**: either span-only / ≤2 discrete with a recurrence keyword ("weekly", "Saturdays"), or a regular discrete grid whose span **extends past** the captured dates (the series' tail was caught as a range). | **Manual** — build the real meeting dates from the source page, then delete the span. The discrete dates the auto-fixer would have generated can't be trusted here (break weeks, enrollment-only programs). |
| **INVERSE** | A continuously-open **exhibition** with a correct span **plus bogus regular discrete dates** layered on (e.g. "Hyunjin Park: Jump", weekly Fridays on a daily-open show). | **Manual** — delete the discrete rows, **keep** the span. |
| LIKELY_OK | Continuous exhibition/run, or irregular dates. | Leave alone. |

Inspect any id with `--show` (the long span is flagged `<-- SPAN`, with the description):

```bash
./venv/bin/python scripts/fix_recurring_spans.py --show 92589,75800
```

Nothing is written by `--review` / `--show` / the default dry-run.

## Step 2: Triage the FIX_SPAN bucket

`--review` and the default dry-run both surface the auto-fixable set; `--skipped` additionally lists what was declined and why:

```bash
./venv/bin/python scripts/fix_recurring_spans.py --skipped
```

You own the final call on this list. Two checks:

- **Verify they're real meetings.** Names should read as classes/workshops/socials/concerts/markets, almost always with consistent start/end **times** on the discrete rows. Anything that looks continuously-open, drop with `--exclude` (Step 3).
- **Scan `--skipped` for wrongly-declined meetings.** A real meeting can be skipped for irregular cadence or a coincidental exhibition keyword. Confirm via `--show`, then force it in with `--ids`.

### Handling RECURRING_RANGE and INVERSE (manual)

These are **not** auto-fixed. For **INVERSE**, keep the span and drop the fake discrete rows:

```sql
-- keep the span; remove the fake regular point-occurrences
DELETE FROM event_occurrences
WHERE event_id = {id} AND (end_date IS NULL OR DATEDIFF(end_date,start_date) <= 2);
UPDATE events SET section = NULL WHERE id = {id};
```

For **RECURRING_RANGE**, decide per event: if the existing discrete rows already cover the real meetings, just delete the span (`... AND end_date IS NOT NULL AND DATEDIFF(end_date,start_date) > 14`). If the span hides additional sessions, rebuild the real dates from the source first. **Enrollment-only programs** ("Register For…", closed courses with assessments) and **registration artifacts** are judgment calls — they may not belong on a public events map at all; consider `suppressed = 1`.

## Step 3: Apply the FIX_SPAN bucket

Once the list is reviewed, write the changes. Drop any false positives you found with `--exclude`:

```bash
./venv/bin/python scripts/fix_recurring_spans.py --apply --exclude 102500,75832
```

Or restrict to a hand-approved subset with `--ids`:

```bash
./venv/bin/python scripts/fix_recurring_spans.py --apply --ids 92589,84169,143466
```

For each fixed event the script: deletes the >14-day envelope span(s), inserts any missing in-window cadence dates at the meeting time, and sets `section = NULL` for reclassification.

> **Tip:** snapshot the affected occurrences first if you want an easy revert — `SELECT * FROM event_occurrences WHERE event_id IN (...)` to a file before applying.

## Step 4: Re-export

After fixing, re-export so the changes reach the live site:

```python
import sys
sys.path.insert(0, 'pipeline')
from db import create_connection
from exporter import export_events, classify_event_sections

conn = create_connection()
cursor = conn.cursor(buffered=True)

classify_event_sections(cursor, conn)   # reclassifies the section=NULL events
export_events(cursor)

cursor.close()
conn.close()
```

Then `python scripts/upload_public_html.py` to deploy (or let the next `/run-pipeline` carry it).

## Notes

- **Root cause (upstream):** extraction emits a date range for "recurs monthly through November" alongside the next few specific dates, and the merger keeps both — so a re-crawl can reintroduce a span. Re-running this command periodically (or after a big crawl) keeps it clean; a pipeline-side guard mirroring the classify logic would prevent regression entirely.
- The `--apply` step only touches events that survive both the auto-classifier **and** your `--exclude`/`--ids` review — when in doubt, leave it out and handle it by hand.
