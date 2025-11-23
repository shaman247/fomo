"""
Response Processing Script

This script processes extracted event data from markdown tables and enriches
them with location coordinates and additional metadata.

Key features:
- Parses markdown tables from Gemini AI extraction
- Sanitizes text (removes HTML, entities, normalizes whitespace)
- Enriches events with location data (coordinates, neighborhoods)
- Creates short names for events (removes redundant location info)
- Processes and normalizes tags
- Handles emoji extraction and validation
- Generates unique event IDs

Configuration:
- Input: event_data/extracted/YYYYMMDD/*.md
- Output: event_data/processed/YYYYMMDD/*.json
- Reference data: data/locations.json, data/tags.json
"""

import os
import re
import json
from datetime import datetime, timedelta
import regex

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def find_first_emoji(text: str) -> str:
    """
    Finds the first emoji in a string.

    This function scans a string and returns the first complete emoji
    it encounters. It handles simple emojis, emojis with skin-tone
    modifiers, variation selectors, and complex multi-character emojis like family groups.

    Args:
        text: The string to search for an emoji.

    Returns:
        The first emoji found as a string, or an empty string if no
        emoji is found.
    """
    # Comprehensive emoji pattern that handles:
    # - Regional indicator symbols (flags) - two consecutive RI characters
    # - Variation selectors (\uFE0F, \uFE0E)
    # - Skin tone modifiers (\p{Emoji_Modifier})
    # - Zero-width joiners (\u200D) for compound emojis (rainbow flag, families, etc.)
    # - Keycap sequences (\u20E3)
    # - Tag sequences (\p{Emoji_Component})
    emoji_pattern = regex.compile(
        r'(?:\p{Regional_Indicator}{2})'  # Flag emojis (two regional indicators)
        r'|'
        r'\p{Emoji}'
        r'[\uFE0E\uFE0F]?'  # Variation selectors
        r'[\u20E3]?'  # Keycap combining enclosing
        r'(?:\p{Emoji_Modifier})?'  # Skin tone modifiers
        r'(?:\u200D\p{Emoji}[\uFE0E\uFE0F]?(?:\p{Emoji_Modifier})?)*'  # ZWJ sequences
    )
    match = emoji_pattern.search(text)

    if match:
        return match.group(0)  # Return the matched emoji
    else:
        return ""  # Return an empty string if no emoji is found

def _sanitize_text(text):
    """Removes HTML tags, entities, and normalizes whitespace."""
    if not text:
        return text

    # Remove HTML tags (e.g., <br>, <b>, <strong>, etc.)
    text = re.sub(r'<[^>]+>', ' ', text)

    # Decode common HTML entities
    html_entities = {
        '&nbsp;': ' ',
        '&amp;': '&',
        '&lt;': '<',
        '&gt;': '>',
        '&quot;': '"',
        '&#39;': "'",
        '&apos;': "'",
        '&ndash;': '–',
        '&mdash;': '—',
        '&rsquo;': ''',
        '&lsquo;': ''',
        '&rdquo;': '"',
        '&ldquo;': '"',
    }
    for entity, char in html_entities.items():
        text = text.replace(entity, char)

    # Replace newline, carriage return, and tab characters with spaces
    text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')

    # Remove zero-width and other invisible Unicode characters
    # Zero-width space, zero-width joiner (except in emojis), zero-width non-joiner, etc.
    text = text.replace('\u200b', '')  # Zero-width space
    text = text.replace('\u200c', '')  # Zero-width non-joiner
    text = text.replace('\ufeff', '')  # Zero-width no-break space (BOM)
    text = text.replace('\u00ad', '')  # Soft hyphen

    # Normalize multiple spaces to single space
    text = re.sub(r'\s+', ' ', text)

    # Strip leading/trailing whitespace
    return text.strip()

def _create_short_name(name):
    """Creates a shortened version of the event name for search results."""
    if not name:
        return name

    short_name = name

    # Remove common prefixes followed by "–", ":", or " - "
    prefix_patterns = [
        r'^Exhibition\s*[–:\-]\s*',
        r'^Talks?\s*[:\-]\s*',
        r'^Screening\s*[:\-]\s*',
        r'^Performance\s*[:\-]\s*',
        r'^Concert\s*[:\-]\s*',
        r'^Event\s*[:\-]\s*',
    ]
    for pattern in prefix_patterns:
        short_name = re.sub(pattern, '', short_name, flags=re.IGNORECASE)

    # Remove main title before colon if there's a subtitle (e.g., "Film Night: Movie Name" -> "Movie Name")
    # Only apply if the title is longer than 40 characters
    if len(short_name) > 40 and ':' in short_name:
        parts = short_name.split(':', 1)
        # Only use the subtitle if it's substantial (more than 3 chars after stripping)
        if len(parts[1].strip()) > 3:
            short_name = parts[1].strip()

    # Remove text after " – " (en dash with spaces) or " - " (hyphen with spaces)
    # Only apply if the title is longer than 40 characters
    if len(short_name) > 40:
        short_name = re.sub(r'\s+[–\-]\s+.*$', '', short_name)

    # Remove parenthetical details: (Early Show), (6:30), (Ages 3-5), etc.
    short_name = re.sub(r'\s*\([^)]*\)', '', short_name)

    # Remove " - Q&A with..." and similar suffixes
    short_name = re.sub(r'\s*[-–]\s*Q&A\s+with\s+.*$', '', short_name)

    # Remove "\ | with..." or " | with..." suffixes
    short_name = re.sub(r'\s*\\?\s*\|\s*with\s+.*$', '', short_name)

    # Remove " w/ [artists]" or " with [artists]" suffixes (performer lists)
    short_name = re.sub(r'\s+w/\s+.*$', '', short_name)
    short_name = re.sub(r'\s+with\s+.*$', '', short_name, flags=re.IGNORECASE)

    # Remove " at [venue]" or "@[venue]" suffixes (venue names)
    short_name = re.sub(r'\s+at\s+.*$', '', short_name, flags=re.IGNORECASE)
    short_name = re.sub(r'\s*@.*$', '', short_name)

    # Remove " in NYC" and similar location suffixes
    short_name = re.sub(r'\s+in\s+NYC\s*[-–].*$', '', short_name)

    # Remove date ranges at the end: " - Tuesday, October 21 - Sunday, October 26"
    short_name = re.sub(r'\s*[-–]\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+.*$', '', short_name)

    # Normalize multiple spaces and strip
    short_name = re.sub(r'\s+', ' ', short_name).strip()

    return short_name

def _process_tags(row_dict, tag_rules):
    """Processes the 'hashtags' string into a list of 'tags'."""
    if 'hashtags' in row_dict:
        hashtag_string = row_dict.pop('hashtags')  # Remove old 'hashtags' field
        rewrite_rules = tag_rules.get('rewrite', {})
        exclude_list = set(tag_rules.get('exclude', []))

        # Split by '#' and filter out empty strings
        raw_tags = [tag.strip().rstrip(',') for tag in hashtag_string.split('#') if tag.strip()]
        
        processed_tags = []
        seen_tags = set()
        for tag in raw_tags:
            # Add spaces before capital letters in camelCase tags, then strip
            # This regex handles acronyms like 'NYC' and numbers like '10K' correctly.
            processed_tag = re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', ' ', tag).strip()

            # Add space before standalone numbers (e.g., "Carrie2" -> "Carrie 2", "Catch22" -> "Catch 22")
            processed_tag = re.sub(r'([a-zA-Z])(\d+)', r'\1 \2', processed_tag)

            # Fix Irish/Scottish names: remove space after Mc/O (e.g., "Mc Pherson" -> "McPherson", "O Brien" -> "O'Brien")
            processed_tag = re.sub(r'\bMc\s+([A-Z])', r'Mc\1', processed_tag)
            processed_tag = re.sub(r'\bO\s+([A-Z])', r"O'\1", processed_tag)

            # Fix "St" abbreviation (e.g., "St James" -> "St. James")
            processed_tag = re.sub(r'\bSt\s+([A-Z])', r'St. \1', processed_tag)

            # Check for rewrite rules (case-insensitive)
            lookup_tag = processed_tag.lower().replace(" ", "")
            final_tag = rewrite_rules.get(lookup_tag, processed_tag)

            # Lowercase common connecting words in tags (e.g., "Foo And Bar" -> "Foo and Bar")
            # But keep "The" capitalized if it's at the start of the tag
            final_tag = re.sub(r'(?<!^)\b(A|And|Of|The|Or|In|At|On|For|To|With|From|By)\b', lambda m: m.group(1).lower(), final_tag)

            # Remove spaces before K in number-K patterns (e.g., "4 K" -> "4K", "10 K Run" -> "10K Run")
            final_tag = re.sub(r'\b(\d+)\s+K\b', r'\1K', final_tag)

            # Remove spaces before D in number-D patterns (e.g., "3 D" -> "3D")
            final_tag = re.sub(r'\b(\d+)\s+D\b', r'\1D', final_tag)

            # Preserve lowercase ordinal suffixes (e.g., "38Th" -> "38th", "1St" -> "1st", "2Nd" -> "2nd", "3Rd" -> "3rd")
            final_tag = re.sub(r'(\d+)(St|Nd|Rd|Th)\b', lambda m: m.group(1) + m.group(2).lower(), final_tag)

            # Fix ampersand capitalization (e.g., "Q&a" -> "Q&A", "R&b" -> "R&B")
            final_tag = re.sub(r'\b([A-Z])&([a-z])\b', lambda m: m.group(1) + '&' + m.group(2).upper(), final_tag)

            # Check for exclusion (case-insensitive and space-insensitive)
            final_tag_lookup = final_tag.lower().replace(" ", "")
            if final_tag_lookup not in exclude_list and final_tag_lookup not in seen_tags:
                processed_tags.append(final_tag)
                seen_tags.add(final_tag_lookup)
        # Add the new 'tags' field
        row_dict['tags'] = processed_tags
    return row_dict

def _standardize_time(time_str):
    """Standardizes time formats like '6:30 PM' or '6:30 p.m.' to '6:30pm'."""
    if not time_str: return ''
    normalized_time = time_str.lower().replace(' ', '').replace('.', '')
    if normalized_time == 'allday':
        return ''
    # Remove ':00' for on-the-hour times (e.g., '7:00pm' -> '7pm')
    normalized_time = normalized_time.replace(':00', '')
    return normalized_time

def _group_event_occurrences(rows):
    """Groups event rows by name and consolidates their occurrences."""

    def normalize_name_for_grouping(name):
        """Normalize event name for fuzzy matching (similar to export_events.py logic)."""
        if not name:
            return ""
        # Remove underscores specifically (common in event titles)
        no_underscores = name.replace('_', '')
        # Remove all punctuation except spaces
        no_punct = re.sub(r'[^\w\s]', '', no_underscores.strip().lower())
        # Collapse multiple spaces into single space and strip
        normalized = re.sub(r'\s+', ' ', no_punct).strip()
        return normalized

    def find_matching_group_key(event_name, grouped_events):
        """Find an existing group key that matches the event name, or return the event name itself."""
        normalized_event = normalize_name_for_grouping(event_name)

        # First check for exact match
        if event_name in grouped_events:
            return event_name

        # Then check for normalized match
        for existing_key in grouped_events.keys():
            normalized_existing = normalize_name_for_grouping(existing_key)

            # Exact match after normalization
            if normalized_event == normalized_existing:
                return existing_key

            # Substring match (for prefix/suffix variations), with minimum length requirement
            if len(normalized_event) >= 5 and len(normalized_existing) >= 5:
                if normalized_event in normalized_existing or normalized_existing in normalized_event:
                    return existing_key

        # No match found, return the original name
        return event_name

    grouped_events = {}
    for row_dict in rows:
        event_name = row_dict.get('name')
        if not event_name:
            continue

        if event_name.upper().startswith(('CANCELED:', 'CANCELLED:', 'KIM:', 'KIM -')):
            continue

        # If >40% of the letters in an event name are uppercase, convert to title case for consistency.
        # Skip recapitalization if the event name is 5 or fewer characters long.
        alpha_chars = [char for char in event_name if char.isalpha()]
        # Avoid division by zero for names without letters
        if alpha_chars and len(event_name) > 5:
            num_alpha = len(alpha_chars)
            num_upper = sum(1 for char in alpha_chars if char.isupper())
            if (num_upper / num_alpha) > 0.5:
                original_name = event_name
                event_name = event_name.title()
                # Normalize apostrophes: convert curly apostrophes to straight apostrophes
                event_name = event_name.replace(''', "'").replace(''', "'")
                # Fix possessive 'S after apostrophe (e.g., "Baker'S" -> "Baker's")
                # Handle both straight and curly apostrophes in case normalization missed any
                event_name = re.sub(r"['']S\b", "'s", event_name)
                # Fix contractions like "Wouldn'T", "Didn'T", "I'D", etc.
                event_name = re.sub(r"['']T\b", "'t", event_name)
                event_name = re.sub(r"['']D\b", "'d", event_name)
                # Lowercase common connecting words (e.g., "Foo And Bar" -> "Foo and Bar")
                event_name = re.sub(r'(?<!^)\b(A|And|Of|The|Or|In|At|On|For|To|With|From|By)\b', lambda m: m.group(1).lower(), event_name)
                # Lowercase "W/" shorthand (e.g., "W/" -> "w/")
                event_name = re.sub(r'\bW/', r'w/', event_name)
                # Preserve capitalization for Roman numerals (e.g., "Ii" -> "II", "Iv" -> "IV")
                event_name = re.sub(r'\b(I|Ii|Iii|Iv|V|Vi|Vii|Viii|Ix|X|Xi|Xii)\b', lambda m: m.group(1).upper(), event_name)
                # Preserve lowercase for film formats (e.g., "35Mm" -> "35mm", "70Mm" -> "70mm")
                event_name = re.sub(r'\b(35|65|70)Mm\b', r'\1mm', event_name)
                # Preserve lowercase ordinal suffixes (e.g., "38Th" -> "38th", "1St" -> "1st", "2Nd" -> "2nd", "3Rd" -> "3rd")
                event_name = re.sub(r'(\d+)(St|Nd|Rd|Th)\b', lambda m: m.group(1) + m.group(2).lower(), event_name)
                # Capitalize two-consonant abbreviations (e.g., "Dj" -> "DJ", "Tv" -> "TV")
                # Matches word boundaries with exactly 2 consonants (no vowels)
                event_name = re.sub(r'\b([BCDFGHJKLMNPQRSTVWXYZ])([bcdfghjklmnpqrstvwxyz])\b', lambda m: m.group(0).upper(), event_name)
                row_dict['name'] = event_name
                #print(f"  - Normalized mostly-caps event name: '{original_name}' -> '{event_name}'")

        start_date = row_dict.get('start_date', '')
        end_date = row_dict.get('end_date', '')
        if start_date and end_date and start_date == end_date:
            end_date = ''

        start_time = _standardize_time(row_dict.get('start_time', ''))
        end_time = _standardize_time(row_dict.get('end_time', ''))

        occurrence = [
            start_date,
            start_time,
            end_date,
            end_time
        ]

        # Find matching group key (handles fuzzy matching)
        group_key = find_matching_group_key(event_name, grouped_events)

        if group_key not in grouped_events:
            # Create a new entry, removing date/time fields
            base_event = {k: v for k, v in row_dict.items() if k not in ['start_date', 'start_time', 'end_date', 'end_time', 'sublocation', 'url']}
            base_event['occurrences'] = []
            # Only add sublocation if it's not empty or 'N/A'
            sublocation = row_dict.get('sublocation', '').strip()
            if sublocation and sublocation.upper() != 'N/A':
                base_event['sublocation'] = row_dict['sublocation']

            # Initialize urls list with the first URL
            url = row_dict.get('url', '').strip()
            base_event['urls'] = [url] if url else []

            grouped_events[group_key] = base_event
        else:
            # If we're merging events, prefer the shorter name (less likely to have extra punctuation)
            existing_name = grouped_events[group_key]['name']
            if len(event_name) < len(existing_name):
                grouped_events[group_key]['name'] = event_name

            # Add URL if it's new and not empty
            url = row_dict.get('url', '').strip()
            if url and url not in grouped_events[group_key]['urls']:
                grouped_events[group_key]['urls'].append(url)

        # Check if the occurrence is already listed to avoid duplicates
        if occurrence not in grouped_events[group_key]['occurrences']:
            grouped_events[group_key]['occurrences'].append(occurrence)

    return list(grouped_events.values())

def _filter_by_date(row_dict, current_date, future_limit_date):
    """Filters a row based on its start and end dates."""
    start_date_str = row_dict.get('start_date', '').strip()
    end_date_str = row_dict.get('end_date', '').strip()

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()

        # Exclude if start_date is more than 3 months in the future
        if start_date > future_limit_date:
            return False

        # Use start_date if end_date is missing, then check if it's in the past
        effective_end_date_str = end_date_str if end_date_str else start_date_str
        effective_end_date = datetime.strptime(effective_end_date_str, '%Y-%m-%d').date()
        if effective_end_date < current_date:
            return False

        # Exclude events that last longer than 400 days
        event_duration = (effective_end_date - start_date).days
        if event_duration > 400:
            return False
    except (ValueError, TypeError):
        # Skip row if start_date is invalid or missing
        return False
    return True

def _filter_by_tag(processed_row, tag_rules):
    """Filters a row based on removable tags."""
    tags_to_remove = set(tag_rules.get('remove', []))
    event_tags = set(tag.lower().replace(" ", "") for tag in processed_row.get('tags', []))
    return event_tags.isdisjoint(tags_to_remove)

def _normalize_location_name(name):
    """Normalizes a location name for better matching."""
    if not name:
        return ""
    # Lowercase first, but keep track of original structure for dash detection
    original_lower = name.lower()
    # Remove punctuation except for checking if borough comes after dash
    has_dash_before_borough = False
    for borough in ['queens', 'bronx', 'brooklyn', 'manhattan', 'staten island']:
        if f'- {borough}' in original_lower or f'_{borough}' in original_lower:
            has_dash_before_borough = True
            break

    normalized = re.sub(r'[^\w\s]', '', original_lower)

    # Remove online/virtual/livestream events
    if normalized in ['virtual', 'online', 'livestream']:
        return ""
    # Remove "the " prefix
    if len(normalized) > 15 and normalized.startswith('the '):
        normalized = normalized[4:]

    # Remove common geographic suffixes, but NOT if they appeared after a dash/underscore
    # (which indicates they're part of the identifier, not a description)
    suffixes_to_remove = ['nyc', 'new york', 'brooklyn', 'manhattan', 'queens', 'bronx', 'staten island']
    if normalized in suffixes_to_remove:
        return ""

    if not has_dash_before_borough:
        for suffix in suffixes_to_remove:
            # Check if the string ends with the current suffix (preceded by a space)
            if normalized.endswith(f' {suffix}') and len(normalized) > len(suffix) + 2:
                # If it does, slice the string to remove the suffix
                normalized = normalized[:-len(f' {suffix}')].strip()
                # Exit the loop after finding and removing one suffix
                break

    # Remove extra whitespace
    return " ".join(normalized.split())

def _build_locations_map():
    """Loads location data and builds a map for lat/lng enrichment."""
    locations_map = {}
    with open(os.path.join(SCRIPT_DIR, 'data', 'locations.json'), 'r', encoding='utf-8') as f:
        locations_data = json.load(f)
        for loc in locations_data:
            location_info = {
                'lat': loc.get('lat'),
                'lng': loc.get('lng'),
                'emoji': loc.get('emoji')
            }

            def add_to_map_if_valid(key, value):
                """Adds key-value to map if key is at least 5 chars long."""
                if key and len(key) >= 5:
                    locations_map[key] = value

            # Process main name and its normalized version
            main_name = loc.get('name', '')
            add_to_map_if_valid(main_name.lower(), location_info)
            add_to_map_if_valid(_normalize_location_name(main_name), location_info)

            # Process alternate names and their normalized versions
            for alt_name in loc.get('alternate_names', []):
                add_to_map_if_valid(alt_name.lower(), location_info)
                add_to_map_if_valid(_normalize_location_name(alt_name), location_info)

    return locations_map

def _calculate_levenshtein_ratio(s1, s2):
    """Calculates the Levenshtein distance ratio between two strings."""
    if not s1 or not s2:
        return 0.0

    # Using a simple and direct implementation of Levenshtein distance
    if len(s1) < len(s2):
        return _calculate_levenshtein_ratio(s2, s1)

    if len(s2) == 0:
        return 1.0

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    distance = previous_row[-1]
    ratio = (len(s1) + len(s2) - distance) / (len(s1) + len(s2))
    return ratio

def _get_location_coords(location_name_raw, sublocation_name_raw, source_site_name, event_name_raw, locations_map):
    """
    Finds the best matching latitude and longitude for an event.

    It prioritizes the longest, most specific match from the event's location/sublocation,
    then checks the event name itself, and falls back to matching against the source site name.

    Returns:
        A dictionary containing location info (lat, lng, emoji) or None if no match is found.
    """
    normalized_event_location = _normalize_location_name(location_name_raw)
    normalized_event_sublocation = _normalize_location_name(sublocation_name_raw)
    normalized_event_name = _normalize_location_name(event_name_raw)
    full_normalized_event_loc = f"{normalized_event_location} {normalized_event_sublocation}".strip()

    if len(full_normalized_event_loc) > 5:
        # Prioritize an exact match first.
        if full_normalized_event_loc in locations_map:
            return locations_map.get(full_normalized_event_loc)
        if normalized_event_location in locations_map:
            return locations_map.get(normalized_event_location)

    # Check if the event name itself matches a location
    if len(normalized_event_name) > 5 and normalized_event_name in locations_map:
        return locations_map.get(normalized_event_name)

    # If no exact match, find the best partial match
    best_match_key = None
    best_score = -1

    potential_matches = []

    if len(full_normalized_event_loc) > 5 or len(normalized_event_name) > 5:
        # Find the best match from the event's location/sublocation strings.
        for key in locations_map:
            if not key.strip():
                continue

            # Matching conditions
            is_exact_match = (key == normalized_event_location) # full_normalized_event_loc already checked
            is_exact_name_match = (len(normalized_event_name) > 5 and key == normalized_event_name)
            is_key_a_prefix = (len(key) > 5 and full_normalized_event_loc.startswith(key))
            is_key_a_suffix = (len(key) > 5 and full_normalized_event_loc.endswith(key))
            is_key_in_event_loc = (len(key) > 5 and key in full_normalized_event_loc)
            is_event_loc_in_key = (len(normalized_event_location) > 5 and normalized_event_location and normalized_event_location in key)
            is_event_subloc_in_key = (len(normalized_event_sublocation) > 5 and normalized_event_sublocation and normalized_event_sublocation in key)

            # Pre-filter to find potential matches before running expensive calculations
            if is_exact_match or is_exact_name_match or is_key_a_prefix or is_key_a_suffix or is_key_in_event_loc or is_event_loc_in_key or is_event_subloc_in_key:
                potential_matches.append(key)

                # Exact name match gets highest priority (perfect score)
                if is_exact_name_match:
                    score = 1.0
                # If the canonical name is a prefix or suffix of the event location, it's a very strong signal.
                # Give it a high score to prioritize it, but slightly less than a perfect match.
                elif is_key_a_prefix or is_key_a_suffix:
                    # Score based on the length of the prefix/suffix to favor the longest, most specific match.
                    # We normalize it by the length of the event string and scale it to be high (e.g., in the 0.9-0.99 range)
                    # This ensures it's always higher than a Levenshtein score but still allows for ranking among prefixes/suffixes.
                    score = 0.9 + (len(key) / len(full_normalized_event_loc)) * 0.09
                else:
                    # Otherwise, calculate score based on Levenshtein distance ratio
                    score = max(_calculate_levenshtein_ratio(normalized_event_location, key),
                                _calculate_levenshtein_ratio(full_normalized_event_loc, key),
                                _calculate_levenshtein_ratio(normalized_event_name, key) if len(normalized_event_name) > 5 else 0)

                # Match if score is above threshold and better than the current best
                if score >= 0.85 and score > best_score: # Using a higher threshold for Levenshtein
                    best_score = score
                    best_match_key = key

    # If no match, fall back to checking the source site name.
    if not best_match_key:
        normalized_source_site = _normalize_location_name(source_site_name)
        for key in locations_map:
            score = _calculate_levenshtein_ratio(normalized_source_site, _normalize_location_name(key))
            if score >= 0.85 and score > best_score:
                #print(f"  - Matched location via fallback to source: '{normalized_source_site}' ({key}) for event at '{full_normalized_event_loc}'")
                best_score = score
                best_match_key = key

    if best_match_key:
        #if len(potential_matches) > 1 and best_score < 1.0: # Don't log for perfect-scoring but non-exact matches
        #    print(f"  - Multiple location matches for '{full_normalized_event_loc}': {potential_matches}. Selected best match: '{best_match_key}'")
        return locations_map.get(best_match_key)

    # If still no match, log it and return None.
    unmapped_location_str = f"'{location_name_raw}'"
    if sublocation_name_raw:
        unmapped_location_str += f" / '{sublocation_name_raw}'"
    #print(f"  - Could not map location: {unmapped_location_str} (for site '{source_site_name}')")
    return None

def process_response(gemini_response_text, source_filename, locations_map):
    """
    Processes the text response from Gemini, parses the Markdown table,
    enriches it with location data, and saves it as a JSON file.
    """

    if not gemini_response_text or not gemini_response_text.strip():
        return

    lines = gemini_response_text.strip().split('\n')
    expected_headers = ['name', 'location', 'sublocation', 'start_date', 'start_time', 'end_date', 'end_time', 'description', 'url', 'hashtags', 'emoji']
    headers = [h.strip() for h in lines[0].strip().strip('|').split('|')]
    
    if headers != expected_headers:
        #print(f"Error: Headers in {source_filename} do not match the expected format.")
        #print(f"Expected: {expected_headers}")
        #print(f"Found:    {headers}")
        #print(f"Attempting parsing anyway...")
        headers = expected_headers
    
    current_date = datetime.now().date()
    future_limit_date = (datetime.now() + timedelta(days=90)).date()

    try:
        with open(os.path.join(SCRIPT_DIR, 'data', 'tags.json'), 'r', encoding='utf-8') as f:
            tag_rules = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        tag_rules = {'remove': []}

    parsed_rows = []

    if len(lines) < 2:
        #print(f"Response content for {source_filename} is not a valid Markdown table. Writing empty JSON.")
        # Extract date from source_filename (e.g., '20250912_sitename.md')
        date_match = re.match(r'(\d{8})_', source_filename)
        if date_match:
            date_str = date_match.group(1)
        else:
            date_str = datetime.now().strftime('%Y%m%d')

        output_dir = os.path.join(SCRIPT_DIR, "..", "event_data", "processed")
        dated_output_dir = os.path.join(output_dir, date_str)
        os.makedirs(dated_output_dir, exist_ok=True)

        # Remove date prefix from filename
        basename_without_date = re.sub(r'^\d{8}_', '', source_filename)
        output_filename = os.path.join(dated_output_dir, os.path.splitext(basename_without_date)[0] + ".json")
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write("[]")
        return

    for line in lines[2:]:
        if not line.strip() or line.strip().startswith('|---'):
            continue
        # the following line times out rarely in case of a Gemini failure.
        values = [v.strip() for v in re.split(r'\s*\|\s*', line.strip().strip('|'))]

        # Handle case where event name contains a pipe character
        if len(values) == len(headers) + 1:
            try:
                # Check if the potential start_date column has the correct format
                datetime.strptime(values[4], '%Y-%m-%d')
                # If it does, merge the first two columns for the name
                values = [f"{values[0]} | {values[1]}"] + values[2:]
            except ValueError:
                # The format doesn't match, so it's a genuinely malformed row
                # print(f"Warning: Skipping malformed row with {len(values)} values: {line}")
                continue
        else:
            # Check for malformed rows
            is_missing_last_optional_field = len(values) == len(headers) - 1 and line.strip().endswith('|')
            if len(values) != len(headers) and not is_missing_last_optional_field:
                #print(f"Warning: Skipping malformed row with {len(values)} values: {line}")
                continue

        row_dict = dict(zip(headers, values))

        # Sanitize text fields to remove HTML tags, entities, and normalize whitespace
        if 'name' in row_dict:
            row_dict['name'] = _sanitize_text(row_dict['name'])
            # Replace escaped pipe characters with colons
            row_dict['name'] = row_dict['name'].replace(' \\ |', ':').replace(' \\|', ':')
        if 'description' in row_dict:
            row_dict['description'] = _sanitize_text(row_dict['description'])
        if 'location' in row_dict:
            row_dict['location'] = _sanitize_text(row_dict['location'])
        if 'sublocation' in row_dict:
            row_dict['sublocation'] = _sanitize_text(row_dict['sublocation'])

        if not _filter_by_date(row_dict, current_date, future_limit_date):
            continue

        processed_row = _process_tags(row_dict, tag_rules)

        # Check for online/virtual events and add tag if necessary
        location_name_raw_check = processed_row.get('location', '').lower()
        online_keywords = ['virtual', 'online', 'livestream']
        if any(keyword in location_name_raw_check for keyword in online_keywords):
            if 'Virtual' not in processed_row.get('tags', []):
                processed_row.setdefault('tags', []).append('Virtual')

        if not _filter_by_tag(processed_row, tag_rules):
            continue

        # Extract the source site name from the filename (e.g., 'oculus' from '20250913_oculus.md')
        source_site_name = ""
        match = re.match(r'\d{8}_(.+)\.md', source_filename)
        if match:
            source_site_name = match.group(1).replace('_', ' ').lower()

        # Enrich with lat/lng coordinates
        location_name_raw = processed_row.get('location', '').strip()
        sublocation_name_raw = processed_row.get('sublocation', '').strip()
        event_name_raw = processed_row.get('name', '').strip()

        location_info = _get_location_coords(location_name_raw, sublocation_name_raw, source_site_name, event_name_raw, locations_map)

        if location_info:
            processed_row['lat'] = location_info.get('lat')
            processed_row['lng'] = location_info.get('lng')
        else:
            # Log unmapped location for debugging
            print(f" Failed to map '{processed_row.get('name', 'N/A')}' ({processed_row.get('location', 'N/A')})")

        # Process emoji: use first found, fallback to location's emoji
        # Filter out emojis that render incorrectly (box/square characters)
        emoji_from_response = processed_row.get('emoji', '')
        first_emoji = find_first_emoji(emoji_from_response)
        # Block box/square emoji that render poorly: ⬜ (U+2B1C), □ (U+25A1), ◻ (U+25FB), ⬛ (U+2B1B), ■ (U+25A0)
        blocked_emoji = {'⬜', '□', '◻', '⬛', '■', '▪', '▫', '◼', '◾', '◽', '◿', '▢', '▣', '▤', '▥', '▦', '▧', '▨', '▩'}
        if first_emoji and first_emoji not in blocked_emoji:
            processed_row['emoji'] = first_emoji
        elif location_info and location_info.get('emoji'):
            processed_row['emoji'] = location_info['emoji']

        parsed_rows.append(processed_row)

    events = _group_event_occurrences(parsed_rows)

    # Create short_name for each event after capitalization normalization
    for event in events:
        if 'name' in event:
            event['short_name'] = _create_short_name(event['name'])

    # Extract date from source_filename (e.g., '20250912_sitename.md')
    date_match = re.match(r'(\d{8})_', source_filename)
    if date_match:
        date_str = date_match.group(1)
    else:
        date_str = datetime.now().strftime('%Y%m%d')

    output_dir = os.path.join(SCRIPT_DIR, "..", "event_data", "processed")
    dated_output_dir = os.path.join(output_dir, date_str)
    os.makedirs(dated_output_dir, exist_ok=True)

    # Remove date prefix from filename
    basename_without_date = re.sub(r'^\d{8}_', '', source_filename)
    output_filename = os.path.join(dated_output_dir, os.path.splitext(basename_without_date)[0] + ".json")
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=2, ensure_ascii=False)
    #print(f"Successfully processed and saved {len(events)} events to '{output_filename}'.")

def main():
    extracted_dir = os.path.join(SCRIPT_DIR, '..', 'event_data', 'extracted')
    if not os.path.isdir(extracted_dir):
        print(f"Error: Directory '{extracted_dir}' not found.")
        return

    # Load location data once. Exit if it fails.
    try:
        locations_map = _build_locations_map()
        print(f"Successfully loaded {len(locations_map)} location entries.")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: Could not load or parse 'locations.json'. Exiting. Error: {e}")
        return

    # Iterate through dated subdirectories
    for date_subdir in os.listdir(extracted_dir):
        date_path = os.path.join(extracted_dir, date_subdir)
        if not os.path.isdir(date_path) or not re.match(r'\d{8}', date_subdir):
            continue

        for filename in os.listdir(date_path):
            if filename.endswith(".md"):
                # Check if the output JSON file already exists in processed/YYYYMMDD/
                output_dir = os.path.join(SCRIPT_DIR, "..", "event_data", "processed")
                output_filename = os.path.join(output_dir, date_subdir, os.path.splitext(filename)[0] + ".json")
                if os.path.exists(output_filename):
                    # print(f"Skipping {filename} as output file '{output_filename}' already exists.")
                    continue

                file_path = os.path.join(date_path, filename)
                # Pass filename with date prefix for tracking (matching extract_events.py format)
                source_filename_with_date = f"{date_subdir}_{filename}"
                print(f"--- Processing {source_filename_with_date} ---")
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                process_response(content, source_filename_with_date, locations_map)

if __name__ == "__main__":
    main()