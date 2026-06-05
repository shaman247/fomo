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

## Step 1: Find candidates

Run the scan from a Python script — the matcher logic lives in `pipeline/processor.py`:

```python
import sys; sys.path.insert(0, 'pipeline')
import re
from collections import defaultdict
from db import create_connection
from processor import _extract_street_address_loose, sublocation_redundant_with_address

# A "real" address-style sublocation starts with a number AND contains a
# street-type token. Plain sub-venue values like "Studio B" or "5th Floor"
# don't match this pattern and are skipped.
STARTS_NUM = re.compile(r'^\s*\d+')
STREET_TYPE = re.compile(
    r'\b(st|ave|blvd|dr|rd|pl|ct|ln|pkwy|hwy|street|avenue|boulevard|drive|'
    r'road|place|court|lane|parkway|highway|broadway|bowery|way|sq|square|'
    r'terrace|tpke|turnpike)\b\.?', re.IGNORECASE)

def looks_like_street_address(s):
    return bool(s and STARTS_NUM.match(s) and STREET_TYPE.search(s))

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
""")

by_loc = defaultdict(list)
for r in cur.fetchall():
    if not looks_like_street_address(r['sublocation']):
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

1. **Skip if `generic_location = 1`** — the sublocation is meant to give the specific spot within a neighborhood/park; that's correct.
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

If the scan flags a venue where the DB address and sublocation are the *same* address but written differently (e.g. word ordinals, hyphenated Queens numbers, suite/floor suffixes, leading venue names in the DB address), and the existing `_extract_street_address_loose` doesn't normalize them to the same form, the matcher itself needs a tweak — not the data. Look at `pipeline/processor.py:744-807`. Add a test case to `/tmp/test_loose.py` first, get it passing, then re-export.

Common normalization gaps that have been added historically: `Tenth` → `10th`, `5-52` → `552`, leading `<Venue Name>, <addr>`, trailing `Suite 605A` / `#1A` / `2nd floor`, `Broadway` / `Bowery` as standalone street names, trailing punctuation on `St.`.

## Notes

- Don't try to clear the `sublocation` field on individual events as a fix — the raw text is load-bearing for the location matcher (Step 5b), and the export filter is the right place for the redundancy logic.
- Splitting one location row into per-branch rows (e.g. Gagosian Madison + Gagosian Chelsea) is a bigger task; leave the sublocation visible on the event until the location split happens.
- A venue that genuinely has two valid street addresses for the same building (corner location like Bar 13) doesn't need a fix — sublocation showing `121 University Pl` while the DB has `35 E 13th St` is a feature, not a bug.
