"""Persist event pictograms under the shared lock; exporting remains read-only.

Default is a dry run. --apply validates saved assignments without classifying. --init-schema
explicitly installs the table. --manual EVENT_ID --icon ID|fallback --reason TEXT
sets a protected editorial choice (requires --apply). No command uploads data.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from event_icons import ROOT, ICON_IDS, RULE_VERSION, input_hash, propose

COLUMNS = ('event_id','icon_id','origin','rule_version','input_hash','review_required','reason','evidence_json')


def load_assignments(cursor, ids=None):
    try:
        sql = 'SELECT ' + ','.join(COLUMNS) + ' FROM event_icon_assignments'
        if ids is not None:
            if not ids:
                return {}
            sql += ' WHERE event_id IN (' + ','.join(['%s'] * len(ids)) + ')'
        cursor.execute(sql, tuple(ids) if ids is not None else ())
        return {row[0]: dict(zip(COLUMNS,row)) for row in cursor.fetchall()}
    except Exception as exc:
        if getattr(exc, 'errno', None) == 1146:  # old DB / rolling migration: Unicode fallback
            return {}
        raise


def require_lock(cursor):
    cursor.execute("SELECT IS_USED_LOCK('fomo_write') = CONNECTION_ID()")
    if cursor.fetchone()[0] != 1:
        raise RuntimeError('Event icon writes require the shared fomo_write lock')


def fetch_events(cursor, ids=None):
    if ids is None:
        from constants import get_active_date_window
        start, end = get_active_date_window()
        from exporter import _PUBLISHABLE_WEBSITE_GATE
        cursor.execute(f'''SELECT e.id,e.name,e.description FROM events e
            JOIN locations l ON l.id=e.location_id LEFT JOIN websites w ON w.id=e.website_id
            WHERE e.archived=0 AND e.suppressed=0 AND l.lat IS NOT NULL AND l.lng IS NOT NULL
            AND ({_PUBLISHABLE_WEBSITE_GATE})
            AND EXISTS (SELECT 1 FROM event_occurrences o WHERE o.event_id=e.id
              AND COALESCE(o.end_date,o.start_date)>=%s AND o.start_date<=%s) ORDER BY e.id''', (start,end))
    else:
        if not ids:
            return []
        cursor.execute('SELECT id,name,description FROM events WHERE id IN (' + ','.join(['%s']*len(ids)) + ')',tuple(ids))
    events = {r[0]:dict(id=r[0],name=r[1],description=r[2],tags=[]) for r in cursor.fetchall()}
    event_ids=list(events)
    for offset in range(0,len(event_ids),1000):
        chunk=event_ids[offset:offset+1000]
        cursor.execute('SELECT et.event_id,t.name FROM event_tags et JOIN tags t ON t.id=et.tag_id WHERE et.event_id IN (' + ','.join(['%s']*len(chunk))+')',tuple(chunk))
        for eid,tag in cursor.fetchall():
            events[eid]['tags'].append(tag)
    return list(events.values())


def desired_assignment(event, existing=None):
    fingerprint=input_hash(event)
    if existing and existing['origin'] in ('manual','agent'):
        # Preserve the decision, but withhold it from export if content changed.
        return dict(existing, review_required=int(bool(existing['review_required']) or existing['input_hash']!=fingerprint))
    result=propose(event)
    if result['decision']=='fallback':
        return None
    return dict(event_id=event['id'],icon_id=result['icon_id'],origin='rule',rule_version=RULE_VERSION,
                input_hash=fingerprint,review_required=int(result['decision']=='review'),
                reason=result['reason'].replace('; pending editorial review.','.'),
                evidence_json=json.dumps(result['evidence'],ensure_ascii=False))


def export_icon(event, assignment):
    if not assignment or assignment['review_required'] or assignment['icon_id'] not in ICON_IDS:
        return None
    if assignment['origin']=='rule' and assignment['rule_version']!=RULE_VERSION:
        return None
    return assignment['icon_id'] if assignment['input_hash']==input_hash(event) else None


def save(cursor, assignment):
    cursor.execute('INSERT INTO event_icon_assignments (' + ','.join(COLUMNS) + ') VALUES (' + ','.join(['%s']*len(COLUMNS)) + ') ON DUPLICATE KEY UPDATE ' + ','.join(f'{c}=VALUES({c})' for c in COLUMNS[1:]),tuple(assignment[c] for c in COLUMNS))


def sync_assignments(cursor, events=None, apply=False):
    """Maintain saved choices only. New semantic decisions belong to agent review.

    The historical name is retained for callers; this no longer invokes propose.
    """
    if apply:
        require_lock(cursor)
    events=fetch_events(cursor) if events is None else events
    existing=load_assignments(cursor)
    stats=Counter(events=len(events))
    for event in events:
        old=existing.get(event['id'])
        new=retained_assignment(event,old)
        if new==old:
            stats['unchanged']+=1
        elif new is None:
            stats['removed']+=1
            if apply:
                cursor.execute('DELETE FROM event_icon_assignments WHERE event_id=%s',(event['id'],))
        else:
            stats['updated' if old else 'created']+=1
            if apply:
                save(cursor,new)
        if export_icon(event,new):
            stats['assigned']+=1
        if new and new['review_required']:
            stats['review']+=1
    return dict(stats)


def retained_assignment(event, existing=None):
    if not existing:
        return None
    stale = existing['input_hash'] != input_hash(event)
    unknown = existing['icon_id'] is not None and existing['icon_id'] not in ICON_IDS
    return dict(existing, review_required=int(bool(existing['review_required']) or stale or unknown))


def manual_assignment(event, icon_id, reason):
    if icon_id is not None and icon_id not in ICON_IDS:
        raise ValueError('Unknown icon ID')
    if not reason.strip():
        raise ValueError('A manual decision needs a reason')
    return dict(event_id=event['id'],icon_id=icon_id,origin='manual',rule_version=None,
                input_hash=input_hash(event),review_required=0,reason=reason,evidence_json='[]')


def merge_manual_decisions(event, assignments):
    """Preserve equal manual choices; conflicting choices become a locked fallback."""
    manual=[a for a in assignments if a and a['origin']=='manual']
    # Human decisions take precedence. Agent decisions survive a merge but must
    # be re-reviewed with the surviving event's full context.
    if not manual:
        agents=[a for a in assignments if a and a['origin']=='agent']
        if agents:
            result=dict(agents[0],event_id=event['id'],review_required=1)
            if len({a['icon_id'] for a in agents}) > 1:
                result.update(icon_id=None,reason='Conflicting agent icon decisions after event merge.')
            return result
    if not manual:
        return None
    conflicts=len({a['icon_id'] for a in manual})>1 or any(
        a['icon_id'] is not None and a['icon_id'] not in ICON_IDS for a in manual)
    pending=conflicts or any(a['review_required'] or a['input_hash'] != input_hash(event) for a in manual)
    result=manual_assignment(event, None if conflicts else manual[0]['icon_id'],
        'Conflicting manual icon decisions after event merge.' if conflicts else manual[0]['reason'])
    result['review_required']=int(pending)
    result['evidence_json']=json.dumps(manual,ensure_ascii=False)
    return result


def merge_assignments(cursor, keep_id, remove_id):
    # Dedupe callers already hold the same shared lock. Missing-table old installs
    # continue to merge normally until their explicit icon migration is applied.
    rows=load_assignments(cursor, [keep_id, remove_id])
    decisions=[rows.get(keep_id),rows.get(remove_id)]
    if not any(decisions):
        return
    require_lock(cursor)
    event=fetch_events(cursor,[keep_id])[0]
    result=merge_manual_decisions(event,decisions)
    if result:
        save(cursor,result)
    else:
        # Keep a surviving legacy choice if valid; never classify during merge.
        result=retained_assignment(event,rows.get(keep_id))
        if result:
            save(cursor,result)
        else:
            cursor.execute('DELETE FROM event_icon_assignments WHERE event_id=%s',(keep_id,))
    cursor.execute('DELETE FROM event_icon_assignments WHERE event_id=%s',(remove_id,))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--init-schema',action='store_true')
    parser.add_argument('--manual',type=int)
    parser.add_argument('--icon')
    parser.add_argument('--reason')
    parser.add_argument('--backup',type=Path)
    parser.add_argument('--export-site',action='store_true')
    args=parser.parse_args()
    if (args.init_schema or args.export_site or args.manual is not None) and not args.apply:
        parser.error('Schema, manual choices, and local export require --apply')
    if args.manual is not None and (not args.icon or not args.reason):
        parser.error('--manual requires --icon ID|fallback and --reason')
    from db import create_connection
    from dblock import write_lock
    conn=create_connection()
    if conn is None:
        raise RuntimeError('Database unavailable')
    try:
        cursor=conn.cursor()
        if not args.apply:
            print(json.dumps(sync_assignments(cursor),indent=2));return
        with write_lock(conn,label='event_icon_assignments'):
            if args.init_schema:
                cursor.execute((ROOT/'database/migrations/20260908_event_icons.sql').read_text())
                conn.commit()
            if args.backup:
                args.backup.parent.mkdir(parents=True,exist_ok=True)
                args.backup.write_text(json.dumps(load_assignments(cursor),ensure_ascii=False,indent=2))
            if args.manual is not None:
                events=fetch_events(cursor,[args.manual])
                if not events:
                    raise ValueError('Event does not exist')
                save(cursor,manual_assignment(events[0],None if args.icon=='fallback' else args.icon,args.reason))
                print('Saved manual icon decision for event',args.manual)
            else:
                print(json.dumps(sync_assignments(cursor,apply=True),indent=2))
            conn.commit()
            if args.export_site:
                from exporter import export_events
                stats = export_events(cursor)
                stats['organizer_roots'] = len(stats.pop('organizer_root_ids', []))
                print(json.dumps(stats,default=str,indent=2))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__=='__main__':
    main()
