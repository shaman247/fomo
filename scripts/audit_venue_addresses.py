#!/usr/bin/env python3
"""Read-only address/pin audit, including generic parks and neighborhoods.

Compares event sublocations to verified venue addresses already in the database.
Unmatched addresses remain in the report for source review/name-first geocoding;
shared-building addresses are never treated as an automatic venue assignment.
"""
import argparse,json,math,sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pipeline'))
from db import create_connection
from processor import _extract_street_address_loose, sublocation_looks_like_address, sublocation_redundant_with_address, _parse_city_state


def distance_m(a,b):
    if any(x is None for x in (a['lat'],a['lng'],b['lat'],b['lng'])):return None
    x,y=map(math.radians,(float(a['lat']),float(b['lat'])))
    dx=y-x;dy=math.radians(float(b['lng'])-float(a['lng']))
    return round(6371000*2*math.asin(min(1,math.sqrt(math.sin(dx/2)**2+math.cos(x)*math.cos(y)*math.sin(dy/2)**2))))


def audit(cursor,threshold=500):
    cursor.execute('SELECT id,name,address,lat,lng,generic_location FROM locations')
    locations={r['id']:r for r in cursor.fetchall()};addresses=defaultdict(list)
    for l in locations.values():
        key=_extract_street_address_loose(l['address'] or '')
        if key:addresses[key].append(l)
    cursor.execute('''SELECT id,name,website_id,location_id,location_name,sublocation
        FROM events WHERE archived=0 AND suppressed=0 AND sublocation IS NOT NULL''')
    events=cursor.fetchall();conflicts=[];unknown=[];nearby=[];checked=0
    for e in events:
        sub=e['sublocation'];home=locations.get(e['location_id'])
        if not home or not sublocation_looks_like_address(sub):continue
        checked+=1
        if sublocation_redundant_with_address(sub,home['address'] or ''):continue
        key=_extract_street_address_loose(sub)
        if not key:unknown.append(dict(event=e,venue=home,reason='address_not_parsed'));continue
        candidates=[dict(l,distance_m=distance_m(home,l)) for l in addresses.get(key,[]) if l['id']!=home['id']]
        # Keep all co-tenants visible. These are candidate addresses, not proof
        # that an event is hosted by a particular tenant.
        item=dict(event=e,venue=home,address_key=key,candidates=candidates)
        if not candidates:unknown.append(item)
        elif any(l['distance_m'] is not None and l['distance_m']>=threshold for l in candidates):conflicts.append(item)
        else:nearby.append(item)
    return dict(counts=dict(active_events_with_sublocation=len(events),address_shaped=checked,
                distant_conflicts=len(conflicts),unresolved_addresses=len(unknown),nearby_buildings=len(nearby)),
                threshold_m=threshold,conflicts=conflicts,unresolved=unknown,nearby=nearby)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path);ap.add_argument('--threshold',type=int,default=500);args=ap.parse_args()
    c=create_connection()
    try:report=audit(c.cursor(dictionary=True),args.threshold)
    finally:c.close()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,default=str,indent=2));print(json.dumps(report['counts']))
if __name__=='__main__':main()
