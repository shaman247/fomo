"""
Event deduplication and merging module.

Merges crawl_events into the final events table with deduplication.
"""

import re
from datetime import datetime, timedelta


def normalize_name_for_dedup(name):
    """Remove punctuation, underscores, and whitespace; convert to lowercase for comparison."""
    no_underscores = name.replace('_', '')
    no_punct = re.sub(r'[^\w\s]', '', no_underscores.strip().lower())
    normalized = re.sub(r'\s+', ' ', no_punct).strip()
    return normalized


def are_names_similar(name1, name2):
    """
    Check if two event names are similar enough to be considered duplicates.
    """
    norm1 = normalize_name_for_dedup(name1)
    norm2 = normalize_name_for_dedup(name2)

    if norm1 == norm2:
        return True

    # Check if one is a substring of the other (for prefix/suffix variations)
    if len(norm1) >= 5 and len(norm2) >= 5:
        if norm1 in norm2 or norm2 in norm1:
            return True

    return False


def merge_crawl_events(cursor, connection):
    """
    Merge new crawl_events into the final events table with deduplication.

    Deduplication logic:
    - Events are considered duplicates if they share the same lat/lng, similar name,
      and have an overlapping occurrence date.
    - For duplicates, we merge URLs and keep the shorter name / longer description.
    - Links to crawl_events are tracked in event_sources table.

    Returns:
        Tuple of (new_events_count, merged_count)
    """
    current_date = datetime.now().date()
    future_limit_date = (datetime.now() + timedelta(days=90)).date()

    # Get crawl_events that haven't been linked to any final event yet
    cursor.execute("""
        SELECT ce.id, ce.name, ce.short_name, ce.description, ce.emoji,
               ce.location_name, ce.sublocation, ce.lat, ce.lng, ce.url,
               cr.website_id
        FROM crawl_events ce
        JOIN crawl_results cr ON ce.crawl_result_id = cr.id
        LEFT JOIN event_sources es ON ce.id = es.crawl_event_id
        WHERE cr.status = 'processed'
          AND es.id IS NULL
    """)

    new_crawl_events = cursor.fetchall()
    print(f"  Found {len(new_crawl_events)} unprocessed crawl_events")

    if not new_crawl_events:
        return 0, 0

    # Build a lookup of existing events by (lat, lng, first_start_date) for efficient matching
    cursor.execute("""
        SELECT e.id, e.name, e.lat, e.lng,
               (SELECT MIN(eo.start_date) FROM event_occurrences eo WHERE eo.event_id = e.id) as first_date
        FROM events e
        WHERE e.lat IS NOT NULL AND e.lng IS NOT NULL
    """)
    existing_events = {}
    for row in cursor.fetchall():
        event_id, name, lat, lng, first_date = row
        if lat is not None and lng is not None and first_date is not None:
            key = (round(float(lat), 5), round(float(lng), 5), str(first_date))
            if key not in existing_events:
                existing_events[key] = []
            existing_events[key].append({'id': event_id, 'name': name})

    new_events_count = 0
    merged_count = 0

    for ce_row in new_crawl_events:
        ce_id, name, short_name, description, emoji, location_name, sublocation, lat, lng, url, website_id = ce_row

        if not name:
            continue

        # Get occurrences for this crawl event
        cursor.execute("""
            SELECT start_date, start_time, end_date, end_time, sort_order
            FROM crawl_event_occurrences
            WHERE crawl_event_id = %s
            ORDER BY start_date, sort_order
        """, (ce_id,))
        occurrences = cursor.fetchall()

        # Filter occurrences by date range
        valid_occurrences = []
        for occ in occurrences:
            start_date = occ[0]
            if start_date and current_date <= start_date <= future_limit_date:
                valid_occurrences.append(occ)

        if not valid_occurrences:
            # No valid future occurrences, skip
            continue

        first_start_date = valid_occurrences[0][0]

        # Get tags for this crawl event
        cursor.execute("SELECT tag FROM crawl_event_tags WHERE crawl_event_id = %s", (ce_id,))
        tags = [row[0] for row in cursor.fetchall()]

        # Check for duplicate in existing events
        matched_event_id = None
        if lat is not None and lng is not None:
            key = (round(float(lat), 5), round(float(lng), 5), str(first_start_date))
            if key in existing_events:
                for existing in existing_events[key]:
                    if are_names_similar(name, existing['name']):
                        matched_event_id = existing['id']
                        break

        if matched_event_id:
            # Merge with existing event
            # Add URL if not already present
            if url:
                cursor.execute(
                    "SELECT id FROM event_urls WHERE event_id = %s AND url = %s",
                    (matched_event_id, url)
                )
                if not cursor.fetchone():
                    cursor.execute(
                        "INSERT INTO event_urls (event_id, url, sort_order) VALUES (%s, %s, 99)",
                        (matched_event_id, url[:2000])
                    )

            # Link crawl_event to existing event
            cursor.execute(
                "INSERT INTO event_sources (event_id, crawl_event_id, is_primary) VALUES (%s, %s, FALSE)",
                (matched_event_id, ce_id)
            )
            merged_count += 1

        else:
            # Create new event
            cursor.execute("""
                INSERT INTO events (name, short_name, description, emoji, location_id, location_name,
                                   sublocation, lat, lng, website_id)
                VALUES (%s, %s, %s, %s, NULL, %s, %s, %s, %s, %s)
            """, (
                name[:500],
                short_name[:255] if short_name else None,
                description,
                emoji[:10] if emoji else None,
                location_name[:255] if location_name else None,
                sublocation[:255] if sublocation else None,
                lat,
                lng,
                website_id
            ))
            new_event_id = cursor.lastrowid

            # Try to match location_id from locations table
            if lat is not None and lng is not None:
                cursor.execute("""
                    SELECT id FROM locations
                    WHERE ROUND(lat, 5) = ROUND(%s, 5) AND ROUND(lng, 5) = ROUND(%s, 5)
                    LIMIT 1
                """, (lat, lng))
                loc_match = cursor.fetchone()
                if loc_match:
                    cursor.execute("UPDATE events SET location_id = %s WHERE id = %s",
                                 (loc_match[0], new_event_id))

            # Add occurrences
            for i, occ in enumerate(valid_occurrences):
                cursor.execute("""
                    INSERT INTO event_occurrences (event_id, start_date, start_time, end_date, end_time, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (new_event_id, occ[0], occ[1], occ[2], occ[3], i))

            # Add URL
            if url:
                cursor.execute(
                    "INSERT INTO event_urls (event_id, url, sort_order) VALUES (%s, %s, 0)",
                    (new_event_id, url[:2000])
                )

            # Add tags
            for tag in tags:
                if tag:
                    # Get or create tag
                    cursor.execute("SELECT id FROM tags WHERE name = %s", (tag[:100],))
                    tag_row = cursor.fetchone()
                    if tag_row:
                        tag_id = tag_row[0]
                    else:
                        cursor.execute("INSERT INTO tags (name) VALUES (%s)", (tag[:100],))
                        tag_id = cursor.lastrowid

                    # Link tag to event
                    cursor.execute(
                        "INSERT IGNORE INTO event_tags (event_id, tag_id) VALUES (%s, %s)",
                        (new_event_id, tag_id)
                    )

            # Link crawl_event to new event
            cursor.execute(
                "INSERT INTO event_sources (event_id, crawl_event_id, is_primary) VALUES (%s, %s, TRUE)",
                (new_event_id, ce_id)
            )

            # Add to existing_events lookup for future dedup within this batch
            if lat is not None and lng is not None:
                key = (round(float(lat), 5), round(float(lng), 5), str(first_start_date))
                if key not in existing_events:
                    existing_events[key] = []
                existing_events[key].append({'id': new_event_id, 'name': name})

            new_events_count += 1

    connection.commit()
    print(f"  Added {new_events_count} new events, merged {merged_count} duplicates")
    return new_events_count, merged_count
