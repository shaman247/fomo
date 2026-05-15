# Fix Unmapped Events Command

Investigate and fix events that are not mapped to a location, or are mapped to a generic location.

## Background

Events need a location to appear correctly on the map. The pipeline's location matcher handles most cases, but some events end up:
- **Unmapped** (`location_id IS NULL`): The extracted `location_name` didn't match any known location
- **Generic** (`generic_location = TRUE`): Mapped to a neighborhood/borough instead of a specific venue

Common causes:
- **New venues** not yet in the locations table
- **Vague location names**: "Not specified", "TBD", zip codes, neighborhood names
- **Virtual/online events**: Zoom, webinar, virtual — no physical location
- **Out-of-area events**: Venues in Houston, Miami, Albany, etc. extracted from NYC-based org websites
- **Address-only locations**: Street addresses without venue names

## Step 1: Find Unmapped Events

```sql
SELECT e.id, e.name, e.location_id, e.location_name, w.name as website_name,
       CASE WHEN l.generic_location = 1 THEN 'GENERIC'
            WHEN e.location_id IS NULL THEN 'NO LOCATION' END as issue
FROM events e
LEFT JOIN locations l ON e.location_id = l.id
LEFT JOIN websites w ON e.website_id = w.id
WHERE e.suppressed = 0 AND e.archived = 0
  AND (e.location_id IS NULL OR l.generic_location = 1)
ORDER BY w.name, e.id;
```

Group by website to handle in batches — events from the same source often need the same fix.

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
UPDATE events SET suppressed = 1 WHERE id = {event_id};
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
