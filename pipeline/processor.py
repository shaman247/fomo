"""
Event Processing Module

Parses extracted JSON events, enriches with location data, and stores in database.

Key features:
- Sanitizes text (removes HTML, entities, normalizes whitespace)
- Enriches events with location data (coordinates from locations table)
- Creates short names for events (removes redundant location info)
- Processes and normalizes tags (using rules from tag_rules table)
- Handles emoji extraction and validation
- Supports both JSON (structured output) and legacy markdown table formats
"""

import json
import re
from datetime import datetime, timedelta

import regex

import db
from crawler import create_safe_filename

# Blocked emoji characters that render poorly
BLOCKED_EMOJI = {'⬜', '□', '◻', '⬛', '■', '▪', '▫', '◼', '◾', '◽', '◿', '▢', '▣', '▤', '▥', '▦', '▧', '▨', '▩'}


# =============================================================================
# Text Processing Utilities
# =============================================================================

def find_first_emoji(text: str) -> str:
    """
    Finds the first emoji in a string.

    Handles simple emojis, skin-tone modifiers, variation selectors,
    and complex multi-character emojis like family groups.
    """
    emoji_pattern = regex.compile(
        r'(?:\p{Regional_Indicator}{2})'  # Flag emojis
        r'|'
        r'\p{Emoji}'
        r'[\uFE0E\uFE0F]?'  # Variation selectors
        r'[\u20E3]?'  # Keycap combining enclosing
        r'(?:\p{Emoji_Modifier})?'  # Skin tone modifiers
        r'(?:\u200D\p{Emoji}[\uFE0E\uFE0F]?(?:\p{Emoji_Modifier})?)*'  # ZWJ sequences
    )
    match = emoji_pattern.search(text)
    return match.group(0) if match else ""


def sanitize_text(text):
    """Removes HTML tags, entities, and normalizes whitespace."""
    if not text:
        return text

    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)

    # Decode common HTML entities
    html_entities = {
        '&nbsp;': ' ', '&amp;': '&', '&lt;': '<', '&gt;': '>',
        '&quot;': '"', '&#39;': "'", '&apos;': "'",
        '&ndash;': '–', '&mdash;': '—',
        '&rsquo;': "'", '&lsquo;': "'", '&rdquo;': '"', '&ldquo;': '"',
    }
    for entity, char in html_entities.items():
        text = text.replace(entity, char)

    # Normalize curly apostrophes
    text = text.replace(''', "'").replace(''', "'")

    # Replace newlines/tabs with spaces
    text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')

    # Remove invisible Unicode characters
    for char in ['\u200b', '\u200c', '\ufeff', '\u00ad']:
        text = text.replace(char, '')

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def create_short_name(name):
    """Creates a shortened version of the event name for search results."""
    if not name:
        return name

    short_name = name

    # Remove common prefixes
    prefix_patterns = [
        r'^Exhibition\s*[–:\-]\s*', r'^Talks?\s*[:\-]\s*',
        r'^Screening\s*[:\-]\s*', r'^Performance\s*[:\-]\s*',
        r'^Concert\s*[:\-]\s*', r'^Event\s*[:\-]\s*',
    ]
    for pattern in prefix_patterns:
        short_name = re.sub(pattern, '', short_name, flags=re.IGNORECASE)

    # Extract subtitle if title is long and has colon (not time)
    if len(short_name) > 40 and ':' in short_name:
        colon_idx = short_name.index(':')
        before_colon = short_name[:colon_idx]
        after_colon = short_name[colon_idx+1:]
        is_time_colon = (before_colon and before_colon[-1].isdigit() and
                         after_colon and after_colon[0].isdigit())
        if not is_time_colon:
            parts = short_name.split(':', 1)
            if len(parts[1].strip()) > 3:
                short_name = parts[1].strip()

    # Remove metadata after dash
    short_name = re.sub(r'\s+[-–]\s+.*\b(?:20\d{2}|at\s+\w).*$', '', short_name, flags=re.IGNORECASE)

    # Remove parenthetical details
    short_name = re.sub(r'\s*\([^)]*\)', '', short_name)

    # Remove Q&A, performer, venue suffixes
    short_name = re.sub(r'\s*[-–]\s*Q&A\s+with\s+.*$', '', short_name)
    short_name = re.sub(r'\s*\\?\s*\|\s*with\s+.*$', '', short_name)
    short_name = re.sub(r'\s+w/\s+.*$', '', short_name)
    short_name = re.sub(r'\s+with\s+.*$', '', short_name, flags=re.IGNORECASE)
    short_name = re.sub(r'\s+at\s+.*$', '', short_name, flags=re.IGNORECASE)
    short_name = re.sub(r'\s*@.*$', '', short_name)
    short_name = re.sub(r'\s+in\s+NYC\s*[-–].*$', '', short_name)

    # Remove date patterns
    short_name = re.sub(r'\s*[-–]\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+.*$', '', short_name)
    months = r'(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
    short_name = re.sub(rf'\s+{months}\s+\d{{1,2}}(?:st|nd|rd|th)?\s+(.+?)\s+\d{{1,2}}:\d{{2}}\s*(?:am|pm|AM|PM)?$', r' \1', short_name, flags=re.IGNORECASE)
    short_name = re.sub(rf'\s+{months}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:\s+\d{{1,2}}:\d{{2}}\s*(?:am|pm|AM|PM)?)?$', '', short_name, flags=re.IGNORECASE)

    # Remove day + time patterns
    days_short = r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)'
    short_name = re.sub(rf'\s*[-–]\s*{days_short}(?:\s+\d{{1,2}}:\d{{2}}\s*(?:am|pm)|\s*[-–]\s*\d{{1,2}}:\d{{2}}\s*(?:am|pm))?(?:\s*[-–]\s*{months})?$', '', short_name, flags=re.IGNORECASE)

    # Remove trailing times with am/pm
    short_name = re.sub(r'\s+\d{1,2}:\d{2}\s*(?:am|pm)$', '', short_name, flags=re.IGNORECASE)
    short_name = re.sub(r'\s+\d{1,2}\s*(?:am|pm)$', '', short_name, flags=re.IGNORECASE)

    return re.sub(r'\s+', ' ', short_name).strip()


# =============================================================================
# Tag Processing
# =============================================================================

def process_tags(row_dict, tag_rules, extra_tags=None):
    """Processes the 'hashtags' field (string or list) into a list of 'tags'."""
    if 'hashtags' not in row_dict:
        return row_dict

    hashtags_field = row_dict.pop('hashtags')
    rewrite_rules = tag_rules.get('rewrite', {})
    exclude_list = set(tag_rules.get('exclude', []))

    # Handle both list (JSON) and string (markdown) formats
    if isinstance(hashtags_field, list):
        raw_tags = [tag.strip() for tag in hashtags_field if tag.strip()]
    else:
        raw_tags = [tag.strip().rstrip(',') for tag in hashtags_field.split('#') if tag.strip()]

    processed_tags = []
    seen_tags = set()

    # Add extra_tags first
    if extra_tags:
        for tag in extra_tags:
            tag_normalized = tag.lower().replace(" ", "")
            if tag_normalized not in exclude_list and tag_normalized not in seen_tags:
                processed_tags.append(tag)
                seen_tags.add(tag_normalized)

    for tag in raw_tags:
        # Add spaces in camelCase
        processed_tag = re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', ' ', tag).strip()
        processed_tag = re.sub(r'([a-zA-Z])(\d+)', r'\1 \2', processed_tag)

        # Fix name patterns
        processed_tag = re.sub(r'\bMc\s+([A-Z])', r'Mc\1', processed_tag)
        processed_tag = re.sub(r'\bO\s+([A-Z])', r"O'\1", processed_tag)
        processed_tag = re.sub(r'\bSt\s+([A-Z])', r'St. \1', processed_tag)

        # Apply rewrite rules
        lookup_tag = processed_tag.lower().replace(" ", "")
        final_tag = rewrite_rules.get(lookup_tag, processed_tag)

        # Lowercase connecting words
        final_tag = re.sub(r'(?<!^)\b(A|And|Of|The|Or|In|At|On|For|To|With|From|By)\b',
                          lambda m: m.group(1).lower(), final_tag)

        # Fix number patterns
        final_tag = re.sub(r'\b(\d+)\s+K\b', r'\1K', final_tag)
        final_tag = re.sub(r'\b(\d+)\s+D\b', r'\1D', final_tag)
        final_tag = re.sub(r'(\d+)(St|Nd|Rd|Th)\b', lambda m: m.group(1) + m.group(2).lower(), final_tag)
        final_tag = re.sub(r'\b([A-Z])&([a-z])\b', lambda m: m.group(1) + '&' + m.group(2).upper(), final_tag)

        # Remove NYC prefix/suffix
        final_tag = re.sub(r'^NYC\s+', '', final_tag, flags=re.IGNORECASE)
        final_tag = re.sub(r'\s+NYC$', '', final_tag, flags=re.IGNORECASE)

        final_tag_lookup = final_tag.lower().replace(" ", "")
        if final_tag_lookup not in exclude_list and final_tag_lookup not in seen_tags:
            processed_tags.append(final_tag)
            seen_tags.add(final_tag_lookup)

    row_dict['tags'] = processed_tags
    return row_dict


def filter_by_tag(processed_row, tag_rules):
    """Filters a row based on removable tags."""
    tags_to_remove = set(tag_rules.get('remove', []))
    event_tags = set(tag.lower().replace(" ", "") for tag in processed_row.get('tags', []))
    return event_tags.isdisjoint(tags_to_remove)


# =============================================================================
# Date/Time Processing
# =============================================================================

def filter_by_date(row_dict, current_date, future_limit_date):
    """Filters a row based on its start and end dates."""
    start_date_str = row_dict.get('start_date', '').strip()
    end_date_str = row_dict.get('end_date', '').strip()

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        if start_date > future_limit_date:
            return False

        effective_end_date_str = end_date_str if end_date_str else start_date_str
        effective_end_date = datetime.strptime(effective_end_date_str, '%Y-%m-%d').date()
        if effective_end_date < current_date:
            return False

        if (effective_end_date - start_date).days > 400:
            return False
    except (ValueError, TypeError):
        return False
    return True


def _standardize_time(time_str):
    """Standardizes time formats like '6:30 PM' to '6:30pm'."""
    if not time_str:
        return ''
    normalized = time_str.lower().replace(' ', '').replace('.', '')
    if normalized == 'allday':
        return ''
    # Remove :00 suffix (e.g., '6:00pm' -> '6pm')
    return normalized.replace(':00', '')


# =============================================================================
# Event Grouping
# =============================================================================

def group_event_occurrences(rows, source_url=None):
    """Groups event rows by name and consolidates their occurrences."""

    def normalize_name_for_grouping(name):
        if not name:
            return ""
        no_underscores = name.replace('_', '')
        no_punct = re.sub(r'[^\w\s]', '', no_underscores.strip().lower())
        return re.sub(r'\s+', ' ', no_punct).strip()

    def find_matching_group_key(event_name, grouped_events):
        normalized_event = normalize_name_for_grouping(event_name)
        if event_name in grouped_events:
            return event_name
        for existing_key in grouped_events.keys():
            normalized_existing = normalize_name_for_grouping(existing_key)
            if normalized_event == normalized_existing:
                return existing_key
            if len(normalized_event) >= 5 and len(normalized_existing) >= 5:
                if normalized_event in normalized_existing or normalized_existing in normalized_event:
                    return existing_key
        return event_name

    grouped_events = {}
    for row_dict in rows:
        event_name = row_dict.get('name')
        if not event_name:
            continue

        if event_name.upper().startswith(('CANCELED:', 'CANCELLED:', 'KIM:', 'KIM -')):
            continue

        # Normalize mostly-caps names to title case
        alpha_chars = [char for char in event_name if char.isalpha()]
        if alpha_chars and len(event_name) > 5:
            num_upper = sum(1 for char in alpha_chars if char.isupper())
            if (num_upper / len(alpha_chars)) > 0.5:
                # Find two-letter acronyms before title casing (excluding common words)
                common_words = {'OF', 'OR', 'IN', 'AT', 'ON', 'TO', 'BY', 'AN', 'AS', 'IF', 'SO', 'UP', 'WE', 'NO', 'BE', 'DO', 'GO', 'HE', 'IT', 'ME', 'MY', 'US'}
                two_letter_acronyms = {m for m in re.findall(r'\b([A-Z]{2})\b', event_name) if m not in common_words}

                event_name = event_name.title()
                # Lowercase any letter after apostrophe at word boundary (handles 's, 't, 'd, 've, 'll, etc.)
                event_name = re.sub(r"[''ʼ]([A-Z])\b", lambda m: "'" + m.group(1).lower(), event_name)
                event_name = re.sub(r'(?<!^)\b(A|And|Of|The|Or|In|At|On|For|To|With|From|By)\b',
                                   lambda m: m.group(1).lower(), event_name)
                event_name = re.sub(r'\bW/', r'w/', event_name)
                event_name = re.sub(r'\b(I|Ii|Iii|Iv|V|Vi|Vii|Viii|Ix|X|Xi|Xii)\b',
                                   lambda m: m.group(1).upper(), event_name)
                event_name = re.sub(r'\b(35|65|70)Mm\b', r'\1mm', event_name)
                event_name = re.sub(r'(\d+)(St|Nd|Rd|Th)\b',
                                   lambda m: m.group(1) + m.group(2).lower(), event_name)
                event_name = re.sub(r'\b([BCDFGHJKLMNPQRSTVWXYZ])([bcdfghjklmnpqrstvwxyz])\b',
                                   lambda m: m.group(0).upper(), event_name)
                # Restore two-letter acronyms that contained vowels
                for acronym in two_letter_acronyms:
                    event_name = re.sub(r'\b' + acronym.title() + r'\b', acronym, event_name)
                row_dict['name'] = event_name

        start_date = row_dict.get('start_date', '')
        end_date = row_dict.get('end_date', '')
        if start_date and end_date and start_date == end_date:
            end_date = ''

        occurrence = [
            start_date,
            _standardize_time(row_dict.get('start_time', '')),
            end_date,
            _standardize_time(row_dict.get('end_time', ''))
        ]

        group_key = find_matching_group_key(event_name, grouped_events)

        if group_key not in grouped_events:
            base_event = {k: v for k, v in row_dict.items()
                         if k not in ['start_date', 'start_time', 'end_date', 'end_time', 'sublocation', 'url']}
            base_event['occurrences'] = []

            sublocation = row_dict.get('sublocation', '').strip()
            if sublocation and sublocation.upper() != 'N/A':
                base_event['sublocation'] = sublocation

            # Prefer event-specific URL over source_url (which is often generic)
            urls = []
            url = row_dict.get('url', '').strip()
            if url:
                urls.append(url)
            if source_url and source_url not in urls:
                urls.append(source_url)
            base_event['urls'] = urls

            grouped_events[group_key] = base_event
        else:
            existing_name = grouped_events[group_key]['name']
            if len(event_name) < len(existing_name):
                grouped_events[group_key]['name'] = event_name

            url = row_dict.get('url', '').strip()
            if url and url not in grouped_events[group_key]['urls']:
                grouped_events[group_key]['urls'].append(url)

        if occurrence not in grouped_events[group_key]['occurrences']:
            grouped_events[group_key]['occurrences'].append(occurrence)

    # Post-process: detect and clear "run end dates"
    # If multiple occurrences have the same end_date but different start_dates,
    # the end_date is likely the show's run end date, not each occurrence's end
    for event in grouped_events.values():
        occurrences = event.get('occurrences', [])
        if len(occurrences) > 3:
            # Check if all occurrences have the same non-empty end_date
            end_dates = [occ[2] for occ in occurrences if len(occ) > 2 and occ[2]]
            start_dates = [occ[0] for occ in occurrences if occ[0]]
            if end_dates and len(set(end_dates)) == 1 and len(set(start_dates)) > 3:
                # Same end_date for many different start_dates = run end date
                # Clear the end_date from all occurrences
                for occ in occurrences:
                    if len(occ) > 2:
                        occ[2] = ''

    return list(grouped_events.values())


# =============================================================================
# Location Matching
# =============================================================================

def _normalize_location_name(name):
    """Normalizes a location name for matching."""
    if not name:
        return ""

    original_lower = name.lower()
    has_dash_before_borough = any(
        f'- {b}' in original_lower or f'_{b}' in original_lower
        for b in ['queens', 'bronx', 'brooklyn', 'manhattan', 'staten island']
    )

    normalized = re.sub(r'[^\w\s]', '', original_lower)

    if normalized in ['virtual', 'online', 'livestream']:
        return ""
    if len(normalized) > 15 and normalized.startswith('the '):
        normalized = normalized[4:]

    suffixes = ['nyc', 'new york', 'brooklyn', 'manhattan', 'queens', 'bronx', 'staten island']
    if normalized in suffixes:
        return ""

    if not has_dash_before_borough:
        for suffix in suffixes:
            if normalized.endswith(f' {suffix}') and len(normalized) > len(suffix) + 2:
                normalized = normalized[:-len(f' {suffix}')].strip()
                break

    return " ".join(normalized.split())


def _calculate_levenshtein_ratio(s1, s2):
    """Calculates the Levenshtein distance ratio between two strings."""
    if not s1 or not s2:
        return 0.0
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
    return (len(s1) + len(s2) - distance) / (len(s1) + len(s2))


def _normalize_street_address(address_str):
    """Normalize a street address for matching.

    Handles common abbreviations: Ave/Avenue, St/Street, Blvd/Boulevard, etc.
    E.g., "347 Davis Avenue" -> "347 davis ave"
    """
    if not address_str:
        return None

    addr = address_str.lower().strip()

    # Common street type abbreviations (normalize to short form)
    replacements = [
        ('avenue', 'ave'),
        ('street', 'st'),
        ('boulevard', 'blvd'),
        ('drive', 'dr'),
        ('road', 'rd'),
        ('place', 'pl'),
        ('court', 'ct'),
        ('lane', 'ln'),
        ('parkway', 'pkwy'),
        ('highway', 'hwy'),
        ('east', 'e'),
        ('west', 'w'),
        ('north', 'n'),
        ('south', 's'),
    ]
    for long_form, short_form in replacements:
        # Replace as whole word (with word boundaries)
        addr = re.sub(r'\b' + long_form + r'\b', short_form, addr)

    return addr if len(addr) >= 5 else None


def _extract_street_address(full_address):
    """Extract just the street number and name from a full address.

    E.g., "347 Davis Ave, Staten Island, NY 10310, USA" -> "347 davis ave"
    """
    if not full_address:
        return None
    # Take everything before the first comma (or the whole thing if no comma)
    street_part = full_address.split(',')[0].strip()
    if not street_part or len(street_part) < 5:
        return None
    return _normalize_street_address(street_part)


def build_locations_map(cursor):
    """Query locations table and build tiered maps for lat/lng enrichment.

    Returns a dict with:
    - 'names': main location names -> info (for unique) or list (for ambiguous)
    - 'alternate_names': global alternate names (not website-scoped)
    - 'short_names': short names
    - 'addresses': street addresses (number + street name portion)
    - 'website_scoped': dict mapping website_id -> {normalized_name -> info}
    """
    locations_map = {
        'names': {},
        'alternate_names': {},
        'short_names': {},
        'addresses': {},
        'website_scoped': {},
    }

    locations_data = db.get_all_locations(cursor)

    def add_with_duplicates(tier, key, full_info):
        """Add to tier, tracking multiple locations with same name."""
        if not key or len(key) < 3:
            return
        if key not in tier:
            tier[key] = full_info
        elif isinstance(tier[key], list):
            # Already have multiple candidates
            tier[key].append(full_info)
        else:
            # Convert single to list of candidates
            tier[key] = [tier[key], full_info]

    for loc in locations_data:
        # Full info for location matching
        full_info = {
            'id': loc.get('id'),
            'name': loc.get('name'),
            'address': loc.get('address'),
            'lat': loc.get('lat'),
            'lng': loc.get('lng'),
            'emoji': loc.get('emoji')
        }
        # Simple info for backward compatibility
        info = {'lat': loc.get('lat'), 'lng': loc.get('lng'), 'emoji': loc.get('emoji')}

        main_name = loc.get('name', '')
        normalized_main = _normalize_location_name(main_name)

        # For names tier, track multiple locations with same name
        add_with_duplicates(locations_map['names'], main_name.lower(), full_info)
        if normalized_main != main_name.lower():
            add_with_duplicates(locations_map['names'], normalized_main, full_info)

        # Global alternate names (no website_id) - use full_info to include id
        for alt_name in loc.get('alternate_names', []):
            if alt_name and len(alt_name) >= 3:
                locations_map['alternate_names'][alt_name.lower()] = full_info
                normalized_alt = _normalize_location_name(alt_name)
                if normalized_alt and len(normalized_alt) >= 3:
                    locations_map['alternate_names'][normalized_alt] = full_info

        short_name = loc.get('short_name', '')
        if short_name and len(short_name) >= 3:
            locations_map['short_names'][short_name.lower()] = full_info
            normalized_short = _normalize_location_name(short_name)
            if normalized_short and len(normalized_short) >= 3:
                locations_map['short_names'][normalized_short] = full_info

        # Website-scoped alternate names
        for website_id, scoped_names in loc.get('website_scoped_names', {}).items():
            if website_id not in locations_map['website_scoped']:
                locations_map['website_scoped'][website_id] = {}
            for alt_name in scoped_names:
                if alt_name and len(alt_name) >= 3:
                    locations_map['website_scoped'][website_id][alt_name.lower()] = full_info
                    normalized_alt = _normalize_location_name(alt_name)
                    if normalized_alt and len(normalized_alt) >= 3:
                        locations_map['website_scoped'][website_id][normalized_alt] = full_info

        # Index by street address (e.g., "347 davis ave" from "347 Davis Ave, Staten Island, NY")
        address = loc.get('address', '')
        street_address = _extract_street_address(address)
        if street_address:
            locations_map['addresses'][street_address] = info

    return locations_map


def build_websites_map(cursor):
    """Builds a map for URL-to-extra_tags mapping from the database."""
    return db.get_websites_with_tags(cursor)


def get_location_id(location_name_raw, sublocation_name_raw, source_site_name, event_name_raw, locations_map, website_id=None):
    """Finds the best matching location ID for an event.

    Args:
        location_name_raw: The location name from the event
        sublocation_name_raw: The sublocation name from the event
        source_site_name: The source website name
        event_name_raw: The event name
        locations_map: The locations map from build_locations_map()
        website_id: Optional website ID for website-scoped alternate name matching

    Returns:
        Dict with id, emoji keys, or None if no match found.
    """
    normalized_loc = _normalize_location_name(location_name_raw)
    normalized_subloc = _normalize_location_name(sublocation_name_raw)
    normalized_name = _normalize_location_name(event_name_raw)
    full_loc = f"{normalized_loc} {normalized_subloc}".strip()

    # Location-only keys (for prefix matching where event names cause false positives)
    location_keys = []
    if len(full_loc) > 3:
        location_keys.append(full_loc)
    if len(normalized_loc) > 3 and normalized_loc not in location_keys:
        location_keys.append(normalized_loc)

    # All search keys including event name (for exact and fuzzy matching)
    search_keys = location_keys.copy()
    if len(normalized_name) > 3:
        search_keys.append(normalized_name)

    def make_result(info):
        """Helper to construct result dict."""
        return {
            'id': info.get('id'),
            'emoji': info.get('emoji'),
        }

    def get_first(match):
        """Get first item if list, otherwise return as-is."""
        return match[0] if isinstance(match, list) else match

    # Step 1: Website-scoped alternate names (highest priority, most specific)
    if website_id and website_id in locations_map.get('website_scoped', {}):
        website_tier = locations_map['website_scoped'][website_id]
        for key in search_keys:
            if key in website_tier:
                return make_result(website_tier[key])

    # Step 2: Exact matches in global tiers (names, alternate_names, short_names)
    for tier_name in ['names', 'alternate_names', 'short_names']:
        tier = locations_map.get(tier_name, {})
        for key in search_keys:
            if key in tier:
                return make_result(get_first(tier[key]))

    # Step 3: Address matching (e.g., "347 Davis Ave" matches location at that address)
    addresses_tier = locations_map.get('addresses', {})
    for key in search_keys:
        normalized_addr = _normalize_street_address(key)
        if normalized_addr and normalized_addr in addresses_tier:
            return make_result(addresses_tier[normalized_addr])

    # Step 4: Prefix matching (e.g., "Devocíon" matches "Devocíon (Williamsburg)")
    # Only use location_keys here to avoid matching event names to unrelated locations
    for key in location_keys:
        if len(key) >= 5:
            for loc_key, match in locations_map.get('names', {}).items():
                if loc_key.startswith(key + ' ') or loc_key.startswith(key + '('):
                    return make_result(get_first(match))

    # Step 5: Fuzzy matching across all tiers
    all_tiers = [
        (0, locations_map.get('names', {})),
        (1, locations_map.get('alternate_names', {})),
        (2, locations_map.get('short_names', {}))
    ]
    if website_id and website_id in locations_map.get('website_scoped', {}):
        all_tiers.insert(0, (-1, locations_map['website_scoped'][website_id]))

    best_result, best_score, best_priority = None, -1, 999

    if len(full_loc) > 3 or len(normalized_name) > 3:
        for priority, tier in all_tiers:
            for key in tier:
                if not key.strip():
                    continue

                is_match = (
                    key == normalized_loc or
                    (len(normalized_name) > 3 and key == normalized_name) or
                    (len(key) > 3 and (full_loc.startswith(key) or full_loc.endswith(key) or key in full_loc)) or
                    (len(normalized_loc) > 3 and normalized_loc in key) or
                    (len(normalized_subloc) > 3 and normalized_subloc in key)
                )

                if is_match:
                    if len(normalized_name) > 3 and key == normalized_name:
                        score = 1.0
                    elif len(key) > 3 and (full_loc.startswith(key) or full_loc.endswith(key)):
                        score = 0.9 + (len(key) / len(full_loc)) * 0.09
                    else:
                        score = max(
                            _calculate_levenshtein_ratio(normalized_loc, key),
                            _calculate_levenshtein_ratio(full_loc, key),
                            _calculate_levenshtein_ratio(normalized_name, key) if len(normalized_name) > 3 else 0
                        )

                    if score >= 0.85 and (score > best_score or (score == best_score and priority < best_priority)):
                        best_score, best_priority = score, priority
                        best_result = get_first(tier[key])

    if best_result:
        return make_result(best_result)

    # Step 6: Source site fallback (match website name to location)
    normalized_site = _normalize_location_name(source_site_name)
    best_score, best_result = -1, None

    for priority, tier in all_tiers:
        for key in tier:
            match = tier[key]
            if isinstance(match, list):
                continue
            score = _calculate_levenshtein_ratio(normalized_site, _normalize_location_name(key))
            if score >= 0.85 and (score > best_score or (score == best_score and priority < best_priority)):
                best_score, best_priority, best_result = score, priority, match

    if best_result:
        return make_result(best_result)

    return None


# =============================================================================
# URL Extraction
# =============================================================================

def extract_url_from_content(content):
    """Extract URL from first line of content if present."""
    if content and content.startswith('http'):
        first_newline = content.find('\n')
        if first_newline != -1:
            return content[:first_newline].strip(), content[first_newline + 1:]
    return None, content


# =============================================================================
# Parsing Functions
# =============================================================================

def _parse_json_events(extracted_content):
    """Parse JSON structured output into list of row dicts with occurrences expanded."""
    try:
        data = json.loads(extracted_content)
        events = data.get('events', [])
    except json.JSONDecodeError:
        return None  # Not valid JSON, try markdown fallback

    rows = []
    for event in events:
        # Each occurrence becomes a separate row (matching legacy behavior)
        occurrences = event.get('occurrences', [])
        if not occurrences:
            continue

        for occ in occurrences:
            row = {
                'name': event.get('name', ''),
                'location': event.get('location', ''),
                'sublocation': event.get('sublocation') or '',
                'start_date': occ.get('start_date', ''),
                'start_time': occ.get('start_time') or '',
                'end_date': occ.get('end_date') or '',
                'end_time': occ.get('end_time') or '',
                'description': event.get('description', ''),
                'url': event.get('url') or '',
                'hashtags': event.get('hashtags', []),  # Keep as list
                'emoji': event.get('emoji', ''),
            }
            rows.append(row)

    return rows


def _parse_markdown_table(extracted_content):
    """Parse legacy markdown table format into list of row dicts."""
    lines = extracted_content.strip().split('\n')
    expected_headers = ['name', 'location', 'sublocation', 'start_date', 'start_time',
                        'end_date', 'end_time', 'description', 'url', 'hashtags', 'emoji']

    if len(lines) < 2:
        return []

    headers = [h.strip() for h in lines[0].strip().strip('|').split('|')]
    if headers != expected_headers:
        headers = expected_headers

    rows = []
    for line in lines[2:]:
        if not line.strip() or line.strip().startswith('|---') or line.strip().startswith('| :---'):
            continue

        values = [v.strip() for v in re.split(r'\s*\|\s*', line.strip().strip('|'))]

        # Handle pipe in event name
        if len(values) == len(headers) + 1:
            try:
                datetime.strptime(values[4], '%Y-%m-%d')
                values = [f"{values[0]} | {values[1]}"] + values[2:]
            except ValueError:
                continue
        else:
            is_missing_last = len(values) == len(headers) - 1 and line.strip().endswith('|')
            if len(values) != len(headers) and not is_missing_last:
                continue

        row_dict = dict(zip(headers, values))
        rows.append(row_dict)

    return rows


# =============================================================================
# Main Processing Function
# =============================================================================

def process_events(cursor, connection, crawl_result_id, website_name, run_date_str):
    """
    Process extracted events and store in crawl_events table.

    Supports both JSON (structured output) and legacy markdown table formats.

    Returns:
        Number of events processed
    """
    extracted_content, website_id = db.get_extracted_content(cursor, crawl_result_id)
    if not extracted_content:
        print("    - No extracted content found")
        return 0

    crawled_content = db.get_crawled_content(cursor, crawl_result_id)
    source_url, _ = extract_url_from_content(crawled_content) if crawled_content else (None, None)

    locations_map = build_locations_map(cursor)
    websites_map = build_websites_map(cursor)

    safe_filename = create_safe_filename(website_name)

    # Try JSON first, fall back to markdown
    parsed_rows = _parse_json_events(extracted_content)
    if parsed_rows is None:
        # Fallback to markdown parsing
        parsed_rows = _parse_markdown_table(extracted_content)

    if not parsed_rows:
        db.update_crawl_result_processed(cursor, connection, crawl_result_id, 0)
        return 0

    current_date = datetime.now().date()
    future_limit_date = (datetime.now() + timedelta(days=90)).date()

    # Get tag rules from database
    tag_rules = db.get_tag_rules(cursor)

    processed_rows = []

    for row_dict in parsed_rows:
        # Sanitize fields
        for field in ['name', 'description', 'location', 'sublocation']:
            if field in row_dict:
                row_dict[field] = sanitize_text(row_dict[field])
        if 'name' in row_dict:
            row_dict['name'] = row_dict['name'].replace(' \\ |', ':').replace(' \\|', ':')

        if not filter_by_date(row_dict, current_date, future_limit_date):
            continue

        # Get extra_tags
        extra_tags_list = []
        if source_url and websites_map:
            extra_tags_list = websites_map.get(source_url.rstrip('/').lower(), [])

        processed_row = process_tags(row_dict, tag_rules, extra_tags=extra_tags_list)

        # Check for virtual events
        if any(kw in processed_row.get('location', '').lower() for kw in ['virtual', 'online', 'livestream']):
            if 'Virtual' not in processed_row.get('tags', []):
                processed_row.setdefault('tags', []).append('Virtual')

        if not filter_by_tag(processed_row, tag_rules):
            continue

        # Enrich with location ID
        location_info = get_location_id(
            processed_row.get('location', '').strip(),
            processed_row.get('sublocation', '').strip(),
            safe_filename.replace('_', ' ').lower(),
            processed_row.get('name', '').strip(),
            locations_map,
            website_id=website_id
        )

        if location_info:
            processed_row['location_id'] = location_info.get('id')

        # Process emoji
        first_emoji = find_first_emoji(processed_row.get('emoji', ''))
        if first_emoji and first_emoji not in BLOCKED_EMOJI:
            processed_row['emoji'] = first_emoji
        elif location_info and location_info.get('emoji'):
            processed_row['emoji'] = location_info['emoji']

        processed_rows.append(processed_row)

    # Group occurrences and create short names
    events = group_event_occurrences(processed_rows, source_url)
    for event in events:
        if 'name' in event:
            event['short_name'] = create_short_name(event['name'])

    # Store in database
    event_count = 0
    for event_data in events:
        if not event_data.get('name'):
            continue

        cursor.execute(
            """INSERT INTO crawl_events
               (crawl_result_id, name, short_name, description, emoji,
                location_name, sublocation, location_id, url, raw_data)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                crawl_result_id,
                event_data.get('name', '')[:500],
                event_data.get('short_name', '')[:255] if event_data.get('short_name') else None,
                event_data.get('description'),
                event_data.get('emoji', '')[:10] if event_data.get('emoji') else None,
                event_data.get('location', '')[:255] if event_data.get('location') else None,
                event_data.get('sublocation', '')[:255] if event_data.get('sublocation') else None,
                event_data.get('location_id'),
                (event_data.get('urls', [None])[0])[:2000] if event_data.get('urls') else None,
                json.dumps(event_data)
            )
        )
        crawl_event_id = cursor.lastrowid

        # Insert occurrences
        for i, occ in enumerate(event_data.get('occurrences', [])):
            if len(occ) >= 1 and occ[0]:
                try:
                    cursor.execute(
                        """INSERT INTO crawl_event_occurrences
                           (crawl_event_id, start_date, start_time, end_date, end_time, sort_order)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (crawl_event_id, occ[0], occ[1] if len(occ) > 1 else None,
                         occ[2] if len(occ) > 2 and occ[2] else None,
                         occ[3] if len(occ) > 3 else None, i)
                    )
                except Exception:
                    pass

        # Insert tags
        for tag in event_data.get('tags', []):
            if tag:
                cursor.execute(
                    "INSERT INTO crawl_event_tags (crawl_event_id, tag) VALUES (%s, %s)",
                    (crawl_event_id, tag[:100])
                )

        event_count += 1

    connection.commit()
    db.update_crawl_result_processed(cursor, connection, crawl_result_id, event_count)

    return event_count
