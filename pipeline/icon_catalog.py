"""Approved artwork aliases and a persistent review queue for new emoji.

Unicode remains source data. Resolution is exact (ignoring presentation selectors),
never an activity/name classifier; unknown values render the catalog fallback.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

CATALOG_DIR = Path(__file__).resolve().parents[1] / 'config' / 'event-icons'
FALLBACK_ID = 'noto-1f4c5'

def canonical(emoji):
    return (emoji or '').strip().replace('\ufe0e', '').replace('\ufe0f', '')

@lru_cache(maxsize=1)
def catalog():
    custom = json.loads((CATALOG_DIR/'catalog.json').read_text())['icons']
    noto = json.loads((CATALOG_DIR/'noto.json').read_text())['icons']
    return {e['id'] for e in custom+noto}, {e['emoji']:e['id'] for e in noto}

def resolve_icon(emoji, preferred=None):
    ids, aliases = catalog()
    return preferred if preferred in ids else aliases.get(canonical(emoji), FALLBACK_ID)

def unknown_emoji(emoji):
    value = canonical(emoji)
    return bool(value) and value not in catalog()[1]

def record_unknown(cursor, emoji, source_kind, source_id=None, source_name=''):
    """Called in the extraction transaction; never approve or alter the emoji."""
    if not unknown_emoji(emoji): return False
    value = canonical(emoji)
    cursor.execute('''INSERT INTO icon_review_queue
        (emoji_hash,emoji,source_kind,source_id,source_name)
        VALUES (%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE last_seen=CURRENT_TIMESTAMP,
            observations=observations+1''',
        (hashlib.sha256(value.encode()).hexdigest(),value,source_kind,source_id,(source_name or '')[:500]))
    return True

def inventory(cursor):
    """Binary grouping preserves distinct emoji under MariaDB's Unicode collation."""
    result = {}
    for table in ('events','crawl_events','locations','tags','websites'):
        cursor.execute(f'''SELECT BINARY emoji,COUNT(*),MIN(id) FROM {table}
            WHERE emoji IS NOT NULL AND emoji != '' GROUP BY BINARY emoji''')
        result[table] = [(e.decode() if isinstance(e,bytes) else e,count,row_id)
                         for e,count,row_id in cursor.fetchall()]
    return result

def flag_metadata(cursor):
    """Catch newly edited tag/place/organizer emoji in the locked publish tail."""
    for table in ('locations', 'tags', 'websites'):
        cursor.execute(f'''SELECT BINARY emoji,MIN(id) FROM {table}
            WHERE emoji IS NOT NULL AND emoji != '' GROUP BY BINARY emoji''')
        rows = cursor.fetchall()
        for emoji, row_id in rows:
            record_unknown(cursor, emoji.decode() if isinstance(emoji,bytes) else emoji, table, row_id)

def main():
    import argparse
    from db import create_connection
    from dblock import write_lock
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory',type=Path,help='Save historical database emoji counts (read only)')
    p.add_argument('--scan',action='store_true',help='Find unknown values across the database')
    p.add_argument('--apply',action='store_true',help='Save scan findings under the shared lock')
    p.add_argument('--init-schema',action='store_true')
    p.add_argument('--output',type=Path,help='Write the pending review report')
    p.add_argument('--dismiss',help='Dismiss one reviewed emoji value, preserving its history')
    p.add_argument('--note',help='Reason for dismissing a malformed/unsupported value')
    a=p.parse_args()
    if a.dismiss and (not a.apply or not a.note): p.error('--dismiss requires --apply and --note')
    conn=create_connection()
    if not conn: raise SystemExit('Database unavailable')
    cur=conn.cursor()
    try:
        if a.init_schema:
            if not a.apply: p.error('--init-schema requires --apply')
            with write_lock(conn):
                cur.execute((Path(__file__).resolve().parents[1]/'database/migrations/20260908_icon_review_queue.sql').read_text())
                conn.commit()
        if a.dismiss:
            with write_lock(conn):
                cur.execute("UPDATE icon_review_queue SET status='dismissed',review_note=%s WHERE emoji_hash=%s",
                    (a.note,hashlib.sha256(canonical(a.dismiss).encode()).hexdigest()))
                conn.commit()
        if a.inventory or a.scan:
            rows=inventory(cur)
            if a.inventory:
                a.inventory.parent.mkdir(parents=True,exist_ok=True)
                a.inventory.write_text(json.dumps({t:{e:n for e,n,_ in values} for t,values in rows.items()},ensure_ascii=False,indent=2)+'\n')
            findings=[dict(emoji=e,count=n,source_kind=t,source_id=i) for t,values in rows.items() for e,n,i in values if unknown_emoji(e)]
            print(json.dumps({'unknown_values':len({canonical(r['emoji']) for r in findings}),'affected_rows':sum(r['count'] for r in findings)},indent=2))
            if a.scan and a.apply:
                with write_lock(conn):
                    for row in findings: record_unknown(cur,row['emoji'],row['source_kind'],row['source_id'])
                    conn.commit()
            if not a.apply: return
        cur.execute('''SELECT emoji,source_kind,source_id,source_name,observations,first_seen,last_seen,review_note
            FROM icon_review_queue WHERE status='pending' ORDER BY last_seen DESC''')
        names=[c[0] for c in cur.description]
        report=[dict(zip(names,r)) for r in cur.fetchall()]
        # Importing approved artwork resolves its queue entries at the next scan.
        resolved=[r for r in report if not unknown_emoji(r['emoji'])]
        if a.apply and resolved:
            with write_lock(conn):
                cur.executemany("UPDATE icon_review_queue SET status='resolved' WHERE emoji_hash=%s",
                    [(hashlib.sha256(canonical(r['emoji']).encode()).hexdigest(),) for r in resolved])
                conn.commit()
        pending=[r for r in report if unknown_emoji(r['emoji'])]
        output=json.dumps(pending,ensure_ascii=False,indent=2,default=str)+'\n'
        if a.output:
            a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(output)
        else: print(output)
    finally: cur.close();conn.close()

if __name__=='__main__': main()
