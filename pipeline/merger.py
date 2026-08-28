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
from math import ceil, cos, radians
from pathlib import Path

import mysql.connector

import db
from constants import get_active_date_window

# Maximum retries for deadlock errors
DEADLOCK_MAX_RETRIES = 3
DEADLOCK_RETRY_DELAY = 2  # seconds

# How far back a DATELESS crawl_event (no occurrence rows at all) may be picked
# up by the merger. Dated crawl_events are unbounded — a future occurrence makes
# them self-limiting — but a dateless one carries no date to age out on, so the
# window plus the "website's latest crawl" test is the only thing keeping the
# historical backlog from replaying.
DATELESS_MERGE_WINDOW_DAYS = 14


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


# A "Fan Event" / "Fan First Screening" is a SEPARATELY ticketed, separately dated
# showing that a cinema chain lists alongside the film's regular run under a nearly
# identical name ("Legend of the White Dragon Fan Event" on Aug 28, then "Legend of
# the White Dragon" Aug 29 - Sep 2). Without this guard the two fuse, the merger
# unions their occurrences, and the survivor ends up holding two sort_order = 0
# URLs — one of which points at the wrong ticket listing.
#
# Deliberately narrow: the marker word must be followed by a showing noun. A bare
# \bfan\b also matches "Cosi Fan Tutte", "When Sh*t Hits the Fan" and "World Cup
# Fan Village", which measurably broke legitimate merges. Screening-FORMAT variants
# of the same showing (3D, IMAX, "(Open Cap/Eng Sub)") carry no fan marker and are
# unaffected — they must keep merging.
_FAN_SHOWING_RE = re.compile(
    r'\bfan\s+(?:first\s+)?'
    r'(?:event|screening|preview|premiere|celebration|party|night)s?\b'
)


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

    # Apostrophes are DELETED, not spaced. The generic punctuation pass below turns
    # every mark into a space, which splits a possessive into two tokens and makes
    # "Women's" ("women s") a different key from "Womens" — so the same title from
    # two feeds, one of which drops the apostrophe, never matched. Sources disagree
    # about apostrophes constantly ("Hell's Kitchen"/"Hells Kitchen", "Joe Turner's
    # Come and Gone", "Kid's Crafternoon"), including curly vs straight within one
    # site. Measured over all 189,187 events: 11,476 names change key but only 33
    # groups newly fuse, and every one is a genuine possessive variant of the same
    # title. Contractions are unaffected either way ("Rock 'n' Roll" already matched
    # "Rock n Roll", and still does).
    no_apostrophes = re.sub(r"['‘’ʼ´`]", '', no_underscores)

    # Replace remaining punctuation with spaces (not just remove) to avoid word
    # concatenation, e.g. "Alice/Bob" should become "Alice Bob", not "AliceBob"
    no_punct = re.sub(r'[^\w\s]', ' ', no_apostrophes.strip().lower())
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


# Keywords that turn the SHORT token right after them into a cohort label rather
# than noise ("Class C", "Part II", "Grades K-2"). See `_significant_tokens`.
_COHORT_KEYWORDS = frozenset({
    'class', 'classes', 'section', 'sections', 'level', 'levels',
    'part', 'parts', 'grade', 'grades', 'group', 'groups', 'room', 'rooms',
    'unit', 'units', 'series', 'week', 'weeks', 'cohort', 'cohorts',
    'lesson', 'lessons',
})

# Short tokens that are connectors, never a cohort label, even directly after a
# cohort keyword: "SWING Classes w/Margaret Batiuchok", "Marvin's First Day x
# Brooklyn Book Bodega", "Levels 'n' Stuff". ("a" is deliberately NOT here —
# "Class A" and "Group A" are real labels.)
_NOT_COHORT_LABELS = frozenset({'w', 'x', 'n'})

_ROMAN_CHARS = frozenset('ivxlcdm')


def _is_cohort_label(word, prev_raw, next_raw):
    """Is this short token a cohort label ("Class C", "Part II", "Grades K-2")?

    `prev_raw`/`next_raw` are the RAW adjacent tokens, not the surviving
    significant ones: adjacency is the whole signal, and reading the previous
    *significant* token instead lets the test cascade down a run of short tokens
    ("Group S*x" -> "group s x": drop "s", and "x" then sees "group" as its
    predecessor and gets admitted in its place).
    """
    if prev_raw not in _COHORT_KEYWORDS or word in _NOT_COHORT_LABELS:
        return False
    if not (len(word) == 1 or all(c in _ROMAN_CHARS for c in word)):
        return False
    # A cohort label is ONE token. A run of two short letter tokens is mangled
    # text — a censored word split at its asterisk ("Navigating Group S*x"), or
    # an ampersand joining two installments ("Excel Part I & II") — not a label.
    return not (next_raw and len(next_raw) < 3 and next_raw.isalpha())


def _is_year(w):
    """Check if word is a 4-digit year (2000-2099)."""
    return len(w) == 4 and w.isdigit() and w.startswith('20')


def _coord_key(lat, lng):
    """Build the rounded (lat, lng) tuple used as a coordinate index key."""
    return (round(float(lat), 5), round(float(lng), 5))


def _significant_tokens(name):
    """Ordered significant tokens of `name` — the shared basis of every name tier.

    Tokens under 3 characters are dropped as noise, EXCEPT purely numeric ones,
    which are kept. A short number is almost never noise: it is usually the whole
    discriminator between two otherwise identical names. Under the blanket 3-char
    floor, "Rugby Clinic (Ages 3-6)" and "Rugby Clinic (Ages 7-12)" both reduced
    to {ages, clinic, rugby} — literally the same name to every word-based tier —
    and BPCA events 212806/215628 genuinely cross-merged (both rows ended up
    holding both cohorts' sources) and had to be repaired by hand. Same shape for
    "Week 1"/"Week 2", "Level 2"/"Level 5", "(Grades 3-5)"/"(Grades 6-8)",
    "Program 12"/"Program 14" and 2-digit room numbers — 3-digit numbers already
    cleared the floor, which is why "Meeting Room 201" vs "305" never had the bug.

    Two exceptions keep the exemption from firing on numbers that are NOT
    discriminators:

    - Years, as before. "Fall Festival 2025"/"2026" is a republication, and the
      schedule layers own that call.
    - A short number in the name's LEADING run of digits. On this corpus a
      leading bare number is an extraction artifact, not part of the title:
      Partiful's discover page prefixes an RSVP count ("39 ⁂ release party ⁂"
      and "47 ⁂ release party ⁂" are the same Partiful URL on the same date),
      and NYC DSA's canvass feed prefixes a per-day count ("4 Candidate
      Canvasses" / "119 Candidate Canvasses"). Making those significant split one
      event into one row per crawl. Only SHORT leading numbers are dropped, so
      this exception never removes a token the old rule kept.

    Measured with `_drop_shared_weak_tokens` over all 32,402 distinct (event,
    source crawl_event) name pairs reachable via event_sources — pairs of live
    events are a selection-bias trap, they are live precisely because they did
    NOT merge (.scratch/numtok_measure.py, 2026-08-16). 270 pairs stop matching,
    32,131 are unaffected, 1 newly matches (a correct one). Hand-labelled, the
    stops are 105 age/grade cohorts, 42 numbered weeks/sessions/classes, 36
    showtime or date variants, 20 numbered programs/episodes, 13 class levels and
    55 assorted — ~15 of the 270 are genuine same-event pairs and the rest are
    distinct events. The blanket exemption without the leading-run carve-out
    stopped 271 but 56 of its stop lines were the Partiful/DSA artifact shape,
    i.e. real regressions. A lost correct merge degrades to a duplicate event
    that /dedupe-events catches; a wrong merge writes another cohort's dates onto
    a live event, so the trade is deliberately biased toward blocking.

    A short LETTER is kept under the same reasoning, but only where the name
    itself says it is a cohort label: directly after a cohort keyword, and
    subject to `_is_cohort_label`. The letter version of the shape is identical —
    "... Learn to Swim Level 1 (Class C)" / "(Class D)" / "(Class E)" reduced to
    byte-identical token lists, so NYC Parks' swim classes fused across class
    letters, across programs (Children's vs Parent-and-Tots) and even across
    pools. Unlike a bare number, a bare letter really is noise almost everywhere,
    which is why the keyword, not the letter, is the trigger.

    Measured the same way over all 32,856 distinct differing pairs
    (.scratch/shorttok_measure.py, 2026-08-19): 39 pairs stop matching, 32,817
    are unaffected, 0 newly match. All 39 are distinct events — 36 NYC Parks
    swim-class cohorts, 2 grade bands ("Kerboom Kidz- Grades K-2" vs "Grades
    3-5") and "Layer the Walls Part I" vs "Part II" — with no regression left
    after the `_is_cohort_label` guards. The looser forms measured alongside are
    the reason for those guards: reading the previous *significant* token instead
    of the raw one split "HMU Academy: Navigating Group S*x" from its own
    uncensored crawl, and admitting any short token (not just a letter or roman
    numeral) after a keyword picks up "Day of", "Week of", "Series of".

    Note this does NOT by itself unfuse the tightest cases: "... Level 1 (Class
    C)" vs "(Class D)" still matches on a 0.85 Jaccard, where the letter is
    present but outvoted. The ratio tiers own that; this only guarantees the
    discriminator reaches them.

    Short MIXED alphanumerics ("3d", "1a", "5k") were measured as a third
    carve-out and NOT taken: 7 pairs change, and while 5 are genuinely distinct
    (including a Regal 3D showing that holds the 2D permalink), the change
    reverses the deliberate cinema policy that screening-FORMAT variants merge
    (`_FORMAT_TAGS`, `_FAN_SHOWING_RE`) and would make "Movie (3D)" — whose
    parenthetical `_strip_format_parentheticals` deletes outright — stop matching
    "Movie 3D". Too marginal, and it belongs in the format-tag layer where both
    spellings are handled together.
    """
    toks = normalize_name_for_dedup(name).split()
    lead = 0
    while lead < len(toks) and toks[lead].isdigit():
        lead += 1
    out = []
    for i, w in enumerate(toks):
        if w in _STOP_WORDS or _is_year(w):
            continue
        if w.isdigit():
            if len(w) < 3 and i < lead:
                continue
            # Zero-padding is a formatting choice, not a different number: the
            # same yacht party is listed as "... - August 8" and "... | Aug 08".
            out.append(w.lstrip('0') or '0')
        elif len(w) >= 3:
            out.append(w)
        elif _is_cohort_label(w, toks[i - 1] if i else '',
                              toks[i + 1] if i + 1 < len(toks) else ''):
            out.append(w)
    return out


def get_significant_words(name, stem=False):
    """Get significant words from a normalized name (see `_significant_tokens`)."""
    result = set(_significant_tokens(name))
    if stem:
        result = set(stem_word(w) for w in result)
    return result


def _subtitle_content_words(text):
    """Significant words of a subtitle, minus the short tokens that
    `_significant_tokens` newly admits (bare numbers, and cohort labels).

    Used by the two "does this subtitle carry real distinguishing content?"
    tests, which must stay at their pre-numeric-token behaviour. A subtitle that
    is only a date or an installment number ("Reading Rhythms Lower Manhattan:
    July 27") is a per-occurrence label, not a distinct sub-event, and the bare
    series name must still be able to absorb it — same reasoning as
    `_trailing_date_token`. Longer numbers are left in, because they are part of
    the title ("TechConnect: Podcasting 101 A&B" really is a different class from
    "TechConnect In-Person: Open Lab") and the old rule counted them.
    """
    return set(w for w in get_significant_words(text) if len(w) >= 3)


def _drop_shared_weak_tokens(words1, words2):
    """Remove short tokens the two word sets AGREE on, before the ratio tiers.

    Numbers and cohort labels are kept as significant tokens so that a
    *disagreement* can break a match (see `_significant_tokens`), but an
    *agreement* on one is weak evidence of same-eventness: a venue's calendar
    repeats the same times, dates, age bands and section letters across every
    listing it publishes. Left in the numerator, a shared number pushes unrelated
    siblings over the Jaccard / containment thresholds — "Sunday June 21 | the Alex Owen Quartet" vs "Sunday June 21 |
    DJ Dance" (two acts, one night) and "FRI 8 & 9:30 - Igor Lumpert w/Drew
    Gress, Jeff Miles, Tom Rainey" vs "...w/Drew Gress, Damion Reid" both cross
    0.75 containment on the shared "21" / "8" / "9" alone.

    Dropping shared short tokens from both sides makes the whole short-token
    change purely restrictive: every ratio is <= what it was before the change,
    so no pair that fails to match today starts matching. The subset tier
    upstream is deliberately left alone — it compares whole sets, so a shared
    number cannot manufacture a match there, while a one-sided number correctly
    breaks containment. Measured 2026-08-16: this removes all 19 name-tier merges
    the numeric exemption would otherwise have created, of which ~6 were wrong.
    Extended to cohort labels 2026-08-19, where it removes the only 2 merges the
    letter exemption would have created — both wrong ("Glass in Context Part II:
    The Rise of the Artist" and "Part II - From Venice to Industrialization" are
    two different lectures that a shared "ii" pushes over containment).
    """
    shared = set(w for w in (words1 & words2) if w.isdigit() or len(w) < 3)
    if not shared:
        return words1, words2
    return words1 - shared, words2 - shared


def _subset_match(words1, words2, name1, name2, stem=False):
    """Word-set subset test, guarded against one-word names swallowing longer ones.

    A name that reduces to a SINGLE significant word is a subset of every other
    name containing that word, so an unguarded subset test merges unrelated
    events that merely share a common noun: "Block by Block" (-> {block}, since
    "by" is a stop word and the set collapses the repeat) matched "Brooklyn
    Botanic Garden Block Party 2026" and dragged a May-Oct exhibition's date
    range onto a one-evening party.

    But the single-word case is genuinely load-bearing — it is how a bare
    headliner or title picks up its fuller listing ("Yoga" <- "Yoga with Nicole
    and ShapeUp NYC", "SYTE" <- "SYTE, Von Stearns", "QED" <- 40 crawl_events).
    Over every (event, source crawl_event) name pair on the live corpus, 21 such
    merges are correct and 16 are wrong, so refusing them all is worse than
    allowing them all.

    What separates the two is POSITION, not rarity (corpus frequency does not
    separate them: "yoga" appears in 128 live names and is right, "block"
    appears in 158 and is wrong). A real title match leads the longer name --
    "Yoga with Nicole...", "SYTE, Von Stearns", "QED: A conversation..." -- while
    a coincidental shared noun sits in the middle or at the end: "Brooklyn
    Botanic Garden [Block] Party", "Boy [Band] Brunch", "Graduating Student
    [Exhibition]". Requiring the lone word to be the longer name's first
    significant token keeps 17 of the 21 and blocks 12 of the 16. The 4 it costs
    (OLMO, BINI, Conspirare, "Outdoor Yoga...") degrade to a duplicate event,
    which /dedupe-events catches -- strictly milder than wrong dates on a live
    event.

    Equal word sets are always allowed: "The Moth" vs "Moth" differ only in stop
    words, and the substring branch upstream can't catch them (it needs 5+
    chars). Regression 2026-08-04.
    """
    if not (words1.issubset(words2) or words2.issubset(words1)):
        return False
    if words1 == words2 or min(len(words1), len(words2)) >= 2:
        return True

    # Exactly one significant word on the smaller side — demand it leads the
    # longer name.
    lone = next(iter(words1 if len(words1) < len(words2) else words2))
    longer = name2 if len(words1) < len(words2) else name1
    leading = _ordered_significant_words(longer)
    if stem:
        leading = [stem_word(w) for w in leading]
    return bool(leading) and leading[0] == lone


# ── URL identity ──────────────────────────────────────────────────────────────
# A crawl_event's URL is the one piece of identity the SOURCE controls: a venue
# publishing the same event twice publishes it at the same link. Everything else
# the merger matches on (location_id, coordinates, location_name) is our own
# inference and drifts run to run — a listing page yields "Greenwich Village"
# while the detail page yields "Father Demo Square", `processor.get_location_id`
# resolves them to different rows, the cross-location guard refuses the match,
# and a duplicate event row is created and then archived as an orphan. Measured
# on the live corpus: 861 currently-coexisting event pairs are that shape.
#
# Query strings are KEPT (minus tracking params) because on several platforms
# the query IS the identity (`?event=`, `?performanceId=`); stripping it would
# fuse distinct events behind one path.
_URL_TRACKING_PARAM_RE = re.compile(
    r'^(?:utm_[a-z_]+|fbclid|gclid|msclkid|mc_cid|mc_eid|_ga|igshid)$', re.I
)

# Host aliases that serve the SAME page under two names, applied after the
# scheme and a leading `www.` are stripped. `api.lu.ma` is a different service
# (JSON endpoint) and must not be folded, hence the `(?=[/?]|$)` anchor.
_HOST_ALIASES = (
    (re.compile(r'^lu\.ma(?=[/?]|$)', re.I), 'luma.com'),
)

# Guards on the URL-identity tier, all three calibrated against the live corpus
# (see the write-up in .claude/scheduled-tasks.md):
#  - a URL carrying more than this many distinct normalized event names is a
#    LISTING page, not an event page. Painting Lounge's rezclick root carries
#    190 names across two real branches; without the cap the tier fuses the
#    Harlem and Midtown studios' identically-named classes (80 bad pairs).
URL_IDENTITY_MAX_DISTINCT_NAMES = 2
#  - two venues further apart than this are different places even when the name,
#    website, URL and schedule all agree. A run club that meets in two parks
#    (w4860) and a cinema chain's two branches (Nitehawk Williamsburg vs
#    Prospect Park, 6.2 km) are the shapes this blocks; at 3 km the run clubs
#    come back.
URL_IDENTITY_MAX_KM = 2.0


# A trailing per-OCCURRENCE date segment on an event permalink
# (`/event/guided-brewery-tour-and-sake-tasting/2026-11-01/`). Tribe and several
# other calendars mint one of these per date of the SAME event, which split a
# recurring series into one event row per URL variant.
_URL_TRAILING_DATE_RE = re.compile(
    r'^(?P<head>.+/(?P<slug>[^/]*[a-z][^/]*))/'
    r'\d{4}-\d{2}-\d{2}(?:[t_-]\d{2}[:-]?\d{2})?$'
)
# ...but only when what precedes the date is an event SLUG. A per-day listing
# index (`/events/2026-08-23/`, `/calendar/2026-08-23/`) has the same shape and
# would collapse to a site-level key shared by every event on the site. The
# name-diversity guard downstream (`URL_IDENTITY_MAX_DISTINCT_NAMES`) would
# reject such a key anyway, but folding it here first is cheaper and keeps the
# key honest for the other callers of this function.
_URL_LISTING_SEGMENTS = frozenset({
    'e', 'ev', 'event', 'events', 'calendar', 'calendars', 'cal', 'schedule',
    'schedules', 'program', 'programs', 'programme', 'programmes', 'whats-on',
    'agenda', 'day', 'date', 'dates', 'listing', 'listings', 'search', 'p',
})


def normalize_url_for_identity(url):
    """Canonicalize a URL for identity comparison.

    Drops the fragment and tracking-only query params, the scheme, a leading
    `www.`, and the trailing slash; sorts the surviving query params so
    parameter order can't split one event in two. Returns '' for a falsy URL.

    A trailing `/YYYY-MM-DD/` segment is dropped as well: it addresses one
    OCCURRENCE of an event, not a different event, and keeping it split
    recurring series in two. Industry City's "Guided Brewery Tour and Sake
    Tasting" ran as two live rows — one holding the August dates, one the
    September/November ones — purely because the URL variants never met, and
    the differing location (Brooklyn Kura vs the campus row) then blocked every
    other tier. Measured over all 281,235 `event_urls` rows on 2026-08-23: 9,163
    keys change, forming 7,316 newly-shared pairs of which only **5 have both
    sides live**, and all 5 are genuine duplicates (two Industry City, plus
    Riverside Park, Downtown Brooklyn Partnership and Prospect Park). The rest
    are archived rows that were already the same event.

    Host aliases that address the SAME page are folded to one spelling
    (`_HOST_ALIASES`) — `lu.ma` 301s to `luma.com`, but the two strings made 3
    of 10 Luma slug collisions invisible to this tier on 2026-08-17.
    `processor.absolutize_url` now canonicalizes at ingest; this keeps the tier
    correct for the rows written before that and for any path that bypasses it.
    """
    if not url:
        return ''
    cleaned = url.strip().split('#')[0]
    cleaned = re.sub(r'^https?://', '', cleaned, flags=re.I)
    cleaned = re.sub(r'^www\.', '', cleaned, flags=re.I)
    for alias_re, canonical in _HOST_ALIASES:
        cleaned, count = alias_re.subn(canonical, cleaned, count=1)
        if count:
            break
    if '?' in cleaned:
        base, query = cleaned.split('?', 1)
        kept = sorted(
            p for p in query.split('&')
            if p and not _URL_TRACKING_PARAM_RE.match(p.split('=')[0])
        )
        cleaned = base + ('?' + '&'.join(kept) if kept else '')
    cleaned = cleaned.rstrip('/').lower()
    # Only on a bare path — a query string means the date may be doing real
    # routing work, and stripping it could fold two genuinely different pages.
    if '?' not in cleaned:
        m = _URL_TRAILING_DATE_RE.match(cleaned)
        if m and m.group('slug') not in _URL_LISTING_SEGMENTS:
            cleaned = m.group('head')
    return cleaned


def _locations_within(loc_a, loc_b, coords, max_km=URL_IDENTITY_MAX_KM):
    """True when two location_ids denote the same or a nearby place.

    Unknown on either side (NULL location, or a location row without
    coordinates) counts as compatible — that is the venue-mapping-drift case
    this exists to rescue. Distance is an equirectangular approximation, which
    is exact enough at metro scale and avoids a trig-heavy haversine in a
    per-crawl_event loop.
    """
    if loc_a is None or loc_b is None or loc_a == loc_b:
        return True
    a = coords.get(loc_a)
    b = coords.get(loc_b)
    if not a or not b or a[0] is None or b[0] is None:
        return True
    lat_a, lng_a = float(a[0]), float(a[1])
    lat_b, lng_b = float(b[0]), float(b[1])
    dy = (lat_a - lat_b) * 111.0
    dx = (lng_a - lng_b) * 111.0 * cos(radians((lat_a + lat_b) / 2))
    return (dx * dx + dy * dy) ** 0.5 < max_km


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


# Heads that are a DELIVERY MODE or a generic category, never an event's identity.
# A "<head>: <subtitle>" name whose head is one of these must keep its subtitle:
# collapsing it hands the containment tiers downstream a high-collision core that
# matches every other listing sharing the same house prefix. This is not a
# theoretical risk — "In-Person:" / "Online:" is NYPL's and BPL's house prefix, so
# reducing "In-Person: Searching Bloomberg: One-on-One" to "In-Person" fused
# unrelated library programs into one event (regression 2026-08-17).
#
# Compared against BOTH the raw lowercase head and its normalized form, because
# the same head is punctuated differently across sources ("In-Person", "In Person",
# "IN PERSON!").
_GENERIC_CORE_TITLE_HEADS = {
    'online', 'virtual', 'zoom', 'free', 'webinar', 'workshop', 'class', 'live',
    'in person', 'inperson', 'hybrid', 'in library', 'in branch', 'remote',
}


def _is_generic_core_head(main_title):
    """True when a pre-colon head carries no event identity of its own."""
    lowered = main_title.strip().lower()
    if lowered in _GENERIC_CORE_TITLE_HEADS:
        return True
    return normalize_name_for_dedup(main_title) in _GENERIC_CORE_TITLE_HEADS


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
    # The \b after each marker is load-bearing: without it the pattern matches
    # INSIDE a longer word, so "Tax Preparation Presentation" lost everything up
    # to "Present" and returned the core "ation" — which the containment tier
    # then found inside "English Conversation Group" and merged two unrelated BPL
    # programs. Likewise "FOSSS Guided Music Production Session: Beginner" ->
    # "Session". Regression 2026-08-17.
    presenter_patterns = [
        r'^.+?\s+presents?\b\s*:?\s*',       # "X Presents: " or "X Present "
        r'^.+?\s+productions?\s*:\s*',       # "X Productions: " (colon required —
                                             # "Music Production Session" is a
                                             # title, not a presenter credit)
        r'^hosted\s+by\s+.+?:\s*',           # "Hosted by X: " (requires colon)
    ]

    for pattern in presenter_patterns:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)

    # Remove subtitles after colon (but keep if main title is too short or a
    # generic delivery/category word). "Online: <subtitle>" must not collapse
    # to "Online", because the substring check downstream would then match any
    # title containing the word "online".
    if ':' in result:
        parts = result.split(':', 1)
        main_title = parts[0].strip()
        if len(main_title) >= 5 and not _is_generic_core_head(main_title):
            result = main_title

    return result.strip()


# Lineup markers ("ft:", "feat:", etc.) introduce a per-occurrence cast rather
# than a distinct sub-event, so a colon right after one is NOT a subtitle break.
_LINEUP_MARKERS = {'ft', 'feat', 'featuring', 'w', 'with', 'presents', 'present'}


def _ordered_significant_words(name):
    """Like get_significant_words but preserves order (for prefix comparison)."""
    return _significant_tokens(name)


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
    if len(_subtitle_content_words(subtitle)) < 2:
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


# A private booking is never the public class it is booked on. Studios that take
# private parties publish them in the same feed with the class title appended
# ("Private Party - Ryan W. / NYU - Starry Night Over Empire State Building",
# w1190 Painting Lounge), so the public name is a literal SUBSTRING of the
# private one and every containment tier fuses them — putting a stranger's
# private booking's dates on a public class. The marker is the identity.
_PRIVATE_BOOKING_RE = re.compile(
    r'\b(?:private\s+(?:part(?:y|ies)|events?|bookings?|class(?:es)?|groups?|sessions?|lessons?)'
    r'|buyouts?|corporate\s+(?:events?|part(?:y|ies)|bookings?))\b'
)


# Spelled-out installment numbers, canonicalized to digits so "Session One" and
# "Session 1" stay the same session.
_SPELLED_NUMBERS = {
    'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5', 'six': '6',
    'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10', 'eleven': '11', 'twelve': '12',
}


# Skill-level words. A class series published one row per level ("High Beginner
# Level English Conversation Classes: We Speak NYC" vs "Intermediate Level ...")
# differs by exactly ONE token out of seven, so every ratio tier — and the 75%
# asymmetric-containment tier in particular — reads the siblings as one event and
# fuses two different classes (regression 2026-08-17, NYPL/BPL "We Speak NYC").
# The level word IS the identity of such a listing, the same way "Men's"/"Women's"
# is for a sport.
_LEVEL_WORDS_RE = re.compile(
    r'\b(beginner|beginners|beginning|intermediate|advanced|novice|basics?|introductory|intro|expert)\b'
)
# Spelling variants of ONE level must canonicalize together, or the guard splits
# a listing from itself ("Computer Basics" vs BPL's "Computer Basic").
_LEVEL_CANONICAL = {
    'beginners': 'beginner', 'beginning': 'beginner',
    'basics': 'basic', 'introductory': 'intro',
}


def _level_words(norm):
    return set(_LEVEL_CANONICAL.get(w, w) for w in _LEVEL_WORDS_RE.findall(norm))


def _level_variant_mismatch(norm1, norm2):
    """Two names that each name a skill LEVEL, and name different ones.

    Requires a level word on BOTH sides: a bare "Excel Class" against "Excel
    Class: Advanced" is the ordinary fuller-title shape and must still merge.
    Subset relations are also allowed through ("Advanced Beginner Ballet" vs
    "Beginner Ballet" is one listing described twice), so only a genuine
    disagreement — beginner vs intermediate — blocks the match.
    """
    levels1 = _level_words(norm1)
    levels2 = _level_words(norm2)
    if not (levels1 and levels2):
        return False
    return not (levels1 <= levels2 or levels2 <= levels1)


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


# A trailing date/enumeration suffix ("Joonbug Dusk 08/02", "Ambient Music
# (2/3)") is the house style on Resident Advisor and posh.vip promoter feeds and
# on multi-session class listings: the SAME series name is republished once per
# date with the date appended. `get_significant_words` keeps only tokens of 3+
# chars, so "08/02" normalizes to "08 02" and BOTH halves are dropped — the
# suffix was invisible to every name rule, and two listings differing ONLY by it
# looked identical. That is how event 167515 ("Joonbug Dusk") swallowed 5 RA
# listings that already had rows 167517-167520 of their own.
#
# Slash and dot forms only, and the dot form must be zero-padded MM.DD:
#  - a hyphen range ("Ages 12-16", "Free Community Basketball ... Ages 11-14") is
#    far more often an age/level band than a date on this corpus,
#  - unpadded dots would read "Vol. 2.5" as February 5th.
_TRAILING_DATE_RE = re.compile(
    r'(?:^|[\s\-–—|,:(\[])'
    r'(?:'
    r'(?P<m1>\d{1,2})/(?P<d1>\d{1,2})'   # 8/16, 08/02, (2/3)
    r'|(?P<m2>\d{2})\.(?P<d2>\d{2})'     # 06.12
    r')'
    r'(?:[/.]\d{2,4})?'                  # optional /YY, /YYYY, .YY year tail
    r'\s*[)\]]?\s*$'
)


def _trailing_date_token(name):
    """Return a canonical 'MMDD' when `name` ENDS in a date-like suffix, else None.

    Deliberately anchored to the end of the name: a date embedded mid-name
    ("9/11 Memorial Tour") is part of the title, not a per-night discriminator.
    A name that is nothing but a date returns None — there is no series name to
    discriminate within.
    """
    if not name:
        return None
    stripped = name.strip()
    match = _TRAILING_DATE_RE.search(stripped)
    if not match:
        return None
    if match.group('m1') is not None:
        month, day = int(match.group('m1')), int(match.group('d1'))
    else:
        month, day = int(match.group('m2')), int(match.group('d2'))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    if not stripped[:match.start()].strip():
        return None
    return '%02d%02d' % (month, day)


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
    - Different trailing date suffixes ("... 08/02" vs "... 08/16")
    - A cinema "Fan Event" / "Fan First Screening" vs the film's regular run
    - Different sports opponents
    - A bare/umbrella name vs a more specific "Head: Subtitle" sibling
    """
    norm1 = normalize_name_for_dedup(name1)
    norm2 = normalize_name_for_dedup(name2)

    # Two listings that differ only by a trailing date suffix are different
    # nights of one series, never the same event. Fires only when BOTH names
    # carry a suffix: a bare series name ("Joonbug Dusk") against a dated
    # listing ("Joonbug Dusk 08/02") is the ordinary fuller-title shape and
    # still merges — the merger requires an overlapping date there anyway, so a
    # bare name can only absorb the night it actually shares dates with, while
    # two dated siblings by construction name two different nights.
    date1 = _trailing_date_token(name1)
    date2 = _trailing_date_token(name2)
    if date1 and date2 and date1 != date2:
        return True

    # Different gendered sports events (Men's vs Women's)
    # Use word boundaries to avoid false matches on substrings (e.g., "documentary" contains "men").
    # The optional trailing s is required because normalization now DELETES apostrophes, so
    # "Men's" arrives here as the single token "mens" rather than "men s" — without it this
    # guard silently stopped firing and "NYU Men's Basketball" matched "NYU Women's Basketball".
    # "womens" cannot satisfy \bmens?\b: the char before "mens" inside it is a word char.
    has_men1 = bool(re.search(r'\bmens?\b', norm1))
    has_men2 = bool(re.search(r'\bmens?\b', norm2))
    has_women1 = bool(re.search(r'\bwomens?\b', norm1))
    has_women2 = bool(re.search(r'\bwomens?\b', norm2))
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

    # A fan event / fan first screening vs the film's regular run — a distinct,
    # separately ticketed showing on its own date (see _FAN_SHOWING_RE).
    if bool(_FAN_SHOWING_RE.search(norm1)) != bool(_FAN_SHOWING_RE.search(norm2)):
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

    # Different set/part/volume numbers (Set 1 vs Set 2, Part 1 vs Part 2, Vol. 2 vs Vol. 3).
    # Spelled-out ordinals count too and canonicalize to the digit, because
    # libraries and studios write "Session One" / "Session Two" (BPL's "First
    # Five Years: Story and Play", w4) while sports write "Rounds 1 & 2" —
    # digits-only left those siblings merging on the shared series name.
    for keyword in ['set', 'part', 'vol', 'volume', 'chapter', 'session', 'round']:
        numbered_pattern = rf'\b{keyword}s?\.?\s*(\d+|{"|".join(_SPELLED_NUMBERS)})\b'
        match1 = re.search(numbered_pattern, norm1, re.IGNORECASE)
        match2 = re.search(numbered_pattern, norm2, re.IGNORECASE)
        if match1 and match2:
            num1 = _SPELLED_NUMBERS.get(match1.group(1).lower(), match1.group(1))
            num2 = _SPELLED_NUMBERS.get(match2.group(1).lower(), match2.group(1))
            if num1 != num2:
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

    # Sibling class listings that differ only by skill level. Regression
    # 2026-08-17 (NYPL/BPL "We Speak NYC" English conversation classes).
    if _level_variant_mismatch(norm1, norm2):
        return True

    # A private booking vs the public class it names (see _PRIVATE_BOOKING_RE).
    # Fires only when ONE side is marked private: two private parties named the
    # same way are left to the other rules. Regression 2026-08-17 (w1190).
    if bool(_PRIVATE_BOOKING_RE.search(norm1)) != bool(_PRIVATE_BOOKING_RE.search(norm2)):
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
    sibling_subtitles = False
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
                    # Sibling veto: an equal series HEAD with subtitles whose
                    # WORDS barely overlap means two sub-events of one program
                    # ("2026 Oscar Nominated Shorts: Animation" / ": Documentary",
                    # "Kids in Motion: <playground A>" / "<playground B>",
                    # "Author Talk with <X>" / "<Y>"). The shared head then
                    # outvotes the one distinguishing token in the containment
                    # tiers below (the dominant shape of the 2026-08-19 URL
                    # contamination, 21 of 37 wrong rows), so those tiers are
                    # switched off for this pair. Word-level corroboration keeps
                    # the legitimate variants the raw-substring test above is too
                    # strict for — an abbreviated lineup vs its full spelling
                    # ("Khraibani, Matuk, …" ⊂ "Sahar Khraibani, Farid Matuk, …"),
                    # a lineup that gained acts — by letting >= 0.75 of the
                    # smaller subtitle's stemmed words vouch for the pair, and the
                    # symmetric Jaccard tiers stay on either way (they judge whole
                    # names, so "&" vs "and" formatting twins still merge).
                    # Measured over all 33,829 distinct (event, crawl_event) name
                    # pairs (.scratch/nametier_measure.py, 2026-08-27): 498 pairs
                    # stop matching, 0 newly match. Hand-sampled ~150: dominated
                    # by genuinely distinct siblings (Oscar-shorts categories,
                    # library-festival sub-events, NYC Parks playground fleet,
                    # age cohorts); the losses are typo twins ("Carl Schruz") and
                    # TBD-vs-resolved World Cup placeholders, which degrade to
                    # duplicates /dedupe-events catches — the deliberate bias.
                    sub_words1 = get_significant_words(subtitle1, stem=True)
                    sub_words2 = get_significant_words(subtitle2, stem=True)
                    if sub_words1 and sub_words2:
                        smaller = min(len(sub_words1), len(sub_words2))
                        if len(sub_words1 & sub_words2) / smaller < 0.75:
                            sibling_subtitles = True
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
                    and len(_subtitle_content_words(short_split[1])) >= 2
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
        if not sibling_subtitles and _subset_match(words1, words2, name1, name2):
            return True

        # Jaccard similarity >= 70%
        ratio1, ratio2 = _drop_shared_weak_tokens(words1, words2)
        intersection = ratio1 & ratio2
        union = ratio1 | ratio2
        if union and len(intersection) / len(union) >= 0.7:
            return True

    # Try with stemmed words to catch variations like residency/residence
    stemmed1 = get_significant_words(name1, stem=True)
    stemmed2 = get_significant_words(name2, stem=True)

    if stemmed1 and stemmed2:
        if not sibling_subtitles and _subset_match(stemmed1, stemmed2, name1, name2, stem=True):
            return True

        # Both ratio tiers below run on the sets stripped of shared short
        # tokens; a name that is nothing but numbers and cohort labels the other
        # side also has carries no evidence at all.
        stemmed1, stemmed2 = _drop_shared_weak_tokens(stemmed1, stemmed2)
        if not (stemmed1 and stemmed2):
            return False
        intersection = stemmed1 & stemmed2
        union = stemmed1 | stemmed2
        if len(intersection) / len(union) >= 0.7:
            return True

        # Asymmetric containment: if 75%+ of the shorter name's words appear in the longer
        # Handles cases like "Jam Session" matching "TUES 8pm Jam Session. House band: ..."
        if not sibling_subtitles:
            shorter, longer = (stemmed1, stemmed2) if len(stemmed1) <= len(stemmed2) else (stemmed2, stemmed1)
            if len(shorter) >= 2 and len(intersection) / len(shorter) >= 0.75:
                return True

    return False


def _match_dateless_crawl_event(name, location_id, lat, lng, location_name,
                                existing_by_location_id, existing_by_coords,
                                existing_by_location, website_id=None,
                                existing_by_website=None):
    """Match a crawl_event that carries NO dates at all to an existing event.

    Long-running exhibitions are published without dates ("Ongoing", or a
    "Through Aug 22" line Gemini returns as null/null). The processor keeps such
    a row (`missing_date`) so the detail crawl can date it later — but when the
    detail page is dateless too, the crawl_event ends up with zero
    crawl_event_occurrences rows. Those crawl_events used to be invisible to the
    merger: the loader required a future occurrence, so they never linked to
    anything, and archival read the show as absent-from-crawl and archived it
    while it was still on the page (MoMA's `Marcel Duchamp`, e66269 — 73 sources
    and archived; six such shows in one 2026-07-26 crawl alone).

    Matching here is deliberately much stricter than the dated path: an EXACT
    normalized name at the crawl_event's OWN venue, and nothing else. A dated
    crawl_event can afford fuzzy names and a same-website fallback because a
    shared occurrence corroborates the guess; a dateless one has no second
    signal, and a wrong link silently resurrects an unrelated event (two
    galleries can both run a show called "Marcel Duchamp").

    Returns an event id or None. Never creates anything.
    """
    norm_name = normalize_name_for_dedup(name)
    if not norm_name:
        return None

    def _exact(candidates, enforce_location_id=False):
        for existing in candidates:
            if enforce_location_id and location_id is not None:
                existing_loc_id = existing.get('location_id')
                if existing_loc_id is not None and existing_loc_id != location_id:
                    continue
            if normalize_name_for_dedup(existing['name']) == norm_name:
                return existing['id']
        return None

    if location_id is not None:
        matched = _exact(existing_by_location_id.get(location_id, []))
        if matched:
            return matched

    if lat is not None and lng is not None:
        matched = _exact(existing_by_coords.get(_coord_key(lat, lng), []))
        if matched:
            return matched

    venue_known = location_id is not None
    if location_name:
        loc_key = normalize_name_for_dedup(location_name)
        if loc_key and len(loc_key) >= 3:
            candidates = existing_by_location.get(loc_key, [])
            if candidates:
                venue_known = True
            matched = _exact(candidates, enforce_location_id=True)
            if matched:
                return matched

    # Last tier, only for a crawl_event with NO usable venue signal at all (no
    # location_id, and a location_name no existing event uses — e.g. MoMA's
    # "MoMA Design Store Soho", a satellite venue that isn't in `locations`).
    # Same website + exact name, and ONLY when that pair is unambiguous: if the
    # site runs two identically-named shows, a dateless row cannot say which one
    # it is, and guessing would silently merge two venues' events.
    if not venue_known and website_id is not None and existing_by_website:
        hits = {existing['id'] for existing in existing_by_website.get(website_id, [])
                if normalize_name_for_dedup(existing['name']) == norm_name}
        if len(hits) == 1:
            return hits.pop()

    return None


def _match_by_url_identity(name, url, website_id, location_id, crawl_event_slots,
                           existing_by_url, url_name_counts, listing_url_keys,
                           location_coords):
    """Match a crawl_event to an existing event by SHARED URL — the tier that is
    deliberately exempt from the cross-location guard.

    Every other tier infers identity from a venue we resolved ourselves, so a
    listing page and a detail page describing the same event to different
    location rows never match, a duplicate is created, and the orphan is
    archived on the next run. The URL comes straight from the source and does
    not drift, so it can carry identity across a location disagreement.

    Because it bypasses the guard that stops the dominant over-merge (same
    program at many branches), every other signal is held at maximum strictness:

    - same website, and a URL that is NOT one of the website's crawl/listing
      URLs (those are shared by every event on the site),
    - the URL must carry at most URL_IDENTITY_MAX_DISTINCT_NAMES distinct
      normalized event names — more than that and it is a listing page we simply
      failed to recognise as one,
    - EXACT normalized name equality, never fuzzy similarity,
    - a shared occurrence SLOT (date + canonicalized start time), not merely an
      overlapping date range — two showtimes of one film on one day are distinct
      events and share a date but not a slot,
    - the two locations must be the same, unknown, or within
      URL_IDENTITY_MAX_KM of each other.

    When several events qualify, one sitting at the crawl_event's OWN location
    wins over a merely-nearby one (a cinema whose two branch rows both ended up
    holding one branch's URL must not have the wrong branch picked), and ties
    break to the lowest id so the choice is deterministic and prefers the oldest
    row. Returns an event id, or None.
    """
    if not url or website_id is None or not crawl_event_slots:
        return None
    url_key = normalize_url_for_identity(url)
    if not url_key:
        return None
    index_key = (website_id, url_key)
    if index_key in listing_url_keys:
        return None
    if url_name_counts.get(index_key, 0) > URL_IDENTITY_MAX_DISTINCT_NAMES:
        return None

    norm_name = normalize_name_for_dedup(name)
    if not norm_name:
        return None

    best = None  # (0 if same location_id else 1, event_id)
    for existing in existing_by_url.get(index_key, []):
        if normalize_name_for_dedup(existing['name']) != norm_name:
            continue
        if not (crawl_event_slots & existing['slots']):
            continue
        existing_loc_id = existing.get('location_id')
        if not _locations_within(location_id, existing_loc_id, location_coords):
            continue
        rank = (0 if (location_id is not None and existing_loc_id == location_id) else 1,
                existing['id'])
        if best is None or rank < best:
            best = rank
    return best[1] if best else None


def _event_has_live_occurrence(cursor, event_id, current_date):
    """True when the event still has a current or future occurrence.

    Gates the un-archive on a dateless link: "the venue still lists this" is
    reason enough to record a source, but not to put a finished run back on the
    map. An archived event with only past occurrences stays archived — its
    fresh event_sources row simply stops archival from re-firing on it.
    """
    cursor.execute(
        "SELECT 1 FROM event_occurrences WHERE event_id = %s "
        "  AND (start_date >= %s OR (end_date IS NOT NULL AND end_date >= %s)) LIMIT 1",
        (event_id, current_date, current_date),
    )
    return cursor.fetchone() is not None


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


def _norm_location_label(name):
    """Conservative comparison form for a location LABEL — case/whitespace only.

    Deliberately NOT `normalize_name_for_dedup`: this decides whether a stored
    label is byte-for-byte our own copy of a `locations.name`, so anything
    fuzzier ("The Foo" ≡ "Foo") would start matching source-written strings.
    """
    return (name or '').strip().lower()


def resolve_stale_location_name(stored_name, current_location_id, location_names_by_id,
                                source_location_ids, source_raw_names):
    """Return the canonical name `events.location_name` should be rewritten to, or None.

    THE BUG: `location_name` is set to `locations.name` of the then-current
    `location_id` on event CREATION only. The merge path refreshes it only when it
    is NULL/'Not specified'/''. So once an event's `location_id` is corrected —
    by a later merge, by `/fix-unmapped-events`, by a repin script — the displayed
    label FREEZES at the *previous* location's canonical name.

    THE NAIVE FIX WAS MEASURED AND REJECTED (2026-08-09): refreshing from
    `locations.name` on every merge overwrites correct, more-specific EXTRACTED
    labels with a generic row name. A global scan found 3874 events (106 live)
    where `location_name` merely equals the `locations.name` of some *other*
    location row, and that population is dominated by legitimate coincidences —
    a source that genuinely wrote "Harlem" / "Park Slope" / "Chelsea", which also
    happen to be neighborhood rows in `locations`.

    THE DISCRIMINATOR: rewrite only when the stored label is provably OUR OWN
    canonical copy rather than a source string, i.e. both of:
      1. no crawl_event feeding this event ever emitted that raw string
         (`source_raw_names`) — if any source wrote it, the label is the
         source's, not ours, and must stand; and
      2. the label exactly equals `locations.name` of a location one of this
         event's own crawl_events resolved to (`source_location_ids`) — the
         "frozen at the previous location's canonical name" signature proven on
         the SAPO block parties.
    Measured on live data: 3874 rows pass the naive test, 39 live rows pass this
    one, and hand-inspection of all 39 found no correct label rewritten.
    """
    if not current_location_id:
        return None
    canonical = location_names_by_id.get(current_location_id)
    if not canonical:
        return None
    stored = _norm_location_label(stored_name)
    if not stored or stored in ('not specified',):
        return None
    if stored == _norm_location_label(canonical):
        return None  # already in sync
    if any(stored == _norm_location_label(raw) for raw in source_raw_names):
        return None  # a source wrote this exact string — it is not our copy
    if any(stored == _norm_location_label(location_names_by_id.get(lid))
           for lid in source_location_ids if lid):
        return canonical
    return None


def _demote_other_primary_urls(cursor, event_id, keep_id=None):
    """Ensure at most one `event_urls` row for `event_id` keeps sort_order = 0.

    The exporter orders an event's URLs by `sort_order` alone, so two rows at 0
    make the published link query-plan-dependent — the user can get either one.
    Call this immediately BEFORE promoting/inserting a new primary URL: every
    other row currently at 0 is pushed to the end of the ordering (max + 1, 2, …)
    so the incoming URL is the sole primary and the demoted ones keep a stable,
    distinct rank instead of all colliding on one value.
    """
    cursor.execute(
        "SELECT id FROM event_urls WHERE event_id = %s AND sort_order = 0 ORDER BY id",
        (event_id,),
    )
    stale = [row[0] for row in cursor.fetchall() if row[0] != keep_id]
    if not stale:
        return 0
    cursor.execute(
        "SELECT COALESCE(MAX(sort_order), 0) FROM event_urls WHERE event_id = %s",
        (event_id,),
    )
    next_order = cursor.fetchone()[0]
    for row_id in stale:
        next_order += 1
        cursor.execute(
            "UPDATE event_urls SET sort_order = %s WHERE id = %s", (next_order, row_id)
        )
    return len(stale)


# A meridiem-less 1-11 o'clock ('6:50', '7', '7:00'). processor._standardize_time
# deliberately leaves these alone — a bare '7:00' is as plausibly 7am as 7pm, and
# guessing PM is the documented trap. But the same showtime routinely arrives twice
# from one site, once bare and once qualified (Film Forum listed "Late Fame" at
# both '6:50' and '6:50pm' on 2026-08-07), and the two spellings are different
# dedupe keys, so both rows land. The bare form carries strictly less information,
# so it loses to its own am/pm twin exactly the way a dateless row loses to a timed
# one. No AM/PM is ever inferred: without a twin the bare value is stored unchanged.
_BARE_CLOCK_RE = re.compile(r'^(\d{1,2})(?::([0-5]\d))?$')
_QUALIFIED_CLOCK_RE = re.compile(r'^(\d{1,2})(?::([0-5]\d))?(am|pm)$')


def _bare_clock_twins(start_time):
    """The am/pm spellings a bare, meridiem-less start_time could stand for."""
    m = _BARE_CLOCK_RE.match(start_time or '')
    if not m:
        return ()
    hour = int(m.group(1))
    if not 1 <= hour <= 11:
        return ()  # 0/12/13-23 are unambiguous and already canonicalized
    minute = m.group(2)
    face = f'{hour}:{minute}' if minute and minute != '00' else str(hour)
    return (f'{face}am', f'{face}pm')


def _qualified_clock_bare_forms(start_time):
    """The bare spellings that a canonical am/pm start_time supersedes."""
    m = _QUALIFIED_CLOCK_RE.match(start_time or '')
    if not m:
        return ()
    hour = int(m.group(1))
    if not 1 <= hour <= 11:
        return ()
    minute = m.group(2)
    if minute and minute != '00':
        return (f'{hour}:{minute}',)
    return (str(hour), f'{hour}:00')


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

        # A bare, meridiem-less clock face loses to its own am/pm twin.
        if any(twin in existing_starts for twin in _bare_clock_twins(new_st)):
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

        # Symmetric case: a qualified time arriving over an already-stored bare
        # twin. Drop the bare row so the pair collapses whichever order they land.
        for bare in _qualified_clock_bare_forms(new_st):
            if bare not in existing_starts:
                continue
            if ed is None:
                cursor.execute(
                    "DELETE FROM event_occurrences WHERE event_id = %s "
                    "AND start_date = %s AND start_time = %s AND end_date IS NULL",
                    (event_id, sd, bare),
                )
            else:
                cursor.execute(
                    "DELETE FROM event_occurrences WHERE event_id = %s "
                    "AND start_date = %s AND start_time = %s AND end_date = %s",
                    (event_id, sd, bare, ed),
                )
            existing_by_key.pop((sd, bare, ed), None)
            existing_starts.discard(bare)

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

    # URL identity for the archived-twin absorption below: a stale twin that
    # shares the keeper's event URL is the same event however its venue string
    # happened to resolve. Same guards as the URL-identity tier — the website's
    # own listing URLs and URLs carrying many distinct event names are excluded,
    # because those are shared by every event on the site and would fuse a
    # multi-branch program's twins. See _match_by_url_identity.
    dup_ids = sorted({eid for _key, ids in dup_groups for eid in ids})
    event_url_keys = {}
    url_key_names = {}
    listing_url_keys = set()
    cursor.execute("SELECT website_id, url FROM website_urls")
    for site_id, site_url in cursor.fetchall():
        key = normalize_url_for_identity(site_url)
        if key:
            listing_url_keys.add((site_id, key))
    placeholders = ','.join(['%s'] * len(dup_ids))
    cursor.execute(f"""
        SELECT eu.event_id, eu.url, e.website_id, e.name
        FROM event_urls eu
        JOIN events e ON e.id = eu.event_id
        WHERE eu.event_id IN ({placeholders})
    """, tuple(dup_ids))
    for event_id, event_url, site_id, event_name in cursor.fetchall():
        key = normalize_url_for_identity(event_url)
        if not key or site_id is None:
            continue
        index_key = (site_id, key)
        if index_key in listing_url_keys:
            continue
        event_url_keys.setdefault(event_id, set()).add(index_key)
        url_key_names.setdefault(index_key, set()).add(
            normalize_name_for_dedup(event_name or '')
        )
    shared_url_keys = {
        k for k, names in url_key_names.items()
        if len(names) <= URL_IDENTITY_MAX_DISTINCT_NAMES
    }
    cursor.execute("SELECT id, lat, lng FROM locations")
    location_coords = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

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

        # The keeper inherits the twin's crawl history, so judged tag blocks
        # must carry over or re-crawl votes could re-apply a removed tag.
        cursor.execute("""
            INSERT IGNORE INTO event_tag_blocks (event_id, tag_id, reason)
            SELECT %s, tag_id, reason FROM event_tag_blocks WHERE event_id = %s
        """, (keep_id, remove_id))

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
        # same location_id, NULL on either side, the same extracted
        # location_name (the drift case — an identical venue string mapped to
        # different location rows across crawls), or a shared event URL at a
        # nearby venue (the same drift seen from the source's side, which is the
        # only signal that survives when BOTH the location row and the extracted
        # venue string changed). Twins whose extracted venue strings genuinely
        # differ AND that sit at unrelated venues (multi-branch programs sharing
        # a time slot) stay untouched.
        for dead_id in stale:
            dead_loc = event_location.get(dead_id)
            dead_loc_name = event_loc_name.get(dead_id, '')
            dead_urls = event_url_keys.get(dead_id, set())
            for cl in clusters:
                keep_id = cl[0]
                if frozenset((keep_id, dead_id)) in dismissed_pairs:
                    continue
                loc_compatible = cl[1] is None or dead_loc is None or cl[1] == dead_loc
                name_compatible = bool(dead_loc_name) and dead_loc_name == event_loc_name.get(keep_id, '')
                url_compatible = (
                    bool(dead_urls & event_url_keys.get(keep_id, set()) & shared_url_keys)
                    and _locations_within(dead_loc, cl[1], location_coords)
                )
                if not (loc_compatible or name_compatible or url_compatible):
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
          AND (
              EXISTS (
                  SELECT 1 FROM crawl_event_occurrences ceo
                  WHERE ceo.crawl_event_id = ce.id
                    AND (ceo.start_date >= %s OR (ceo.end_date IS NOT NULL AND ceo.end_date >= %s))
              )
              OR (
                  -- Dateless listing: an "Ongoing" exhibition whose detail page
                  -- is dateless too ends up with NO occurrence rows at all. It
                  -- can still say "this show is still listed" by linking to its
                  -- existing event (see _match_dateless_crawl_event), which is
                  -- what stops archival from burying long-running shows.
                  --
                  -- Tightly bounded on purpose: only from the website's most
                  -- recent crawl and only recently. ~27k such crawl_events sit
                  -- in the historical backlog, and replaying those would link
                  -- long-superseded listings and resurrect finished runs.
                  NOT EXISTS (
                      SELECT 1 FROM crawl_event_occurrences ceo2
                      WHERE ceo2.crawl_event_id = ce.id
                  )
                  AND cr.processed_at >= %s
                  AND cr.id = (
                      SELECT MAX(cr2.id) FROM crawl_results cr2
                      WHERE cr2.website_id = cr.website_id
                        AND cr2.status IN ('processed', 'extracted')
                  )
              )
          )
    """
    dateless_cutoff = datetime.now() - timedelta(days=DATELESS_MERGE_WINDOW_DAYS)
    merge_params = [current_date, current_date, dateless_cutoff]
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
    cursor.execute("SELECT id, name, emoji, lat, lng FROM locations")
    location_rows = cursor.fetchall()
    location_names_by_id = {row[0]: row[1] for row in location_rows}
    # Reverse index used only as a cheap pre-filter for the stale-label refresh
    # below: a label that matches no location row at all can never be our copy.
    location_norm_names = {_norm_location_label(row[1]) for row in location_rows}
    # Venue emoji fallback: events whose extraction (listing or detail crawl)
    # returned no emoji inherit their venue's emoji so they never render blank.
    location_emoji_by_id = {row[0]: row[2] for row in location_rows}
    # Coordinates for the URL-identity tier's proximity guard.
    location_coords = {row[0]: (row[3], row[4]) for row in location_rows}

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

    # ── Build the URL-identity index (see _match_by_url_identity) ──
    # (website_id, normalized url) -> candidate events, plus the number of
    # distinct normalized event names behind that URL (the listing-page tell)
    # and the set of keys that ARE the website's own crawl/listing URLs.
    existing_events_by_url = {}
    url_key_names = {}
    listing_url_keys = set()
    cursor.execute("SELECT website_id, url FROM website_urls")
    for row in cursor.fetchall():
        key = normalize_url_for_identity(row[1])
        if key:
            listing_url_keys.add((row[0], key))
    if event_ids_with_future:
        placeholders = ','.join(['%s'] * len(event_ids_with_future))
        cursor.execute(f"""
            SELECT eu.event_id, eu.url, e.name, e.website_id, e.location_id
            FROM event_urls eu
            JOIN events e ON e.id = eu.event_id
            WHERE eu.event_id IN ({placeholders})
        """, tuple(event_ids_with_future))
        for event_id, event_url, event_name, event_website_id, event_location_id in cursor.fetchall():
            if event_website_id is None or not event_name:
                continue
            url_key = normalize_url_for_identity(event_url)
            if not url_key:
                continue
            index_key = (event_website_id, url_key)
            url_key_names.setdefault(index_key, set()).add(
                normalize_name_for_dedup(event_name)
            )
            slots = event_slots.get(event_id)
            if not slots:
                continue
            existing_events_by_url.setdefault(index_key, []).append({
                'id': event_id,
                'name': event_name,
                'location_id': event_location_id,
                'slots': slots,
            })
    url_key_name_counts = {k: len(v) for k, v in url_key_names.items()}

    # ── Match crawl events to existing events or create new ones ──
    new_events_count = 0
    merged_count = 0
    source_url_lookup_cache = {}  # website_id -> set of trimmed listing URLs

    # Imported here, not at module scope, to keep `merger` importable without
    # pulling in crawl4ai (processor -> crawler) — same reason as
    # `_standardize_time` below.
    from processor import canonicalize_luma_host

    for ce_row in new_crawl_events:
        ce_id, name, short_name, description, emoji, location_name, sublocation, location_id, url, website_id, lat, lng = ce_row

        # Host aliases must be folded before the URL is compared to, or stored
        # alongside, an event's existing links: `already_present` below is an
        # exact string match, so an un-canonicalized `lu.ma/<slug>` would insert
        # a second row for a page the event already links to (and demote the
        # canonical one off sort_order 0). New crawls are canonicalized by
        # `processor.absolutize_url`; this covers crawl_events written before it.
        url = canonicalize_luma_host(url)

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

        # A crawl_event with NO occurrence rows at all is a dateless listing
        # (see _match_dateless_crawl_event). It is handled on a restricted path:
        # it may link to an existing event, but never creates one — inventing a
        # date for an undated listing would drop arbitrary events onto the map.
        dateless = not occurrences

        if not valid_occurrences and not dateless:
            # Had dates, none of them current/future — skip
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

        if dateless:
            # Exact name at this crawl_event's own venue, or nothing. No fuzzy
            # names, no coordinate-less website fallback, no creation.
            matched_event_id = _match_dateless_crawl_event(
                name, location_id, lat, lng, location_name,
                existing_events_by_location_id, existing_events_by_coords,
                existing_events_by_location, website_id, existing_events_by_website,
            )
            if matched_event_id is None:
                continue

        # Try matching by location_id first (most precise and reliable).
        # Allow no-date-overlap match here only: same venue + exact name is a
        # strong-enough signal to merge a recurring event whose old occurrences
        # have lapsed before the new crawl extracted fresh dates.
        if matched_event_id is None and location_id is not None and location_id in existing_events_by_location_id:
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

        # URL-identity tier — the ONE tier exempt from the guard above, and the
        # last one to run, so it only ever rescues a crawl_event that would
        # otherwise have created a duplicate row (it can never steal a match
        # another tier already made). Its own guards are stricter than any other
        # tier's; see _match_by_url_identity. Dateless crawl_events carry no
        # slots and are deliberately out of scope.
        if matched_event_id is None and not dateless:
            matched_event_id = _match_by_url_identity(
                name, url, website_id, location_id, crawl_event_slots,
                existing_events_by_url, url_key_name_counts, listing_url_keys,
                location_coords,
            )
            if matched_event_id is not None and location_id is not None:
                cursor.execute("SELECT location_id FROM events WHERE id = %s", (matched_event_id,))
                _m = cursor.fetchone()
                current_loc_id = _m[0] if _m else None

        # A dateless crawl_event that HAD a match and lost it to the cross-location
        # guard above must not fall through to the create-new branch: it carries no
        # occurrences, so the new event would be created with ZERO occurrence rows —
        # invisible on the map (the exporter needs a date) yet still absorbing
        # event_sources, participating in dedup, and counting against archival. The
        # no-match case already `continue`s inside the dateless block; this closes the
        # guard-rejected case so the rule "a dateless listing never creates an event"
        # holds on every path.
        if dateless and matched_event_id is None:
            continue

        if matched_event_id:
            # Merge with existing event
            # Un-archive event if it was previously archived (event found in new crawl).
            # A dateless link brings no date of its own, so it may only revive an
            # event that still has a current/future occurrence — otherwise the
            # source row is recorded (which is what stops archival re-firing)
            # while a genuinely finished run stays archived.
            if not dateless or _event_has_live_occurrence(cursor, matched_event_id, current_date):
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
                        _demote_other_primary_urls(
                            cursor, matched_event_id, keep_id=already_present[0]
                        )
                        cursor.execute(
                            "UPDATE event_urls SET sort_order = 0 WHERE id = %s",
                            (already_present[0],)
                        )
                    else:
                        # Only one row may hold sort_order=0 — the exporter breaks
                        # ties arbitrarily, so demote any incumbent primary first.
                        _demote_other_primary_urls(cursor, matched_event_id)
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
            effective_location_id = current_loc_id
            if location_id:
                current_location_id = current_loc_id
                if not current_location_id or (
                    current_location_id != location_id and
                    website_id in website_location_ids and
                    location_id in website_location_ids[website_id]
                ):
                    cursor.execute("UPDATE events SET location_id = %s WHERE id = %s", (location_id, matched_event_id))
                    effective_location_id = location_id

            # Update location_name/sublocation if currently missing or placeholder
            cursor.execute(
                "SELECT location_name, location_id FROM events WHERE id = %s",
                (matched_event_id,),
            )
            result = cursor.fetchone()
            current_loc = result[0] if result else None
            if result and result[1] is not None:
                effective_location_id = result[1]
            if location_name and location_name not in ('Not specified', ''):
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
                    current_loc = location_name

            # Refresh a POPULATED-but-STALE location_name. The label is only
            # rewritten when it is provably our own copy of some *other*
            # location's canonical name rather than a string a source wrote —
            # see resolve_stale_location_name for the discriminator and for why
            # the unconditional refresh was measured and rejected on 2026-08-09.
            # The cheap in-memory pre-filter below keeps the extra query off the
            # ~92% of merges whose label matches no location row at all.
            if (current_loc and effective_location_id
                    and _norm_location_label(current_loc) in location_norm_names
                    and _norm_location_label(current_loc)
                        != _norm_location_label(location_names_by_id.get(effective_location_id))):
                cursor.execute("""
                    SELECT ce.location_id, ce.location_name
                    FROM event_sources es
                    JOIN crawl_events ce ON ce.id = es.crawl_event_id
                    WHERE es.event_id = %s
                """, (matched_event_id,))
                src_rows = cursor.fetchall()
                src_loc_ids = [r[0] for r in src_rows]
                src_raw_names = [r[1] for r in src_rows]
                src_raw_names.append(location_name)  # this crawl_event's raw string
                refreshed = resolve_stale_location_name(
                    current_loc, effective_location_id, location_names_by_id,
                    src_loc_ids, src_raw_names,
                )
                if refreshed:
                    cursor.execute(
                        "UPDATE events SET location_name = %s WHERE id = %s",
                        (refreshed[:255], matched_event_id),
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

                # Keep the URL index current too: within a single merge the
                # listing crawl_event and the detail crawl_event of the SAME
                # event arrive back to back, so without this the pair that the
                # URL tier exists to fuse would still create two rows.
                new_url_key = normalize_url_for_identity(url)
                if new_url_key and crawl_event_slots:
                    index_key = (website_id, new_url_key)
                    names_at_key = url_key_names.setdefault(index_key, set())
                    names_at_key.add(norm_name)
                    url_key_name_counts[index_key] = len(names_at_key)
                    existing_events_by_url.setdefault(index_key, []).append({
                        **event_entry,
                        'location_id': location_id,
                        'slots': crawl_event_slots,
                    })

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

        # Precompute the archival helper temp tables ONCE for the whole loop so
        # each per-website archive query is a ~1s indexed lookup rather than a
        # ~35s scan (this loop was the dominant cost of Step 6 — 47min on a full
        # run). See db.build_archival_temps for the correctness argument.
        db.build_archival_temps(cursor)
        try:
            for website_id in website_ids:
                archived_count, upcoming_events = _retry_on_deadlock(
                    db.archive_outdated_events, cursor, connection, website_id, temps_built=True)
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

            # Events whose every source website is now disabled are unreachable
            # from the per-website loop above (a disabled website is never
            # crawled, so no iteration ever runs for it). Sweep them once per
            # merge. See db.archive_dead_source_events.
            dead_archived, dead_upcoming = _retry_on_deadlock(
                db.archive_dead_source_events, cursor, connection, temps_built=True)
            if dead_archived > 0:
                print(f"  Archived {dead_archived} event(s) whose source websites are all disabled")
                total_archived += dead_archived
                if dead_upcoming:
                    print(f"    ⚠️  WARNING: {len(dead_upcoming)} upcoming event(s) among them:")
                    for event_id, name, next_occ in dead_upcoming:
                        print(f"        - Event {event_id}: {name} (next: {next_occ})")
                    total_upcoming_flagged += len(dead_upcoming)
        finally:
            db.drop_archival_temps(cursor)

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
