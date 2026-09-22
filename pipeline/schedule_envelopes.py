"""Conservative cross-publisher reconciliation of date envelopes and daily sessions."""
from datetime import date, timedelta
from occurrence_times import standardize_time

# These formats describe scheduled attendance. Browsable runs, festivals,
# camps and unknown types can contain sessions without replacing their span.
SESSION_TYPES = frozenset({'Talk', 'Reading', 'Workshop', 'Class', 'Concert',
                          'Theater Show', 'Comedy Show', 'Screening', 'Service'})


def occurrence(row):
    def day(value):
        if not value:
            return None
        return date.fromisoformat(str(value))
    return (day(row[0]), standardize_time(row[1]), day(row[2]), standardize_time(row[3]))


def envelope(row):
    sd, st, ed, et = occurrence(row)
    return bool(sd and ed and 1 <= (ed - sd).days <= 30 and not st and not et)


def _clock(value):
    import re
    match = re.fullmatch(r'(\d{1,2})(?::(\d{2}))?(am|pm)', value or '')
    if not match:
        return None
    hour, minute, meridiem = match.groups()
    return (int(hour) % 12 + (12 if meridiem == 'pm' else 0)) * 60 + int(minute or 0)


def redundant_envelopes(event, rows, sources):
    """Return exact untimed ranges safely covered by one independent source.

    Sources contain id, website_id, source_type, location_id and occurrences.
    Do not assemble completeness from different crawls, extrapolate cadence,
    trust canonical event ownership, or reinterpret an unknown location. A
    conflicting dated source or canonical session vetoes automatic removal.
    """
    if event.get('event_type') not in SESSION_TYPES or not event.get('location_id'):
        return set()
    rows = [occurrence(r) for r in rows]
    sources = [dict(s, occurrences=[occurrence(r) for r in s['occurrences']]) for s in sources]
    redundant = set()
    for span in set(r for r in rows if envelope(r)):
        sd, _, ed, _ = span
        owners = [s for s in sources if span in s['occurrences']]
        if not owners:
            continue  # No provenance for a legacy canonical range.
        days = {sd + timedelta(days=i) for i in range((ed - sd).days + 1)}
        relevant = [s for s in sources if any(r[0] and r[0] <= ed and (r[2] or r[0]) >= sd
                                             for r in s['occurrences'])]
        if any(s.get('location_id') != event['location_id'] or not s.get('website_id')
               for s in relevant):
            continue
        for source in relevant:
            if source.get('source_type') != 'primary':
                continue
            if any(s['website_id'] == source['website_id'] for s in owners):
                continue  # Same publisher may deliberately offer both shapes.
            schedule = [r for r in source['occurrences'] if r[0] in days]
            if not schedule or any(r[2] not in (None, r[0]) or _clock(r[1]) is None
                                   or _clock(r[3]) is None or _clock(r[3]) <= _clock(r[1])
                                   for r in schedule):
                continue
            if {r[0] for r in schedule} != days:
                continue
            # Never erase a date envelope when another source or the canonical
            # event describes different hours, an overlapping span or a session
            # outside this range that runs into it.
            evidence = rows + [r for s in relevant for r in s['occurrences']]
            conflict = False
            for r in evidence:
                if r == span or not r[0] or r[0] > ed or (r[2] or r[0]) < sd:
                    continue
                if r[0] not in days or r[2] not in (None, r[0]):
                    conflict = True
                    break
                if not any(p[0] == r[0] and (not r[1] or p[1] == r[1])
                           and (not r[3] or p[3] == r[3]) for p in schedule):
                    conflict = True
                    break
            if not conflict:
                redundant.add(span)
                break
    return redundant


def reconcile_envelopes(cursor, event_id, crawl_event_id, existing, incoming):
    """Apply only canonical removals inside the caller's transaction/write lock.

    Original crawl evidence remains untouched. Called only when a match has a
    candidate range; either incoming ranges are ignored or old ranges removed.
    """
    cursor.execute('SELECT event_type,location_id FROM events WHERE id=%s', (event_id,))
    row = cursor.fetchone()
    if not row or row[0] not in SESSION_TYPES or not row[1]:
        return existing, incoming
    event = dict(event_type=row[0], location_id=row[1])
    cursor.execute('''SELECT ce.id,cr.website_id,w.source_type,ce.location_id,
        co.start_date,co.start_time,co.end_date,co.end_time
        FROM crawl_events ce JOIN crawl_results cr ON cr.id=ce.crawl_result_id
        JOIN websites w ON w.id=cr.website_id
        JOIN crawl_event_occurrences co ON co.crawl_event_id=ce.id
        WHERE ce.id=%s OR ce.id IN
            (SELECT crawl_event_id FROM event_sources WHERE event_id=%s)''',
                   (crawl_event_id, event_id))
    sources = {}
    for ce, website, source_type, location, *occ in cursor.fetchall():
        source = sources.setdefault(ce, dict(id=ce, website_id=website,
            source_type=source_type, location_id=location, occurrences=[]))
        source['occurrences'].append(occ)
    redundant = redundant_envelopes(event, list(existing) + list(incoming), list(sources.values()))
    # A source schedule must also be represented by this merge's actual rows;
    # a stale source link alone cannot remove the only publishable date range.
    for span in list(redundant):
        sd, _, ed, _ = span
        timed_days = {r[0] for r in map(occurrence, list(existing) + list(incoming))
                      if r[0] and sd <= r[0] <= ed and r[1] and r[2] in (None, r[0])}
        if len(timed_days) != (ed - sd).days + 1:
            redundant.remove(span)
    for span in redundant:
        if any(occurrence(r) == span for r in existing):
            cursor.execute('''DELETE FROM event_occurrences WHERE event_id=%s
                AND start_date=%s AND end_date=%s
                AND COALESCE(start_time,'')='' AND COALESCE(end_time,'')='' ''',
                           (event_id, span[0], span[2]))
    return ([r for r in existing if occurrence(r) not in redundant],
            [r for r in incoming if occurrence(r) not in redundant])
