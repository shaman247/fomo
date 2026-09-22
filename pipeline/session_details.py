"""Keep date-specific room and eligibility evidence when grouping a series."""
import json


def preserve_session_details(event, rows):
    variants = {}
    for row in rows:
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
        return
    details = list(variants.values())
    sections = []
    for variant in details:
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
        sections.append(heading + '\n' + variant['description'])
    event['description'] = '\n\n'.join(sections)
    if len({v['sublocation'] for v in details}) > 1:
        event['sublocation'] = 'Varies by session; see description'
    event['session_details'] = details


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
