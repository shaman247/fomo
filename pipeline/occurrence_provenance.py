"""Publisher all-day evidence bound to exact source occurrences (BL12).

Two narrow facts about "no clock time" travel through the pipeline here:

1. **Explicit publisher flags.** A source plugin that copies a calendar API's
   strict per-record ``all_day`` Boolean into the explicit-occurrence grammar
   (below) lets the processor bind that flag to the exact grouped occurrence it
   describes. A bound ``true`` turns the API's full-day boundary (``12am`` to
   ``11:59pm``) into blank clocks; a bound ``false`` protects a real midnight
   start from every placeholder heuristic. The binding is recorded per
   occurrence in ``crawl_events.raw_data["occurrence_provenance"]`` together
   with the record ID, original URL, title, source timestamps and capture
   identity, so a later merge can tell which slot the claim covers and when it
   was observed. Model output alone never creates or changes a claim.

2. **The full-day placeholder pair.** ``12am``–``11:59pm`` is how WordPress
   calendars print an all-day listing ("Sun, October 18 at 12:00 AM – Sun,
   October 18 at 11:59 PM"), and how earlier extractions spelled "All Day".
   It carries no attendance clock. The merger therefore never lets it demote a
   blank row for the same dates, and retires a stored placeholder row only when
   the same publisher's own page (website + URL) later reported that exact
   date span without clocks. See ``plan_placeholder_retirement``.

Everything else -- partial midnight starts, ``12am``–``3am`` programs, other
publishers' clocks, legacy rows with no attributable source -- keeps the
ordinary merge behavior. Nothing here infers ``true`` from midnight boundaries.

Dependency-free apart from ``occurrence_times`` so tests can import it alone.
"""
import hashlib
import json
import re

from occurrence_times import standardize_time

VERSION = 1
PROVENANCE_KEY = 'occurrence_provenance'

# Endpoints the processor synthesized rather than read from the source:
# an end-only run ("Through Nov 1") gets today's date as its start, and a
# start-only open run ("Opened May 28") gets today + OPEN_RUN_HORIZON_DAYS as
# its end. Neither is a published date.
START_AS_OF_CRAWL = 'start_as_of_crawl'
OPEN_RUN_HORIZON_DAYS = 60  # processor.OPEN_RUN_HORIZON_DAYS is this value
END_OPEN_RUN_HORIZON = 'end_open_run_horizon'

# Canonical clocks of the full-day placeholder: 00:00 -> 23:59 / 23:59:59
# both standardize to these. 12am alone (unknown end) is NOT a placeholder.
PLACEHOLDER_START = '12am'
PLACEHOLDER_END = '11:59pm'

# ---------------------------------------------------------------------------
# Explicit-occurrence grammar (version 0, emitted by sources/tribe_window.py):
#
#   ### [<title>](<url>)
#
#   {"title": "<title>", ..., "all_day": true|false|null, "timezone": "...",
#    "venues": [{"venue": "..."}...]}
#
#   Explicit source occurrences (start / end / original URL / source ID):
#
#   - YYYY-MM-DD HH:MM:SS / YYYY-MM-DD HH:MM:SS / <url> / <id>
#   - ...
#
# Paragraphs are separated by a blank line. Any deviation -- metadata title
# different from the heading, non-dict JSON, a non-Boolean flag, a malformed
# occurrence line -- makes that group's flag unknown. Nothing is scanned out of
# free text, so a page-wide "all_day=true" phrase is never evidence.
# ---------------------------------------------------------------------------
GRAMMAR_HEADER = 'Explicit source occurrences (start / end / original URL / source ID):'
_HEADING_RE = re.compile(r'^### \[(?P<title>.+)\]\((?P<url>\S+)\)$')
_LINE_RE = re.compile(
    r'^- (?P<sd>\d{4}-\d{2}-\d{2}) (?P<sc>\d{2}:\d{2}(?::\d{2})?) / '
    r'(?P<ed>\d{4}-\d{2}-\d{2}) (?P<ec>\d{2}:\d{2}(?::\d{2})?) / '
    r'(?P<url>\S+) / (?P<id>\S+)$')


def is_full_day_placeholder(start_time, end_time):
    """True for the exact 12am -> 11:59pm boundary pair (any spelling)."""
    return (standardize_time(start_time) == PLACEHOLDER_START
            and standardize_time(end_time) == PLACEHOLDER_END)


def strict_url_key(url):
    """Exact page identity: scheme, www, fragment, case and trailing slash only.

    Deliberately stricter than merger.normalize_url_for_identity -- a dated
    instance path (/event/x/2026-10-02/) stays distinct from its series page.
    """
    if not url:
        return ''
    cleaned = url.strip().split('#', 1)[0]
    cleaned = re.sub(r'^https?://', '', cleaned, flags=re.I)
    cleaned = re.sub(r'^www\.', '', cleaned, flags=re.I)
    return cleaned.rstrip('/').lower()


def title_key(title):
    text = (title or '').lower().replace('&', ' and ')
    text = re.sub(r'[‘’“”\'"]', '', text)
    return re.sub(r'[^0-9a-z]+', ' ', text).strip()


def titles_compatible(source_title, event_name):
    """Exact normalized title, or one fully containing the other.

    A parent exhibition's flag must not attach to a child tour sharing its URL
    ("... Juried Art Competition" vs "...: Awards & Reception" fails).
    """
    a, b = title_key(source_title), title_key(event_name)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short.split()) >= 2 and f' {short} ' in f' {long_} ' and (
        long_.endswith(short) or long_.startswith(short))


def parse_explicit_records(content):
    """Return the grammar's per-occurrence records found in captured content."""
    if not content or GRAMMAR_HEADER not in content:
        return []
    paragraphs = [p.strip() for p in content.split('\n\n')]
    records = []
    i = 0
    while i < len(paragraphs):
        heading = _HEADING_RE.match(paragraphs[i])
        if not (heading and i + 2 < len(paragraphs)
                and paragraphs[i + 2] == GRAMMAR_HEADER):
            i += 1
            continue
        try:
            metadata = json.loads(paragraphs[i + 1])
        except ValueError:
            metadata = None
        j = i + 3
        lines = []
        while j < len(paragraphs) and paragraphs[j].startswith('- '):
            lines.append(paragraphs[j])
            j += 1
        valid = isinstance(metadata, dict) and metadata.get('title') == heading['title']
        flag = metadata.get('all_day') if isinstance(metadata, dict) else None
        if not valid or not isinstance(flag, bool):
            flag = None  # malformed, string-valued or absent: unknown
        venues = []
        if isinstance(metadata, dict) and isinstance(metadata.get('venues'), list):
            venues = sorted({(v.get('venue') or '').strip() for v in metadata['venues']
                             if isinstance(v, dict) and (v.get('venue') or '').strip()})
        for line in lines:
            m = _LINE_RE.match(line)
            if not m:
                continue  # one malformed line never borrows a neighbor's identity
            digest = hashlib.sha256('\n\n'.join(
                (paragraphs[i], paragraphs[i + 1], line)).encode('utf-8')).hexdigest()
            records.append(dict(
                title=heading['title'], event_url=m['url'], record_id=m['id'],
                start_date=m['sd'], start_clock=m['sc'], end_date=m['ed'],
                end_clock=m['ec'], all_day=flag,
                timezone=metadata.get('timezone') if isinstance(metadata, dict) else None,
                venues=venues, sha256=digest))
        i = j
    return records


def index_records(records):
    """{(strict url key, start date, end date): [records]} for binding."""
    index = {}
    for record in records:
        key = (strict_url_key(record['event_url']), record['start_date'], record['end_date'])
        index.setdefault(key, []).append(record)
    return index


def _slot(occ):
    sd = occ[0] if len(occ) > 0 else ''
    st = standardize_time(occ[1] if len(occ) > 1 else '')
    ed = (occ[2] if len(occ) > 2 else '') or ''
    et = standardize_time(occ[3] if len(occ) > 3 else '')
    if ed == sd:
        ed = ''
    return [str(sd or ''), st, str(ed or ''), et]


def bind_event(event, index, capture):
    """Bind explicit records to one grouped event's occurrences, in place.

    ``capture`` = {'crawl_result_id', 'observed_at'}. Returns the sidecar dict
    (also stored on ``event[PROVENANCE_KEY]``) or None when nothing bound.
    Only a bound ``true`` with blank or full-day-boundary clocks changes a
    slot (to blank clocks). Dates are never changed.
    """
    if not index:
        return None
    url_keys = {strict_url_key(u) for u in (event.get('urls') or []) if u}
    url_keys.discard('')
    entries, conflicts = [], []
    occurrences = event.get('occurrences') or []
    for position, occ in enumerate(occurrences):
        if not occ or not occ[0]:
            continue
        slot = _slot(occ)
        end_day = slot[2] or slot[0]
        candidates = [r for key in url_keys
                      for r in index.get((key, slot[0], end_day), ())]
        if not candidates:
            continue
        reason = None
        titled = [r for r in candidates if titles_compatible(r['title'], event.get('name'))]
        if not titled:
            reason = 'title_mismatch'
        else:
            flags = {r['all_day'] for r in titled}
            clocks = {(r['start_clock'], r['end_clock']) for r in titled}
            ids = {r['record_id'] for r in titled}
            if None in flags:
                reason = 'flag_unknown'
            elif len(flags) != 1 or len(clocks) != 1:
                reason = 'ambiguous_records'
            elif any(len(r['venues']) > 1 for r in titled):
                reason = 'multiple_venues'
        record = titled[0] if titled else candidates[0]
        base = dict(
            event_url=record['event_url'], source_record_id=record['record_id'],
            source_title=record['title'],
            source_start=f"{record['start_date']} {record['start_clock']}",
            source_end=f"{record['end_date']} {record['end_clock']}",
            timezone=record['timezone'],
            evidence_capture_id=capture.get('crawl_result_id'),
            evidence_sha256=record['sha256'],
            evidence_observed_at=capture.get('observed_at'))
        if reason is None and len(ids) > 1:
            base['equivalent_record_ids'] = sorted(ids)
        if reason:
            conflicts.append(dict(base, slot=slot, reason=reason))
            continue
        flag = record['all_day']
        if flag and (slot[1] or slot[3]):
            if is_full_day_placeholder(slot[1], slot[3]):
                slot = [slot[0], '', slot[2], '']
                occurrences[position] = [occ[0], '', occ[2] if len(occ) > 2 else '', '']
            else:
                # A substantive clock on an all-day record: keep it, surface it.
                conflicts.append(dict(base, slot=slot, reason='all_day_vs_clock'))
                continue
        entries.append(dict(base, slot=slot, all_day=flag))
    if not entries and not conflicts:
        return None
    sidecar = event.get(PROVENANCE_KEY) or dict(version=VERSION, entries=[])
    sidecar['entries'] = sidecar.get('entries', []) + entries
    if conflicts:
        sidecar['conflicts'] = sidecar.get('conflicts', []) + conflicts
    event[PROVENANCE_KEY] = sidecar
    return sidecar


def record_synthesized_endpoints(event, marks):
    """Store [(occurrence, kind)] marks for slots still present on the event."""
    present = {tuple(_slot(o)) for o in event.get('occurrences') or [] if o and o[0]}
    endpoints = []
    for occ, kind in marks:
        mark = dict(slot=_slot(occ), kind=kind)
        if tuple(mark['slot']) in present and mark not in endpoints:
            endpoints.append(mark)
    if not endpoints:
        return None
    sidecar = event.setdefault(PROVENANCE_KEY, dict(version=VERSION, entries=[]))
    sidecar['endpoints'] = sidecar.get('endpoints', []) + [
        m for m in endpoints if m not in sidecar.get('endpoints', [])]
    return sidecar


def endpoint_slots(sidecar, kind):
    """{(start_date, end_date|None)} whose endpoint of ``kind`` was synthesized."""
    out = set()
    for mark in (sidecar or {}).get('endpoints', ()):
        slot = mark.get('slot')
        if mark.get('kind') == kind and isinstance(slot, list) and len(slot) == 4:
            out.add((str(slot[0]), str(slot[2]) if slot[2] and slot[2] != slot[0] else None))
    return out


def sidecar_from_raw(raw_data):
    """The validated sidecar of a crawl_event's raw_data, or None."""
    if not raw_data:
        return None
    try:
        data = json.loads(raw_data) if isinstance(raw_data, (str, bytes)) else raw_data
    except ValueError:
        return None
    sidecar = data.get(PROVENANCE_KEY) if isinstance(data, dict) else None
    if not isinstance(sidecar, dict) or sidecar.get('version') != VERSION:
        return None
    if not isinstance(sidecar.get('entries'), list):
        return None
    return sidecar


def entry_slots(sidecar, flag):
    """{(start_date, end_date_or_None)} with an actionable entry of ``flag``."""
    out = set()
    for entry in (sidecar or {}).get('entries', ()):
        slot = entry.get('slot')
        if entry.get('all_day') is flag and isinstance(slot, list) and len(slot) == 4:
            out.add((str(slot[0]), str(slot[2]) if slot[2] and slot[2] != slot[0] else None))
    return out


def resync_after_detail(raw_data, surviving, synthesized=()):
    """Re-key a sidecar after detail enrichment replaced a source's slots.

    Returns (new_raw_json, new_surviving) or (None, surviving) when the raw
    data holds no sidecar. An entry stays actionable only while its exact slot
    survives; a ``true`` entry also blanks a surviving full-day-boundary slot
    with the same dates. Every other entry moves to ``superseded`` -- a newer
    substantive clock or a changed date ends that claim's authority, and the
    claim is never inherited onto a different date or URL.
    """
    sidecar = sidecar_from_raw(raw_data)
    if sidecar is None and not synthesized:
        return None, surviving
    try:
        data = json.loads(raw_data) if raw_data else {}
    except ValueError:
        return None, surviving
    if not isinstance(data, dict):
        return None, surviving
    sidecar = sidecar or dict(version=VERSION, entries=[])
    true_dates = {(e['slot'][0], e['slot'][2]) for e in sidecar['entries']
                  if e.get('all_day') is True}
    rows = []
    for occ in surviving:
        slot = _slot(occ)
        if (slot[0], slot[2]) in true_dates and is_full_day_placeholder(slot[1], slot[3]):
            occ = (occ[0], '', occ[2], '')
        rows.append(occ)
    current = {tuple(_slot(o)) for o in rows}
    kept, dropped = [], list(sidecar.get('superseded') or [])
    for entry in sidecar['entries']:
        (kept if tuple(entry['slot']) in current else dropped).append(entry)
    sidecar = dict(sidecar, entries=kept)
    if dropped:
        sidecar['superseded'] = dropped
    # The detail page's own synthesized endpoints replace the listing's.
    endpoints = [m for m in sidecar.get('endpoints', []) if tuple(m['slot']) in current]
    for occ, kind in synthesized:
        mark = dict(slot=_slot(occ), kind=kind)
        if tuple(mark['slot']) in current and mark not in endpoints:
            endpoints.append(mark)
    sidecar.pop('endpoints', None)
    if endpoints:
        sidecar['endpoints'] = endpoints
    data[PROVENANCE_KEY] = sidecar
    return json.dumps(data), rows


# ---------------------------------------------------------------------------
# Canonical placeholder retirement (merger)
# ---------------------------------------------------------------------------

def _day(value):
    return str(value) if value else None


def plan_placeholder_retirement(rows, sources, url_key):
    """Decide which canonical full-day placeholder rows to blank.

    rows: canonical (start_date, start_time, end_date, end_time) tuples.
    sources: dicts with website_id, url, observed_at, occurrences (4-tuples),
        sidecar -- every linked source plus the incoming one.
    url_key: page identity function (merger.normalize_url_for_identity).

    Returns ({(sd, ed): 'blank' | 'drop'}, {(sd, ed): veto reason}). 'drop'
    means an exact blank twin already exists and the placeholder is redundant.

    A placeholder row is retired only when ALL of:
      * every linked source that carries that exact slot shares one publisher
        page (website + URL) -- unknown or mixed owners veto;
      * that page's newest observation of the same date span is strictly
        newer than every placeholder owner and carries blank clocks only;
      * no source holds an explicit ``all_day=false`` claim for the dates.
    The row is dropped rather than blanked when a blank twin or another clocked
    session already represents those dates; other rows are never touched.
    """
    def norm(o):
        sd, ed = _day(o[0]), _day(o[2])
        return (sd, standardize_time(o[1]), None if ed == sd else ed, standardize_time(o[3]))

    canonical = [norm(r) for r in rows]
    plan, vetoes = {}, {}
    false_dates = set()
    for s in sources:
        false_dates |= {(sd, ed) for sd, ed in entry_slots(s.get('sidecar'), False)}
    for sd, st, ed, et in canonical:
        if not sd or (st, et) != (PLACEHOLDER_START, PLACEHOLDER_END):
            continue
        key = (sd, ed)
        if key in false_dates:
            vetoes[key] = 'explicit_false'
            continue
        owners = [s for s in sources
                  if (sd, PLACEHOLDER_START, ed, PLACEHOLDER_END) in map(norm, s['occurrences'])]
        if not owners:
            vetoes[key] = 'no_owner'
            continue
        pages = {(s.get('website_id'), url_key(s.get('url'))) for s in owners}
        if len(pages) != 1 or not all(next(iter(pages))):
            vetoes[key] = 'mixed_owners'
            continue
        page = next(iter(pages))
        if any(s.get('observed_at') is None for s in owners):
            vetoes[key] = 'unknown_chronology'
            continue
        same_page = [s for s in sources
                     if (s.get('website_id'), url_key(s.get('url'))) == page
                     and s.get('observed_at') is not None
                     and any(o[0] == sd and o[2] == ed for o in map(norm, s['occurrences']))]
        newest = max(s['observed_at'] for s in same_page)
        latest = [s for s in same_page if s['observed_at'] == newest]
        if newest <= max(s['observed_at'] for s in owners):
            vetoes[key] = 'placeholder_is_newest'
            continue
        latest_clocks = {(o[1], o[3]) for s in latest for o in map(norm, s['occurrences'])
                         if o[0] == sd and o[2] == ed}
        if latest_clocks != {('', '')}:
            vetoes[key] = 'newest_not_blank'
            continue
        # A blank twin or another clocked session already represents the day;
        # a blank row would itself lose to that session in an ordinary merge.
        represented = any(r[0] == sd and r[2] == ed and (r[1], r[3]) != (st, et)
                          for r in canonical)
        plan[key] = 'drop' if represented else 'blank'
    return plan, vetoes
