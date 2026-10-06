"""Reviewed public-link exclusions without changing truthful source history.

A URL's later death/reuse does not invalidate what an archived publisher said.
Only the public canonical link is gated, and only while the reviewed event's
identity/sessions and its replacement link remain intact.
"""
import hashlib
import json


def _hash(url):
    return hashlib.sha256(url.encode('utf-8')).hexdigest()


def _snapshot(cursor, event_id):
    cursor.execute('SELECT name, location_id, archived, suppressed FROM events WHERE id=%s', (event_id,))
    row = cursor.fetchone()
    if not row or row[2] or row[3]:
        return None
    cursor.execute('''SELECT start_date,start_time,end_date,end_time FROM event_occurrences
                      WHERE event_id=%s ORDER BY start_date,start_time,end_date,end_time''', (event_id,))
    slots = [list(map(lambda value: str(value) if value is not None else None, slot))
             for slot in cursor.fetchall()]
    if not slots:
        return None
    return {'name': row[0], 'location_id': row[1], 'occurrences': slots}


def load_url_exclusions(cursor):
    """One compact index per merge; ordinary URL writes need no extra queries."""
    cursor.execute('SELECT event_id,url_hash,url,replacement_url,event_snapshot FROM event_url_exclusions')
    return {(row[0], row[1]): tuple(row[2:]) for row in cursor.fetchall()}


def canonical_url_allowed(cursor, event_id, url, *, index=None):
    """False only for an exact, still-valid reviewed canonical URL exclusion.

    Apply after matching, before every URL insertion or priority promotion.
    New canonical IDs and changed schedules cannot inherit another review.
    """
    if not isinstance(url, str) or not url:
        return True
    if index is None:
        cursor.execute('''SELECT url,replacement_url,event_snapshot FROM event_url_exclusions
                          WHERE event_id=%s AND url_hash=%s''', (event_id, _hash(url)))
        row = cursor.fetchone()
    else:
        row = index.get((event_id, _hash(url)))
    if not row or row[0] != url:
        return True
    try:
        reviewed = json.loads(row[2])
    except (ValueError, TypeError):
        return True
    if _snapshot(cursor, event_id) != reviewed:
        return True
    cursor.execute('SELECT url FROM event_urls WHERE event_id=%s', (event_id,))
    # Python comparison is byte-exact; database URL collation may not be.
    return not any(existing[0] == row[1] for existing in cursor.fetchall())


def record_url_exclusion(cursor, event_id, url, replacement_url, evidence):
    """Record one reviewed exclusion; caller owns lock, audit and transaction.

    Evidence is a receipt path or attributable source explanation. No network
    liveness or identity is inferred by this function, and no source is edited.
    """
    if (not isinstance(evidence, str) or not evidence.strip()
            or not url or not replacement_url or url == replacement_url):
        raise ValueError('Distinct URLs and explicit review evidence are required')
    snapshot = _snapshot(cursor, event_id)
    if snapshot is None:
        raise ValueError('Exclusions require an active event with recorded sessions')
    cursor.execute('SELECT url FROM event_urls WHERE event_id=%s', (event_id,))
    if not any(row[0] == replacement_url for row in cursor.fetchall()):
        raise ValueError('The reviewed replacement must already belong to this event')
    cursor.execute('''INSERT INTO event_url_exclusions
        (event_id,url_hash,url,replacement_url,event_snapshot,evidence)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE replacement_url=VALUES(replacement_url),
          event_snapshot=VALUES(event_snapshot),evidence=VALUES(evidence),reviewed_at=CURRENT_TIMESTAMP''',
        (event_id,_hash(url),url,replacement_url,json.dumps(snapshot,sort_keys=True),evidence))
