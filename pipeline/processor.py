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

import asyncio
import json
import os
import re
from datetime import datetime, timedelta

import regex

import db
import crawler
from constants import FUTURE_WINDOW_DAYS, FUZZY_MATCH_THRESHOLD, PREFIX_MATCH_COVERAGE
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
    Rejects bare ASCII characters (digits 0-9, #, *) which are technically
    in Unicode's Emoji category but render as plain text without keycap sequences.
    """
    emoji_pattern = regex.compile(
        r'(?:\p{Regional_Indicator}{2})'  # Flag emojis
        r'|'
        r'[0-9#*]\uFE0F\u20E3'  # Keycap sequences (e.g. 1️⃣) — must have both VS16 + enclosing keycap
        r'|'
        r'(?![0-9#*])\p{Emoji}'  # Other emoji, excluding bare digits/hash/asterisk
        r'[\uFE0E\uFE0F]?'  # Variation selectors
        r'(?:\p{Emoji_Modifier})?'  # Skin tone modifiers
        r'(?:\u200D\p{Emoji}[\uFE0E\uFE0F]?(?:\p{Emoji_Modifier})?)*'  # ZWJ sequences
    )
    match = emoji_pattern.search(text)
    return match.group(0) if match else ""


def strip_leading_emoji(text: str) -> str:
    """Strips leading emoji characters (and surrounding whitespace) from text."""
    if not text:
        return text
    emoji_pattern = regex.compile(
        r'^(?:\s*(?:'
        r'(?:\p{Regional_Indicator}{2})'  # Flag emojis
        r'|'
        r'(?:\p{Emoji_Presentation}[\uFE0E\uFE0F]?|\p{Emoji}\uFE0F)'  # Pictographic emoji (excludes bare digits)
        r'[\u20E3]?'  # Keycap combining enclosing
        r'(?:\p{Emoji_Modifier})?'  # Skin tone modifiers
        r'(?:\u200D(?:\p{Emoji_Presentation}[\uFE0E\uFE0F]?|\p{Emoji}\uFE0F)(?:\p{Emoji_Modifier})?)*'  # ZWJ sequences
        r'))+\s*'
    )
    return emoji_pattern.sub('', text)


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

    # Remove Q&A, performer, venue suffixes — only if name exceeds the map
    # label width (matches MAX_LEN in src/js/map/mapManager.js). Short titles
    # like "Java with Jo Anne" fit on the label and shouldn't be over-shortened.
    LABEL_MAX_LEN = 22
    if len(short_name) > LABEL_MAX_LEN:
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
# Tag Ancestor Map (loaded from database tag_hierarchy)
# =============================================================================

_tag_ancestor_data = None

def _load_tag_ancestor_map(cursor=None):
    """Load tag hierarchy from database, build ancestor map.

    Returns (ancestor_map, root_tags) where:
      - ancestor_map: dict mapping normalized_tag_name -> set of ancestor tag names
      - root_tags: set of normalized names for root tags (no parents, excl. Free/Virtual)

    If cursor is None, returns cached data (or empty defaults).
    """
    global _tag_ancestor_data
    if _tag_ancestor_data is not None:
        return _tag_ancestor_data

    if cursor is None:
        return {}, set()

    _tag_ancestor_data = db.build_tag_ancestor_map(cursor)
    return _tag_ancestor_data


# =============================================================================
# Tag Processing
# =============================================================================

def _disambiguate(alias_norm, processed_tags, disambiguation_rules, ancestor_map):
    """Resolve an ambiguous tag alias to a specific variant based on co-tags.

    Scoring: each rule's context contributes points to its variant equal to how
    many co-tags are the context tag itself or descendants of it. The variant
    with the highest score wins. Ties are broken by max priority among the
    rules that contributed. If no rule scored, the unconditional fallback
    (rule with ctx_name=None) is used. Returns the target tag name, or None.
    """
    rules = disambiguation_rules.get(alias_norm)
    if not rules:
        return None
    co_tag_keys = {t.lower().replace(' ', '') for t in processed_tags}
    # Build a per-co-tag ancestor set so we can count descendants relative to a context
    co_tag_ancestor_sets = {
        k: {a.lower().replace(' ', '') for a in ancestor_map.get(k, set())}
        for k in co_tag_keys
    }

    fallback = None
    variant_scores = {}  # target_name -> {'score': int, 'priority': int}
    for rule in rules:
        ctx = rule['ctx_name']
        target = rule['target_name']
        priority = rule['priority']
        if ctx is None:
            if fallback is None:
                fallback = target
            continue
        score = 0
        if ctx in co_tag_keys:
            score += 1
        for k, anc in co_tag_ancestor_sets.items():
            if ctx in anc:
                score += 1
        if score == 0:
            continue
        v = variant_scores.setdefault(target, {'score': 0, 'priority': priority})
        v['score'] += score
        v['priority'] = max(v['priority'], priority)

    if not variant_scores:
        return fallback
    return max(variant_scores.items(),
               key=lambda kv: (kv[1]['score'], kv[1]['priority']))[0]


def process_tags(row_dict, tag_rules, extra_tags=None, ancestor_map=None, root_tags=None,
                 disambiguation_rules=None):
    """Processes the 'hashtags' field (string or list) into a list of 'tags'."""
    if 'hashtags' not in row_dict:
        return row_dict

    hashtags_field = row_dict.pop('hashtags')
    rewrite_rules = tag_rules.get('rewrite', {})
    exclude_list = set(tag_rules.get('exclude', []))
    disambiguation_rules = disambiguation_rules or {}

    # Handle both list (JSON) and string (markdown) formats
    if isinstance(hashtags_field, list):
        raw_tags = [tag.strip() for tag in hashtags_field if tag.strip()]
    else:
        raw_tags = [tag.strip().rstrip(',') for tag in hashtags_field.split('#') if tag.strip()]

    processed_tags = []
    seen_tags = set()
    deferred_ambiguous = []

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

        # Defer ambiguous tags for second-pass resolution once co-tags are known
        if lookup_tag in disambiguation_rules:
            deferred_ambiguous.append(lookup_tag)
            continue

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

    # Derive ancestor tags from the database hierarchy
    if ancestor_map is None or root_tags is None:
        ancestor_map, root_tags = _load_tag_ancestor_map()

    # Second pass: resolve deferred ambiguous tags now that co-tags are known
    for alias_norm in deferred_ambiguous:
        target = _disambiguate(alias_norm, processed_tags, disambiguation_rules, ancestor_map)
        if target is None:
            continue
        target_norm = target.lower().replace(' ', '')
        if target_norm in seen_tags or target_norm in exclude_list:
            continue
        processed_tags.append(target)
        seen_tags.add(target_norm)

    if ancestor_map:
        ancestors_to_add = set()
        for tag in processed_tags:
            key = tag.lower().replace(' ', '')
            for ancestor in ancestor_map.get(key, set()):
                if ancestor.lower().replace(' ', '') not in seen_tags:
                    ancestors_to_add.add(ancestor)
        for anc in sorted(ancestors_to_add):
            processed_tags.append(anc)
            seen_tags.add(anc.lower().replace(' ', ''))

        # Fallback: add "Other" if no root-level tag was assigned
        # (Free/Virtual are cross-cutting and don't count as root tags)
        has_root = any(
            t.lower().replace(' ', '') in root_tags for t in processed_tags
        )
        if not has_root and 'other' not in seen_tags:
            processed_tags.append('Other')
            seen_tags.add('other')

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

# Grace period (days) for events with a start_date in the past but no
# explicit end_date. Covers multi-session events where only the first date
# was extracted, recently-ended one-offs whose listing hasn't updated yet,
# and timezone edge cases. Events with an explicit end_date ignore this
# grace and are rejected as soon as end_date < today.
PAST_START_GRACE_DAYS = 7


def filter_by_date(row_dict, current_date, future_limit_date):
    """Filters a row based on its start and end dates.

    Returns (True, None) if the row passes, or (False, reason) if rejected.
    Reason is one of: 'start_too_future', 'end_in_past', 'duration_too_long',
    'invalid_date'.

    When end_date is present, rejects as soon as end_date < today.
    When end_date is absent, allows a PAST_START_GRACE_DAYS grace period
    before rejecting so multi-session events and recently-ended listings
    aren't dropped on day 1.
    """
    start_date_str = row_dict.get('start_date', '').strip()
    end_date_str = row_dict.get('end_date', '').strip()

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        if start_date > future_limit_date:
            return False, 'start_too_future'

        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            if end_date < current_date:
                return False, 'end_in_past'
            duration_days = (end_date - start_date).days
        else:
            # No explicit end_date: grace period on start_date
            if start_date < current_date - timedelta(days=PAST_START_GRACE_DAYS):
                return False, 'end_in_past'
            duration_days = 0

        if duration_days > 400:
            return False, 'duration_too_long'
    except (ValueError, TypeError):
        return False, 'invalid_date'
    return True, None


# URL path segments too generic to use for grounding checks (they appear
# in site navigation / home page, not as unique event identifiers).
_GENERIC_URL_SEGMENTS = {
    '', 'events', 'event', 'calendar', 'schedule', 'programs', 'program',
    'shows', 'show', 'upcoming', 'news', 'home', 'index', 'page',
    'performances', 'performance', 'exhibitions', 'exhibition',
    'whats-on', 'tickets', 'ticket',
}


def _url_grounded_in_content(url, crawled_content):
    """Check whether an extracted event URL can be found in the crawled content.

    Returns True if the URL's meaningful path segment is present in content
    (likely a real event link the AI saw), False if not (likely hallucinated).

    Returns True for URLs we can't meaningfully check (no path, only generic
    segments, or very short tokens) to avoid false-positive rejections.
    """
    if not url or not crawled_content:
        return True

    # Strip protocol and query/fragment
    cleaned = re.sub(r'^https?://', '', url, flags=re.IGNORECASE)
    cleaned = cleaned.split('?', 1)[0].split('#', 1)[0].rstrip('/')
    parts = cleaned.split('/', 1)
    if len(parts) < 2 or not parts[1]:
        # Domain-only URL (e.g. https://venue.com/) — can't ground, skip check
        return True

    path = parts[1]
    # Find the most distinctive segment: longest non-generic path piece
    segments = [s for s in path.split('/') if s]
    candidate_segments = [
        s for s in segments
        if s.lower() not in _GENERIC_URL_SEGMENTS and len(s) >= 6
    ]
    if not candidate_segments:
        # Nothing distinctive to check (e.g. /events/123 numeric-only)
        # Fall back to full path substring if it's long enough
        if len(path) >= 10:
            return path in crawled_content
        return True

    # At least one distinctive segment must appear in the content
    return any(seg in crawled_content for seg in candidate_segments)


def log_rejection(cursor, connection, crawl_result_id, website_id,
                  rejection_type, stage, event_name=None, event_url=None,
                  start_date=None, end_date=None, details=None):
    """Log an extraction/detail-crawl rejection for later investigation.

    Writes to the extraction_rejections table. Does not raise on failure —
    logging must never break the pipeline.
    """
    try:
        cursor.execute(
            """INSERT INTO extraction_rejections
               (crawl_result_id, website_id, rejection_type, stage, event_name,
                event_url, extracted_start_date, extracted_end_date, details)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                crawl_result_id, website_id, rejection_type, stage,
                (event_name or '')[:500] or None,
                (event_url or '')[:2000] or None,
                start_date if start_date else None,
                end_date if end_date else None,
                details,
            ),
        )
    except Exception as e:
        print(f"    - Warning: failed to log rejection: {e}")


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

def normalize_event_name_caps(event_name):
    """Normalizes mostly-caps event names to title case with smart rules.

    Handles: connecting words, apostrophes, Roman numerals, ordinals,
    two-letter acronyms, film sizes, and w/ prefix.
    Returns the name unchanged if it's not mostly-caps or too short.
    """
    alpha_chars = [char for char in event_name if char.isalpha()]
    if not alpha_chars or len(event_name) <= 5:
        return event_name
    num_upper = sum(1 for char in alpha_chars if char.isupper())
    if (num_upper / len(alpha_chars)) <= 0.5:
        return event_name

    # Find two-letter acronyms before title casing (excluding common words)
    common_words = {'OF', 'OR', 'IN', 'AT', 'ON', 'TO', 'BY', 'AN', 'AS', 'IF', 'SO', 'UP', 'WE', 'NO', 'BE', 'DO', 'GO', 'HE', 'IT', 'ME', 'MY', 'US'}
    two_letter_acronyms = {m for m in re.findall(r'\b([A-Z]{2})\b', event_name) if m not in common_words}

    event_name = event_name.title()
    # Lowercase any letter after apostrophe at word boundary (handles 's, 't, 'd, 've, 'll, etc.)
    event_name = re.sub(r"['\u2018\u2019\u02BC]([A-Z])\b", lambda m: "'" + m.group(1).lower(), event_name)
    event_name = re.sub(r'(?<!^)\b(A|And|Of|The|Or|In|At|On|For|To|With|From|By)\b(?!\.)',
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

    return event_name


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
        event_name = normalize_event_name_caps(event_name)
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

    if normalized in ['virtual', 'online', 'livestream', 'private residence',
                      'various locations', 'zoom', 'unknown venue']:
        return ""
    if len(normalized) > 15 and normalized.startswith('the '):
        normalized = normalized[4:]

    # Strip trailing state abbreviations/names (e.g., "Brooklyn, NY" -> "brooklyn")
    state_suffixes = [' ny', ' nj', ' ct', ' new york', ' new jersey', ' connecticut']
    for ss in state_suffixes:
        if normalized.endswith(ss) and len(normalized) > len(ss) + 1:
            normalized = normalized[:-len(ss)].strip()
            break

    suffixes = ['nyc', 'new york', 'brooklyn', 'manhattan', 'queens', 'bronx', 'staten island',
                'the bronx', 'long island']
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


_ADDR_STREET_TYPES = sorted(
    {'st', 'ave', 'blvd', 'dr', 'rd', 'pl', 'ct', 'ln', 'pkwy', 'hwy',
     'broadway', 'bowery', 'way', 'sq', 'terrace', 'tpke'},
    key=len, reverse=True,
)
# Street names that can stand alone with no preceding name word (e.g. "350 Bowery").
_ADDR_STANDALONE_TYPES = {'broadway', 'bowery'}
_ADDR_LONG_TO_SHORT = {
    'avenue': 'ave', 'street': 'st', 'boulevard': 'blvd', 'drive': 'dr',
    'road': 'rd', 'place': 'pl', 'court': 'ct', 'lane': 'ln',
    'parkway': 'pkwy', 'highway': 'hwy', 'east': 'e', 'west': 'w',
    'north': 'n', 'south': 's', 'turnpike': 'tpke', 'square': 'sq',
}
_ADDR_WORD_NUMS = {
    'first': '1st', 'second': '2nd', 'third': '3rd', 'fourth': '4th',
    'fifth': '5th', 'sixth': '6th', 'seventh': '7th', 'eighth': '8th',
    'ninth': '9th', 'tenth': '10th', 'eleventh': '11th', 'twelfth': '12th',
}
_ADDR_PATTERN = re.compile(
    r'(\d+(?:-\d+)?)\s+(?:([\w.&\'\- ]+?)\s+)?(' + '|'.join(_ADDR_STREET_TYPES) + r')\b\.?',
    re.IGNORECASE,
)


def _extract_street_address_loose(s):
    """Extract first <number> <words> <street-type> match from anywhere in `s`.

    More permissive than `_extract_street_address`: handles a leading venue
    name ("Gotham Park, 1 Rose St" → "1 rose st"), trailing apt/suite suffixes,
    word ordinals ("Tenth" → "10th"), hyphenated Queens numbers ("5-52" → "552"),
    apartment-letter on house number ("161A Chrystie" → "161 chrystie st"),
    Avenue A/B/C/D, and redundant "Bowery St" / "Broadway St".
    """
    if not s:
        return None
    s = s.lower().strip()
    for long, short in _ADDR_LONG_TO_SHORT.items():
        s = re.sub(r'\b' + long + r'\b', short, s)
    for word, num in _ADDR_WORD_NUMS.items():
        s = re.sub(r'\b' + word + r'\b', num, s)
    s = re.sub(r'\b([nsew])(\d)', r'\1 \2', s)
    # Strip apartment-letter glued to house number ("161a chrystie" → "161 chrystie",
    # "626b 10th" → "626 10th") so the regex's `\d+\s+` can match.
    s = re.sub(r'\b(\d+)[a-z](?=\s)', r'\1', s)
    # Avenue A/B/C/D — the lettered suffix follows the type word, which the
    # main regex can't express. Match these explicitly.
    m_ave = re.search(r'\b(\d+)\s+ave\s+([a-d])\b', s)
    if m_ave:
        return f"{m_ave.group(1)} ave {m_ave.group(2)}"
    m = _ADDR_PATTERN.search(s)
    if not m:
        return None
    num, name, st = m.groups()
    num = num.replace('-', '')
    # "50 Bowery St" / "350 Broadway St" — the standalone street is the real
    # street name and the trailing "st" is redundant. Drop it.
    if name and name.lower() in _ADDR_STANDALONE_TYPES:
        return f"{num} {name.lower()}"
    if name:
        name = re.sub(r'[.\']+', '', name)
        name = re.sub(r'\s+', ' ', name.strip())
        return f"{num} {name} {st}"
    # Standalone street (Broadway, Bowery) — guard against bare "<n> st" matches
    if st not in _ADDR_STANDALONE_TYPES:
        return None
    return f"{num} {st}"


def sublocation_redundant_with_address(sublocation, location_address):
    """True when sublocation is just the venue address (safe to clear).

    Some scrapers (e.g. Posh.vip) put the venue's full street address into
    sublocation. After location matching, that's redundant with the matched
    location's own address — clear it. Real sub-venue values like "Studio B"
    or "5th Floor" don't parse as a street address and are preserved.
    """
    if not sublocation or not location_address:
        return False
    sub = _extract_street_address_loose(sublocation)
    addr = _extract_street_address_loose(location_address)
    return bool(sub and addr and sub == addr)


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

    # Website-linked locations (from website_locations table)
    locations_map['website_linked'] = db.get_website_locations_map(cursor)

    return locations_map


def build_websites_map(cursor):
    """Builds a map for URL-to-extra_tags mapping from the database."""
    return db.get_websites_with_tags(cursor)


def get_location_id(location_name_raw, sublocation_name_raw, source_site_name, event_name_raw, locations_map, website_id=None):
    """Finds the best matching location ID for an event.

    Matching cascade (checked in priority order, first match wins):
      1. Website-scoped alternate names (highest priority — exact match for this website)
      2. Exact name match (against names, alternate_names, short_names)
      3. Address match (normalized street address comparison)
      4. Prefix match (location name starts with known name, ≥PREFIX_MATCH_COVERAGE to avoid generics)
      5. Fuzzy match (Levenshtein ratio ≥ FUZZY_MATCH_THRESHOLD)
      6. Source site fallback (website name matches a location name)
      7. Website-linked location (single-venue websites via website_locations table)

    Each tier tries location_name, sublocation, and event_name variants.
    Within a tier, results are scored and the best match is selected.

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

    # Snapshot before adding heuristic variants. The website-scoped tier (Step 1)
    # only consults primary keys — it represents user-curated mappings that take
    # precedence over our extraction-recovery heuristics.
    primary_search_keys = location_keys.copy()
    if len(normalized_name) > 3:
        primary_search_keys.append(normalized_name)

    # Variant: handle "Branch, Room" patterns (e.g. BPL "Highlawn, Meeting Room")
    # by also trying just the part before the first comma. Some extraction passes
    # mash the room name into location instead of putting it in sublocation —
    # without this we silently miss the venue. We also try common venue-type
    # suffix completions so a bare "Highlawn" can hit "Highlawn Library".
    # ' park' deliberately omitted: too easily fuzzy-matches "X Parkway".
    if location_name_raw and ',' in location_name_raw:
        before_comma = _normalize_location_name(location_name_raw.split(',')[0])
        if before_comma and before_comma != normalized_loc and len(before_comma) > 3:
            for suffix in (' library', ' garden', ' center', ' studio', ''):
                variant = (before_comma + suffix).strip()
                if variant and variant not in location_keys:
                    location_keys.append(variant)

    # Variant: handle generic venue-type suffixes (e.g. "Pleasant Village
    # Community Garden" when DB has "Pleasant Village", or "La Petit Versailles
    # Garden" when DB has "Le Petit Versailles"). Strip and re-try.
    for suffix in (' community garden', ' garden', ' library', ' center', ' park'):
        if normalized_loc.endswith(suffix) and len(normalized_loc) > len(suffix) + 3:
            stripped = normalized_loc[:-len(suffix)].strip()
            if stripped and stripped not in location_keys:
                location_keys.append(stripped)
            break

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

    # Step 1: Website-scoped alternate names (highest priority, most specific).
    # Uses primary_search_keys, not heuristic variants — user-curated mappings
    # should win, and a per-website override deserves the original input.
    if website_id and website_id in locations_map.get('website_scoped', {}):
        website_tier = locations_map['website_scoped'][website_id]
        for key in primary_search_keys:
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
        street_addr = _extract_street_address(key)
        if street_addr and street_addr in addresses_tier:
            return make_result(addresses_tier[street_addr])

    # Step 4: Prefix matching (e.g., "Devocíon" matches "Devocíon (Williamsburg)")
    # Only use location_keys here to avoid matching event names to unrelated locations
    # Require prefix to cover >= 70% of the key to avoid generic names matching
    # specific venues (e.g., "New York City" matching "New York City Center")
    for key in location_keys:
        if len(key) >= 5:
            for loc_key, match in locations_map.get('names', {}).items():
                if loc_key.startswith(key + '(') or (
                    loc_key.startswith(key + ' ') and len(key) / len(loc_key) >= PREFIX_MATCH_COVERAGE
                ):
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

    # Token sets for the variants we're willing to fuzzy-compare against.
    # Lets a single-character typo like "La Petit Versailles" vs "Le Petit
    # Versailles" trigger fuzzy matching even though substring containment
    # fails. Tokens shorter than 4 chars are excluded so generic words don't
    # cause spurious matches.
    variant_tokens = []
    for variant in location_keys:
        toks = {t for t in variant.split() if len(t) >= 4}
        if len(toks) >= 2:
            variant_tokens.append((variant, toks))

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

                # Token-overlap tripwire: if a variant shares ≥2 long tokens
                # with this key, fuzzy-compare against all matching variants.
                # This catches single-char typos that defeat substring checks.
                matched_variants = []
                if not is_match and variant_tokens:
                    key_toks = {t for t in key.split() if len(t) >= 4}
                    for variant, toks in variant_tokens:
                        if len(toks & key_toks) >= 2:
                            matched_variants.append(variant)
                    if matched_variants:
                        is_match = True

                if is_match:
                    if len(normalized_name) > 3 and key == normalized_name:
                        score = 1.0
                    elif len(key) > 3 and (full_loc.startswith(key) or full_loc.endswith(key)) and len(key) / len(full_loc) >= PREFIX_MATCH_COVERAGE:
                        score = 0.9 + (len(key) / len(full_loc)) * 0.09
                    else:
                        score = max(
                            _calculate_levenshtein_ratio(normalized_loc, key),
                            _calculate_levenshtein_ratio(full_loc, key),
                            _calculate_levenshtein_ratio(normalized_name, key) if len(normalized_name) > 3 else 0,
                            *(_calculate_levenshtein_ratio(v, key) for v in matched_variants)
                        )

                    if score >= FUZZY_MATCH_THRESHOLD and (score > best_score or (score == best_score and priority < best_priority)):
                        best_score, best_priority = score, priority
                        best_result = get_first(tier[key])

    if best_result:
        return make_result(best_result)

    # Step 5b: Sublocation address matching
    # When name-based matching (steps 1-5) fails, try the sublocation as a street address.
    # This handles cases like location="POWRPLNT", sublocation="100 Hinsdale St, NY"
    # where the sublocation contains the actual venue address.
    # Placed after fuzzy matching to avoid overriding correct name-based matches
    # (e.g., "MoCADA Culture Lab" should fuzzy-match MoCADA, not match a different
    # venue at the same address like 651 ARTS).
    if normalized_subloc and len(normalized_subloc) > 3:
        street_addr = _extract_street_address(normalized_subloc)
        if street_addr and street_addr in addresses_tier:
            return make_result(addresses_tier[street_addr])

    # Step 6: Source site fallback (match website name to location)
    # Only fires when no real venue name was extracted — otherwise an event
    # held at a partner venue (e.g., SVA exhibition at Pfizer Building) would
    # silently get pinned to the website's home location.
    if not normalized_loc:
        normalized_site = _normalize_location_name(source_site_name)
        best_score, best_result = -1, None

        for priority, tier in all_tiers:
            for key in tier:
                match = tier[key]
                if isinstance(match, list):
                    continue
                score = _calculate_levenshtein_ratio(normalized_site, _normalize_location_name(key))
                if score >= FUZZY_MATCH_THRESHOLD and (score > best_score or (score == best_score and priority < best_priority)):
                    best_score, best_priority, best_result = score, priority, match

        if best_result:
            return make_result(best_result)

    # Step 7: Website-linked location fallback
    # When the location name is virtual/generic (normalized to empty) and the website
    # has exactly one linked location, use it. Handles "Online" events from
    # single-venue websites (e.g., MoMath "Online" → MoMath).
    # Only applies when there's no real venue name to match against.
    if website_id and not normalized_loc:
        linked = locations_map.get('website_linked', {}).get(website_id, [])
        if len(linked) == 1:
            return make_result(linked[0])

    # Step 8: Single-venue website brand-name fallback.
    # When fuzzy matching (Step 5) didn't find anything but the AI returned a
    # variant brand name (e.g. "AMC Theatres", "Regal UA Sheepshead Bay" when
    # DB has "Regal Cinema Sheepshead Bay") and the website has exactly one
    # linked location, the linked location is virtually always the right
    # answer. Two conditions either qualify:
    #   (a) substring containment in either direction (handles "AMC Theatres"
    #       inside "AMC 34th Street 14")
    #   (b) Levenshtein ratio ≥ 0.6 (handles "Regal UA Sheepshead Bay" vs
    #       "Regal Cinema Sheepshead Bay" — close but not substring)
    # Without this tier, those events end up with `location_id = NULL` and
    # never appear on the map.
    if website_id and normalized_loc:
        linked = locations_map.get('website_linked', {}).get(website_id, [])
        if len(linked) == 1:
            linked_id = linked[0].get('id')
            linked_norm_name = ''
            for tier_name in ('names', 'short_names'):
                for key, match in locations_map.get(tier_name, {}).items():
                    candidate = match[0] if isinstance(match, list) else match
                    if candidate.get('id') == linked_id:
                        linked_norm_name = key
                        break
                if linked_norm_name:
                    break
            if linked_norm_name and len(normalized_loc) >= 3:
                contains = (
                    normalized_loc in linked_norm_name or
                    linked_norm_name in normalized_loc
                )
                ratio = _calculate_levenshtein_ratio(normalized_loc, linked_norm_name)
                if contains or ratio >= 0.6:
                    return make_result(linked[0])

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
        occurrences = event.get('occurrences') or []

        if not occurrences:
            # Event extracted without date info — store with empty dates
            # so it can be flagged for investigation
            row = {
                'name': event.get('name', ''),
                'location': event.get('location', ''),
                'sublocation': event.get('sublocation') or '',
                'start_date': '',
                'start_time': '',
                'end_date': '',
                'end_time': '',
                'description': event.get('description', ''),
                'url': event.get('url') or '',
                'hashtags': event.get('hashtags', []),
                'emoji': event.get('emoji', ''),
                'missing_date': True,
            }
            rows.append(row)
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

    # Fingerprint-skip marker: extractor copied events from a prior identical
    # crawl and already marked this crawl 'processed'. Don't re-parse the empty
    # marker JSON (which would clobber the copied event count).
    if '"skipped": "fingerprint match' in extracted_content:
        cursor.execute(
            "SELECT event_count FROM crawl_results WHERE id = %s", (crawl_result_id,)
        )
        row = cursor.fetchone()
        copied = (row[0] if row and not isinstance(row, dict) else
                  (row['event_count'] if row else 0)) or 0
        print(f"    - Skipped (fingerprint match: {copied} events copied from prior crawl)")
        return copied

    crawled_content = db.get_crawled_content(cursor, crawl_result_id)
    source_url, _ = extract_url_from_content(crawled_content) if crawled_content else (None, None)

    # Load blocked location names for this website (e.g., "Chicago" for multi-city sites)
    blocked_location_names = set()
    if website_id:
        cursor.execute("SELECT blocked_location_names FROM websites WHERE id = %s", (website_id,))
        row = cursor.fetchone()
        if row and row[0]:
            blocked_location_names = {name.strip().lower() for name in row[0].split(',')}

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
    future_limit_date = (datetime.now() + timedelta(days=FUTURE_WINDOW_DAYS)).date()

    # Get tag rules, aliases, and ancestor map from database
    tag_rules = db.get_tag_rules(cursor)
    tag_aliases = db.get_tag_aliases(cursor)
    tag_rules['rewrite'].update(tag_aliases)  # aliases override rewrites
    ancestor_map, root_tags = _load_tag_ancestor_map(cursor)
    disambiguation_rules = db.get_tag_disambiguations(cursor)

    processed_rows = []
    rejection_counts = {}

    for row_dict in parsed_rows:
        # Sanitize fields
        for field in ['name', 'description', 'location', 'sublocation']:
            if field in row_dict:
                row_dict[field] = sanitize_text(row_dict[field])
        if 'name' in row_dict:
            row_dict['name'] = row_dict['name'].replace(' \\ |', ':').replace(' \\|', ':')
            row_dict['name'] = strip_leading_emoji(row_dict['name'])

        # URL grounding check: if the AI returned a URL that doesn't appear in
        # the crawled content, it's likely a hallucinated event. Log and skip.
        event_url = (row_dict.get('url') or '').strip()
        if event_url and crawled_content and not _url_grounded_in_content(event_url, crawled_content):
            log_rejection(
                cursor, connection, crawl_result_id, website_id,
                rejection_type='url_not_in_content', stage='extract',
                event_name=row_dict.get('name'), event_url=event_url,
                start_date=(row_dict.get('start_date') or None),
                end_date=(row_dict.get('end_date') or None),
                details='URL path not found in crawled content',
            )
            rejection_counts['url_not_in_content'] = rejection_counts.get('url_not_in_content', 0) + 1
            continue

        if not row_dict.get('missing_date'):
            ok, reason = filter_by_date(row_dict, current_date, future_limit_date)
            if not ok:
                if reason in ('end_in_past', 'start_too_future'):
                    log_rejection(
                        cursor, connection, crawl_result_id, website_id,
                        rejection_type=reason, stage='extract',
                        event_name=row_dict.get('name'), event_url=event_url or None,
                        start_date=(row_dict.get('start_date') or None),
                        end_date=(row_dict.get('end_date') or None),
                    )
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                continue

        # Get extra_tags
        extra_tags_list = []
        if source_url and websites_map:
            extra_tags_list = websites_map.get(source_url.rstrip('/').lower(), [])

        processed_row = process_tags(row_dict, tag_rules, extra_tags=extra_tags_list,
                                     ancestor_map=ancestor_map, root_tags=root_tags,
                                     disambiguation_rules=disambiguation_rules)

        # Check for virtual events
        if any(kw in processed_row.get('location', '').lower() for kw in ['virtual', 'online', 'livestream']):
            if 'Virtual' not in processed_row.get('tags', []):
                processed_row.setdefault('tags', []).append('Virtual')

        if not filter_by_tag(processed_row, tag_rules):
            continue

        # Skip events at blocked locations (e.g., Chicago events from multi-city websites)
        event_loc = processed_row.get('location', '').strip().lower()
        if blocked_location_names and any(blocked in event_loc for blocked in blocked_location_names):
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
    undated_count = 0
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

        # Track undated events (extracted without dates from source)
        has_valid_occurrences = any(
            len(occ) >= 1 and occ[0]
            for occ in event_data.get('occurrences', [])
        )
        if not has_valid_occurrences:
            undated_count += 1

        event_count += 1

    connection.commit()
    db.update_crawl_result_processed(cursor, connection, crawl_result_id, event_count)

    if undated_count > 0:
        print(f"    - ⚠️ {undated_count} event(s) extracted without dates (need investigation)")

    if rejection_counts:
        summary = ', '.join(f"{k}={v}" for k, v in rejection_counts.items())
        print(f"    - Rejected {sum(rejection_counts.values())} event(s): {summary}")

    return event_count


def apply_crawled_details(cursor, connection, ce_id, data, tag_context):
    """Apply detail-crawl data to a crawl_event row.

    Updates description, emoji, location, sublocation, occurrences, and tags
    in crawl_events/crawl_event_occurrences/crawl_event_tags.

    Args:
        cursor: DB cursor
        connection: DB connection
        ce_id: crawl_event ID
        data: dict from extract_single_event() with description, hashtags, emoji, etc.
        tag_context: tuple of (tag_rules, ancestor_map, root_tags, disambiguation_rules)
    """
    tag_rules, ancestor_map, root_tags, disambiguation_rules = tag_context

    # Process tags through pipeline rules
    row_dict = {'hashtags': data['hashtags']}
    process_tags(
        row_dict, tag_rules,
        ancestor_map=ancestor_map, root_tags=root_tags,
        disambiguation_rules=disambiguation_rules,
    )
    processed_tags = row_dict.get('tags', [])

    # Process emoji
    emoji = data.get('emoji', '')
    first_emoji = find_first_emoji(emoji) if emoji else None
    if first_emoji and first_emoji in BLOCKED_EMOJI:
        first_emoji = None

    # Update crawl_events row
    update_fields = ["description = %s", "emoji = %s"]
    update_values = [data['description'], first_emoji]

    if data.get('location'):
        update_fields.append("location_name = %s")
        update_values.append(data['location'])
    if data.get('sublocation'):
        update_fields.append("sublocation = %s")
        update_values.append(data['sublocation'])

    update_values.append(ce_id)
    cursor.execute(
        f"UPDATE crawl_events SET {', '.join(update_fields)} WHERE id = %s",
        update_values,
    )

    # Update occurrences if we got new ones
    if data.get('occurrences'):
        cursor.execute(
            "SELECT COUNT(*) FROM crawl_event_occurrences WHERE crawl_event_id = %s",
            (ce_id,),
        )
        existing_count = cursor.fetchone()[0]
        # Only replace if there were no occurrences or just one
        # (single occurrence from listing page may lack times)
        if existing_count <= 1:
            today = datetime.now().date()

            # Look up crawl_result_id + website_id for rejection logging
            cursor.execute(
                "SELECT ce.crawl_result_id, cr.website_id "
                "FROM crawl_events ce "
                "JOIN crawl_results cr ON cr.id = ce.crawl_result_id "
                "WHERE ce.id = %s",
                (ce_id,),
            )
            row = cursor.fetchone()
            cr_id, ws_id = (row[0], row[1]) if row else (None, None)

            cursor.execute(
                "DELETE FROM crawl_event_occurrences WHERE crawl_event_id = %s",
                (ce_id,),
            )
            sort_order = 0
            for occ in data['occurrences']:
                start_date = occ.get('start_date')
                if not start_date:
                    continue
                try:
                    parsed_start = datetime.strptime(str(start_date), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    continue
                end_date = occ.get('end_date')
                parsed_end = None
                if end_date:
                    try:
                        parsed_end = datetime.strptime(str(end_date), '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        end_date = None

                # Filter past occurrences: mirror filter_by_date's policy —
                # reject immediately when end_date is present and past;
                # apply PAST_START_GRACE_DAYS grace when end_date is absent
                # (covers multi-session events / recently-ended listings).
                if parsed_end:
                    past = parsed_end < today
                else:
                    past = parsed_start < (today - timedelta(days=PAST_START_GRACE_DAYS))
                if past:
                    log_rejection(
                        cursor, connection, cr_id, ws_id,
                        rejection_type='end_in_past', stage='detail_crawl',
                        event_name=data.get('name'),
                        event_url=data.get('url'),
                        start_date=start_date, end_date=end_date,
                        details=f'crawl_event_id={ce_id}',
                    )
                    continue

                cursor.execute(
                    "INSERT INTO crawl_event_occurrences "
                    "(crawl_event_id, start_date, start_time, end_date, end_time, sort_order) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (ce_id, start_date, occ.get('start_time'),
                     end_date, occ.get('end_time'), sort_order),
                )
                sort_order += 1

    # Replace tags
    cursor.execute(
        "DELETE FROM crawl_event_tags WHERE crawl_event_id = %s",
        (ce_id,),
    )
    for tag in processed_tags:
        cursor.execute(
            "INSERT INTO crawl_event_tags (crawl_event_id, tag) VALUES (%s, %s)",
            (ce_id, tag[:100]),
        )

    connection.commit()


async def crawl_event_details(cursor, connection, candidates, num_workers=10):
    """Crawl individual event pages to fill in missing details.

    For events whose listing pages lacked descriptions or locations, crawls
    the individual event URL, extracts details via Gemini, and updates
    crawl_events before the merger reads them.

    Args:
        cursor: DB cursor
        connection: DB connection
        candidates: list of (ce_id, name, url, website_id) from
            db.get_detail_crawl_candidates()
        num_workers: max concurrent crawl workers

    Returns number of events successfully updated.
    """
    from crawl4ai import AsyncWebCrawler
    import extractor  # Local import to avoid circular dependency with extractor→processor

    print(f"\n  Crawling details for {len(candidates)} event(s) with missing descriptions...")

    # Load per-website crawl + browser settings
    website_ids = {ws_id for _, _, _, ws_id in candidates}
    website_settings = db.get_website_crawl_settings(cursor, website_ids)

    # Load tag processing context
    tag_rules = db.get_tag_rules(cursor)
    tag_aliases = db.get_tag_aliases(cursor)
    tag_rules['rewrite'].update(tag_aliases)
    ancestor_map, root_tags = db.build_tag_ancestor_map(cursor)
    disambiguation_rules = db.get_tag_disambiguations(cursor)
    tag_context = (tag_rules, ancestor_map, root_tags, disambiguation_rules)

    # Build crawl configs per website (once each)
    crawl_configs = {
        ws_id: crawler.build_event_crawl_config(ws)
        for ws_id, ws in website_settings.items()
    }

    # Group events by website
    events_by_website = {}
    for event_tuple in candidates:
        ws_id = event_tuple[3]
        events_by_website.setdefault(ws_id, []).append(event_tuple)

    # Group websites by browser settings so each group shares a browser instance
    browser_batches = {}  # browser_key -> [ws_id, ...]
    for ws_id in events_by_website:
        key = crawler.get_browser_key(website_settings.get(ws_id, {}))
        browser_batches.setdefault(key, []).append(ws_id)

    # Phase 1: Crawl + extract with per-website sequential, cross-website parallel
    semaphore = asyncio.Semaphore(num_workers)
    results = []  # list of (ce_id, name, data) for successful extractions

    attempted_ids = []  # Track all attempted ce_ids for counter increment

    async def process_website(web_crawler, ws_id):
        """Process all events for one website sequentially."""
        ws_results = []
        crawl_config = crawl_configs.get(ws_id, crawler.build_event_crawl_config({}))
        for ce_id, name, url, _ in events_by_website[ws_id]:
            async with semaphore:
                attempted_ids.append(ce_id)
                content = await crawler.crawl_event_url(web_crawler, url, crawl_config)
                if not content:
                    continue
                data = await extractor.extract_single_event(name, content)
                if data:
                    ws_results.append((ce_id, name, data))
        return ws_results

    for (text_mode, light_mode, use_stealth, headed, user_agent), ws_ids in browser_batches.items():
        if len(browser_batches) > 1:
            stealth_str = ", stealth" if use_stealth else ""
            headed_str = ", headed" if headed and not use_stealth else ""
            ua_str = ", custom UA" if user_agent else ""
            event_count = sum(len(events_by_website[ws_id]) for ws_id in ws_ids)
            print(f"    Browser batch: text={text_mode}{stealth_str}{headed_str}{ua_str} ({len(ws_ids)} sites, {event_count} events)")

        browser_config = crawler.get_browser_config(
            text_mode=text_mode, light_mode=light_mode,
            use_stealth=use_stealth, headed=headed, user_agent=user_agent,
        )
        async with AsyncWebCrawler(config=browser_config) as web_crawler:
            tasks = [process_website(web_crawler, ws_id) for ws_id in ws_ids]
            for ws_results in await asyncio.gather(*tasks):
                results.extend(ws_results)

    # Increment attempt counter for all attempted events (success or failure)
    if attempted_ids:
        placeholders = ','.join(['%s'] * len(attempted_ids))
        cursor.execute(
            f"UPDATE crawl_events SET detail_crawl_attempts = detail_crawl_attempts + 1 "
            f"WHERE id IN ({placeholders})",
            attempted_ids,
        )
        connection.commit()

    # Phase 2: Apply DB updates sequentially
    enriched = 0
    for ce_id, name, data in results:
        apply_crawled_details(cursor, connection, ce_id, data, tag_context)
        enriched += 1
        location_info = f" @ {data['location']}" if data.get('location') else ""
        print(f"    + {name}{location_info}: {data['description'][:80]}...")

    print(f"  Detail-crawled {enriched}/{len(candidates)} events")
    return enriched
