"""
Event deduplication and merging module.

Merges crawl_events into the final events table with deduplication.
Archives outdated events that are no longer found in recent crawls.
Logs all changes to the edits table for sync tracking.
"""

import re
import sys
import time
import unicodedata
from collections import Counter
from datetime import date as date_type, datetime, timedelta
from math import ceil
from pathlib import Path

import mysql.connector

import db
from constants import get_active_date_window

# Maximum retries for deadlock errors
DEADLOCK_MAX_RETRIES = 3
DEADLOCK_RETRY_DELAY = 2  # seconds


def _retry_on_deadlock(func, *args, max_retries=DEADLOCK_MAX_RETRIES, **kwargs):
    """Retry a function on MySQL deadlock (error 1213).

    Deadlocks can occur when multiple pipeline processes run concurrently.
    InnoDB rolls back the deadlocked statement, so retrying is safe.
    """
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except mysql.connector.errors.DatabaseError as e:
            if e.errno == 1213 and attempt < max_retries:
                print(f"    Deadlock detected, retrying ({attempt + 1}/{max_retries})...")
                time.sleep(DEADLOCK_RETRY_DELAY * (attempt + 1))
            else:
                raise

# Add database module to path for edit logger
sys.path.insert(0, str(Path(__file__).parent.parent / 'database'))

try:
    from edit_logger import EditLogger
except ImportError:
    EditLogger = None


# Cinema/screening format & accessibility tags. When a parenthetical group is
# made up ENTIRELY of these, it carries no event identity (it marks how a film
# is screened, not which film). Left in, the shared tokens inflate word-overlap
# and make DIFFERENT films match (e.g. "Pressure (Open Cap/Eng Sub)" ~
# "Star Wars … (Open Cap/Eng Sub)" via asymmetric-containment).
_FORMAT_TAGS = {
    'open', 'cap', 'caption', 'captioned', 'captions', 'oc',
    'eng', 'sub', 'subs', 'subbed', 'subtitle', 'subtitled', 'subtitles',
    'cc', 'ad', 'ov', 'omu', 'dub', 'dubbed', 'dubs',
    '2d', '3d', 'imax', 'dbox', '4dx', 'hd', 'ddh', 'das',
}


def _strip_format_parentheticals(name):
    """Drop ()/[] groups whose alpha tokens are all screening-format tags."""
    def repl(match):
        inner = match.group(1) if match.group(1) is not None else match.group(2)
        tokens = [t for t in re.split(r'[^a-z0-9]+', inner.lower()) if t]
        alpha = [t for t in tokens if not t.isdigit()]
        if alpha and all(t in _FORMAT_TAGS for t in alpha):
            return ' '
        return match.group(0)
    return re.sub(r'\(([^()]*)\)|\[([^\[\]]*)\]', repl, name)


def normalize_name_for_dedup(name):
    """Remove accents, punctuation, underscores, and whitespace; convert to lowercase."""
    name = _strip_format_parentheticals(name)
    # Normalize unicode to remove accents (é -> e, etc.)
    nfkd = unicodedata.normalize('NFKD', name)
    ascii_name = ''.join(c for c in nfkd if not unicodedata.combining(c))

    no_underscores = ascii_name.replace('_', '')
    # Replace punctuation with spaces (not just remove) to avoid word concatenation
    # e.g., "Alice/Bob" should become "Alice Bob", not "AliceBob"
    no_punct = re.sub(r'[^\w\s]', ' ', no_underscores.strip().lower())
    normalized = re.sub(r'\s+', ' ', no_punct).strip()
    return normalized


def normalize_time_for_dedup(time_str):
    """Normalize a start_time string for dedup comparison.

    Source feeds (notably nyc.gov) emit the same time in inconsistent formats
    across crawls ("11:30 AM" vs "11:30am", "1:00 PM" vs "1pm"). Without
    normalization the same-name dedup safety net misses these as duplicates.

    '11:30 AM' / '11:30am' -> '1130am'
    '1:00 PM'  / '1pm'     -> '1pm'
    None / ''              -> ''
    """
    if not time_str:
        return ''
    s = time_str.strip().lower().replace(' ', '').replace('.', '')
    # Drop ':00' minute suffix before am/pm so '1:00pm' == '1pm'
    s = re.sub(r':00(am|pm)$', r'\1', s)
    return s


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


# Stop words that don't contribute to event identity.
_STOP_WORDS = frozenset({'the', 'and', 'for', 'with', 'from', 'into', 'your'})


def _is_year(w):
    """Check if word is a 4-digit year (2000-2099)."""
    return len(w) == 4 and w.isdigit() and w.startswith('20')


def _coord_key(lat, lng):
    """Build the rounded (lat, lng) tuple used as a coordinate index key."""
    return (round(float(lat), 5), round(float(lng), 5))


def get_significant_words(name, stem=False):
    """Get significant words (3+ chars) from normalized name, excluding stop words and years."""
    norm = normalize_name_for_dedup(name)
    words = norm.split()

    result = set(w for w in words if len(w) >= 3 and w not in _STOP_WORDS and not _is_year(w))
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

    # Remove subtitles after colon (but keep if main title is too short or a
    # generic delivery/category word). "Online: <subtitle>" must not collapse
    # to "Online", because the substring check downstream would then match any
    # title containing the word "online".
    GENERIC_PREFIXES = {'online', 'virtual', 'zoom', 'free', 'webinar', 'workshop', 'class', 'live'}
    if ':' in result:
        parts = result.split(':', 1)
        main_title = parts[0].strip()
        if len(main_title) >= 5 and main_title.lower() not in GENERIC_PREFIXES:
            result = main_title

    return result.strip()


# Lineup markers ("ft:", "feat:", etc.) introduce a per-occurrence cast rather
# than a distinct sub-event, so a colon right after one is NOT a subtitle break.
_LINEUP_MARKERS = {'ft', 'feat', 'featuring', 'w', 'with', 'presents', 'present'}


def _ordered_significant_words(name):
    """Like get_significant_words but preserves order (for prefix comparison)."""
    words = normalize_name_for_dedup(name).split()
    return [
        w for w in words
        if len(w) >= 3 and w not in _STOP_WORDS
        and not _is_year(w)
    ]


def _split_on_subtitle_colon(name):
    """Return (head, subtitle) split on a genuine "Head: Subtitle" colon, or None.

    Only a *clean top-level* colon counts. We skip colons that are:
    - inside parentheses/brackets/quotes (e.g. "(2hr:Harlem:Lenox)")
    - part of a clock time (digit:digit, e.g. "10:00am")
    - immediately preceded by a lineup marker (e.g. "ft:", "feat:")
    """
    depth = 0
    openers = {'(': ')', '[': ']', '{': '}'}
    closers = {')', ']', '}'}
    for i, ch in enumerate(name):
        if ch in openers:
            depth += 1
        elif ch in closers:
            depth = max(0, depth - 1)
        elif ch == ':' and depth == 0:
            prev_char = name[i - 1] if i > 0 else ''
            next_char = name[i + 1] if i + 1 < len(name) else ''
            # Clock time like 10:00 — digit on both immediate sides.
            if prev_char.isdigit() and next_char.isdigit():
                continue
            head, subtitle = name[:i].strip(), name[i + 1:].strip()
            if not head or not subtitle:
                return None
            last_word = re.sub(r'[^a-z]', '', head.split()[-1].lower()) if head.split() else ''
            if last_word in _LINEUP_MARKERS:
                continue
            return head, subtitle
    return None


def _bare_name_vs_distinct_subtitle(bare, specific):
    """Detect a bare/umbrella name being loosely matched against a more specific
    "Head: Subtitle" sibling that it should NOT merge with.

    Fires only when ALL of the following hold:
    - `specific` has a clean subtitle colon and `bare` has no such colon
    - `bare` matches the head LOOSELY (substring or word-subset) but NOT exactly
    - `bare` shares no significant words with the subtitle

    This blocks a short umbrella name (e.g. "DanceAfrica") from absorbing a
    distinct sub-event ("BAM DanceAfrica 2026: Visual Art | Sanaa Gateja") whose
    subtitle carries the distinguishing content. It deliberately leaves the
    common legitimate case intact — when the bare name EQUALS the head (e.g.
    "The Monsters" vs "The Monsters: a Sibling Love Story") it is the same event.
    """
    split = _split_on_subtitle_colon(specific)
    if split is None or _split_on_subtitle_colon(bare) is not None:
        return False
    head, subtitle = split

    # The subtitle must carry real distinguishing content (>=2 significant words)
    # to count as a distinct sub-event. A one-word tagline ("Constance: A
    # Confession") is just a fuller title of the same event, so don't split it —
    # that structure is otherwise indistinguishable from "<presenter> <core>:
    # <sub-event>" by name alone, and over-firing would create duplicate events.
    if len(get_significant_words(subtitle)) < 2:
        return False

    nbare = normalize_name_for_dedup(bare)
    nhead = normalize_name_for_dedup(head)
    # Bare name equal to the head => same event, not a false positive.
    if nbare == nhead:
        return False

    # If the bare name is a leading prefix of the full specific name, the
    # specific name is just a longer/fuller title of the SAME event (e.g.
    # "MOCA TALKS with Madelyn Postman" vs "MOCA TALKS with Madelyn Postman
    # Staring into the Sun: Stories ..."), not an umbrella absorbing a distinct
    # sub-event. The umbrella case has the shared token embedded mid-name
    # ("DanceAfrica" inside "BAM DanceAfrica 2026: ...").
    bare_ordered = _ordered_significant_words(bare)
    specific_ordered = _ordered_significant_words(specific)
    if len(bare_ordered) >= 2 and specific_ordered[:len(bare_ordered)] == bare_ordered:
        return False

    bare_words = get_significant_words(bare)
    head_words = get_significant_words(head)
    loose_head_match = (
        (len(nbare) >= 5 and len(nhead) >= 5 and nbare in nhead)
        or (bare_words and head_words and bare_words.issubset(head_words))
    )
    if not loose_head_match:
        return False

    # If the bare name references the subtitle at all, it's plausibly the same
    # specific event described two ways — don't treat as a false positive.
    if bare_words & get_significant_words(subtitle):
        return False

    return True


def _series_enumeration_mismatch(norm1, norm2):
    """One normalized name carries an "N of M" series-member marker and the
    other does not.

    A bare umbrella name ("Schmigadoon") must not absorb an enumerated member
    ("Schmigadoon! Producer's Picks [3 of 4]") via loose substring matching —
    the enumeration is precisely the signal that the longer name is one item of
    a set, not a fuller title of the same event. Operates on already-normalized
    names, where "[3 of 4]" has become "3 of 4". Member-vs-member cases (both
    enumerated) are left to the existing numbered-sequence checks and to the
    schedule/dedup layers, so this only fires on the umbrella-vs-member shape.
    """
    of_re = r'\b\d+\s+of\s+\d+\b'
    return bool(re.search(of_re, norm1)) != bool(re.search(of_re, norm2))


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
    - A bare/umbrella name vs a more specific "Head: Subtitle" sibling
    """
    norm1 = normalize_name_for_dedup(name1)
    norm2 = normalize_name_for_dedup(name2)

    # Different gendered sports events (Men's vs Women's)
    # Use word boundaries to avoid false matches on substrings (e.g., "documentary" contains "men")
    has_men1 = bool(re.search(r'\bmen\b', norm1))
    has_men2 = bool(re.search(r'\bmen\b', norm2))
    has_women1 = bool(re.search(r'\bwomen\b', norm1))
    has_women2 = bool(re.search(r'\bwomen\b', norm2))
    if has_men1 != has_men2 or has_women1 != has_women2:
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

    # Different clock times incl. bare hours ("8pm" vs "10pm" vs "12am") — the
    # minute-bearing patterns above miss bare hours. Comedy clubs list the same show
    # name at multiple showtimes ("Friday: Primetime Comedy 8pm / 10pm / 12am"), which
    # are distinct ticketed events; without this they merge via stemmed-word containment.
    # Canonicalize so "8pm" == "8:00pm" (same time, different format) is NOT flagged.
    def _clock_times(norm):
        return set(
            f'{int(h)}:{mn or "00"}{ap.lower()}'
            for h, mn, ap in re.findall(r'\b(\d{1,2})(?:\s*(\d{2}))?\s*(am|pm)\b', norm, re.IGNORECASE)
        )
    ct1, ct2 = _clock_times(norm1), _clock_times(norm2)
    if ct1 and ct2 and ct1 != ct2:
        return True

    # Bare/umbrella name vs a distinct "Head: Subtitle" sibling (check both
    # orderings since the bare name may be either argument).
    if (_bare_name_vs_distinct_subtitle(name1, name2)
            or _bare_name_vs_distinct_subtitle(name2, name1)):
        return True

    # Umbrella name vs an enumerated "N of M" series member (the colon-less
    # cousin of the bare/subtitle case): "Schmigadoon" vs "Schmigadoon!
    # Producer's Picks [3 of 4]". Regression 2026-06-24.
    if _series_enumeration_mismatch(norm1, norm2):
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
                # Containment is only unsafe when the *contained* (shorter) core
                # is a generic umbrella HEAD left behind by stripping a distinct
                # subtitle (e.g. "Early Literacy: Lapsit Storytime ..." collapses
                # to the core "Early Literacy", which is then contained in "Early
                # Literacy Process Art ..." — two different programs). In that
                # case, mirror the equality-case rule: only treat them as the
                # same event when BOTH names carry subtitles AND those subtitles
                # corroborate. Distinct subtitles => distinct sub-events; a name
                # with no subtitle (a fuller title or "<core> at <venue>"
                # listing) still merges as before. Regression 2026-06-24.
                short_name = name1 if norm_core1 in norm_core2 else name2
                short_core = norm_core1 if norm_core1 in norm_core2 else norm_core2
                long_name = name2 if short_name is name1 else name1
                short_split = _split_on_subtitle_colon(short_name)
                umbrella_head = (
                    short_split is not None
                    and normalize_name_for_dedup(short_split[0]) == short_core
                    and len(get_significant_words(short_split[1])) >= 2
                )
                long_split = _split_on_subtitle_colon(long_name)
                if umbrella_head and long_split is not None:
                    short_sub = normalize_name_for_dedup(short_split[1])
                    long_sub = normalize_name_for_dedup(long_split[1])
                    if short_sub == long_sub or short_sub in long_sub or long_sub in short_sub:
                        return True  # same sub-event, fuller prefix — merge
                    # else: distinct subtitles under a shared head — do not match
                else:
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


def source_url_listing_set(cursor, cache, website_id):
    """Return the set of trimmed website_urls for a website (memoized).
    Used to detect when a candidate URL is a generic listing page so we can
    prefer event-specific detail URLs in event_urls."""
    if website_id is None:
        return set()
    if website_id not in cache:
        cursor.execute("SELECT url FROM website_urls WHERE website_id = %s", (website_id,))
        cache[website_id] = {row[0].rstrip('/') for row in cursor.fetchall()}
    return cache[website_id]


def _merge_occurrences_into_event(cursor, event_id, new_occurrences):
    """Insert new occurrences into event_occurrences, deduping by (sd, st, ed).

    Within a (start_date, end_date) bucket, a row with non-empty start_time supersedes
    one with empty start_time. Within a (start_date, start_time, end_date) key, only
    one row exists; end_time is reconciled by promoting empty → non-empty, but conflicting
    non-empty end_times resolve to the existing row (first-writer-wins). This prevents
    later sources from clobbering established occurrences when their extractor misreads
    a time (e.g. 12am → 12pm).

    Incoming start_time/end_time strings are canonicalized through
    processor._standardize_time at the DB-write boundary, so legacy data and any
    path that bypasses pipeline normalization still lands in canonical form.

    new_occurrences is an iterable of (start_date, start_time, end_date, end_time, ...).
    """
    from processor import _standardize_time
    cursor.execute(
        "SELECT start_date, start_time, end_date, end_time, COALESCE(MAX(sort_order), -1) "
        "FROM event_occurrences WHERE event_id = %s "
        "GROUP BY start_date, start_time, end_date, end_time",
        (event_id,),
    )
    existing_rows = cursor.fetchall()
    # (sd, start_time, ed) -> end_time. Legacy data may have multiple rows per key
    # (pre-tightening); we keep the first non-empty end_time we see so the new
    # merger doesn't clobber a real value with a stale empty one.
    existing_by_key = {}
    # (sd, ed) -> set of start_times for the dateless-vs-timed supersession check
    starts_by_date = {}
    for sd, st, ed, et, _so in existing_rows:
        st_s = st or ''
        et_s = et or ''
        key = (sd, st_s, ed)
        prev = existing_by_key.get(key, '')
        if not prev:
            existing_by_key[key] = et_s
        starts_by_date.setdefault((sd, ed), set()).add(st_s)
    next_sort = max((row[4] for row in existing_rows), default=-1) + 1

    for occ in new_occurrences:
        sd = occ[0]
        ed = occ[2]
        # Canonicalize at the write boundary — guarantees the dedupe key compares
        # strings in a single normalized form (e.g. '17:38' vs '5:38pm' both
        # collapse to '5:38pm').
        new_st = _standardize_time(occ[1])
        new_et = _standardize_time(occ[3])

        date_key = (sd, ed)
        existing_starts = starts_by_date.get(date_key, set())

        # Dateless incoming loses to any timed existing row at this (sd, ed).
        if not new_st and any(s for s in existing_starts):
            continue

        key = (sd, new_st, ed)
        if key in existing_by_key:
            existing_et = existing_by_key[key]
            if existing_et or not new_et:
                # Existing already has an end_time, or incoming has nothing to add.
                continue
            # Promote: existing rows for this key have empty end_time; fill them in.
            if ed is None:
                cursor.execute(
                    "UPDATE event_occurrences SET end_time = %s "
                    "WHERE event_id = %s AND start_date = %s "
                    "AND COALESCE(start_time, '') = %s "
                    "AND end_date IS NULL AND COALESCE(end_time, '') = ''",
                    (new_et, event_id, sd, new_st),
                )
            else:
                cursor.execute(
                    "UPDATE event_occurrences SET end_time = %s "
                    "WHERE event_id = %s AND start_date = %s "
                    "AND COALESCE(start_time, '') = %s "
                    "AND end_date = %s AND COALESCE(end_time, '') = ''",
                    (new_et, event_id, sd, new_st, ed),
                )
            existing_by_key[key] = new_et
            continue

        # New (sd, st, ed) key. Demote any dateless existing row at this date if
        # incoming has a start_time.
        if new_st and ('' in existing_starts):
            if ed is None:
                cursor.execute(
                    "DELETE FROM event_occurrences WHERE event_id = %s "
                    "AND start_date = %s AND (start_time IS NULL OR start_time = '') "
                    "AND end_date IS NULL",
                    (event_id, sd),
                )
            else:
                cursor.execute(
                    "DELETE FROM event_occurrences WHERE event_id = %s "
                    "AND start_date = %s AND (start_time IS NULL OR start_time = '') "
                    "AND end_date = %s",
                    (event_id, sd, ed),
                )
            existing_by_key.pop((sd, '', ed), None)
            existing_starts.discard('')

        cursor.execute(
            "INSERT INTO event_occurrences (event_id, start_date, start_time, end_date, end_time, sort_order) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (event_id, sd, new_st, ed, new_et, next_sort),
        )
        next_sort += 1
        existing_by_key[key] = new_et
        existing_starts.add(new_st)
        starts_by_date[date_key] = existing_starts


def _deduplicate_same_name_events(cursor, connection, current_date, edit_logger=None):
    """Find and merge exact-name duplicate events within the same website.

    Catches duplicates that slip through the main matching logic when AI extraction
    assigns inconsistent location info between crawls. Two events are treated as
    duplicates only when they share at least one (start_date, start_time) tuple —
    otherwise same-name events from a single website are legitimately distinct
    (e.g. SummerStage's Met Opera Summer Recital touring 5 different parks; a
    festival re-running the same program at multiple venues; weekly recurring
    library programs). Without the shared-occurrence gate, this safety net
    aggressively conflates those into a single row at the wrong venue.

    Keeps the oldest event (lowest id) and merges newer duplicates into it.

    ARCHIVED events with future occurrences also join their group, but only as
    absorb candidates — never keepers. When a site re-lists an event after its
    row was archived and the fresh extraction maps to a different location row
    (venue-mapping drift: a corrected alt-name, duplicate location rows, sibling
    venues), the main matcher's cross-location guard correctly refuses the merge
    and a new active row is created — leaving a stale archived twin that churns
    every subsequent run. Folding the archived twin into the active row also
    moves its event_sources, so the next crawl merges into the survivor instead
    of resurrecting the stale copy.

    Returns the number of duplicate events removed.
    """
    # Fetch candidate (name, website, date, time) tuples and group in Python so
    # we can apply `normalize_time_for_dedup` to start_time. Doing this in SQL
    # would require a hairy REGEXP_REPLACE; doing it in Python keeps the rule
    # alongside the helper so future format-drift can be patched in one place.
    # Active-but-suppressed events stay excluded (a human hid them; the dedupe
    # workflow owns those), but archived rows are included regardless of
    # suppression so stale twins of re-listed events get absorbed.
    cursor.execute("""
        SELECT LOWER(TRIM(e.name)) AS norm_name, e.website_id, e.id,
               eo.start_date, eo.start_time, e.location_id,
               e.archived, e.suppressed, e.location_name
        FROM events e
        JOIN event_occurrences eo ON eo.event_id = e.id
        WHERE eo.start_date >= %s
          AND (e.archived = 1 OR e.suppressed = 0)
    """, (current_date,))

    groups = {}
    event_location = {}  # event_id -> location_id (for the cross-location guard)
    event_archived = {}
    event_loc_name = {}  # event_id -> normalized extracted location_name
    for (norm_name, website_id, event_id, start_date, start_time, location_id,
         archived, _suppressed, location_name) in cursor.fetchall():
        key = (norm_name, website_id, start_date, normalize_time_for_dedup(start_time))
        groups.setdefault(key, set()).add(event_id)
        event_location[event_id] = location_id
        event_archived[event_id] = bool(archived)
        event_loc_name[event_id] = normalize_name_for_dedup(location_name) if location_name else ''

    dup_groups = [(key, sorted(ids)) for key, ids in groups.items() if len(ids) > 1]

    if not dup_groups:
        return 0

    # An event has multiple occurrences, so the same event id can appear in
    # several (name, website, date, time) groups. When duplicate rows of the
    # same name span different dates (e.g. a gallery artwork re-extracted across
    # crawls, each row covering an overlapping run of days), one event can be the
    # keeper (lowest id) in one group but a removed duplicate in another. If the
    # group where it's removed is processed first, its row is gone before the
    # group where it's the keeper runs — and `UPDATE event_sources SET event_id`
    # would then point at a deleted id, violating the FK. Resolve every id through
    # `merged_into` to its surviving keeper so merges chain transitively and the
    # keeper always exists, regardless of dict iteration order.
    merged_into = {}

    def resolve(event_id):
        while event_id in merged_into:
            event_id = merged_into[event_id]
        return event_id

    def _merge_pair_into(keep_id, remove_id):
        """Fold remove_id into keep_id: move sources/occurrences, delete the dup."""
        # Transfer event_sources that don't already exist on the keeper
        cursor.execute("""
            UPDATE event_sources SET event_id = %s
            WHERE event_id = %s
              AND crawl_event_id NOT IN (
                  SELECT crawl_event_id FROM (
                      SELECT crawl_event_id FROM event_sources WHERE event_id = %s
                  ) t
              )
        """, (keep_id, remove_id, keep_id))

        # Remove leftover sources
        cursor.execute("DELETE FROM event_sources WHERE event_id = %s", (remove_id,))

        # Merge any unique occurrences into the keeper
        cursor.execute("""
            INSERT IGNORE INTO event_occurrences
                (event_id, start_date, start_time, end_date, end_time, sort_order)
            SELECT %s, start_date, start_time, end_date, end_time, sort_order
            FROM event_occurrences WHERE event_id = %s
        """, (keep_id, remove_id))

        # Clean up the duplicate
        cursor.execute("DELETE FROM event_occurrences WHERE event_id = %s", (remove_id,))
        cursor.execute("DELETE FROM event_urls WHERE event_id = %s", (remove_id,))
        cursor.execute("DELETE FROM event_tags WHERE event_id = %s", (remove_id,))

        if edit_logger:
            cursor.execute("SELECT * FROM events WHERE id = %s", (remove_id,))
            record = cursor.fetchone()
            if record:
                col_names = [d[0] for d in cursor.description]
                edit_logger.log_delete('events', remove_id, dict(zip(col_names, record)))

        cursor.execute("DELETE FROM events WHERE id = %s", (remove_id,))
        merged_into[remove_id] = keep_id

    # Human "not a duplicate" decisions from the dedupe workflow are binding —
    # never absorb across a dismissed pair.
    cursor.execute("SELECT event_id_a, event_id_b FROM dedupe_dismissed_pairs")
    dismissed_pairs = {frozenset(row) for row in cursor.fetchall()}

    removed = 0
    for _key, ids in dup_groups:
        live = []
        for i in ids:
            r = resolve(i)
            if r not in live:
                live.append(r)
        if len(live) < 2:
            continue
        live.sort()
        active = [eid for eid in live if not event_archived.get(eid)]
        stale = [eid for eid in live if event_archived.get(eid)]
        if not active:
            continue  # nothing live to absorb into; leave archived twins alone

        # Cross-location guard: same-name/time events at DIFFERENT known
        # location_ids are distinct venues (a recurring program — Open Play,
        # Zumba, Story Time — running the same hour at multiple library/park
        # branches), not duplicates. Cluster the live events so each only merges
        # with location-compatible peers; a NULL location_id is a wildcard that
        # joins the first located cluster (the inconsistent-extraction case this
        # dedup exists to catch). Mirrors find_best_match()'s
        # `require_location_id_match` guard.
        clusters = []  # each: [keep_id (lowest), cluster_loc, [member_ids...]]
        for eid in active:  # active is id-ordered, so each cluster's first member is its keeper
            loc = event_location.get(eid)
            for cl in clusters:
                if cl[1] is None or loc is None or cl[1] == loc:
                    cl[2].append(eid)
                    if cl[1] is None and loc is not None:
                        cl[1] = loc  # pin the cluster to the first known location
                    break
            else:
                clusters.append([eid, loc, [eid]])

        for keep_id, _cluster_loc, members in clusters:
            for remove_id in members[1:]:
                _merge_pair_into(keep_id, remove_id)
                removed += 1

        # Absorb stale archived twins into a location-compatible active keeper.
        # Location compatibility is looser here than for active-active merges:
        # same location_id, NULL on either side, or the same extracted
        # location_name (the drift case — an identical venue string mapped to
        # different location rows across crawls). Twins whose extracted venue
        # strings genuinely differ (multi-branch programs sharing a time slot)
        # stay untouched.
        for dead_id in stale:
            dead_loc = event_location.get(dead_id)
            dead_loc_name = event_loc_name.get(dead_id, '')
            for cl in clusters:
                keep_id = cl[0]
                if frozenset((keep_id, dead_id)) in dismissed_pairs:
                    continue
                loc_compatible = cl[1] is None or dead_loc is None or cl[1] == dead_loc
                name_compatible = bool(dead_loc_name) and dead_loc_name == event_loc_name.get(keep_id, '')
                if not (loc_compatible or name_compatible):
                    continue
                # Deliberately no suppression propagation: suppressed=1 on an
                # archived twin almost always means "hidden as a duplicate copy"
                # (find_duplicate_events --suppress), not "this event is
                # uninteresting" — copying it would hide the live keeper.
                _merge_pair_into(keep_id, dead_id)
                removed += 1
                break

    _retry_on_deadlock(connection.commit)
    return removed


# Maximum keyword tags to keep per event after majority vote
MAX_KEYWORD_TAGS = 6


def compute_voted_tags(cursor, event_id, current_crawl_tags, curated_tag_set,
                       ancestor_map, root_tags):
    """Compute tags for an event using majority vote across crawl history.

    Tags that appear consistently across multiple crawl runs are kept;
    one-off hallucinations are dropped. Curated hierarchy tags (type='tag')
    are exempt from voting.

    Args:
        cursor: Database cursor
        event_id: The event ID to compute tags for
        current_crawl_tags: Tags from the current (not yet linked) crawl event
        curated_tag_set: Set of tag names with type='tag'
        ancestor_map: Dict mapping normalized_tag -> set of ancestor tag names
        root_tags: Set of normalized root tag names

    Returns:
        List of tag names that passed the vote
    """
    def _norm(t):
        return db.normalize_tag_key(t)

    # Count how many crawl runs produced each tag (from already-linked crawl events)
    cursor.execute("""
        SELECT cet.tag, COUNT(DISTINCT es.crawl_event_id) as crawl_count
        FROM event_sources es
        JOIN crawl_event_tags cet ON cet.crawl_event_id = es.crawl_event_id
        WHERE es.event_id = %s
        GROUP BY cet.tag
    """, (event_id,))
    tag_counts = {row[0]: row[1] for row in cursor.fetchall()}

    # Count existing crawl runs for this event
    cursor.execute(
        "SELECT COUNT(DISTINCT crawl_event_id) FROM event_sources WHERE event_id = %s",
        (event_id,)
    )
    existing_crawl_count = cursor.fetchone()[0]

    # Include current crawl's tags (not yet in event_sources)
    for tag in current_crawl_tags:
        if tag:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    total_crawls = existing_crawl_count + 1

    # If only 1 crawl total, keep all tags (no history to vote on)
    if total_crawls <= 1:
        return list(current_crawl_tags)

    # Apply majority vote threshold
    threshold = max(2, ceil(total_crawls * 0.3))

    surviving = []
    for tag, count in tag_counts.items():
        if count >= threshold:
            surviving.append((tag, count))

    # Separate curated vs keyword tags
    curated_survivors = [(t, c) for t, c in surviving if t in curated_tag_set]
    keyword_survivors = [(t, c) for t, c in surviving if t not in curated_tag_set]

    # Cap keyword tags, keeping highest-frequency first
    keyword_survivors.sort(key=lambda x: (-x[1], x[0]))
    keyword_tags = [t for t, _ in keyword_survivors[:MAX_KEYWORD_TAGS]]

    # Start with all surviving tags (curated + capped keywords)
    seen = set()
    final_tags = [t for t, _ in curated_survivors]
    for tag in final_tags:
        seen.add(_norm(tag))
    for tag in keyword_tags:
        if _norm(tag) not in seen:
            final_tags.append(tag)
            seen.add(_norm(tag))

    # Also derive ancestor (curated) tags from surviving tags
    # This catches curated parents that weren't in crawl_event_tags directly
    # (e.g., "Science" as ancestor of "Civic Tech")
    for tag in list(final_tags):
        key = _norm(tag)
        for ancestor in ancestor_map.get(key, set()):
            anc_key = _norm(ancestor)
            if anc_key not in seen:
                final_tags.append(ancestor)
                seen.add(anc_key)

    # Fallback: add "Other" if no root-level tag was assigned
    has_root = any(
        _norm(t) in root_tags for t in final_tags
    )
    if not has_root and 'other' not in seen:
        final_tags.append('Other')

    return final_tags


def merge_crawl_events(cursor, connection, crawl_run_id=None, website_ids=None):
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
        website_ids: Optional list of website IDs to restrict to

    Returns:
        Tuple of (new_events_count, merged_count)
    """
    current_date, future_limit_date = get_active_date_window()

    # ── Setup ──
    # Initialize edit logger if available
    edit_logger = None
    if EditLogger:
        edit_logger = EditLogger(cursor, connection, source='crawl',
                                 editor_info=f'crawl_run:{crawl_run_id}' if crawl_run_id else 'crawl')

    # ── Pre-load tag voting data ──
    cursor.execute("SELECT name FROM tags WHERE type = 'tag'")
    curated_tag_set = {row[0] for row in cursor.fetchall()}
    ancestor_map, root_tags = db.build_tag_ancestor_map(cursor)

    # ── Load unprocessed crawl events ──
    # Get crawl_events that haven't been linked to any final event yet.
    # Only fetch CEs that have at least one future occurrence — skips historical
    # backlog CEs with only past dates that can never match future events.
    merge_query = """
        SELECT ce.id, ce.name, ce.short_name, ce.description, ce.emoji,
               ce.location_name, ce.sublocation, ce.location_id, ce.url,
               cr.website_id, l.lat, l.lng
        FROM crawl_events ce
        JOIN crawl_results cr ON ce.crawl_result_id = cr.id
        LEFT JOIN event_sources es ON ce.id = es.crawl_event_id
        LEFT JOIN locations l ON ce.location_id = l.id
        WHERE cr.status = 'processed'
          AND es.id IS NULL
          AND EXISTS (
              SELECT 1 FROM crawl_event_occurrences ceo
              WHERE ceo.crawl_event_id = ce.id
                AND (ceo.start_date >= %s OR (ceo.end_date IS NOT NULL AND ceo.end_date >= %s))
          )
    """
    merge_params = [current_date, current_date]
    if website_ids:
        placeholders = ','.join(['%s'] * len(website_ids))
        merge_query += f" AND cr.website_id IN ({placeholders})"
        merge_params.extend(website_ids)
    cursor.execute(merge_query, merge_params)

    new_crawl_events = cursor.fetchall()
    print(f"  Found {len(new_crawl_events)} unprocessed crawl_events")

    if not new_crawl_events:
        return 0, 0

    # ── Build lookup indexes for deduplication ──
    # Build website -> location_ids map for authoritative location correction
    cursor.execute("SELECT website_id, location_id FROM website_locations")
    website_location_ids = {}
    for row in cursor.fetchall():
        website_location_ids.setdefault(row[0], set()).add(row[1])

    # Build location_id -> canonical name so events.location_name stays in sync
    # with locations.name when a venue is resolved (otherwise the AI's raw
    # location string — e.g. an IG handle "@stella34macys" — leaks through).
    cursor.execute("SELECT id, name, emoji FROM locations")
    location_rows = cursor.fetchall()
    location_names_by_id = {row[0]: row[1] for row in location_rows}
    # Venue emoji fallback: events whose extraction (listing or detail crawl)
    # returned no emoji inherit their venue's emoji so they never render blank.
    location_emoji_by_id = {row[0]: row[2] for row in location_rows}

    # Websites needing strict name matching: a fuzzy (non-exact) name match must
    # be confirmed by a shared occurrence before merging. Without this, distinct
    # recurring programs at a shared generic venue (e.g. different daily.nyc run
    # clubs all meeting in Central Park, whose names share tokens) collapse onto
    # one event via the partial-name fallback. Exact-name matches and
    # same-schedule co-listings still merge. Configured per-website via
    # websites.strict_name_match to keep the merger generic — no site-specific
    # logic here.
    cursor.execute("SELECT id FROM websites WHERE strict_name_match = 1")
    strict_name_match_ids = {row[0] for row in cursor.fetchall()}

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
           OR (eo.end_date IS NOT NULL AND eo.end_date >= %s)
    """, (recent_cutoff, recent_cutoff))
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
            existing_events_by_location_id.setdefault(location_id, []).append(event_entry)

        # Index by coordinates if available (for legacy compatibility)
        if lat is not None and lng is not None:
            key = _coord_key(lat, lng)
            existing_events_by_coords.setdefault(key, []).append(event_entry)

        # Also index by normalized location_name (for fallback matching).
        # Track location_id on the entry so the fallback can reject candidates
        # whose location_id conflicts with the crawl_event's location_id (e.g.
        # AMC theaters all share the brand "AMC Theatres" as a location_name
        # but are distinct venues with distinct location_ids).
        if location_name:
            loc_key = normalize_name_for_dedup(location_name)
            if loc_key and len(loc_key) >= 3:
                existing_events_by_location.setdefault(loc_key, []).append(
                    {**event_entry, 'location_id': location_id}
                )

        # Index by website_id (last-resort fallback for location mismatches).
        # Track location_name on the entry so the fallback can avoid merging events
        # at clearly different specific venues.
        if website_id is not None:
            existing_events_by_website.setdefault(website_id, []).append(
                {**event_entry, 'location_name': location_name}
            )

    print(f"  Loaded {len(event_ids_with_future)} existing events with future occurrences")

    # Load future occurrence dates and date ranges for these events (for dedup)
    event_dates = {eid: set() for eid in event_ids_with_future}
    event_date_ranges = {eid: [] for eid in event_ids_with_future}
    event_slots = {eid: set() for eid in event_ids_with_future}  # {eid: {(date_str, std_time)}}
    if event_ids_with_future:
        from processor import _standardize_time
        # Use a placeholder approach for large IN clauses
        placeholders = ','.join(['%s'] * len(event_ids_with_future))
        cursor.execute(f"""
            SELECT event_id, start_date, start_time, end_date FROM event_occurrences
            WHERE event_id IN ({placeholders})
              AND (start_date >= %s AND start_date <= %s
                   OR (end_date IS NOT NULL AND end_date >= %s))
        """, (*event_ids_with_future, current_date, future_limit_date, current_date))
        for row in cursor.fetchall():
            event_id, start_date, start_time, end_date = row
            if start_date:
                event_dates[event_id].add(str(start_date))
                event_slots[event_id].add((str(start_date), _standardize_time(start_time)))
            if start_date and end_date:
                event_date_ranges[event_id].append((start_date, end_date))

    # ── Match crawl events to existing events or create new ones ──
    new_events_count = 0
    merged_count = 0
    source_url_lookup_cache = {}  # website_id -> set of trimmed listing URLs

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
            end_date = occ[2]
            if start_date and start_date <= future_limit_date:
                # Include if start_date is today or future, OR if end_date extends past today
                if start_date >= current_date or (end_date and end_date >= current_date):
                    valid_occurrences.append(occ)

        if not valid_occurrences:
            # No valid future occurrences, skip
            continue

        # Build set of occurrence dates and date ranges for this crawl event
        crawl_event_dates = set(str(occ[0]) for occ in valid_occurrences if occ[0])
        crawl_event_ranges = [(occ[0], occ[2]) for occ in valid_occurrences if occ[0] and occ[2]]
        from processor import _standardize_time as _std_time
        crawl_event_slots = {(str(occ[0]), _std_time(occ[1])) for occ in valid_occurrences if occ[0]}
        strict_match = website_id in strict_name_match_ids

        # Get tags for this crawl event
        cursor.execute("SELECT tag FROM crawl_event_tags WHERE crawl_event_id = %s", (ce_id,))
        tags = [row[0] for row in cursor.fetchall()]

        # Check for duplicate in existing events (same location + overlapping dates + similar name)
        matched_event_id = None
        norm_name = normalize_name_for_dedup(name)

        def _dates_overlap(existing_id):
            """Check if crawl event dates overlap with existing event dates.
            First checks start_date intersection, then falls back to date range overlap
            (for ongoing events like exhibitions where start_dates may differ between crawls).
            """
            existing_dates = event_dates.get(existing_id, set())
            if crawl_event_dates & existing_dates:
                return True
            # Fallback: check date range overlap (s1 <= e2 and s2 <= e1)
            existing_ranges = event_date_ranges.get(existing_id, [])
            for cs, ce in crawl_event_ranges:
                for es, ee in existing_ranges:
                    if cs <= ee and es <= ce:
                        return True
                # Also check if crawl event's range contains an existing start_date
                for ed_str in existing_dates:
                    try:
                        ed = date_type.fromisoformat(ed_str)
                        if cs <= ed <= ce:
                            return True
                    except ValueError:
                        pass
            # Also check if any existing range contains a crawl start_date
            for es, ee in existing_ranges:
                for cd_str in crawl_event_dates:
                    try:
                        cd = date_type.fromisoformat(cd_str)
                        if es <= cd <= ee:
                            return True
                    except ValueError:
                        pass
            return False

        def find_best_match(candidates, require_location_id_match=False, allow_no_date_overlap=False):
            """Find best matching event, preferring exact normalized name matches.

            When `require_location_id_match` is set and the crawl_event has a
            location_id, candidates with a different location_id are rejected.
            This prevents cross-venue merges when the location_name fallback
            tier matches generic brand names that are shared across venues
            (e.g. "AMC Theatres" appears at every AMC location).

            When `allow_no_date_overlap` is set, exact-name matches (normalized)
            are accepted even when date ranges don't overlap. This rescues
            recurring weekly programs whose previously-extracted occurrences
            ran out before the new crawl extracted fresh dates — without this,
            the merger creates a duplicate event each time a recurring program's
            "schedule horizon" lapses.

            For `strict_match` websites a *partial* (non-exact) name match is only
            accepted when the crawl_event shares at least one occurrence slot
            (date + start time) with the candidate. This stops different recurring
            programs at a shared generic venue — whose generic names merely share
            tokens (e.g. several run clubs in Central Park) — from collapsing,
            while still allowing same-schedule co-listings to merge. Exact matches
            are unaffected.
            """
            best_id = None
            exact_no_overlap_id = None
            for existing in candidates:
                if require_location_id_match and location_id is not None:
                    existing_loc_id = existing.get('location_id')
                    if existing_loc_id is not None and existing_loc_id != location_id:
                        continue
                if _dates_overlap(existing['id']):
                    if are_names_similar(name, existing['name']):
                        if normalize_name_for_dedup(existing['name']) == norm_name:
                            return existing['id']  # Exact match — best possible
                        elif best_id is None:
                            if strict_match and not (crawl_event_slots & event_slots.get(existing['id'], set())):
                                continue  # partial name match unconfirmed by schedule — skip
                            best_id = existing['id']  # Partial match — keep looking
                elif allow_no_date_overlap and exact_no_overlap_id is None:
                    if normalize_name_for_dedup(existing['name']) == norm_name:
                        exact_no_overlap_id = existing['id']
            return best_id if best_id is not None else exact_no_overlap_id

        # Try matching by location_id first (most precise and reliable).
        # Allow no-date-overlap match here only: same venue + exact name is a
        # strong-enough signal to merge a recurring event whose old occurrences
        # have lapsed before the new crawl extracted fresh dates.
        if location_id is not None and location_id in existing_events_by_location_id:
            matched_event_id = find_best_match(
                existing_events_by_location_id[location_id],
                allow_no_date_overlap=True,
            )

        # Fallback: match by coordinates if no location_id match found
        if matched_event_id is None and lat is not None and lng is not None:
            key = _coord_key(lat, lng)
            if key in existing_events_by_coords:
                matched_event_id = find_best_match(existing_events_by_coords[key])

        # Second fallback: match by location_name if still no match found.
        # Pass require_location_id_match=True so that brand-name location_names
        # shared across distinct venues (e.g. "AMC Theatres" at every AMC) don't
        # collapse different theaters' events into one.
        if matched_event_id is None and location_name:
            loc_key = normalize_name_for_dedup(location_name)
            if loc_key and len(loc_key) >= 3:
                # Try exact normalized match first
                if loc_key in existing_events_by_location:
                    matched_event_id = find_best_match(
                        existing_events_by_location[loc_key],
                        require_location_id_match=True,
                    )
                # If no exact match, try prefix containment (catches AI-added suffixes
                # like ", Brooklyn" or " New York" on otherwise matching location names).
                # Require the shorter key to be ≥20 chars to avoid false matches on
                # generic short names.
                if matched_event_id is None and len(loc_key) >= 20:
                    for existing_loc_key, candidates in existing_events_by_location.items():
                        if len(existing_loc_key) >= 20 and (
                            loc_key.startswith(existing_loc_key) or existing_loc_key.startswith(loc_key)
                        ):
                            matched_event_id = find_best_match(
                                candidates,
                                require_location_id_match=True,
                            )
                            if matched_event_id:
                                break

        # Last-resort fallback: match by website_id when location strategies all failed.
        # Catches cases where AI extraction assigns inconsistent location names between
        # crawls (e.g., "Online (via Zoom)" vs "Online", "Various NYC Venues" vs
        # "New York City Venues").
        #
        # Guard against false merges across distinct venues on the same website (e.g.,
        # NYPL has 90+ branches; "Library A" event must NOT match "Library B" event):
        # only allow this fallback when at least one side lacks a specific location
        # signal, OR when the location_names are similar.
        if matched_event_id is None and website_id in existing_events_by_website:
            crawl_loc_norm = normalize_name_for_dedup(location_name) if location_name else ''
            generic_locs = {'', 'online', 'virtual', 'zoom', 'tba', 'tbd', 'in person',
                            'various', 'multiple locations', 'not specified', 'na', 'n a'}
            crawl_loc_is_generic = (not crawl_loc_norm) or (crawl_loc_norm in generic_locs)

            def _safe_website_match(candidates):
                for existing in candidates:
                    if not _dates_overlap(existing['id']):
                        continue
                    if not are_names_similar(name, existing['name']):
                        continue
                    # strict_match sites: a non-exact name match needs a shared
                    # occurrence slot (see find_best_match) to merge here too.
                    if (strict_match
                            and normalize_name_for_dedup(existing['name']) != norm_name
                            and not (crawl_event_slots & event_slots.get(existing['id'], set()))):
                        continue
                    existing_loc_norm = normalize_name_for_dedup(existing.get('location_name') or '') if existing.get('location_name') else ''
                    existing_loc_is_generic = (not existing_loc_norm) or (existing_loc_norm in generic_locs)
                    # Allow merge only if either side is generic, or location_names match
                    if crawl_loc_is_generic or existing_loc_is_generic or crawl_loc_norm == existing_loc_norm:
                        return existing['id']
                return None
            matched_event_id = _safe_website_match(existing_events_by_website[website_id])

        # Global cross-location guard: never merge a crawl_event into an event at a
        # DIFFERENT known location. Same-name events at distinct venues (library
        # programs across branches, a film across theaters, a class series across
        # parks) are the dominant over-merge cause — the per-path guards missed
        # cases routed through the coordinate/website fallbacks or via NULL-location
        # "bridge" crawl_events. This is the authoritative backstop.
        current_loc_id = None
        if matched_event_id is not None and location_id is not None:
            cursor.execute("SELECT location_id FROM events WHERE id = %s", (matched_event_id,))
            _m = cursor.fetchone()
            current_loc_id = _m[0] if _m else None
            if _m and _m[0] is not None and _m[0] != location_id:
                matched_event_id = None

        if matched_event_id:
            # Merge with existing event
            # Un-archive event if it was previously archived (event found in new crawl)
            cursor.execute(
                "UPDATE events SET archived = FALSE WHERE id = %s AND archived = TRUE",
                (matched_event_id,)
            )

            # Append new occurrences from this crawl that aren't already on the event.
            # Without this, a multi-day run first ingested with one date (e.g. announcement-only)
            # would stay stuck on that date even after later crawls discover the full schedule.
            #
            # Specificity ladder for same (start_date, end_date): a row with a non-empty
            # start_time is more specific than one with empty start_time, and within a
            # given start_time, a non-empty end_time is more specific than empty. Listing
            # crawls often re-emit dateless variants of dates the detail crawl already
            # populated with times — without this ladder, the merger ended up storing both
            # rows and the popup showed e.g. "2026-05-22 11am-4pm" and "2026-05-22" as
            # two separate occurrences.
            _merge_occurrences_into_event(
                cursor, matched_event_id, valid_occurrences,
            )

            # Add URL if not already present.
            # Promote event-specific URLs over website listing URLs: if the new URL
            # is NOT one of the website's listing URLs but the event currently
            # has listing URLs, replace them with the more specific detail URL.
            if url:
                trimmed_url = url[:2000]
                cursor.execute(
                    "SELECT id FROM event_urls WHERE event_id = %s AND url = %s LIMIT 1",
                    (matched_event_id, trimmed_url)
                )
                already_present = cursor.fetchone()

                source_urls = source_url_listing_set(cursor, source_url_lookup_cache, website_id)
                new_is_listing = url.rstrip('/') in source_urls

                if not new_is_listing:
                    # Find existing listing URLs on this event to demote/remove
                    cursor.execute(
                        "SELECT id, url FROM event_urls WHERE event_id = %s",
                        (matched_event_id,)
                    )
                    listing_ids = [row[0] for row in cursor.fetchall() if row[1].rstrip('/') in source_urls]
                    if listing_ids:
                        placeholders = ','.join(['%s'] * len(listing_ids))
                        cursor.execute(
                            f"DELETE FROM event_urls WHERE id IN ({placeholders})",
                            listing_ids
                        )

                    if already_present:
                        # Promote existing matching URL to sort_order=0
                        cursor.execute(
                            "UPDATE event_urls SET sort_order = 0 WHERE id = %s",
                            (already_present[0],)
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO event_urls (event_id, url, sort_order) VALUES (%s, %s, 0)",
                            (matched_event_id, trimmed_url)
                        )
                elif not already_present:
                    # New URL is a listing page — only insert if no other URL exists yet
                    cursor.execute(
                        "SELECT 1 FROM event_urls WHERE event_id = %s LIMIT 1",
                        (matched_event_id,)
                    )
                    if not cursor.fetchone():
                        cursor.execute(
                            "INSERT INTO event_urls (event_id, url, sort_order) VALUES (%s, %s, 99)",
                            (matched_event_id, trimmed_url)
                        )

            # Update location_id if missing or if the new value is the website's
            # linked location (corrects stale fuzzy-match errors from earlier crawls)
            if location_id:
                current_location_id = current_loc_id
                if not current_location_id or (
                    current_location_id != location_id and
                    website_id in website_location_ids and
                    location_id in website_location_ids[website_id]
                ):
                    cursor.execute("UPDATE events SET location_id = %s WHERE id = %s", (location_id, matched_event_id))

            # Update location_name/sublocation if currently missing or placeholder
            if location_name and location_name not in ('Not specified', ''):
                cursor.execute(
                    "SELECT location_name FROM events WHERE id = %s",
                    (matched_event_id,),
                )
                result = cursor.fetchone()
                current_loc = result[0] if result else None
                if not current_loc or current_loc in ('Not specified', ''):
                    update_fields = ["location_name = %s"]
                    update_values = [location_name]
                    if sublocation:
                        update_fields.append("sublocation = %s")
                        update_values.append(sublocation)
                    update_values.append(matched_event_id)
                    cursor.execute(
                        f"UPDATE events SET {', '.join(update_fields)} WHERE id = %s",
                        update_values,
                    )

            # Backfill placeholder description/emoji from this source. The two
            # are handled INDEPENDENTLY: an event can have a real description but
            # a missing emoji (e.g. the detail crawl returned an empty emoji and
            # overwrote the listing's), so the emoji must be able to backfill
            # even when the description is already populated — otherwise the
            # event stays emoji-less forever.
            cursor.execute(
                "SELECT description, emoji FROM events WHERE id = %s",
                (matched_event_id,),
            )
            result = cursor.fetchone()
            current_desc = result[0] if result else None
            current_emoji = result[1] if result else None

            backfill_fields = []
            backfill_values = []
            if (description and description != 'No description available.'
                    and (not current_desc or current_desc == 'No description available.')):
                backfill_fields.append("description = %s")
                backfill_values.append(description)
            if not current_emoji or current_emoji == '📅':
                new_emoji = (emoji[:10] if emoji else None) or location_emoji_by_id.get(location_id)
                if new_emoji and new_emoji != current_emoji:
                    backfill_fields.append("emoji = %s")
                    backfill_values.append(new_emoji)
            if backfill_fields:
                backfill_values.append(matched_event_id)
                cursor.execute(
                    f"UPDATE events SET {', '.join(backfill_fields)} WHERE id = %s",
                    backfill_values,
                )

            # Update tags using majority vote across crawl history
            if tags:
                voted_tags = compute_voted_tags(
                    cursor, matched_event_id, tags,
                    curated_tag_set, ancestor_map, root_tags
                )
                db.upsert_event_tags(cursor, matched_event_id, voted_tags, replace=True)

            # Link crawl_event to existing event
            cursor.execute(
                "INSERT IGNORE INTO event_sources (event_id, crawl_event_id, is_primary) VALUES (%s, %s, FALSE)",
                (matched_event_id, ce_id)
            )
            merged_count += 1

        else:
            # Create new event
            canonical_loc_name = location_names_by_id.get(location_id) if location_id else None
            effective_loc_name = canonical_loc_name or location_name
            # Never create an emoji-less event: AI emoji → venue emoji → 📅.
            effective_emoji = (emoji[:10] if emoji else None) or location_emoji_by_id.get(location_id) or '📅'
            cursor.execute("""
                INSERT INTO events (name, short_name, description, emoji, location_id, location_name,
                                   sublocation, website_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                name[:500],
                short_name[:255] if short_name else None,
                description,
                effective_emoji,
                location_id,
                effective_loc_name[:255] if effective_loc_name else None,
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
                    'emoji': effective_emoji,
                    'location_id': location_id,
                    'location_name': effective_loc_name[:255] if effective_loc_name else None,
                    'sublocation': sublocation[:255] if sublocation else None,
                    'website_id': website_id
                })

            # Add occurrences — canonicalize times at the boundary.
            from processor import _standardize_time
            for i, occ in enumerate(valid_occurrences):
                cursor.execute("""
                    INSERT IGNORE INTO event_occurrences (event_id, start_date, start_time, end_date, end_time, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (new_event_id, occ[0], _standardize_time(occ[1]), occ[2], _standardize_time(occ[3]), i))

            # Add URL
            if url:
                cursor.execute(
                    "INSERT INTO event_urls (event_id, url, sort_order) VALUES (%s, %s, 0)",
                    (new_event_id, url[:2000])
                )

            # Add tags
            db.upsert_event_tags(cursor, new_event_id, tags)

            # Link crawl_event to new event
            cursor.execute(
                "INSERT IGNORE INTO event_sources (event_id, crawl_event_id, is_primary) VALUES (%s, %s, TRUE)",
                (new_event_id, ce_id)
            )

            # Add to lookup indexes for future dedup within this batch
            event_entry = {'id': new_event_id, 'name': name}
            event_dates[new_event_id] = crawl_event_dates
            event_date_ranges[new_event_id] = crawl_event_ranges
            event_slots[new_event_id] = crawl_event_slots

            if location_id is not None:
                existing_events_by_location_id.setdefault(location_id, []).append(event_entry)

            if lat is not None and lng is not None:
                key = _coord_key(lat, lng)
                existing_events_by_coords.setdefault(key, []).append(event_entry)

            if location_name:
                loc_key = normalize_name_for_dedup(location_name)
                if loc_key and len(loc_key) >= 3:
                    # Carry location_id so find_best_match's require_location_id_match
                    # check rejects cross-venue brand-name matches (e.g. "AMC Theatres"
                    # spans every AMC theater).
                    existing_events_by_location.setdefault(loc_key, []).append(
                        {**event_entry, 'location_id': location_id}
                    )

            if website_id is not None:
                existing_events_by_website.setdefault(website_id, []).append(
                    {**event_entry, 'location_name': location_name}
                )

            new_events_count += 1

    _retry_on_deadlock(connection.commit)
    print(f"  Added {new_events_count} new events, merged {merged_count} duplicates")

    # ── Post-merge dedup (safety net) ──
    # Post-merge dedup: catch any exact-name duplicates the matching logic missed.
    # This happens when AI extraction assigns different locations between crawls,
    # causing the merger to create a new event instead of matching the existing one.
    if new_events_count > 0:
        deduped = _retry_on_deadlock(_deduplicate_same_name_events, cursor, connection, current_date, edit_logger)
        if deduped > 0:
            print(f"  Post-merge dedup: merged {deduped} duplicate(s)")

    # ── Archive outdated events ──
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
            archived_count, upcoming_events = _retry_on_deadlock(db.archive_outdated_events, cursor, connection, website_id)
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

        # ── Stamp merged_at on the crawl_results whose events went through this merge ──
        # Pure observability: lets `status='processed' AND merged_at IS NULL` flag
        # crawl results whose merge tail was interrupted (lock race / killed run)
        # without joining through event_sources.
        for i in range(0, len(crawl_event_ids), 1000):
            chunk = crawl_event_ids[i:i + 1000]
            ph = ','.join(['%s'] * len(chunk))
            cursor.execute(f"""
                UPDATE crawl_results SET merged_at = NOW()
                WHERE id IN (SELECT DISTINCT crawl_result_id FROM crawl_events WHERE id IN ({ph}))
            """, chunk)
        _retry_on_deadlock(connection.commit)

    return new_events_count, merged_count
