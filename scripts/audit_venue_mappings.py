#!/usr/bin/env python3
"""Read-only, source-aware audit of same-name events at different venues.

Groups events in Python before fetching their dates, avoiding a quadratic SQL
join across the entire occurrence table. Reports evidence; never merges rows.
"""
import argparse
from collections import defaultdict
from datetime import date
from itertools import combinations
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from db import create_connection


def audit(cursor, today):
    cursor.execute('''SELECT e.id,e.name,e.website_id,e.location_id,
        l.name venue,l.address,l.generic_location,w.name publisher
        FROM events e JOIN locations l ON l.id=e.location_id
        LEFT JOIN websites w ON w.id=e.website_id
        WHERE e.archived=0 AND e.suppressed=0''')
    groups=defaultdict(list)
    for row in cursor.fetchall():
        groups[' '.join(row['name'].casefold().split())].append(row)
    groups={name:rs for name,rs in groups.items() if len({r['location_id'] for r in rs})>1}
    ids=sorted({r['id'] for rs in groups.values() for r in rs})
    if not ids:return {'pairs':[], 'counts':{}}
    dates=defaultdict(list);urls=defaultdict(set);sources=defaultdict(set)
    # Bounded batches also keep the query packet small on large deployments.
    for start in range(0,len(ids),1000):
        batch=ids[start:start+1000];ph=','.join(['%s']*len(batch))
        cursor.execute(f'''SELECT event_id,start_date,COALESCE(end_date,start_date) end_date
            FROM event_occurrences WHERE event_id IN ({ph})
            AND COALESCE(end_date,start_date)>=%s''',(*batch,today))
        for r in cursor.fetchall():dates[r['event_id']].append((r['start_date'],r['end_date']))
        cursor.execute(f'SELECT event_id,url FROM event_urls WHERE event_id IN ({ph})',batch)
        for r in cursor.fetchall():urls[r['event_id']].add(r['url'])
        cursor.execute(f'''SELECT DISTINCT es.event_id,cr.website_id,ce.location_id,w.name publisher
            FROM event_sources es JOIN crawl_events ce ON ce.id=es.crawl_event_id
            JOIN crawl_results cr ON cr.id=ce.crawl_result_id JOIN websites w ON w.id=cr.website_id
            WHERE es.event_id IN ({ph})''',batch)
        for r in cursor.fetchall():sources[r['event_id']].add((r['website_id'],r['location_id'],r['publisher']))
    pairs=[];counts=defaultdict(int)
    for name,events in groups.items():
        for a,b in combinations(events,2):
            if a['location_id']==b['location_id']:continue
            if not any(max(x[0],y[0])<=min(x[1],y[1]) for x in dates[a['id']] for y in dates[b['id']]):continue
            shared_urls=urls[a['id']]&urls[b['id']]
            source_a=sources[a['id']];source_b=sources[b['id']]
            common={s[0] for s in source_a}&{s[0] for s in source_b}
            # Branch programming is only classified as such when the SAME
            # library publisher has sources explicitly pinned to EACH branch.
            library_branches=any('librar' in s[2].casefold() and s[0] in common
                and s[1]==a['location_id'] and any(t[0]==s[0] and t[1]==b['location_id'] for t in source_b)
                for s in source_a)
            category=('shared_url' if shared_urls else 'library_branches' if library_branches else 'review')
            counts[category]+=1
            pairs.append(dict(name=name,a=a,b=b,category=category,shared_urls=sorted(shared_urls),
                sources_a=sorted(source_a,key=str),sources_b=sorted(source_b,key=str)))
    return {'as_of':today,'counts':dict(counts),'candidate_events':len(ids),'pairs':pairs}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--date',type=date.fromisoformat,default=date.today())
    args=ap.parse_args();conn=create_connection()
    if conn is None:raise RuntimeError('Database unavailable')
    try:report=audit(conn.cursor(dictionary=True),args.date)
    finally:conn.close()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,default=str,indent=2))
    print(json.dumps(report['counts'],sort_keys=True))

if __name__=='__main__':main()
