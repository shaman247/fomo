"""Reviewed venue corrections bounded by source, event identity and dates.

Rules are deployment data. A correction never applies to another title, another
publisher or a later season merely because it shares a listing URL.
"""
from datetime import date, datetime
import unicodedata
from urllib.parse import urlsplit, urlunsplit


def name_key(value):
    return ' '.join(unicodedata.normalize('NFKC', value or '').casefold().split())


def url_key(value):
    try:
        parsed = urlsplit(value or '')
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            return ''
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip('/'), parsed.query, ''))
    except ValueError:
        return ''


def as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def load_rules(cursor):
    cursor.execute('''SELECT r.id, r.website_id, r.event_name, r.source_url,
        r.url_prefix, r.valid_from, r.valid_until, r.location_id,
        r.location_name, r.sublocation, l.lat, l.lng, l.emoji
        FROM event_venue_overrides r JOIN locations l ON l.id=r.location_id
        WHERE r.enabled=1''')
    fields=('id','website_id','event_name','source_url','url_prefix','valid_from',
            'valid_until','location_id','location_name','sublocation','lat','lng','emoji')
    return [dict(row) if isinstance(row, dict) else dict(zip(fields,row))
            for row in cursor.fetchall()]


def find_rule(rules, website_id, name, urls, occurrences):
    """Require every occurrence to be reviewed and assigned to one venue.

    Separate reviewed date windows may cover a recurring class. Mixed venues
    decline here; the processor resolves each date before grouping it.
    """
    bounds=[]
    for occurrence in occurrences or []:
        if isinstance(occurrence,dict):
            start,end=occurrence.get('start_date'),occurrence.get('end_date')
        else:
            start=occurrence[0] if occurrence else None
            end=occurrence[2] if len(occurrence)>2 else None
        start,end=as_date(start),as_date(end) if end else as_date(start)
        if start is None or end is None:
            return None
        bounds.append((start,end))
    if not bounds:
        return None
    urls=[url_key(u) for u in urls or [] if u]
    matches=[]
    for rule in rules:
        if rule['website_id']!=website_id or name_key(rule['event_name'])!=name_key(name):
            continue
        expected=url_key(rule['source_url'])
        # Prefixes are for a publisher's stable event-slug stem, never for
        # lookalike hosts (example.org.evil) or an empty URL.
        expected_parts = urlsplit(expected)
        if not expected or not any(
                u == expected or rule['url_prefix'] and u.startswith(expected)
                and urlsplit(u).netloc == expected_parts.netloc
                and expected_parts.path.strip('/') for u in urls):
            continue
        matches.append(rule)
    if not matches:
        return None
    chosen=[]
    for start,end in bounds:
        covered=[r for r in matches
                 if as_date(r['valid_from']) <= start <= end <= as_date(r['valid_until'])]
        if not covered:
            return None
        targets={(r['location_id'],r['location_name'],r['sublocation']) for r in covered}
        if len(targets)>1:
            raise ValueError(f'Conflicting reviewed venue overrides for website {website_id}, event {name!r}')
        chosen.append(covered[0])
    if len({(r['location_id'],r['location_name'],r['sublocation']) for r in chosen}) != 1:
        return None
    return chosen[0]


def for_event(rules, website_id, event):
    occurrences=event.get('occurrences')
    if occurrences is None and event.get('start_date'):
        occurrences=[event]
    urls=event.get('urls') or ([event['url']] if event.get('url') else [])
    return find_rule(rules,website_id,event.get('name'),urls,occurrences)
