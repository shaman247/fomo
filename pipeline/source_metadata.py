"""Refresh ordinary matched-event metadata only with attributable source evidence."""
import json
from datetime import date, datetime

from occurrence_times import standardize_time
from delivery import virtual_tags_for_location


def _label(value):
    return ' '.join((value or '').split()).casefold()


def _empty_room(value, location_name=None):
    label = _label(value)
    return (label in {'', 'not specified', 'unknown', 'tba', 'tbd', 'n/a', 'none'}
            or bool(label and label == _label(location_name)))


def _description(value):
    label = _label(value)
    return bool(label and label != 'no description available.')


def _grouped(raw):
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return True  # Unknown provenance must not permit replacing grouped text.
    if data is not None and not isinstance(data, dict):
        return True
    return bool(isinstance(data, dict) and data.get('session_details'))


def _timestamp(value):
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _delivery_candidate(event, incoming):
    # Positive source evidence can restore a lost label. An omitted Virtual
    # marker cannot establish an in-person transition, and an existing online
    # or hybrid label may carry attendance details that must not be discarded.
    return (not event.get('reviewed')
            and not virtual_tags_for_location(event.get('location_name'))
            and bool(virtual_tags_for_location(incoming.get('location_name'))))


def _slots(occurrences, today):
    slots = set()
    for row in occurrences:
        start = str(row['start_date'] or '')
        end = str(row.get('end_date') or start)
        if max(start, end) < str(today):
            continue
        slots.add((start, standardize_time(row.get('start_time')), end))
    return slots


def plan_source_metadata_refresh(event, incoming, sources, occurrences,
                                 incoming_occurrences, today=None):
    """Return independent field changes; never replace a specific room.

    A canonical description may refresh only if unreviewed and still an exact
    copy of this publisher's older source. A lost online/hybrid location label
    may refresh under the same constraints; absence is not in-person evidence.
    Require one publisher, the same
    known venue, a strictly newer crawl, and evidence covering every remaining
    session. A rolling subset must not describe the whole canonical series.
    Grouped date-specific descriptions retain their separate refresh policy.
    """
    today = today or date.today()
    if (event.get('suppressed') or not incoming.get('website_id')
            or event.get('website_id') != incoming['website_id']
            or not event.get('location_id')
            or event['location_id'] != incoming.get('location_id')
            or _grouped(incoming.get('raw_data'))):
        return {}
    prior = [s for s in sources if s['id'] != incoming['id']]
    if not prior or any(s.get('website_id') != incoming['website_id'] for s in prior):
        return {}
    fresh = _timestamp(incoming.get('crawled_at'))
    times = [_timestamp(s.get('crawled_at')) for s in prior]
    if not fresh or any(t is None for t in times) or fresh <= max(times):
        return {}
    current_slots = _slots(occurrences, today)
    if not current_slots or not current_slots <= _slots(incoming_occurrences, today):
        return {}

    fields = {}
    if (_delivery_candidate(event, incoming)
            and any(_label(s.get('location_name')) == _label(event.get('location_name'))
                    for s in prior)
            and not any(_grouped(s.get('raw_data')) for s in prior)):
        fields['location_name'] = incoming['location_name'].strip()[:255]
    room = (incoming.get('sublocation') or '').strip()
    if (_empty_room(event.get('sublocation'), event.get('location_name'))
            and not _empty_room(room, incoming.get('location_name'))
            and _label(room) != 'varies by session; see description'
            # A known historical room at this venue is contrary evidence.
            and all(_empty_room(s.get('sublocation'), s.get('location_name'))
                    or _label(s.get('sublocation')) == _label(room)
                    for s in prior if s.get('location_id') == event['location_id'])):
        fields['sublocation'] = room[:255]

    old, new = event.get('description'), incoming.get('description')
    if (not event.get('reviewed') and _description(old) and _description(new)
            and old != new and any(s.get('description') == old for s in prior)
            and not any(_grouped(s.get('raw_data')) for s in prior)):
        fields['description'] = new
    return fields


def refresh_source_metadata(cursor, event_id, crawl_event_id, today=None,
                            edit_logger=None):
    """Plan and apply a refresh inside the merger's existing transaction/lock."""
    event_keys = ('id', 'website_id', 'reviewed', 'suppressed', 'location_id',
                  'location_name', 'sublocation', 'description')
    source_keys = ('id', 'website_id', 'crawled_at', 'location_id', 'location_name',
                   'sublocation', 'description', 'raw_data')
    cursor.execute('''SELECT e.id,e.website_id,e.reviewed,e.suppressed,e.location_id,
        e.location_name,e.sublocation,e.description,
        ce.id,cr.website_id,cr.crawled_at,ce.location_id,ce.location_name,
        ce.sublocation,ce.description,ce.raw_data
        FROM events e JOIN crawl_events ce ON ce.id=%s
        JOIN crawl_results cr ON cr.id=ce.crawl_result_id WHERE e.id=%s''',
                   (crawl_event_id, event_id))
    row = cursor.fetchone()
    if not row:
        return {}
    event = dict(zip(event_keys, row[:len(event_keys)]))
    incoming = dict(zip(source_keys, row[len(event_keys):]))
    # Most matches bring no usable change; avoid history/occurrence queries.
    room_candidate = (_empty_room(event['sublocation'], event['location_name'])
                      and not _empty_room(incoming['sublocation'], incoming['location_name']))
    description_candidate = (not event['reviewed'] and _description(incoming['description'])
                             and _description(event['description'])
                             and incoming['description'] != event['description'])
    delivery_candidate = _delivery_candidate(event, incoming)
    if (not (room_candidate or description_candidate or delivery_candidate) or event['suppressed']
            or event['website_id'] != incoming['website_id']
            or not event['location_id'] or event['location_id'] != incoming['location_id']
            or _grouped(incoming['raw_data'])):
        return {}
    cursor.execute('''SELECT ce.id,cr.website_id,cr.crawled_at,ce.location_id,
        ce.location_name,ce.sublocation,ce.description,ce.raw_data
        FROM event_sources es JOIN crawl_events ce ON ce.id=es.crawl_event_id
        JOIN crawl_results cr ON cr.id=ce.crawl_result_id WHERE es.event_id=%s''', (event_id,))
    sources = [dict(zip(source_keys, r)) for r in cursor.fetchall()]
    cursor.execute('''SELECT 0,start_date,start_time,end_date FROM event_occurrences WHERE event_id=%s
        UNION ALL SELECT 1,start_date,start_time,end_date FROM crawl_event_occurrences
        WHERE crawl_event_id=%s''', (event_id, crawl_event_id))
    schedules = ([], [])
    for kind, start, time, end in cursor.fetchall():
        schedules[kind].append(dict(start_date=start, start_time=time, end_date=end))
    fields = plan_source_metadata_refresh(event, incoming, sources, *schedules, today=today)
    if fields:
        cursor.execute('UPDATE events SET ' + ','.join(k + '=%s' for k in fields)
                       + ' WHERE id=%s', (*fields.values(), event_id))
        if edit_logger:
            for field, value in fields.items():
                edit_logger.log_update('events', event_id, field, event[field], value)
    return fields
