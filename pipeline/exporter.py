"""
Event export module.

Exports events from the database to JSON files for the website.
"""

import json
import os
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Bounding box for the "init" set (NYC core area)
INIT_LAT_RANGE = (40.672945, 40.735535)
INIT_LNG_RANGE = (-73.998595, -73.943125)


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


def export_events(cursor):
    """
    Export events from the events table to JSON files for the website.

    Creates:
    - events.init.json (core NYC area, 7-day window)
    - events.full.json (extended area and time range)
    - locations.init.json (locations for init events)
    - locations.full.json (locations for full events)
    """
    output_dir = os.path.join(SCRIPT_DIR, '..', 'src', 'data')
    os.makedirs(output_dir, exist_ok=True)

    current_date = datetime.now().date()
    future_limit_date = (datetime.now() + timedelta(days=90)).date()
    init_limit_date = (datetime.now() + timedelta(days=7)).date()

    # Get all events with their occurrences (exclude archived and suppressed events)
    # Events must have a location with coordinates to be exported
    # Exclude events from aggregator sources unless verified by a primary source
    cursor.execute("""
        SELECT e.id, e.name, e.short_name, e.description, e.emoji,
               e.location_name, e.sublocation,
               l.name as matched_location_name,
               l.lat, l.lng
        FROM events e
        JOIN locations l ON e.location_id = l.id
        LEFT JOIN websites w ON e.website_id = w.id
        WHERE l.lat IS NOT NULL AND l.lng IS NOT NULL
          AND e.archived = FALSE
          AND e.suppressed = FALSE
          AND (
            w.source_type = 'primary'
            OR w.id IS NULL
            OR EXISTS (
                SELECT 1 FROM event_sources es
                JOIN crawl_events ce ON es.crawl_event_id = ce.id
                JOIN crawl_results cr ON ce.crawl_result_id = cr.id
                JOIN websites w2 ON cr.website_id = w2.id
                WHERE es.event_id = e.id AND w2.source_type = 'primary'
            )
          )
    """)

    all_events = []
    for row in cursor.fetchall():
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

        # Get URLs
        cursor.execute("""
            SELECT url FROM event_urls WHERE event_id = %s ORDER BY sort_order
        """, (event_id,))
        urls = [r[0] for r in cursor.fetchall()]

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
            'name': row[1],
            'location': row[7] or row[5],  # matched_location_name or location_name
            'description': row[3],
            'emoji': row[4],
            'tags': tags,
            'lat': lat,
            'lng': lng,
            'occurrences': occurrences,
            'urls': urls,
        }
        if row[2]:  # short_name
            event['short_name'] = row[2]

        all_events.append(event)

    # Sort by first occurrence date
    all_events.sort(key=lambda e: e.get('occurrences', [[None]])[0][0] or '9999-99-99')

    # Split into init and full sets
    init_events = []
    full_events = []

    for event in all_events:
        lat = event.get('lat')
        lng = event.get('lng')
        is_in_bbox = (lat is not None and lng is not None and
                      INIT_LAT_RANGE[0] <= lat <= INIT_LAT_RANGE[1] and
                      INIT_LNG_RANGE[0] <= lng <= INIT_LNG_RANGE[1])

        first_occurrence_start_str = event.get('occurrences', [[None]])[0][0]
        is_in_init_timeframe = False
        if first_occurrence_start_str:
            try:
                start_date = datetime.strptime(first_occurrence_start_str, '%Y-%m-%d').date()
                if start_date < init_limit_date:
                    is_in_init_timeframe = True
            except (ValueError, TypeError):
                pass

        if is_in_bbox and is_in_init_timeframe:
            init_events.append(event)
        else:
            full_events.append(event)

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

        # Get website URL for this location
        cursor.execute("""
            SELECT w.base_url FROM website_locations wl
            JOIN websites w ON wl.website_id = w.id
            WHERE wl.location_id = %s
            LIMIT 1
        """, (location_id,))
        website_row = cursor.fetchone()

        loc = {
            'name': row[1],
            'lat': float(row[2]),
            'lng': float(row[3]),
        }
        if tags:
            loc['tags'] = tags
        if row[4]:
            loc['emoji'] = row[4]
        if row[5]:
            loc['alt_emoji'] = row[5]
        if row[6]:
            loc['address'] = row[6]
        if row[7]:
            loc['short_name'] = row[7]
        if row[8]:
            loc['very_short_name'] = row[8]
        if row[9]:
            loc['description'] = row[9]
        if website_row and website_row[0]:
            loc['website_url'] = website_row[0]
        all_locations.append(loc)

    init_locations = get_active_locations(init_events, all_locations)
    init_location_coords = set(
        (round(loc['lat'], 5), round(loc['lng'], 5)) for loc in init_locations
    )
    full_locations = [
        loc for loc in get_active_locations(full_events, all_locations)
        if (round(loc['lat'], 5), round(loc['lng'], 5)) not in init_location_coords
    ]

    # Write output files (compact JSON — no whitespace)
    for filename, data in [
        ('events.init.json', init_events),
        ('locations.init.json', init_locations),
        ('events.full.json', full_events),
        ('locations.full.json', full_locations),
    ]:
        with open(os.path.join(output_dir, filename), 'w', encoding='utf-8') as f:
            json.dump(data, f, separators=(',', ':'), ensure_ascii=False)

    print(f"  Exported {len(init_events)} init events, {len(full_events)} full events")
    print(f"  Exported {len(init_locations)} init locations, {len(full_locations)} full locations")

    return {
        'init_events': len(init_events),
        'full_events': len(full_events),
        'init_locations': len(init_locations),
        'full_locations': len(full_locations)
    }
