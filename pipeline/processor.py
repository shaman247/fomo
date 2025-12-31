"""
Event Processing Module

Parses extracted markdown tables, enriches with location data, and stores in database.

Key features:
- Sanitizes text (removes HTML, entities, normalizes whitespace)
- Enriches events with location data (coordinates from locations table)
- Creates short names for events (removes redundant location info)
- Processes and normalizes tags (using rules from tag_rules table)
- Handles emoji extraction and validation
- Groups event occurrences
"""

import json
import os
import re
from datetime import datetime, timedelta

import regex

import db
from crawler import create_safe_filename

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

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
    """Processes the 'hashtags' string into a list of 'tags'."""
    if 'hashtags' not in row_dict:
        return row_dict

    hashtag_string = row_dict.pop('hashtags')
    rewrite_rules = tag_rules.get('rewrite', {})
    exclude_list = set(tag_rules.get('exclude', []))

    raw_tags = [tag.strip().rstrip(',') for tag in hashtag_string.split('#') if tag.strip()]
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
                event_name = event_name.title()
                event_name = re.sub(r"['']S\b", "'s", event_name)
                event_name = re.sub(r"['']T\b", "'t", event_name)
                event_name = re.sub(r"['']D\b", "'d", event_name)
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

            urls = []
            if source_url:
                urls.append(source_url)
            url = row_dict.get('url', '').strip()
            if url and url not in urls:
                urls.append(url)
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


def build_locations_map(cursor):
    """Query locations table and build tiered maps for lat/lng enrichment."""
    locations_map = {'names': {}, 'alternate_names': {}, 'short_names': {}}

    locations_data = db.get_all_locations(cursor)

    def add_if_valid(tier, key, value):
        if key and len(key) >= 3:
            tier[key] = value

    for loc in locations_data:
        info = {'lat': loc.get('lat'), 'lng': loc.get('lng'), 'emoji': loc.get('emoji')}

        main_name = loc.get('name', '')
        add_if_valid(locations_map['names'], main_name.lower(), info)
        add_if_valid(locations_map['names'], _normalize_location_name(main_name), info)

        for alt_name in loc.get('alternate_names', []):
            add_if_valid(locations_map['alternate_names'], alt_name.lower(), info)
            add_if_valid(locations_map['alternate_names'], _normalize_location_name(alt_name), info)

        short_name = loc.get('short_name', '')
        if short_name:
            add_if_valid(locations_map['short_names'], short_name.lower(), info)
            add_if_valid(locations_map['short_names'], _normalize_location_name(short_name), info)

    return locations_map


def build_websites_map():
    """Loads website data and builds a map for URL-to-extra_tags mapping."""
    websites_map = {}
    with open(os.path.join(SCRIPT_DIR, 'data', 'websites.json'), 'r', encoding='utf-8') as f:
        for website in json.load(f):
            extra_tags = website.get('extra_tags', [])
            if extra_tags:
                for url in website.get('urls', []):
                    websites_map[url.rstrip('/').lower()] = extra_tags
    return websites_map


def get_location_coords(location_name_raw, sublocation_name_raw, source_site_name, event_name_raw, locations_map):
    """Finds the best matching latitude and longitude for an event."""
    normalized_loc = _normalize_location_name(location_name_raw)
    normalized_subloc = _normalize_location_name(sublocation_name_raw)
    normalized_name = _normalize_location_name(event_name_raw)
    full_loc = f"{normalized_loc} {normalized_subloc}".strip()

    search_keys = []
    if len(full_loc) > 3:
        search_keys.append(full_loc)
    if len(normalized_loc) > 3:
        search_keys.append(normalized_loc)
    if len(normalized_name) > 3:
        search_keys.append(normalized_name)

    # Priority 1-3: Exact matches in each tier
    for tier_name in ['names', 'alternate_names', 'short_names']:
        tier = locations_map.get(tier_name, {})
        for key in search_keys:
            if key in tier:
                return tier[key]

    # Priority 4: Fuzzy matching
    all_tiers = [
        (0, locations_map.get('names', {})),
        (1, locations_map.get('alternate_names', {})),
        (2, locations_map.get('short_names', {}))
    ]

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
                        best_score, best_priority, best_result = score, priority, tier[key]

    if best_result:
        return best_result

    # Priority 5: Source site fallback
    normalized_site = _normalize_location_name(source_site_name)
    best_score = -1

    for priority, tier in all_tiers:
        for key in tier:
            score = _calculate_levenshtein_ratio(normalized_site, _normalize_location_name(key))
            if score >= 0.85 and (score > best_score or (score == best_score and priority < best_priority)):
                best_score, best_priority, best_result = score, priority, tier[key]

    return best_result


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
# Main Processing Function
# =============================================================================

def process_events(cursor, connection, crawl_result_id, website_name, run_date_str):
    """
    Process extracted events and store in crawl_events table.

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
    websites_map = build_websites_map()

    safe_filename = create_safe_filename(website_name)

    # Parse markdown table
    lines = extracted_content.strip().split('\n')
    expected_headers = ['name', 'location', 'sublocation', 'start_date', 'start_time',
                        'end_date', 'end_time', 'description', 'url', 'hashtags', 'emoji']

    if len(lines) < 2:
        db.update_crawl_result_processed(cursor, connection, crawl_result_id, 0)
        return 0

    headers = [h.strip() for h in lines[0].strip().strip('|').split('|')]
    if headers != expected_headers:
        headers = expected_headers

    current_date = datetime.now().date()
    future_limit_date = (datetime.now() + timedelta(days=90)).date()

    # Get tag rules from database
    tag_rules = db.get_tag_rules(cursor)

    parsed_rows = []

    for line in lines[2:]:
        if not line.strip() or line.strip().startswith('|---'):
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

        # Enrich with coordinates
        location_info = get_location_coords(
            processed_row.get('location', '').strip(),
            processed_row.get('sublocation', '').strip(),
            safe_filename.replace('_', ' ').lower(),
            processed_row.get('name', '').strip(),
            locations_map
        )

        if location_info:
            processed_row['lat'] = location_info.get('lat')
            processed_row['lng'] = location_info.get('lng')

        # Process emoji
        first_emoji = find_first_emoji(processed_row.get('emoji', ''))
        if first_emoji and first_emoji not in BLOCKED_EMOJI:
            processed_row['emoji'] = first_emoji
        elif location_info and location_info.get('emoji'):
            processed_row['emoji'] = location_info['emoji']

        parsed_rows.append(processed_row)

    # Group occurrences and create short names
    events = group_event_occurrences(parsed_rows, source_url)
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
                location_name, sublocation, lat, lng, url, raw_data)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                crawl_result_id,
                event_data.get('name', '')[:500],
                event_data.get('short_name', '')[:255] if event_data.get('short_name') else None,
                event_data.get('description'),
                event_data.get('emoji', '')[:10] if event_data.get('emoji') else None,
                event_data.get('location', '')[:255] if event_data.get('location') else None,
                event_data.get('sublocation', '')[:255] if event_data.get('sublocation') else None,
                event_data.get('lat'),
                event_data.get('lng'),
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
