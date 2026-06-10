"""
Event export module.

Exports events from the database to JSON files for the website.
"""

import json
import os
import sys
from datetime import datetime, timedelta

import db
from constants import FUTURE_WINDOW_DAYS
from processor import sublocation_redundant_with_address

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Number of single-day chunks to emit (today, +1, +2, +3). Everything else
# goes into the "remainder" chunk. Frontend loads the chunk matching its
# current date in Phase 1 and the rest in Phase 2.
NUM_DAY_CHUNKS = 4


def classify_event_sections(cursor, connection):
    """Classify events into sections (Events/Ongoing) based on occurrence patterns.

    Events with an existing section value are left unchanged (supports manual overrides).
    """
    cursor.execute("""
        SELECT e.id
        FROM events e
        WHERE e.section IS NULL
          AND e.archived = FALSE
          AND e.suppressed = FALSE
    """)
    event_ids = [row[0] for row in cursor.fetchall()]

    if not event_ids:
        print("  No events need section classification")
        return

    classified = 0
    for event_id in event_ids:
        cursor.execute("""
            SELECT start_date, end_date
            FROM event_occurrences
            WHERE event_id = %s
            ORDER BY start_date
        """, (event_id,))
        occurrences = cursor.fetchall()

        if not occurrences:
            continue

        section = 'Events'

        # Check if any single occurrence spans > 14 days
        for start_date, end_date in occurrences:
            if start_date and end_date and (end_date - start_date).days > 14:
                section = 'Ongoing'
                break

        # Check if many occurrences spread over > 21 days
        if section == 'Events' and len(occurrences) > 4:
            first_date = occurrences[0][0]
            last_date = occurrences[-1][0]
            if first_date and last_date and (last_date - first_date).days > 21:
                section = 'Ongoing'

        cursor.execute("UPDATE events SET section = %s WHERE id = %s", (section, event_id))
        classified += 1

    connection.commit()
    cursor.execute("SELECT COUNT(*) FROM events WHERE section = 'Ongoing' AND archived = FALSE AND suppressed = FALSE")
    ongoing_count = cursor.fetchone()[0]
    print(f"  Classified {classified} events ({ongoing_count} ongoing)")


def get_active_locations(events, all_locations):
    """Get locations that have events at their coordinates."""
    active_coords = set(
        (round(event['lat'], 5), round(event['lng'], 5))
        for event in events if event.get('lat') and event.get('lng')
    )
    return [
        loc for loc in all_locations
        if loc.get('lat') is not None and loc.get('lng') is not None
        and (round(loc['lat'], 5), round(loc['lng'], 5)) in active_coords
    ]


def _occurrence_dates(occurrences):
    """Yield (start_date, end_date) for each occurrence in an exported event.

    Mirrors the export shape: occurrence is a list [start_str, start_time, end_str, end_time].
    Skips entries with unparseable dates.
    """
    for occ in occurrences:
        start_str = occ[0]
        end_str = occ[2] if len(occ) > 2 else None
        if not start_str:
            continue
        try:
            start = datetime.strptime(start_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            continue
        end = start
        if end_str:
            try:
                end = datetime.strptime(end_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                end = start
        yield start, end


def _event_covers_day(event, day):
    """True if any occurrence of the event spans `day`."""
    for start, end in _occurrence_dates(event.get('occurrences', [])):
        if start <= day <= end:
            return True
    return False


def _event_extends_past(event, day):
    """True if any occurrence of the event ends after `day`."""
    for _, end in _occurrence_dates(event.get('occurrences', [])):
        if end > day:
            return True
    return False


def _load_parent_map(cursor):
    """Map of {child_website_id: parent_website_id} for organizer attribution.

    `websites.parent_website_id` points at the organizer root a site belongs to
    (e.g. each nycgovparks.org park page -> the NYC Parks root site).
    """
    cursor.execute("SELECT id, parent_website_id FROM websites WHERE parent_website_id IS NOT NULL")
    return {row[0]: row[1] for row in cursor.fetchall()}


def _resolve_root(website_id, parent_map):
    """Resolve a website to its organizer root (parent chain, else itself).

    The hierarchy is single-level by convention (enforced by
    scripts/backfill_parent_websites.py --audit), but chains are followed
    defensively with a depth cap and cycle guard so bad data can never make
    the export loop or crash — on a cycle the original id is returned as-is.
    """
    seen = set()
    current = website_id
    for _ in range(10):
        parent = parent_map.get(current)
        if parent is None:
            return current
        if parent in seen:
            return website_id  # cycle — audit will flag it
        seen.add(current)
        current = parent
    return current


def export_events(cursor):
    """
    Export events from the events table to JSON files for the website.

    Splits events into per-day chunks for fast frontend startup:
    - events.day0.json … events.day{NUM_DAY_CHUNKS-1}.json — events occurring on
      that calendar day (an event with multiple occurrences appears in every
      chunk it touches; the frontend dedupes by id)
    - events.remainder.json — events with at least one occurrence past the last
      day chunk (within the 90-day future window)
    - locations.{chunk}.json — locations referenced by events in that chunk
    - manifest.json — { days: ["YYYY-MM-DD", …] } so the frontend can pick the
      chunk matching the user's current date
    """
    output_dir = os.path.join(SCRIPT_DIR, '..', 'src', 'data')
    os.makedirs(output_dir, exist_ok=True)

    current_date = datetime.now().date()
    future_limit_date = (datetime.now() + timedelta(days=FUTURE_WINDOW_DAYS)).date()
    day_dates = [current_date + timedelta(days=i) for i in range(NUM_DAY_CHUNKS)]
    last_day = day_dates[-1]

    # Organizer roots: a website with parent_website_id set belongs to that
    # parent organizer (e.g. 133 nycgovparks.org park pages -> one NYC Parks
    # root). All organizer attribution below works on resolved roots.
    parent_map = _load_parent_map(cursor)

    # Build set of (root_website_id, location_id) pairs where the website (or
    # any of its sibling sites under the same root) IS the venue. Tested at
    # root granularity because the displayed organizer chip is the root.
    # NOTE: temporarily unused — the organizer-attribution gate below is disabled
    # for debugging (every event gets an organizer_id). Kept for an easy revert.
    cursor.execute("SELECT website_id, location_id FROM website_locations")
    venue_links = set((_resolve_root(row[0], parent_map), row[1]) for row in cursor.fetchall())

    # Get all events with their occurrences (exclude archived and suppressed events)
    # Events must have a location with coordinates to be exported.
    #
    # Aggregator trust gate: enabled aggregators (RA, Eventbrite, Partiful, …) are
    # trusted discovery feeds — keep their events.
    cursor.execute("""
        SELECT e.id, e.name, e.short_name, e.description, e.emoji,
               e.location_name, e.sublocation,
               l.name as matched_location_name,
               l.lat, l.lng, e.section, e.website_id, e.location_id,
               l.address
        FROM events e
        JOIN locations l ON e.location_id = l.id
        LEFT JOIN websites w ON e.website_id = w.id
        WHERE l.lat IS NOT NULL AND l.lng IS NOT NULL
          AND e.archived = FALSE
          AND e.suppressed = FALSE
          AND (
            w.id IS NULL
            OR w.source_type = 'primary'
            OR w.disabled = FALSE
            OR EXISTS (
                SELECT 1 FROM event_sources es
                JOIN crawl_events ce ON es.crawl_event_id = ce.id
                JOIN crawl_results cr ON ce.crawl_result_id = cr.id
                JOIN websites w2 ON cr.website_id = w2.id
                WHERE es.event_id = e.id AND w2.source_type = 'primary'
            )
          )
    """)

    event_rows = cursor.fetchall()

    # Prefetch the distinct source websites for every event (merged events can
    # carry several). Used to attribute multiple organizer chips per event. The
    # event's own website_id (the merger's primary) is added first below.
    source_sites_by_event = {}
    cursor.execute("""
        SELECT es.event_id, cr.website_id
        FROM event_sources es
        JOIN crawl_events ce ON es.crawl_event_id = ce.id
        JOIN crawl_results cr ON ce.crawl_result_id = cr.id
        WHERE cr.website_id IS NOT NULL
    """)
    for ev_id, src_wid in cursor.fetchall():
        source_sites_by_event.setdefault(ev_id, set()).add(src_wid)

    all_events = []
    descriptions_by_id = {}  # event_id -> description; shipped as desc companions
    referenced_organizer_ids = set()  # organizer roots emitted on any exported event
    for row in event_rows:
        event_id = row[0]

        # Get occurrences
        cursor.execute("""
            SELECT start_date, start_time, end_date, end_time
            FROM event_occurrences
            WHERE event_id = %s
            ORDER BY start_date, start_time
        """, (event_id,))
        occurrences = []
        for occ in cursor.fetchall():
            start_date = occ[0]
            end_date = occ[2] if occ[2] else start_date
            # Only include occurrences within the active date range
            if start_date and start_date <= future_limit_date and end_date >= current_date:
                occurrences.append([
                    str(occ[0]) if occ[0] else None,
                    occ[1],
                    str(occ[2]) if occ[2] else None,
                    occ[3]
                ])

        if not occurrences:
            continue

        # Get URLs — events without any URL are not shown on fomo.nyc
        cursor.execute("""
            SELECT url FROM event_urls WHERE event_id = %s ORDER BY sort_order
        """, (event_id,))
        urls = [r[0] for r in cursor.fetchall()]
        if not urls:
            continue

        # Get tags
        cursor.execute("""
            SELECT t.name FROM event_tags et JOIN tags t ON et.tag_id = t.id WHERE et.event_id = %s
        """, (event_id,))
        tags = [r[0] for r in cursor.fetchall()]

        # Use location coordinates (events no longer have their own coordinates)
        lat = float(row[8]) if row[8] is not None else None
        lng = float(row[9]) if row[9] is not None else None

        # Skip events without coordinates (shouldn't happen due to JOIN, but safety check)
        if lat is None or lng is None:
            continue

        event = {
            'id': event_id,
            'name': row[1],
            'location': row[7] or row[5],  # matched_location_name or location_name
            'emoji': row[4],
            'tags': tags,
            'lat': lat,
            'lng': lng,
            'occurrences': occurrences,
            'urls': urls,
        }
        # description is shipped in a companion events.<chunk>.desc.json (loaded
        # after the markers render) — see _write_chunk_files. display_tags
        # (leaf-only tags for popups) is now derived client-side from the tag
        # hierarchy the frontend already loads, so neither is emitted inline.
        if row[3]:
            descriptions_by_id[event_id] = row[3]
        if row[2]:  # short_name
            event['short_name'] = row[2]

        sublocation = row[6]
        if sublocation and not sublocation_redundant_with_address(sublocation, row[13]):
            event['sublocation'] = sublocation

        section = row[10]
        if section and section != 'Events':
            event['section'] = section

        # Organizer attribution: a merged event can come from several sources.
        # Each source website resolves to its organizer ROOT (parent_website_id
        # chain, else itself), so sibling sites of one org (e.g. several BPCA
        # park pages) collapse into a single organizer id. Primary's root
        # first. The frontend renders one chip per organizer that resolves in
        # organizers.json — aggregators and unknown sources are dropped there.
        #
        # TEMP (debugging organizer attribution): the primary website is included
        # even when it IS the venue itself. To restore production behavior
        # (external organizers only), gate the primary on venue_links:
        #     location_id = row[12]
        #     primary_root = _resolve_root(website_id, parent_map)
        #     primary = primary_root if (primary_root, location_id) not in venue_links else None
        website_id = row[11]
        organizer_ids = []
        if website_id:
            organizer_ids.append(_resolve_root(website_id, parent_map))  # merger's primary, first
        for src_wid in sorted(source_sites_by_event.get(event_id, set())):
            root = _resolve_root(src_wid, parent_map)
            if root not in organizer_ids:
                organizer_ids.append(root)
        if organizer_ids:
            event['organizer_ids'] = organizer_ids
            referenced_organizer_ids.update(organizer_ids)

        all_events.append(event)

    # Sort by first occurrence date
    all_events.sort(key=lambda e: e.get('occurrences', [[None]])[0][0] or '9999-99-99')

    # Split events into per-day chunks plus a remainder. Events with multiple
    # occurrences spanning several days appear in each matching chunk so the
    # frontend can load just one chunk and have everything for that day.
    day_event_chunks = [[] for _ in range(NUM_DAY_CHUNKS)]
    remainder_events = []

    for event in all_events:
        for i, day in enumerate(day_dates):
            if _event_covers_day(event, day):
                day_event_chunks[i].append(event)
        if _event_extends_past(event, last_day):
            remainder_events.append(event)

    # Load locations from database
    cursor.execute("""
        SELECT id, name, lat, lng, emoji, alt_emoji, address, short_name, very_short_name, description
        FROM locations
        WHERE lat IS NOT NULL AND lng IS NOT NULL
    """)
    all_locations = []
    for row in cursor.fetchall():
        location_id = row[0]

        # Get tags for this location
        cursor.execute("""
            SELECT t.name FROM location_tags lt
            JOIN tags t ON lt.tag_id = t.id
            WHERE lt.location_id = %s
        """, (location_id,))
        tags = [r[0] for r in cursor.fetchall()]

        # Get website URLs for this location (primary first, then secondaries).
        # Multiple URLs are exported as an array — locations can have e.g. both
        # an official directory page and a venue's own website.
        cursor.execute("""
            SELECT COALESCE(wl.url, w.base_url) as url FROM website_locations wl
            JOIN websites w ON wl.website_id = w.id
            WHERE wl.location_id = %s
            ORDER BY wl.is_primary DESC, wl.id
        """, (location_id,))
        website_urls = []
        seen_urls = set()
        for r in cursor.fetchall():
            url = r[0]
            if url and url not in seen_urls:
                website_urls.append(url)
                seen_urls.add(url)

        loc = {
            'name': row[1],
            'lat': float(row[2]),
            'lng': float(row[3]),
        }
        if tags:
            loc['tags'] = tags  # display_tags derived client-side from the hierarchy
        if row[4]:
            loc['emoji'] = row[4]
        # alt_emoji is only a Windows fallback for flag emoji (which render as
        # letter boxes there) — pointless to ship otherwise.
        if row[5] and db.is_country_flag_emoji(row[4]):
            loc['alt_emoji'] = row[5]
        if row[6]:
            loc['address'] = row[6]
        if row[7]:
            loc['short_name'] = row[7]
        if row[8]:
            loc['very_short_name'] = row[8]
        if row[9]:
            loc['description'] = row[9]
        if website_urls:
            # Keep website_url as the primary for backwards-compat; full list in website_urls.
            loc['website_url'] = website_urls[0]
            if len(website_urls) > 1:
                loc['website_urls'] = website_urls
        all_locations.append(loc)

    # Locations per chunk include all venues referenced by that chunk's events.
    # Recurring venues will appear in multiple files; the frontend dedupes by
    # lat/lng key on merge.
    day_location_chunks = [get_active_locations(events, all_locations) for events in day_event_chunks]
    remainder_locations = get_active_locations(remainder_events, all_locations)

    # Remove old init/full files left over from the previous export scheme so
    # downstream steps (FTP upload tracking) don't keep shipping stale data.
    for stale in ('events.init.json', 'events.full.json',
                  'locations.init.json', 'locations.full.json'):
        stale_path = os.path.join(output_dir, stale)
        if os.path.exists(stale_path):
            os.remove(stale_path)

    # Description companion for a chunk: {event_id: description} for that chunk's
    # events. Loaded by the frontend AFTER the markers render (descriptions are
    # the single largest, worst-compressing field and aren't needed for the map
    # or the initial paint), then merged into events + the search index.
    def _desc_map(events):
        return {e['id']: descriptions_by_id[e['id']]
                for e in events if e['id'] in descriptions_by_id}

    files_to_write = []
    for i in range(NUM_DAY_CHUNKS):
        files_to_write.append((f'events.day{i}.json', day_event_chunks[i]))
        files_to_write.append((f'events.day{i}.desc.json', _desc_map(day_event_chunks[i])))
        files_to_write.append((f'locations.day{i}.json', day_location_chunks[i]))
    files_to_write.append(('events.remainder.json', remainder_events))
    files_to_write.append(('events.remainder.desc.json', _desc_map(remainder_events)))
    files_to_write.append(('locations.remainder.json', remainder_locations))
    files_to_write.append(('manifest.json', {'days': [d.isoformat() for d in day_dates]}))

    for filename, data in files_to_write:
        with open(os.path.join(output_dir, filename), 'w', encoding='utf-8') as f:
            json.dump(data, f, separators=(',', ':'), ensure_ascii=False)

    total_event_placements = sum(len(c) for c in day_event_chunks) + len(remainder_events)
    unique_event_count = len({e['id'] for e in all_events})
    print(f"  Exported {unique_event_count} unique events across {NUM_DAY_CHUNKS} day chunks + remainder")
    for i, day in enumerate(day_dates):
        print(f"    day{i} ({day.isoformat()}): {len(day_event_chunks[i])} events, {len(day_location_chunks[i])} locations")
    print(f"    remainder: {len(remainder_events)} events, {len(remainder_locations)} locations")
    print(f"    placements (sum across chunks, with overlap): {total_event_placements}")

    return {
        'unique_events': unique_event_count,
        'placements': total_event_placements,
        'day_event_counts': [len(c) for c in day_event_chunks],
        'remainder_events': len(remainder_events),
        'organizer_root_ids': referenced_organizer_ids,
    }


def export_tag_hierarchy(cursor):
    """Export tag hierarchy from database to JSON for frontend consumption.

    Creates src/data/tag_hierarchy.json with curated tags and their parent relationships.
    Keywords are NOT included — the frontend infers keyword status by checking whether
    an event's tag is in the curated set.
    """
    output_dir = os.path.join(SCRIPT_DIR, '..', 'src', 'data')
    os.makedirs(output_dir, exist_ok=True)

    tags_list = db.get_tag_hierarchy_for_export(cursor)

    # Add aliases to each tag entry
    aliases_by_tag = db.get_tag_aliases_for_export(cursor)
    for tag_entry in tags_list:
        aliases = aliases_by_tag.get(tag_entry['name'])
        if aliases:
            tag_entry['aliases'] = aliases

    output = {'tags': tags_list}

    output_path = os.path.join(output_dir, 'tag_hierarchy.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, separators=(',', ':'), ensure_ascii=False)

    print(f"  Exported {len(tags_list)} tags to tag_hierarchy.json")

    # Warn (don't fail) on flag-emoji locations/tags lacking an alt_emoji — these
    # render as letter boxes on Windows. Catches AI-curated tags that picked up a
    # flag emoji since the last publish. See scripts/check_flag_emoji_alt.py.
    try:
        scripts_dir = os.path.join(SCRIPT_DIR, '..', 'scripts')
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from check_flag_emoji_alt import find_flag_emoji_without_alt
        problems = find_flag_emoji_without_alt(cursor)
        if problems:
            print(f"  WARNING: {len(problems)} flag-emoji record(s) missing alt_emoji "
                  f"(won't render on Windows):")
            for p in problems:
                print(f"    {p['kind']} #{p['id']} {p['emoji']}  {p['name']}")
    except Exception as e:
        print(f"  (flag-emoji alt check skipped: {e})")


def export_organizers(cursor, organizer_ids=None):
    """Export organizers (root websites) referenced by exported events to JSON.

    Creates src/data/organizers.json as a map of {id: {name, url, emoji, description}}.
    `organizer_ids` is the `organizer_root_ids` set returned by export_events()
    — exactly the organizer roots emitted on exported events, so the map can't
    miss secondary-source-only organizers and doesn't depend on the disabled
    flag. When None (ad-hoc callers), the set is recomputed from active events.
    """
    output_dir = os.path.join(SCRIPT_DIR, '..', 'src', 'data')
    os.makedirs(output_dir, exist_ok=True)

    if organizer_ids is None:
        # Recompute roots from active events' primary + source websites.
        parent_map = _load_parent_map(cursor)
        organizer_ids = set()
        cursor.execute("""
            SELECT DISTINCT e.website_id FROM events e
            WHERE e.website_id IS NOT NULL
              AND e.archived = FALSE AND e.suppressed = FALSE
        """)
        wids = [row[0] for row in cursor.fetchall()]
        cursor.execute("""
            SELECT DISTINCT cr.website_id
            FROM event_sources es
            JOIN crawl_events ce ON es.crawl_event_id = ce.id
            JOIN crawl_results cr ON ce.crawl_result_id = cr.id
            JOIN events e ON es.event_id = e.id
            WHERE cr.website_id IS NOT NULL
              AND e.archived = FALSE AND e.suppressed = FALSE
        """)
        wids += [row[0] for row in cursor.fetchall()]
        organizer_ids = {_resolve_root(w, parent_map) for w in wids}

    if not organizer_ids:
        organizers = {}
        output_path = os.path.join(output_dir, 'organizers.json')
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(organizers, f, separators=(',', ':'), ensure_ascii=False)
        print("  Exported 0 organizers to organizers.json")
        return

    # Aggregator sources (platforms / re-listers like Eventbrite, Partiful, RA)
    # are NOT real organizers, so they're excluded here — that hides their
    # organizer chip and makes them non-filterable on the frontend (the
    # isKnownOrganizerTag guard suppresses any organizer not in this map).
    placeholders = ','.join(['%s'] * len(organizer_ids))
    cursor.execute(f"""
        SELECT w.id, w.name, w.base_url, w.description, w.emoji
        FROM websites w
        WHERE w.source_type <> 'aggregator'
          AND w.id IN ({placeholders})
        ORDER BY w.name
    """, tuple(organizer_ids))

    organizers = {}
    for row in cursor.fetchall():
        org = {'name': row[1]}
        if row[2]:
            org['url'] = row[2]
        if row[3]:
            org['description'] = row[3]
        if row[4]:
            org['emoji'] = row[4]
        organizers[str(row[0])] = org

    output_path = os.path.join(output_dir, 'organizers.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(organizers, f, separators=(',', ':'), ensure_ascii=False)

    print(f"  Exported {len(organizers)} organizers to organizers.json")
