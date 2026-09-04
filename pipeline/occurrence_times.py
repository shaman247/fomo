"""Canonical form of an occurrence time string, and the one place it is defined.

Format: compact lowercase 12-hour with no space and no `:00` — '7pm',
'7:30pm', '11am', '12am' (midnight), '12pm' (noon). Empty and sentinel values
('allday', 'tba', …) normalize to ''.

Every write into `event_occurrences` / `crawl_event_occurrences` goes through
`db.insert_event_occurrences` / `db.insert_crawl_event_occurrences`, which call
`standardize_time` on both time columns — so a stored time is always a fixed
point of this function, and readers never need to re-normalize. (Verified over
the whole corpus on 2026-09-04: 0 of 478 distinct `event_occurrences` start
times moved; the 12 raw `crawl_event_occurrences` forms were backfilled.)

Dependency-free on purpose: `merger` imports it without pulling in crawl4ai.
"""
import re

TZ_SUFFIX_RE = re.compile(r'(est|edt|pst|pdt|mst|mdt|cst|cdt|et|pt|mt|ct)$')
TWELVE_HOUR_RE = re.compile(r'^(\d{1,2})(?::(\d{2}))?(am|pm)$')
HHMM_RE = re.compile(r'^(\d{1,2}):(\d{2})$')
HH_RE = re.compile(r'^(\d{1,2})$')
# 'HH:MM:SS' (MySQL TIME columns, ISO clock strings). None of the patterns above
# match it, so it used to fall through unchanged and land in event_occurrences
# next to its own canonical 12-hour form — 79 duplicate twin rows accumulated
# that way. Drop the seconds field and re-run the normal cascade.
SECONDS_RE = re.compile(r'^(\d{1,2}:\d{2}):[0-5]\d(am|pm)?$')
SENTINEL_TIMES = frozenset({
    '', 'allday', 'allday/varies', 'varioustimes', 'multipletimes', 'tba', 'tbd',
    'none', 'close', 'closing', 'late', 'tbc', 'ongoing', 'sundown', 'sunrise',
    'sunset', 'dusk', 'dawn',
})


def canonical_time(hour, minute, is_pm):
    """Build a canonical time string from a 12-hour hour (1-12), minute, and AM/PM."""
    suffix = 'pm' if is_pm else 'am'
    return f'{hour}{suffix}' if minute == 0 else f'{hour}:{minute:02d}{suffix}'


def standardize_time(time_str):
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
    if s in SENTINEL_TIMES:
        return ''

    # Strip US timezone suffixes (1pmest, 7pmet, etc.)
    s = TZ_SUFFIX_RE.sub('', s)
    if not s:
        return ''

    # '19:30:00' -> '19:30', '7:30:00pm' -> '7:30pm'
    m = SECONDS_RE.match(s)
    if m:
        s = m.group(1) + (m.group(2) or '')

    m = TWELVE_HOUR_RE.match(s)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2) or 0)
        if 1 <= h <= 12 and 0 <= mi <= 59:
            return canonical_time(h, mi, m.group(3) == 'pm')
        return s  # malformed (e.g. '13pm'); preserve so it's findable

    m = HHMM_RE.match(s)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            # Unambiguous 24-hour values: hour 0 (midnight), hour 12 (noon), hour 13-23.
            # Hour 1-11 in HH:MM with no AM/PM is ambiguous; leave alone.
            if h == 0:
                return canonical_time(12, mi, False)
            if h == 12:
                return canonical_time(12, mi, True)
            if h >= 13:
                return canonical_time(h - 12, mi, True)
            return s

    m = HH_RE.match(s)
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
                return canonical_time(h - 12, 0, True)
            if has_leading_zero:
                return canonical_time(h, 0, False)  # '08' -> '8am'
            return s  # bare '6' is ambiguous; leave alone

    return s  # unrecognized; preserve original text (normalized whitespace/case)
