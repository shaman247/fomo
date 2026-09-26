"""Source identities captured by an explicit duplicate merge, never suppression.

Rules retain exact source names, URLs, known venues and reviewed occurrence
slots. A later season, renamed program, different branch or ambiguous target
falls back to ordinary matching. Call writers inside the caller's write lock
and transaction; this module never commits or creates its schema.
"""
import json
import unicodedata
from datetime import date, timedelta
from urllib.parse import urlsplit
from occurrence_times import standardize_time

UNMAPPED_POLICY = 'reviewed_unmapped_v1'


class IdentityIndex(dict):
    """Ordinary redirect slots plus separately reviewed unmapped identities."""
    def __init__(self):
        super().__init__()
        self.unmapped = {}
        self.unmapped_schedules = {}


def _full_slot(row):
    return (str(row[0]), row[1] or '', str(row[2] or row[0]), row[3] or '')


def _untimed_days(rows):
    """Complete untimed edition, bounded to 31 days; never infer recurrence."""
    days = set()
    try:
        for row in rows:
            # Raw unknown clock labels are not proof of an untimed schedule.
            if row[1] not in (None, '') or row[3] not in (None, ''):
                return None
            start = date.fromisoformat(str(row[0]))
            end = date.fromisoformat(str(row[2] or row[0]))
            if not 0 <= (end - start).days <= 30:
                return None
            days.update(str(start + timedelta(days=i)) for i in range((end-start).days + 1))
        if not 2 <= len(days) <= 31:
            return None
        return frozenset(days)
    except (ValueError, TypeError, IndexError):
        return None


def _program_url(url, website_id, listing, allow_listing=False):
    try:
        parsed = urlsplit(url or '')
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            return False
        return allow_listing or bool((parsed.path.strip('/') or parsed.query)
                                     and (website_id, url.rstrip('/')) not in listing)
    except ValueError:
        return False


def name_key(name):
    return ' '.join(unicodedata.normalize('NFKC', name or '').casefold().split())


def slot(row):
    start, time, end = row[:3]
    return (str(start), standardize_time(time), str(end or start))


def _rows(cursor, sql, args=()):
    cursor.execute(sql, args)
    names = [d[0] for d in cursor.description]
    return [r if isinstance(r, dict) else dict(zip(names, r)) for r in cursor.fetchall()]


def record_merge(cursor, keep_id, duplicate_id, *, reviewed_source_ids=()):
    """Capture a duplicate decision, optionally backfilling reviewed moved sources.

    Explicit source IDs must already belong to the survivor. The caller must
    verify their historical association with this duplicate; we never infer
    that association from all sources currently attached to the survivor.
    Venue and reviewed-slot bounds apply equally to these source identities.
    """
    if keep_id == duplicate_id:
        raise ValueError('An event cannot redirect to itself')
    events = {r['id']: r for r in _rows(cursor, '''SELECT id,name,website_id,location_id,
        suppressed FROM events WHERE id IN (%s,%s)''', (keep_id, duplicate_id))}
    if len(events) != 2 or events[keep_id]['suppressed']:
        raise ValueError('A duplicate merge needs an existing unsuppressed survivor')
    reviewed_source_ids = tuple(sorted(set(reviewed_source_ids)))
    moved_sources = []
    if reviewed_source_ids:
        marks = ','.join(['%s'] * len(reviewed_source_ids))
        linked = _rows(cursor, f'''SELECT crawl_event_id FROM event_sources
            WHERE event_id=%s AND crawl_event_id IN ({marks})''',
            (keep_id, *reviewed_source_ids))
        if {r['crawl_event_id'] for r in linked} != set(reviewed_source_ids):
            raise ValueError('Reviewed moved sources must belong to the survivor')
        moved_sources = _rows(cursor, f'''SELECT ce.id,ce.name,ce.url,ce.location_id,
            cr.website_id,o.start_date,o.start_time,o.end_date FROM crawl_events ce
            JOIN crawl_results cr ON cr.id=ce.crawl_result_id
            JOIN crawl_event_occurrences o ON o.crawl_event_id=ce.id
            WHERE ce.id IN ({marks})''', reviewed_source_ids)
    cursor.execute('SELECT 1 FROM dedupe_dismissed_pairs WHERE event_id_a=%s AND event_id_b=%s',
                   tuple(sorted((keep_id, duplicate_id))))
    if cursor.fetchone():
        raise ValueError('This pair has a keep-separate decision')
    cursor.execute('''SELECT 1 FROM event_merge_redirects r
        WHERE (r.duplicate_id=%s AND r.survivor_id=%s)
        OR (r.survivor_id=%s AND EXISTS (SELECT 1 FROM dedupe_dismissed_pairs p
            WHERE p.event_id_a=LEAST(r.duplicate_id,%s)
            AND p.event_id_b=GREATEST(r.duplicate_id,%s)))''',
        (keep_id,duplicate_id,duplicate_id,keep_id,keep_id))
    if cursor.fetchone():
        raise ValueError('Redirect reversal or inherited keep-separate decision needs review')
    keep, duplicate = events[keep_id], events[duplicate_id]
    # Reconsidering an old pair must not leave its obsolete target active if
    # the new cross-venue/undated decision cannot produce a replacement rule.
    cursor.execute('DELETE FROM event_merge_redirects WHERE duplicate_id=%s AND survivor_id<>%s',
                   (duplicate_id,keep_id))
    cursor.execute('''UPDATE event_merge_redirects SET survivor_id=%s,survivor_name=%s
        WHERE survivor_id=%s''', (keep_id, keep['name'], duplicate_id))
    # A reviewed cross-venue consolidation does not authorize a new source to
    # bypass the merger's cross-location guard.
    if not duplicate['location_id'] or duplicate['location_id'] != keep['location_id']:
        return
    dates = _rows(cursor, '''SELECT start_date,start_time,end_date FROM event_occurrences
        WHERE event_id=%s''', (duplicate_id,))
    reviewed_slots = {slot((r['start_date'],r['start_time'],r['end_date'])) for r in dates}
    if not reviewed_slots:
        return
    sources = _rows(cursor, '''SELECT ce.id,ce.name,ce.url,ce.location_id,cr.website_id,
        o.start_date,o.start_time,o.end_date FROM event_sources es
        JOIN crawl_events ce ON ce.id=es.crawl_event_id
        JOIN crawl_results cr ON cr.id=ce.crawl_result_id
        JOIN crawl_event_occurrences o ON o.crawl_event_id=ce.id WHERE es.event_id=%s''', (duplicate_id,))
    identities = {}
    def add(name, url, website_id, location_id, slots):
        if not website_id or location_id != duplicate['location_id'] or not name_key(name):
            return
        try:
            parsed = urlsplit(url or '')
            if parsed.scheme not in ('http','https') or not parsed.hostname or not (parsed.path.strip('/') or parsed.query):
                return
        except ValueError:
            return
        key = (website_id, url, name_key(name), location_id)
        identities.setdefault(key, set()).update(slots & reviewed_slots)
    for r in sources + moved_sources:
        add(r['name'],r['url'],r['website_id'],r['location_id'],
            {slot((r['start_date'],r['start_time'],r['end_date']))})
    # Already-repaired losers have no sources. Their retained primary URL and
    # exact old name/date partition can still record an explicitly reviewed pair.
    for r in _rows(cursor, 'SELECT url FROM event_urls WHERE event_id=%s AND sort_order=0', (duplicate_id,)):
        add(duplicate['name'],r['url'],duplicate['website_id'],duplicate['location_id'],reviewed_slots)
    listing = {(r['website_id'],r['url'].rstrip('/')) for r in _rows(cursor,'SELECT website_id,url FROM website_urls')}
    scopes = [dict(website_id=k[0],url=k[1],name=k[2],location_id=k[3],slots=sorted(v))
              for k,v in identities.items() if v and (k[0],k[1].rstrip('/')) not in listing]
    previous = _rows(cursor, 'SELECT source_identities FROM event_merge_redirects '
                     'WHERE duplicate_id=%s AND survivor_id=%s', (duplicate_id,keep_id))
    if previous:
        # Re-running a repaired merge must not erase aliases captured before
        # the losing row's sources moved away.
        for old in json.loads(previous[0]['source_identities']):
            if old not in scopes:
                scopes.append(old)
    if scopes:
        cursor.execute('''INSERT INTO event_merge_redirects
            (duplicate_id,survivor_id,survivor_name,source_identities)
            VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE survivor_id=VALUES(survivor_id),
            survivor_name=VALUES(survivor_name),source_identities=VALUES(source_identities)''',
            (duplicate_id,keep_id,keep['name'],json.dumps(scopes,ensure_ascii=False)))


def record_unmapped_aliases(cursor, keep_id, duplicate_id, *, reviewed_source_ids,
                            review_reason, allow_listing_urls=(), include_captured_venues=False):
    """Enroll explicitly reviewed umbrella sources after an existing duplicate merge.

    Unlike ordinary redirects this policy pins a reviewed NULL-venue survivor
    and its entire untimed edition. Homepage/listing exceptions are exact
    (publisher, URL) approvals. A historical venue is accepted only if explicitly
    requested AND already captured on this pair's original redirect. No primary
    URL or generic name is turned into an alias by this function.
    """
    source_ids = tuple(sorted(set(reviewed_source_ids)))
    if not source_ids or not str(review_reason or '').strip():
        raise ValueError('Explicit source IDs and a review reason are required')
    events = {r['id']: r for r in _rows(cursor, '''SELECT id,name,location_id,
        reviewed,suppressed,archived FROM events WHERE id IN (%s,%s)''', (keep_id, duplicate_id))}
    keep, duplicate = events.get(keep_id), events.get(duplicate_id)
    if (keep_id == duplicate_id or not keep or not duplicate or not keep['reviewed']
            or keep['location_id'] is not None or keep['suppressed'] or keep['archived']
            or not duplicate['reviewed'] or not duplicate['suppressed']):
        raise ValueError('A reviewed unmapped survivor and reviewed hidden duplicate are required')
    previous = _rows(cursor, '''SELECT source_identities FROM event_merge_redirects
        WHERE duplicate_id=%s AND survivor_id=%s''', (duplicate_id, keep_id))
    if not previous:
        raise ValueError('An explicit duplicate-merge record must already exist')
    cursor.execute('SELECT 1 FROM dedupe_dismissed_pairs WHERE event_id_a=%s AND event_id_b=%s',
                   tuple(sorted((keep_id, duplicate_id))))
    if cursor.fetchone():
        raise ValueError('This pair has a keep-separate decision')
    old_scopes = json.loads(previous[0]['source_identities'])
    target_rows = _rows(cursor, '''SELECT start_date,start_time,end_date,end_time
        FROM event_occurrences WHERE event_id=%s''', (keep_id,))
    target_slots = sorted({_full_slot((r['start_date'], r['start_time'], r['end_date'], r['end_time']))
                           for r in target_rows})
    edition = _untimed_days(target_slots)
    if not edition:
        raise ValueError('The reviewed target must have a complete untimed multi-day edition')
    marks = ','.join(['%s'] * len(source_ids))
    sources = _rows(cursor, f'''SELECT ce.id,ce.name,ce.url,ce.location_id,cr.website_id,
        o.start_date,o.start_time,o.end_date,o.end_time FROM event_sources es
        JOIN crawl_events ce ON ce.id=es.crawl_event_id
        JOIN crawl_results cr ON cr.id=ce.crawl_result_id
        JOIN crawl_event_occurrences o ON o.crawl_event_id=ce.id
        WHERE es.event_id=%s AND ce.id IN ({marks})''', (keep_id, *source_ids))
    by_id = {}
    for r in sources:
        by_id.setdefault(r['id'], []).append(r)
    if set(by_id) != set(source_ids):
        raise ValueError('Every reviewed source must be dated and attached to the survivor')
    listing = {(r['website_id'], r['url'].rstrip('/'))
               for r in _rows(cursor, 'SELECT website_id,url FROM website_urls')}
    approved_listing = set(allow_listing_urls)
    scopes = {}
    for source_id, records in sorted(by_id.items()):
        r = records[0]
        rows = [(v['start_date'], v['start_time'], v['end_date'], v['end_time']) for v in records]
        allow_listing = (r['website_id'], r['url']) in approved_listing
        if (r['location_id'] is not None or not r['website_id'] or not name_key(r['name'])
                or _untimed_days(rows) != edition
                or not _program_url(r['url'], r['website_id'], listing, allow_listing)):
            raise ValueError(f'Source {source_id} lacks the approved unmapped edition identity')
        venues = {None}
        if include_captured_venues:
            for old in old_scopes:
                old_rows = [(*s, '') for s in old.get('slots', [])]
                if (not old.get('policy') and old.get('website_id') == r['website_id']
                        and old.get('url') == r['url'] and old.get('name') == name_key(r['name'])
                        and old.get('location_id') == duplicate['location_id']
                        and old.get('location_id') is not None and _untimed_days(old_rows) == edition):
                    venues.add(old['location_id'])
        for venue in sorted(venues, key=lambda value: (value is not None, value or 0)):
            key = (r['website_id'], r['url'], name_key(r['name']), venue)
            scope = scopes.setdefault(key, dict(
                policy=UNMAPPED_POLICY, website_id=key[0], url=key[1], name=key[2], location_id=venue,
                # Pre-policy readers may still inspect NULL-venue scopes.
                # An empty legacy slot list makes this additive format inert.
                slots=[],
                reviewed_target_id=keep_id, target_slots=target_slots, edition_days=sorted(edition),
                evidence_location_id=None, reviewed_source_ids=[], review_reason=review_reason.strip(),
                allow_listing_url=allow_listing,
                source_venue_basis='captured_duplicate_redirect' if venue is not None else 'reviewed_source'))
            scope['reviewed_source_ids'].append(source_id)
    payload = [s for s in old_scopes if s.get('policy') != UNMAPPED_POLICY] + list(scopes.values())
    cursor.execute('''UPDATE event_merge_redirects SET survivor_name=%s,source_identities=%s
        WHERE duplicate_id=%s AND survivor_id=%s''',
        (keep['name'], json.dumps(payload, ensure_ascii=False), duplicate_id, keep_id))
    return list(scopes.values())


def _load_unmapped_scope(cursor, index, rule, scope, current_slots):
    """Fail closed if the explicitly reviewed target or source evidence changed."""
    target = rule['survivor_id']
    expected = {tuple(s) for s in scope.get('target_slots', [])}
    edition = _untimed_days(expected)
    source_ids = scope.get('reviewed_source_ids', [])
    if (not rule['reviewed'] or rule['location_id'] is not None
            or scope.get('reviewed_target_id') != target or not expected
            or expected != current_slots or not edition
            or set(scope.get('edition_days', [])) != edition
            or not scope.get('review_reason') or not source_ids
            or scope.get('evidence_location_id') is not None
            or (scope.get('location_id') is not None
                and (scope.get('source_venue_basis') != 'captured_duplicate_redirect'
                     or scope['location_id'] != rule['duplicate_location_id']))):
        return
    listing = {(r['website_id'], r['url'].rstrip('/'))
               for r in _rows(cursor, 'SELECT website_id,url FROM website_urls')}
    if not _program_url(scope['url'], scope['website_id'], listing, scope.get('allow_listing_url') is True):
        return
    marks = ','.join(['%s'] * len(source_ids))
    evidence = _rows(cursor, f'''SELECT ce.id,ce.name,ce.url,ce.location_id,cr.website_id,
        o.start_date,o.start_time,o.end_date,o.end_time FROM event_sources es
        JOIN crawl_events ce ON ce.id=es.crawl_event_id
        JOIN crawl_results cr ON cr.id=ce.crawl_result_id
        JOIN crawl_event_occurrences o ON o.crawl_event_id=ce.id
        WHERE es.event_id=%s AND ce.id IN ({marks})''', (target, *source_ids))
    by_id = {}
    for row in evidence:
        if (row['website_id'] != scope['website_id'] or row['url'] != scope['url']
                or name_key(row['name']) != scope['name'] or row['location_id'] is not None):
            return
        by_id.setdefault(row['id'], []).append(
            (row['start_date'], row['start_time'], row['end_date'], row['end_time']))
    if set(by_id) != set(source_ids) or any(_untimed_days(v) != edition for v in by_id.values()):
        return
    key = (scope['website_id'], scope['url'], scope['name'], scope['location_id'])
    index.unmapped.setdefault(key, {}).setdefault(target, set()).add(edition)
    index.unmapped_schedules[target] = sorted(expected)


def unmapped_schedule(index, event_id):
    """Canonical schedule pinned by a currently valid explicit unmapped review."""
    rows = getattr(index, 'unmapped_schedules', {}).get(event_id)
    if rows is None:
        return None
    return [(date.fromisoformat(sd), st, None if ed == sd else date.fromisoformat(ed), et)
            for sd, st, ed, et in rows]


def load_index(cursor):
    """Only load still-hidden duplicates leading to live, unchanged survivors."""
    rules = _rows(cursor, '''SELECT r.*,e.name AS current_name,e.location_id,e.reviewed,
        d.location_id AS duplicate_location_id
        FROM event_merge_redirects r JOIN events e ON e.id=r.survivor_id
        JOIN events d ON d.id=r.duplicate_id
        WHERE d.suppressed=1 AND d.reviewed=1 AND e.suppressed=0 AND e.archived=0
        AND NOT EXISTS (SELECT 1 FROM dedupe_dismissed_pairs p
            WHERE p.event_id_a=LEAST(r.duplicate_id,r.survivor_id)
            AND p.event_id_b=GREATEST(r.duplicate_id,r.survivor_id))''')
    targets = {r['survivor_id'] for r in rules}
    schedules = {eid:set() for eid in targets}
    full_schedules = {eid:set() for eid in targets}
    if targets:
        marks=','.join(['%s']*len(targets))
        for r in _rows(cursor,f'''SELECT event_id,start_date,start_time,end_date,end_time
                FROM event_occurrences WHERE event_id IN ({marks})''', tuple(targets)):
            schedules[r['event_id']].add(slot((r['start_date'],r['start_time'],r['end_date'])))
            full_schedules[r['event_id']].add(_full_slot(
                (r['start_date'], r['start_time'], r['end_date'], r['end_time'])))
    index = IdentityIndex()
    for r in rules:
        if name_key(r['survivor_name']) != name_key(r['current_name']):
            continue
        for scope in json.loads(r['source_identities']):
            if scope.get('policy') == UNMAPPED_POLICY:
                _load_unmapped_scope(cursor, index, r, scope, full_schedules[r['survivor_id']])
                continue
            if scope.get('policy'):
                continue
            if scope['location_id'] != r['location_id']:
                continue
            key = (scope['website_id'],scope['url'],scope['name'],scope['location_id'])
            allowed = {tuple(s) for s in scope['slots']} & schedules[r['survivor_id']]
            if allowed:
                index.setdefault(key, {}).setdefault(r['survivor_id'],set()).update(allowed)
    return index


def match(index, website_id, name, url, location_id, occurrences, *, full_source_occurrences=None):
    """Require complete reviewed date/time coverage and one unambiguous target."""
    if not occurrences:
        return None
    incoming = {slot(o) for o in occurrences}
    key = (website_id,url,name_key(name),location_id)
    targets = index.get(key, {}) if location_id else {}
    unmapped = getattr(index, 'unmapped', {}).get(key, {})
    # Ambiguous identities decline even if only one target covers all dates.
    if len(set(targets) | set(unmapped)) != 1:
        return None
    if unmapped:
        target, editions = next(iter(unmapped.items()))
        # The edition's first day may already be past. Validate the publisher's
        # complete source schedule, not the caller's active-date projection.
        source_rows = occurrences if full_source_occurrences is None else full_source_occurrences
        return target if _untimed_days(source_rows) in editions else None
    target, allowed = next(iter(targets.items()))
    return target if incoming <= allowed else None
