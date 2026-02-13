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
    # Replace punctuation with spaces (not just remove) to avoid word concatenation
    # e.g., "Alice/Bob" should become "Alice Bob", not "AliceBob"
    no_punct = re.sub(r'[^\w\s]', ' ', no_underscores.strip().lower())
    normalized = re.sub(r'\s+', ' ', no_punct).strip()
    return normalized


def stem_word(word):
    """Basic stemming to handle common suffix variations."""
    # First apply semantic equivalents (words that should match each other)
    semantic_equivalents = {
        'dinner': 'dine',
        'dining': 'dine',
        'diner': 'dine',
        # Day abbreviations -> full names
        'mon': 'monday',
        'tue': 'tuesday',
        'tues': 'tuesday',
        'wed': 'wednesday',
        'weds': 'wednesday',
        'thu': 'thursday',
        'thur': 'thursday',
        'thurs': 'thursday',
        'fri': 'friday',
        'sat': 'saturday',
        'sun': 'sunday',
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
    """Get significant words (3+ chars) from normalized name, excluding stop words and years."""
    # Stop words that don't contribute to event identity
    stop_words = {'the', 'and', 'for', 'with', 'from', 'into', 'your'}

    norm = normalize_name_for_dedup(name)
    words = norm.split()

    def is_year(w):
        """Check if word is a 4-digit year (2000-2099)."""
        return len(w) == 4 and w.isdigit() and w.startswith('20')

    result = set(w for w in words if len(w) >= 3 and w not in stop_words and not is_year(w))
    if stem:
        result = set(stem_word(w) for w in result)
    return result


def strip_common_prefixes(name):
    """
    Strip common prefixes that don't change event identity.

    Handles:
    - Bracketed prefixes: [member-only], [free], [sold out], [virtual], etc.
    - Known event program prefixes: FIDO (Prospect Park dog events), etc.

    Examples:
    - "[member-only] Sewing Machines: Basic Use & Safety" -> "Sewing Machines: Basic Use & Safety"
    - "FIDO Coffee Bark" -> "Coffee Bark"
    - "[FREE] Jazz in the Park" -> "Jazz in the Park"
    """
    result = name.strip()

    # Remove bracketed prefixes at the start (e.g., [member-only], [free], [virtual])
    result = re.sub(r'^\s*\[[^\]]+\]\s*', '', result)

    # Known single-word prefixes that indicate event programs/series but not event identity
    # These are typically added by venues to categorize events
    known_prefixes = [
        'FIDO',      # Prospect Park "Friends In Dog Ownership" events
    ]

    for prefix in known_prefixes:
        # Match prefix followed by space at start of string (case-insensitive)
        pattern = rf'^{re.escape(prefix)}\s+'
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)

    return result.strip()


def extract_core_title(name):
    """
    Extract the core title by removing common presenter prefixes and subtitles.

    Examples:
    - "Manhattan Theatre Club Presents The Monsters" -> "The Monsters"
    - "The Monsters: a Sibling Love Story" -> "The Monsters"
    - "Lincoln Center Presents: Jazz at Midnight" -> "Jazz at Midnight"
    - "[member-only] Sewing Class" -> "Sewing Class"
    - "FIDO Coffee Bark" -> "Coffee Bark"
    """
    # First strip common prefixes
    result = strip_common_prefixes(name)

    # Common presenter patterns to remove
    presenter_patterns = [
        r'^.+?\s+presents?\s*:?\s*',       # "X Presents: " or "X Present "
        r'^.+?\s+productions?\s*:?\s*',    # "X Productions: "
        r'^hosted\s+by\s+.+?:\s*',         # "Hosted by X: " (requires colon)
    ]

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
    - Different showtimes (6:00 PM vs 8:00 PM, anywhere in name)
    - Early vs Late sets
    - Different episode numbers
    - Different set/part/volume numbers (Set 1 vs Set 2)
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

    # Different set/part/volume numbers (Set 1 vs Set 2, Part 1 vs Part 2, Vol. 2 vs Vol. 3)
    for keyword in ['set', 'part', 'vol', 'volume', 'chapter', 'session', 'round']:
        numbered_pattern = rf'\b{keyword}\.?\s*(\d+)'
        match1 = re.search(numbered_pattern, norm1, re.IGNORECASE)
        match2 = re.search(numbered_pattern, norm2, re.IGNORECASE)
        if match1 and match2 and match1.group(1) != match2.group(1):
            return True

    # Different standalone sequence numbers after pipe/dash separators (e.g., "| Wednesday Set 2 | 10:30 pm")
    # Catches "...| 1 |..." vs "...| 2 |..." style numbering
    seq_pattern = r'(?:^|\|)\s*#?\s*(\d+)\s*(?:\||$)'
    seq1 = re.findall(seq_pattern, norm1)
    seq2 = re.findall(seq_pattern, norm2)
    if seq1 and seq2 and seq1 != seq2:
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

    # Different times anywhere in name (catches "9:00 PM" vs "10:30 PM" even when not at end)
    # After normalization, "9:00 PM" becomes "9 00 pm" and "10:30 PM" becomes "10 30 pm"
    time_anywhere_pattern = r'\b(\d{1,2}\s*\d{2}\s*(?:am|pm))\b'
    times1 = set(re.findall(time_anywhere_pattern, norm1, re.IGNORECASE))
    times2 = set(re.findall(time_anywhere_pattern, norm2, re.IGNORECASE))
    if times1 and times2 and times1 != times2:
        return True

    return False


def are_names_similar(name1, name2):
    """
    Check if two event names are similar enough to be considered duplicates.

    Uses multiple strategies:
    1. Exact match after normalization (removing accents, punctuation, etc.)
    2. Match after stripping common prefixes (FIDO, [member-only], etc.)
    3. Substring matching for prefix/suffix variations
    4. Core title extraction (removing "X Presents" prefixes and subtitles)
    5. Word-based matching (subset or 70%+ Jaccard similarity)
    6. Stemmed word matching to handle variations like residency/residence

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

    # Check if names match after stripping common prefixes (e.g., FIDO, [member-only])
    stripped1 = normalize_name_for_dedup(strip_common_prefixes(name1))
    stripped2 = normalize_name_for_dedup(strip_common_prefixes(name2))
    if stripped1 == stripped2:
        return True

    # Check if one is a substring of the other (for prefix/suffix variations)
    if len(norm1) >= 5 and len(norm2) >= 5:
        if norm1 in norm2 or norm2 in norm1:
            return True

    # Also check substring after stripping prefixes
    if len(stripped1) >= 5 and len(stripped2) >= 5:
        if stripped1 in stripped2 or stripped2 in stripped1:
            return True

    # Try comparing core titles (removing presenter prefixes and subtitles)
    core1 = extract_core_title(name1)
    core2 = extract_core_title(name2)
    skip_core_title_match = False
    if core1 and core2:
        norm_core1 = normalize_name_for_dedup(core1)
        norm_core2 = normalize_name_for_dedup(core2)
        # If core titles match exactly or one contains the other
        if norm_core1 == norm_core2:
            # But if both have colons (series:episode format), the series name alone
            # isn't enough - require subtitles to be similar too
            # e.g., "Backstage Pass: Duran Duran" vs "Backstage Pass: Arctic Monkeys" should NOT match
            if ':' in name1 and ':' in name2:
                subtitle1 = name1.split(':', 1)[1].strip()
                subtitle2 = name2.split(':', 1)[1].strip()
                if subtitle1 and subtitle2:
                    norm_sub1 = normalize_name_for_dedup(subtitle1)
                    norm_sub2 = normalize_name_for_dedup(subtitle2)
                    # Subtitles must match or one contains the other
                    if norm_sub1 == norm_sub2 or norm_sub1 in norm_sub2 or norm_sub2 in norm_sub1:
                        return True
                    # Subtitles don't match - skip core title matching entirely
                    skip_core_title_match = True
                else:
                    return True
            else:
                return True
        if not skip_core_title_match and len(norm_core1) >= 5 and len(norm_core2) >= 5:
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

        # Asymmetric containment: if 75%+ of the shorter name's words appear in the longer
        # Handles cases like "Jam Session" matching "TUES 8pm Jam Session. House band: ..."
        shorter, longer = (stemmed1, stemmed2) if len(stemmed1) <= len(stemmed2) else (stemmed2, stemmed1)
        if len(shorter) >= 2 and len(intersection) / len(shorter) >= 0.75:
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
               ce.location_name, ce.sublocation, ce.location_id, ce.url,
               cr.website_id, l.lat, l.lng
        FROM crawl_events ce
        JOIN crawl_results cr ON ce.crawl_result_id = cr.id
        LEFT JOIN event_sources es ON ce.id = es.crawl_event_id
        LEFT JOIN locations l ON ce.location_id = l.id
        WHERE cr.status = 'processed'
          AND es.id IS NULL
    """)

    new_crawl_events = cursor.fetchall()
    print(f"  Found {len(new_crawl_events)} unprocessed crawl_events")

    if not new_crawl_events:
        return 0, 0

    # Build lookups of existing events for deduplication:
    # 1. By location_id for events with matched locations
    # 2. By normalized location_name for events without location_id (fallback)
    # Only load events that have at least one recent/future occurrence (optimization for large datasets)
    # Use 10-day buffer to catch recurring events that may not have next occurrence posted yet
    recent_cutoff = (datetime.now() - timedelta(days=10)).date()
    cursor.execute("""
        SELECT DISTINCT e.id, e.name, e.location_id, l.lat, l.lng, e.location_name, e.website_id
        FROM events e
        JOIN event_occurrences eo ON e.id = eo.event_id
        LEFT JOIN locations l ON e.location_id = l.id
        WHERE eo.start_date >= %s
    """, (recent_cutoff,))
    existing_events_by_coords = {}  # key: (lat, lng) -> list of {id, name}
    existing_events_by_location_id = {}  # key: location_id -> list of {id, name}
    existing_events_by_location = {}  # key: normalized location_name -> list of {id, name}
    existing_events_by_website = {}  # key: website_id -> list of {id, name}
    event_ids_with_future = set()
    for row in cursor.fetchall():
        event_id, name, location_id, lat, lng, location_name, website_id = row
        event_ids_with_future.add(event_id)
        event_entry = {'id': event_id, 'name': name}

        # Index by location_id if available (primary matching method)
        if location_id is not None:
            if location_id not in existing_events_by_location_id:
                existing_events_by_location_id[location_id] = []
            existing_events_by_location_id[location_id].append(event_entry)

        # Index by coordinates if available (for legacy compatibility)
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

        # Index by website_id (last-resort fallback for location mismatches)
        if website_id is not None:
            if website_id not in existing_events_by_website:
                existing_events_by_website[website_id] = []
            existing_events_by_website[website_id].append(event_entry)

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
        ce_id, name, short_name, description, emoji, location_name, sublocation, location_id, url, website_id, lat, lng = ce_row

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
        norm_name = normalize_name_for_dedup(name)

        def find_best_match(candidates):
            """Find best matching event, preferring exact normalized name matches."""
            best_id = None
            for existing in candidates:
                existing_dates = event_dates.get(existing['id'], set())
                if crawl_event_dates & existing_dates:  # date overlap required
                    if are_names_similar(name, existing['name']):
                        if normalize_name_for_dedup(existing['name']) == norm_name:
                            return existing['id']  # Exact match — best possible
                        elif best_id is None:
                            best_id = existing['id']  # Partial match — keep looking
            return best_id

        # Try matching by location_id first (most precise and reliable)
        if location_id is not None and location_id in existing_events_by_location_id:
            matched_event_id = find_best_match(existing_events_by_location_id[location_id])

        # Fallback: match by coordinates if no location_id match found
        if matched_event_id is None and lat is not None and lng is not None:
            key = (round(float(lat), 5), round(float(lng), 5))
            if key in existing_events_by_coords:
                matched_event_id = find_best_match(existing_events_by_coords[key])

        # Second fallback: match by location_name if still no match found
        if matched_event_id is None and location_name:
            loc_key = normalize_name_for_dedup(location_name)
            if loc_key and len(loc_key) >= 3 and loc_key in existing_events_by_location:
                matched_event_id = find_best_match(existing_events_by_location[loc_key])

        # Last-resort fallback: match by website_id when location strategies all failed.
        # Catches cases where AI extraction assigns inconsistent location names between
        # crawls (e.g., "Online (via Zoom)" vs "Online", "Various NYC Venues" vs
        # "New York City Venues"). Safe because name similarity + date overlap + same
        # website is a strong enough signal.
        if matched_event_id is None and website_id in existing_events_by_website:
            matched_event_id = find_best_match(existing_events_by_website[website_id])

        if matched_event_id:
            # Merge with existing event
            # Un-archive event if it was previously archived (event found in new crawl)
            cursor.execute(
                "UPDATE events SET archived = FALSE WHERE id = %s AND archived = TRUE",
                (matched_event_id,)
            )

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
            if location_id:
                cursor.execute("SELECT location_id FROM events WHERE id = %s", (matched_event_id,))
                result = cursor.fetchone()
                current_location_id = result[0] if result else None
                if not current_location_id:
                    cursor.execute("UPDATE events SET location_id = %s WHERE id = %s", (location_id, matched_event_id))

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
                                   sublocation, website_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                name[:500],
                short_name[:255] if short_name else None,
                description,
                emoji[:10] if emoji else None,
                location_id,
                location_name[:255] if location_name else None,
                sublocation[:255] if sublocation else None,
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
                    'location_id': location_id,
                    'location_name': location_name[:255] if location_name else None,
                    'sublocation': sublocation[:255] if sublocation else None,
                    'website_id': website_id
                })

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

            if location_id is not None:
                if location_id not in existing_events_by_location_id:
                    existing_events_by_location_id[location_id] = []
                existing_events_by_location_id[location_id].append(event_entry)

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

            if website_id is not None:
                if website_id not in existing_events_by_website:
                    existing_events_by_website[website_id] = []
                existing_events_by_website[website_id].append(event_entry)

            new_events_count += 1

    connection.commit()
    print(f"  Added {new_events_count} new events, merged {merged_count} duplicates")

    # Archive outdated events after merging
    # Only archive for websites where we processed crawl_events from their LATEST
    # crawl result. This prevents mass-archiving when processing a backlog of old
    # crawl_events from historical crawls.
    if new_crawl_events:
        crawl_event_ids = [row[0] for row in new_crawl_events]
        placeholders = ','.join(['%s'] * len(crawl_event_ids))
        cursor.execute(f"""
            SELECT DISTINCT cr.website_id
            FROM crawl_events ce
            JOIN crawl_results cr ON ce.crawl_result_id = cr.id
            JOIN event_sources es ON ce.id = es.crawl_event_id
            WHERE ce.id IN ({placeholders})
              AND cr.id = (
                  SELECT MAX(cr2.id)
                  FROM crawl_results cr2
                  WHERE cr2.website_id = cr.website_id
                    AND cr2.status IN ('processed', 'extracted')
              )
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
