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
import functools
import time
import json
from contextlib import asynccontextmanager
import re
import urllib.parse

import city_config
import subprocess
import unicodedata
from datetime import datetime, timedelta

import regex

import db
import crawler
from constants import FUZZY_MATCH_THRESHOLD, PREFIX_MATCH_COVERAGE, get_active_date_window
from crawler import create_safe_filename

# Blocked emoji characters that render poorly
BLOCKED_EMOJI = {'⬜', '□', '◻', '⬛', '■', '▪', '▫', '◼', '◾', '◽', '◿', '▢', '▣', '▤', '▥', '▦', '▧', '▨', '▩'}

# Delivery-method detection from the raw source `location` string (stored as
# `events.location_name`). Per `.claude/rules/tag-system.md` §Virtual, virtual
# events are still pinned to their organizer's venue, so `location_name` — not
# `locations.name` — is the only reliable signal, and the `Virtual` tag is what
# lets users filter them. Ordered: first match wins for the leaf; the `Virtual`
# root is always added on top of it.
# Patterns are regexes matched against the lowercased location string.
VIRTUAL_LOCATION_PATTERNS = [
    (r'\bzoom\b(?!\s*room)', 'Zoom'),          # "Zoom", "Via Zoom Platform"; not the "Zoom Room" gyms
    (r'\bwebinars?\b', 'Webinar'),
    (r'live\s*stream|livestream|streaming', 'Live Stream'),
    (r'\bvirtual\s+tour\b', 'Virtual Tour'),
    (r'\bonline\b|microsoft\s+teams|\bms\s+teams\b|google\s+meet|\bwebex\b|google\s+hangouts?',
     'Online'),
    (r'\bvirtual\b|\bremote(?:ly)?\b', None),  # root only — no platform named
]


def virtual_tags_for_location(location_str):
    """Returns the Virtual-family tags implied by a raw source location string.

    Returns [] when the string names no online delivery, else ['Virtual'] plus
    at most one platform/format leaf. Hybrids ("Online & In-Person") are
    intentionally included: they *are* attendable online, and the `Virtual` tag
    is a delivery filter, not an exclusivity claim.
    """
    loc = (location_str or '').lower()
    if not loc:
        return []
    for pattern, leaf in VIRTUAL_LOCATION_PATTERNS:
        if re.search(pattern, loc):
            return ['Virtual', leaf] if leaf else ['Virtual']
    return []


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
        r'(?:\p{Extended_Pictographic}[\uFE0E\uFE0F]?)'  # Pictographic emoji (text- or emoji-default; excludes bare digits/#/*)
        r'[\u20E3]?'  # Keycap combining enclosing
        r'(?:\p{Emoji_Modifier})?'  # Skin tone modifiers
        r'(?:\u200D\p{Extended_Pictographic}[\uFE0E\uFE0F]?(?:\p{Emoji_Modifier})?)*'  # ZWJ sequences
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
        _region_tok = city_config.region_tag_token()
        if _region_tok:
            short_name = re.sub(rf'\s+in\s+{re.escape(_region_tok)}\s*[-–].*$', '', short_name)

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


def load_tag_context(cursor):
    """Load the tag-processing context: (tag_rules, ancestor_map, root_tags, disambiguation_rules).

    `tag_rules` has the tag aliases merged into its 'rewrite' dict (aliases
    override rewrites). The ancestor map comes from _load_tag_ancestor_map, which
    is process-cached, so repeated calls within a run reuse the same data
    (tag_hierarchy is immutable mid-run). Consolidates the identical block that
    process_events and crawl_event_details previously built inline.
    """
    tag_rules = db.get_tag_rules(cursor)
    tag_rules['rewrite'].update(db.get_tag_aliases(cursor))  # aliases override rewrites
    ancestor_map, root_tags = _load_tag_ancestor_map(cursor)
    disambiguation_rules = db.get_tag_disambiguations(cursor)
    return tag_rules, ancestor_map, root_tags, disambiguation_rules


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
    co_tag_keys = {db.normalize_tag_key(t) for t in processed_tags}
    # Build a per-co-tag ancestor set so we can count descendants relative to a context
    co_tag_ancestor_sets = {
        k: {db.normalize_tag_key(a) for a in ancestor_map.get(k, set())}
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
            tag_normalized = db.normalize_tag_key(tag)
            if tag_normalized not in exclude_list and tag_normalized not in seen_tags:
                processed_tags.append(tag)
                seen_tags.add(tag_normalized)

    # Region prefix/suffix patterns are constant for the whole call (lru_cached
    # config); compile once. Empty token => no-op, same as the inline guard.
    _region_tok = city_config.region_tag_token()
    if _region_tok:
        _rt = re.escape(_region_tok)
        _region_prefix_pat = re.compile(rf'^{_rt}\s+', re.IGNORECASE)
        _region_suffix_pat = re.compile(rf'\s+{_rt}$', re.IGNORECASE)
    else:
        _region_prefix_pat = None
        _region_suffix_pat = None

    for tag in raw_tags:
        # Add spaces in camelCase
        processed_tag = re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', ' ', tag).strip()
        processed_tag = re.sub(r'([a-zA-Z])(\d+)', r'\1 \2', processed_tag)

        # Fix name patterns
        processed_tag = re.sub(r'\bMc\s+([A-Z])', r'Mc\1', processed_tag)
        processed_tag = re.sub(r'\bO\s+([A-Z])', r"O'\1", processed_tag)
        processed_tag = re.sub(r'\bSt\s+([A-Z])', r'St. \1', processed_tag)

        # Apply rewrite rules
        lookup_tag = db.normalize_tag_key(processed_tag)

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

        # Remove region prefix/suffix (e.g. "NYC Comedy" -> "Comedy")
        if _region_prefix_pat is not None:
            final_tag = _region_prefix_pat.sub('', final_tag)
            final_tag = _region_suffix_pat.sub('', final_tag)

        final_tag_lookup = db.normalize_tag_key(final_tag)
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
        target_norm = db.normalize_tag_key(target)
        if target_norm in seen_tags or target_norm in exclude_list:
            continue
        processed_tags.append(target)
        seen_tags.add(target_norm)

    if ancestor_map:
        ancestors_to_add = set()
        for tag in processed_tags:
            key = db.normalize_tag_key(tag)
            for ancestor in ancestor_map.get(key, set()):
                if db.normalize_tag_key(ancestor) not in seen_tags:
                    ancestors_to_add.add(ancestor)
        for anc in sorted(ancestors_to_add):
            processed_tags.append(anc)
            seen_tags.add(db.normalize_tag_key(anc))

        # Fallback: add "Other" if no root-level tag was assigned
        # (Free/Virtual are cross-cutting and don't count as root tags)
        has_root = any(
            db.normalize_tag_key(t) in root_tags for t in processed_tags
        )
        if not has_root and 'other' not in seen_tags:
            processed_tags.append('Other')
            seen_tags.add('other')

    row_dict['tags'] = processed_tags
    return row_dict


def filter_by_tag(processed_row, tag_rules):
    """Filters a row based on removable tags."""
    tags_to_remove = set(tag_rules.get('remove', []))
    event_tags = set(db.normalize_tag_key(tag) for tag in processed_row.get('tags', []))
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

    Open-ended runs ("Through Aug 22") arrive with an end_date and NO
    start_date; row_dict['start_date'] is backfilled with today so the row
    survives (see below).
    """
    start_date_str = (row_dict.get('start_date') or '').strip()
    end_date_str = (row_dict.get('end_date') or '').strip()

    # Open-ended run: an exhibition listed only by its closing date ("Through
    # Aug 22") comes back from Gemini as {"start_date": null, "end_date":
    # "2026-08-22"}. strptime('') used to raise here, the row was rejected as
    # 'invalid_date', and — because a rejected row never becomes a crawl_event —
    # archive_outdated_events then archived the show as absent-from-crawl while
    # it was still on the page (MoMA's Marcel Duchamp, e66269, across three
    # crawls). The run IS happening today, so today is the correct start.
    # Rows with NEITHER date fall through unchanged and stay 'invalid_date'.
    if not start_date_str and end_date_str:
        try:
            open_run_end = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return False, 'invalid_date'
        if open_run_end < current_date:
            return False, 'end_in_past'
        start_date_str = current_date.strftime('%Y-%m-%d')
        row_dict['start_date'] = start_date_str

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


def log_rejection(cursor, crawl_result_id, website_id,
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


# High-precision "this is not a real public event" name patterns. Kept
# deliberately conservative — these must (almost) never match a genuine event,
# since matches are dropped at extraction time before they ever become a
# crawl_event. Broader / fuzzier heuristics live in
# scripts/find_review_candidates.py, which only flags events for human review.
# Patterns are matched case-insensitively against the (sanitized) event name.
_NON_EVENT_NAME_PATTERNS = [
    # Calls for submissions / applications / grants (not attendable events)
    r'\bopen call\b',
    r'\bcall for (artists?|art|submissions?|entries|proposals|vendors?|applicants?|papers?|works?)\b',
    r'\bsubmissions?\s+(period|deadline|window|open|guidelines)\b',
    r'^\s*submissions?\s*:',
    r'\b(now\s+)?accepting\s+(submissions|applications|entries|proposals)\b',
    r'^\s*grants?\s*:',
    r'\bmicro[\s-]?grants?\b',
    r'\bgrants?\s+(cycle|round|application|deadline)\b',
    # Program/initiative announcements that lead with "Announcing ..." — a press
    # release about a residency, fellowship or partnership, not something you
    # attend ("Announcing PlayCo & Švanda Theatre Residency Exchange", e199661).
    # Vetoed when the name also names an attendable occasion, so the announcement
    # OF an event survives ("Announcing the Winners: Awards Ceremony").
    r'^\s*announcing\b(?!.*\b(ceremony|reception|party|gala|concert|screening|'
    r'performance|showcase|festival|opening|premiere|celebration|awards?|night|'
    r'launch|tour|talk|workshop|class|reading|film|show|club|series|meetup|'
    r'open\s+house|session)\b)',
    # Season/program announcements ("Upcoming 2026 Exhibitions", e199675).
    # Start-anchored so a real event that merely contains the words survives
    # ("Upcoming Exhibition Opening Reception", "2026 Exhibitions Curator Talk").
    #
    # A sibling "Save the Date" prefix rule was tried and REJECTED: it matched
    # 7 of 7 live events on 2026-07-26 (e138919 Randalls Island Full Moon Ride,
    # e180036 Art of Fairy Tales Symposium, e186058 Flight Night, e187265 Demo
    # Rinpoche, e189389 ArtTable Leadership Series, e199776 MOCA Mid-Autumn
    # Festival, e184215 Brompton Urban Challenge) — venues use "Save the Date"
    # as a marketing prefix on fully-scheduled events, not as a placeholder.
    r'^\s*upcoming\s+20\d{2}\b',
    # Venue operating hours published as an "event" ("Museum Open Daily",
    # e200267; "Gallery Hours"; "Open Daily, April – December"). The ENTIRE name
    # must be the hours notice, so real programming that contains the words is
    # untouched: "Gallery Hours Happy Hour", "Open Daily Meditation Practice",
    # "After Hours at the Museum", "Open Studio Hours with the Artist".
    #
    # Two precision guards learned from the live corpus:
    #  - a leading venue noun (or the literal "Open Daily") is required, or a
    #    bare "Hours" would eat the film "The Hours";
    #  - the optional trailing clause may contain ONLY schedule tokens (months,
    #    weekdays, numbers, am/pm, "year-round", …). An earlier `.{0,60}` tail
    #    swallowed "Gallery Hours - New Jersey Birds X New Jersey Artists"
    #    (e81745), a real exhibition listed by its viewing hours.
    r'^\s*(?:the\s+)?(?:'
    r'open\s+daily'
    r'|(?:museum|gallery|galleries|garden|gardens|shop|store|library|park|zoo|'
    r'aquarium|conservatory|farm|barn|observatory|planetarium|grounds|'
    r'visitor\s+cent(?:er|re)|exhibit(?:ion)?s?)\s+'
    r'(?:open\s+daily|hours(?:\s+of\s+operation)?)'
    r')(?:\s*[,:–—-]\s*(?:(?:'
    r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*|'
    r'(?:mon|tues?|wed(?:nes)?|thur?s?|fri|sat(?:ur)?|sun)(?:day)?s?|'
    r'\d{1,4}(?:st|nd|rd|th)?|[ap]\.?m\.?|noon|midnight|'
    r'thru|through|to|and|until|year[\s-]?round|daily|weekends?|weekdays?|'
    r'hours?|closed|open|except|holidays?'
    r')(?:[\s,:/&–—-]+|$))+)?\s*$',
    # Casting / talent-recruitment calls (auditions to be cast or hired, not an
    # attendable public event — sibling of "open call" above). High precision:
    # "casting call" is unambiguous; the "<role> wanted/needed/sought" forms
    # match recruitment notices ("Models Wanted", "Dancers Needed").
    r'\bcasting call\b',
    r'\b(models?|actors?|dancers?|performers?|stylists?|extras?|vocalists?|musicians?)\s+(wanted|needed|sought)\b',
    # Closures / cancellations (venue/program notices, not events)
    r'\bclosed\s*[:\|\-—]',
    r'\bclosed\s+(to the public|for|on|due|until|this|next|all)\b',
    r'\b(museum|library|park|gallery|office|building|city hall|center|centre|garden|gym|pool|branch|store|shop|hall|room\b[^a-z]*\w*)\s+clos(ed|es|ure)\b',
    # Estate / nature-preserve closure notices, added for the recurring Duke
    # Farms "Campus Closed" weekly notice (captured as an event 13 times) and
    # its "Farm Barn Cafe CLOSED" sibling. Same shape as the venue-noun rule
    # above — the noun must sit immediately before the closure word — plus a
    # lookahead veto so a real programmed event ABOUT a closure survives
    # ("Trail Closure Workshop", e166530).
    r'\b(campus|grounds|farm|trails?|preserve|conservatory|arboretum|zoo|aquarium|caf[eé])'
    r'\s+clos(ed|es|ure)\b'
    r'(?!(?:\s+[\w&\'-]+){0,2}\s+(?:workshop|talk|tour|hike|walk|class|meeting|discussion|panel|'
    r'seminar|celebration|party|festival|program|series|lecture|session))',
    r'\bcloses?\s+(early|today|tonight|at\s+\d|\d)',
    r'^\s*closed\s+(today|tonight|this\s+(?:week|weekend|morning|afternoon|evening))\b',
    # "No <thing> Today" cancelled-instance notices. The interior character
    # classes allow hyphens/apostrophes/slashes so compound program names match
    # ("No Walk-In Class Today", "No Drop-in Open Gym This Week"); the original
    # `[\w\s]*` form broke on the hyphen in "Walk-In" and let those through.
    # Both a program noun AND a temporal marker are required, which is what
    # keeps genuine "No ..." events alive ("No Pants Subway Ride").
    #
    # Dark-night notices are the same shape with a performance noun and a
    # HOLIDAY instead of "today": a venue announces it is not programming over a
    # long weekend ("No Shows - Labor Day Weekend", e214750 Brooklyn Comedy
    # Collective, which reached the map and was hand-suppressed at
    # classification on 2026-08-09). Both extensions are required together — a
    # bare `^No Show` would eat 54 Below's real cabaret **"No Show"** (e20967),
    # and it is the temporal marker that spares it. Measured over all 183,900
    # events: the noun+holiday extension adds exactly ONE match (214750), loses
    # none of the 10 the pattern already had, and leaves "No Show" untouched.
    r'^\s*no\s+[\w\s\-\'/&]{0,40}\b(program|programming|class|classes|session|'
    r'sessions|service|services|meeting|meetings|practice|rehearsal|'
    r'show|shows|performance|performances|screening|screenings|matinee|matinees|'
    r'story\s*time|open\s*gym|drop[\s-]?in|hours)\b[\w\s\-\'/&]{0,25}\b'
    r'(today|tonight|this\s+(?:week|weekend|morning|afternoon|evening|month)|'
    r'(?:labor|memorial|presidents?\'?|columbus|veterans?|independence|'
    r'new\s+year\'?s?)\s+day(?:\s+weekend)?|thanksgiving|christmas|halloween|'
    r'easter|holiday\s+weekend)\b',
    # Cancelled-instance notices. Venues announce a dead occurrence by editing
    # the title rather than pulling the row. Three unambiguous shapes only:
    # a "CANCELLED:" prefix, a trailing "(CANCELLED)" / "- CANCELED" marker,
    # and an explicit "<X> is/has been cancelled" sentence. A bare "cancel"
    # anywhere is deliberately NOT matched — real events discuss cancel
    # culture, cancelled plans, etc.
    r'^\s*cancell?ed\s*[:\|\-—]',
    r'[\(\[\-—|]\s*cancell?ed\s*[\)\]]?\s*$',
    r'\b(?:is|are|has\s+been|have\s+been|was|were)\s+cancell?ed\b',
    r'^\s*(?:class|classes|session|program|meeting|show|screening|performance|'
    r'practice|rehearsal|tour|workshop|service|game)e?s?\s+cancell?ed\b',
    # Rentals / venue marketing (selling the space, not hosting an event).
    # NOTE: a bare "RENTAL:" prefix is NOT auto-dropped — venues use it as an
    # internal booking label on public events too (rented-out dance parties,
    # comedy shows). Only match the rental *listing itself* ("Space Rental",
    # "Point Rental"); leave bare-prefix cases to editorial review.
    r'\b(venue|space|room|hall|studio|facility|point|field|court|table)\s+rental\b',
    r'\bavailable for (booking|rent|hire|private|your)\b',
    r'\bprivate\s+(rental|booking)\b',
    # Production / location-shoot booking notices. Community gardens and small
    # venues post these to warn that a film crew has the space — the venue stays
    # open and there is nothing to attend ("Film Shooting – Happy Accidents",
    # event 200503 at La Plaza Cultural, 2026-07-27).
    # Deliberately requires a SEPARATOR after the shoot phrase, or the phrase to
    # be the entire name: "Photo Shoot Workshop" and "Video Shoot Basics" are
    # real classes and must survive. Note "shoot" never matches "screening", so
    # film screenings are unaffected.
    r'^\s*(film|photo|video|tv|television|commercial)\s+shoot(ing)?\s*(?:[:\|\-—–]|$)',
    # Season passes / passes-for-sale
    r'\bseason\s*pass\b',
    r'\bsummer\s*pass\b',
    # Registration / enrollment notices — the sign-up window itself, not an
    # attendable event. Anchored to the start of the name so genuine events that
    # merely contain the word (e.g. "Voter Registration Drive", "Open
    # Registration Soccer Tournament") are not dropped.
    r'^\s*registration\s+(for|is|now|open|opens?|closes?|closed|deadline|required|begins?|ends?|available)\b',
    r'^\s*(class|workshop|camp|program|course|session)\s+registration\b',
    # Academic-calendar day markers (school/library sources leak these as "events")
    r'^\s*(first|last)\s+day\s+of\s+(the\s+)?(\d{4}\s*[-–/]\s*\d{2,4}\s+)?school\b',
    r'^\s*no\s+school\b',
    # Early-dismissal / half-day school markers ("Fair Lawn Schools Early
    # Dismissal"). A fixed school-calendar phrase, never an attendable event.
    r'\bearly\s+dismissal\b',
    # Civic date markers (election / voting days leak from government & library
    # calendars as "events"). Anchored to the END of the name so attendable
    # election-night occasions survive ("Election Day Watch Party", "Election
    # Returns Social"); only the bare marker is dropped.
    r'^\s*(primary|general|presidential|municipal|special|run[\s-]?off|local|state|federal|school\s+board|village|town|county|borough)?\s*election\s+day\s*(\d{4})?\s*$',
    r'^\s*(presidential\s+)?primary\s+(election\s+)?day\s*(\d{4})?\s*$',
    # Donation drop-off notices (a collection, not an attendable event)
    r'\bdonations?\s+(accepted|drop[\s-]?off)\b',
    # Cinema/venue placeholder listing pages
    r'\bshowtimes\b',
    # SEO / spam injected into crawled calendars
    r'\[[^\]]*~[^\]]*\]',
    r'\bpay (my|your)\b[\w\s]{0,30}\bbill\b',
    r'\bover the phone\b',
    r'\b(customer (service|support|care)|help[\s-]?line|toll[\s-]?free)\b[\w\s]{0,20}\bnumber\b',
    # Bill-pay / account-enrollment SEO spam (vendor titles like
    # "ATT Automated Payment Enrollment No Login Required Same Day")
    r'\b(automated|automatic|same[\s-]?day|instant|24[\s-]?hour)\s+payment\b',
    r'\bpayment\s+(enrollment|portal|hotline|help[\s-]?line|processing|cent(er|re)|line)\b',
    r'\bno\s+login\s+(required|needed)\b',
    # Fundraising / donation-match campaigns (a giving drive, not an attendable
    # gathering — "Give Where Your Heart Lives Match Campaign"). Attendable
    # fundraisers put words after "campaign" ("Annual Campaign Kickoff Gala"),
    # so all but the unmistakable "match campaign" are anchored to the end of
    # the name (optionally trailed by a year). Attendable BENEFITS (benefit
    # concerts, galas) are real events and must not match here.
    r'\bmatch(ing)?\s+campaign\b',
    r'\b(donation|fundraising|giving|annual|capital)\s+campaign\s*(\d{4})?\s*$',
    r'\bgiving\s+day\s*(\d{4})?\s*$',
    # Standing physical-attraction admission tickets — a zoo / wildlife park /
    # water park / botanical garden's general admission sold as a dated "2026"
    # ticket, not a scheduled event ("Bergen County Zoo Admission 2026"). Gated
    # to true attraction venues so a show's "General Admission" ticket tier never
    # matches (only "<attraction-venue> admission").
    r'\b(zoo|aquarium|safari\s+park|wildlife\s+(?:cent(?:er|re)|preserve|park)|'
    r'water\s*park|theme\s*park|amusement\s*park|botanical\s+garden|'
    r'observation\s+deck)\s+admission\b',
    # Retail loyalty / membership marketing rows leaked from store calendars
    # ("Premium & Rewards Members Online Exclusive Bonus $10 Reward ..."). A real
    # member occasion ("Member Appreciation Night") carries an occasion word and
    # won't pair "members" with bonus/exclusive/reward/offer/deal marketing.
    r'\b(?:premium|rewards?)\s+members?\b[^.\n]{0,80}\b(?:exclusive|bonus|reward|offer|deal)\b',
    # Obvious test / placeholder rows ("Do not buy tickets test test").
    r'\btest\s+test\b',
    r'^\s*do\s+not\s+buy\b',
    # Registration-window announcements where the notice is a SUFFIX rather than
    # the start of the name ("Read a Palooza Registration Open", "Summer Camp
    # Registration Now Open"). The start-anchored rule above misses these. Gated
    # to the END of the name so events that merely mention registration mid-name
    # ("Open Registration Soccer Tournament") survive.
    r'\bregistration\s+(?:is\s+)?(?:now\s+)?opens?\s*!?\s*$',
    # Hiatus / series-paused announcements. A recurring series announces its
    # break by publishing a DATED row whose title is the announcement ("Summer
    # Hiatus ... Monthly Saturday Night Swings (Returning in Sep)"), so the
    # description still describes the real series and can't be used as a gate.
    # "Hiatus" is essentially never in a genuine event title, but a band can be
    # named it (Hiatus Kaiyote), so a bare leading "Hiatus" only counts when a
    # delimiter follows it (announcement punctuation, not a band's second word).
    r'^\s*(?:summer|winter|spring|fall|autumn|holiday|seasonal)\s+hiatus\b',
    r'^\s*hiatus\b\s*(?:[:\|\-–—]|\.{2,})',
    r'\bon\s+hiatus\b',
    # Library room-booking placeholder leaked as an "event" ("Non Library
    # Program" = a non-library use of a room; never an attendable program).
    r'^\s*non[\s-]*library\s+program\s*$',
    # Cinema "premium offering" / format / accessibility badge chips that leak
    # from theater calendars (esp. AMC) as standalone "events" — e.g. "Dolby
    # Cinema at AMC", "RealD 3D", "Laser at AMC", "70mm", "Open Caption
    # (On-screen Subtitles)". High precision: the ENTIRE name must be just the
    # format/amenity descriptor. A real screening always carries the film title
    # too ("Wicked (Open Caption)", "Oppenheimer in 70mm", "Avatar: RealD 3D"),
    # so anchoring to the whole name leaves those untouched.
    r'^\s*(?:'
    r'dolby\s+cinema(?:\s+at\s+amc)?|'
    r'dolby\s+atmos(?:\s+at\s+amc)?|'
    r'reald\s*3d|'
    r'imax(?:\s+(?:at\s+amc|with\s+laser|3d))?|'
    r'laser\s+at\s+amc|'
    r'(?:amc\s+prime|prime\s+at\s+amc)|'
    r'big\s*d|'
    r'\d{2,3}\s*mm|'
    r'(?:open|closed)\s+caption(?:ing|s)?(?:\s*\([^)]*\))?(?:\s+at\s+amc)?|'
    r'audio\s+description(?:\s+at\s+amc)?'
    r')\s*$',
]

_NON_EVENT_NAME_RE = re.compile('|'.join(_NON_EVENT_NAME_PATTERNS), re.IGNORECASE)

# Cancellation marker in the event's own URL slug. Many CMSes (NYC Parks,
# Carnegie Hall, Asia Society, Eventbrite, Bowery/Knitting Factory, MCNY, …)
# announce a cancellation by re-slugging the URL — `/events/2026/07/18/
# canceled-kids-in-motion-flynn-playground` — while leaving the VISIBLE title
# untouched. The extractor faithfully reads the clean title, so the event
# lands looking perfectly live and only a URL inspection reveals it is dead.
# The existing `CANCELED:`/`CANCELLED:` name-prefix drop in
# group_event_occurrences never fires on these because the name is clean.
#
# Must be a delimited whole word: `canceled`, `cancelled` or `postponed`
# bounded by `-`, `_`, `/` or end-of-path. That precision matters —
#   - bare `cancel` would swallow `.../382314-cancel-culture-context-gender...`
#     (a real NYU panel ABOUT cancel culture),
#   - no trailing delimiter would swallow `/events/cancelledpitched-through-friends`,
#   - `rescheduled` is deliberately EXCLUDED: a rescheduled event still happens,
#     just on a new date, and its listing carries the corrected date.
# Query strings are stripped before matching so an `?aff=…cancel…` tracking
# param can never trigger it.
#
# Measured over all 241,679 event_urls rows: 36 matches, 36 true cancellations,
# zero false positives.
_CANCELLED_URL_SLUG_RE = re.compile(
    r'[-_/](?:canceled|cancelled|postponed)(?=[-_/]|$)', re.IGNORECASE
)


def is_cancelled_by_url(url):
    """True if the event URL's path marks it cancelled/postponed.

    Venues that re-slug a cancelled event's URL but keep the original title are
    the only signal we get that the event is dead; without this the row lands
    active and indistinguishable from a real listing.
    """
    if not url:
        return False
    path = re.sub(r'^[a-z]+://[^/]*', '', url.strip(), flags=re.IGNORECASE)
    path = path.split('?')[0].split('#')[0]
    return bool(_CANCELLED_URL_SLUG_RE.search(path))


# Bare generic single-word names ("Music", "Program", "TBD") carry no event
# information; combined with a missing description they are placeholder rows the
# extractor should never have emitted. Only fires when the description is empty
# (a real event reaching here virtually always has a description), so a richly
# described event that happens to be titled "Music" is never dropped.
_BARE_GENERIC_NAME_RE = re.compile(
    r'(?:music|events?|programs?|performances?|shows?|class(?:es)?|workshops?|'
    r'sessions?|meetings?|activit(?:y|ies)|general|misc(?:ellaneous)?|untitled|'
    r'placeholder|n/?a|none|tba|tbd|'
    # Opaque calendar-availability markers. Shared/booking calendars (NYC
    # Resistor, room-reservation systems) publish these as "events" with no
    # body — they say the space is taken, not that anything is happening.
    r'busy|reserved|blocked|booked|occupied|unavailable|hold|on\s+hold|'
    r'private|closed|maintenance)',
    re.IGNORECASE)

# Placeholder screening rows: a cinema publishes an unannounced slot as
# "Untitled Movie (Angelika SoHo)" — no title, no description, 20 occurrences —
# and it comes back every run. The bare "Untitled" case is already covered by
# _BARE_GENERIC_NAME_RE; this catches the "<format> (<venue>)" shape.
#
# Precision comes from requiring "untitled" to LEAD the title and be immediately
# followed by the format word, plus a blank description. Real films whose titles
# contain the word survive: "An Untitled Horror Movie" and '"Untitled" Movie'
# don't lead with it, "Untitled Horror Movie" has a word in between, and
# "Untitled: A Dance Work" isn't followed by a format word.
_UNTITLED_PLACEHOLDER_NAME_RE = re.compile(
    r'^\s*untitled\s+(?:movie|film|feature|screening|event|program|programme|'
    r'show|performance|concert|exhibit(?:ion)?)\s*(?:\([^)]*\))?\s*$',
    re.IGNORECASE)

# Descriptions that carry no information. Merged rows use the literal
# "No description available." placeholder, so an empty-description gate must
# treat it the same as ''.
_EMPTY_DESCRIPTION_RE = re.compile(
    r'^\s*(?:no\s+description(?:\s+available)?\.?|n/?a|none|-+)?\s*$',
    re.IGNORECASE)

# Room-setup instructions in place of a description. A library/community-center
# booking system exports the room's furniture layout into the description field
# ("Theatre Style, 40 chairs."), which is contentless in exactly the way an
# empty string is — it describes the room, never the programming.
#
# Treated as BLANK rather than as junk on its own, deliberately. "Senior Movie"
# (e214155) carries this same description and is a real library screening with a
# useless body; dropping on the description alone would take it. Feeding the
# existing blank-description machinery instead means the name still has to carry
# a junk signal — which is what separates e230446 "Girl Scouts of America" (an
# org name booking a room -> dropped by `_is_org_room_booking`) from it.
#
# Corpus-checked over all 199,302 events: 2 descriptions match, both the
# "Theatre Style, 40 chairs." shape, 0 false positives.
_ROOM_SETUP_FRAGMENT_RE = re.compile(
    r'^\W*(?:'
    r'(?:theat(?:re|er)|classroom|boardroom|conference|banquet|lecture|'
    r'u[\s-]?shape[d]?|hollow\s+square|round\s*table|open\s+space)\s*'
    r'(?:style|setup|set[\s-]?up|seating)?'
    r'|\d+\s*(?:chairs?|tables?|seats?|rounds?)'
    r'|no\s+(?:setup|chairs?|tables?)'
    r'|(?:setup|set[\s-]?up|seating)\s*[:\-]?'
    r')(?:[\s,;/&+.]+|$)', re.IGNORECASE)

# Cap on how much text the setup rule will consider. A real description that
# merely opens with seating info ("Theatre style seating. Tonight the quartet
# plays...") must never be read as blank, and length is the cheap guard.
_ROOM_SETUP_MAX_CHARS = 120


def _is_room_setup_only(description):
    """True when a description is nothing but room/furniture setup instructions."""
    if not description:
        return False
    remaining = description.strip()
    if len(remaining) > _ROOM_SETUP_MAX_CHARS:
        return False
    matched = False
    for _ in range(8):
        m = _ROOM_SETUP_FRAGMENT_RE.match(remaining)
        if not m:
            break
        matched = True
        remaining = remaining[m.end():]
    if not matched:
        return False
    # Any leftover letter or digit in ANY script is real content. `isalnum`
    # rather than `[A-Za-z]` because the corpus carries CJK, Bengali and
    # Cyrillic descriptions that a Latin-only test would call empty.
    return not any(ch.isalnum() for ch in remaining)


def _description_is_blank(description):
    """True when the description carries no information at all."""
    if _EMPTY_DESCRIPTION_RE.match(description or ''):
        return True
    return _is_room_setup_only(description)


def _description_adds_nothing(name, description):
    """True when the description is blank OR merely repeats the title.

    Several junk gates below are deliberately conditioned on "no description",
    because a described row is usually a real event someone bothered to write up.
    But a feed that echoes the title into the description defeats that gate while
    adding no information at all — e2​16438 "Patron Reservation - O'Connor" carried
    the description "Patron Reservation - O'Connor" and so slipped a rule that
    matched its name exactly. `_is_seo_listicle_spam` already treats a
    title-verbatim description as title-only for the same reason; this shares that
    definition instead of restating it per-rule.

    Deliberately strict: only an exact match after whitespace/case normalisation
    counts. A description that merely STARTS with the title ("Patron Reservation -
    O'Connor. Join us for…") is real content and must not be treated as blank.
    """
    if _description_is_blank(description):
        return True
    if not name:
        return False
    norm = lambda s: re.sub(r'\s+', ' ', (s or '').strip().lower())
    return norm(name) == norm(description)

# Two-signal patterns: the name alone is ambiguous (real attendable events
# share these words), so a corroborating description signal is required before
# dropping. Same conservatism as above — a miss just means the row falls
# through to find_review_candidates.py instead.
#
# Submission-call contests: creative-work contests entered by submitting a
# piece, not by showing up ("Children's Library Card Art Contest"). Attendable
# contest EVENTS (trivia contests, dance contests, pie-eating contests) are
# real, so three gates: the name must carry a creative-work qualifier directly
# before "contest"/"competition", the description must use call-for-entries
# framing, and names signalling an attendable occasion (awards night, winners'
# screening) never match.
_SUBMISSION_CONTEST_NAME_RE = re.compile(
    r'\b(arts?|design|poster|photo(?:graphy)?|essay|writing|poetry|drawing|'
    r'coloring|logo|bookmark|recipe|video|short[\s-]story)\s+(contest|competition)\b',
    re.IGNORECASE)
_ATTENDABLE_CONTEST_NAME_RE = re.compile(
    r'\b(screening|ceremony|awards?|reception|party|showcase|show|night|gala|'
    r'festival|celebration|finale?|finals)\b', re.IGNORECASE)
_SUBMISSION_CALL_DESC_RE = re.compile(
    r'\b(submission|entry)\s+deadline\b|'
    r'\bdeadline\s+(to|for)\s+(submit|enter|entries|submissions?)\b|'
    r'\bsubmissions?\s+(are\s+|is\s+)?due\b|'
    r'\b(now\s+)?accepting\s+(submissions?|entries)\b|'
    r'\bsubmit\s+(your|an?|one|original)\b|'
    r'\bwinning\s+submissions?\b',
    re.IGNORECASE)

# Calls for applications that only reveal themselves in the DESCRIPTION. The
# name-level rules above catch "Open Call: ..." titles, but a residency or
# fellowship is usually titled after the program ("2027 Artist Residency",
# "Emerging Artists Program") with the call framing in the body. Two gates: the
# description must use unmistakable call-for-applications language, and the name
# must not name an attendable occasion (an info session or grant-writing
# workshop ABOUT applying is a real event).
#
# Deliberately NOT included: a bare "open call" / "call for artists" in the
# description. Galleries routinely describe a real, attendable exhibition by how
# its work was solicited ("an annual open call exhibition", "presents an Open
# Call: SUMMER JAM — a Non-Juried Exhibition"), and those phrases matched 5 live
# events on 2026-07-26 (e111902, e180673, e180675, e189495, e194641). The
# name-level `\bopen call\b` rule above already covers titles that ARE the call.
_APPLICATION_CALL_DESC_RE = re.compile(
    r'\b(?:now\s+)?accepting\s+applications\b|'
    r'\bapplications?\s+(?:are\s+|is\s+)?(?:now\s+)?(?:open|being\s+accepted)\b|'
    r'\bapplication\s+(?:deadline|window|period)\b|'
    r'\bdeadline\s+to\s+apply\b',
    re.IGNORECASE)
_ATTENDABLE_OCCASION_NAME_RE = re.compile(
    r'\b(session|workshop|class|classes|course|reception|ceremony|awards?|party|'
    r'gala|concert|screening|performance|panel|talk|lecture|tour|festival|'
    r'showcase|opening|premiere|celebration|meeting|orientation|open\s+house|'
    r'fair|market|reading|seminar|conference|symposium|brunch|dinner|mixer|'
    r'social|hike|walk|run|race|game|clinic|demo|demonstration|q\s*&\s*a)\b',
    re.IGNORECASE)

# Private bookings leaked from a venue's own calendar ("FAB5 @ The Jacob Javits
# Center" — description: "Private event, not open to the public.", e199703).
# Both signals are required, which is what keeps a public event that merely
# mentions private hire alive ("...the back room is also available for private
# events"), and what keeps "private view"/"private shopping appointment"
# phrasing out of scope.
_PRIVATE_BOOKING_DESC_RE = re.compile(
    r'\bprivate\s+(event|function|booking|rental|party|hire)s?\b', re.IGNORECASE)
_NOT_PUBLIC_DESC_RE = re.compile(
    r'\bnot\s+open\s+to\s+the\s+(?:general\s+)?public\b|'
    r'\bclosed\s+to\s+the\s+(?:general\s+)?public\b|'
    r'\bnot\s+a\s+public\s+event\b|'
    r'\binvitation\s+only\b|\binvite[\s-]only\b',
    re.IGNORECASE)

# ...and the one alternative above that stands on its OWN, without a "private
# event" phrase anywhere in the body. LibCal community-room bookings say it flatly
# and say nothing else about privacy — e231431 "Community Sponsored: RMA Book
# Group" (w5242 Greenwich Library) reached the map with the body "This event is
# not open to the public. This event and the content thereof are neither sponsored
# nor endorsed by Greenwich Library."
#
# ONLY this exact phrase is promoted to a single-signal rule. Measured 2026-08-24
# over ALL 1,130,648 crawl_events and all 199,916 events:
#   `not open to the (general) public`  10 crawl rows / 7 distinct, 100% junk —
#       the Greenwich book group, w2167's private Javits gig, w1771 Orchestra of
#       St. Luke's private youth recital, w1359 Capitol Theatre closed-for-private,
#       w1477 Urban Bush Women's two private engagements, w753 "Recirculation
#       Closed". TWO of them (e57177, e43668) reached the map unsuppressed.
#   `closed to the (general) public`   152 rows and NOT safe: BCPC's real,
#       public TGNC Swim Night is described as "swimming in a pool closed to the
#       public", and the phrase is ordinary prose about a facility.
#   `invitation only` / `invite-only`  256 rows and NOT safe: Downtown Music
#       Gallery's 31st-anniversary in-store series, Fabrik's "Breakfast With
#       Friends", Copland House concerts are all real, listed events.
#   `neither sponsored nor endorsed`   REFUTED as an arm of its own, see
#       `_is_not_public_notice`.
#
# The veto guards the one shape the corpus does not contain but easily could: a
# real event with a private PORTION ("the reception afterwards is not open to the
# public"). It is applied to the sentence carrying the phrase, not the whole body,
# so a private booking that happens to mention a reception elsewhere still fires.
_NOT_PUBLIC_STANDALONE_DESC_RE = re.compile(
    r'\bnot\s+open\s+to\s+the\s+(?:general\s+)?public\b', re.IGNORECASE)
_NOT_PUBLIC_PARTIAL_VETO_RE = re.compile(
    r'\b(?:portion|part|parts|segment|section|rehearsals?|receptions?|'
    r'after[\s-]?part(?:y|ies)|afterparty|backstage|green\s?room|'
    r'load[\s-]?in|first\s+(?:hour|half)|second\s+half|'
    r'dinner|q\s*&\s*a|talkback)\b',
    re.IGNORECASE)
_SENTENCE_BREAK_RE = re.compile(r'[.;!?]')


def _is_not_public_notice(name, description=None):
    """True when the body states the occasion itself is not open to the public.

    Deliberately a SINGLE-signal rule, unlike the `_PRIVATE_BOOKING_DESC_RE` +
    `_NOT_PUBLIC_DESC_RE` pair below it: a library community-room booking never
    calls itself a "private event", it just says it is not open to the public.

    The "neither sponsored nor endorsed by <library>" half of the same LibCal
    boilerplate was prototyped as its own arm and REFUTED: it is a blanket
    disclaimer the library staples onto EVERY outside-group booking, including
    fully public ones. Its 2-row hit set contains e228086 "Community Sponsored:
    Little Readers, Big Creators", a real, live children's storytime whose body
    carries the disclaimer and nothing else. Do not add it.
    """
    description = description or ''
    match = _NOT_PUBLIC_STANDALONE_DESC_RE.search(description)
    if not match:
        return False
    start = description.rfind('.', 0, match.start()) + 1
    for char in ';!?':
        start = max(start, description.rfind(char, 0, match.start()) + 1)
    end = _SENTENCE_BREAK_RE.search(description, match.end())
    sentence = description[start:end.end() if end else len(description)]
    return not _NOT_PUBLIC_PARTIAL_VETO_RE.search(sentence)


# Members-only programming — a real occasion, but attendable only by holders of
# a membership (museum member tours/previews, social-club meetups, coworking
# member sessions, gym member classes). The map lists attendable PUBLIC events,
# so these are out of scope, and the title says so itself: venues label them
# explicitly ("Members-Only Tour: …", "[MEMBERS ONLY] …", "… | MEMBERS ONLY",
# "(Members Only)", "Fabrik Member Exclusive"). e220070 (Fabrik DUMBO) reached
# the map and was hand-suppressed on 2026-08-20, joining a long hand-suppression
# trail (90906, 157004, 173129, 206565, 210142, 223832, 224595, 197142, …).
#
# NAME-ONLY on purpose: the phrase in a title is the venue's own access notice.
# A "members only" phrase in the DESCRIPTION is deliberately NOT matched —
# museums advertise a members-only preview day inside the body of a fully
# public exhibition, and "become a member" upsell copy is everywhere.
#
# Measured over all 193,909 events: "member(s) only" 146 name matches and
# "member(s) exclusive" 20 more, every one a true members-only occasion except
# a single venue NAMED "Members Only" (a West Village lounge, e5405 "New Year's
# Eve @ Members Only West Village Lounge") — which is what the venue veto is
# for: the phrase preceded by "@"/"at", or followed by a venue noun, is a place,
# not an access restriction.
_MEMBERS_ONLY_NAME_RE = re.compile(
    r'\bmembers?[\s-]+only\b|\bmembers?[\s-]?exclusive\b', re.IGNORECASE)
_MEMBERS_ONLY_VENUE_VETO_RE = re.compile(
    r'[@]\s*members?[\s-]+only\b|\b(?:at|in)\s+members\s+only\b|'
    r'\bmembers?[\s-]+only\s+(?:lounge|club|bar|tavern|venue|band|nyc)\b',
    re.IGNORECASE)

# Enrolled-student academic orientations ("New Student Orientation",
# e207564 w536 Pratt, hand-suppressed on 2026-08-20 with its two siblings) —
# a closed-audience event for a school's own incoming students, not public
# programming. NOT the same thing as a public orientation: volunteer/docent
# orientations are attendable by anyone who wants to volunteer, and the
# academic-milestone veto above deliberately spares "orientation" for exactly
# that reason — so this rule is scoped to the STUDENT form only.
#
# Two arms:
#  - the literal "…Student(s) Orientation" phrase in the name (name-only;
#    3 corpus matches, all true — Pratt ×2, NYU Performance Studies);
#  - "Orientation" in the name corroborated by a student audience in the
#    description ("A welcome and orientation day for MFA … students",
#    e207565, whose name lacks the phrase). The veto spares public
#    orientations (volunteer/docent/usher/mentor/tutor) and open-enrollment
#    phrasing ("students of all levels welcome" at a dance studio).
# Measured over all 193,909 events: the two arms together match 7 rows, all of
# them school orientations for enrolled students/their families (Pratt ×4,
# NYU ×3), 0 false positives.
_STUDENT_ORIENTATION_NAME_RE = re.compile(
    r"\b(?:new\s+)?students?'?\s+orientation\b", re.IGNORECASE)
_ORIENTATION_NAME_RE = re.compile(r'\borientation\b', re.IGNORECASE)
_STUDENT_AUDIENCE_DESC_RE = re.compile(r'\bstudents?\b', re.IGNORECASE)
_ORIENTATION_PUBLIC_VETO_RE = re.compile(
    r'\b(?:volunteer|docent|usher|mentor|tutor)s?\b|'
    r'\ball\s+levels\b|\bbeginners?\s+welcome\b|'
    r'\bopen\s+to\s+(?:the\s+)?(?:public|all|everyone)\b|'
    r'\bno\s+experience\b',
    re.IGNORECASE)

# Festival info-booth sub-listings: an org's marketing booth inside a festival
# program ("L'Alliance Booths"), not an attendable event. The name must END
# with "Booths"/"Info Booth(s)" (a name merely containing "booths" mid-phrase
# is left alone) and the description must read as visit-our-booth marketing.
_BOOTH_NAME_RE = re.compile(r'\b(info(?:rmation)?\s+booths?|booths)\s*$',
                            re.IGNORECASE)
_BOOTH_MARKETING_DESC_RE = re.compile(
    r'\b(visit|stop by|swing by|come by|find)\b[^.!?]{0,80}\bbooths?\b|'
    r'\bbooths?\b[^.!?]{0,80}\blearn more\b',
    re.IGNORECASE)

# Childcare-amenity listings: nursery/childcare offered as a convenience
# DURING another activity at the venue ("Nursery-Preschool Care ... during
# worship services"), not an attendable event itself. Children's programs and
# childcare-themed workshops ARE real events ("Toddler Storytime", "Childcare
# CPR Training", "Preschool Open House", "Kids' Night Out drop-off party"),
# so two tight gates: the name must consist ENTIRELY of childcare-amenity
# vocabulary — any other word vetoes the rule (this is what keeps
# "Babysitting 101 Training Course" and Public Records' "The Nursery: <DJ>"
# club series alive) — and the description must frame the care as provided
# during/while parents attend something else.
_CHILDCARE_AMENITY_NAME_RE = re.compile(
    r'^(?=.*\b(?:nursery|child\s*care|babysitting)\b)'
    r'(?:(?:nursery|child\s*care|preschool|babysitting|care|and)\b[\s/&-]*)+$',
    re.IGNORECASE)
_CHILDCARE_DURING_DESC_RE = re.compile(
    r'\bduring\b[^.;!?]{0,60}\b(?:worship|services?|mass|church|meetings?)\b|'
    r'\bwhile\s+(?:you|parents?|caregivers?|adults?|families)\b[^.;!?]{0,40}'
    r'\b(?:attend|participate|worship)\b|'
    r'\b(?:parents?|families|caregivers?)\s+(?:can\s+|may\s+)?attend(?:ing)?\b',
    re.IGNORECASE)

# Congregate-meal menu listings: a senior/older-adult center's daily lunch menu
# leaked one row per dish ("BBQ Pulled Pork", "Roasted Chicken Legs"), where the
# description is the day's menu rather than an attendable occasion. Real events
# DO happen at senior centers (concerts, bingo, classes), so two gates: the
# description must name a meal served at an older-adult/senior center with menu
# framing ("featuring"/"served with"/"menu"), AND the name must carry no
# attendable-event word — any such word vetoes the drop so a genuine
# "Bingo at the Senior Center" survives.
_CONGREGATE_MEAL_DESC_RE = re.compile(
    r'(?=.*\b(?:older[\s-]adult|senior)\s+cent(?:er|re)\b)'
    r'\b(?:breakfast|brunch|lunch|dinner)\b[^.!?]{0,60}'
    r'\b(?:featuring|served with|menu)\b',
    re.IGNORECASE)
_MEAL_ATTENDABLE_NAME_RE = re.compile(
    r'\b(?:class|workshop|concert|show|bingo|party|social|dance|tour|talk|'
    r'lecture|meeting|club|game|movie|film|trip|celebration|festival|fair|'
    r'market|performance|screening|reading|seminar|presentation|learn)\b',
    re.IGNORECASE)
# A menu's "featuring" precedes food; a real lunch gathering's precedes a
# speaker/activity. If the description carries event-content language, it's a
# genuine occasion (a lunch-and-learn, performance, etc.), not a menu — veto.
_MEAL_REAL_EVENT_DESC_RE = re.compile(
    r'\b(?:speakers?|presenters?|presentation|learn|discussion|workshop|'
    r'seminar|performance|live music|\bdj\b|rsvp|registers?|registration|'
    r'q&a|screening|demonstration|entertainment|guest)\b',
    re.IGNORECASE)

# Standing physical attractions described as something you ride or visit
# whenever the venue is open, rather than a scheduled event — a park's splash
# pad / water obstacle course, a carousel ("Le Carrousel", "The Splash Zone").
# The "<attraction-venue> admission" names are dropped on the name above; these
# carry a plain proper-noun name, so they need a corroborating description: an
# attraction/ride noun AND visit-it framing. Any attendable-event word in the
# name vetoes the drop (a "Carousel Concert" or "Splash Pad Story Hour" is a
# real event), and the rule never fires when the description is missing.
_ATTRACTION_DESC_RE = re.compile(
    r'\b(?:water\s+attraction|newest\s+attraction|carr?ousel|'
    r'splash\s+(?:pad|zone)|obstacle\s+course\s+on\s+the\s+water)\b',
    re.IGNORECASE)
_ATTRACTION_VISIT_RE = re.compile(
    r'\b(?:creatures?\s+to\s+ride|to\s+ride\b|hop\s+(?:on|around)|climb\s+on|'
    r'take\s+a\s+(?:whirl|spin|ride))\b',
    re.IGNORECASE)
_ATTRACTION_NAME_VETO_RE = re.compile(
    r'\b(?:concert|show|class|workshop|party|social|dance|tour|talk|lecture|'
    r'meeting|club|game|movie|film|screening|reading|festival|fair|market|'
    r'performance|celebration|night|series|hour|story\s*time|camp|race|run|'
    r'meet|fest|recital|jam|mixer|opening|reception|sing-?along)\b',
    re.IGNORECASE)

# Bare holiday-name closure markers: a venue/office calendar leaks a federal
# holiday as an "event" whose body announces a CLOSURE ("Memorial Day" — "The
# office is closed in observance of the holiday."), not an attendable occasion.
# Real holiday programming shares the name ("Memorial Day" BBQ at a bar,
# "Juneteenth" art workshop, "Independence Day" teaser), so three gates: the
# name must be ONLY a bare holiday marker (exact-anchored, optional
# "(observed)"/year), the description must carry closure/observance framing, and
# any attendable language in the description vetoes the drop. Never fires without
# a description.
_HOLIDAY_NAMES = (
    r"(?:new\s+year'?s?(?:\s+(?:eve|day))?|"
    r"martin\s+luther\s+king(?:\s+jr\.?)?(?:\s+day)?|mlk(?:\s+jr\.?)?(?:\s+day)?|"
    r"presidents?'?\s+day|washington'?s?\s+birthday|lincoln'?s?\s+birthday|"
    r"memorial\s+day|juneteenth|independence\s+day|fourth\s+of\s+july|july\s+4(?:th)?|"
    r"labor\s+day|columbus\s+day|indigenous\s+peoples[’']?\s+day|veterans?\s+day|"
    r"thanksgiving(?:\s+day)?|christmas(?:\s+eve|\s+day)?|halloween|easter(?:\s+sunday)?)"
)
_HOLIDAY_MARKER_NAME_RE = re.compile(
    r"^\s*" + _HOLIDAY_NAMES +
    r"\s*(?:\(?observed\)?)?\s*(?:\d{4})?\s*$", re.IGNORECASE)

# Venue-OPEN holiday notices — the exact inverse of the closure rule above and
# just as much a non-event ("Columbus Day/Indigenous Peoples' Day | Innisfree
# Open for Holiday" — "Innisfree is open in observance of..."). It announces the
# building's hours on a holiday; nothing is scheduled.
#
# The danger of any "Open"/"Holiday" rule is eating real programming, so the
# gates are narrow: the name must contain BOTH a holiday name AND an explicit
# "open for/on/during <the holiday>" construction (which "Open Studios", "Open
# House", "July 4th Concert" never produce), the description must carry
# observance framing, and the same attendable-language veto as the closure rule
# applies — so "Memorial Day BBQ - We're Open for the Holiday!" survives.
_HOLIDAY_OPEN_NOTICE_NAME_RE = re.compile(
    r"\bopen\s+(?:for|on|during)\s+(?:the\s+)?"
    r"(?:holiday|observance|" + _HOLIDAY_NAMES + r")\b", re.IGNORECASE)
_HOLIDAY_NAME_ANYWHERE_RE = re.compile(r"\b" + _HOLIDAY_NAMES + r"\b", re.IGNORECASE)
_CLOSURE_OBSERVANCE_DESC_RE = re.compile(
    r"\b(?:closed|will\s+be\s+closed|office\s+closed|closure|"
    r"no\s+(?:school|classes|programs?|programming|service|services)|"
    r"in\s+observance|observ(?:ed|ance)\s+of|holiday\s+closure)\b", re.IGNORECASE)
_HOLIDAY_ATTENDABLE_DESC_VETO_RE = re.compile(
    r"\b(?:celebrate|celebration|join\s+us|come\s+(?:celebrate|join|out)|party|bbq|"
    r"cookout|parade|concert|live\s+music|\bdj\b|festival|kick\s+off|kickoff|"
    r"brunch|dinner|cocktails?|drinks?|special\s+menu|performance|dance)\b",
    re.IGNORECASE)

# Drink/food "month"/"week" promotions: a bar/restaurant's marketing period
# ("Martini Month" — "special Tanqueray martinis throughout June"), a span of
# drink specials rather than a single attendable event. Real events anchor on
# these too (a "Negroni Week Tasting", a "Burger Month Kickoff Party"), so three
# gates: name = "<drink/food> month|week", description carries promo-special
# framing ($price / special / all-month), and any attendable word in name or
# description vetoes the drop. Weekday forms ("Margarita Mondays") are excluded —
# those are recurring social events people attend.
_DRINK_PROMO_NAME_RE = re.compile(
    r'\b(?:martini|cocktail|margarita|negroni|spritz|wine|whisk(?:e)?y|bourbon|'
    r'tequila|mezcal|gin|rum|vodka|sangria|champagne|prosecco|beer|cider|sake|'
    r'oyster|burger|taco|lobster|pizza|pasta|ramen|dumpling|wing|milkshake|sundae)'
    r'\s+(?:month|week)\b', re.IGNORECASE)
_PROMO_SPECIAL_DESC_RE = re.compile(
    r'(?:\$\d+|\bspecials?\b|\bdeals?\b|half[\s-]?off|\bdiscount\b|\bfeatured\b|'
    r'\ball\s+(?:month|week)\b|throughout\s+(?:the\s+)?(?:month|week|january|'
    r'february|march|april|may|june|july|august|september|october|november|'
    r'december))', re.IGNORECASE)
_PROMO_ATTENDABLE_VETO_RE = re.compile(
    r'\b(?:party|tasting|dinner|pairing|class|workshop|festival|fest|kickoff|'
    r'kick-?off|live\s+music|\bdj\b|concert|dance|competition|contest|throwdown|'
    r'crawl)\b', re.IGNORECASE)

# Buy-one-get-one ticket promotions ("Kids' Night on Broadway at Top of the
# Rock" — "Buy one full-price adult Timed Admission ticket and receive one
# complimentary youth ticket…", e225309 w41 Rockefeller Center, hand-suppressed
# on 2026-08-20). Nothing is programmed: the attraction's normal admission is
# discounted for a few days.
#
# The offer must OPEN the description, and that anchor is the entire rule. A
# BOGO phrase merely present in the body is emphatically NOT junk — 53 events
# carry one, and they include real programming that happens to advertise a deal
# ("Missing Movies Double Feature", "DUMBO After Dark", "Karaoke Tuesday with
# the Fabulous LaMaria", 6 of them live right now). What separates the promo is
# that the offer is ALL there is: the body opens with the transaction because
# there is no event to describe first. Anchored, the corpus yields 4 matches
# over all 193,874 events — a pretzel-day BOGO, "Best Friend Promo!", "July 4
# Weekend BOGO!" and e225309 — all four promos, none live.
#
# The veto is the second safety net for the day a real event leads with its
# ticket offer and then describes itself.
_BOGO_OFFER_DESC_RE = re.compile(
    r'^\s*buy\s+one\b[^.]{0,80}?\b(?:get|receive)\s+one\b', re.IGNORECASE)
_BOGO_ATTENDABLE_VETO_RE = re.compile(
    r'\b(?:join\s+us|featuring|performance|performing|live\s+music|\bdj\b|'
    r'concert|show(?:case)?|screening|class|workshop|tour|doors\s+open|'
    r'lineup|line-up|hosted\s+by|presents)\b', re.IGNORECASE)

# Standing daily happy hour — a bar's permanent drink-deal window published as a
# dated row ("Happy Hour & Live Music" — "The venue advertises daily happy hour
# deals on drinks and food along with live music", e225510 w1290 Don't Tell
# Mama, hand-suppressed on 2026-08-20). It is the `<drink> Month/Week` promo's
# nearest sibling: an offer that is true every day, not something that happens.
#
# **"Happy hour" in a name is NOT a junk signal and must never become one** —
# 50 live events are named one right now, and they are named programming: DJ
# sets ("[happy hour] ✽ she.they.dj ✽"), "Poetry Happy Hour", "Art History
# Happy Hour", comedy hours, networking mixers, run-club post-run drinks. The
# discriminator is entirely in the BODY, and specifically in its FREQUENCY: a
# standing offer describes itself as daily/nightly/every day, which no dated
# programme ever does. Weekly and monthly forms are deliberately excluded — a
# weekly happy hour IS a recurring event people show up to ("Sunday Football
# Happy Hour", "Weekly Happy Hour", "Dumbo Happy Hour" on first Wednesdays,
# all live), and only the every-single-day form is a pure venue amenity.
#
# Measured over all 193,874 events: 14 matches, 0 live, and every one of the 14
# is a venue's standing happy hour. None of the 50 live "happy hour" events
# comes within reach of the frequency gate.
_HAPPY_HOUR_NAME_RE = re.compile(r'\bhappy\s+hour\b', re.IGNORECASE)
_STANDING_OFFER_DESC_RE = re.compile(
    r'\b(?:daily|nightly|every\s+day|seven\s+days\s+a\s+week|'
    r'7\s+days\s+a\s+week)\b', re.IGNORECASE)
_HAPPY_HOUR_DEAL_DESC_RE = re.compile(
    r'\b(?:deals?|specials?|discounted)\b|\$\d', re.IGNORECASE)


def _is_standing_happy_hour(name, description):
    """True for a venue's permanent daily happy hour published as an event."""
    if not name or not description:
        return False
    return bool(_HAPPY_HOUR_NAME_RE.search(name)
                and _STANDING_OFFER_DESC_RE.search(description)
                and _HAPPY_HOUR_DEAL_DESC_RE.search(description))

# National FOOD/DRINK holiday marketing posts ("National Fajita Day" — "Come
# grab some sizzling goodness for National Fajita Day!", e221838 w868 Hudson
# Blue, hand-suppressed at classification on 2026-08-17). A bar or restaurant
# hangs a hashtag holiday on its normal service: nothing is programmed, nothing
# starts, you just eat there that day. Sibling of the `<drink> Month/Week` promo
# rule above, which covers the named-period form.
#
# **A name-only version of this rule was measured and REFUTED on 2026-07-27**
# (test_processor.TestJunkFilterGaps20260727
# .test_national_food_day_deliberately_not_dropped): a bare "National Chicken
# Wing Day" with no body is a coin flip on intent, because venues do host real
# themed nights on the same food holidays. That ruling stands — this rule adds
# the second signal it was missing and fires ONLY on a body written as dining
# marketing ("Come grab…", "Buy one, get one", "$5 pours"). A bare marker with
# no description still survives, and so does one whose body describes a party.
# The narrowing costs 7 of the 30 name matches (30 → 23) and is the right
# direction. It also catches e200728, the row the 2026-07-27 pass suppressed by
# hand — that one's body is "Come grab some wings…", i.e. it always had the
# second signal the refuted name-only rule could not see.
#
# The load-bearing gate is that the WHOLE name is "National <food/drink> Day"
# and the qualifier comes from a closed food/drink list. The national-day family
# at large is overwhelmingly real programming — National Trails Day, National
# Cleanup Day, National Zoo Day, National Superhero Day, National Scrabble Day,
# National Seed Swap Day, National Honey Bee Day, National Youth Takeover Day —
# so nothing but the food/drink axis may decide this. Anything appended to the
# title means a real occasion was built on the holiday and the anchor spares it:
# "National Ice Cream Day at the Carousel" (Prospect Park), "National Pizza Day
# Dinner", "National Chicken Finger Day Challenge", "Whispering Angel Rosé
# Tasting – National Rosé Day". A trailing dash clause is allowed ONLY because
# e221838 arrived with its own description glued onto the title.
#
# Measured over all 190,989 events: 30 name matches, all 30 bar/restaurant promos
# from five venues (w868, w1348, w1349, w1199, w5057), ZERO real events; 23 of
# them also clear the description gate and are what this rule drops. Zero of the
# nine a human has already reviewed were KEPT — all nine were suppressed by hand,
# the opposite of the "Whiskey Wednesday" weekday-special precedent (see
# test_junk_filter_calendar_non_events.TestWeekdayFoodSpecialsStayUnfiltered),
# where the reviewed row was deliberately kept. The one still live (e191338
# "National Drink Beer Day", w1349) is a correct kill the suppression pass has
# not reached. Foods NOT on the list keep their
# rows: "National Oreo Day" at Chelsea Market and 'National "Tziki" Day' are real
# and are spared by omission, which is the intended failure direction.
_FOOD_DRINK_HOLIDAY_NOUN = (
    r'(?:'
    r'pizza|taco|fajita|burrito|nacho(?:s)?|guacamole|quesadilla|empanada(?:s)?|'
    r'burger|cheeseburger|hamburger|hot\s*dog|meatball(?:s)?|'
    r'chicken\s+(?:wing|finger|tender|nugget)s?|wing(?:s)?|'
    r'french\s+fr(?:y|ies)|tater\s+tot(?:s)?|'
    r'pasta|spaghetti|lasagna|ramen|dumpling(?:s)?|sushi|steak|bbq|barbecue|'
    r'oyster(?:s)?|lobster|shrimp|'
    r'bagel|pretzel|pancake(?:s)?|waffle(?:s)?|french\s+toast|'
    r'donut(?:s)?|doughnut(?:s)?|cookie(?:s)?|brownie(?:s)?|cupcake(?:s)?|'
    r'ice\s*cream|gelato|sundae|milkshake|dessert|cheesecake|'
    r'wine\s+and\s+cheese|wine\s*&\s*cheese|'
    r'margarita|martini|mojito|daiquiri|pi(?:n|ñ)a\s+colada|sangria|'
    r'cocktail(?:s)?|mimosa|bloody\s+mary|old\s+fashioned|negroni|spritz|'
    r'whisk(?:e)?y(?:\s+sour)?|bourbon|scotch|rum|vodka|gin|tequila|mezcal|sake|'
    r'wine|prosecco|champagne|beer|ipa|lager|stout|cider|'
    r'espresso|latte|boba|bubble\s+tea|iced\s+tea'
    r')'
)
# Optional flavour/colour qualifiers ("Vanilla Ice Cream", "Red Wine"). Kept
# separate from the noun list so the list stays a list of foods.
_FOOD_HOLIDAY_NAME_RE = re.compile(
    r'^\s*national\s+'
    r'(?:(?:drink|eat|sip)\s+)?'
    r'(?:(?:vanilla|chocolate|strawberry|red|white|ros(?:e|é)|sparkling|iced|'
    r'frozen|craft|dark|spicy)\s+){0,2}'
    + _FOOD_DRINK_HOLIDAY_NOUN +
    r'\s+day\s*[!.]?'
    r'(?:\s*[-–—:]\s*.{0,160})?'      # e221838 glued its description onto the title
    r'\s*$',
    re.IGNORECASE)
# The second signal: the body reads as dining marketing rather than an occasion.
# Deliberately does NOT accept a blank description — that is the exact case the
# 2026-07-27 refutation covers.
_FOOD_HOLIDAY_DESC_RE = re.compile(
    r'\bcome\s+(?:on\s+)?(?:grab|in|down|by|celebrate|enjoy|try|sip|taste|indulge)\b|'
    r'\bgrab\s+(?:a|an|some|your|yourself)\b|'
    r'\bstop\s+(?:by|in)\b|'
    r'\bjoin\s+us\b[^.!?]{0,70}\b(?:grab|sip|try|enjoy|indulge|drink|taste|order|'
    r'bite|glass|pour|pours|slice)\b|'
    r'\bsip\s+on\b|\bindulge\b|'
    r'\bbuy\s+one\b|\bwhile\s+supplies\s+last\b|'
    r'\bspecial(?:ty)?\s+(?:drink|cocktail|menu|food|pricing)|'
    r'\$\d|\bhalf[\s-]?off\b|\bbogo\b|'
    r'\bour\s+(?:bartenders|kitchen|chefs?)\b|'
    r'\bhappy\s+hour\b',
    re.IGNORECASE)
# Any real programming hung on the holiday keeps the row. Measured to fire on
# none of the 30 name matches, so it costs no yield and covers the realistic
# failure mode (a venue that turns the holiday into an actual party one year).
_FOOD_HOLIDAY_VETO_RE = re.compile(
    r'\b(?:party|tasting|pairing|class|workshop|demo(?:nstration)?|festival|fest|'
    r'live\s+music|\bdj\b|band|concert|screening|film|comedy|trivia|karaoke|'
    r'bingo|tour|parade|hike|volunteer|ranger|market|pop[\s-]?up|competition|'
    r'contest|challenge|fundraiser|benefit|ticket(?:s|ed)?|rsvp|register|'
    r'registration|guest\s+chef|cook[\s-]?off)\b',
    re.IGNORECASE)

# (6) Ticketing upsell PRODUCTS. A venue's ticket store publishes its packages
# and bundles on the same feed as its exhibitions, so a thing you BUY reaches the
# extractor looking like a thing you ATTEND. Raised by the 2026-08-17
# classification pass, which could only label two ARTECHOUSE (w1166) rows
# UNKNOWN: e222525 "VIP & Date Night Packages" and e222526 "ARTECHOUSE x Color
# Factory Experience Bundle" ("Both tickets must be redeemed within 30 days of
# purchase"). The venue's genuine exhibitions already exist as their own rows, so
# these add nothing but a duplicate pin. The same shape recurs across the
# corpus — Empire State Building "Birthday Celebration Packages", SUMMIT "Spring
# Bundle", ArtTable "VIP Pass Packages".
#
# Two gates plus a veto, per this block's convention:
#   - the NAME must END on "package(s)" / "bundle(s)". The tail anchor is
#     load-bearing: "VIP package" appears INSIDE plenty of real listings (Bear
#     Mountain's "Magical Princess Brunch" offers "an optional VIP package"), and
#     only a title that ends on the product noun IS the product.
#   - the DESCRIPTION must read as a purchase product: the package/bundle
#     "includes"/"provides" a ticket or access, must be "redeemed", is a
#     "pre-order", names an "availability window" or an "anytime ticket".
#   - the VETO spares the two real-event families that clear both gates.
#
# The veto is measured, not decorative. Over all 191,070 events only 17 titles
# end on package/bundle, and TWO of them are real: e21299 "Buster Keaton Shorts
# Package" (a cinema shorts PROGRAMME — `shorts`/`films` veto) and e23209 "LIU
# Cares Week: Care in Every Package" (a care-package packing drive — `come
# together`/`participate`/`donate`/`drive` veto). A bare name-tail rule would
# have killed both.
#
# Measured over all 191,070 events plus 134,254 crawl_events from the last 21
# days: 8 net-new events and 2 net-new crawl_events, every one a purchase
# product or a private-hire package. ZERO live, ZERO reviewed-and-kept, ZERO
# false positives. Known accepted miss (fail-safe): e205218, the February
# ARTECHOUSE bundle whose body is pure marketing copy with no purchase term.
_TICKET_PRODUCT_NAME_RE = re.compile(
    r'\b(?:packages?|bundles?)\s*[.!]?\s*$', re.IGNORECASE)
_TICKET_PRODUCT_DESC_RE = re.compile(
    r'\b(?:package|packages|bundle|bundles|tickets?)\b[^.!?]{0,80}'
    r'\b(?:includes?|provides?|grants?|offers?)\b'
    r'|\b(?:includes?|provides?|grants?|offers?)\b[^.!?]{0,80}'
    r'\b(?:ticket|tickets|admission|access|entry|pass|passes)\b'
    r'|\bmust\s+be\s+redeemed\b|\bredeem(?:ed|able)?\b[^.!?]{0,40}\bpurchase\b'
    r'|\bdays?\s+of\s+purchase\b|\bpre-?order\b'
    r'|\bavailability\s+window\b|\banytime\s+ticket\b'
    r'|\badd[\s-]?on\b[^.!?]{0,40}\b(?:ticket|purchase|price)\b',
    re.IGNORECASE)
_TICKET_PRODUCT_VETO_RE = re.compile(
    r'\b(?:short(?:s)?|film(?:s)?|feature|screening|double\s+feature|'
    r'programme?\s+of|retrospective|'
    r'come\s+together|participate|volunteer|donate|drive|'
    r'performance|concert|band|\bdj\b|live\s+music|'
    r'workshop|class(?:es)?|lecture|panel|reading|tour\b|'
    r'parade|festival)\b',
    re.IGNORECASE)

# Retail spend-and-get promotions: a vendor's purchase incentive leaked from a
# venue calendar ("Blackbird Special World Cup Promotion" — "Spend $40 ...
# receive a free 4-pack ... while supplies last"). Two gates: name ends in
# "promo(tion)" and the description carries retail-incentive framing. (Name
# alone is ambiguous — a band can be named "...Pawn Promotion".)
_RETAIL_PROMO_NAME_RE = re.compile(r'\bpromo(?:tion)?\s*$', re.IGNORECASE)
_RETAIL_PROMO_DESC_RE = re.compile(
    r'(?:spend\s+\$?\d+|while\s+supplies\s+last|receive\s+a\s+free|'
    r'\bfree\s+\w+.{0,25}\b(?:with|when\s+you)\b|%\s*off|\$\d+\s+(?:off|reward)|'
    r'purchase\s+\w+.{0,20}\bget\b)', re.IGNORECASE)

# Venue reopening announcements: a "<venue> Reopening" status notice ("Museum
# Reopening" — "reopens in Autumn 2026 following summer restoration") rather than
# an attendable event. Two gates plus a veto: name ENDS in "reopening", the
# description carries reopening-status framing, and event words in the name
# ("Grand Reopening Party") veto the drop.
_REOPENING_NAME_RE = re.compile(r'\bre[\s-]?open(?:ing|s)?\s*$', re.IGNORECASE)
_REOPENING_NAME_VETO_RE = re.compile(
    r'\b(?:party|celebration|gala|bash|reception|concert|festival|night|tour|'
    r'preview)\b', re.IGNORECASE)
_REOPENING_DESC_RE = re.compile(
    r'\breopen(?:s|ing|ed)?\b.{0,80}\b(?:autumn|spring|summer|fall|winter|\d{4}|'
    r'following|after|restoration|renovation|renovated|refurbish|closed)\b|'
    r'welcomed?\s+back', re.IGNORECASE)


# Standing menu / food-and-drink specials leaked from a bar or restaurant's
# calendar ("Lunch Specials" — "Daily lunch specials are available Monday
# through Friday"). Not an occasion: it describes what the kitchen offers
# whenever it is open. Sibling of the "<drink> Month/Week" promo rule above,
# which only covers the named-period marketing form.
#
# Precision comes from the name being FULLY anchored: the whole title must be
# "<meal-or-drink> <specials|menu|deals>" and nothing else, so any real event
# built on the same words survives untouched ("Lunch Specials Tasting Party",
# "Prix Fixe Dinner with the Chef", "Happy Hour Trivia"). The description must
# additionally frame it as an ongoing/recurring offer rather than a one-night
# occasion.
_MENU_SPECIAL_NAME_RE = re.compile(
    r'^\s*(?:new\s+|our\s+|daily\s+|weekly\s+|weekday\s+|weekend\s+)?'
    r'(?:lunch|brunch|dinner|breakfast|drink|food|bar|late[\s-]night|'
    r'bottomless|prix[\s-]?fixe|happy[\s-]?hour)\s+'
    r'(?:special(?:s)?|menu|deal(?:s)?|offering(?:s)?)\s*$',
    re.IGNORECASE)
_MENU_SPECIAL_DESC_RE = re.compile(
    r'\b(?:daily|weekly|weekday|every\s+day|all\s+week|seven\s+days)\b'
    r'[^.!?]{0,50}\b(?:special(?:s)?|menu|deal(?:s)?|offer(?:ed|ing|ings)?|'
    r'available|served)\b|'
    r'\b(?:special(?:s)?|menu|deal(?:s)?)\b[^.!?]{0,80}\b(?:monday|tuesday|'
    r'wednesday|thursday|friday|saturday|sunday|weekdays?|daily|every\s+day|'
    r'all\s+week)\b',
    re.IGNORECASE)
# Any of these in the description means a real, dated occasion is attached and
# the row is more than a standing menu.
_MENU_SPECIAL_VETO_RE = re.compile(
    r'\b(?:live\s+music|\bdj\b|band|concert|performance|trivia|bingo|karaoke|'
    r'comedy|tasting|class|workshop|party|festival|screening|rsvp|ticket)\b',
    re.IGNORECASE)


# Shapes that reached the map and only got caught downstream, by the event-type
# classifier labelling them UNKNOWN. Same two-signal conservatism as the block
# above: each needs a corroborating description, so a miss just falls through to
# find_review_candidates.py. Every candidate here was measured over the whole
# events table before shipping — most of the batch failed that bar and is
# recorded as rejected below.

# (1) Library room-booking placeholders. Public LibCal/EventKeeper calendars
# expose patron room reservations alongside real programming
# ("Patron Reservation - Furbacher.", e210295). Always nameless-of-content, so
# a blank description is required — a described "Room Reservation Workshop"
# survives.
_ROOM_RESERVATION_NAME_RE = re.compile(
    r'^\s*(?:patron|room|study\s+room|meeting\s+room|space|equipment)\s+reservation\b',
    re.IGNORECASE)

# Opening-hours notices. Library and museum calendars publish their own hours as
# calendar rows — "Library open 9 AM - 5 PM", body "Library will be open 9 AM to
# 5 PM for Columbus Day". Nothing is happening; the building is merely unlocked.
#
# This is the mirror image of the existing CLOSURE family (which is already
# filtered): a holiday that changes the hours gets published either way round,
# and only the "closed" half was covered.
#
# "open" is a very live word, so a CLOCK TIME is the load-bearing gate — not the
# word "open" and not a trailing preposition. A precision audit over all 185,367
# events proved how narrow this has to be: an earlier draft that accepted
# `open … (until|from|for)` swept up "Open for Bowling!" (a real Brooklyn Bowl
# session, 6 rows), "Open for cocktails" (Zinc Bar), "Open for Ops", and even
# "Open Forum" — where `for` matched the first three letters of "Forum".
#
# So: the name must state open/closed AND carry an explicit clock time, and must
# contain no attendable-event word. "Open for Bowling!" has no clock time and is
# spared; "Library open 9 AM - 5 PM" is caught.
#
# Note the CLOSED half of this shape is already handled by the closure family
# above; this exists for the "open" half, which was the uncovered mirror image.
_HOURS_NOTICE_NAME_RE = re.compile(
    r'^\s*(?:the\s+)?'
    r'(?:library|museum|gallery|building|office|branch|center|centre|store|shop|'
    r'garden|park|pool|rink|cafe|kitchen|desk|lobby|front\s+desk)?\s*'
    r'(?:will\s+be\s+|is\s+|are\s+)?'
    r'(?:open|closed|closing|opening\s+hours|hours)\b'
    r'[^A-Za-z0-9]{0,4}'
    r'\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)\b'   # an explicit clock time
    r'.{0,60}$',
    re.IGNORECASE)
# Anything implying a gathering vetoes the drop, even with a clock time present.
_HOURS_NOTICE_VETO_RE = re.compile(
    r'\b(?:mic|house|studios?|reception|rehearsal|swim|play|gym|skate|practice|'
    r'run|call|casting|audition|tour|class|workshop|reading|concert|show|party|'
    r'market|fair|meeting|talk|screening|social|bowling|cocktails?|forum|ops)\b',
    re.IGNORECASE)


def _is_hours_notice(name, description=None):
    """True for a bare opening/closing-hours announcement, not an event."""
    if not name:
        return False
    if _HOURS_NOTICE_VETO_RE.search(name):
        return False
    return bool(_HOURS_NOTICE_NAME_RE.match(name.strip()))


# (1b) Delayed / late opening notices ("Delayed Opening - Staff Development",
# body "Due to staff development, the library will be opening at 1:00pm" —
# e225218 w3530 BCCLS, hand-suppressed at classification on 2026-08-20). The
# building opens late; nothing is programmed. This is the third face of the same
# operational-calendar shape the closure and hours families already cover, and
# neither of them reaches it: the hours rule's load-bearing gate is a clock time
# in the NAME, and these carry the time in the body if anywhere.
#
# Two gates, per this block's convention: the delay phrase in the name, plus
# either a body that adds nothing or one that states the later opening. The
# hours-notice attendable veto is reused, which is what keeps a gallery's "Late
# Opening Reception" or a "Late Opening Party" out of reach.
#
# Verified over all 193,874 events: 6 name matches, all 6 operational notices
# (4 NYPL system-wide, 1 museum, plus e225218), 0 live, 0 false positives.
_DELAYED_OPENING_NAME_RE = re.compile(
    r'\b(?:delayed|late)\s+opening\b|\bopening\s+(?:late|delayed)\b'
    r'|\bdelayed\s+open\b', re.IGNORECASE)
_DELAYED_OPENING_DESC_RE = re.compile(
    r'\bdelayed\s+opening\b'
    r'|\b(?:will\s+(?:be\s+)?open(?:ing)?|opens?)\b[^.]{0,40}'
    r'\b(?:at\s+\d{1,2}|later|delayed|noon)\b',
    re.IGNORECASE)


def _is_delayed_opening_notice(name, description=None):
    """True for a "<facility> is opening late today" notice, not an event."""
    if not name:
        return False
    if not _DELAYED_OPENING_NAME_RE.search(name):
        return False
    if _HOURS_NOTICE_VETO_RE.search(name):
        return False
    description = description or ''
    return bool(_description_adds_nothing(name, description)
                or _DELAYED_OPENING_DESC_RE.search(description))

# (2) "On this Day:" historical archival posts. Park conservancies publish these
# alongside real programming — they narrate a past anniversary ("On October 12,
# 1935, Fort Tryon Park was officially dedicated…") and no gathering is being
# held. All 5 in the DB come from w82 Fort Tryon Park Conservancy; two reached
# the map and were hand-suppressed at classification on 2026-08-05.
#
# Two gates, per this block's convention. The historical gate is what makes the
# rule about archival posts rather than about the phrase: a future event simply
# *titled* "On This Day" carries no past year and no commemoration language.
# The veto is the second safety net, so a conservancy that ever turns one of
# these into an actual guided anniversary walk keeps it.
# Verified over all 180,262 events (.scratch/on_this_day_verify.py): 5 name
# matches, 5 suppressed, 0 false positives, 0 spared.
_ARCHIVAL_ON_THIS_DAY_NAME_RE = re.compile(
    r'^\s*on\s+this\s+day\b\s*[:—–-]', re.IGNORECASE)
# Year range starts at 1500: colonial-era anniversaries are exactly what these
# posts narrate, and e218929 ("On this Day: Margaret Corbin's Birthday", born
# **1751**) slipped through the original 18xx/19xx/20xx range and had to be
# caught downstream by the event-type classifier on 2026-08-14. Re-verified
# over all 188,480 events after widening: still only the 7 genuine archival
# posts match the name gate, 0 false positives.
_ARCHIVAL_HISTORICAL_DESC_RE = re.compile(
    r'\b(?:1[5-9]\d{2}|20[0-2]\d)\b|\b(?:anniversar|commemorat)\w*',
    re.IGNORECASE)
_ARCHIVAL_GATHERING_VETO_RE = re.compile(
    r'\b(?:join\s+us|rsvp|register|registration|tickets?|admission|'
    r'workshop|class|guided|meet\s+(?:us|at)|performance|screening|'
    r'doors\s+open|refreshments)\b', re.IGNORECASE)

# (3) Academic / registrar calendar milestones. University and community-college
# feeds publish their whole academic calendar as "events": add/drop deadlines,
# tuition-refund cutoffs, pass/fail request windows, term start dates, final-exam
# periods. Nobody attends a deadline. Seven LIU rows had to be hand-suppressed at
# classification on 2026-08-06 and e214913 on 2026-08-09; NYU and Bronx CC emit
# the same shape continuously.
#
# NAME-ONLY on purpose (unlike the two-signal rules above): these rows are
# usually description-less, and where a description exists it just restates the
# deadline ("The deadline for students to drop or add courses"), so it carries
# no independent signal. The precision instead comes from the phrases themselves
# being registrar jargon plus an attendable-occasion veto over the NAME.
#
# The veto is what keeps this off real programming, and it is not decoration:
#  - "Classes Resume, Town Hall (Dance and Music Recitals)" (e78067) is a real
#    recital and is spared by `recitals?` — note the plural, the singular form
#    missed it;
#  - the singular "final exam" was DROPPED from the exam arm because it eats
#    "Final Exam Horror Trivia, No. 39" (e154254, a real NYChorror trivia
#    night). Only the plural "final examinations"/"final exams" and the explicit
#    "final exam period/schedule/week" forms are matched.
#  - `registration begins/opens` was likewise DROPPED: it hits real library
#    sign-up programming ("2026 Summer Reading Program Registration Begins",
#    "Adult Summer Reading Registration Begins!") and half of its matches were
#    already covered by the start-anchored registration rule above.
#  - "<term/session> begins/ends" was DROPPED: it hits "Bronx Bops Weekday
#    Session Start" (e39357), a real children's music program's first day.
#
# Measured over all 183,900 events (.scratch/jf_final2.py): 71 matches, ALL of
# them registrar/school-calendar markers (NYU 33, Bronx CC 25, LIU 9,
# Mind-Builders 2, Ballet Tech 1, plus NYC Events' "Primary Election - Last Day
# to Register to Vote"), and exactly ONE currently-live row — 117776 "Last Day
# of Summer 2026 5W1 Instruction / Final Exams" — which is itself junk. Zero
# false positives. Of the 408 live events from academic-named websites, this is
# the only one that fires, so real university lectures/concerts are untouched.
_ACADEMIC_MILESTONE_NAME_RE = re.compile(
    r'\bclasses\s+(?:begin|begins|start|starts|end|ends|resume|resumes)\b'
    r'|\bno\s+classes\b'
    r'|\blast\s+class(?:es)?(?:\s+meeting)?\b(?=\s*[/,:&-]|\s*$)'
    r'|\bfinal\s+exam(?:ination)?s\b'
    r'|\bfinal\s+exam(?:ination)?\s+(?:period|schedule|week)\b'
    r'|\b(?:last|final)\s+day\s+(?:to|for)\s+[\w/\s]{0,30}?'
    r'(?:add|drop|withdraw|withdrawal|enroll|register|registration|refund|'
    r'pass\s*/?\s*fail|audit)\b'
    r'|\b(?:drop\s*/\s*add|add\s*/\s*drop)\b'
    r'|\bpass\s*/?\s*fail\s+(?:grade\s+)?option\b'
    r'|^\s*week(?:end|day)\s+session\s+[a-z0-9]\s*:',
    re.IGNORECASE)
_ACADEMIC_ATTENDABLE_VETO_RE = re.compile(
    r'\b(?:recitals?|ceremon(?:y|ies)|commencement|graduation|convocation|'
    r'part(?:y|ies)|receptions?|concerts?|festivals?|celebrations?|'
    r'open\s+house|orientation|fairs?|showcases?|performances?|screenings?|'
    r'exhibit(?:ion)?s?|tours?|talks?|lectures?|panels?|workshops?|'
    r'trivia|quiz|comedy|games?|socials?|mixers?|brunch|dinners?|breakfast|bbq|'
    r'town\s+hall|study\s+(?:break|jam|session)|meet\s*(?:&|and)\s*greet|'
    r'rall(?:y|ies)|march|fundraiser|auction|clinic|camp)\b',
    re.IGNORECASE)

# Take-home / grab-and-go kit distributions. Libraries publish "Grab & Go:
# <craft>" / "Adult Take-Home Craft" rows where patrons pick up a kit at the
# desk and do the activity at home — nobody attends anything, so they are not
# map events. Three reached `events` from w3530 (BCCLS) on 2026-08-14 and were
# only caught downstream by the event-type classifier labelling them Other
# (219397, 219412, 219497).
#
# Three gates: the pickup idiom in the NAME, a kit/craft word in name or
# description, and pickup corroboration in the DESCRIPTION. The veto spares
# in-person programming that merely sends attendees home with the result:
# "Indoor Spring: Learn Grow and Take Home Plants" is a real 4-session class
# and is spared by `session`/`join us`.
#
# Verified over all 188,480 events: 105 fires, every one a genuine kit
# distribution (13 live, all kits — including the three above); 0 false
# positives. Known safe misses: kit rows whose description omits any pickup
# word ("Grab & Go: Blackout Poetry Kits" — body is just the activity blurb).
#
# 2026-08-17 WIDENING (e221467 "Take-n-Make!", w3 Roosevelt Island Library,
# raised by the 2026-08-16 classification pass). The arm missed it twice over:
#
#   (a) The NAME idiom list was too literal. `grab\s*(?:&|and|n)\s*go` cannot
#       match a HYPHENATED separator, so "Grab-and-Go Craft", "Grab 'n Go" and
#       "Kids Create Grab-and-Go" all fell through; and the whole "Take & Make"
#       / "Take n Make" / "Take & Create" family — the same libraries' other
#       house style for the identical thing — had no pattern at all. Both
#       separators are now `[-–\s]*` and the take-<verb> family is spelled out.
#
#   (b) The `join us` veto is now SOFT. e221467's body is "Join us at the
#       Roosevelt Island Library World Cup Celebration to pick up some fun craft
#       materials to take home while supplies last!" — a kit pickup that happens
#       to open with the branch's stock invitation. `join us` alone is far too
#       weak to prove somebody attends something, so it only vetoes when the
#       body carries no UNAMBIGUOUS distribution phrase ("while supplies last",
#       "first come first served", "pick up a …", "available for pickup"). The
#       hard veto (workshop/class/session/instructor/…) is untouched and still
#       spares "Indoor Spring: Learn Grow and Take Home Plants", the real
#       4-session class this arm was originally tuned around.
#
# Re-measured over all 191,070 events plus 134,254 crawl_events from the last 21
# days: the widening fires on 14 NET-NEW events (1 live, e210845 "August Take &
# Make - Paint by Number", a correct kill) and 4 net-new crawl_events. Every one
# is a library kit pickup. ZERO false positives, ZERO reviewed-and-kept rows.
_TAKE_HOME_KIT_NAME_RE = re.compile(
    r'\b(?:'
    r'grab\s*[-–\s]*(?:&(?:amp;)?|and|\'?n\'?|’n’)\s*[-–\s]*go'
    r'|take\s*[-–\s]*(?:&(?:amp;)?|and|\'?n\'?|’n’)\s*[-–\s]*'
    r'(?:make|create|craft|bake|go)'
    r'|take[\s-]?home'
    r')\b', re.IGNORECASE)
_TAKE_HOME_KIT_SIGNAL_RE = re.compile(
    r'\b(?:kits?|crafts?)\b', re.IGNORECASE)
_TAKE_HOME_KIT_DESC_RE = re.compile(
    r'\b(?:kits?|pick\s*-?\s*up|supplies\s+last|take\s+home)\b', re.IGNORECASE)
# HARD veto: words that assert an actual gathering. Never overridden.
_TAKE_HOME_KIT_VETO_RE = re.compile(
    r'\b(?:workshop|class|session|together|in[\s-]?person|'
    r'demonstration|instructor|learn\s+how)\b', re.IGNORECASE)
# SOFT veto: boilerplate invitation language that says nothing about attending.
_TAKE_HOME_KIT_SOFT_VETO_RE = re.compile(r'\bjoin\s+us\b', re.IGNORECASE)
# Distribution phrases that are unambiguous enough to override the SOFT veto.
_TAKE_HOME_KIT_PICKUP_RE = re.compile(
    r'\bwhile\s+(?:the\s+)?supplies\s+last\b|\bwhile\s+they\s+last\b|'
    r'\bfirst\s+come,?\s+first\s+serve[d]?\b|'
    r'\bpick\s*-?\s*up\s+(?:a|an|one|some|your|free|,)|'
    r'\bpick\s+up\b[^.!?]{0,60}\bto\s+take\s+home\b|'
    r'\bavailable\s+(?:for\s+)?pick\s*-?\s*up\b',
    re.IGNORECASE)

# Program-deadline notices: "<program> Ends!" rows whose body is a submit-your-
# logs reminder ("Please SUBMIT all Summer Reading logs by AUGUST 17!"), not a
# wrap-up gathering. e219452 (w3530) reached the map this way on 2026-08-14.
#
# The NAME gate requires a program noun before "Ends" — a bare `ends$` matched
# the film "It Ends" seven times over the events table, so the noun is
# load-bearing, not decoration. The description gate requires deadline
# language, and the veto spares an actual end-of-program party ("celebrate",
# "prizes awarded"). Verified over all 188,480 events: 3 name matches, 1 fire
# (219452 itself); the other two are description-less echoes already handled
# manually.
#
# Widened 2026-08-20 for the PLURAL/bare form ("Summer Reading Programs End",
# e225219 w3530, description-less): the noun may be plural and the verb may
# therefore lose its "s", and the trailing "!" was never required anyway. The
# program noun stays mandatory for the same reason as before — it is the only
# thing standing between this rule and the film "It Ends". Re-verified over all
# 193,874 events: 4 name matches (up from 3), all four are summer-reading
# wrap-up markers, none live.
_PROGRAM_DEADLINE_NAME_RE = re.compile(
    r'\b(?:reading|programs?|challenges?|registrations?)\s+ends?!?\s*$',
    re.IGNORECASE)
_PROGRAM_DEADLINE_DESC_RE = re.compile(
    r'\b(?:submit|deadline|last\s+day\s+to|logs?\s+by)\b', re.IGNORECASE)
_PROGRAM_DEADLINE_VETO_RE = re.compile(
    r'\b(?:party|celebration|celebrate|join\s+us|performance|concert|ceremony|'
    r'prizes?\s+awarded)\b', re.IGNORECASE)

# (4) Facility-closure notices. Parks, golf courses, schools and community-board
# calendars publish "<facility> Closed" as a dated row ("Hendricks Field Golf
# Course Closed", "Francis A Byrne Golf Course Closed", w Essex County Parks).
# The `_NON_EVENT_NAME_RE` closure family above only covers a fixed list of venue
# nouns ("museum|library|park|…  clos(ed|es|ure)") and the punctuated
# "Closed: …" / "Closed for …" forms, so a facility it has never heard of keeps
# coming back: the extractor re-creates the row every run and a human re-
# suppresses it. This is a CHURN cost, not a correctness bug — none of these are
# on the map.
#
# Two gates, per this block's convention: the word anywhere in the name, plus a
# corroborating description. A blank description counts as corroboration
# (`_description_adds_nothing`) because "No description available." is the common
# shape here — these rows say nothing beyond the closure itself.
#
# The description gate is what makes it safe, and it is keyed on `closed|closure`
# only — never `closing`/`closes`. That is what spares the real events that
# merely contain the word: 8452 "Closed Curtain" (the Jafar Panahi film), 42435
# "Saidah Gets Closure", 50432 "Poetic Closure" (a poetry workshop), and the
# early-closing HOURS notices whose bodies say the venue "will close early".
#
# `closed(?!\s*caption)` is REQUIRED, not decoration: BCCLS runs a real "Closed
# Captioning Film Club", which a bare `closed` matched — the same false positive
# was hit and fixed on 2026-08-05 in the w3530 admin-marker regex.
#
# The name veto covers the two families that are about something OTHER than the
# facility being shut: an early-closing hours change ("Early Closure: 2 PM
# Saturday, January 31" — the venue is open, just for fewer hours) and a real
# event whose SIGN-UP has closed ("Drag Story Hour … (Registration Closed)").
# Both would otherwise fire on a blank description.
#
# Known accepted misses (fail-safe, not bugs): "Closed For Private Event"
# (38318, 60244) whose bodies say "unavailable"/"not open"; "Mid-Winter Recess
# (Bms Closed, Open for Makeups)". Missing junk is the right failure direction.
#
# The ANCHORED `Closing: <thing>` alternative is the LibCal/library punctuation
# form of the same notice ("Closing: Labor Day Weekend 2026", w2014 New York
# Society Library, e231355 hand-suppressed 2026-08-24). It is anchored to the
# start of the name and requires the colon/dash immediately after the word,
# because an unanchored or bare-word `closing` is a trap: 33 of the 37 events
# whose name starts with "Closing" are real occasions — "Closing Reception",
# "Closing Party for IDENTITIES", "Closing Night With Juilliard Music",
# "Closing the Gap: Investor Breakfast" — and mid-name "Closing:" adds
# "Summer Reading Closing: Myron the Magnificent", "Gallery Closing: …",
# "Early Closing: 2PM". Measured 2026-08-24 over all 199,916 events: the
# anchored form matches 4, all four of them w2014 holiday closures (28631
# Presidents Day, 75335 Easter, 132286 Memorial Day, 231355 Labor Day), 0 false
# positives. The `closed|closure` description gate below still applies and is
# what would spare a hypothetical "Closing: Party for <show>".
_CLOSURE_NOTICE_NAME_RE = re.compile(
    r'\b(?:closed(?!\s*caption)|closure)\b'
    r'|^\s*closing\s*[:\u2013\u2014-]\s*\S', re.IGNORECASE)
_CLOSURE_NOTICE_NAME_VETO_RE = re.compile(
    r'\bearly\s+clos(?:ure|ing|ed|es)\b|\bclos(?:ing|ed|es)\s+early\b'
    r'|\b(?:registration|application|applications|submission|submissions|'
    r'entries|entry|rsvps?|ticket|tickets|voting|nominations?)\s+'
    r'clos(?:ed|es|ure|ing)\b',
    re.IGNORECASE)
_CLOSURE_NOTICE_DESC_RE = re.compile(r'\b(?:closed|closure)\b', re.IGNORECASE)


def _is_closure_notice(name, description=None):
    """True for a "<facility> Closed" notice, not an event."""
    if not name:
        return False
    if not _CLOSURE_NOTICE_NAME_RE.search(name):
        return False
    if _CLOSURE_NOTICE_NAME_VETO_RE.search(name):
        return False
    description = description or ''
    return bool(_description_adds_nothing(name, description)
                or _CLOSURE_NOTICE_DESC_RE.search(description))


# Sibling shapes prototyped here and DELIBERATELY REJECTED — they cannot be made
# precise enough for this function, so they live in
# scripts/find_review_candidates.py (human review) instead.
# Measured over all 179,767 events (180,262 for the observance rule):
#
#   awareness-observance titles ("National … Day/Week", "World … Day") — filed
#     as the sibling of (2) above, and it is the opposite verdict. 75 matches
#     and the large majority are REAL programming: World Tai Chi Day at Bryant
#     Park (free instruction + demonstrations), National Trails Day (a hike),
#     World Fish Migration Day (seining the Harlem River), National Scrabble
#     Day, World Circus Day, International Women's Day. Scoping it to the
#     Parks/conservancy source that raised it does NOT rescue it — Fort Tryon's
#     own "National Wildflower Week" and "World Migratory Bird Day" are guided
#     tours and bird walks. The two genuine junk rows (190775, 190776) differ
#     only in the DESCRIPTION: they invite you to visit the park on your own
#     ("the perfect place to celebrate", "take a moment to recharge") with no
#     gathering. That distinction is far too fuzzy for this function.
#
#   ticket giveaways ("… Free Tickets Giveaway") — 6 hits, but e191251 "Free
#     Shakespeare in the Park Ticket Giveaway" at Snug Harbor is a REAL,
#     attendable in-person ticket-distribution event. A promo notice and a
#     distribution event are not separable from the text.
#
#   standing food/drink features ("Taco Tuesday", "Jerk Fest") — a
#     dining-offer description gate caught **109 rows, many of them real
#     events**: "Soul Supper - Live Motown & Soul Dining Experience", the
#     immersive murder mystery "Speakeasy, Die Softly" (three-course meal
#     included), the "Month Of Love" jazz series, a community potluck. A
#     three-course meal is a very common *component* of a real event.
#
#     RE-TESTED 2026-08-09 in its tightest possible form and REJECTED AGAIN
#     (.scratch/jf_measure.py). The tight form was: the WHOLE name is
#     "<menu-item> <Weekday>", the description is a bare price offer
#     ($N / half-price / "buy X get Y"), and no programming word appears. Over
#     all 183,900 events it fires on **3 rows** — Greenwood Park's already-
#     suppressed "Taco Tuesdays" and "Burger Mondays", plus **e18533 "Whiskey
#     Wednesday" (Mosaic), which is LIVE and `reviewed=1`: a human looked at it
#     and deliberately kept it.** So the tightest safe rule buys 2 rows and
#     costs 1 reversal of an explicit editorial decision.
#     The review record shows the class is a venue-by-venue judgment, not a
#     fact: `reviewed=1, suppressed=0` on "Taco Tuesday" (e7862, Jungly),
#     "Martini Monday" (e13254), "Whiskey Wednesday" (e18533) and "Happy Hour
#     Friday" (e139462, the Aldrich Museum's extended-hours art programming);
#     `reviewed=1, suppressed=1` on the near-identical "Taco Tuesday" (e210703,
#     Miss Lily's) and "Steak Monday" (e138556). Near-misses in the same shape
#     are unambiguously real: "Soup Sunday" (e211561, a free communal meal),
#     "Taco Tuesday" whose body is "$5 Tacos & Margarita Pitchers + Bingo
#     Night!". `_DRINK_PROMO_NAME_RE` above already excludes weekday forms for
#     the same reason. **This class belongs to `/hide-uninteresting-events`**
#     (find_review_candidates.py pattern 1 + pattern 31), where the call stays
#     visible and reversible — do not also add it here.
#
# Don't re-add either without re-running .scratch/junkfilter_precision.py.


# SEO / affiliate listicles injected into a crawled feed. Nine of these landed
# on the map in July 2026 via website 388 (RA / Resident Advisor's GraphQL feed),
# each with a real NYC venue attached because the location matcher happily pinned
# the fake row: "Allstate Insurance Quick Pay — Fastest Bill Pay Method Available
# 2026", "Progressive Insurance — The Definitive Consumer Guide 2026", ...
#
# They all share one shape: the title IS the whole row (description is either the
# title verbatim or empty), the title ends in the target SEO year, and it carries
# commercial bill-pay / how-to-guide phrasing. All four gates are required —
# any single one of them alone would eat real events:
#   - "How to Apply For Funding" clinics are real, dated, attendable events;
#   - plenty of real events end in a year ("... (May 2026)");
#   - plenty of real events have a blank description.
# The attendable-word veto is the lookahead that saves them (verified: it is what
# spares the three "Brooklyn Org Application Clinic: How to Apply ... (2026)"
# rows, the only real events that clear the year+marker gates).
_SEO_LISTICLE_YEAR_TAIL_RE = re.compile(r'\b(?:20[2-3]\d)\s*[)\]\.]?\s*$')
_SEO_LISTICLE_MARKER_RE = re.compile(
    r'\b(?:bill\s*pay|quick\s*pay|auto[\s-]?pay|one[\s-]?time\s+payment|'
    r'make\s+a\s+payment|pay\s+(?:my|your|online|by\s+phone|without|bill)|'
    r'how\s+to\s+(?:pay|find|get|cancel|contact|apply|file|claim|save)|'
    r'ways?\s+to\s+pay|where\s+to\s+find|'
    r'policy\s+number|account\s+number|routing\s+number|member\s+id|'
    r'grace\s+period|customer\s+(?:service|support|care)|'
    r'no\s+(?:account|login|credentials?|sign[\s-]?up|password)\s+'
    r'(?:needed|required)|'
    r'without\s+(?:login|logging\s+in|an?\s+account|credentials)|'
    r'(?:definitive|ultimate|complete|comprehensive|essential|beginner\'?s?)\s+'
    r'(?:[a-z]+\s+){0,2}guide|'
    r'step[\s-]by[\s-]step|everything\s+you\s+need\s+to\s+know|'
    r'\bexplained\b|\blogin\b|\bsign[\s-]?in\b|'
    r'promo\s+code|coupon\s+code|discount\s+code|free\s+trial|'
    r'refinance|mortgage\s+rates?|credit\s+score|'
    r'\bnear\s+me\b)',
    re.IGNORECASE)
# Any word that implies somebody shows up somewhere vetoes the drop.
_SEO_LISTICLE_VETO_RE = re.compile(
    r'\b(?:party|concert|gig|festival|fest|workshop|class(?:es)?|show(?:case)?|'
    r'\bdj\b|live|tour|screening|film|movie|market|gala|benefit|night|brunch|'
    r'dinner|meetup|meeting|conference|summit|panel|talk|lecture|seminar|fair|'
    r'expo|race|run|walk|yoga|dance|comedy|karaoke|trivia|exhibition|opening|'
    r'reception|performance|reading|book|game|tournament|camp|retreat|'
    r'celebration|parade|ceremony|graduation|recital|jam|mixer|social|'
    r'fundraiser|auction|clinic|training|bootcamp|hackathon|demo\s*day)\b',
    re.IGNORECASE)


def _is_seo_listicle_spam(name, description):
    """True for affiliate/SEO listicle rows injected into an event feed.

    Four gates, all required: the row is title-only (description empty or a
    verbatim copy of the title), the title ends in a year, it carries commercial
    bill-pay/how-to-guide phrasing, and it contains no attendable-event word.
    """
    if not name:
        return False
    normalized_name = re.sub(r'\s+', ' ', name.strip().lower())
    normalized_desc = re.sub(r'\s+', ' ', (description or '').strip().lower())
    if not (_description_is_blank(description) or normalized_name == normalized_desc):
        return False
    if not _SEO_LISTICLE_YEAR_TAIL_RE.search(name):
        return False
    if not _SEO_LISTICLE_MARKER_RE.search(name):
        return False
    return not _SEO_LISTICLE_VETO_RE.search(name)


# (5) Room-booking-calendar shapes. Some venues publish their internal
# room-reservation calendar on the same feed as their public programming, so
# staff meetings, third-party private bookings, maintenance blocks and
# hours/closure notices all reach the extractor looking like events. BCCLS
# Libraries (w3530, 77 member libraries on LibCal) is the worst offender: on
# 2026-08-08 it produced 13 of the 14 rows that the event-type classifier could
# only label UNKNOWN, and every one had to be hand-suppressed.
#
# The arms below were each measured over all 188,480 events before shipping
# (.scratch/rb_precision2.py): 53 net-new rows, 53 genuine junk, 0 false
# positives, 1 of them live (186516, below). They are deliberately NOT scoped to
# w3530 — every arm is anchored tightly enough to measure clean corpus-wide, and
# the same shapes come from other booking calendars (Glow Cultural Center w3009,
# ArteVino Studio, 54 Below). Hard-coding a website id here would also break the
# city-agnostic fork contract in CLAUDE.md.
#
# `RENTAL:`-prefixed listings stay OUT of scope, per the existing convention in
# `_NON_EVENT_NAME_PATTERNS`: venues use that prefix on public events too.

# (5a) Private-booking titles. `_NON_EVENT_NAME_PATTERNS` already covers
# "private rental" / "private booking"; these are the sibling nouns the same
# calendars use ("Private Meeting", "Private Session - Up Lift", "Private Event
# - Girl Scouts", "SUMMIT Private Events"). 40 corpus hits, all of them either a
# genuine invitation-only booking or the venue advertising its private-hire
# space; none live.
#
# The veto is measured, not decorative: St. Mazie posts "Private Event from
# 7-9pm + Open to the Public at 9:30pm!" (e73111, `reviewed=1, suppressed=0` —
# a human deliberately kept it) and e43997. The room is privately booked for
# part of the night and genuinely public afterwards, so the row is a real
# listing and must survive.
# `part(y|ies)` added 2026-08-17 for the rezclick class-booking calendars
# (Painting Lounge w1190, w28), which publish every reserved slot in the same
# feed as the public classes: "Private Party - Ryan W. / NYU - Starry Night Over
# Manhattan (2hr:Midtown:Main)", "Private Party - Amber P. / Galentine's Event",
# down to a bare "Private Party". Before this the merger folded them into the
# public class of the same painting; the cross-location guard now detaches them
# instead, which left them displaying as nothing at all — so drop them at
# extraction rather than relying on the merger. Measured over all 191,070
# events: 80 net-new rows, **all** of them bookings, **zero** live, all from
# those two websites. The existing "open to the public" veto still applies.
_PRIVATE_BOOKING_NAME_RE = re.compile(
    r'\bprivate\s+(?:meeting|event|session|function|use|hire|part(?:y|ies))s?\b',
    re.IGNORECASE)
_PRIVATE_BOOKING_NAME_VETO_RE = re.compile(
    r'\bopen\s+to\s+the\s+(?:general\s+)?public\b|\bpublic\s+welcome\b',
    re.IGNORECASE)

# (5a2) A tentative HOLD leaked from a shared room-booking calendar. The
# organiser blocks the room before the session is confirmed and titles the block
# "HOLD: <what it might become>"; the feed publishes the placeholder verbatim.
# This is the [[shared_calendar_leakage]] shape, and until 2026-08-24 it was
# caught only by hand: NYC Resistor (w716) alone accounts for a hand-suppression
# trail of 20+ rows, joined by Greenwich Library (e228047) and Yonkers Public
# Library ("Hold-Devon", "Hold-Peggy Belles" — both room bookings whose entire
# body is "meeting").
#
# TWO SHAPES, both deliberately narrow:
#   * `Hold<sep>` — the word followed immediately by a colon or dash, any case.
#   * `HOLD ` — the word in ALL CAPS followed by a space, and the next token must
#     contain a lowercase letter ("HOLD Kitchen Lithography", e231327). The
#     lowercase lookahead is what keeps an all-caps real title safe: a site that
#     upper-cases every name would otherwise donate "HOLD YOUR BREATH".
#
# The separator is REQUIRED, not decoration. Measured 2026-08-24 over all 199,916
# events: `^hold\b` matches 54 and a dozen of them are real — "Hold It Down Nyc",
# "Hold Me Tight (Serre-moi fort)", "Hold On To Your Butts", "Hold Up Movie Club",
# "Hold Em In Harlem", "Hold The Phone! & Some Beers", "Hold On To Your Music".
# The two shapes here match 40 of those 54 and EVERY ONE is a booking placeholder
# — 0 false positives — with 39 more rows over the last 60 days of crawl_events.
#
# `^hold for <thing>` ("Hold for Art Exhibit Installation", e228423) was measured
# and deliberately LEFT OUT: 2 rows DB-wide, both already suppressed, against a
# live collision risk with film titles of the "Hold for Ransom" shape, which
# cinema feeds publish with a blank description. Revisit only if it recurs.
_HOLD_PLACEHOLDER_NAME_RE = re.compile(
    r'^\s*(?:HOLD|Hold|hold)'
    r'(?:\s*[:\u2013\u2014-]\s*\S'
    r'|(?<=HOLD)\s+(?=\S*[a-z]))')

# (5b) Staff-only internal blocks ("Staff event", "Booked for Staff", "Dept Head
# Mtg."). The whole name must BE the marker — that anchoring is what keeps real
# programming alive, since "staff" is common inside genuine event titles ("Tech
# Assistance with Library Staff", e112534, a real one-on-one class). 4 corpus
# hits, all w3530, none live.
#
# A bare `^booked` prefix arm was prototyped and REJECTED: "Booked for the
# Movies: Inside Out" is a real monthly book-and-film club (6 rows), and "Booked
# & Busy", "Booked & Brewed", "Booked & Unbothered" are real reading events —
# 8 false positives against 2 true hits. "Booked for Staff" is caught here only
# because `staff` closes the name.
_STAFF_ONLY_BLOCK_NAME_RE = re.compile(
    r'^\s*(?:booked\s+for\s+)?staff\s*'
    r'(?:event|meeting|mtg\.?|day|training|development|in[\s-]?service|'
    r'only|use|retreat|luncheon)?\s*[.!]?\s*$'
    r'|\b(?:dept|department)\s+heads?\s+(?:mtg\.?|meeting)\b',
    re.IGNORECASE)

# (5c) Bare private life-occasion bookings ("Wedding", "Baby Shower"). The whole
# name is the occasion and the body says nothing — a room is booked for somebody
# else's party. 2 corpus hits: e214016 (w3530) and e186516 "Baby Shower" at Glow
# Cultural Center (w3009), which was LIVE and is the one row this batch removed
# from the map; w3009 is the same kind of raw booking calendar ("Private Event
# 2:00pm - 6:00pm", "Jerry Hold", "Volunteer Interview").
#
# Church sacraments are deliberately EXCLUDED. "Communion" (e141704, First
# Presbyterian) is a real recurring service published with no description, and
# "Baptism"/"Christening"/"Memorial Service" are the same shape. The list here
# is only occasions that are private by definition.
_PRIVATE_OCCASION_NAME_RE = re.compile(
    r'^\s*(?:the\s+)?(?:'
    r'wedding(?:\s+(?:reception|ceremony))?|'
    r'baby\s+shower|bridal\s+shower|wedding\s+shower|'
    r'rehearsal\s+dinner|engagement\s+party|'
    r'bar\s+mitzvah|bat\s+mitzvah|'
    r'funeral|repast|wake'
    r')\s*[.!]?\s*$',
    re.IGNORECASE)

# (5d) Maintenance blocks ("Repair Work" — "Community room unavailable for some
# repair work."). The whole name must be the maintenance phrase plus a
# work/project noun, which is what spares the very common real programming built
# on the same words: "Rock Painting", "Watercolor Painting for Adults", "Repair
# Cafe", "Bike Repair Workshop". 1 corpus hit.
#
# Second arm added 2026-08-20 for the equipment-work form, which needs no
# work/project noun to close it ("AV upgrade", e225249 w3530 Wyckoff Public
# Library, description-less, reached the event-type classifier as UNKNOWN). Same
# whole-name anchoring, and the systems list is a closed one: the name must be a
# building-system noun plus a work verb and nothing else, so "Sound Bath",
# "Lighting Design Workshop" and "Computer Class" cannot match. 1 corpus hit
# over all 193,874 events, not live.
_MAINTENANCE_BLOCK_NAME_RE = re.compile(
    r'^\s*(?:building|room|facility|community\s+room|floor|carpet|hvac|'
    r'boiler|elevator|roof)?\s*'
    r'(?:repair|repairs|maintenance|renovation|construction|cleaning|painting)\s*'
    r'(?:work|works|project|day)\s*$'
    r'|^\s*(?:a[/\s]?v|audio[\s-]?visual|it|network|wi[\s-]?fi|hvac|boiler|'
    r'elevator|carpet|server|phone|computer|lighting|sound|electrical|'
    r'plumbing|security)\s+'
    r'(?:upgrades?|installation|install|outage|replacement|work|works|'
    r'repairs?|maintenance)\s*[.!]?\s*$',
    re.IGNORECASE)

# (5f) Staff prep blocks — a room held while someone SETS UP for a program that
# happens later ("Kindergarten Kick-Off Craft Setup", e225259 w3530 Oakland
# Public Library, description-less). The row is the prep, not the program.
#
# A bare "setup" anywhere in the name is far too broad, so two things scope it:
# the word must CLOSE the name, and the description must add nothing. Both are
# load-bearing. Of the 5 tail-anchored corpus matches over all 193,874 events,
# 4 are real, described events — "Tech Help: Libby Set-Up" (a library class, 2
# rows), "BKO Volunteer Day: … Unpacking & Store Setup" and "Picnic Set-up"
# (volunteer shifts people sign up for) — and every one of them is spared by the
# description gate. That leaves 1 fire: e225259 itself.
_SETUP_BLOCK_NAME_RE = re.compile(r'\S\s+set[\s-]?up\s*[.!]?\s*$', re.IGNORECASE)

# (5e) "No <program>" cancelled-instance notices whose body says nothing ("No
# Storytime"). The existing `_NON_EVENT_NAME_PATTERNS` negation rule requires
# BOTH a program noun and a temporal marker ("No Storytime Today"), so the bare
# form fell through.
#
# This is the narrowest possible slice of the `^no <noun>` family that the
# facility-closure task deliberately deferred as unmeasurable: the ENTIRE name
# must be "No" plus one program noun from a closed list, AND the description
# must add nothing. Real events that open with "No" carry more than a program
# noun ("No Kidding! Comedy", "No Lights No Lycra", "No Pants Subway Ride") and
# cannot match a full-name anchor. 1 corpus hit. The broader arm — free-form
# noun phrases, "[CANCELLED]" prefixes — remains unshipped and unmeasured.
_NO_PROGRAM_NAME_RE = re.compile(
    r'^\s*no\s+(?:'
    r'story\s*times?|story\s*hours?|'
    r'programs?|programming|classes?|sessions?|meetings?|'
    r'practices?|rehearsals?|services?|'
    r'(?:baby|toddler|preschool|family|children\'?s?|kids?|teen|adult|'
    r'morning|evening)\s+'
    r'(?:story\s*time|story\s*hour|programs?|classes?|sessions?|time)'
    r')\s*[.!]?\s*$',
    re.IGNORECASE)

# (5f) Seasonal / weekday HOURS notices ("Summer Hours (2 PM Close)", "Summer
# Saturday Hours"). `_is_hours_notice` above needs a clock time in the NAME, and
# these put it in the body instead.
#
# The name gate is the load-bearing part and it is deliberately brutal: the
# whole title must be one to three season/weekday qualifiers plus the word
# "Hours", optionally trailed by a parenthetical or a short dash clause. A
# looser draft keyed on "<anything> Hours" plus an hours-y body took **31 false
# positives out of 33** — "Extended Museum Hours", "Member Morning Hours",
# "Members-Only Hours", "Open Studio Hours", "Garden Hours with a Garden
# Educator", "Teen Open Hours", "Friday Extended Hours", "Winter Recess Hours"
# are all real programming, exactly the "Extended Hours gallery night" the
# scheduled task warned about. Requiring the qualifier to be the ONLY thing
# before "Hours" removes every one of them. "Social Worker Office Hours" (a real
# recurring BCCLS service) cannot match for the same reason.
#
# The description must then state the building's hours, and any gathering
# language vetoes the drop. 2 corpus hits, both w3530.
_SEASONAL_HOURS_NAME_RE = re.compile(
    r'^\s*(?:the\s+)?'
    r'(?:(?:summer|winter|spring|fall|autumn|holiday|seasonal|weekend|weekday|'
    r'monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\s+){1,3}'
    r'hours\b'
    r'\s*(?:\([^)]{0,40}\)|[-–—:,][^.!?]{0,40})?\s*$',
    re.IGNORECASE)
_SEASONAL_HOURS_DESC_RE = re.compile(
    r'\bclos(?:e|es|ed|ing)\s+(?:at|early|on)\b'
    r'|\bhours\s+(?:are|will\s+be|:)'
    r'|\b(?:library|building|branch|museum|office)\b[^.!?]{0,40}'
    r'\b(?:open|closed?)\b[^.!?]{0,20}\d',
    re.IGNORECASE)
_SEASONAL_HOURS_VETO_RE = re.compile(
    r'\b(?:join\s+us|register|registration|rsvp|workshop|class|performance|'
    r'concert|screening|tour|drop[\s-]?in|all\s+ages\s+welcome)\b',
    re.IGNORECASE)

# (5g) Outside organizations booking the room. The calendar row names WHO has the
# space, not what is happening ("Historical Society", e222076 w3530 Oakland
# Public Library; "Saddle River Valley Lions Club", e214224; "Girl Scouts",
# e169811) — the same BCCLS LibCal feed as the rest of this block.
#
# Two gates, both required. The whole name must BE an organization name whose
# head is one of a closed list of civic/fraternal org types, and the description
# must add nothing: a described row is a real program the org is hosting and
# survives untouched. Measured over all 190,989 events, the name gate alone hits
# 14 rows; the blank-description gate cuts that to 5 (e92077, e169811, e210304,
# e214224 and today's e222076), and every row it drops is a bare booking. Zero
# of the 5 are live, zero were reviewed-and-kept.
#
# What the description gate saves is the point of it: "Yonkers Historical
# Society" (e99365, e144607) carries "Monthly meeting", "Girl Scouts" (e131176)
# carries "Join the Girl Scouts for an afternoon gathering held at the Oakland
# Public Library's Makerspace", "Hawthorne Rotary Club Meeting" (e210893,
# e222090) carries a joining pitch, and "Troop 3200" (e196602) is a real Girl
# Scouts camp show — all described, all spared.
#
# Deliberately EXCLUDED after measurement: garden clubs ("Our Garden Club" is a
# real BPL children's program, 8 rows; "Kids Garden Club" is a real w3530 one),
# bare "Scout"/"Troop N" (e193225 "The Scout" is a Film Forum SCREENING), PTA/PTO
# and boards of education (public meetings people attend), and craft guilds
# (library knitting/quilt guilds are open programs).
_ORG_BOOKING_NAME_RE = re.compile(
    r'^\s*(?:the\s+)?[\w.,&\'’\- ]{0,40}?\b(?:'
    r'historical\s+society|genealogical\s+society|preservation\s+society|'
    r'rotary\s+club|lions\s+club|kiwanis\s+club|optimist\s+club|'
    r'elks\s+(?:lodge|club)|moose\s+lodge|knights\s+of\s+columbus|'
    r'american\s+legion(?:\s+post\s*\d*)?|vfw(?:\s+post\s*\d*)?|'
    r'chamber\s+of\s+commerce|'
    r'(?:girl|boy|cub)\s+scouts?(?:\s+troop\s*\d*)?'
    r')'
    # Optional "of <Affiliation>" tail — national and council-level org names
    # ("Girl Scouts of America", "Girl Scouts of Northern New Jersey") are the
    # same bare booking as the bare head, but the original tail stopped at
    # "meeting" and let them through. Added 2026-08-23 after e230446 reached the
    # map and was only caught at event-type classification. Re-measured over all
    # 199,302 events: 3 newly dropped (214080, 216487, 230446), all genuine bare
    # bookings, 0 false positives — "Girl Scouts of NJ" (e98162) writes up its
    # meetings and the description gate spares it, exactly as designed.
    r'(?:\s+of\s+(?:the\s+)?[\w.\'’\- ]{1,40}?)?'
    r'\s*(?:meeting)?\s*[.!]?\s*$',
    re.IGNORECASE)
# A content word anywhere in the title means the org is PRESENTING something, so
# the row is a real program even though it ends on the org's name
# ("Lecture: Bergen County Historical Society").
_ORG_BOOKING_NAME_VETO_RE = re.compile(
    r'\b(?:lecture|talk|presentation|program|workshop|class|tour|exhibit(?:ion)?|'
    r'sale|fair|festival|dinner|breakfast|lunch(?:eon)?|ceremony|awards?|'
    r'open\s+house|book|film|concert|show|party|celebration|fundraiser|'
    r'induction|installation)\b',
    re.IGNORECASE)

# (5h) Month-CALENDAR placeholder rows. A venue's own monthly calendar page gets
# extracted as if it were an event: "The Stone at The New School: September
# Calendar" (e221887 w653) — description is boilerplate venue copy, occurrence is
# the whole month (2026-09-01 → 2026-09-30). **This shape recurs every month** —
# the June (e158041) and July (e178870) rows are already in the table — and the
# community-board feeds emit it continuously in the mirrored word order
# ("Bronx Community Board 11 Calendar - April 2026", e19334; "Bronx Community
# Board 11 Monthly Calendar - May 2026", e25605, which is LIVE on the map today).
#
# The gate is the month qualifier sitting directly on "Calendar" at the end of
# the title, in either order. That is what separates a calendar-page row from the
# real events that merely end on the word: 40 events table-wide end in
# "Calendar", and a bare `calendar$` rule would kill "Back-to-School: Design you
# Own Calendar" (e217078, LIVE), "What Are You Doing Tonight? How to Start Your
# Own Events Calendar" (e143159, a real panel) and "Calendar" (e17132, Atom
# Egoyan's FILM at w986). Requiring the month drops all three.
#
# Venue-listing placeholders without a month ("Chelsea Studio Calendar",
# "Event Calendar", "Brooklyn Music Kitchen Entertainment Calendar" — 20 rows,
# all junk, all archived) are a DIFFERENT shape and stay unfiltered: the same
# name gate that catches them catches the film and the two craft programs.
#
# Measured over all 190,989 events: 16 matches, 16 calendar-page placeholders,
# zero real events, zero reviewed-and-kept, 2 of them currently live (e25605,
# e47673 — both correct kills).
_MONTH_NAMES = (
    r'(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|'
    r'jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|'
    r'dec(?:ember)?)'
)
# (5i) Operational notices that a venue's CMS dates like programming. Three
# shapes, all surfaced 2026-08-22 as UNKNOWN rows that reached the map:
#
#   - Early-closing notices ("Greenwich Library Early Close (5pm ET)",
#     "Bookstore Closing Early", "Early Closing: 2PM"). Name-only by design: the
#     body is always a real sentence explaining the early close, so a
#     description gate would spare every one of them. Corpus-checked over all
#     198,068 events: 20 matches, all genuine closure notices, 0 false
#     positives. A programmed event never advertises itself by its closing time.
_EARLY_CLOSE_NAME_RE = re.compile(
    r'\b(?:early\s+clos(?:e|ing)|clos(?:es|ing)\s+early|will\s+close\s+at|'
    r'clos(?:ed|ing)\s+at\s+\d)',
    re.IGNORECASE)

#   - Administrative deadlines ("Last Day to Turn in Reading Logs",
#     "Photography Show Registration Closes", "Application Deadline"). Adjacent
#     to the existing submission-call rule, which keys on "Open Call" /
#     "Submissions:" and misses deadline phrasing. Anchored at the START of the
#     name so a real program that merely mentions a deadline downstream survives.
#     Corpus-checked at the final width: 67 matches, all genuine deadlines
#     (mostly NYU/CUNY registrar milestones already covered in spirit by the
#     academic-calendar rule), 0 false positives.
#     Two shapes, anchored at opposite ends, and both anchors are load-bearing.
#     "Last Day to" / "Deadline" only count at the START, so a real program that
#     mentions a deadline downstream survives. The registration/submission idiom
#     only counts at the END: an earlier draft allowed a 50-character prefix and
#     a unit test immediately caught "Poetry Workshop (registration closes
#     Friday)" — a real workshop whose title merely names its cutoff. Requiring
#     the idiom to CLOSE the title keeps "Photography Show Registration Closes"
#     and "Teen Council Spring 2026 Application Deadline" while sparing it.
_ADMIN_DEADLINE_NAME_RE = re.compile(
    r'^\s*(?:last\s+(?:day|chance)\s+to\b|deadline\b)'
    r'|\b(?:registration|sign[\-\s]?ups?|submissions?|applications?)\s+'
    r'(?:close|closes|closed|due|deadline|ends)\s*[.!]?\s*$',
    re.IGNORECASE)

#   - Facility maintenance blocks whose name ENDS on "maintenance"
#     ("Discovery Lab Maintenance"). The existing
#     `_MAINTENANCE_BLOCK_NAME_RE` only recognises a fixed prefix vocabulary
#     (building/room/HVAC/...), so a named room slips it. Tail-anchoring alone
#     is NOT safe — "Bike Maintenance" and "Car Maintenance" are real library
#     classes — so this additionally requires the body to be blank or to say the
#     space is closed/unavailable. Corpus-checked: 1 match, 0 false positives.
_MAINTENANCE_TAIL_NAME_RE = re.compile(
    r'^[\w\'\u2019\-&. ]{1,45}\bmaintenance\s*[.!]?\s*$', re.IGNORECASE)
_MAINTENANCE_CLOSED_DESC_RE = re.compile(
    r'\b(?:clos(?:ed|ing|es)|unavailable|out\s+of\s+service)\b', re.IGNORECASE)

# (5j) A housing corporation / co-op board booking a public room, titled with the
# entity's own name ("Huntington Village Coop / Nathan Hale Owners Corp").
# Deliberately NARROW: an earlier draft keyed on a generic "association|inc|corp"
# tail and produced 7 false positives out of 10 corpus matches — "Street Tree
# Care w/ Decatur Block Association" and "Music Storytime With Intersection Music
# and Arts, Inc." are real programs, and "RVC Civic Association" is exactly the
# civic engagement the review doc says to KEEP. Only housing/condo entity types
# are listed here, and a preposition or activity word anywhere vetoes the match.
# Corpus-checked at this width: 1 match, 0 false positives.
_HOUSING_CORP_NAME_RE = re.compile(
    r'^\s*(?:the\s+)?[\w.,&\'\u2019/\- ]{0,60}?\b(?:'
    r'owners\s+corp\.?(?:oration)?|home\s?owners\s+association|hoa|'
    r'tenants?\s+association|condominium(?:\s+association)?|'
    r'co[\-\s]?op(?:erative)?(?:\s+board)?'
    r')\s*[.!]?\s*$', re.IGNORECASE)
_HOUSING_CORP_VETO_RE = re.compile(
    r'\b(?:w/|with|feat\.?|featuring|presented\s+by|hosted\s+by|celebrate|'
    r'storytime|lecture|talk|workshop|class|tour|sale|fair|festival|party)\b',
    re.IGNORECASE)

_MONTH_CALENDAR_NAME_RE = re.compile(
    r'(?:'
    #  "... September Calendar", "May 2026 Meeting Calendar", "June 2026 Monthly Calendar"
    r'\b(?:' + _MONTH_NAMES + r'|monthly)\s+(?:\d{4}\s+)?'
    r'(?:(?:meeting|monthly|events?|program(?:ming)?)\s+)?calendar'
    r'|'
    #  "... Calendar - April 2026", "Monthly Calendar: September"
    r'\bcalendar\s*[-–—:,]\s*' + _MONTH_NAMES + r'\b(?:\s+\d{4})?'
    r')\s*[.!]?\s*$',
    re.IGNORECASE)
# A calendar someone MAKES is a real craft program, not a listing page.
_MONTH_CALENDAR_VETO_RE = re.compile(
    r'\b(?:make|makes|making|maker|create|creating|craft(?:ing)?|diy|'
    r'design(?:ing)?|decorate|decorating|paint(?:ing)?|collage|print(?:ing)?|'
    r'scrapbook(?:ing)?|photo|workshop|class|advent)\b',
    re.IGNORECASE)


def _is_private_booking_name(name, description=None):
    """True for a title that IS a private booking, not an attendable event."""
    if not name:
        return False
    if not _PRIVATE_BOOKING_NAME_RE.search(name):
        return False
    return not _PRIVATE_BOOKING_NAME_VETO_RE.search(name + ' ' + (description or ''))


def _is_room_reservation(name, description=None):
    """True for a patron/room-reservation placeholder row.

    The description gate accepts three shapes, all of which say nothing beyond
    the booking: blank, a verbatim echo of the title, or ANOTHER reservation
    line. The third case is why e214168 ("Patron Reservation" / "Patron
    Reservation - Mahjong") slipped the original rule — the body restates the
    booking with the patron's activity appended, which `_description_adds_nothing`
    correctly refuses to call an echo.
    """
    if not name or not _ROOM_RESERVATION_NAME_RE.match(name):
        return False
    if _description_adds_nothing(name, description):
        return True
    return bool(_ROOM_RESERVATION_NAME_RE.match((description or '').strip()))


def _is_seasonal_hours_notice(name, description=None):
    """True for a "<season/weekday> Hours" building-hours notice."""
    if not name or not _SEASONAL_HOURS_NAME_RE.match(name.strip()):
        return False
    if _SEASONAL_HOURS_VETO_RE.search(name + ' ' + (description or '')):
        return False
    return bool(_SEASONAL_HOURS_DESC_RE.search(description or ''))


def _is_org_room_booking(name, description=None):
    """True for a calendar row whose whole title is the organization holding it."""
    if not name or not _ORG_BOOKING_NAME_RE.match(name):
        return False
    if _ORG_BOOKING_NAME_VETO_RE.search(name):
        return False
    return _description_adds_nothing(name, description)


# (5k) The library "NO <Program>" cancelled-session convention. LibNet/LibCal
# branches announce a skipped session by prefixing the program's own title with
# a capitalised "NO" ("NO Senior Movie", "NO Music & Movement"). The existing
# "No <thing> Today" rule above cannot reach these: it requires a temporal
# marker ("today", "this week", a holiday), and this convention carries none.
#
# Two guards, and BOTH are load-bearing — a bare `^NO ` matched 12 rows corpus-
# wide of which 9 were real events:
#   - Case-sensitive, and vetoed when the rest of the title is itself all-caps,
#     so a shouted title contributes no signal.
#   - A blank / title-echoing description is REQUIRED. That single gate is what
#     separates the notices from "NO PICNIC Introduced by filmmaker Philip
#     Hartman" (a 1985 film, 5 rows) and "NO TE ENAMORES FEST 3" (a Spanish
#     warehouse party, 3 rows) — every one of those is written up properly.
#
# Corpus-checked over all 199,302 events: 2 matches, both genuine cancellation
# notices (230422, 230474), 0 false positives.
_NO_PREFIX_CANCELLED_RE = re.compile(r'^\s*NO\s+(?=[^\W\d_])')


def _is_no_prefix_cancellation(name, description=None):
    """True for a library "NO <Program>" skipped-session row with no body."""
    if not name or not _NO_PREFIX_CANCELLED_RE.match(name):
        return False
    rest = _NO_PREFIX_CANCELLED_RE.sub('', name.strip())
    letters = [c for c in rest if c.isalpha()]
    # An all-caps remainder means the whole title is shouted; "NO" is then just
    # part of the styling, not a marker. Too few letters to judge = same veto.
    if len(letters) < 3 or all(c.isupper() for c in letters):
        return False
    return _description_adds_nothing(name, description)


def _is_early_close_notice(name, description=None):
    """True for an early-closing operational notice ("Bookstore Closing Early")."""
    return bool(name and _EARLY_CLOSE_NAME_RE.search(name))


def _is_admin_deadline(name, description=None):
    """True for an administrative deadline row ("Last Day to ...", "... Registration Closes")."""
    return bool(name and _ADMIN_DEADLINE_NAME_RE.search(name.strip()))


def _is_maintenance_tail_block(name, description=None):
    """True for "<named room> Maintenance" when the body is blank or says closed.

    The description gate is load-bearing: "Bike Maintenance" is a real class.
    """
    if not name or not _MAINTENANCE_TAIL_NAME_RE.match(name.strip()):
        return False
    if _description_is_blank(description):
        return True
    return bool(_MAINTENANCE_CLOSED_DESC_RE.search(description or ''))


def _is_housing_corp_booking(name, description=None):
    """True for a co-op / owners-corp room booking titled with the entity name."""
    if not name or not _HOUSING_CORP_NAME_RE.match(name.strip()):
        return False
    if _HOUSING_CORP_VETO_RE.search(name):
        return False
    return _description_adds_nothing(name, description)


def _is_month_calendar_placeholder(name, description=None):
    """True for a "<Month> Calendar" listing-page row extracted as an event."""
    if not name or not _MONTH_CALENDAR_NAME_RE.search(name.strip()):
        return False
    return not _MONTH_CALENDAR_VETO_RE.search(name)


def _is_take_home_kit(name, description=None):
    """True for a take-home / grab-and-go kit distribution, not a gathering.

    Four gates: the pickup idiom in the NAME, a kit/craft word in either field,
    pickup corroboration in the DESCRIPTION, and no veto. The veto is two-tier —
    see the comment block above `_TAKE_HOME_KIT_NAME_RE` for why `join us` alone
    is not allowed to save a row that also says "while supplies last".
    """
    description = description or ''
    if not name or not description:
        return False
    if not _TAKE_HOME_KIT_NAME_RE.search(name):
        return False
    if not (_TAKE_HOME_KIT_SIGNAL_RE.search(name)
            or _TAKE_HOME_KIT_SIGNAL_RE.search(description)):
        return False
    if not _TAKE_HOME_KIT_DESC_RE.search(description):
        return False
    both = name + ' ' + description
    if _TAKE_HOME_KIT_VETO_RE.search(both):
        return False
    if (_TAKE_HOME_KIT_SOFT_VETO_RE.search(both)
            and not _TAKE_HOME_KIT_PICKUP_RE.search(description)):
        return False
    return True


def _is_ticket_product_package(name, description=None):
    """True for a ticketing upsell product (a package/bundle), not an event.

    See the comment block above `_TICKET_PRODUCT_NAME_RE`.
    """
    if not name or not _TICKET_PRODUCT_NAME_RE.search(name):
        return False
    description = description or ''
    if not _TICKET_PRODUCT_DESC_RE.search(description):
        return False
    return not _TICKET_PRODUCT_VETO_RE.search(name + ' ' + description)


def _is_food_holiday_promo(name, description=None):
    """True for a "National <food/drink> Day" restaurant marketing post."""
    if not name or not _FOOD_HOLIDAY_NAME_RE.match(name):
        return False
    if not _FOOD_HOLIDAY_DESC_RE.search(description or ''):
        return False
    return not _FOOD_HOLIDAY_VETO_RE.search(name + ' ' + (description or ''))


def is_obvious_non_event(name, description=None):
    """Return True if the event is an unmistakable non-event.

    Covers closures, calls for submissions/grants, venue rentals, season-pass
    listings, cinema showtime placeholders, SEO spam, fundraising campaigns,
    submission-call contests, festival info-booth listings, childcare-amenity
    listings, senior-center congregate-meal menus, registration-window
    announcements, academic/registrar calendar milestones (add/drop deadlines,
    term start dates, exam periods), take-home/grab-and-go kit distributions,
    program-deadline notices, room-booking-calendar shapes (private bookings,
    staff-only blocks, private life occasions, maintenance blocks, bare
    "No <program>" notices, seasonal hours notices, tentative shared-calendar
    HOLD placeholders, outside-organization
    bookings titled with the org's own name), month-calendar listing
    placeholders, "National <food/drink> Day" restaurant promos, ticketing
    upsell products (packages/bundles), and bare
    generic placeholder names — the kinds of rows that
    should never reach the map. High precision by design; anything fuzzier
    belongs in scripts/find_review_candidates.py for human review.

    Most patterns match on the name alone; a few ambiguous categories
    (contests, booths, childcare amenities, congregate meals) also require
    corroborating description language and never fire when the description is
    missing.
    """
    if not name:
        return False
    if _NON_EVENT_NAME_RE.search(name):
        return True
    description = description or ''
    # Bare generic name with no description at all -> placeholder junk.
    if _description_is_blank(description) and _BARE_GENERIC_NAME_RE.fullmatch(name.strip()):
        return True
    # Placeholder "Untitled <format> (<venue>)" screening rows.
    if _description_is_blank(description) and _UNTITLED_PLACEHOLDER_NAME_RE.match(name):
        return True
    # Library room-booking placeholder. Uses `_description_adds_nothing` rather
    # than `_description_is_blank`: these feeds echo the title into the body.
    if _is_room_reservation(name, description):
        return True
    # Room-booking-calendar shapes (block 5): private bookings, staff-only
    # blocks, bare private occasions, maintenance blocks, bare "No <program>"
    # notices and seasonal hours notices. All fire with or without a
    # description — a blank body IS the corroboration for most of them — so they
    # cannot live in the `if description:` block below.
    if _is_private_booking_name(name, description):
        return True
    # Tentative shared-calendar HOLD ("HOLD: Synth Night", "Hold-Peggy Belles").
    # Name-only by design: the prefix is the booker's own "not confirmed" marker,
    # and these rows carry a real-looking body as often as a blank one.
    if _HOLD_PLACEHOLDER_NAME_RE.match(name):
        return True
    if _STAFF_ONLY_BLOCK_NAME_RE.search(name):
        return True
    if (_PRIVATE_OCCASION_NAME_RE.match(name)
            and _description_adds_nothing(name, description)):
        return True
    if _MAINTENANCE_BLOCK_NAME_RE.match(name):
        return True
    # Staff prep block ("… Craft Setup"). The blank/echo body is the second gate
    # — a described "… Set-Up" is a class or a volunteer shift, not a prep hold.
    if (_SETUP_BLOCK_NAME_RE.search(name)
            and _description_adds_nothing(name, description)):
        return True
    if (_NO_PROGRAM_NAME_RE.match(name)
            and _description_adds_nothing(name, description)):
        return True
    if _is_seasonal_hours_notice(name, description):
        return True
    # An outside organization's room booking, titled with the org's own name
    # ("Historical Society", "Saddle River Valley Lions Club"). Requires a body
    # that adds nothing, so a described program the org hosts survives.
    if _is_org_room_booking(name, description):
        return True
    # (5i/5j) Operational notices and housing-corp room bookings — see the regex
    # block above for the corpus counts behind each of these four gates.
    if _is_early_close_notice(name, description):
        return True
    # (5k) Library "NO <Program>" skipped-session notice with no body.
    if _is_no_prefix_cancellation(name, description):
        return True
    if _is_admin_deadline(name, description):
        return True
    if _is_maintenance_tail_block(name, description):
        return True
    if _is_housing_corp_booking(name, description):
        return True
    # "<Month> Calendar" listing-page placeholder ("The Stone at The New School:
    # September Calendar", "Bronx Community Board 11 Calendar - April 2026").
    # Name-only by design — the body is venue boilerplate either way.
    if _is_month_calendar_placeholder(name, description):
        return True
    # "National <food/drink> Day" restaurant marketing post. Two signals plus a
    # veto — a bare marker with no body stays editorial, per the 2026-07-27
    # refutation. Lives here rather than in the `if description:` block only for
    # readability; `_is_food_holiday_promo` requires a description of its own.
    if _is_food_holiday_promo(name, description):
        return True
    # "<program> Ends!" deadline notice, corroborated by a body that adds
    # nothing ("Summer Reading Ends!" / "SUMMER READING ENDS!"). The
    # deadline-language half of this rule stays in the `if description:` block
    # below; only the blank/echo half belongs up here.
    if (_PROGRAM_DEADLINE_NAME_RE.search(name)
            and _description_adds_nothing(name, description)
            and not _PROGRAM_DEADLINE_VETO_RE.search(name + ' ' + description)):
        return True
    # Opening-hours notice ("Library open 9 AM - 5 PM"). Fires with or without a
    # description — the body is normally a restatement of the hours.
    if _is_hours_notice(name, description):
        return True
    # Delayed/late opening notice ("Delayed Opening - Staff Development"). Fires
    # with or without a description, like its closure and hours siblings.
    if _is_delayed_opening_notice(name, description):
        return True
    # Facility-closure notice ("Hendricks Field Golf Course Closed"). Fires with
    # or without a description — the blank body IS the corroboration here — so it
    # cannot live in the `if description:` block below.
    if _is_closure_notice(name, description):
        return True
    # Academic/registrar calendar milestone (add/drop deadline, term start, exam
    # period). Fires with or without a description — these rows are usually
    # description-less — so it cannot live in the `if description:` block below.
    if (_ACADEMIC_MILESTONE_NAME_RE.search(name)
            and not _ACADEMIC_ATTENDABLE_VETO_RE.search(name)):
        return True
    # SEO / affiliate listicle spam ("Allstate Insurance Quick Pay — Fastest Bill
    # Pay Method Available 2026"). Fires with or without a description, so it
    # cannot live in the `if description:` block below.
    if _is_seo_listicle_spam(name, description):
        return True
    # Members-only programming ("Members-Only Tour: …", "… | MEMBERS ONLY").
    # Name-only: the title is the venue's own access notice. The veto spares
    # events AT a venue named "Members Only".
    if (_MEMBERS_ONLY_NAME_RE.search(name)
            and not _MEMBERS_ONLY_VENUE_VETO_RE.search(name)):
        return True
    # Enrolled-student academic orientation, literal-phrase arm ("New Student
    # Orientation"). Fires with or without a description; the desc-corroborated
    # arm lives in the `if description:` block below.
    if _STUDENT_ORIENTATION_NAME_RE.search(name):
        return True
    if description:
        # "On this Day:" archival post narrating a past anniversary, not a gathering.
        if (_ARCHIVAL_ON_THIS_DAY_NAME_RE.match(name)
                and _ARCHIVAL_HISTORICAL_DESC_RE.search(description)
                and not _ARCHIVAL_GATHERING_VETO_RE.search(description)):
            return True
        if (_MENU_SPECIAL_NAME_RE.match(name)
                and _MENU_SPECIAL_DESC_RE.search(description)
                and not _MENU_SPECIAL_VETO_RE.search(description)):
            return True
        # Take-home / grab-and-go / take-n-make kit distribution — a pickup, not
        # a gathering.
        if _is_take_home_kit(name, description):
            return True
        # Ticketing upsell product ("VIP & Date Night Packages", "… Experience
        # Bundle") — a thing you buy, not a thing you attend.
        if _is_ticket_product_package(name, description):
            return True
        # "<program> Ends!" submit-your-logs deadline notice.
        if (_PROGRAM_DEADLINE_NAME_RE.search(name)
                and _PROGRAM_DEADLINE_DESC_RE.search(description)
                and not _PROGRAM_DEADLINE_VETO_RE.search(name + ' ' + description)):
            return True
        if (_SUBMISSION_CONTEST_NAME_RE.search(name)
                and not _ATTENDABLE_CONTEST_NAME_RE.search(name)
                and _SUBMISSION_CALL_DESC_RE.search(description)):
            return True
        if (_APPLICATION_CALL_DESC_RE.search(description)
                and not _ATTENDABLE_OCCASION_NAME_RE.search(name)):
            return True
        # The body says, in the venue's own words, that this occasion is not
        # open to the public — enough on its own; see `_is_not_public_notice`.
        if _is_not_public_notice(name, description):
            return True
        if (_PRIVATE_BOOKING_DESC_RE.search(description)
                and _NOT_PUBLIC_DESC_RE.search(description)):
            return True
        # School orientation whose name lacks the literal "Student Orientation"
        # phrase but whose body names the student audience ("A welcome and
        # orientation day for MFA … students", e207565).
        if (_ORIENTATION_NAME_RE.search(name)
                and _STUDENT_AUDIENCE_DESC_RE.search(description)
                and not _ORIENTATION_PUBLIC_VETO_RE.search(name + ' ' + description)):
            return True
        if (_BOOTH_NAME_RE.search(name)
                and _BOOTH_MARKETING_DESC_RE.search(description)):
            return True
        if (_CHILDCARE_AMENITY_NAME_RE.match(name.strip())
                and _CHILDCARE_DURING_DESC_RE.search(description)):
            return True
        if (_CONGREGATE_MEAL_DESC_RE.search(description)
                and not _MEAL_ATTENDABLE_NAME_RE.search(name)
                and not _MEAL_REAL_EVENT_DESC_RE.search(description)):
            return True
        if (_ATTRACTION_DESC_RE.search(description)
                and _ATTRACTION_VISIT_RE.search(description)
                and not _ATTRACTION_NAME_VETO_RE.search(name)):
            return True
        if (_HOLIDAY_MARKER_NAME_RE.search(name)
                and _CLOSURE_OBSERVANCE_DESC_RE.search(description)
                and not _HOLIDAY_ATTENDABLE_DESC_VETO_RE.search(description)):
            return True
        if (_HOLIDAY_OPEN_NOTICE_NAME_RE.search(name)
                and _HOLIDAY_NAME_ANYWHERE_RE.search(name)
                and _CLOSURE_OBSERVANCE_DESC_RE.search(description)
                and not _HOLIDAY_ATTENDABLE_DESC_VETO_RE.search(name + ' ' + description)):
            return True
        if (_DRINK_PROMO_NAME_RE.search(name)
                and _PROMO_SPECIAL_DESC_RE.search(description)
                and not _PROMO_ATTENDABLE_VETO_RE.search(name + ' ' + description)):
            return True
        # Buy-one-get-one ticket promotion whose body IS the offer.
        if (_BOGO_OFFER_DESC_RE.search(description)
                and not _BOGO_ATTENDABLE_VETO_RE.search(description)):
            return True
        # A venue's standing daily happy hour, published as a dated row.
        if _is_standing_happy_hour(name, description):
            return True
        if (_RETAIL_PROMO_NAME_RE.search(name)
                and _RETAIL_PROMO_DESC_RE.search(description)):
            return True
        if (_REOPENING_NAME_RE.search(name)
                and not _REOPENING_NAME_VETO_RE.search(name)
                and _REOPENING_DESC_RE.search(description)):
            return True
    return False


# Canonical time format: compact lowercase 12-hour with no space, no colon-zero.
# Examples: '7pm', '7:30pm', '11am', '12am' (midnight), '12pm' (noon).
# Empty/sentinel values normalize to ''.
_TZ_SUFFIX_RE = re.compile(r'(est|edt|pst|pdt|mst|mdt|cst|cdt|et|pt|mt|ct)$')
_TWELVE_HOUR_RE = re.compile(r'^(\d{1,2})(?::(\d{2}))?(am|pm)$')
_HHMM_RE = re.compile(r'^(\d{1,2}):(\d{2})$')
_HH_RE = re.compile(r'^(\d{1,2})$')
# 'HH:MM:SS' (MySQL TIME columns, ISO clock strings). None of the patterns above
# match it, so it used to fall through unchanged and land in event_occurrences
# next to its own canonical 12-hour form — 79 duplicate twin rows accumulated
# that way. Drop the seconds field and re-run the normal cascade.
_SECONDS_RE = re.compile(r'^(\d{1,2}:\d{2}):[0-5]\d(am|pm)?$')
_SENTINEL_TIMES = frozenset({
    '', 'allday', 'allday/varies', 'varioustimes', 'multipletimes', 'tba', 'tbd',
    'none', 'close', 'closing', 'late', 'tbc', 'ongoing', 'sundown', 'sunrise',
    'sunset', 'dusk', 'dawn',
})


def _canonical_time(hour, minute, is_pm):
    """Build a canonical time string from a 12-hour hour (1-12), minute, and AM/PM."""
    suffix = 'pm' if is_pm else 'am'
    return f'{hour}{suffix}' if minute == 0 else f'{hour}:{minute:02d}{suffix}'


_LUMA_HOSTS = ('luma.com', 'lu.ma', 'www.luma.com', 'www.lu.ma')
_LUMA_SLUG = re.compile(r'^[a-z0-9][a-z0-9-]{4,}$', re.I)

# `lu.ma/<slug>` and `luma.com/<slug>` are the SAME page — lu.ma 301s to
# luma.com — but they are different strings, so every URL-keyed comparison
# (merger's shared-URL identity tier, detail-crawl shared-URL dedup, the
# `event_urls` uniqueness we rely on) sees two unrelated links. The Luma
# calendar injector emits `lu.ma` while embeds and other sites emit `luma.com`,
# so the same event routinely arrives under both hosts: on 2026-08-17, 3 of 10
# Luma slug collisions were invisible to the dedupe tier for exactly this
# reason, and 8 live events held both spellings of one link. Canonicalize the
# short host away at ingest so it is fixed once, for every consumer.
# `api.lu.ma` is deliberately NOT rewritten — it is a different service (the
# JSON endpoint), not an alias of the web page.
_LUMA_CANONICAL_HOST = 'luma.com'
_LUMA_ALIAS_HOSTS = frozenset({'lu.ma', 'www.lu.ma', 'www.luma.com'})


def canonicalize_luma_host(url):
    """Rewrite `lu.ma` / `www.` Luma links to the canonical `https://luma.com/…`.

    Path, query and fragment are preserved verbatim; non-Luma URLs (including
    `api.lu.ma`) are returned unchanged.
    """
    if not url:
        return url
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    if (parts.hostname or '').lower() not in _LUMA_ALIAS_HOSTS:
        return url
    if parts.port or parts.username:
        return url  # not a plain public Luma link; leave it alone
    return urllib.parse.urlunsplit(
        ('https', _LUMA_CANONICAL_HOST, parts.path, parts.query, parts.fragment))

# Luma CALENDAR-level endpoints. Luma organizer sources are crawled through the
# calendar's own JSON endpoint (`api.lu.ma/url?url=<slug>` or
# `api.lu.ma/calendar/get-items?calendar_api_id=cal-XXX`; a few sit on the
# `lu.ma/calendar/cal-XXX` page). That payload carries per-event objects AND a
# pile of calendar-level metadata — `calendar.name`, the host list, and a
# `tags[]` array of audience labels — and the extractor sometimes reads one of
# those labels as an event.
#
# e208609 "Technologists" (w5111 Fractal Tech) was exactly that: the calendar's
# own `tags[].name` ("Technologists", `upcoming_event_count: 0`), extracted with
# `url: null` and no description, then pooled **36 occurrences** scraped from
# every real Fractal Tech event's times. It false-matched every real Fractal
# meetup in the dedupe pass.
#
# The structural tell is the URL. Every genuine event in the payload carries its
# own `lu.ma/<slug>` (the slug-expanding `js_code` guarantees it), so a record
# with no event URL of its own falls back to `source_url` in
# `group_event_occurrences` and ends up pointing at the calendar endpoint it was
# extracted FROM. Calendar-level metadata is the only thing that can produce
# that shape.
_LUMA_CAL_ID_RE = re.compile(r'^/calendar/(cal-[A-Za-z0-9]+)$')


def _luma_calendar_key(url):
    """Identity of the Luma CALENDAR a URL addresses, or '' if it isn't one.

    Returns a comparable key so an event URL can be tested against the crawl's
    own source URL: 'slug:<calendar-slug>' or 'cal:<calendar-api-id>'.

    Deliberately NOT a "looks like a Luma calendar" test in isolation —
    `api.lu.ma/url?url=<slug>` also accepts an *event* slug (e199135 carries a
    live `api.lu.ma/url?url=pubkey-jj3u`, a real PubKey event whose link is
    merely the unusable JSON form). Only the comparison against the source URL
    tells the two apart.
    """
    if not url:
        return ''
    try:
        parts = urllib.parse.urlparse(url.strip())
    except ValueError:
        return ''
    host = (parts.hostname or '').lower()
    path = (parts.path or '').rstrip('/')
    query = urllib.parse.parse_qs(parts.query or '')
    if host == 'api.lu.ma':
        if path == '/url':
            slug = (query.get('url') or [''])[0].strip().lower()
            return f'slug:{slug}' if slug else ''
        if path == '/calendar/get-items':
            cal_id = (query.get('calendar_api_id') or [''])[0].strip().lower()
            return f'cal:{cal_id}' if cal_id.startswith('cal-') else ''
        return ''
    if host in _LUMA_HOSTS:
        match = _LUMA_CAL_ID_RE.match(path)
        if match:
            return f'cal:{match.group(1).lower()}'
    return ''


def is_luma_calendar_listing_url(url, source_url):
    """True when an event URL is the Luma calendar endpoint it was crawled from.

    Self-referential by design: the record has no event page of its own, so its
    "URL" is the listing it came from. `luma.com/user/<handle>` host pages are
    NOT included — those are a person, not a calendar payload, and both corpus
    instances are real described events.
    """
    key = _luma_calendar_key(url)
    return bool(key) and key == _luma_calendar_key(source_url)

# Signed-media CDN hosts (Instagram/Facebook photo delivery). The Instagram/picnob
# path sometimes hands us the post's *image* URL instead of the post permalink; those
# carry an expiring signature and 404 within weeks, so the event silently loses its
# only link. Same family as the relative-URL bug below, but time-delayed.
_SIGNED_CDN_HOST_RE = re.compile(
    r'(^|\.)(cdninstagram\.com|fbcdn\.net|fbsbx\.com)$', re.I)


def is_signed_cdn_url(url):
    """True for expiring signed-CDN media URLs, which are never event pages."""
    try:
        host = (urllib.parse.urlparse(url or '').hostname or '').lower()
    except ValueError:
        return False
    if not host:
        return False
    if _SIGNED_CDN_HOST_RE.search(host):
        return True
    # Meta's edge nodes are always a first label of `scontent` / `scontent-<pop>`;
    # matched separately so a future signed host on a new apex is still caught.
    label = host.split('.')[0]
    return label == 'scontent' or label.startswith('scontent-')


def absolutize_url(url, source_url):
    """Resolve an extracted event URL against the page it was extracted from.

    Gemini returns the href as written in the markup, so site-root paths
    ("/events/2026/05/27/ranger-tot-time") and Luma's bare event slugs ("b8mc6adj") arrive
    relative. Nothing downstream fixes them: they are stored verbatim, the exporter counts
    them as a URL, and the frontend's Utils.isValidUrl (http/https only) then skips them —
    so the event publishes with no link at all. A 2026-07-25 sweep found 2,688 such rows on
    601 live events, 175 of which had no other URL.

    Returns '' when no absolute URL can be formed, so the caller can drop it rather than
    store a link that cannot work.

    Also canonicalizes the Luma short host (`lu.ma` -> `luma.com`, see
    `canonicalize_luma_host`) so one event page has one spelling everywhere downstream.
    """
    url = (url or '').strip()
    if not url:
        return ''
    if is_signed_cdn_url(url):
        return ''  # expiring image CDN link, not an event page
    # "http://https://real.url" — a scheme glued onto an already-absolute URL.
    doubled = re.match(r'^https?://(https?://.+)$', url, re.I)
    if doubled:
        return canonicalize_luma_host(doubled.group(1))
    if re.match(r'^https?://', url, re.I):
        return canonicalize_luma_host(url)
    if url.startswith('//'):
        scheme = urllib.parse.urlparse(source_url or '').scheme or 'https'
        return canonicalize_luma_host(f'{scheme}:{url}')
    if re.match(r'^[a-z][a-z0-9+.-]*:', url, re.I):
        return ''  # mailto:, tel:, javascript: — not an event page
    if not source_url:
        return ''
    # Luma slugs are global to the site, not relative to the calendar path they were
    # listed on: /calendar/cal-XXX + "a7oxbpwy" must resolve to luma.com/a7oxbpwy.
    host = urllib.parse.urlparse(source_url).netloc.lower()
    if host in _LUMA_HOSTS and '/' not in url and _LUMA_SLUG.match(url):
        return f'https://{_LUMA_CANONICAL_HOST}/{url}'
    resolved = urllib.parse.urljoin(source_url, url)
    if is_signed_cdn_url(resolved):
        return ''
    if not re.match(r'^https?://', resolved, re.I):
        return ''
    return canonicalize_luma_host(resolved)


def _standardize_time(time_str):
    """Canonicalize a time string to compact lowercase 12-hour form.

    Examples:
        '6:30 PM' -> '6:30pm'
        '6:00pm'  -> '6pm'
        '17:38'   -> '5:38pm'
        '19:30:00'-> '7:30pm'
        '20'      -> '8pm'
        '08'      -> '8am'
        '1pmest'  -> '1pm'
        'allday'  -> ''
        '7pm'     -> '7pm'  (idempotent)

    Ambiguous inputs (bare HH:MM with HH in 1-12, bare HH in 1-12) are returned with
    whitespace/case normalized but otherwise unchanged — they could be either AM or PM
    and auto-converting risks corrupting data. Unrecognized strings get the same
    treatment so manual cleanup can find them via grep.
    """
    if time_str is None:
        return ''
    s = str(time_str).strip().lower()
    # Strip whitespace, dots, and underscores ('9_pm' -> '9pm').
    s = s.replace(' ', '').replace('.', '').replace('_', '')
    # Collapse single-digit zero minutes ('7:0pm' -> '7pm', '10:0' -> '10').
    s = re.sub(r':0(?!\d)', '', s)
    if s in _SENTINEL_TIMES:
        return ''

    # Strip US timezone suffixes (1pmest, 7pmet, etc.)
    s = _TZ_SUFFIX_RE.sub('', s)
    if not s:
        return ''

    # '19:30:00' -> '19:30', '7:30:00pm' -> '7:30pm'
    m = _SECONDS_RE.match(s)
    if m:
        s = m.group(1) + (m.group(2) or '')

    m = _TWELVE_HOUR_RE.match(s)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2) or 0)
        if 1 <= h <= 12 and 0 <= mi <= 59:
            return _canonical_time(h, mi, m.group(3) == 'pm')
        return s  # malformed (e.g. '13pm'); preserve so it's findable

    m = _HHMM_RE.match(s)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            # Unambiguous 24-hour values: hour 0 (midnight), hour 12 (noon), hour 13-23.
            # Hour 1-11 in HH:MM with no AM/PM is ambiguous; leave alone.
            if h == 0:
                return _canonical_time(12, mi, False)
            if h == 12:
                return _canonical_time(12, mi, True)
            if h >= 13:
                return _canonical_time(h - 12, mi, True)
            return s

    m = _HH_RE.match(s)
    if m:
        raw = m.group(1)
        h = int(raw)
        if 0 <= h <= 23:
            # A leading zero (e.g. '08') is a strong 24-hour signal even for hours 1-12.
            has_leading_zero = len(raw) >= 2 and raw[0] == '0'
            if h == 0:
                return '12am'
            if h == 12:
                return '12pm'
            if h >= 13:
                return _canonical_time(h - 12, 0, True)
            if has_leading_zero:
                return _canonical_time(h, 0, False)  # '08' -> '8am'
            return s  # bare '6' is ambiguous; leave alone

    return s  # unrecognized; preserve original text (normalized whitespace/case)


_SOURCE_MIDNIGHT_RE = re.compile(r'(?<!\d)12\s*am\b', re.IGNORECASE)


def _sanity_check_end_time(start_time, end_time, source_text):
    """Fix '12pm' (noon) end_time when context implies midnight close.

    Gemini occasionally emits '12am' (midnight) as '12pm' (noon). Two cheap
    heuristics catch the common cases:

    1. PM start with 12pm end is impossible — '7pm-12pm' would mean going
       backward through noon, so flip to 12am unconditionally.
    2. AM start with 12pm end is usually noon — but if the source text
       explicitly mentions '12am', the extractor probably misread it.

    Inputs are canonicalized internally; the original end_time is returned
    when nothing matches, so the caller's idempotency contract is preserved.
    """
    if _standardize_time(end_time) != '12pm':
        return end_time
    std_st = _standardize_time(start_time)
    m = _TWELVE_HOUR_RE.match(std_st)
    if m and m.group(3) == 'pm' and 1 <= int(m.group(1)) <= 11:
        return '12am'
    if source_text and _SOURCE_MIDNIGHT_RE.search(source_text):
        return '12am'
    return end_time


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

    def loc_key(d):
        """Location identity for a row/group: resolved location_id if known,
        else the normalized location_name, else None (unknown)."""
        lid = d.get('location_id')
        if lid:
            return ('id', lid)
        loc = re.sub(r'\s+', ' ', (d.get('location') or '').strip().lower())
        return ('name', loc) if loc else None

    def locations_compatible(a, b):
        """Two rows may group only if their locations don't conflict. A missing
        location, or an id-vs-name mismatch we can't compare, is treated as
        compatible; two different resolved ids (or two different names) are not.
        This stops a generic name ("National Trails Day") from absorbing a
        distinct event at another venue ("...: Highbridge Park Guided Walk")
        purely because one name is a substring of the other."""
        if a is None or b is None or a[0] != b[0]:
            return True
        return a[1] == b[1]

    def urls_compatible(row_url, existing_urls):
        """Gate for the substring-containment branch only: two listings that
        carry DIFFERENT event URLs are different ticketed events, so a shorter
        name must not swallow a longer one across a URL boundary.

        Measured failure (2026-07-31, every Regal site): the chain lists
        "PAW Patrol: The Dino Movie-Early Access" (HO00022109, Aug 8) and
        "PAW Patrol: The Dino Movie" (HO00021331, Aug 13-20) as separate
        detail pages. Containment fused them, the shorter name won, and the
        regular run's eight showtimes inherited the Early Access ticket URL —
        the same shape for "… Fan Event" and "(Sensory)" siblings.

        Deliberately permissive: a missing URL on either side still groups, and
        exact / normalized-equal names never reach this check, so a series
        listed once per date with per-date URLs (The Boat Yard's "Family Night"
        at /event/family-night-<date>/) still collapses into one event."""
        if not row_url or not existing_urls:
            return True
        return row_url in existing_urls

    def find_matching_group_key(event_name, row_loc, row_url, grouped_events,
                                normalized_group_keys, group_event_urls):
        normalized_event = normalize_name_for_grouping(event_name)
        for existing_key, existing in grouped_events.items():
            if not locations_compatible(row_loc, loc_key(existing)):
                continue
            normalized_existing = normalized_group_keys[existing_key]
            if event_name == existing_key or normalized_event == normalized_existing:
                return existing_key
            if len(normalized_event) >= 5 and len(normalized_existing) >= 5:
                if normalized_event in normalized_existing or normalized_existing in normalized_event:
                    if not urls_compatible(row_url, group_event_urls.get(existing_key)):
                        continue
                    return existing_key
        # No location-compatible group matched. If the plain name is already a
        # key, it belongs to a location-INCOMPATIBLE group (a compatible one
        # would have matched above) — returning it here would silently merge two
        # distinct venues that share an event name (e.g. Puzzled Pint's identical
        # monthly theme running the same night at Farm.One and Beer Authority).
        # Return a location-scoped key so the two stay separate.
        if event_name in grouped_events:
            return (event_name, row_loc)
        return event_name

    grouped_events = {}
    normalized_group_keys = {}
    # Event-specific URLs per group (source_url excluded) — the containment
    # branch consults these via urls_compatible.
    group_event_urls = {}
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

        row_url = absolutize_url(row_dict.get('url'), source_url)
        group_key = find_matching_group_key(
            event_name, loc_key(row_dict), row_url, grouped_events,
            normalized_group_keys, group_event_urls)
        if row_url:
            group_event_urls.setdefault(group_key, set()).add(row_url)

        if group_key not in grouped_events:
            base_event = {k: v for k, v in row_dict.items()
                         if k not in ['start_date', 'start_time', 'end_date', 'end_time', 'sublocation', 'url']}
            base_event['occurrences'] = []

            sublocation = (row_dict.get('sublocation') or '').strip()
            if sublocation and sublocation.upper() != 'N/A':
                base_event['sublocation'] = sublocation

            # Prefer event-specific URL over source_url (which is often generic)
            urls = []
            url = absolutize_url(row_dict.get('url'), source_url)
            if url:
                urls.append(url)
            if source_url and source_url not in urls:
                urls.append(source_url)
            base_event['urls'] = urls

            grouped_events[group_key] = base_event
            # Key off the event name, not group_key: the latter may be a
            # (name, loc) tuple for location-disambiguated groups, which
            # normalize_name_for_grouping can't consume.
            normalized_group_keys[group_key] = normalize_name_for_grouping(event_name)
        else:
            existing_name = grouped_events[group_key]['name']
            if len(event_name) < len(existing_name):
                grouped_events[group_key]['name'] = event_name

            url = absolutize_url(row_dict.get('url'), source_url)
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

# Generic venue-type / room-descriptor common nouns. Stripping a borough suffix
# from a venue name like "Gallery Brooklyn" would collapse it to one of these
# bare tokens ("gallery"), and that token then exact-matches any unrelated event
# whose location is just the generic word (e.g. the Ace Hotel's in-house
# "Gallery"). When borough-stripping would leave only a single generic token, we
# keep the borough so the name stays specific. Distinctive single tokens
# ("Fotografiska", "Aurora") are unaffected and still strip normally.
#
# Deliberately NOT included: directional/area words (downtown, midtown, lower,
# east, ...). Those ARE the short form of neighborhood locations ("Midtown" ->
# "Midtown Manhattan"), so collapsing them is intended neighborhood resolution,
# not a venue collision.
GENERIC_LOCATION_WORDS = {
    'gallery', 'bar', 'lounge', 'studio', 'garden', 'lobby', 'hall', 'room',
    'cafe', 'kitchen', 'market', 'club', 'space', 'theater', 'theatre',
    'museum', 'library', 'park', 'shop', 'store', 'center', 'centre', 'hotel',
    'restaurant', 'rooftop', 'terrace', 'patio', 'courtyard', 'atrium',
    'mezzanine', 'auditorium', 'chapel', 'sanctuary', 'annex', 'pavilion',
    'plaza', 'commons', 'field', 'court', 'pool', 'deck', 'stage', 'cellar',
    'ballroom', 'parlor', 'parlour', 'gym', 'loft', 'table', 'basement',
    'harbor', 'harbour', 'sea', 'dance',
}

# Tokens that must not PREFIX-MATCH or COLLAPSE-TO a specific venue, but which
# must still count as *distinctive* when comparing two venue names.
#
# "playground" needs the first behaviour and not the second. A bare
# "Playground" was prefix-matching loc 8914 "Playground One" (a Lower East Side
# playground) at 10/13 = 0.77 coverage, dragging NYC Parks "Kids In Motion"
# programs for St. John's Park, Schmul, Elmhurst, Rosemary's and Phil "Scooter"
# Rizzuto Park onto one unrelated pin. But putting it in GENERIC_LOCATION_WORDS
# outright ALSO makes it a non-significant leftover in the fuzzy tripwire, which
# measurably broke "Matthews Muliner Playground" -> loc 7487 (a correct match).
# Measured A/B over every playground-touching crawl_event: as a bare-token block
# this fixes 47 mis-pins and newly resolves "Playground, Elmhurst Park" -> 283,
# with zero regressions.
BARE_ONLY_GENERIC_WORDS = GENERIC_LOCATION_WORDS | {'playground'}

# Leftover tokens that don't distinguish one venue from another, so a mismatch
# on them shouldn't block the fuzzy token-overlap tripwire: corporate/legal
# suffixes (Inc vs Corp for the same business) and grammatical connectors.
_DROPPABLE_LEFTOVER_TOKENS = {
    'inc', 'corp', 'corporation', 'incorporated', 'llc', 'ltd', 'co', 'lp',
    'plc', 'company', 'the', 'and', 'of', 'at', 'for', 'a', 'an', 'in', 'on',
}


# Words that name a KIND of venue rather than a particular venue. Superset of
# GENERIC_LOCATION_WORDS, used ONLY by the venue-type-swap guard below (which
# the prefix and fuzzy tiers consult) — these extra words must stay out of
# GENERIC_LOCATION_WORDS itself, where they would also suppress prefix matching
# and collapse real venue names ("Picnic House", "Brooklyn Grange Farm") to
# bare generics.
_VENUE_TYPE_WORDS = GENERIC_LOCATION_WORDS | {
    'house', 'church', 'cathedral', 'temple', 'synagogue', 'mosque',
    'school', 'academy', 'college', 'university', 'institute', 'conservatory',
    'arena', 'stadium', 'cinema', 'playhouse', 'tavern', 'pub', 'inn',
    'brewery', 'winery', 'distillery', 'taproom', 'diner', 'bakery',
    'warehouse', 'factory', 'foundry', 'barn', 'farm', 'beach', 'pier',
    'playground', 'boathouse', 'firehouse', 'clubhouse', 'greenhouse',
    'bookstore', 'bookshop', 'arcade', 'casino', 'spa', 'salon', 'showroom',
    'workshop', 'studios', 'galleries', 'gardens', 'lanes', 'grounds',
}


# Different words for the SAME venue type. A swap between two of these is not a
# venue-type mismatch: "Housing Works Chelsea Thrift Store" and "Housing Works
# Chelsea Thrift Shop" are one shop. (Spelling variants like theatre/theater and
# harbour/harbor already reconcile via _leftover_reconciles; these don't.)
_TYPE_SYNONYMS = {
    'store': 'shop', 'shoppe': 'shop', 'bookshop': 'bookstore',
    'cinema': 'theater', 'theatre': 'theater', 'centre': 'center',
    'harbour': 'harbor', 'parlour': 'parlor',
}


def _generic_type_swap(leftover_a, leftover_b):
    """True when two names differ ONLY by a swap of venue-TYPE words.

    "Brooklyn Public Library" vs "Brooklyn Public House": the two names are
    token-identical apart from one venue-type word each, and those words name
    different KINDS of place. Levenshtein happily scores that pair over
    FUZZY_MATCH_THRESHOLD (one word out of three, same length), and the
    significant-leftover tripwire never fires because at least one of the two
    differing tokens is a generic venue word, so `sig_v and sig_k` is False.

    A venue-type mismatch is a stronger signal of "different place" than string
    distance is of "same place", so this is a rejection, not an abstention.

    Deliberately narrow: BOTH sides must have a leftover (a pure subset like
    "Picnic House" ⊂ "Prospect Park Picnic House" is not a swap), and EVERY
    leftover on both sides must be a venue-type word (anything distinctive is
    the existing tripwire's business). Spelling variants of the same type
    ("theater"/"theatre", "harbor"/"harbour", "studio"/"studios") reconcile and
    are not a swap.
    """
    a = {t for t in leftover_a if t not in _DROPPABLE_LEFTOVER_TOKENS}
    b = {t for t in leftover_b if t not in _DROPPABLE_LEFTOVER_TOKENS}
    if not a or not b or a == b:
        return False
    if not (a <= _VENUE_TYPE_WORDS and b <= _VENUE_TYPE_WORDS):
        return False
    a = {_TYPE_SYNONYMS.get(t, t) for t in a}
    b = {_TYPE_SYNONYMS.get(t, t) for t in b}
    if a == b:
        return False
    if (all(_leftover_reconciles(x, b) for x in a)
            and all(_leftover_reconciles(y, a) for y in b)):
        return False
    return True


def _venue_type_swap_names(a, b):
    """_generic_type_swap for two whole normalized names.

    "madison square park" vs "madison square garden" — token-identical apart
    from one venue-type word each. Levenshtein scores that 0.90 exactly.
    """
    if not a or not b:
        return False
    ta, tb = set(a.split()), set(b.split())
    shared = ta & tb
    return _generic_type_swap(ta - shared, tb - shared)


def _fuzzy_ratio(candidate, key):
    """Levenshtein ratio for the fuzzy tier, but 0 for a venue-type swap."""
    if _venue_type_swap_names(candidate, key):
        return 0
    return _calculate_levenshtein_ratio(candidate, key)


def _significant_leftovers(tokens):
    """Keep only tokens that actually identify a venue.

    Drops generic venue-type words ("center", "theater"), corporate/legal
    suffixes and connectors, and very short non-numeric tokens (abbreviations
    like "st" for "saint", articles like "la"/"le"). Numbers are always kept —
    a street/pier number is identifying ("100" vs "55 Washington St").
    """
    sig = set()
    for t in tokens:
        if t in GENERIC_LOCATION_WORDS or t in _DROPPABLE_LEFTOVER_TOKENS:
            continue
        if len(t) >= 3 or t.isdigit():
            sig.add(t)
    return sig


def _shares_distinctive_token(a, b):
    """True if two normalized names share at least one venue-identifying token.

    Generic venue-type words ("rooftop", "plaza", "dance") and connectors are
    discarded first, so this asks whether the two strings actually name the same
    thing rather than merely describing the same kind of thing. Used to decide
    whether a website-scoped alternate name is portable knowledge about a venue
    ("Prospect Park Picnic House" ↔ "Picnic House") or in-site shorthand that
    means nothing elsewhere ("The Rooftop" ↔ "Elsewhere").
    """
    if not a or not b:
        return False
    return bool(_significant_leftovers(set(a.split()))
                & _significant_leftovers(set(b.split())))


# "Play Area (in Spuyten Duyvil Playground), Bronx" — NYC Parks (and its
# conservancy siblings) name a sub-feature first and put the containing park in
# an "(in …)" parenthetical. The parenthetical is the only part that names a
# venue we actually have a row for; see _extract_parenthetical_parent.
_PARENTHETICAL_PARENT_RE = re.compile(r'\(\s*in\s+([^)]{3,})\)', re.IGNORECASE)


def _extract_parenthetical_parent(raw):
    """Return the normalized parent venue from a "<feature> (in <Parent>)" string.

    NYC Parks emits sub-feature locations like "Main Pool (in Crotona Park)",
    "Dance Room (in St. John's Recreation Center)" or "Pier 2 (in Brooklyn
    Bridge Park)". The full string matches nothing (the leading feature name
    drags prefix coverage below PREFIX_MATCH_COVERAGE and Levenshtein below the
    fuzzy threshold), so ~57 Parks sub-features re-orphaned to NULL on every
    crawl. The parenthetical names the park itself, which we do have.

    Returns '' when there is no "(in …)" parenthetical.
    """
    if not raw or '(' not in raw:
        return ''
    match = _PARENTHETICAL_PARENT_RE.search(raw)
    if not match:
        return ''
    return _normalize_location_name(match.group(1))


def _squash_identity(name):
    """Collapse a name to its bare identity: alphanumerics only, plural dropped.

    Two names squash to the same key only when they are the *same* name written
    differently — spacing, punctuation, an @handle, a stray apostrophe, a
    trailing "s". Used by the source-site fallback (Step 6 of get_location_id),
    which has nothing but the organizer's name to go on and therefore cannot
    afford a fuzzy threshold. See the comment there.
    """
    squashed = re.sub(r'[^a-z0-9]', '', (name or '').lower())
    return squashed[:-1] if squashed.endswith('s') else squashed


# Words skipped when building a venue initialism — "Museum of the Moving Image"
# is MMI, not MOTMI.
_INITIALISM_STOPWORDS = {'the', 'of', 'and', 'at', 'in', 'for', 'a', 'an', 'on', '&'}


def _is_initialism_of(key, venue_name):
    """True if `key` is an acronym-shaped self-abbreviation of `venue_name`.

    Venues routinely refer to themselves by their initials on their own site
    ("SRC" on secretrisoclub.com), which the extractor faithfully emits as the
    location name. Substring and Levenshtein tests both miss that relationship —
    "src" is neither contained in nor similar to "secret riso club" — so the
    acronym has to be built explicitly. Deliberately narrow: only bare
    alphanumeric keys of 2-6 characters, and only an exact initials match.
    """
    if not key or not venue_name:
        return False
    if len(key) < 2 or len(key) > 6 or not key.isalnum():
        return False
    words = [w for w in re.findall(r'[a-z0-9]+', venue_name.lower())
             if w not in _INITIALISM_STOPWORDS]
    if len(words) < 2:
        return False
    return key.lower() == ''.join(w[0] for w in words)


def _single_linked_venue(locations_map, website_id):
    """The one venue a website is linked to, or None if it isn't single-venue."""
    if not website_id:
        return None
    linked = locations_map.get('website_linked', {}).get(website_id, [])
    return linked[0] if len(linked) == 1 else None


def _leftover_reconciles(token, others):
    """True if `token` plausibly refers to the same thing as some token in
    `others` — a typo (high Levenshtein ratio) or a hyphen-join / containment
    ("hudson" ⊂ "midhudson"). Used to tell "Saint/St"-style noise apart from a
    genuine venue-identity conflict ("BCC" vs "DEP", "Java" vs "Maple")."""
    for other in others:
        if token in other or other in token:
            return True
        if _calculate_levenshtein_ratio(token, other) >= 0.8:
            return True
    return False


# Sentinel marking a street address shared by 2+ distinct venues in the
# addresses tier. Address matching skips these — it can't disambiguate which
# venue an event at that address belongs to.
_AMBIGUOUS_ADDRESS = object()


# A trailing postal address on a venue name: a separator, a house number and
# street, then whatever city/state cruft, anchored by a 5-digit ZIP.
#
# The ZIP is the whole point — it is what distinguishes a genuine address tail
# from a room, stage, branch or cross-street suffix that must be preserved
# ("Bartow Community Center - Room 31", "Montague Store - 122 Montague St.",
# "NY - 14TH ST. Mainstage", "Entrance - 34th Avenue between 77th and 78th
# Streets in Travers Park"). Without it this would shred those.
_TRAILING_POSTAL_ADDRESS_RE = re.compile(
    r'\s*[,;:–—-]\s*'                     # separator
    r'\d+[A-Za-z]?\s+'                    # house number
    r'[^,]{2,40}?'                        # street
    r'(?:,[^,]{0,40}?){0,3}'              # optional unit / city / state parts
    r',?\s*\b\d{5}(?:-\d{4})?\b'          # the ZIP
    r'[\s,]*(?:USA|United States)?\s*$',
    re.I)


def _strip_trailing_postal_address(name):
    """Return `name` with a trailing full postal address removed, or `name`.

    Only used as a last-resort retry inside `get_location_id` (see Step 8 there
    for the measured reason it must not run as an up-front normalization).
    """
    if not name:
        return name
    stripped = _TRAILING_POSTAL_ADDRESS_RE.sub('', name).strip(' ,;:-–—')
    # Never reduce a name to nothing, to a bare number, or to a stub.
    if not stripped or stripped.isdigit() or len(stripped) < 3:
        return name
    return stripped


def _normalize_location_name(name):
    """Normalizes a location name for matching."""
    return _normalize_location_name_parts(name)[0]


def _normalize_location_name_parts(name):
    """Normalize `name`, and report which area qualifier the collapse consumed.

    Returns `(normalized, area_token)`. `area_token` is the
    `city_config.city_area_tokens()` entry stripped off the END of the name
    ("Downtown Brooklyn" -> ("downtown", "brooklyn")), or None when nothing was
    stripped. That token is the ONLY information the collapse destroys which
    still names a different place, so it is what `_area_qualifier_conflict`
    needs to tell "Downtown Brooklyn" apart from "Downtown NYC" after both have
    become the bare key "downtown". Kept as one function with
    `_normalize_location_name` so the two can never disagree about what was
    stripped.
    """
    if not name:
        return "", None

    # Strip diacritics so "Café" matches "Cafe", "Jardín" matches "Jardin".
    name = ''.join(
        c for c in unicodedata.normalize('NFKD', name)
        if not unicodedata.combining(c)
    )
    # Normalize "&" and "+" to "and" so "Art & Architecture" matches "Art and Architecture".
    name = re.sub(r'\s*[&+]\s*', ' and ', name)

    # A period used as a separator with no space after it ("St.Albans Library",
    # "Mt.Vernon Library") would otherwise be *deleted* by the punctuation strip
    # below and fuse the two words ("stalbans library"), which matches nothing.
    # Restore the space instead. Deliberately requires two letters on BOTH sides
    # so initialisms keep collapsing the way they always have ("P.S. 321",
    # "A.R.T.", "J.F.K." are untouched) and no decimal or version number is
    # split.
    name = re.sub(r'(?<=[A-Za-z][A-Za-z])\.(?=[A-Za-z][A-Za-z])', ' ', name)

    original_lower = name.lower()
    has_dash_before_borough = any(
        f'- {b}' in original_lower or f'_{b}' in original_lower
        for b in city_config.borough_tokens()
    )

    normalized = re.sub(r'[^\w\s]', '', original_lower)

    if normalized in ['virtual', 'online', 'livestream', 'private residence',
                      'various locations', 'zoom', 'unknown venue']:
        return "", None
    if len(normalized) > 15 and normalized.startswith('the '):
        normalized = normalized[4:]

    # Strip trailing state abbreviations/names (e.g., "Brooklyn, NY" -> "brooklyn")
    suffixes = city_config.city_area_tokens()
    area_token = None
    state_suffixes = city_config.state_suffixes()
    for ss in state_suffixes:
        if normalized.endswith(ss) and len(normalized) > len(ss) + 1:
            stripped = normalized[:-len(ss)].strip()
            # See BARE_ONLY_GENERIC_WORDS: don't collapse to a bare generic token.
            if ' ' not in stripped and stripped in BARE_ONLY_GENERIC_WORDS:
                break
            normalized = stripped
            # "New York" is both a state suffix and the city's own name, so this
            # branch — not the area-token loop below — is what consumes it in
            # "Downtown New York". Record it, or that string stays
            # indistinguishable from "Downtown Brooklyn". Suffixes that are only
            # ever states ("ny", "nj") name no area and are not recorded.
            if ss.strip() in suffixes:
                area_token = ss.strip()
            break

    if normalized in suffixes:
        return "", None

    if not has_dash_before_borough:
        for suffix in suffixes:
            if normalized.endswith(f' {suffix}') and len(normalized) > len(suffix) + 2:
                stripped = normalized[:-len(f' {suffix}')].strip()
                # Don't collapse a venue to a bare generic token (e.g.
                # "Gallery Brooklyn" -> "gallery"), which would then exact-match
                # any unrelated event whose location is just that word. Keep the
                # borough so the name stays specific.
                if ' ' not in stripped and stripped in BARE_ONLY_GENERIC_WORDS:
                    break
                normalized = stripped
                area_token = suffix
                break

    return " ".join(normalized.split()), area_token


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
    # Require a leading house number. Without this, a value like "Harbor" (from a
    # venue whose address is literally "Harbor, Frankfort, NY") or a bare park
    # name ("Bryant Park, New York") becomes an address key and collides with
    # unrelated queries. Real street addresses start with a number; venues are
    # matched by name elsewhere.
    if not re.match(r'\d', street_part):
        return None
    return _normalize_street_address(street_part)


# US state abbreviations, used to parse the "City, ST" tail of an address.
_US_STATES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID',
    'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS',
    'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK',
    'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV',
    'WI', 'WY', 'DC',
}


def _parse_city_state(address):
    """Parse the (city, state) tail of a US address string.

    "9003 Bergenline Ave, North Bergen, NJ 07047, USA" -> ("north bergen", "NJ")
    "Central Park, New York, NY, USA"                   -> ("new york", "NY")
    Returns (None, None) when no recognizable "City, ST" tail is present.
    """
    if not address:
        return (None, None)
    parts = [p.strip() for p in address.split(',') if p.strip()]
    if parts and parts[-1].upper() in ('USA', 'US', 'UNITED STATES'):
        parts = parts[:-1]
    if len(parts) < 2:
        return (None, None)
    m = re.match(r'^([A-Za-z]{2})(?:\s+\d{5}(?:-\d{4})?)?$', parts[-1])
    if not m:
        return (None, None)
    state = m.group(1).upper()
    if state not in _US_STATES:
        return (None, None)
    return (parts[-2].lower(), state)


# Sentinel class for the city's own names ("NYC", "New York", "New York City"),
# which denote the whole city rather than one area inside it. Not a possible
# normalized token, so it can never collide with a real one.
_CITY_WIDE_CLASS = '\x00city'


def _area_qualifier_class(token):
    """Collapse equivalent spellings of one area qualifier to a single class.

    "the bronx" and "bronx" are one place; so are the city's own names ("nyc",
    "new york", "new york city"), which sources use interchangeably. Everything
    else — each borough, "long island" — is its own class. Derived from the
    active city config, so no NYC strings live in engine code.
    """
    if not token:
        return None
    token = re.sub(r'^the\s+', '', token.strip().lower())
    if token in _city_self_tokens():
        return _CITY_WIDE_CLASS
    return token


@functools.lru_cache(maxsize=1)
def _city_self_tokens():
    """Normalized spellings that name the CITY itself rather than a sub-area."""
    names = {city_config.city_name(), city_config.city_short(),
             city_config.metro_name(), city_config.region_tag_token()}
    out = set()
    for n in names:
        n = re.sub(r'[^\w\s]', '', (n or '').lower()).strip()
        if n:
            out.add(n)
            out.add(re.sub(r'\s+city$', '', n).strip())
    return {t for t in out if t}


def _area_qualifier_conflict(raw_text, candidate_info, area_classes=None):
    """True if the source and the candidate name DIFFERENT area qualifiers.

    `_normalize_location_name` strips a trailing borough/city qualifier, which
    is what lets a source that only said "Midtown" reach "Midtown Manhattan".
    But the collapse is lossy on BOTH sides, so it also fuses qualifiers that
    name different places: "Downtown NYC", "Downtown Manhattan" and "Downtown
    Brooklyn" all become the bare key "downtown", and every one of them landed
    on the Downtown Brooklyn geotag.

    The prefix/fuzzy tier cannot use the brand-family guard to tell these apart
    (see the note there — it un-pinned 2,971 correctly-matched rows, because by
    the time that tier runs, a spelled-out branch is indistinguishable from a
    bare brand). This restores exactly the bit that was destroyed instead: it
    fires ONLY when both sides actually carried a qualifier and the two name
    different areas. A source that named no area ("Midtown") still resolves, and
    a source that agrees ("Green Room NYC" -> "Green Room NYC") is untouched.

    `area_classes` maps location_id -> every area a location is CURATED to
    answer to, gathered in build_locations_map from its name, its global
    alternate names and its short_name. A curated alias is an explicit
    statement that a spelling refers to this venue, so "Lower Manhattan"
    aliased as "Downtown NYC" accepts a source that says "Downtown NYC" —
    while Downtown Brooklyn, which claims no such alias, still rejects it.
    """
    cand_classes = (area_classes or {}).get((candidate_info or {}).get('id'))
    if cand_classes is None:
        cand_class = _area_qualifier_class(
            _normalize_location_name_parts((candidate_info or {}).get('name') or '')[1])
        cand_classes = {cand_class} if cand_class else set()
    if not cand_classes or cand_classes == {_CITY_WIDE_CLASS}:
        # A row we only ever called "<Name> New York" claims the whole city, so
        # a source naming a borough INSIDE it adds specificity rather than
        # contradicting: "The Meadows Brooklyn" is "The Meadows New York"
        # (loc 869, 17 Meadow St, Brooklyn). The reverse is not symmetric and is
        # handled below — a source saying "Downtown NYC" is VAGUER than a row
        # specifically named "Downtown Brooklyn", and must not claim it.
        return False
    for part in re.split(r'[,/]', raw_text or ''):
        # A segment carrying a house number is an ADDRESS, not a venue name, so
        # its trailing city is a postal tail rather than a qualifier — the
        # comma split alone does not catch "…(between 31st & 32nd Streets) New
        # York" (loc 3497, whose street address matches exactly).
        if any(ch.isdigit() for ch in part):
            continue
        src_class = _area_qualifier_class(
            _normalize_location_name_parts(part)[1])
        if src_class is not None and src_class not in cand_classes:
            return True
    return False


def _region_conflict(raw_text, candidate_info, city_states):
    """True if `raw_text`'s address tail names a city in a conflicting state.

    Guards the heuristic match tiers (alternate-name/short-name/prefix/fuzzy)
    against bare-name collisions across municipalities — e.g. a "Columbus Park,
    199 W Franklin St, Hackensack, NJ" event fuzzy-matching "Columbus Park" in
    Manhattan. The city->state knowledge is learned from the DB's own location
    addresses (see build_locations_map), so the engine stays city-agnostic.

    Conservative by construction to avoid false positives: it only inspects the
    comma/slash-delimited segments AFTER the first comma (the address tail, not
    the venue name), and a segment must EQUAL a known city — modulo a trailing
    state/zip — to count. This ignores city words embedded in a venue name
    ("Elizabeth Catlett Art Space", "Fairfield Inn") or in a street ("50 Madison
    Ave"), and only fires when the named city maps to a single state in the data
    that differs from the candidate's.
    """
    if not raw_text or ',' not in raw_text or not city_states:
        return False
    _, cand_state = _parse_city_state((candidate_info or {}).get('address') or '')
    if not cand_state:
        return False
    tail = raw_text.split(',', 1)[1]
    for seg in re.split(r'[,/]', tail):
        toks = seg.split()
        if len(toks) >= 2 and toks[-1].upper() in _US_STATES:
            toks = toks[:-1]
        if toks and re.fullmatch(r'\d{5}(?:-\d{4})?', toks[-1]):
            toks = toks[:-1]
        states = city_states.get(_normalize_location_name(' '.join(toks)))
        if states and len(states) == 1 and cand_state not in states:
            return True
    return False


_ADDR_STREET_TYPES = sorted(
    # "concourse" is here for the Bronx's Grand Concourse, which greenmarket
    # and park addresses name as a cross street ("192nd St & Grand Concourse",
    # loc 669). Without it the side doesn't read as a street at all and the
    # whole intersection is discarded.
    {'st', 'ave', 'blvd', 'dr', 'rd', 'pl', 'ct', 'ln', 'pkwy', 'hwy',
     'broadway', 'bowery', 'way', 'sq', 'terrace', 'tpke', 'concourse'},
    key=len, reverse=True,
)
# Street names that can stand alone with no preceding name word (e.g. "350 Bowery").
_ADDR_STANDALONE_TYPES = {'broadway', 'bowery'}
_ADDR_LONG_TO_SHORT = {
    'avenue': 'ave', 'street': 'st', 'boulevard': 'blvd', 'drive': 'dr',
    'road': 'rd', 'place': 'pl', 'court': 'ct', 'lane': 'ln',
    'parkway': 'pkwy', 'highway': 'hwy', 'east': 'e', 'west': 'w',
    'north': 'n', 'south': 's', 'turnpike': 'tpke', 'square': 'sq',
    # "Saint Marks Ave" → "St Marks Ave" (matches DB form "St Marks Ave")
    'saint': 'st',
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
# Abbreviated and spelled-out street types together — "does this text mention a
# street at all?" See `sublocation_looks_like_address`.
_ADDR_TYPE_WORDS = sorted(
    set(_ADDR_STREET_TYPES) | {
        'street', 'avenue', 'boulevard', 'drive', 'road', 'place', 'court',
        'lane', 'parkway', 'highway', 'square', 'turnpike'},
    key=len, reverse=True,
)


# Cross-street suffix on a house address: galleries and theaters write their
# address as "980 Madison at 76th Street" (loc 333 Gagosian). The cross street's
# own type token closes the address regex, so the key comes out as
# "980 madison at 76 st" and never equals the DB form "980 madison ave" — the
# sublocation then exports redundantly next to the venue address.
#
# Stripping " at ..." is only safe when the *house address comes first*: plenty
# of real sublocations put the address AFTER the preposition ("Studio B at 150 W
# 42nd St") or use " at " to name a sub-venue ("The Loft at Prince Street",
# "Audubon Center at the Boathouse"), and those must be left alone. So the strip
# requires the text to START with a house number.
_LEADS_WITH_HOUSE_NUMBER_RE = re.compile(r'^\d+(?:-\d+)?[a-z]?\s+\S')
_CROSS_STREET_SUFFIX_RE = re.compile(r'\s+at\s+.*$')


def _strip_cross_street_suffix(s):
    """Drop a trailing " at <cross street>" clause from a house address."""
    if s and _LEADS_WITH_HOUSE_NUMBER_RE.match(s):
        return _CROSS_STREET_SUFFIX_RE.sub('', s).strip()
    return s


# "980 madison" — a house number plus a street name with no street-type token at
# all, which is what remains once the cross-street clause is stripped. Anchored
# to the whole string so only a bare address qualifies.
_TYPELESS_HOUSE_ADDR_RE = re.compile(r"^(\d+)\s+([a-z][a-z0-9.'\- ]{2,})$")
_TRAILING_STREET_TYPE_RE = re.compile(
    r'\s+(?:' + '|'.join(_ADDR_STREET_TYPES) + r')$')


def _extract_typeless_house_address(s):
    """Return "<num> <street name>" for a house address written with no street type.

    "980 Madison at 76th Street" → "980 madison". Returns None for anything that
    still carries a street type (the normal `_extract_street_address_loose` path
    handles those) or that is not purely a house number plus a name.
    """
    if not s:
        return None
    s = s.lower().strip()
    for long, short in _ADDR_LONG_TO_SHORT.items():
        s = re.sub(r'\b' + long + r'\b', short, s)
    s = _strip_cross_street_suffix(s)
    m = _TYPELESS_HOUSE_ADDR_RE.match(s)
    if not m:
        return None
    name = re.sub(r'\s+', ' ', re.sub(r"[.']+", '', m.group(2))).strip()
    if not name or _TRAILING_STREET_TYPE_RE.search(' ' + name):
        return None
    return f"{m.group(1)} {name}"


def _flatten_house_number(num):
    """Flatten a house number to its comparison key, zero-padding Queens/Bronx
    hyphenates so the same address written two ways lands on one key.

    Queens and Bronx addresses are `<block>-<lot>` with the lot conventionally
    written as two digits ("180-04 State Rd", "45-50 Van Dam St"). Sources drop
    the pad freely, and a bare `.replace('-', '')` then turns "180-04" into
    `18004` but "180-4" into `1804` — two different keys for one building, so
    the sublocation-vs-address redundancy check reports a false mismatch. Seen
    2026-08-23 on loc 10077 (Roxbury 9/11 Memorial), where DB "180-04 State Rd"
    and source "180-4 State Road" are the same address.

    Padding to the convention's own width is what makes both spellings agree;
    the *value* of the key does not matter, only that the two forms share it.
    Segments already two or more digits are untouched, so the range-looking
    forms that are really block-lot pairs ("5-11 47th Ave") keep the key they
    have today and no existing match changes.
    """
    if '-' not in num:
        return num
    block, _, lot = num.partition('-')
    return block + lot.zfill(2)


def _extract_street_address_loose(s):
    """Extract first <number> <words> <street-type> match from anywhere in `s`.

    More permissive than `_extract_street_address`: handles a leading venue
    name ("Gotham Park, 1 Rose St" → "1 rose st"), trailing apt/suite suffixes,
    word ordinals ("Tenth" → "10th"), hyphenated Queens numbers ("5-52" → "552"),
    apartment-letter on house number ("161A Chrystie" → "161 chrystie st"),
    Avenue A/B/C/D, redundant "Bowery St" / "Broadway St", and a trailing
    " at <cross street>" clause ("980 Madison at 76th Street" → "980 madison").
    """
    if not s:
        return None
    s = s.lower().strip()
    s = _strip_cross_street_suffix(s)
    for long, short in _ADDR_LONG_TO_SHORT.items():
        s = re.sub(r'\b' + long + r'\b', short, s)
    for word, num in _ADDR_WORD_NUMS.items():
        s = re.sub(r'\b' + word + r'\b', num, s)
    s = re.sub(r'\b([nsew])(\d)', r'\1 \2', s)
    # Leading room/suite code before the real street address ("122 CC 150 First
    # Avenue" — room 122CC at 150 1st Ave). Without this the regex latches onto
    # the room number as the house number and the address never matches the DB
    # form. Tightly gated: a number plus a 2-4 letter code immediately followed
    # by another number, and the code must not be a compass directional (so
    # "150 W 42nd St" is never mistaken for a room code) or a street type.
    s = re.sub(
        r'^\s*\d+\s*(?!(?:n|s|e|w|ne|nw|se|sw|no|so|' + '|'.join(_ADDR_STREET_TYPES)
        + r')\b)[a-z]{2,4}\s+(?=\d)', '', s)
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
    num = _flatten_house_number(num)
    # "4140 Broadway & 176th St" — a trailing "& <cross street>" after a
    # standalone street name gets absorbed into the name group ("broadway &
    # 176") with the cross street's type closing the match. The address is
    # just "<num> <standalone>". (After a *typed* street the regex already
    # stops at the first type token, so only standalone names need this.)
    if name and '&' in name:
        head = name.split('&')[0].strip().rstrip('.').lower()
        if head in _ADDR_STANDALONE_TYPES:
            return f"{num} {head}"
    # "50 Bowery St" / "350 Broadway St" — the standalone street is the real
    # street name and the trailing "st" is redundant. Drop it.
    if name and name.lower() in _ADDR_STANDALONE_TYPES:
        return f"{num} {name.lower()}"
    if name:
        name = re.sub(r'[.\']+', '', name)
        name = re.sub(r'\s+', ' ', name.strip())
        # Drop ordinal suffixes from numbered street names so "14 st" and
        # "14th st" normalize to the same form ("14 st" vs "39 w 14th st").
        name = re.sub(r'\b(\d+)(st|nd|rd|th)\b', r'\1', name)
        return f"{num} {name} {st}"
    # Standalone street (Broadway, Bowery) — guard against bare "<n> st" matches
    if st not in _ADDR_STANDALONE_TYPES:
        return None
    return f"{num} {st}"


_INTERSECTION_SPLIT = re.compile(r'\s+(?:&|and|at)\s+|\s*&\s*')


def _normalize_street_side(side):
    """Normalize one side of a cross-street pair, or None if it isn't a street.

    Applies the same long→short / ordinal-word normalization the house-address
    parser uses, then requires the result to actually name a street: it must
    carry a street-type token ("ave", "st", "blvd") or be a standalone street
    name ("Broadway", "Bowery"). That requirement is what keeps "Arts & Crafts
    Room" from being read as an intersection.
    """
    if not side:
        return None
    s = side.lower().strip().strip('.,')
    for long, short in _ADDR_LONG_TO_SHORT.items():
        s = re.sub(r'\b' + long + r'\b', short, s)
    for word, num in _ADDR_WORD_NUMS.items():
        s = re.sub(r'\b' + word + r'\b', num, s)
    s = re.sub(r'\b(\d+)(st|nd|rd|th)\b', r'\1', s)
    s = re.sub(r"[.']+", '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    if not s:
        return None
    tokens = s.split()
    if not (set(tokens) & (set(_ADDR_STREET_TYPES) | _ADDR_STANDALONE_TYPES)):
        return None
    # Drop a leading compass directional: "W 176 st" and "176 st" are the same
    # cross street, and one side of the pair routinely omits it.
    if tokens[0] in ('n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw') and len(tokens) > 1:
        tokens = tokens[1:]
    return ' '.join(tokens)


def _extract_intersection(s):
    """Extract a cross-street pair from `s` as an order-insensitive key.

    Greenmarkets, park entrances and street fairs are addressed by intersection
    ("14th St Loop & Avenue A") rather than house number, so the house-address
    parser returns None for them and any comparison built on it silently fails.
    Returns a frozenset of the two normalized sides, or None.

    Only the comma-delimited segments are considered, and a segment must split
    into exactly two street-looking sides — an address like Bay Ridge's
    "3rd Avenue & 95th Street, Walgreen's Parking, lot 9408 3rd Ave, ..." still
    yields the intersection from its first segment.
    """
    if not s:
        return None
    # Google's canonical intersection format puts a comma AFTER the joiner
    # ("7th Ave &, 44th St, Brooklyn, NY"). Splitting on commas first would
    # leave the segment "7th Ave &", which yields only one side and is skipped —
    # so the whole intersection is lost. Pull the joiner back together first.
    s = re.sub(r'\s*(&|\band\b|\bat\b)\s*,\s*', r' \1 ', s)
    for segment in s.split(','):
        parts = [p for p in _INTERSECTION_SPLIT.split(segment) if p.strip()]
        if len(parts) != 2:
            continue
        a = _normalize_street_side(parts[0])
        b = _normalize_street_side(parts[1])
        if a and b and a != b:
            return frozenset((a, b))
    return None


def _extract_intersection_pairs(s):
    """Every cross-street pair named in `s`, as a set of frozensets.

    Looser than `_extract_intersection`, which only reads a segment that splits
    into exactly two sides. A greenmarket sitting mid-block is addressed with
    three streets ("34th Ave & 79th Street &, 80th St" — loc 428 Jackson
    Heights) and that segment yields nothing under the strict rule. Here every
    unordered pair is returned instead.

    Only the block/range comparisons use this: both are anchored by a street
    the sublocation named explicitly, so the extra pairs can never fire alone.
    """
    if not s:
        return frozenset()
    # Same joiner-comma repair as `_extract_intersection` ("7th Ave &, 44th St").
    s = re.sub(r'\s*(&|\band\b|\bat\b)\s*,\s*', r' \1 ', s)
    pairs = set()
    for segment in s.split(','):
        sides = []
        for part in _INTERSECTION_SPLIT.split(segment):
            if not part.strip():
                continue
            side = _normalize_street_side(part)
            if side:
                sides.append(side)
        for i in range(len(sides)):
            for j in range(i + 1, len(sides)):
                if sides[i] != sides[j]:
                    pairs.add(frozenset((sides[i], sides[j])))
    return pairs


# A house number leads the text: "112 W 34th St", "34-12 36th Ave" (Queens),
# "626B 10th Ave". Matched on lowercased text. This is the gate that keeps the
# bare-street-name rule below from ever swallowing a real building number —
# "19th St." does NOT match (the ordinal suffix is glued to the digits), while
# every one of those three does.
_HOUSE_NUMBER_LEAD_RE = re.compile(r'^\s*\d+(?:-\d+)?[a-z]?\s')
# The whole (normalized) text is a street and nothing else: an optional one- or
# two-word name, or a number, followed by the street type. "40th Street Plaza"
# and "14th Street corridor" deliberately fail — those name a spot inside a
# venue and stay on the map.
_BARE_STREET_RE = re.compile(
    r"^(\d+|[a-z][a-z'\-]*(?:\s+[a-z][a-z'\-]*)?)\s+("
    + '|'.join(_ADDR_STREET_TYPES) + r')$')
_NUMBERED_STREET_RE = re.compile(
    r'^(\d+)\s+(' + '|'.join(_ADDR_STREET_TYPES) + r')$')


# A comma-separated tail that is only a place qualifier: a state, a ZIP, a
# country, or a metro place name. Anything else after the comma is content
# ("Adams Street, Multipurpose Room" names a room; "Centre Street, Domino Park,
# Rockefeller Center, ..." lists other venues) and must keep the text from
# reading as a bare street name.
_PLACE_QUALIFIER_RE = re.compile(
    r'^(?:usa?|u\.s\.a?\.?|ny|n\.y\.|nj|ct)$'
    r'|^(?:ny|nj|ct)\s+\d{5}(?:-\d{4})?$'
    r'|^\d{5}(?:-\d{4})?$')
_place_qualifiers = None


def _is_place_qualifier(segment):
    """True when a trailing comma segment only says *where*, not *what*."""
    global _place_qualifiers
    seg = segment.strip().lower().rstrip('.')
    if not seg:
        return True
    if _PLACE_QUALIFIER_RE.match(seg):
        return True
    if _place_qualifiers is None:
        _place_qualifiers = (
            {g.lower() for g in city_config.geotags()}
            | set(city_config.city_area_tokens())
            | {s.strip() for s in city_config.state_suffixes()})
    return seg in _place_qualifiers


def _bare_street_name(s):
    """Normalized street name when `s` names a street and carries no address.

    "19th St." → "19 st", "27th Street" → "27 st", "34th Avenue, Jackson
    Heights" → "34 ave", "W 27th St" → "27 st".

    Returns None as soon as a house number leads the text — "112 W 34th St",
    "34-12 36th Ave" and "626B 10th Ave" are addresses, not bare street names —
    and also for anything carrying more than the street ("40th Street Plaza",
    "65th Street Entrance"), which is sub-venue detail worth keeping. Only a
    place-qualifier tail (", Jackson Heights", ", Brooklyn, NY 11249, USA") is
    allowed past the comma.
    """
    if not s:
        return None
    segments = s.lower().split(',')
    seg = segments[0].strip()
    if not seg or _HOUSE_NUMBER_LEAD_RE.match(seg):
        return None
    if not all(_is_place_qualifier(t) for t in segments[1:]):
        return None
    name = _normalize_street_side(seg)
    if not name:
        return None
    if name in _ADDR_STANDALONE_TYPES:
        return name
    return name if _BARE_STREET_RE.match(name) else None


def _address_street_names(address):
    """Every street named by `address`, normalized the cross-street way.

    "537 W 27th St, New York, NY" → {"w 27 st", "27 st"}; "5th Ave & 17th St,
    Brooklyn" → {"5 ave", "17 st"}; "34th Ave, Queens, NY 11372" → {"34 ave"}.
    Built from the three parsers that already exist so a street is recognized
    the same way whether it appears with a house number, in an intersection, or
    on its own.
    """
    names = set()
    if not address:
        return names
    key = _extract_street_address_loose(address)
    if key:
        m = re.match(r'^\d+\s+(.+)$', key)
        if m:
            street = m.group(1)
            names.add(street)
            # One side of a comparison routinely omits the compass directional.
            names.add(re.sub(r'^(?:n|s|e|w|ne|nw|se|sw)\s+', '', street))
    for pair in _extract_intersection_pairs(address):
        names.update(pair)
    for segment in address.split(','):
        bare = _bare_street_name(segment)
        if bare:
            names.add(bare)
    return names


# "<main street> between <A> & <B>" — how GrowNYC writes every greenmarket
# ("2nd Avenue between 90th & 91st Streets") and how community boards write an
# Open Street block. "btw"/"bet" are the abbreviations that turn up in the wild.
_BETWEEN_SPLIT = re.compile(r'\s+(?:between|btwn?\.?|bet\.)\s+')
_CROSS_PAIR_SPLIT = re.compile(r'\s*(?:&|\band\b|\bto\b|/)\s*')
# A plural street type at the end of the second side applies to BOTH sides:
# "49th & 50th Streets" means 49th Street and 50th Street. Without
# redistributing it the first side carries no street type and is rejected.
_SHARED_PLURAL_TYPES = {
    'streets': 'st', 'sts': 'st', 'avenues': 'ave', 'aves': 'ave',
    'boulevards': 'blvd', 'blvds': 'blvd', 'roads': 'rd', 'places': 'pl',
    'drives': 'dr', 'lanes': 'ln', 'courts': 'ct',
}
_SHARED_PLURAL_RE = re.compile(
    r'\b(' + '|'.join(_SHARED_PLURAL_TYPES) + r')\b\.?\s*$', re.IGNORECASE)
# "69th Street to 89th Street" — a block range along one corridor. A bare "-"
# is deliberately excluded: that is Queens house-number punctuation.
_STREET_RANGE_SPLIT = re.compile(r'\s*(?:\bto\b|\bthrough\b|\bthru\b|–|—)\s*')


def _split_cross_street_pair(text):
    """Split "90th & 91st Streets" into ["90 st", "91 st"], or None."""
    parts = [p.strip() for p in _CROSS_PAIR_SPLIT.split(text) if p.strip()]
    if len(parts) != 2:
        return None
    shared = None
    m = _SHARED_PLURAL_RE.search(parts[1])
    if m:
        shared = _SHARED_PLURAL_TYPES[m.group(1).lower()]
        parts[1] = (parts[1][:m.start()].strip() + ' ' + shared).strip()
    sides = []
    for part in parts:
        side = _normalize_street_side(part)
        if not side and shared:
            side = _normalize_street_side(part + ' ' + shared)
        if not side:
            return None
        sides.append(side)
    return sides if sides[0] != sides[1] else None


def _cross_pair_tail(tail):
    """The comma segments of `tail` that still name cross streets.

    Google's formatting can push the second cross street past a comma ("1st Ave
    &, York Ave, New York, NY 10128, USA"), so keep taking segments until one
    says only *where* ("New York", "NY 10128", "USA") — anything past that is
    the address tail, not part of the block.
    """
    kept = []
    for seg in tail.split(','):
        seg = seg.strip()
        if not seg or _is_place_qualifier(seg):
            break
        kept.append(seg)
    return ' '.join(kept)


def _extract_street_block(s, allow_numbered_main=False):
    """Parse "<main street> between <A> & <B>" into (main, [a, b]), or None.

    The main street must be bare — a house number in front means the text is
    already a full address and the normal address path handles it. A DB address
    written in this same block form drops the ordinal ("82 St between 1st Ave &,
    York Ave"), which the bare-name parser reads as house number 82; pass
    `allow_numbered_main=True` when parsing such an address for comparison.
    """
    if not s:
        return None
    text = re.sub(r'\s+', ' ', s.lower().replace('(', ' ').replace(')', ' ')).strip()
    parts = _BETWEEN_SPLIT.split(text, maxsplit=1)
    if len(parts) != 2:
        return None
    main = _bare_street_name(parts[0])
    if not main and allow_numbered_main:
        main = _normalize_street_side(parts[0])
    if not main:
        return None
    sides = _split_cross_street_pair(_cross_pair_tail(parts[1]))
    if not sides:
        return None
    return main, sides


def _street_range_sides(s):
    """Parse "69th Street to 89th Street" into ("st", 69, 89), or None."""
    if not s:
        return None
    parts = [p.strip() for p in _STREET_RANGE_SPLIT.split(s.lower().strip())
             if p.strip()]
    if len(parts) != 2:
        return None
    ends = []
    for part in parts:
        side = _normalize_street_side(part)
        m = _NUMBERED_STREET_RE.match(side) if side else None
        if not m:
            return None
        ends.append((m.group(2), int(m.group(1))))
    (type_a, lo), (type_b, hi) = ends
    if type_a != type_b or lo >= hi:
        return None
    return type_a, lo, hi


def _street_range_covers(sublocation, location_address):
    """True for "69th Street to 89th Street" against an address inside it.

    Corridor locations (Jackson Heights' 37th Ave and Northern Blvd, loc 8345 /
    8547) are named for the block range they run along and addressed at an
    intersection in the middle of it, so a sublocation restating the range adds
    nothing the location already says. Deliberately narrow: the sublocation
    must be *only* the range, both ends must be numbered streets of the same
    type, and the address must name an intersection whose same-type numbered
    street falls inside the range.
    """
    rng = _street_range_sides(sublocation)
    if not rng:
        return False
    st_type, lo, hi = rng
    for pair in _extract_intersection_pairs(location_address):
        for side in pair:
            m = _NUMBERED_STREET_RE.match(side)
            if m and m.group(2) == st_type and lo <= int(m.group(1)) <= hi:
                return True
    return False


def sublocation_looks_like_address(sublocation):
    """True when a sublocation is street-address-shaped enough to compare.

    The /fix-address-mismatches scan asks "does this sublocation claim an
    address that disagrees with the venue's?", so it must first decide whether
    the text claims an address at all. Starting with a digit and containing a
    street-type word is not enough: "65th Street Entrance", "14TH ST.
    Mainstage" and "24th floor terrace" all pass that test while naming a door
    or a room, and they then sit in the candidate list forever because no
    address fix can ever resolve them.

    The gate is structural rather than a list of banned nouns: text leading
    with a house number is always an address, and text without one only counts
    if it parses as a street form we recognize (a bare street name, an
    intersection, a between-block, or a block range). A label like "24th floor
    terrace" parses as none of them.

    This does NOT feed the exporter — labels are useful detail and keep
    publishing; it only keeps them out of the wrong-address scan.
    """
    if not sublocation:
        return False
    text = sublocation.lower().strip()
    if not re.match(r'^\d', text):
        return False
    if not re.search(r'\b(' + '|'.join(_ADDR_TYPE_WORDS) + r')\b\.?', text):
        return False
    if _HOUSE_NUMBER_LEAD_RE.match(text):
        return True
    return bool(_bare_street_name(sublocation)
                or _extract_intersection(sublocation)
                or _extract_street_block(sublocation)
                or _street_range_sides(sublocation))


def _num_in_building_range(num, lo, hi):
    """True if house number `num` falls inside the building range `lo`-`hi`.

    A single building spanning several lot numbers is written as a range
    ("53-83 Water St" = Empire Stores), and a listing may cite any number in
    that range ("55 Water Street"). Endpoint equality alone misses those, so
    the interior is accepted too — but only for forms that are unmistakably a
    range, because Queens-style hyphenated addresses ("5-52 47th Ave") use the
    same punctuation for something else entirely. Three gates keep them apart:

    - `lo < hi` (a Queens address is frequently the reverse or wildly apart),
    - equal digit length (Queens glues a short block number to a house number,
      so "5-52" is excluded while "53-83" passes),
    - matching parity across lo, hi and num — a real range runs down one side
      of the street, so every number in it is odd or every one is even.
    """
    if not (num and lo and hi):
        return False
    if num in (lo, hi):
        return True
    if len(lo) != len(hi):
        return False
    lo_i, hi_i, num_i = int(lo), int(hi), int(num)
    if lo_i >= hi_i:
        return False
    if not (lo_i % 2 == hi_i % 2 == num_i % 2):
        return False
    return lo_i < num_i < hi_i


def sublocation_redundant_with_address(sublocation, location_address):
    """True when sublocation is just the venue address (safe to clear).

    Handles house addresses ("150 1st Ave"), intersection addresses ("14th St
    Loop & Avenue A" — how greenmarkets and park entrances are addressed,
    compared order-insensitively), bare street names ("27th Street" against
    "537 W 27th St"), the between-block form ("2nd Avenue between 90th & 91st
    Streets" against "90th Street & 2nd Ave") and the corridor block range
    ("69th Street to 89th Street" against "37th Ave & 79th St").

    Some scrapers (e.g. Posh.vip) put the venue's full street address into
    sublocation. After location matching, that's redundant with the matched
    location's own address — clear it. Real sub-venue values like "Studio B"
    or "5th Floor" don't parse as a street address and are preserved.

    Also handles the case where one form glues a suite/unit number to the
    house number via a hyphen ("68-117 Jay St") and the other expresses it
    as a #-suffix or comma-separated suite ("68 Jay St #117"). When the
    hyphenated form's leading segment matches the other form's bare house
    number on the same street, treat them as equivalent.
    """
    if not sublocation or not location_address:
        return False
    # Intersection form ("14th St Loop & Avenue A") — neither side parses as a
    # house address, so compare cross-street pairs first. Order-insensitive:
    # "Avenue A & 14th St Loop" is the same corner.
    sub_x = _extract_intersection(sublocation)
    if sub_x and sub_x == _extract_intersection(location_address):
        return True
    # Bare street name ("27th Street", "19th St.") against an address that is
    # already on that street ("537 W 27th St", "2 19th St"). The sublocation
    # names no house number, so it says strictly less than the address does.
    # `_bare_street_name` refuses anything leading with a house number, which
    # is what keeps "112 W 34th St" / "34-12 36th Ave" / "626B 10th Ave" out.
    bare = _bare_street_name(sublocation)
    if bare and bare in _address_street_names(location_address):
        return True
    # "<main> between <A> & <B>" (GrowNYC's greenmarket block form) against the
    # corner the address names ("2nd Avenue between 90th & 91st Streets" vs
    # "90th Street & 2nd Ave"). Anchored on the main street, so a block on some
    # other street can't match.
    block = _extract_street_block(sublocation)
    if block:
        main, sides = block
        addr_pairs = _extract_intersection_pairs(location_address)
        if any(frozenset((main, side)) in addr_pairs for side in sides):
            return True
        # The DB address can be written in that same block form ("82nd Street
        # between 1st & York Avenues" vs "82 St between 1st Ave &, York Ave,
        # New York, NY 10128, USA") — same main street, same two cross streets.
        addr_block = _extract_street_block(location_address,
                                           allow_numbered_main=True)
        if (addr_block and addr_block[0] == main
                and set(addr_block[1]) == set(sides)):
            return True
    # Corridor block range ("69th Street to 89th Street") around the address.
    if _street_range_covers(sublocation, location_address):
        return True
    sub = _extract_street_address_loose(sublocation)
    addr = _extract_street_address_loose(location_address)
    # Type-less house address ("980 Madison at 76th Street" → "980 madison")
    # against the DB's typed form ("980 Madison Ave" → "980 madison ave"): same
    # number, same street name, the sublocation just omits the street type.
    # Both the number AND the full street name must match exactly, so this can
    # only fire on what is literally the venue's own address.
    if not sub and addr:
        typeless_sub = _extract_typeless_house_address(sublocation)
        if typeless_sub:
            typeless_addr = _TRAILING_STREET_TYPE_RE.sub('', addr)
            if typeless_addr != addr and typeless_sub == typeless_addr:
                return True
    if not sub or not addr:
        return False
    if sub == addr:
        return True
    # Hyphenated suite form ("68117 jay st") vs bare house number ("68 jay st")
    # on the same street. Check both directions.
    def _split(key):
        # key is "<digits> <rest>" — return (digits, rest) or (None, None)
        m = re.match(r'^(\d+)\s+(.+)$', key)
        return (m.group(1), m.group(2)) if m else (None, None)
    s_num, s_rest = _split(sub)
    a_num, a_rest = _split(addr)
    if s_num and a_num and s_rest == a_rest:
        # One side might be the hyphen-glued form. The original raw addresses
        # need to have a "#<suite>" or ", suite/unit/apt <suite>" marker that
        # numerically matches the suffix the other side glued on.
        def _suite(raw):
            m = re.search(r'#\s*(\w+)', raw)
            if m:
                return m.group(1).lower()
            m = re.search(r'\b(?:suite|unit|apt|apartment|ste)\s*#?\s*(\w+)',
                          raw, re.IGNORECASE)
            if m:
                return m.group(1).lower()
            return None
        sub_suite = _suite(sublocation)
        addr_suite = _suite(location_address)
        # Case A: sub has the hyphen-glued form (s_num starts with a_num),
        # and the DB raw has a #-suite matching the trailing digits.
        if s_num.startswith(a_num) and len(s_num) > len(a_num):
            tail = s_num[len(a_num):]
            if addr_suite and addr_suite.lstrip('0') == tail.lstrip('0'):
                return True
        # Case B: DB has the hyphen-glued form and sub raw has a #-suite.
        if a_num.startswith(s_num) and len(a_num) > len(s_num):
            tail = a_num[len(s_num):]
            if sub_suite and sub_suite.lstrip('0') == tail.lstrip('0'):
                return True
        # Case C: building-range form ("12-16 Vestry St" — one building spanning
        # numbers 12 through 16) vs a single number in the range. Distinguish
        # from the suite case (which carries a #/suite marker on the non-glued
        # side); here both sides should be bare addresses, and the range form's
        # original raw text must contain "<a>-<b>" with the other side's number
        # equal to <a> or <b>.
        def _range_endpoints(raw):
            # Find first "<digits>-<digits>" at the start of a token
            m = re.search(r'\b(\d+)-(\d+)\b', raw)
            return (m.group(1), m.group(2)) if m else (None, None)
        if not sub_suite and not addr_suite:
            a_lo, a_hi = _range_endpoints(location_address)
            if a_lo and a_hi and _num_in_building_range(s_num, a_lo, a_hi):
                return True
            s_lo, s_hi = _range_endpoints(sublocation)
            if s_lo and s_hi and _num_in_building_range(a_num, s_lo, s_hi):
                return True
    return False


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
        # city (lowercase) -> set of states seen at that city in our data.
        # Learned from location addresses; powers the region-conflict guard.
        'city_states': {},
        # Keys that were DERIVED rather than curated: every `short_names` entry,
        # plus any name/alternate_name key that only exists because
        # _normalize_location_name collapsed the raw string (dropping a borough
        # or city qualifier). See the brand-family guard in get_location_id.
        'weak_keys': set(),
        # normalized bare key -> set of location ids whose own normalized name
        # EXTENDS it ("smorgasburg" -> {2977, 3016, 3017}). A key with 2+ such
        # members names a FAMILY of venues, not one venue.
        'brand_family': {},
        # location id -> every area qualifier the row is CURATED to answer to,
        # from its name, its global alternate names and its short_name. Powers
        # _area_qualifier_conflict; see the note there.
        'area_classes': {},
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

    weak_keys = locations_map['weak_keys']
    strong_keys = set()

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
        main_name = loc.get('name', '')
        normalized_main, main_area = _normalize_location_name_parts(main_name)
        area_classes = locations_map['area_classes'].setdefault(loc.get('id'), set())
        if _area_qualifier_class(main_area):
            area_classes.add(_area_qualifier_class(main_area))

        # For names tier, track multiple locations with same name
        add_with_duplicates(locations_map['names'], main_name.lower(), full_info)
        strong_keys.add(main_name.lower())
        if normalized_main != main_name.lower():
            add_with_duplicates(locations_map['names'], normalized_main, full_info)
            if _collapse_is_significant(main_name, normalized_main):
                weak_keys.add(normalized_main)

        # Every prefix of the location's own name, so a bare brand key can be
        # recognised as naming a FAMILY rather than a venue. Both the raw and
        # the normalized form are indexed: normalization strips the borough, so
        # "Alamo Drafthouse Staten Island" normalizes to the bare brand and
        # would otherwise look like a venue in its own right rather than one
        # member of the family it shares with the Brooklyn and Downtown rows.
        for variant in (normalized_main, main_name.lower()):
            main_tokens = variant.split()
            for i in range(1, len(main_tokens)):
                locations_map['brand_family'].setdefault(
                    ' '.join(main_tokens[:i]), set()).add(loc.get('id'))

        # Global alternate names (no website_id) - use full_info to include id
        for alt_name in loc.get('alternate_names', []):
            if alt_name and len(alt_name) >= 3:
                locations_map['alternate_names'][alt_name.lower()] = full_info
                strong_keys.add(alt_name.lower())
                normalized_alt, alt_area = _normalize_location_name_parts(alt_name)
                if _area_qualifier_class(alt_area):
                    area_classes.add(_area_qualifier_class(alt_area))
                if normalized_alt and len(normalized_alt) >= 3:
                    locations_map['alternate_names'][normalized_alt] = full_info
                    if _collapse_is_significant(alt_name, normalized_alt):
                        weak_keys.add(normalized_alt)

        short_name = loc.get('short_name', '')
        if short_name and len(short_name) >= 3:
            locations_map['short_names'][short_name.lower()] = full_info
            weak_keys.add(short_name.lower())
            normalized_short, short_area = _normalize_location_name_parts(short_name)
            if _area_qualifier_class(short_area):
                area_classes.add(_area_qualifier_class(short_area))
            if normalized_short and len(normalized_short) >= 3:
                locations_map['short_names'][normalized_short] = full_info
                weak_keys.add(normalized_short)

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

        # Index by street address (e.g., "347 davis ave" from "347 Davis Ave, Staten Island, NY").
        # Use full_info so an address match actually resolves a location_id (not
        # just an emoji). Multiple distinct venues can share a street address (a
        # building with several venues); an address match can't tell them apart,
        # so the second distinct venue marks the address AMBIGUOUS and match-time
        # skips it rather than guessing.
        address = loc.get('address', '')
        city, state = _parse_city_state(address)
        if city and state and len(city) >= 4:
            locations_map['city_states'].setdefault(city, set()).add(state)
        street_address = _extract_street_address(address)
        if street_address:
            existing = locations_map['addresses'].get(street_address)
            if existing is None:
                locations_map['addresses'][street_address] = full_info
            elif existing is not _AMBIGUOUS_ADDRESS and existing.get('id') != loc.get('id'):
                locations_map['addresses'][street_address] = _AMBIGUOUS_ADDRESS

    # A key that some location owns outright is never "weak" — an explicit
    # curated name or alias states the mapping, and the brand-family guard must
    # not override a human's deliberate flagship choice.
    weak_keys -= strong_keys

    # Website-linked locations (from website_locations table)
    locations_map['website_linked'] = db.get_website_locations_map(cursor)

    return locations_map


def _collapse_is_significant(raw, normalized):
    """True if normalizing `raw` dropped a venue-DISTINGUISHING part of the name.

    `_normalize_location_name` removes punctuation, a leading "The", and a
    trailing borough/city qualifier. Only the last of those changes which venue
    the string can refer to, so only it makes the resulting key a *derived* bare
    key (see `weak_keys`). Measured: without this, the curated alias
    "The Conference House" -> loc 1479 collapses to "conference house", gets
    treated as a brand key, and 65 Conference House Museum rows lose their pin
    to Conference House Park.
    """
    lowered = (raw or '').lower()
    if normalized == lowered:
        return False
    return normalized != re.sub(r"^the\s+", "", lowered).strip()


def _is_brand_family_key(locations_map, key, cand_id):
    """True if `key` is a DERIVED bare key that names 2+ same-family venues.

    The bare-`short_name` collision (memory `location_bare_shortname_collision`):
    three "Smorgasburg <somewhere>" rows exist, one of them carries the bare
    `short_name` "Smorgasburg", and so it captures every event whose source only
    said "Smorgasburg" — regardless of which market it was. The same shape
    appears without any `short_name` at all, because
    `_normalize_location_name` strips borough/city qualifiers: "Green Room NYC"
    is indexed under the bare "green room", which then out-ranks the two other
    Green Rooms. Deleting the offending row's alias does not help — the name
    just falls through to prefix/fuzzy and lands somewhere else, often worse.

    So the test is on the KEY, not on the row: a key is refused when
      (a) nothing owns it outright — no location is literally named that and no
          curated alias spells it out (see `weak_keys` in build_locations_map);
      (b) it is a strict prefix of the normalized names of 2+ DISTINCT
          locations, i.e. it names the family rather than a member;
      (c) the candidate it would return is ITSELF one of those family members.

    (c) is what keeps the rule about brands. Measured over all 62,163 distinct
    crawl_event location triples, dropping it costs 51 correct rows on one
    website alone: `short_name` "Montague" belongs to "Books Are Magic (Montague
    St)", which is not a "Montague …" venue at all — the key merely happens to
    prefix unrelated Montague Street rows, so it is distinctive shorthand rather
    than a family label, and must keep resolving.

    Refusing yields None, which `/fix-unmapped-events` surfaces — strictly
    better than a confidently wrong pin nobody notices on the map.
    """
    if key not in locations_map.get('weak_keys', ()):
        return False
    family = locations_map.get('brand_family', {}).get(key, ())
    return len(family) >= 2 and cand_id in family


def _is_brand_family_name(locations_map, key):
    """True if `key` is a derived bare key naming 2+ venues of one family.

    The key-side half of `_is_brand_family_key`, with no candidate to check
    against — used where the question is "does this string name a family?"
    rather than "may this candidate answer it?".
    """
    if not key or key not in locations_map.get('weak_keys', ()):
        return False
    return len(locations_map.get('brand_family', {}).get(key, ())) >= 2


def build_websites_map(cursor):
    """Builds a map for URL-to-extra_tags mapping from the database."""
    return db.get_websites_with_tags(cursor)


def get_location_id(location_name_raw, sublocation_name_raw, source_site_name, event_name_raw, locations_map, website_id=None, _retry_without_address=False):
    """Finds the best matching location ID for an event.

    Matching cascade (checked in priority order, first match wins):
      1. Website-scoped alternate names (highest priority — exact match for this website)
      2. Exact name match (against names, alternate_names, short_names)
      3. Address match (normalized street address comparison)
      3.5. Single-venue website authority (a single-venue website's own venue wins
           over arbitrary same-brand prefix/fuzzy matches when the name is generic)
      4. Prefix match (location name starts with known name, ≥PREFIX_MATCH_COVERAGE to avoid generics)
      5. Fuzzy match (Levenshtein ratio ≥ FUZZY_MATCH_THRESHOLD)
      5c. Cross-website exact match on a curated website-scoped alternate name
          (last resort, unambiguous only — beats leaving the event unmapped)
      5d. Parenthetical parent venue ("Main Pool (in Crotona Park)" → Crotona
          Park) — last resort, exact + unambiguous only
      6. Source site fallback (website name matches a location name)
      7. Website-linked location fallback (single-venue website, empty/virtual location_name)

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

    # Raw (un-normalized) location text + city->state index for the region-conflict
    # guard. Uses the raw strings, not the normalized keys, so the "City, ST" tail
    # and city tokens survive for _region_conflict.
    city_states = locations_map.get('city_states', {})
    area_classes = locations_map.get('area_classes', {})
    raw_geo = ' '.join(p for p in (location_name_raw, sublocation_name_raw) if p)

    def conflicts(info):
        """True if this candidate names a region/area the source contradicts.

        Two independent guards, both keyed on the RAW source text: a
        cross-municipality state conflict (`_region_conflict`), and a
        borough/city qualifier the name-collapse would otherwise have thrown
        away (`_area_qualifier_conflict`).
        """
        return (_region_conflict(raw_geo, info, city_states)
                or _area_qualifier_conflict(raw_geo, info, area_classes))

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

    # Also let website-scoped alts (Step 1) match the venue-name portion before a
    # comma-address tail. Aggregators often emit "Columbus Park, 199 W Franklin
    # St, Hackensack" as one location string; a curated per-website alt keyed on
    # the bare "Columbus Park" should still resolve it (and disambiguate two
    # same-named parks in different towns that the state-level guard can't split).
    if location_name_raw and ',' in location_name_raw:
        before_comma_key = _normalize_location_name(location_name_raw.split(',')[0])
        if len(before_comma_key) > 3 and before_comma_key not in primary_search_keys:
            primary_search_keys.append(before_comma_key)

    # Variant: handle "Branch, Room" patterns (e.g. BPL "Highlawn, Meeting Room")
    # by also trying just the part before the first comma. Some extraction passes
    # mash the room name into location instead of putting it in sublocation —
    # without this we silently miss the venue. We also try common venue-type
    # suffix completions so a bare "Highlawn" can hit "Highlawn Library".
    # ' park' deliberately omitted: too easily fuzzy-matches "X Parkway".
    # Heuristic (extraction-recovery) variants are tracked separately from the
    # keys the source actually gave us. Step 2 tries every EXACT key across all
    # tiers before it will consider a mangled variant in ANY tier — see the
    # comment there for why the reverse order silently lost library branches.
    heuristic_keys = set()

    if location_name_raw and ',' in location_name_raw:
        before_comma = _normalize_location_name(location_name_raw.split(',')[0])
        if before_comma and before_comma != normalized_loc and len(before_comma) > 3:
            for suffix in (' library', ' garden', ' center', ' studio', ''):
                variant = (before_comma + suffix).strip()
                if variant and variant not in location_keys:
                    location_keys.append(variant)
                    heuristic_keys.add(variant)

    # Variant: handle generic venue-type suffixes (e.g. "Pleasant Village
    # Community Garden" when DB has "Pleasant Village", or "La Petit Versailles
    # Garden" when DB has "Le Petit Versailles"). Strip and re-try.
    for suffix in (' community garden', ' garden', ' library', ' center', ' park'):
        if normalized_loc.endswith(suffix) and len(normalized_loc) > len(suffix) + 3:
            stripped = normalized_loc[:-len(suffix)].strip()
            if stripped and stripped not in location_keys:
                location_keys.append(stripped)
                heuristic_keys.add(stripped)
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
                # The ONE thing curation cannot speak for: the key is the
                # COLLAPSED form, so a curated "Downtown Manhattan" alias also
                # answers to "Downtown Brooklyn" (both are the bare "downtown").
                # That is the collapse overreaching, not a mapping anyone chose
                # — MAS (w494) has exactly this alias, and all 36 of its
                # "Downtown Brooklyn" rows resolve to Lower Manhattan. Only an
                # area conflict is checked here; every other heuristic still
                # yields to the curated mapping.
                if _area_qualifier_conflict(raw_geo, website_tier[key], area_classes):
                    continue
                return make_result(website_tier[key])

    # Step 2: Exact matches in global tiers (names, alternate_names, short_names).
    # The 'names' tier is the location's own primary name (high confidence — a
    # city token there is usually part of the name). The alternate_names and
    # short_names tiers are looser, so a same-named place in a conflicting
    # municipality is rejected via the region-conflict guard (e.g. the global
    # "Columbus Park" alt of Manhattan's park vs a "Columbus Park, Hoboken" event).
    #
    # Key specificity outranks tier priority. The keys are grouped exact-location
    # first, then heuristic variants, then the event name, and each GROUP is run
    # across all three tiers before the next group starts. Tier order is
    # unchanged within a group, and the groups preserve the original relative
    # order, so this only ever demotes a mangled key below an exact one.
    #
    # Why it matters: the suffix-strip above turns "Park Slope Library" into the
    # bare "park slope". With tiers looping outermost, that stripped key hit
    # names["park slope"] — the neighborhood GENERIC — before
    # alternate_names["park slope library"] — the actual branch — was ever
    # consulted. A library branch was therefore only reachable if its PRIMARY
    # name was literally "<Neighborhood> Library"; reachable-by-alt branches
    # silently dumped their events onto the neighborhood pin. That is the
    # `location_name_vs_program_name` failure mode, and 31 generic/branch pairs
    # were exposed to it.
    exact_loc_keys = [k for k in location_keys if k not in heuristic_keys]
    variant_loc_keys = [k for k in location_keys if k in heuristic_keys]
    event_name_keys = [k for k in search_keys if k not in location_keys]

    # A single-venue site abbreviating itself must not be captured by an
    # unrelated location that happens to own that acronym as its whole name.
    # secretrisoclub.com emits "SRC"; an exact match on names["src"] handed six
    # events to a DUMBO art space also called SRC, three miles from Bushwick.
    # Only the extracted location name itself is checked (not the mangled
    # variants or the event name), and only when the acronym expands to exactly
    # the venue this website is linked to — so a genuinely different venue named
    # in full still wins the exact match, as it should.
    home_venue = _single_linked_venue(locations_map, website_id)
    home_is_initialism = (
        home_venue is not None
        and _is_initialism_of(normalized_loc, home_venue.get('name') or '')
    )

    for key_group in (exact_loc_keys, variant_loc_keys, event_name_keys):
        for tier_name in ['names', 'alternate_names', 'short_names']:
            tier = locations_map.get(tier_name, {})
            for key in key_group:
                if key in tier:
                    cand = get_first(tier[key])
                    if tier_name != 'names' and conflicts(cand):
                        continue
                    # A derived bare key that names a whole family of venues
                    # ("smorgasburg", "green room") can't pick a member.
                    if _is_brand_family_key(locations_map, key, cand.get('id')):
                        continue
                    if (home_is_initialism and key == normalized_loc
                            and cand.get('id') != home_venue.get('id')):
                        return make_result(home_venue)
                    return make_result(cand)

    # Step 3: Address matching (e.g., "347 Davis Ave" matches location at that address)
    addresses_tier = locations_map.get('addresses', {})
    for key in search_keys:
        street_addr = _extract_street_address(key)
        match = addresses_tier.get(street_addr) if street_addr else None
        if match is not None and match is not _AMBIGUOUS_ADDRESS:
            return make_result(match)

    # Step 3.5: Single-venue website authority.
    # When the source website is linked to exactly ONE venue, that venue is
    # authoritative for events crawled from it. If the extracted location_name is
    # only a brand prefix/substring of the venue (e.g. "Regal" from a specific
    # Regal theater's own site, "AMC" from one AMC) it would otherwise prefix- or
    # fuzzy-match an ARBITRARY same-brand venue below and collapse many theaters
    # onto one location. Prefer the website's own venue. A specific DIFFERENT
    # venue name is already returned by the exact/address steps above, so this
    # only fires for generic/partial names consistent with the linked venue.
    # An initialism counts as "consistent with the linked venue" too: neither the
    # substring nor the Levenshtein test relates "src" to "secret riso club", so
    # without it a self-abbreviating venue falls through to prefix/fuzzy matching
    # and lands on an arbitrary venue or nothing at all.
    if home_venue is not None and normalized_loc and len(normalized_loc) >= 3:
        v_name = _normalize_location_name(home_venue.get('name') or '')
        consistent = bool(v_name) and (
            normalized_loc in v_name or v_name in normalized_loc
            or home_is_initialism
        )
        # The Levenshtein arm is the loose one, and on its own it lets a
        # single-venue website claim a name that plainly belongs to somebody
        # else: "Books Are Magic" scores 0.69 against "Brooklyn Book Bodega",
        # so Brooklyn Book Bodega's site would pin the bookstore's readings onto
        # itself (memory `single_venue_website_authority_claims`). That only
        # became reachable once Step 2 started declining brand-family keys, so
        # the veto is scoped to exactly that: a name Step 2 refused because it
        # names a family of venues is a name that belongs to somebody else, and
        # unmapped is the honest answer. Deliberately NOT a general "is this a
        # known venue" test — measured, that also un-pinned 57 Bronx CB9 rows
        # ("ShopRite Community Room") and every org whose events say "New York
        # City", which the fallback is there to catch. The substring and
        # initialism arms are untouched: those describe the home venue itself,
        # which is the whole point of the tier ("Regal" from one Regal
        # theater's own site).
        if not consistent and not _is_brand_family_name(locations_map, normalized_loc):
            consistent = _calculate_levenshtein_ratio(normalized_loc, v_name) >= 0.6
        if consistent:
            return make_result(home_venue)

    # Step 4: Prefix matching (e.g., "Devocíon" matches "Devocíon (Williamsburg)")
    # Only use location_keys here to avoid matching event names to unrelated locations
    # Require prefix to cover >= 70% of the key to avoid generic names matching
    # specific venues (e.g., "New York City" matching "New York City Center").
    # Scan alternate_names too: a curated alternate like "Agger Fish Building at BNY"
    # should still resolve when the extractor emits the bare "Agger Fish Building"
    # (73% coverage). Without this, such near-misses fall through to fuzzy matching,
    # whose 0.90 threshold rejects them — leaving location_id NULL and spawning a
    # duplicate event in the merger.
    for key in location_keys:
        # A bare generic word ("gallery", "studio") carries no venue-identifying
        # information — don't let it prefix-match a specific venue like
        # "Gallery MC" or "Studio 525". Such queries should fall through to
        # website-scoped resolution or stay unmatched.
        if key in BARE_ONLY_GENERIC_WORDS:
            continue
        if len(key) < 5:
            continue
        # Same reasoning as the Step 2 brand-family guard, applied one tier
        # lower. The coverage-ambiguity break below only sees the family members
        # that clear PREFIX_MATCH_COVERAGE, so a family whose members have
        # uneven name lengths ("bloomingdale" -> "Bloomingdale Park" at 0.71 but
        # "Bloomingdale School of Music" at 0.43) would otherwise be resolved by
        # whichever sibling happens to have the shortest name.
        #
        # Gated on the SAME weak-key test as Step 2, and measured: without it,
        # every key that merely prefixes two venue names is refused, which
        # un-pinned 51 Books Are Magic rows keyed on `short_name` "Montague",
        # plus BPL "Pacific", "Pratt Library" and "Queens College" — none of
        # them brand keys, all of them the only sensible answer.
        if _is_brand_family_name(locations_map, key):
            continue
        for tier_name in ('names', 'alternate_names'):
            # A branch-suffixed key ("devocion (williamsburg)") is a deliberate
            # disambiguation of a venue with several outposts, so a bare venue
            # name legitimately prefixes all of them. Keep first-wins there.
            paren_hit = None
            # Coverage-based hits, keyed by location_id so the same venue reached
            # via several keys counts once.
            coverage_hits = {}
            for loc_key, match in locations_map.get(tier_name, {}).items():
                is_paren = loc_key.startswith(key + '(')
                is_coverage = (
                    loc_key.startswith(key + ' ')
                    and len(key) / len(loc_key) >= PREFIX_MATCH_COVERAGE
                )
                if not (is_paren or is_coverage):
                    continue
                # The key reaching this candidate is often a generic-STRIPPED
                # variant of the source name ("Brooklyn Public Library" ->
                # "brooklyn public"), which then re-completes with a DIFFERENT
                # venue-type word ("brooklyn public house", a bar, at 15/21 =
                # 0.71 coverage). Swapping one venue type for another names a
                # different kind of place, so the source name itself vetoes the
                # candidate — see _generic_type_swap.
                if is_coverage and _venue_type_swap_names(normalized_loc, loc_key):
                    continue
                for cand in (match if isinstance(match, list) else [match]):
                    if conflicts(cand):
                        continue
                    if is_paren:
                        if paren_hit is None:
                            paren_hit = cand
                    else:
                        coverage_hits.setdefault(cand.get('id'), cand)

            if paren_hit is not None:
                return make_result(paren_hit)
            if len(coverage_hits) == 1:
                return make_result(next(iter(coverage_hits.values())))
            if len(coverage_hits) > 1:
                # Ambiguous: this key prefixes 2+ distinct venues at >= coverage
                # (e.g. "first reformed church" covers exactly 0.700 of "first
                # reformed church of nyack" AND of a Brooklyn/Hastings twin).
                # Taking the first is a coin flip that silently mis-pins events
                # to another county, so reject the whole key and let the caller
                # fall through to website-scoped/fuzzy resolution or NULL.
                break

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
        all_toks = variant.split()
        toks = {t for t in all_toks if len(t) >= 4}
        if len(toks) >= 2:
            variant_tokens.append((variant, toks, set(all_toks)))

    # A bare generic word shouldn't fuzzy-match a specific venue whose name
    # merely contains it (e.g. "gallery" in "gallery mc"). These depend only on
    # the normalized loc/subloc + module constant, so compute once.
    loc_is_generic = normalized_loc in GENERIC_LOCATION_WORDS
    subloc_is_generic = normalized_subloc in GENERIC_LOCATION_WORDS

    if len(full_loc) > 3 or len(normalized_name) > 3:
        for priority, tier in all_tiers:
            for key in tier:
                if not key.strip():
                    continue

                is_match = (
                    key == normalized_loc or
                    (len(normalized_name) > 3 and key == normalized_name) or
                    (len(key) > 3 and key in full_loc) or
                    (len(normalized_loc) > 3 and not loc_is_generic and normalized_loc in key) or
                    (len(normalized_subloc) > 3 and not subloc_is_generic and normalized_subloc in key)
                )

                # Token-overlap tripwire: if a variant shares ≥2 long tokens
                # with this key, fuzzy-compare against all matching variants.
                # This catches single-char typos that defeat substring checks.
                matched_variants = []
                if not is_match and variant_tokens:
                    key_all = set(key.split())
                    key_toks = {t for t in key_all if len(t) >= 4}
                    for variant, toks, variant_all in variant_tokens:
                        if len(toks & key_toks) < 2:
                            continue
                        # The ≥2 shared long tokens are frequently a generic
                        # venue phrase ("training center", "community center",
                        # "arts center", "X at Hudson River Park"). On its own
                        # that phrase can pin two unrelated facilities to each
                        # other when the only thing distinguishing them is a
                        # short identifier the long-token filter never sees —
                        # e.g. "BCC training center" vs "DEP training center"
                        # (bcc/dep are 3 chars), "100/55 Washington Street",
                        # "Pier 25/66 at Hudson River Park". Honor the tripwire's
                        # actual purpose (recovering typos / abbreviations like
                        # "La/Le Petit Versailles", "Saint/St Nicholas Park"): if
                        # BOTH names carry a *distinctive* leftover token and
                        # they don't reconcile (typo, abbreviation, or hyphen-
                        # join), they're different venues — reject.
                        shared_all = variant_all & key_all
                        sig_v = _significant_leftovers(variant_all - shared_all)
                        sig_k = _significant_leftovers(key_all - shared_all)
                        if sig_v and sig_k and not (
                            all(_leftover_reconciles(a, sig_k) for a in sig_v)
                            and all(_leftover_reconciles(b, sig_v) for b in sig_k)
                        ):
                            continue
                        matched_variants.append(variant)
                    if matched_variants:
                        is_match = True

                # NOTE: the Step 2 brand-family refusal deliberately does NOT
                # extend to this tier, which means a bare family name the exact
                # tier declined can still be answered here (`full_loc` equals
                # the tier key, so the prefix branch scores it 0.99). Measured
                # 2026-08-17 over all 62,163 distinct crawl_event location
                # triples: adding the guard here un-pinned 2,971 rows —
                # "NYU" (352), "BASEMENT" (257), "Midtown" (213), "Devoción"
                # (41) — because normalization is lossy on BOTH sides, so a
                # source that spelled the branch out in full ("Green Room NYC",
                # 206 rows) is indistinguishable from the bare brand by the
                # time this tier sees it. The exact tier can tell them apart;
                # this one cannot, so it must not try.
                if is_match:
                    # Reject an area-conflicting candidate HERE rather than
                    # only at the end, so the runner-up still gets to win. The
                    # final check alone returned None whenever the top scorer
                    # conflicted — e.g. "Downtown Brooklyn" scores the Lower
                    # Manhattan alias highest, and Downtown Brooklyn itself,
                    # sitting just below it, never got its turn. The
                    # region-conflict half stays where it was: falling through
                    # to a second-best candidate across a state line is exactly
                    # the guess that guard exists to refuse.
                    if _area_qualifier_conflict(raw_geo, get_first(tier[key]), area_classes):
                        continue
                    if len(normalized_name) > 3 and key == normalized_name:
                        score = 1.0
                    elif len(key) > 3 and (full_loc.startswith(key) or full_loc.endswith(key)) and len(key) / len(full_loc) >= PREFIX_MATCH_COVERAGE:
                        score = 0.9 + (len(key) / len(full_loc)) * 0.09
                    else:
                        # A source string that differs from the key ONLY by a
                        # venue-TYPE word ("… Library" vs "… House", "madison
                        # square park" vs "madison square garden") names a
                        # different kind of place, so it scores 0 no matter how
                        # close the Levenshtein ratio is (see _generic_type_swap).
                        #
                        # Applied to the SOURCE strings only, never to the
                        # tripwire's variant list. A/B over all 60,644
                        # crawl_event (location_name, sublocation, website_id)
                        # triples, 2026-08-11:
                        #
                        #   source strings only : 1 newly-NULL, a real mis-pin
                        #                         ("The Cornerstone Center",
                        #                         Harlem -> "Cornerstone Bar",
                        #                         Mineola)
                        #   + variants          : 13 newly-NULL, of which 8 were
                        #                         resolving CORRECTLY
                        #
                        # The 8 are venue types that genuinely nest or coincide —
                        # "Betsy Head Pool"/"Saxon Woods Pool" inside their
                        # PARKS, "Brooklyn Borough Plaza" at Borough HALL,
                        # "Crotona Park Tennis House" vs "Crotona Tennis House",
                        # "Clifton Place Memorial Park and Garden" vs the same
                        # venue's "… Garden & Park" — plus stripped variants
                        # manufacturing swaps the real names don't have. Winning
                        # 5 more mis-pins is not worth un-pinning 8 real venues.
                        score = max(
                            _fuzzy_ratio(normalized_loc, key),
                            _fuzzy_ratio(full_loc, key),
                            _fuzzy_ratio(normalized_name, key) if len(normalized_name) > 3 else 0,
                            *(_calculate_levenshtein_ratio(v, key) for v in matched_variants)
                        )

                    if score >= FUZZY_MATCH_THRESHOLD and (score > best_score or (score == best_score and priority < best_priority)):
                        best_score, best_priority = score, priority
                        best_result = get_first(tier[key])

    if best_result and not conflicts(best_result):
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
        match = addresses_tier.get(street_addr) if street_addr else None
        if match is not None and match is not _AMBIGUOUS_ADDRESS:
            return make_result(match)

    # Step 5c: Cross-website exact match on a curated website-scoped alternate name.
    #
    # A website-scoped alt exists to DISAMBIGUATE a string for one website, so it
    # is deliberately invisible to the others (Step 1). But when the whole cascade
    # above has failed, the alternative isn't "a safer match" — it's NULL, which
    # leaves the event unmapped and spawns a duplicate in the merger. A curated
    # alt is hand-entered venue knowledge, and an EXACT full-string hit on one is
    # far better evidence than nothing at all.
    #
    # Kept safe by three constraints:
    #   - runs last (after every global tier, prefix and fuzzy), so it can never
    #     override or weaken an existing match or guard;
    #   - exact match only, on primary_search_keys — no prefix, no fuzzy;
    #   - if the same key is scoped to DIFFERENT locations across websites, that
    #     string is genuinely ambiguous and we decline rather than coin-flip;
    #   - the alt must be CORROBORATED by the venue it points at — it has to
    #     share a distinctive token with the location's own name. Plenty of
    #     scoped alts are pure in-site shorthand that means nothing anywhere
    #     else ("Online Event" → NYU, "The Dance Floor" → Lincoln Center, "The
    #     Rooftop" → Elsewhere, "TODAY Plaza" → Rockefeller Center). Scoping is
    #     precisely what keeps those contained, so they must stay contained.
    #
    # Regression: "Prospect Park Picnic House" (an exact alt of location 6434,
    # scoped to website 2704) resolved to nothing when the same string arrived
    # from website 464.
    scoped_all = locations_map.get('website_scoped', {})
    if scoped_all:
        for key in primary_search_keys:
            hits = []
            for scoped_website_id, tier in scoped_all.items():
                if scoped_website_id == website_id:
                    continue  # already tried in Step 1
                cand = tier.get(key)
                if cand is not None:
                    hits.append(get_first(cand))
            if not hits:
                continue
            ids = {h.get('id') for h in hits}
            if len(ids) > 1:
                continue  # ambiguous across websites — decline
            if conflicts(hits[0]):
                continue
            if not _shares_distinctive_token(
                    key, _normalize_location_name(hits[0].get('name') or '')):
                continue  # in-site shorthand, not portable venue knowledge
            return make_result(hits[0])

    # Step 5d: Parenthetical parent venue — "<feature> (in <Parent Venue>)".
    #
    # NYC Parks names a sub-feature first ("Main Pool", "Play Area", "Dance
    # Room", "Pier 2") and puts the venue we actually have a row for inside an
    # "(in …)" parenthetical. The full string defeats every tier above: the
    # leading feature drags prefix coverage below PREFIX_MATCH_COVERAGE
    # ("brooklyn bridge park" covers 0.69 of "pier 2 in brooklyn bridge park")
    # and the Levenshtein ratio below FUZZY_MATCH_THRESHOLD, so ~57 Parks
    # sub-features re-orphan to NULL on every crawl and get re-mapped by hand.
    #
    # Deliberately LAST-RESORT and deliberately narrow, because the parenthetical
    # names a *container*, not the venue itself — mapping to it is a coarsening,
    # correct only when we have nothing better:
    #   - runs after every global tier, so an exact/prefix/fuzzy hit on the real
    #     sub-feature (many playgrounds have their own location row) always wins;
    #   - EXACT normalized match only, no prefix and no fuzzy, so it cannot fuse
    #     two distinct venues whose names merely resemble each other;
    #   - declines when the parent name is ambiguous (2+ locations share it) or
    #     generic ("in the park"), rather than coin-flipping;
    #   - honors the region-conflict guard like every other tier.
    parenthetical_parent = (
        _extract_parenthetical_parent(location_name_raw)
        or _extract_parenthetical_parent(sublocation_name_raw)
    )
    if (parenthetical_parent and len(parenthetical_parent) >= 5
            and parenthetical_parent not in GENERIC_LOCATION_WORDS):
        for tier_name in ('names', 'alternate_names', 'short_names'):
            match = locations_map.get(tier_name, {}).get(parenthetical_parent)
            if match is None:
                continue
            if isinstance(match, list):
                # Same name at 2+ distinct locations — genuinely ambiguous.
                if len({m.get('id') for m in match}) > 1:
                    continue
            cand = get_first(match)
            if conflicts(cand):
                continue
            return make_result(cand)

    # Step 6: Source site fallback (match website name to location)
    # Only fires when no real venue name was extracted — otherwise an event
    # held at a partner venue (e.g., SVA exhibition at Pfizer Building) would
    # silently get pinned to the website's home location.
    #
    # This tier guesses a venue from the ORGANIZER's name, with nothing from the
    # event to corroborate it, so it must be an identity match — not a fuzzy one.
    # A Levenshtein threshold here is actively harmful: an organizer name is a
    # brand string, and brands differ from unrelated venues by one or two
    # characters all the time. Measured over the live locations table, a 0.90
    # ratio mapped "The Moth" -> "The MOUTH" (a Brooklyn bar), "NJ Botanical
    # Garden" -> "NY Botanical Garden", "Brooklyn Pride" -> "Brooklyn Bridge",
    # "Mint Theater Company" -> "Mayi Theater Company" and "Ulster County
    # Historical Society" -> "Suffolk County Historical Society" — 14 of the 29
    # sites that relied on the fuzzy path were pinned to the wrong venue.
    #
    # So compare on _squash_identity: the names must be the same string once
    # spacing/punctuation (and a plural 's') are discarded. That still absorbs
    # every benign way a website name drifts from its venue name — "OpenPlans" /
    # "Open Plans", "@dearfriendbooks" / "Dear Friend Books", "ITP|IMA" /
    # "ITP IMA", "Rullo's" / "Rullo’s", "Gallery 54" / "Gallery54" — while a
    # genuinely different word can no longer sneak through. Real spelling
    # variants that survive squashing (e.g. "Ave" vs "Avenue") belong in
    # location_alternate_names, which is checked earlier and is explicit.
    if not normalized_loc:
        site_key = _squash_identity(_normalize_location_name(source_site_name))
        if site_key:
            for priority, tier in all_tiers:
                for key in tier:
                    match = tier[key]
                    if isinstance(match, list):
                        continue
                    if _squash_identity(_normalize_location_name(key)) == site_key:
                        return make_result(match)

    # Step 7: Website-linked location fallback
    # When the location name is virtual/generic (normalized to empty) and the website
    # has exactly one linked location, use it. Handles "Online" events from
    # single-venue websites (e.g., MoMath "Online" → MoMath).
    # Only applies when there's no real venue name to match against.
    if website_id and not normalized_loc:
        linked = locations_map.get('website_linked', {}).get(website_id, [])
        if len(linked) == 1:
            return make_result(linked[0])

    # (The former single-venue brand-name fallback is now Step 3.5, which runs
    # before prefix/fuzzy so the authoritative venue wins over arbitrary
    # same-brand prefix matches.)

    # Step 8: retry with a trailing postal address stripped off the venue name.
    # Sources that render "<Venue>, <full street address ... ZIP>" — posh.vip's
    # "Pier 78 at Hudson River Park — 455 12th Ave, New York, NY 10018, USA",
    # Painting Lounge's "Midtown: 40 W 38th St, 2nd Fl, New York NY 10018" —
    # never match, because the address tail swamps every name comparison.
    #
    # This is deliberately a LAST RESORT rather than a normalization step. A/B
    # over all 30,119 distinct crawl_event location_names (2026-08-05): applying
    # the strip up front gives 49 wins but **16 regressions** and 3 wrong
    # re-pins, because when the venue name is not itself a known location the
    # ADDRESS is the only thing that resolves it (e.g. "Low Plaza, 535 W. 116
    # St." → loc 467, "Jerome Greene Hall, 435 W. 116 St." → 7537, both via the
    # address tier). Running it only after everything else has failed keeps all
    # 49 wins with zero regressions and zero re-pins.
    if not _retry_without_address and location_name_raw:
        stripped = _strip_trailing_postal_address(location_name_raw)
        if stripped and stripped != location_name_raw:
            return get_location_id(stripped, sublocation_name_raw, source_site_name,
                                   event_name_raw, locations_map, website_id=website_id,
                                   _retry_without_address=True)

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

    def _row(event, occ):
        # Key insertion order matters — these rows flow into json.dumps stored in
        # crawl_events.raw_data, so the serialized key order must match.
        return {
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

    rows = []
    for event in events:
        # Each occurrence becomes a separate row (matching legacy behavior)
        occurrences = event.get('occurrences') or []

        if not occurrences:
            # Event extracted without date info — store with empty dates
            # so it can be flagged for investigation
            row = _row(event, {})
            row['missing_date'] = True
            rows.append(row)
            continue

        for occ in occurrences:
            rows.append(_row(event, occ))

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

# --- Cross-event description bleed: a locative sentence from a SIBLING event ---
#
# Multi-record listing pages repeat one house sentence per record — NYPL's is
# "This event will take place in person at the <Branch> Library." (2,251 of the
# ~2,340 crawl_events carrying that phrasing are w3). When the extractor chunks
# such a page it regularly staples one record's sentence onto a sibling record,
# producing a description that names a venue the event is not at. Measured
# 2026-08-24: 33 of 173 active w3 events with that phrasing named a branch
# contradicting their own pin.
#
# `location_name` is the reliable field here — on every one of those 33 rows all
# of the event's crawl_events agreed on the correct branch while carrying the
# wrong branch in the prose. So when the sentence contradicts `location_name`,
# the SENTENCE is what is wrong.
#
# The repair drops the whole sentence and never rewrites the venue name inside
# it: the sentence belongs to another record, so patching the name would only
# make a foreign sentence look correct. The body is left untouched — on these
# listing pages it is the program's system-wide blurb, shared across branches.
#
# WHY THIS IS DELIBERATELY NARROW. A general "description must not name a venue
# contradicting location_name" check is NOT safe. Backtested 2026-08-24 over the
# 9,132 crawl_events whose description contains "take(s) place", a loose
# `takes place ... at <X>` rule fired on 1,272 rows — only 488 of them w3 — and
# the non-w3 hits were overwhelmingly legitimate prose it would have destroyed:
#   - date/time tails: "A special opening reception will take place on Saturday,
#     April 11 at 2pm"  (captures "2pm" as the venue)
#   - genuine multi-venue copy under a neighborhood pin: "Performances take place
#     at BAM, Roulette, Public Records"  (pin "Downtown Brooklyn")
#   - a real venue named under a generic pin: "The event takes place at the
#     historic Cipriani"  (pin "Manhattan, New York")
# So the guard matches only the full house form: the subject must be the event
# itself ("This event/program/class..."), the sentence must carry an explicit
# in-person/online modality (which is what excludes the date/time tails), and the
# named venue must contain a capitalized or numbered word. Failure mode is then
# cheap: the worst a false positive can do is drop one redundant sentence that
# restates the venue.

_LOCATIVE_ABBREV = re.compile(r'\b(St|Ave|Blvd|Rd|Dr|Mt|Ft|Jr|Sr)\.$')

# "This event will take place in person at the Parkchester Library"
# The leading char is optional because extraction sometimes clips it ("his
# event will take place..." was observed on event 224496).
_LOCATIVE_SENTENCE = re.compile(
    r'^\W*\w?his\s+(?:event|program|class|workshop|session)\s+'
    r'(?:will\s+)?takes?\s+place\s+'
    r'(?:in[-‐-― ]?person|online|virtually)\s*,?\s+'
    r'(?:at|in)\s+(?:the\s+)?(.+?)\s*[.!?]*$',
    re.IGNORECASE | re.DOTALL,
)

# Words too generic to establish that two venue strings are different places.
_LOCATIVE_STOPWORDS = {
    'the', 'a', 'an', 'of', 'and', 'at', 'in', 'on', 'for', 'this', 'event',
    'program', 'class', 'workshop', 'session', 'person', 'online', 'virtually',
    'library', 'branch', 'center', 'centre', 'room', 'floor', 'building',
    'auditorium', 'community', 'lab', 'st', 'street', 'ave', 'avenue',
    'new', 'york', 'nyc', 'public',
}


def _locative_tokens(text):
    """Significant lowercase word set for comparing two venue strings."""
    text = (text or '').lower().replace("'", '').replace('’', '')
    text = re.sub(r'[^a-z0-9 ]', ' ', text)
    return {w for w in text.split()
            if len(w) > 1 and w not in _LOCATIVE_STOPWORDS}


def _names_a_venue(text):
    """True when the captured phrase looks like a place name rather than a time
    or a bare noun — i.e. it has a capitalized or number-led word."""
    return bool(re.search(r'\b([A-Z][a-zA-Z]|\d+(?:st|nd|rd|th)\b)', text or ''))


def _split_sentences(text):
    """Split on sentence terminators, keeping common abbreviations intact so
    "St. George Library Center" does not break into two sentences."""
    out, buf = [], ''
    for piece in re.split(r'(?<=[.!?])\s+', text):
        buf = (buf + ' ' + piece).strip() if buf else piece
        if _LOCATIVE_ABBREV.search(buf):
            continue
        out.append(buf)
        buf = ''
    if buf:
        out.append(buf)
    return out


def strip_contradicting_locative(description, location_name):
    """Drop a "This event will take place in person at <Venue>" sentence whose
    named venue shares no significant word with `location_name`.

    Returns the description unchanged when nothing contradicts, and None when
    the contradicting sentence was the ENTIRE description — a NULL description
    is recoverable (the detail crawl and the merger backfill both fill it in), a
    confidently wrong venue name is not.
    """
    if not description or not location_name:
        return description
    here = _locative_tokens(location_name)
    if not here:
        return description

    kept, dropped = [], False
    for sentence in _split_sentences(description.strip()):
        match = _LOCATIVE_SENTENCE.match(sentence)
        if match and _names_a_venue(match.group(1)):
            named = _locative_tokens(match.group(1))
            if named and not (named & here):
                dropped = True
                continue
        kept.append(sentence)

    if not dropped:
        return description
    return ' '.join(kept).strip() or None


def process_events(cursor, connection, crawl_result_id, website_name, run_date_str,
                   locations_map=None, websites_map=None, tag_context=None):
    """
    Process extracted events and store in crawl_events table.

    Supports both JSON (structured output) and legacy markdown table formats.

    locations_map, websites_map and tag_context are immutable across a single
    Step-4 run, so a caller processing many crawl_results (e.g. main.py) can build
    them once and pass them in to avoid rebuilding per result. When omitted they
    are built internally, preserving standalone-script callers. tag_context is the
    4-tuple returned by load_tag_context().

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

    safe_filename = create_safe_filename(website_name)

    # Try JSON first, fall back to markdown
    parsed_rows = _parse_json_events(extracted_content)
    if parsed_rows is None:
        # Fallback to markdown parsing
        parsed_rows = _parse_markdown_table(extracted_content)

    if not parsed_rows:
        db.update_crawl_result_processed(cursor, connection, crawl_result_id, 0)
        return 0

    # Sanity-fix 12pm/12am misreads before downstream processing.
    for row in parsed_rows:
        if row.get('end_time'):
            row['end_time'] = _sanity_check_end_time(
                row.get('start_time') or '',
                row['end_time'],
                crawled_content,
            )

    current_date, future_limit_date = get_active_date_window()

    # Build the per-run context lazily (only after we know there are rows to
    # process), reusing what the caller passed in. These are immutable across a
    # Step-4 run, so main.py builds them once and threads them through.
    if locations_map is None:
        locations_map = build_locations_map(cursor)
    if websites_map is None:
        websites_map = build_websites_map(cursor)
    if tag_context is None:
        tag_context = load_tag_context(cursor)
    tag_rules, ancestor_map, root_tags, disambiguation_rules = tag_context

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

        # Non-event junk filter: closures, calls for submissions/grants, venue
        # rentals, season passes, showtime placeholders, SEO spam, fundraising
        # campaigns, submission-call contests, info-booth listings. Drop before
        # they ever become a crawl_event; log so the rejection is auditable.
        if is_obvious_non_event(row_dict.get('name', ''),
                                row_dict.get('description', '')):
            log_rejection(
                cursor, crawl_result_id, website_id,
                rejection_type='non_event_junk', stage='extract',
                event_name=row_dict.get('name'),
                event_url=(row_dict.get('url') or '').strip() or None,
                start_date=(row_dict.get('start_date') or None),
                end_date=(row_dict.get('end_date') or None),
                details='Name matched non-event junk pattern',
            )
            rejection_counts['non_event_junk'] = rejection_counts.get('non_event_junk', 0) + 1
            continue

        event_url = (row_dict.get('url') or '').strip()

        # Cancellation marker in the URL slug: the venue re-slugged the event to
        # `.../canceled-<title>` (or `.../<title>-postponed`) but left the visible
        # title clean, so nothing else in the row says the event is dead. Drop it
        # here rather than letting it land as an active, real-looking listing.
        if event_url and is_cancelled_by_url(event_url):
            log_rejection(
                cursor, crawl_result_id, website_id,
                rejection_type='cancelled_url_slug', stage='extract',
                event_name=row_dict.get('name'), event_url=event_url,
                start_date=(row_dict.get('start_date') or None),
                end_date=(row_dict.get('end_date') or None),
                details='URL slug marks the event canceled/postponed',
            )
            rejection_counts['cancelled_url_slug'] = rejection_counts.get('cancelled_url_slug', 0) + 1
            continue

        # Luma calendar-level metadata read as an event. `group_event_occurrences`
        # falls back to `source_url` when a row has no URL of its own, so the
        # effective URL is computed the same way here. A blank body is the
        # corroborating signal: e161574 (Accent Sisters) is a real screening
        # whose only URL is its calendar page, and its description spares it.
        if source_url and _description_is_blank(row_dict.get('description')):
            effective_url = absolutize_url(event_url, source_url) or source_url
            if is_luma_calendar_listing_url(effective_url, source_url):
                log_rejection(
                    cursor, crawl_result_id, website_id,
                    rejection_type='luma_calendar_metadata', stage='extract',
                    event_name=row_dict.get('name'), event_url=effective_url,
                    start_date=(row_dict.get('start_date') or None),
                    end_date=(row_dict.get('end_date') or None),
                    details='Record has no event URL of its own — points at the '
                            'Luma calendar endpoint it was extracted from',
                )
                rejection_counts['luma_calendar_metadata'] = (
                    rejection_counts.get('luma_calendar_metadata', 0) + 1)
                continue

        # URL grounding check: if the AI returned a URL that doesn't appear in
        # the crawled content, it's likely a hallucinated event. Log and skip.
        if event_url and crawled_content and not _url_grounded_in_content(event_url, crawled_content):
            log_rejection(
                cursor, crawl_result_id, website_id,
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
                        cursor, crawl_result_id, website_id,
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

        # Check for virtual events (delivery method comes from the raw source
        # location string, never from the venue the event is pinned to).
        for _vtag in virtual_tags_for_location(processed_row.get('location', '')):
            if _vtag not in processed_row.get('tags', []):
                processed_row.setdefault('tags', []).append(_vtag)

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

    # Last-resort URL: an event with no URL at all is dropped by the exporter, so
    # a rejected event-specific URL must not be able to turn a real event into an
    # invisible one. group_event_occurrences already appends `source_url` (the
    # leading URL line of the crawled content) to every event, which covers the
    # normal case — Lehman College Art Gallery w885 emits expiring
    # `scontent.cdninstagram.com` image links as its event URLs, and
    # `is_signed_cdn_url` drops them, but the events still keep
    # `https://lehmangallery.org`.
    #
    # ~7% of recent crawls carry no leading URL line (Instagram/picnob bundles
    # and API source plugins build their own markdown header), so `source_url` is
    # None there and that safety net is absent. Fall back to the website's own
    # crawl URL, but ONLY for events that would otherwise have none — appending
    # it unconditionally would staple a raw JSON/API endpoint onto every event of
    # sites like the SAPO Socrata feed.
    if not source_url and website_id and any(not e.get('urls') for e in events):
        cursor.execute(
            "SELECT url FROM website_urls WHERE website_id = %s "
            "ORDER BY sort_order, id LIMIT 1", (website_id,)
        )
        row = cursor.fetchone()
        fallback_url = (row[0] if row and not isinstance(row, dict) else
                        (row['url'] if row else None)) or ''
        if not fallback_url:
            cursor.execute("SELECT base_url FROM websites WHERE id = %s", (website_id,))
            row = cursor.fetchone()
            fallback_url = (row[0] if row and not isinstance(row, dict) else
                            (row['base_url'] if row else None)) or ''
        # Templated multi-date URLs ({{date+3}}) and non-http endpoints are not
        # linkable, so they are no better than nothing.
        if fallback_url.startswith(('http://', 'https://')) and '{{' not in fallback_url:
            for event in events:
                if not event.get('urls'):
                    event['urls'] = [fallback_url]

    for event in events:
        if 'name' in event:
            event['short_name'] = create_short_name(event['name'])
        # Drop a locative sentence that belongs to a SIBLING record on the same
        # listing page (see strip_contradicting_locative above).
        cleaned = strip_contradicting_locative(
            event.get('description'), event.get('location'))
        if cleaned != event.get('description'):
            print(f"    - Dropped contradicting venue sentence from "
                  f"{event.get('name', '?')[:60]!r} "
                  f"(location_name: {event.get('location')})")
            event['description'] = cleaned

    # A re-processed crawl_result REPLACES its rows; it does not add to them.
    #
    # `db.create_crawl_result` is `ON DUPLICATE KEY UPDATE` on
    # `unique_run_file (crawl_run_id, filename)`, so re-crawling a website on a
    # day it has already been crawled REUSES the same `crawl_results` row —
    # `crawled_content`, `extracted_content`, `event_count` and `merged_at` are
    # all overwritten in place (see the `merged_at = NULL` note in
    # `db.update_crawl_result`). This insert loop was the one thing that did not
    # follow, so the second pass's crawl_events piled on top of the first's.
    #
    # w1981 Bronx Council on the Arts, cr-113663: 17 crawl_events written at
    # 2026-08-14 06:53:48, then the site was re-crawled at 09:24:01 and 21 more
    # written at 09:24:38 — 38 rows, 23 distinct names, from two Gemini runs over
    # the same page. It was never a chunked-extraction double-emit; the
    # `extracted_content` still holds a single clean 26-record extraction.
    # 237 crawl_results since 2026-07-15 carry rows spanning more than one pass,
    # 223 of them with duplicated (name, url) pairs.
    #
    # `event_sources.crawl_event_id` is ON DELETE CASCADE, so this drops the
    # superseded pass's source links too — which is the point: the merge that
    # follows re-links every event the new pass still lists, and an event the new
    # pass dropped is exactly what the archival guards exist to judge. The delete
    # is deliberately skipped when the new pass produced nothing to write, so a
    # re-crawl that extracts zero events can never strip a crawl_result bare.
    if events:
        cursor.execute(
            "DELETE FROM crawl_events WHERE crawl_result_id = %s", (crawl_result_id,)
        )
        superseded = cursor.rowcount or 0
        if superseded:
            print(f"    - Replaced {superseded} crawl_events from an earlier pass "
                  f"over crawl_result {crawl_result_id}")

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
                except Exception as e:
                    print(f"    - Warning: failed to insert occurrence {occ!r} for crawl_event {crawl_event_id}: {e}")

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


def apply_crawled_details(cursor, connection, ce_id, data, tag_context,
                          locations_map=None):
    """Apply detail-crawl data to a crawl_event row.

    Updates description, emoji, location, sublocation, occurrences, and tags
    in crawl_events/crawl_event_occurrences/crawl_event_tags.

    Args:
        cursor: DB cursor
        connection: DB connection
        ce_id: crawl_event ID
        data: dict from extract_single_event() with description, hashtags, emoji, etc.
        tag_context: tuple of (tag_rules, ancestor_map, root_tags, disambiguation_rules)
        locations_map: optional map from build_locations_map(). When the detail
            page supplies a NEW location/sublocation we must re-run location
            matching on it — the listing-page string that produced the stored
            location_id is being replaced, and leaving the id behind stranded
            events at NULL even though the new name resolves cleanly.
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

    # Process emoji. Only overwrite the existing emoji when the detail
    # extraction actually produced one — single-event extraction frequently
    # returns an empty emoji, and blindly writing NULL here wiped the emoji the
    # listing extraction / venue fallback had already set, leaving the merged
    # event blank on the map.
    emoji = data.get('emoji', '')
    first_emoji = find_first_emoji(emoji) if emoji else None
    if first_emoji and first_emoji in BLOCKED_EMOJI:
        first_emoji = None

    # Update crawl_events row
    update_fields = ["description = %s"]
    update_values = [data['description']]
    if first_emoji:
        update_fields.append("emoji = %s")
        update_values.append(first_emoji)

    if data.get('location'):
        update_fields.append("location_name = %s")
        update_values.append(data['location'])
    if data.get('sublocation'):
        update_fields.append("sublocation = %s")
        update_values.append(data['sublocation'])

    # Re-resolve location_id whenever the detail page replaced the location text.
    # Only write it when the new text actually matches something — a detail page
    # naming an unknown venue must not blank out an id the listing crawl earned.
    if locations_map and (data.get('location') or data.get('sublocation')):
        cursor.execute(
            "SELECT ce.crawl_result_id, cr.website_id "
            "FROM crawl_events ce "
            "JOIN crawl_results cr ON cr.id = ce.crawl_result_id "
            "WHERE ce.id = %s",
            (ce_id,),
        )
        row = cursor.fetchone()
        ce_website_id = row[1] if row else None
        location_info = get_location_id(
            (data.get('location') or '').strip(),
            (data.get('sublocation') or '').strip(),
            '',
            (data.get('name') or '').strip(),
            locations_map,
            website_id=ce_website_id,
        )
        if location_info and location_info.get('id'):
            update_fields.append("location_id = %s")
            update_values.append(location_info['id'])

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

            # Build the surviving rows BEFORE touching the existing ones.
            # The DELETE below must not fire until we know at least one detail
            # occurrence survives date filtering: when a detail page lists only
            # past dates (a stale page, or one that reports a film's release
            # date / the wrong year instead of showtimes), deleting first left
            # the event with ZERO occurrences and destroyed the correct
            # listing-derived date. Measured 2026-07-27: ~48% of that run's
            # undated events came from this. Each dropped occurrence is still
            # logged as an `end_in_past` rejection either way.
            surviving = []
            for occ in data['occurrences']:
                start_date = occ.get('start_date')
                end_date = occ.get('end_date')
                parsed_end = None
                if end_date:
                    try:
                        parsed_end = datetime.strptime(str(end_date), '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        end_date = None

                if not start_date:
                    # Open-ended run ("Through Aug 22") — mirror filter_by_date:
                    # an occurrence with a live end_date and no start_date is a
                    # show that is running NOW, so today is its start. Without
                    # this the row was skipped outright and the exhibition lost
                    # its only occurrence. An occurrence with neither usable
                    # date is still dropped.
                    if not parsed_end:
                        continue
                    if parsed_end < today:
                        log_rejection(
                            cursor, cr_id, ws_id,
                            rejection_type='end_in_past', stage='detail_crawl',
                            event_name=data.get('name'),
                            event_url=data.get('url'),
                            start_date=None, end_date=end_date,
                            details=f'crawl_event_id={ce_id} (open-ended run)',
                        )
                        continue
                    parsed_start = today
                    start_date = today.strftime('%Y-%m-%d')
                else:
                    try:
                        parsed_start = datetime.strptime(str(start_date), '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        continue

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
                        cursor, cr_id, ws_id,
                        rejection_type='end_in_past', stage='detail_crawl',
                        event_name=data.get('name'),
                        event_url=data.get('url'),
                        start_date=start_date, end_date=end_date,
                        details=f'crawl_event_id={ce_id}',
                    )
                    continue

                # Mirror group_event_occurrences: collapse end_date when it
                # equals start_date so the merger's dedup matches the
                # listing-crawl rows (which use NULL for single-day events).
                if parsed_end and parsed_end == parsed_start:
                    end_date = None

                surviving.append((
                    start_date, _standardize_time(occ.get('start_time')),
                    end_date, _standardize_time(occ.get('end_time')),
                ))

            # Only replace when the detail crawl actually produced usable dates.
            # If nothing survived, keep whatever the listing page gave us.
            if surviving:
                cursor.execute(
                    "DELETE FROM crawl_event_occurrences WHERE crawl_event_id = %s",
                    (ce_id,),
                )
                for sort_order, (s_date, s_time, e_date, e_time) in enumerate(surviving):
                    cursor.execute(
                        "INSERT INTO crawl_event_occurrences "
                        "(crawl_event_id, start_date, start_time, end_date, end_time, sort_order) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (ce_id, s_date, s_time, e_date, e_time, sort_order),
                    )

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


def _kill_crawl_browsers():
    """Force-kill crawl4ai's chromium processes to unblock a wedged browser.

    A single wedged page can hang Playwright's transport thread at the C level,
    where ``asyncio.wait_for``/task cancellation cannot interrupt it — and the
    browser instance is shared across the batch, so every subsequent ``arun``
    on it also hangs (the Step 5 deadlock). SIGKILL'ing the browser process is
    the only reliable way to make those wedged awaits raise and unblock.

    Matched by the ``playwright_chromiumdev_profile`` user-data-dir so the
    standalone Playwright MCP browser (run with ``--isolated``, a different
    profile) is left untouched.
    """
    try:
        subprocess.run(
            ["pkill", "-9", "-f", "playwright_chromiumdev_profile"],
            timeout=10, check=False,
        )
    except Exception as e:
        print(f"    (browser kill failed: {e})")


@asynccontextmanager
async def managed_crawler(browser_config, startup_timeout=90, teardown_timeout=30):
    """`AsyncWebCrawler` context with bounded startup and teardown.

    The in-loop crawl watchdogs (Steps 2 & 5) guard the worker ``gather`` but
    NOT the ``async with AsyncWebCrawler`` boundary itself. A wedged browser can
    hang ``__aenter__`` (startup) or — after a watchdog SIGKILLs it — ``__aexit__``
    (crawl4ai's ``close()`` awaiting a now-dead browser), leaving the step parked
    at 0% CPU with no coverage. Unlike a page wedge inside Playwright's C-level
    transport, start/close are crawl4ai coroutines awaiting their own RPCs, so an
    ``asyncio.wait_for`` over them DOES cancel; on timeout we also SIGKILL the
    chromium so the wedged await raises and teardown completes.
    """
    from crawl4ai import AsyncWebCrawler
    wc = AsyncWebCrawler(config=browser_config)
    try:
        await asyncio.wait_for(wc.__aenter__(), timeout=startup_timeout)
    except Exception as e:
        print(f"    ⚠️ browser startup failed/timed out ({type(e).__name__}); killing chromium")
        _kill_crawl_browsers()
        raise
    try:
        yield wc
    finally:
        try:
            await asyncio.wait_for(wc.__aexit__(None, None, None), timeout=teardown_timeout)
        except Exception as e:
            print(f"    ⚠️ browser teardown failed/timed out ({type(e).__name__}); killing chromium")
            _kill_crawl_browsers()


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
    import extractor  # Local import to avoid circular dependency with extractor→processor

    print(f"\n  Crawling details for {len(candidates)} event(s) with missing descriptions...")

    # Load per-website crawl + browser settings
    website_ids = {ws_id for _, _, _, ws_id in candidates}
    website_settings = db.get_website_crawl_settings(cursor, website_ids)

    # Load tag processing context
    tag_context = load_tag_context(cursor)

    # Location map for re-resolving location_id when a detail page supplies a
    # different (usually cleaner) venue name than the listing page did.
    locations_map = build_locations_map(cursor)

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

    # Stall detection: each completed crawl bumps the heartbeat. A watchdog
    # task aborts the step if no progress is made for STALL_TIMEOUT seconds,
    # so a systemic hang (e.g. a wedged browser) fails fast instead of sitting
    # idle for hours. Individual hung pages are already bounded by the
    # per-crawl timeout in crawler.crawl_event_url(); this is the safety net
    # for failures that escape it.
    STALL_TIMEOUT = 300  # 5 minutes with zero progress => kill browser & abort
    EXTRACT_TIMEOUT = 120  # hard ceiling on a single Gemini extract call
    heartbeat = {'last': time.monotonic(), 'done': 0}
    total_candidates = len(candidates)

    async def process_website(web_crawler, ws_id):
        """Process all events for one website sequentially.

        Appends successful extractions to the shared ``results`` list as they
        complete (rather than returning at the end) so a watchdog abort keeps
        all work finished before the stall.
        """
        crawl_config = crawl_configs.get(ws_id, crawler.build_event_crawl_config({}))
        # The site's own extraction notes steer the detail prompt exactly as
        # they steer the listing prompt. Skipping them here let a per-site
        # directive win on the listing pass and then get undone by this one.
        site_notes = website_settings.get(ws_id, {}).get('notes', '') or ''
        for ce_id, name, url, _ in events_by_website[ws_id]:
            async with semaphore:
                attempted_ids.append(ce_id)
                content = await crawler.crawl_event_url(web_crawler, url, crawl_config)
                heartbeat['last'] = time.monotonic()
                heartbeat['done'] += 1
                if not content:
                    continue
                try:
                    data = await asyncio.wait_for(
                        extractor.extract_single_event(
                            name, content, notes=site_notes, url=url),
                        timeout=EXTRACT_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    print(f"    Extract timed out after {EXTRACT_TIMEOUT}s for {name}")
                    continue
                if data:
                    results.append((ce_id, name, data))

    async def watchdog(gather_task):
        """Abort the detail crawl if no progress is made for STALL_TIMEOUT.

        Cancelling the gather alone cannot unblock a wedged Playwright browser
        (the awaits are stuck below the asyncio layer), so we also SIGKILL the
        crawl4ai chromium — that forces the wedged ``arun`` awaits to raise and
        lets ``await gather_task`` actually return.
        """
        while not gather_task.done():
            await asyncio.sleep(30)
            idle = time.monotonic() - heartbeat['last']
            if idle > STALL_TIMEOUT and not gather_task.done():
                print(
                    f"  ⚠️ WATCHDOG: detail crawl stalled — no progress for "
                    f"{int(idle)}s ({heartbeat['done']}/{total_candidates} crawled). "
                    f"Killing wedged browser and aborting Step 5 with partial results."
                )
                gather_task.cancel()
                _kill_crawl_browsers()
                return

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
        try:
            async with managed_crawler(browser_config) as web_crawler:
                tasks = [process_website(web_crawler, ws_id) for ws_id in ws_ids]
                gather_task = asyncio.gather(*tasks, return_exceptions=True)
                watchdog_task = asyncio.create_task(watchdog(gather_task))
                try:
                    await gather_task
                except asyncio.CancelledError:
                    # Watchdog aborted a stalled batch; keep whatever finished
                    # (workers append to `results` as they go).
                    print("  Detail crawl batch aborted; continuing with partial results.")
                finally:
                    watchdog_task.cancel()
        except Exception as e:
            # managed_crawler bounds startup/teardown (and SIGKILLs a wedged
            # browser); this catches a re-raised startup failure so remaining
            # batches still run.
            print(f"  Detail crawl batch error ({type(e).__name__}: {e}); continuing with remaining batches.")

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
        apply_crawled_details(cursor, connection, ce_id, data, tag_context,
                              locations_map=locations_map)
        enriched += 1
        location_info = f" @ {data['location']}" if data.get('location') else ""
        print(f"    + {name}{location_info}: {data['description'][:80]}...")

    print(f"  Detail-crawled {enriched}/{len(candidates)} events")
    return enriched
