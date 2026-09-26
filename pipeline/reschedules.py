"""Narrow, provenance-aware reconciliation of explicit rescheduling notices."""
import re
from datetime import date, datetime

from occurrence_times import standardize_time

# A standalone statement keeps a sibling's or historical anecdote's reschedule
# out of scope. Deliberately do not infer cancellations from omitted dates.
MONTHS = {m.casefold(): i for i, m in enumerate(
    ('January', 'February', 'March', 'April', 'May', 'June', 'July',
     'August', 'September', 'October', 'November', 'December'), 1)}
_DATE = r'(?:\d{4}-\d{2}-\d{2}|(?:' + '|'.join(MONTHS) + r')\s+\d{1,2}(?:,?\s+\d{4})?)'
_NOTICE = re.compile(r'(?:this (?:event|program|session) (?:was|is|has been) )?'
                     r'rescheduled from (' + _DATE + r')(?: to (' + _DATE + r'))?', re.I)


def has_reschedule_notice(text):
    return bool(re.search(r'\brescheduled\s+from\b', text or '', re.I))


def _name(value):
    return ' '.join((value or '').split()).casefold()


def _day(value):
    return date.fromisoformat(str(value)) if value else None


def _slot(row):
    start = _day(row[0])
    return (start, standardize_time(row[1]), _day(row[2]) or start,
            standardize_time(row[3]))


def _timestamp(value):
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _notice_day(text, replacement):
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
            return date.fromisoformat(text)
        words = text.replace(',', '').split()
        # A yearless notice is bounded to 60 days of the replacement, including
        # year rollover. It must resolve to exactly one date, never today's year.
        years = [int(words[2])] if len(words) == 3 else range(replacement.year - 1, replacement.year + 2)
        candidates = []
        for year in years:
            try:
                value = date(year, MONTHS[words[0].casefold()], int(words[1]))
            except ValueError:
                continue
            if len(words) == 3 or abs((value - replacement).days) <= 60:
                candidates.append(value)
        return candidates[0] if len(candidates) == 1 else None
    except (ValueError, KeyError, IndexError):
        return None


def explicit_reschedule(source):
    """Return (old day, exact replacement slot), or decline ambiguous text.

    Only one single-day replacement slot is supported. Grouped notices, spans,
    multiple showtimes, cancellation text and arbitrary prose need review.
    """
    text = source.get('description') or ''
    if re.search(r'\bcancell?ed\b', text + ' ' + (source.get('name') or ''), re.I):
        return None
    slots = {_slot(r) for r in source.get('occurrences', [])}
    if len(slots) != 1:
        return None
    replacement = next(iter(slots))
    if not replacement[0] or replacement[0] != replacement[2]:
        return None
    statements = []
    for sentence in re.split(r'[!?\n]+|(?<=\.)\s+', text):
        match = _NOTICE.fullmatch(sentence.strip().strip('.*() '))
        if match:
            old = _notice_day(match[1], replacement[0])
            stated_new = _notice_day(match[2], replacement[0]) if match[2] else replacement[0]
            if (old and old != replacement[0] and stated_new == replacement[0]
                    and abs((old - replacement[0]).days) <= 60):
                statements.append((old, replacement))
    return statements[0] if len(statements) == 1 else None


def superseded_slots(event, rows, sources):
    """Return exact old slots whose own publisher explicitly replaces them.

    Identity must already have been matched by the merger. Require exact names,
    a known shared venue and older same-publisher attribution for EVERY removed
    slot. An independently published old date, newer contradictory crawl, unknown
    provenance or multiple old showtimes vetoes removal. Original source rows
    are never changed, and also prevent stale replays restoring superseded dates.
    """
    if event.get('suppressed') or not event.get('location_id'):
        return set()
    rows = {_slot(r) for r in rows}
    sources = [dict(s, slots={_slot(r) for r in s.get('occurrences', [])}) for s in sources]
    result = set()
    for notice in sources:
        change = explicit_reschedule(notice)
        if not change:
            continue
        old_day, replacement = change
        if (not notice.get('website_id') or notice.get('location_id') != event['location_id']
                or _name(notice.get('name')) != _name(event.get('name'))
                or replacement not in rows):
            continue
        old = {r for r in rows if r[0] == old_day}
        if len(old) != 1 or any(r[2] != old_day for r in old):
            continue
        old_slot = next(iter(old))
        owners = [s for s in sources if old_slot in s['slots']]
        if not owners:
            continue
        fresh = _timestamp(notice.get('crawled_at'))
        if not fresh:
            continue
        relevant = [s for s in sources if any(
            r[0] and r[0] <= old_day <= r[2] for r in s['slots'])]
        conflict = False
        for s in relevant:
            timestamp = _timestamp(s.get('crawled_at'))
            # All evidence that touches the old date must be the same old slot,
            # from this exact event/publisher/venue, strictly before the notice.
            if (s.get('website_id') != notice['website_id']
                    or s.get('location_id') != event['location_id']
                    or _name(s.get('name')) != _name(event.get('name'))
                    or not timestamp or timestamp >= fresh
                    or any(r != old_slot for r in s['slots']
                           if r[0] and r[0] <= old_day <= r[2])):
                conflict = True
                break
        # A later/independent notice moving the same date somewhere else is an
        # explicit disagreement even if neither source still emits the old day.
        for s in sources:
            other = explicit_reschedule(s)
            if other and other[0] == old_day and other[1] != replacement:
                conflict = True
            if any(r != replacement for r in s['slots']
                   if r[0] and r[0] <= replacement[0] <= r[2]):
                conflict = True
        if any(r != replacement for r in rows
               if r[0] and r[0] <= replacement[0] <= r[2]):
            conflict = True
        if not conflict:
            result.add(old_slot)
    return result


def reconcile_reschedules(cursor, event_id, crawl_event_id, existing, incoming):
    """Apply exact canonical deletions inside the caller's transaction/write lock."""
    cursor.execute('SELECT name,location_id,suppressed FROM events WHERE id=%s', (event_id,))
    row = cursor.fetchone()
    if not row:
        return existing, incoming
    event = dict(zip(('name', 'location_id', 'suppressed'), row))
    cursor.execute('''SELECT ce.id,ce.name,ce.description,ce.location_id,
        cr.website_id,cr.crawled_at,co.start_date,co.start_time,co.end_date,co.end_time
        FROM crawl_events ce JOIN crawl_results cr ON cr.id=ce.crawl_result_id
        JOIN crawl_event_occurrences co ON co.crawl_event_id=ce.id
        WHERE ce.id=%s OR ce.id IN
            (SELECT crawl_event_id FROM event_sources WHERE event_id=%s)''',
                   (crawl_event_id, event_id))
    sources = {}
    for source_id, name, description, location, website, crawled, *occ in cursor.fetchall():
        source = sources.setdefault(source_id, dict(id=source_id, name=name,
            description=description, location_id=location, website_id=website,
            crawled_at=crawled, occurrences=[]))
        source['occurrences'].append(occ)
    removed = superseded_slots(event, list(existing) + list(incoming), list(sources.values()))
    for row in existing:
        if _slot(row) in removed:
            cursor.execute('''DELETE FROM event_occurrences WHERE event_id=%s
                AND start_date=%s AND COALESCE(start_time,'')=%s
                AND (end_date IS NULL OR end_date=start_date)
                AND COALESCE(end_time,'')=%s''',
                           (event_id, row[0], row[1] or '', row[3] or ''))
    return ([r for r in existing if _slot(r) not in removed],
            [r for r in incoming if _slot(r) not in removed])
