"""Explicit source ownership reviews, independent of duplicate/suppression policy.

A registration URL alone never establishes identity. Each alias pins the reviewed
publisher, title, venue, complete source schedule and target state. Writers run
inside the caller's write lock and transaction; no helper commits.
"""
import json
import re
from delivery import virtual_tags_for_location
from occurrence_times import standardize_time
from reviewed_event_identity import _rows, name_key, _program_url


def full_slot(row):
    return (str(row[0]), standardize_time(row[1]), str(row[2] or row[0]),
            standardize_time(row[3]) if len(row) > 3 else '')


def _schedule(rows):
    return {full_slot((r['start_date'], r['start_time'], r['end_date'], r['end_time']))
            for r in rows}


def record(cursor, event_id, source_id, *, review_reason, aliases=(), allow_listing_url=False):
    """Record a reviewed source already attributed to this canonical event.

    Additional title aliases require the caller's explicit source review. They
    never widen the registration URL, venue, delivery label or dated slot bounds.
    """
    if not str(review_reason or '').strip():
        raise ValueError('A source ownership review reason is required')
    targets = _rows(cursor, 'SELECT id,name,location_id,location_name,suppressed,archived FROM events WHERE id=%s', (event_id,))
    sources = _rows(cursor, '''SELECT ce.id,ce.name,ce.url,ce.location_id,ce.location_name,cr.website_id
        FROM event_sources es JOIN crawl_events ce ON ce.id=es.crawl_event_id
        JOIN crawl_results cr ON cr.id=ce.crawl_result_id
        WHERE es.event_id=%s AND ce.id=%s''', (event_id, source_id))
    if len(targets) != 1 or len(sources) != 1:
        raise ValueError('Source must already belong to the reviewed target')
    target, source = targets[0], sources[0]
    listing = {(r['website_id'], r['url'].rstrip('/')) for r in
               _rows(cursor, 'SELECT website_id,url FROM website_urls')}
    online_target = (target['location_id'] is None
                     and delivery_mode(target.get('location_name'), target['name']) == 'online'
                     and delivery_mode(source.get('location_name'), source['name']) == 'online')
    if (target['archived'] or (not target['location_id'] and not online_target)
            or source['location_id'] != target['location_id']
            or not _program_url(source['url'], source['website_id'], listing, allow_listing_url)):
        raise ValueError('Alias requires an active same-venue target or explicitly online unmapped target and an attributable detail URL')
    source_slots = _schedule(_rows(cursor, '''SELECT start_date,start_time,end_date,end_time
        FROM crawl_event_occurrences WHERE crawl_event_id=%s''', (source_id,)))
    target_slots = _schedule(_rows(cursor, '''SELECT start_date,start_time,end_date,end_time
        FROM event_occurrences WHERE event_id=%s''', (event_id,)))
    if not source_slots or not source_slots <= target_slots:
        raise ValueError('The complete source slot partition must belong to the target')
    if _dismissed_owner(cursor, event_id, source_id):
        raise ValueError('Source has a conflicting keep-separate owner')
    names = sorted({name_key(source['name']), *(name_key(n) for n in aliases)})
    if not all(names):
        raise ValueError('Empty source names cannot establish identity')
    payload = dict(website_id=source['website_id'], url=source['url'],
                   allow_listing_url=bool(allow_listing_url),
                   delivery=delivery_mode(source.get('location_name'), source['name']),
                   source_name=name_key(source['name']), names=names,
                   location_id=target['location_id'], target_name=name_key(target['name']),
                   suppressed=bool(target['suppressed']), slots=sorted(source_slots))
    cursor.execute('''INSERT INTO event_source_identities(event_id,crawl_event_id,identity,review_reason)
        VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE identity=VALUES(identity),
        review_reason=VALUES(review_reason)''',
        (event_id, source_id, json.dumps(payload, ensure_ascii=False), review_reason.strip()))
    return payload


def _dismissed_owner(cursor, event_id, source_id):
    cursor.execute('''SELECT 1 FROM event_sources es JOIN dedupe_dismissed_pairs p
        ON p.event_id_a=LEAST(es.event_id,%s) AND p.event_id_b=GREATEST(es.event_id,%s)
        WHERE es.crawl_event_id=%s AND es.event_id<>%s LIMIT 1''',
        (event_id,event_id,source_id,event_id))
    return bool(cursor.fetchone())


def load_into(cursor, index):
    """Load only unchanged, still-attributed reviews; do not infer new aliases."""
    from reviewed_event_identity import IdentityIndex
    if not isinstance(index, IdentityIndex):
        index = _copy_index(index)
    index.source_aliases = {}
    index.protected_source_keys = set()
    index.source_delivery = {}
    rules = _rows(cursor, '''SELECT r.*,e.name AS target_name,e.location_id AS target_location,
        e.location_name AS target_location_name,
        e.suppressed,e.archived,ce.name AS source_name,ce.url,ce.location_id AS source_location,
        ce.location_name AS source_location_name,cr.website_id,es.event_id AS owner_id FROM event_source_identities r
        JOIN events e ON e.id=r.event_id JOIN crawl_events ce ON ce.id=r.crawl_event_id
        JOIN crawl_results cr ON cr.id=ce.crawl_result_id
        LEFT JOIN event_sources es ON es.event_id=r.event_id AND es.crawl_event_id=r.crawl_event_id''')
    for r in rules:
        scope = json.loads(r['identity'])
        index.protected_source_keys.update(
            (scope['website_id'], scope['url'], name) for name in scope['names'])
        if (r['owner_id'] is None or r['archived'] or r['target_location'] != scope['location_id']
                or r['source_location'] != scope['location_id']
                or (scope['location_id'] is None and (
                    scope.get('delivery') != 'online'
                    or delivery_mode(r.get('target_location_name'), r['target_name']) != 'online'))
                or name_key(r['target_name']) != scope['target_name']
                or name_key(r['source_name']) != scope['source_name']
                or delivery_mode(r.get('source_location_name'), r['source_name']) != scope.get('delivery')
                or bool(r['suppressed']) != scope['suppressed']
                or r['website_id'] != scope['website_id'] or r['url'] != scope['url']
                or _dismissed_owner(cursor, r['event_id'], r['crawl_event_id'])):
            continue
        slots = {tuple(s) for s in scope['slots']}
        current_source = _schedule(_rows(cursor, '''SELECT start_date,start_time,end_date,end_time
            FROM crawl_event_occurrences WHERE crawl_event_id=%s''', (r['crawl_event_id'],)))
        current_target = _schedule(_rows(cursor, '''SELECT start_date,start_time,end_date,end_time
            FROM event_occurrences WHERE event_id=%s''', (r['event_id'],)))
        if not slots or slots != current_source or not slots <= current_target:
            continue
        for name in scope['names']:
            key = (scope['website_id'], scope['url'], name, scope['location_id'])
            index.source_aliases.setdefault(key, {}).setdefault(r['event_id'], []).append(slots)
            index.source_delivery.setdefault((key,r['event_id']),set()).add(scope.get('delivery'))
    return index


def match(index, key, occurrences):
    """Keep partitions separate: their union cannot authorize a combined course."""
    targets = getattr(index, 'source_aliases', {}).get(key, {})
    incoming = {full_slot(o) for o in occurrences}
    if not incoming or len(targets) != 1:
        return None
    target, partitions = next(iter(targets.items()))
    return target if any(incoming <= slots for slots in partitions) else None


def _copy_index(index):
    from reviewed_event_identity import IdentityIndex
    result = IdentityIndex()
    result.update(index)
    return result


def needs_review(index, website_id, name, url, matched_event_id):
    """A known reviewed identity cannot fall back after its evidence changes."""
    return matched_event_id is None and (website_id, url, name_key(name)) in getattr(
        index, "protected_source_keys", set())


def delivery_mode(location_name, name=''):
    """Read explicit attendance, never infer physical delivery from a map pin."""
    label = location_name or ''
    # Only delimited title attendance labels, not subjects such as Online Safety.
    labels = re.findall(r'(?:[|:–—(]\s*)(online|virtual|in[ -]person|hybrid)(?=\s*(?:[-–—|)]|$))',
                        name or '', flags=re.I)
    evidence = label + ' ' + ' '.join(labels)
    remote = bool(virtual_tags_for_location(evidence))
    physical = bool(re.search(r'\bin[ -]person\b',evidence,re.I))
    if re.search(r'\bhybrid\b',evidence,re.I) or (remote and physical):return 'hybrid'
    return 'online' if remote else 'in_person' if physical else None


def delivery_conflicts(index, website_id, name, url, location_id, event_id, raw_location_name):
    key = (website_id,url,name_key(name),location_id)
    modes = getattr(index,'source_delivery',{}).get((key,event_id),set()) - {None}
    incoming = delivery_mode(raw_location_name,name)
    return bool(incoming and modes and incoming not in modes)
