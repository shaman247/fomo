"""Source identities captured by an explicit duplicate merge, never suppression.

Rules retain exact source names, URLs, known venues and reviewed occurrence
slots. A later season, renamed program, different branch or ambiguous target
falls back to ordinary matching. Call writers inside the caller's write lock
and transaction; this module never commits or creates its schema.
"""
import json
import unicodedata
from urllib.parse import urlsplit
from occurrence_times import standardize_time


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


def load_index(cursor):
    """Only load still-hidden duplicates leading to live, unchanged survivors."""
    rules = _rows(cursor, '''SELECT r.*,e.name AS current_name,e.location_id
        FROM event_merge_redirects r JOIN events e ON e.id=r.survivor_id
        JOIN events d ON d.id=r.duplicate_id
        WHERE d.suppressed=1 AND d.reviewed=1 AND e.suppressed=0 AND e.archived=0
        AND NOT EXISTS (SELECT 1 FROM dedupe_dismissed_pairs p
            WHERE p.event_id_a=LEAST(r.duplicate_id,r.survivor_id)
            AND p.event_id_b=GREATEST(r.duplicate_id,r.survivor_id))''')
    targets = {r['survivor_id'] for r in rules}
    schedules = {eid:set() for eid in targets}
    if targets:
        marks=','.join(['%s']*len(targets))
        for r in _rows(cursor,f'''SELECT event_id,start_date,start_time,end_date
                FROM event_occurrences WHERE event_id IN ({marks})''', tuple(targets)):
            schedules[r['event_id']].add(slot((r['start_date'],r['start_time'],r['end_date'])))
    index = {}
    for r in rules:
        if name_key(r['survivor_name']) != name_key(r['current_name']):
            continue
        for scope in json.loads(r['source_identities']):
            if scope['location_id'] != r['location_id']:
                continue
            key = (scope['website_id'],scope['url'],scope['name'],scope['location_id'])
            allowed = {tuple(s) for s in scope['slots']} & schedules[r['survivor_id']]
            if allowed:
                index.setdefault(key, {}).setdefault(r['survivor_id'],set()).update(allowed)
    return index


def match(index, website_id, name, url, location_id, occurrences):
    """Require complete reviewed date/time coverage and one unambiguous target."""
    if not location_id or not occurrences:
        return None
    incoming = {slot(o) for o in occurrences}
    targets = index.get((website_id,url,name_key(name),location_id), {})
    # Ambiguous identities decline even if only one target covers all dates.
    if len(targets) != 1:
        return None
    target, allowed = next(iter(targets.items()))
    return target if incoming <= allowed else None
