# Fix Unmapped Events Command

Investigate and fix events that are not mapped to a location, or are mapped to a generic location.

## Background

Events need a location to appear correctly on the map. The pipeline's location matcher handles most cases, but some events end up:
- **Unmapped** (`location_id IS NULL`): The extracted `location_name` didn't match any known location
- **Generic** (`generic_location = TRUE`): Mapped to a neighborhood/borough instead of a specific venue
- **Mismatched** (mapped to a specific venue, but `location_name` doesn't match the venue's name/address/alt names): The extracted location is more precise than — or just different from — the mapped venue. Usually the venue exists but isn't in the locations table yet, or the location matcher fell back to the website's tied default. Subset of these flow up via Step 1 alongside Generic.

Common causes:
- **New venues** not yet in the locations table
- **Vague location names**: "Not specified", "TBD", zip codes, neighborhood names
- **Virtual/online events**: Zoom, webinar, virtual — no physical location
- **Out-of-area events**: Venues in Houston, Miami, Albany, etc. extracted from NYC-based org websites
- **Address-only locations**: Street addresses without venue names

## Step 1: Find Unmapped Events

```bash
./venv/bin/python scripts/find_unmapped_events.py --count
./venv/bin/python scripts/find_unmapped_events.py --limit 50
./venv/bin/python scripts/find_unmapped_events.py --issue MISMATCHED
./venv/bin/python scripts/find_unmapped_events.py --website "NY Tech Week"
./venv/bin/python scripts/find_unmapped_events.py --suggest-fixes --limit 100   # also re-run get_location_id and show where it would route differently
```

The script reuses `pipeline/processor.py:_normalize_location_name` so apostrophes, `&` / `+` → `and`, diacritics, and borough/state suffixes are all handled in lockstep with the pipeline matcher. No SQL drift.

Output is grouped by issue class then website. Pass `--offset N` to paginate.

### Issue classes

- **NO_LOCATION** — `events.location_id IS NULL`. The matcher couldn't place these. `--suggest-fixes` will report when the current matcher *would* now find a location (e.g. because we added the venue since the event was first crawled).
- **GENERIC** — mapped to a neighborhood/borough/region placeholder (`locations.generic_location = 1`). The event is on the map but pinned to the centroid; a specific venue would be better.
- **MISMATCHED** — mapped to a specific venue, but the normalized `location_name` doesn't substring-match the venue's name / address / alternate names. Subset of these are real mis-maps (AI extracted a specific venue but the matcher fell back to the website's tied default); others are sublocation references (e.g. `"The Spare Room"` is the bar area inside `"The Gutter"` bowling alley) where the reviewer just needs to move the descriptor into `events.sublocation` or add a website-scoped alt name.

### Tuning the skip list

The script ships with a `SKIP_LOCATION_NAMES` set covering common vague labels (`tba`, `online`, `the rooftop`, etc.), chain brand names that map per-theater (`amc theatres`), and `% between %` street-intersection patterns. If a new venue's events keep surfacing because of a generic location_name that's correctly mapped, extend that set rather than adding hundreds of website-scoped alts.

## Step 2: Categorize Each Event

Work through events grouped by website. For each, determine the appropriate action:

### Category A: Identifiable venue — match or add location

The `location_name` refers to a real venue. Search the DB first:

```sql
SELECT id, name, address FROM locations
WHERE name LIKE '%venue_name%' OR address LIKE '%venue_name%';
```

If found, assign it. If not, research the venue (check the source website, search the web), then add it via `scripts/add_locations.php`. See `/add-locations` for the full workflow.

### Category B: Virtual/online event — map to org's home location

Virtual events should map to the hosting organization's home location, not to a generic "Manhattan" fallback. Check `website_locations` for the org's linked venue:

```sql
SELECT l.id, l.name FROM website_locations wl
JOIN locations l ON wl.location_id = l.id
WHERE wl.website_id = {website_id};
```

If no `website_locations` link exists, use a reasonable fallback (the org's known office, or a neighborhood generic as last resort).

### Category C: Vague/TBD location — use generic fallback

Events with "Not specified", "TBD", "Location not specified yet", or neighborhood-only locations should map to the appropriate generic neighborhood/borough location:

```sql
SELECT id, name FROM locations WHERE generic_location = 1 AND name LIKE '%neighborhood%';
```

Common generics: Manhattan (2211), Brooklyn (2208), Queens (2209), Bronx (2212), Staten Island (2210), Jersey City (2695), Hoboken (2694), and neighborhoods like Upper East Side, SoHo, East Village, etc.

### Category D: Out-of-area event — suppress

If the event is genuinely outside the coverage area (NYC metro, Long Island, Westchester, Hudson Valley, Northern NJ, Southern CT), suppress it:

```sql
UPDATE events SET suppressed = 1, reviewed = 1 WHERE id = {event_id};
```

Examples: Cinema Tropical events at Houston's MFAH, PEN America events in Miami, Albany career fairs. Note that NJ (including Raritan, Paterson), Long Island, Hudson Valley, and Westchester ARE in scope.

### Category E: Not an event — suppress

Some extracted items aren't events: ticket ordering deadlines, private weddings, government licensing board meetings. Suppress these.

## Guidelines

- **Suppress only as a last resort.** Most events can be mapped to a specific venue, or to a generic neighborhood/borough location as a fallback.
- **Never fabricate addresses.** If you can't find a venue's address, search the web or check the source website. Don't guess.
- **Research before mapping.** Visit Hudson County events should map to Hudson County venues, not Manhattan. NYC Service events with zip codes should map to the corresponding neighborhood.
- **Groupmuse house concerts** with neighborhood names (e.g., "Loft", "Brooklyn home", "Midtown South") are correctly mapped to their neighborhood generics — don't suppress them.
- **Check `website_locations` links.** If an org's events are defaulting to a wrong venue (e.g., AAA events going to Good Shepherd Auditorium), the `website_locations` link may be incorrect — fix or remove it.
- **Watch for duplicate coordinates.** After adding locations, check that no two locations share exact lat/lng, as this causes UI issues. If they do, perturb one slightly or merge if they're the same place.

## Step 3: Verify

After making changes, verify the counts improved:

```sql
SELECT
  COUNT(CASE WHEN e.location_id IS NULL THEN 1 END) as unmapped,
  COUNT(CASE WHEN l.generic_location = 1 THEN 1 END) as generic
FROM events e
LEFT JOIN locations l ON e.location_id = l.id
WHERE e.suppressed = 0 AND e.archived = 0;
```

## Step 4: Re-export

After fixing, re-export so changes are reflected on the live site:

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
