"""Keep date-specific room and eligibility evidence when grouping a series."""
import json
import re

# Words whose presence flips meaning ("Adults only" vs "All ages", "No
# registration" vs "Registration required"); texts must agree on them to fold.
_POLARITY_WORDS = frozenset(('no', 'not', 'only', 'free', 'cancelled', 'canceled',
                             'postponed', 'rescheduled', 'sold', 'waitlist'))
_TRUNCATION_MARK = re.compile(r'\s*(?:…|\.\.\.)\s*$')


def _placeholder_description(description):
    normalized = ' '.join((description or '').split()).casefold()
    return normalized in ('', 'no description available.')


def _words(text):
    return re.findall(r'\w+', text.casefold())


def _specifics(text):
    """Numbers and mid-sentence capitalized words: names, prices, ages, dates."""
    found = set()
    for sentence in re.split(r'(?<=[.!?;:])\s+|\n+', text):
        for i, word in enumerate(re.findall(r"[\w$][\w'’$.-]*", sentence)):
            word = word.rstrip('.')
            if any(ch.isdigit() for ch in word) or (i and word[:1].isupper()):
                found.add(word.casefold())
    return found


def _truncated_prefix(short, full):
    """`short` is a listing teaser cut from `full` (mid-word or with an ellipsis)."""
    if not _cut_off(short):
        return False
    head, body = _words(_TRUNCATION_MARK.sub('', short)), _words(full)
    if len(head) >= len(body) or not head:
        return False
    # The last word may be cut mid-word ("exerc" of "exercises").
    return head[:-1] == body[:len(head) - 1] and body[len(head) - 1].startswith(head[-1])


def _same_text(a, b):
    """Two extractions of one listing: a paraphrase or a truncated teaser.

    Rewording is fine; a difference in names, numbers or polarity words (one
    night's lineup, a second session's fee, an age band) is session evidence.
    """
    if _truncated_prefix(a, b) or _truncated_prefix(b, a):
        return True
    return (_specifics(a) == _specifics(b)
            and _POLARITY_WORDS & set(_words(a)) == _POLARITY_WORDS & set(_words(b)))


def _display_variants(details):
    """Fold variants that say the same thing so the description shows only real
    per-session differences; `session_details` itself keeps every variant."""
    substantive = [v for v in details if not _placeholder_description(v['description'])]
    rooms = {v['sublocation'] for v in substantive}
    folded = []
    for variant in details:
        stub = _placeholder_description(variant['description'])
        # A stub only says where its sessions were; keep that when no text does.
        if stub and (not variant['sublocation'] or variant['sublocation'] in rooms):
            continue
        home = next((f for f in folded if f['sublocation'] == variant['sublocation']
                     and _placeholder_description(f['description']) == stub
                     and (stub or _same_text(f['description'], variant['description']))),
                    None)
        if home is None:
            folded.append({**variant, 'sessions': list(variant['sessions'])})
            continue
        home['sessions'] += [s for s in variant['sessions'] if s not in home['sessions']]
        if _better_text(variant['description'], home['description']):
            home['description'] = variant['description']
    if not substantive and len(folded) < 2:
        # All stubs, at most one named room: one placeholder the detail crawl can fill.
        stub = max(details, key=lambda v: len(v['description']))
        return [{**(folded[0] if folded else stub), 'description': stub['description']}]
    return folded


def _cut_off(text):
    return not re.search(r'[.!?)"”]\s*$', text) or bool(_TRUNCATION_MARK.search(text))


def _better_text(new, old):
    """Longer wins, except that a complete text beats one cut off mid-sentence."""
    if _cut_off(new) != _cut_off(old):
        return _cut_off(old)
    return len(new) > len(old)


def _description_session_key(row):
    """Require the same identified, timed session before discarding a stub."""
    fields = tuple((row.get(k) or '').strip() for k in
                   ('url', 'start_date', 'start_time', 'end_date', 'end_time',
                    'sublocation', 'location'))
    if not all(fields[:3]):
        return None
    return fields + (row.get('location_id'),)


def preserve_session_details(event, rows):
    substantive_sessions = {
        key for row in rows
        if not _placeholder_description(row.get('description'))
        if (key := _description_session_key(row)) is not None
    }
    description_rows = [
        row for row in rows
        if not (_placeholder_description(row.get('description'))
                and _description_session_key(row) in substantive_sessions)
    ]
    variants = {}
    for row in description_rows:
        description = (row.get('description') or '').strip()
        room = (row.get('sublocation') or '').strip()
        key = (description, room)
        variant = variants.setdefault(key, {'description': description, 'sublocation': room,
                                             'sessions': []})
        session = {k: row.get(k) or '' for k in
                   ('start_date', 'start_time', 'end_date', 'end_time', 'url')}
        if session not in variant['sessions']:
            variant['sessions'].append(session)
    if len(variants) < 2:
        if variants and len(description_rows) < len(rows):
            # The first row may have seeded the group's placeholder text.
            event['description'] = next(iter(variants.values()))['description']
        return
    details = list(variants.values())
    event['session_details'] = details
    render_session_details(event, details)


def render_session_details(event, details):
    """Set the event's description (and mixed-room sublocation) from its variants."""
    shown = _display_variants(details)
    if len(shown) == 1:
        event['description'] = shown[0]['description']
        return
    sections = []
    for variant in shown:
        labels = []
        for session in variant['sessions']:
            label = ' '.join(filter(None, [session['start_date'], session['start_time']]))
            if session['end_date'] and session['end_date'] != session['start_date']:
                label += ' through ' + session['end_date']
            if session['end_time']:
                label += '–' + session['end_time']
            if label not in labels:
                labels.append(label)
        heading = '; '.join(labels)
        if variant['sublocation']:
            heading += ' — ' + variant['sublocation']
        if _placeholder_description(variant['description']):
            sections.append(heading)
        else:
            sections.append(heading + '\n' + variant['description'])
    event['description'] = '\n\n'.join(sections)
    if len({v['sublocation'] for v in shown}) > 1:
        event['sublocation'] = 'Varies by session; see description'


def refresh_source_session_details(cursor, event_id, crawl_event_id, raw_data):
    """Refresh grouped details only when the canonical text has source provenance.

    A manual description or another publisher's text is not overwritten. The
    stored raw marker is produced by the processor, not the extraction schema.
    """
    try:
        data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
    except (TypeError, ValueError):
        return False
    if not isinstance(data, dict) or not isinstance(data.get('session_details'), list):
        return False
    if len(data['session_details']) < 2 or not data.get('description'):
        return False
    cursor.execute('''SELECT e.description FROM events e WHERE e.id=%s AND (
        e.description IS NULL OR e.description='' OR e.description='No description available.'
        OR EXISTS (SELECT 1 FROM event_sources es
          JOIN crawl_events prior ON prior.id=es.crawl_event_id
          JOIN crawl_results pr ON pr.id=prior.crawl_result_id
          JOIN crawl_events incoming ON incoming.id=%s
          JOIN crawl_results ir ON ir.id=incoming.crawl_result_id
          WHERE es.event_id=e.id AND pr.website_id=ir.website_id
            AND prior.description=e.description))''', (event_id, crawl_event_id))
    if cursor.fetchone() is None:
        return False
    cursor.execute('UPDATE events SET description=%s,sublocation=%s WHERE id=%s',
                   (data['description'], data.get('sublocation') or None, event_id))
    return True
