# Recheck Duplicates Command

A **second-pass** duplicate sweep over two blind spots that `/dedupe-events` leaves behind:

1. **Wrongly-dismissed pairs** — events previously waved off in `dedupe_dismissed_pairs`
   (often as "concurrent programming") that are actually the same event re-listed under
   a new title/slug.
2. **Umbrella / envelope events** — a generic row that stands in for several specific
   sub-events (holds their URLs + the union of their dates), or a specific event that has
   "date-bled" a whole series onto itself. Pairwise dedup can't see these.

Run this weekly. It is driven by one detector script; everything it prints is a
**review candidate**, not an auto-fix — you decide and apply.

```bash
./venv/bin/python scripts/recheck_duplicates.py            # both sections
./venv/bin/python scripts/recheck_duplicates.py --dismissed   # only section 1
./venv/bin/python scripts/recheck_duplicates.py --umbrellas   # only section 2
```

All writes go through the cross-session **write lock** (`pipeline/dblock.py`) and reuse
the primitives in `scripts/find_duplicate_events.py`
(`merge_pair`, `apply_field_overrides`, `record_dismissal`). See CLAUDE.md → Concurrent Sessions.

---

## Section 1 — Re-audit dismissed pairs

The script reconsiders only dismissed pairs where **both events are still live** and they
**share a concrete date+time**, ranks them by name/description similarity (boilerplate
descriptions filtered out), and prints the ones worth a fresh look. Two flags:

- `HI-NAME` — names are ~85%+ similar (a likely rename, e.g. an exhibition-title swap)
- `HI-DESC` — titles differ but a substantive, non-boilerplate description matches

For each flagged pair, fetch full data and **holistically review** (same workflow as
`/dedupe-events` Step B — name, description, URLs, occurrences, sublocation, tags):

- **Same event** (same performer/exhibition/host, same date+time, one is the venue's
  re-listing or rename of the other) → **merge**. Keep the clearer/current title; union
  collections via `merge_pair`.
- **Genuinely distinct** (numbered series `(1/6)`, different showtimes `8pm`/`10pm`,
  different council districts, men's vs women's, distinct concurrent programs) → **leave it**.
  The existing dismissal still stands; do nothing.

Most flags will be correct dismissals — that's expected. You are hunting the few real ones.

```python
import sys; sys.path.insert(0, 'pipeline'); sys.path.insert(0, 'scripts')
from db import create_connection
from dblock import write_lock
from find_duplicate_events import apply_field_overrides, merge_pair
conn = create_connection(); cur = conn.cursor()
with write_lock(conn):
    # confirmed same event — pick the better title, then merge + suppress the dup:
    apply_field_overrides(cur, KEEP_ID, name='<clearer/current title>')   # omit kwargs you don't change
    merge_pair(cur, KEEP_ID, DUP_ID)
    # the dismissal row is now moot — drop it so it doesn't linger:
    cur.execute("DELETE FROM dedupe_dismissed_pairs WHERE %s IN (event_id_a,event_id_b) AND %s IN (event_id_a,event_id_b)", (KEEP_ID, DUP_ID))
    conn.commit()
conn.close()
```

## Section 2 — Umbrella / envelope events

A suspect is an event that **shares specific URLs with, and date-covers, ≥2 other active
events at the same location+website**. Suspects a reviewer has already cleared are stored in
`dedupe_dismissed_umbrellas` and filtered out, so the same false positives (concurrent
exhibitions, community-board committees, multiplex films, recurring comedy slots) don't keep
resurfacing — exactly like `dedupe_dismissed_pairs` does for Section 1. Inspect each remaining
suspect with full occurrence + URL data:

```python
import sys; sys.path.insert(0, 'pipeline')
from db import create_connection
conn = create_connection(); cur = conn.cursor(dictionary=True)
for eid in [UMBRELLA_ID, SUB1, SUB2, ...]:
    cur.execute("SELECT id,name,suppressed FROM events WHERE id=%s", (eid,)); print(cur.fetchone())
    cur.execute("SELECT DISTINCT start_date,COALESCE(start_time,'') st FROM event_occurrences WHERE event_id=%s ORDER BY start_date", (eid,))
    print('  occ', [(str(r['start_date']),r['st']) for r in cur.fetchall()])
    cur.execute("SELECT url FROM event_urls WHERE event_id=%s", (eid,)); print('  url', [r['url'] for r in cur.fetchall()])
```

Decide which shape it is, then fix (always **verify coverage first**):

- **Redundant umbrella** — a generic row (e.g. "Summer Organ Series", "In-Store Performance")
  whose specific sub-events already exist and **cover all its future dates**. → suppress the umbrella:
  ```python
  with write_lock(conn): cur.execute("UPDATE events SET suppressed=1 WHERE id=%s", (UMBRELLA_ID,)); conn.commit()
  ```
- **Date-bled specific** — a *named* event carrying a whole series' dates (e.g. one organist's
  recital listing all 5 nights). → delete the stray occurrences, keep its true date:
  ```python
  cur.execute("DELETE FROM event_occurrences WHERE event_id=%s AND start_date<>%s", (EVENT_ID, TRUE_DATE))
  ```
- **Topic envelope** — a weekly series stamped with one week's topic across every week
  (e.g. "Sunday Platform – Motherhood" on all Sundays). If specific dated instances exist
  for the other weeks, **collapse** the envelope to its one true date (same `DELETE` as above);
  otherwise leave it (don't fabricate per-week topics).
- **Legit series / concurrent events** — distinct installments or simultaneous events that
  share a venue calendar URL but are genuinely different (numbered classes, different committee
  meetings, concurrent exhibitions, multiplex films, a recurring slot vs one-off titles). →
  **record a dismissal** so it stops re-surfacing:
  ```python
  import sys; sys.path.insert(0, 'scripts')
  from recheck_duplicates import record_umbrella_dismissal
  with write_lock(conn):
      record_umbrella_dismissal(cur, UMBRELLA_ID, "concise reason — e.g. 'multiplex: concurrent films'")
      conn.commit()
  ```

After suppressing a real umbrella, drop any now-moot dismissal rows that reference it:
```python
cur.execute("DELETE FROM dedupe_dismissed_pairs WHERE %s IN (event_id_a,event_id_b)", (UMBRELLA_ID,))
```

## Finish — re-export (and offer upload)

After all fixes:

```python
import sys; sys.path.insert(0, 'pipeline')
from db import create_connection
from dblock import write_lock
import exporter
conn = create_connection(); cur = conn.cursor()
with write_lock(conn): exporter.export_events(cur); conn.commit()
conn.close()
```

Then ask the user whether to upload via `python scripts/upload_public_html.py`.
