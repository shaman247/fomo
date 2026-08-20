# Fix Address Mismatches Command

Find events whose `sublocation` looks like a street address but doesn't match the linked location's address, then fix the underlying data.

## Background

Some scrapers (Posh.vip, Eventbrite, organizer-side aggregators) put a full street address into the event's `sublocation`. The pipeline keeps that text — it's useful for the location-matcher's address fallback (`pipeline/processor.py` Step 5b). After matching, the export step in `pipeline/exporter.py` calls `sublocation_redundant_with_address()` to skip exporting it if it equals the matched location's address.

When the export *still* shows an address-style sublocation, it means one of:

- **DB has the wrong address** — the venue moved, was geocoded incorrectly, or the row was created by hand with a typo. (Fix.)
- **Multi-branch venue** — one location row covers multiple physical sites (e.g. Gagosian, Kadampa Meditation Center, P.P.O.W Gallery). (Leave; sublocation distinguishes branches.)
- **Corner/cross-street alternate** — DB and sublocation point to the same building from different streets (e.g. Bar 13 at `35 E 13th St` vs `121 University Pl`). (Leave; both are correct.)
- **Generic-location event** — `generic_location = 1` row (`Upper East Side`, `Central Park`, `McCarren Park`) where sublocation gives the specific spot. (Leave; sublocation is the useful detail.)
- **Adjacent building** — venue spans multiple addresses (e.g. Lisson Gallery at 504 + 508 W 24th). (Leave.)

This command finds candidates and fixes only the first category.

## STOP — check for a scheduled move before applying any Category 1 fix

**A venue that is MOVING is not a Category 1 fix, even though it looks exactly like one.** Before
changing any address, grep `.claude/scheduled-tasks.md` for the venue name:

```bash
grep -in "<venue name>" .claude/scheduled-tasks.md .claude/completed-tasks.md
```

If a task governs the move, **follow that task's date and do nothing here** — leave the row alone and
mention it in your report as "deferred to scheduled task". A `locations` row holds ONE address, so
moving it early mispins every event still happening at the OLD site, and those are the imminent,
visible ones. "More events fall after the move than before" is NOT a sufficient reason to move early:
the pre-move events are days away and on the map right now, while the post-move ones are months out.

**Known repeat offender: Brooklyn Brewery (loc 2349).** It moves from 79 N 11th St to 1 Wythe Ave
after a farewell party on 2026-08-29. This pass applied the move early on **2026-08-17** and again on
**2026-08-19**; both were reverted the same day. The tell that it is premature: the venue's own row has
an event *titled* "Farewell Party: One Last Night at 79 N 11th". Do not move it before its task's
`Due` date.

Corollary: **a Google geocode that still returns the OLD address is evidence the move has not
happened yet**, not evidence that our DB is stale. Treat a name-first geocode disagreeing with your
web-search reading as a reason to stop, not to proceed.

## Step 1: Find candidates

Run the scan from a Python script — the matcher logic lives in `pipeline/processor.py`:

```python
import sys; sys.path.insert(0, 'pipeline')
from collections import defaultdict
from db import create_connection
from processor import (
    sublocation_looks_like_address,
    sublocation_redundant_with_address,
)

# `sublocation_looks_like_address` decides whether the text claims a street
# address at all. Plain sub-venue values ("Studio B", "5th Floor") are skipped,
# and so are the ones that merely *start* with a number while naming a door or
# a room ("65th Street Entrance", "14TH ST. Mainstage", "24th floor terrace") —
# no address fix can ever resolve those, so they are not candidates.

conn = create_connection()
cur = conn.cursor(dictionary=True)
cur.execute("""
    SELECT e.id, e.sublocation, e.location_id, l.name AS loc_name,
           l.address AS loc_address, l.lat, l.lng,
           l.generic_location, w.name AS website
    FROM events e
    JOIN locations l ON e.location_id = l.id
    LEFT JOIN websites w ON e.website_id = w.id
    WHERE e.archived = 0 AND e.suppressed = 0
      AND e.sublocation IS NOT NULL AND e.sublocation != ''
      AND l.address IS NOT NULL  AND l.address != ''
      AND l.generic_location = 0
""")

# `generic_location = 1` rows (neighborhoods, parks, corridors) are filtered out in
# SQL, not just skipped during triage: on those rows the sublocation is *supposed*
# to carry the specific spot, so they can never be a fix. Flipping a park/corridor
# row to `generic_location = 1` is therefore the durable way to retire it from this
# scan — before this filter existed they kept reappearing every run.

by_loc = defaultdict(list)
for r in cur.fetchall():
    if not sublocation_looks_like_address(r['sublocation']):
        continue
    if sublocation_redundant_with_address(r['sublocation'], r['loc_address']):
        continue  # matcher already handles this at export
    by_loc[r['location_id']].append(r)

# Sort by event count so we look at the highest-impact venues first
for loc_id, rows in sorted(by_loc.items(), key=lambda kv: -len(kv[1])):
    sample = rows[0]
    unique_subs = sorted({r['sublocation'] for r in rows})
    websites = sorted({r['website'] or '?' for r in rows})
    print(f"loc {loc_id}: {sample['loc_name']!r}")
    print(f"  DB address: {sample['loc_address']!r}")
    print(f"  generic={bool(sample['generic_location'])} coords=({sample['lat']}, {sample['lng']})")
    print(f"  {len(rows)} events / sites {websites}")
    for s in unique_subs[:5]:
        print(f"    sub: {s!r}")
    print()
conn.close()
```

## Step 2: Categorize each candidate

Walk the list top-down. For each location:

1. **`generic_location = 1` rows never reach you** — Step 1 filters them in SQL. If a
   park/corridor/neighborhood row keeps surfacing, the fix is to flip its
   `generic_location` flag, not to re-triage it every run.
2. **Skip if the venue is known to span multiple addresses or sites** (Gagosian, Kadampa Meditation Center, P.P.O.W Gallery, Manhattan Community Boards that meet at rotating venues, etc.).
3. **Skip if the DB and sublocation are the same building from different streets** (corner addresses). You can usually tell by checking that the lat/lng matches both addresses.
4. **Otherwise it's a candidate fix** — most likely the DB has a stale or wrong address. Several events from different sources agreeing on the same alternate address is a strong signal.

## Step 3: Verify with /geocode before changing the DB

Never paste lat/lng from a search snippet — always run `php scripts/geocode.php --json "<query>"`. Verify both:

- Geocoding the venue **name** alone returns the address from the events (not the DB's address).
- Geocoding the DB's address returns coordinates far from where events actually are (or returns a different city — common with bad street prefixes like `W` that move East Hampton to East Islip).

```bash
php scripts/geocode.php --json "Venue Name"
php scripts/geocode.php --json "candidate address from sublocations"
php scripts/geocode.php --json "current DB address"
```

If the venue-name geocode and the sublocation address agree but the DB address disagrees, the DB is wrong.

## Step 4: Apply the fix

Update the location row with the corrected address and lat/lng:

```python
import sys; sys.path.insert(0, 'pipeline')
from db import create_connection
conn = create_connection()
cur = conn.cursor()
cur.execute("""
    UPDATE locations SET
      address = %s,
      lat = %s, lng = %s
    WHERE id = %s
""", ('29 W 36th St, New York, NY 10018, USA', 40.750566, -73.985069, 2668))
conn.commit()
conn.close()
```

Don't touch the events themselves — their `sublocation` text is fine; once the location's address matches, the export filter will hide it automatically.

## Step 5: Re-export

```python
import sys; sys.path.insert(0, 'pipeline')
from db import create_connection
import exporter
conn = create_connection()
exporter.export_events(conn.cursor())
conn.close()
```

Re-run Step 1 and confirm the fixed locations have dropped off the list.

## Improving the matcher (only when needed)

If the scan flags a venue where the DB address and sublocation are the *same* address but written differently (e.g. word ordinals, hyphenated Queens numbers, suite/floor suffixes, leading venue names in the DB address), and the existing `_extract_street_address_loose` doesn't normalize them to the same form, the matcher itself needs a tweak — not the data. Look at `_extract_street_address_loose` / `sublocation_redundant_with_address` in `pipeline/processor.py`. Add a test case to `/tmp/test_loose.py` first, get it passing, then re-export.

Common normalization gaps that have been added historically: `Tenth` → `10th`, `5-52` → `552`, leading `<Venue Name>, <addr>`, trailing `Suite 605A` / `#1A` / `2nd floor`, `Broadway` / `Bowery` as standalone street names, trailing punctuation on `St.`, bare street names (`27th Street` vs `537 W 27th St`), the block form (`2nd Avenue between 90th & 91st Streets` vs `90th St & 2nd Ave`), and corridor ranges (`69th Street to 89th Street` vs `37th Ave & 79th St`).

Tests live in `pipeline/tests/test_processor.py` (`TestBareStreetNames`, `TestStreetBlockAndRangeForms`, `TestSublocationLooksLikeAddress`). Add the case there, get it passing, then re-export.

## Notes

- Don't try to clear the `sublocation` field on individual events as a fix — the raw text is load-bearing for the location matcher (Step 5b), and the export filter is the right place for the redundancy logic.
- Splitting one location row into per-branch rows (e.g. Gagosian Madison + Gagosian Chelsea) is a bigger task; leave the sublocation visible on the event until the location split happens.
- A venue that genuinely has two valid street addresses for the same building (corner location like Bar 13) doesn't need a fix — sublocation showing `121 University Pl` while the DB has `35 E 13th St` is a feature, not a bug.
