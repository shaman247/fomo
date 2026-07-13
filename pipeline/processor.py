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
import time
import json
from contextlib import asynccontextmanager
import re

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
    """
    start_date_str = (row_dict.get('start_date') or '').strip()
    end_date_str = (row_dict.get('end_date') or '').strip()

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
    r'\bcloses?\s+(early|today|tonight|at\s+\d|\d)',
    r'^\s*no\s+[\w\s]*\b(program|programming|class|classes|session|service|meeting)\b[\w\s]*\b(today|tonight|this week)\b',
    # Rentals / venue marketing (selling the space, not hosting an event).
    # NOTE: a bare "RENTAL:" prefix is NOT auto-dropped — venues use it as an
    # internal booking label on public events too (rented-out dance parties,
    # comedy shows). Only match the rental *listing itself* ("Space Rental",
    # "Point Rental"); leave bare-prefix cases to editorial review.
    r'\b(venue|space|room|hall|studio|facility|point|field|court|table)\s+rental\b',
    r'\bavailable for (booking|rent|hire|private|your)\b',
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

# Bare generic single-word names ("Music", "Program", "TBD") carry no event
# information; combined with a missing description they are placeholder rows the
# extractor should never have emitted. Only fires when the description is empty
# (a real event reaching here virtually always has a description), so a richly
# described event that happens to be titled "Music" is never dropped.
_BARE_GENERIC_NAME_RE = re.compile(
    r'(?:music|events?|programs?|performances?|shows?|class(?:es)?|workshops?|'
    r'sessions?|meetings?|activit(?:y|ies)|general|misc(?:ellaneous)?|untitled|'
    r'placeholder|n/?a|none|tba|tbd)',
    re.IGNORECASE)

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
_HOLIDAY_MARKER_NAME_RE = re.compile(
    r"^\s*(?:new\s+year'?s?(?:\s+(?:eve|day))?|"
    r"martin\s+luther\s+king(?:\s+jr\.?)?(?:\s+day)?|mlk(?:\s+jr\.?)?(?:\s+day)?|"
    r"presidents?'?\s+day|washington'?s?\s+birthday|lincoln'?s?\s+birthday|"
    r"memorial\s+day|juneteenth|independence\s+day|fourth\s+of\s+july|july\s+4(?:th)?|"
    r"labor\s+day|columbus\s+day|indigenous\s+peoples'?\s+day|veterans?\s+day|"
    r"thanksgiving(?:\s+day)?|christmas(?:\s+eve|\s+day)?|halloween|easter(?:\s+sunday)?)"
    r"\s*(?:\(?observed\)?)?\s*(?:\d{4})?\s*$", re.IGNORECASE)
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


def is_obvious_non_event(name, description=None):
    """Return True if the event is an unmistakable non-event.

    Covers closures, calls for submissions/grants, venue rentals, season-pass
    listings, cinema showtime placeholders, SEO spam, fundraising campaigns,
    submission-call contests, festival info-booth listings, childcare-amenity
    listings, senior-center congregate-meal menus, registration-window
    announcements, and bare generic placeholder names — the kinds of rows that
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
    if not description.strip() and _BARE_GENERIC_NAME_RE.fullmatch(name.strip()):
        return True
    if description:
        if (_SUBMISSION_CONTEST_NAME_RE.search(name)
                and not _ATTENDABLE_CONTEST_NAME_RE.search(name)
                and _SUBMISSION_CALL_DESC_RE.search(description)):
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
        if (_DRINK_PROMO_NAME_RE.search(name)
                and _PROMO_SPECIAL_DESC_RE.search(description)
                and not _PROMO_ATTENDABLE_VETO_RE.search(name + ' ' + description)):
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
_SENTINEL_TIMES = frozenset({
    '', 'allday', 'allday/varies', 'varioustimes', 'multipletimes', 'tba', 'tbd',
    'none', 'close', 'closing', 'late', 'tbc', 'ongoing', 'sundown', 'sunrise',
    'sunset', 'dusk', 'dawn',
})


def _canonical_time(hour, minute, is_pm):
    """Build a canonical time string from a 12-hour hour (1-12), minute, and AM/PM."""
    suffix = 'pm' if is_pm else 'am'
    return f'{hour}{suffix}' if minute == 0 else f'{hour}:{minute:02d}{suffix}'


def _standardize_time(time_str):
    """Canonicalize a time string to compact lowercase 12-hour form.

    Examples:
        '6:30 PM' -> '6:30pm'
        '6:00pm'  -> '6pm'
        '17:38'   -> '5:38pm'
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

    def find_matching_group_key(event_name, row_loc, grouped_events, normalized_group_keys):
        normalized_event = normalize_name_for_grouping(event_name)
        for existing_key, existing in grouped_events.items():
            if not locations_compatible(row_loc, loc_key(existing)):
                continue
            normalized_existing = normalized_group_keys[existing_key]
            if event_name == existing_key or normalized_event == normalized_existing:
                return existing_key
            if len(normalized_event) >= 5 and len(normalized_existing) >= 5:
                if normalized_event in normalized_existing or normalized_existing in normalized_event:
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

        group_key = find_matching_group_key(event_name, loc_key(row_dict), grouped_events, normalized_group_keys)

        if group_key not in grouped_events:
            base_event = {k: v for k, v in row_dict.items()
                         if k not in ['start_date', 'start_time', 'end_date', 'end_time', 'sublocation', 'url']}
            base_event['occurrences'] = []

            sublocation = (row_dict.get('sublocation') or '').strip()
            if sublocation and sublocation.upper() != 'N/A':
                base_event['sublocation'] = sublocation

            # Prefer event-specific URL over source_url (which is often generic)
            urls = []
            url = (row_dict.get('url') or '').strip()
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

            url = (row_dict.get('url') or '').strip()
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

# Leftover tokens that don't distinguish one venue from another, so a mismatch
# on them shouldn't block the fuzzy token-overlap tripwire: corporate/legal
# suffixes (Inc vs Corp for the same business) and grammatical connectors.
_DROPPABLE_LEFTOVER_TOKENS = {
    'inc', 'corp', 'corporation', 'incorporated', 'llc', 'ltd', 'co', 'lp',
    'plc', 'company', 'the', 'and', 'of', 'at', 'for', 'a', 'an', 'in', 'on',
}


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


def _normalize_location_name(name):
    """Normalizes a location name for matching."""
    if not name:
        return ""

    # Strip diacritics so "Café" matches "Cafe", "Jardín" matches "Jardin".
    name = ''.join(
        c for c in unicodedata.normalize('NFKD', name)
        if not unicodedata.combining(c)
    )
    # Normalize "&" and "+" to "and" so "Art & Architecture" matches "Art and Architecture".
    name = re.sub(r'\s*[&+]\s*', ' and ', name)

    original_lower = name.lower()
    has_dash_before_borough = any(
        f'- {b}' in original_lower or f'_{b}' in original_lower
        for b in city_config.borough_tokens()
    )

    normalized = re.sub(r'[^\w\s]', '', original_lower)

    if normalized in ['virtual', 'online', 'livestream', 'private residence',
                      'various locations', 'zoom', 'unknown venue']:
        return ""
    if len(normalized) > 15 and normalized.startswith('the '):
        normalized = normalized[4:]

    # Strip trailing state abbreviations/names (e.g., "Brooklyn, NY" -> "brooklyn")
    state_suffixes = city_config.state_suffixes()
    for ss in state_suffixes:
        if normalized.endswith(ss) and len(normalized) > len(ss) + 1:
            stripped = normalized[:-len(ss)].strip()
            # See GENERIC_LOCATION_WORDS: don't collapse to a bare generic token.
            if ' ' not in stripped and stripped in GENERIC_LOCATION_WORDS:
                break
            normalized = stripped
            break

    suffixes = city_config.city_area_tokens()
    if normalized in suffixes:
        return ""

    if not has_dash_before_borough:
        for suffix in suffixes:
            if normalized.endswith(f' {suffix}') and len(normalized) > len(suffix) + 2:
                stripped = normalized[:-len(f' {suffix}')].strip()
                # Don't collapse a venue to a bare generic token (e.g.
                # "Gallery Brooklyn" -> "gallery"), which would then exact-match
                # any unrelated event whose location is just that word. Keep the
                # borough so the name stays specific.
                if ' ' not in stripped and stripped in GENERIC_LOCATION_WORDS:
                    break
                normalized = stripped
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


def sublocation_redundant_with_address(sublocation, location_address):
    """True when sublocation is just the venue address (safe to clear).

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
    sub = _extract_street_address_loose(sublocation)
    addr = _extract_street_address_loose(location_address)
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
            if a_lo and a_hi and s_num in (a_lo, a_hi):
                return True
            s_lo, s_hi = _range_endpoints(sublocation)
            if s_lo and s_hi and a_num in (s_lo, s_hi):
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
      3.5. Single-venue website authority (a single-venue website's own venue wins
           over arbitrary same-brand prefix/fuzzy matches when the name is generic)
      4. Prefix match (location name starts with known name, ≥PREFIX_MATCH_COVERAGE to avoid generics)
      5. Fuzzy match (Levenshtein ratio ≥ FUZZY_MATCH_THRESHOLD)
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
    raw_geo = ' '.join(p for p in (location_name_raw, sublocation_name_raw) if p)

    def conflicts(info):
        """True if this candidate's state conflicts with a city named in raw_geo."""
        return _region_conflict(raw_geo, info, city_states)

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

    # Step 2: Exact matches in global tiers (names, alternate_names, short_names).
    # The 'names' tier is the location's own primary name (high confidence — a
    # city token there is usually part of the name). The alternate_names and
    # short_names tiers are looser, so a same-named place in a conflicting
    # municipality is rejected via the region-conflict guard (e.g. the global
    # "Columbus Park" alt of Manhattan's park vs a "Columbus Park, Hoboken" event).
    for tier_name in ['names', 'alternate_names', 'short_names']:
        tier = locations_map.get(tier_name, {})
        for key in search_keys:
            if key in tier:
                cand = get_first(tier[key])
                if tier_name != 'names' and conflicts(cand):
                    continue
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
    if website_id and normalized_loc and len(normalized_loc) >= 3:
        linked = locations_map.get('website_linked', {}).get(website_id, [])
        if len(linked) == 1:
            v_name = _normalize_location_name(linked[0].get('name') or '')
            if v_name and (
                normalized_loc in v_name or v_name in normalized_loc
                or _calculate_levenshtein_ratio(normalized_loc, v_name) >= 0.6
            ):
                return make_result(linked[0])

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
        if key in GENERIC_LOCATION_WORDS:
            continue
        if len(key) >= 5:
            for tier_name in ('names', 'alternate_names'):
                for loc_key, match in locations_map.get(tier_name, {}).items():
                    if loc_key.startswith(key + '(') or (
                        loc_key.startswith(key + ' ') and len(key) / len(loc_key) >= PREFIX_MATCH_COVERAGE
                    ):
                        cand = get_first(match)
                        if conflicts(cand):
                            continue
                        return make_result(cand)

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

    # (The former single-venue brand-name fallback is now Step 3.5, which runs
    # before prefix/fuzzy so the authoritative venue wins over arbitrary
    # same-brand prefix matches.)

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

        # URL grounding check: if the AI returned a URL that doesn't appear in
        # the crawled content, it's likely a hallucinated event. Log and skip.
        event_url = (row_dict.get('url') or '').strip()
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

                cursor.execute(
                    "INSERT INTO crawl_event_occurrences "
                    "(crawl_event_id, start_date, start_time, end_date, end_time, sort_order) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (ce_id, start_date, _standardize_time(occ.get('start_time')),
                     end_date, _standardize_time(occ.get('end_time')), sort_order),
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
                        extractor.extract_single_event(name, content),
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
        apply_crawled_details(cursor, connection, ce_id, data, tag_context)
        enriched += 1
        location_info = f" @ {data['location']}" if data.get('location') else ""
        print(f"    + {name}{location_info}: {data['description'][:80]}...")

    print(f"  Detail-crawled {enriched}/{len(candidates)} events")
    return enriched
