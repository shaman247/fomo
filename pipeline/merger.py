"""
Event deduplication and merging module.

Merges crawl_events into the final events table with deduplication.
Archives outdated events that are no longer found in recent crawls.
Logs all changes to the edits table for sync tracking.
"""

import re
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import db

# Add database module to path for edit logger
sys.path.insert(0, str(Path(__file__).parent.parent / 'database'))

try:
    from edit_logger import EditLogger
except ImportError:
    EditLogger = None


def normalize_name_for_dedup(name):
    """Remove accents, punctuation, underscores, and whitespace; convert to lowercase."""
    # Normalize unicode to remove accents (é -> e, etc.)
    nfkd = unicodedata.normalize('NFKD', name)
    ascii_name = ''.join(c for c in nfkd if not unicodedata.combining(c))

    no_underscores = ascii_name.replace('_', '')
    no_punct = re.sub(r'[^\w\s]', '', no_underscores.strip().lower())
    normalized = re.sub(r'\s+', ' ', no_punct).strip()
    return normalized


def stem_word(word):
    """Basic stemming to handle common suffix variations."""
    # First apply semantic equivalents (words that should match each other)
    semantic_equivalents = {
        'dinner': 'dine',
        'dining': 'dine',
        'diner': 'dine',
    }
    if word in semantic_equivalents:
        return semantic_equivalents[word]

    suffixes = [
        ('ency', 'enc'),   # residency -> residenc
        ('ence', 'enc'),   # residence -> residenc
        ('ing', ''),       # running -> runn
        ('tion', 't'),     # creation -> creat
        ('sion', 's'),     # decision -> decis
        ('ies', 'y'),      # stories -> story
        ('es', ''),        # boxes -> box
        ('s', ''),         # cats -> cat
    ]
    for suffix, replacement in suffixes:
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[:-len(suffix)] + replacement
    return word


def get_significant_words(name, stem=False):
    """Get significant words (3+ chars) from normalized name."""
    norm = normalize_name_for_dedup(name)
    words = norm.split()
    result = set(w for w in words if len(w) >= 3)
    if stem:
        result = set(stem_word(w) for w in result)
    return result


def extract_core_title(name):
    """
    Extract the core title by removing common presenter prefixes and subtitles.

    Examples:
    - "Manhattan Theatre Club Presents The Monsters" -> "The Monsters"
    - "The Monsters: a Sibling Love Story" -> "The Monsters"
    - "Lincoln Center Presents: Jazz at Midnight" -> "Jazz at Midnight"
    """
    # Common presenter patterns to remove
    presenter_patterns = [
        r'^.+?\s+presents?\s*:?\s*',       # "X Presents: " or "X Present "
        r'^.+?\s+productions?\s*:?\s*',    # "X Productions: "
        r'^hosted\s+by\s+.+?:\s*',         # "Hosted by X: " (requires colon)
    ]

    result = name
    for pattern in presenter_patterns:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)

    # Remove subtitles after colon (but keep if main title is too short)
    if ':' in result:
        parts = result.split(':', 1)
        main_title = parts[0].strip()
        # Only remove subtitle if main title is substantial (at least 5 chars)
        if len(main_title) >= 5:
            result = main_title

    return result.strip()


def is_false_positive(name1, name2):
    """
    Check if two "similar" names are actually different events.
    Returns True if they should NOT be merged.

    Catches cases where names share words but refer to distinct events:
    - Men's vs Women's sports
    - Different showtimes (6:00 PM vs 8:00 PM)
    - Early vs Late sets
    - Different episode numbers
    - Different sports opponents
    """
    norm1 = normalize_name_for_dedup(name1)
    norm2 = normalize_name_for_dedup(name2)

    # Different gendered sports events (Men's vs Women's)
    if ("men" in norm1) != ("men" in norm2) or ("women" in norm1) != ("women" in norm2):
        return True

    # Different times at end (different showtimes)
    # After normalization, "6:00 PM" becomes "600 pm"
    time_pattern = r'\d{3,4}\s*(?:am|pm)$'
    time1 = re.search(time_pattern, norm1, re.IGNORECASE)
    time2 = re.search(time_pattern, norm2, re.IGNORECASE)
    if time1 and time2 and time1.group() != time2.group():
        return True

    # Early vs Late sets
    if ("early" in norm1) != ("early" in norm2) or ("late" in norm1) != ("late" in norm2):
        return True

    # Different numbered nights/sessions
    night_pattern = r'night\s*(\d+)'
    night1 = re.search(night_pattern, norm1)
    night2 = re.search(night_pattern, norm2)
    if night1 and night2 and night1.group(1) != night2.group(1):
        return True

    # Different episodes (Ep. 1 vs Ep. 2, Episode 3 vs Episode 4, etc.)
    ep_pattern = r'ep(?:isode)?\.?\s*(\d+)'
    ep1 = re.search(ep_pattern, norm1, re.IGNORECASE)
    ep2 = re.search(ep_pattern, norm2, re.IGNORECASE)
    if ep1 and ep2 and ep1.group(1) != ep2.group(1):
        return True

    # Different sports opponents (vs X vs vs Y)
    vs_pattern = r'vs\.?\s+(.+?)(?:\s*-|$)'
    vs1 = re.search(vs_pattern, norm1, re.IGNORECASE)
    vs2 = re.search(vs_pattern, norm2, re.IGNORECASE)
    if vs1 and vs2:
        opponent1 = vs1.group(1).strip()
        opponent2 = vs2.group(1).strip()
        # If opponents are very different, not a duplicate
        if opponent1 != opponent2 and opponent1 not in opponent2 and opponent2 not in opponent1:
            return True

    return False


def are_names_similar(name1, name2):
    """
    Check if two event names are similar enough to be considered duplicates.

    Uses multiple strategies:
    1. Exact match after normalization (removing accents, punctuation, etc.)
    2. Substring matching for prefix/suffix variations
    3. Core title extraction (removing "X Presents" prefixes and subtitles)
    4. Word-based matching (subset or 70%+ Jaccard similarity)
    5. Stemmed word matching to handle variations like residency/residence

    Also checks for false positives (events that look similar but are distinct).
    """
    # First check for false positives that should never match
    if is_false_positive(name1, name2):
        return False

    norm1 = normalize_name_for_dedup(name1)
    norm2 = normalize_name_for_dedup(name2)

    # Exact match after normalization
    if norm1 == norm2:
        return True

    # Check if one is a substring of the other (for prefix/suffix variations)
    if len(norm1) >= 5 and len(norm2) >= 5:
        if norm1 in norm2 or norm2 in norm1:
            return True

    # Try comparing core titles (removing presenter prefixes and subtitles)
    core1 = extract_core_title(name1)
    core2 = extract_core_title(name2)
    if core1 and core2:
        norm_core1 = normalize_name_for_dedup(core1)
        norm_core2 = normalize_name_for_dedup(core2)
        # If core titles match exactly or one contains the other
        if norm_core1 == norm_core2:
            return True
        if len(norm_core1) >= 5 and len(norm_core2) >= 5:
            if norm_core1 in norm_core2 or norm_core2 in norm_core1:
                return True

    # Word-based similarity with unstemmed words
    words1 = get_significant_words(name1)
    words2 = get_significant_words(name2)

    if words1 and words2:
        # If one set of words is a subset of the other
        if words1.issubset(words2) or words2.issubset(words1):
            return True

        # Jaccard similarity >= 70%
        intersection = words1 & words2
        union = words1 | words2
        if len(intersection) / len(union) >= 0.7:
            return True

    # Try with stemmed words to catch variations like residency/residence
    stemmed1 = get_significant_words(name1, stem=True)
    stemmed2 = get_significant_words(name2, stem=True)

    if stemmed1 and stemmed2:
        if stemmed1.issubset(stemmed2) or stemmed2.issubset(stemmed1):
            return True

        intersection = stemmed1 & stemmed2
        union = stemmed1 | stemmed2
        if len(intersection) / len(union) >= 0.7:
            return True

    return False


def merge_crawl_events(cursor, connection, crawl_run_id=None):
    """
    Merge new crawl_events into the final events table with deduplication.
    Archives outdated events that are no longer found in recent crawls.

    Deduplication logic:
    - Events are considered duplicates if they share the same lat/lng, similar name,
      and have an overlapping occurrence date.
    - For duplicates, we merge URLs and keep the shorter name / longer description.
    - Links to crawl_events are tracked in event_sources table.

    Archiving logic:
    - After merging, archives events from processed websites where ALL source websites
      have newer crawls that don't include the event.
    - Multi-source events are only archived when ALL sources stop listing them.

    Args:
        cursor: Database cursor
        connection: Database connection
        crawl_run_id: Optional crawl run ID for edit logging context

    Returns:
        Tuple of (new_events_count, merged_count)
    """
    current_date = datetime.now().date()
    future_limit_date = (datetime.now() + timedelta(days=90)).date()

    # Initialize edit logger if available
    edit_logger = None
    if EditLogger:
        edit_logger = EditLogger(cursor, connection, source='crawl',
                                 editor_info=f'crawl_run:{crawl_run_id}' if crawl_run_id else 'crawl')

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

    # Build lookups of existing events for deduplication:
    # 1. By (lat, lng) for events with coordinates
    # 2. By normalized location_name for events without coordinates (fallback)
    # Only load events that have at least one recent/future occurrence (optimization for large datasets)
    # Use 10-day buffer to catch recurring events that may not have next occurrence posted yet
    recent_cutoff = (datetime.now() - timedelta(days=10)).date()
    cursor.execute("""
        SELECT DISTINCT e.id, e.name, e.lat, e.lng, e.location_name
        FROM events e
        JOIN event_occurrences eo ON e.id = eo.event_id
        WHERE eo.start_date >= %s
    """, (recent_cutoff,))
    existing_events_by_coords = {}  # key: (lat, lng) -> list of {id, name}
    existing_events_by_location = {}  # key: normalized location_name -> list of {id, name}
    event_ids_with_future = set()
    for row in cursor.fetchall():
        event_id, name, lat, lng, location_name = row
        event_ids_with_future.add(event_id)
        event_entry = {'id': event_id, 'name': name}

        # Index by coordinates if available
        if lat is not None and lng is not None:
            key = (round(float(lat), 5), round(float(lng), 5))
            if key not in existing_events_by_coords:
                existing_events_by_coords[key] = []
            existing_events_by_coords[key].append(event_entry)

        # Also index by normalized location_name (for fallback matching)
        if location_name:
            loc_key = normalize_name_for_dedup(location_name)
            if loc_key and len(loc_key) >= 3:
                if loc_key not in existing_events_by_location:
                    existing_events_by_location[loc_key] = []
                existing_events_by_location[loc_key].append(event_entry)

    print(f"  Loaded {len(event_ids_with_future)} existing events with future occurrences")

    # Load future occurrence dates for these events (only dates we care about for dedup)
    event_dates = {eid: set() for eid in event_ids_with_future}
    if event_ids_with_future:
        # Use a placeholder approach for large IN clauses
        placeholders = ','.join(['%s'] * len(event_ids_with_future))
        cursor.execute(f"""
            SELECT event_id, start_date FROM event_occurrences
            WHERE event_id IN ({placeholders})
              AND start_date >= %s AND start_date <= %s
        """, (*event_ids_with_future, current_date, future_limit_date))
        for event_id, start_date in cursor.fetchall():
            if start_date:
                event_dates[event_id].add(str(start_date))

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

        # Build set of occurrence dates for this crawl event
        crawl_event_dates = set(str(occ[0]) for occ in valid_occurrences if occ[0])

        # Get tags for this crawl event
        cursor.execute("SELECT tag FROM crawl_event_tags WHERE crawl_event_id = %s", (ce_id,))
        tags = [row[0] for row in cursor.fetchall()]

        # Check for duplicate in existing events (same location + overlapping dates + similar name)
        matched_event_id = None

        # Try matching by coordinates first (most precise)
        if lat is not None and lng is not None:
            key = (round(float(lat), 5), round(float(lng), 5))
            if key in existing_events_by_coords:
                for existing in existing_events_by_coords[key]:
                    existing_dates = event_dates.get(existing['id'], set())
                    if crawl_event_dates & existing_dates:  # intersection
                        if are_names_similar(name, existing['name']):
                            matched_event_id = existing['id']
                            break

        # Fallback: match by location_name if no coordinate match found
        if matched_event_id is None and location_name:
            loc_key = normalize_name_for_dedup(location_name)
            if loc_key and len(loc_key) >= 3 and loc_key in existing_events_by_location:
                for existing in existing_events_by_location[loc_key]:
                    existing_dates = event_dates.get(existing['id'], set())
                    if crawl_event_dates & existing_dates:  # intersection
                        if are_names_similar(name, existing['name']):
                            matched_event_id = existing['id']
                            break

        if matched_event_id:
            # Merge with existing event
            # Add URL if not already present
            if url:
                # Check if URL already exists for this event to avoid duplicates
                cursor.execute(
                    "SELECT id FROM event_urls WHERE event_id = %s AND url = %s LIMIT 1",
                    (matched_event_id, url[:2000])
                )
                if not cursor.fetchone():
                    cursor.execute(
                        "INSERT INTO event_urls (event_id, url, sort_order) VALUES (%s, %s, 99)",
                        (matched_event_id, url[:2000])
                    )

            # Update location_id if not already set (in case location was added after event)
            if lat is not None and lng is not None:
                cursor.execute("""
                    UPDATE events SET location_id = (
                        SELECT id FROM locations
                        WHERE ROUND(lat, 5) = ROUND(%s, 5) AND ROUND(lng, 5) = ROUND(%s, 5)
                        LIMIT 1
                    )
                    WHERE id = %s AND location_id IS NULL
                """, (lat, lng, matched_event_id))

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

            # Log the insert for sync tracking
            if edit_logger:
                edit_logger.log_insert('events', new_event_id, {
                    'name': name[:500],
                    'short_name': short_name[:255] if short_name else None,
                    'description': description,
                    'emoji': emoji[:10] if emoji else None,
                    'location_name': location_name[:255] if location_name else None,
                    'sublocation': sublocation[:255] if sublocation else None,
                    'lat': lat,
                    'lng': lng,
                    'website_id': website_id
                })

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
                    INSERT IGNORE INTO event_occurrences (event_id, start_date, start_time, end_date, end_time, sort_order)
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

            # Add to lookup indexes for future dedup within this batch
            event_entry = {'id': new_event_id, 'name': name}
            event_dates[new_event_id] = crawl_event_dates

            if lat is not None and lng is not None:
                key = (round(float(lat), 5), round(float(lng), 5))
                if key not in existing_events_by_coords:
                    existing_events_by_coords[key] = []
                existing_events_by_coords[key].append(event_entry)

            if location_name:
                loc_key = normalize_name_for_dedup(location_name)
                if loc_key and len(loc_key) >= 3:
                    if loc_key not in existing_events_by_location:
                        existing_events_by_location[loc_key] = []
                    existing_events_by_location[loc_key].append(event_entry)

            new_events_count += 1

    connection.commit()
    print(f"  Added {new_events_count} new events, merged {merged_count} duplicates")

    # Archive outdated events after merging
    # Get unique website IDs from the crawl events we just processed
    if new_crawl_events:
        crawl_event_ids = [row[0] for row in new_crawl_events]
        placeholders = ','.join(['%s'] * len(crawl_event_ids))
        cursor.execute(f"""
            SELECT DISTINCT cr.website_id
            FROM crawl_events ce
            JOIN crawl_results cr ON ce.crawl_result_id = cr.id
            JOIN event_sources es ON ce.id = es.crawl_event_id
            WHERE ce.id IN ({placeholders})
        """, crawl_event_ids)

        website_ids = [row[0] for row in cursor.fetchall()]
        total_archived = 0
        total_upcoming_flagged = 0

        for website_id in website_ids:
            archived_count, upcoming_events = db.archive_outdated_events(cursor, connection, website_id)
            if archived_count > 0:
                # Get website name for logging
                cursor.execute("SELECT name FROM websites WHERE id = %s", (website_id,))
                result = cursor.fetchone()
                website_name = result[0] if result else f"ID {website_id}"
                print(f"  Archived {archived_count} outdated event(s) from {website_name}")
                total_archived += archived_count

                # Log warnings for upcoming events (rare - may indicate crawl issues)
                if upcoming_events:
                    print(f"    ⚠️  WARNING: {len(upcoming_events)} upcoming event(s) archived (may indicate crawl failure):")
                    for event_id, name, next_occ in upcoming_events:
                        print(f"        - Event {event_id}: {name} (next: {next_occ})")
                    total_upcoming_flagged += len(upcoming_events)

        if total_archived > 0:
            print(f"  Total archived: {total_archived}")
        if total_upcoming_flagged > 0:
            print(f"  ⚠️  Total upcoming events archived: {total_upcoming_flagged} (review recommended)")

    return new_events_count, merged_count
