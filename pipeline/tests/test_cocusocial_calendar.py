import copy
import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from sources.cocusocial_calendar import build_markdown
except ImportError:
    build_markdown = None

@unittest.skipIf(build_markdown is None, 'city-specific source plugin unavailable')
class CocuSocialCalendarTests(unittest.TestCase):
    def event(self, identity='class-1', venue='Venue A, 1 Main St'):
        return dict(eventId=identity, startTimeUTC='2026-11-01T22:30:00Z',
                    endTimeUTC='2026-11-02T00:30:00Z', timezone='America/New_York',
                    courseName='Pasta', venueInfo={'region':'New York City','address':venue},
                    description='<p>Make pasta.</p>', isPrivate=False, cancelled=False)
    def payload(self, events): return dict(code=0, data={'events':events})
    def test_dst_and_distinct_venues_and_sold_out(self):
        a=self.event();a['availableSeats']=0
        body,count=build_markdown(self.payload([a,self.event('class-2','Venue B, 2 Main St')]),date(2026,10,1))
        self.assertEqual(count,2);self.assertEqual(body.count('### Pasta'),2)
        self.assertIn('2026-11-01T17:30:00-05:00',body);self.assertIn('2026-11-01T19:30:00-05:00',body)
        self.assertIn('/newevent/class-1',body)
    def test_same_evidence_compacts_but_keeps_all_slots(self):
        body,count=build_markdown(self.payload([self.event('a'),self.event('b')]),date(2026,10,1))
        self.assertEqual(count,2);self.assertEqual(body.count('### Pasta'),1);self.assertEqual(body.count('**Published session**'),2)
    def test_duplicate_and_partial_inventory_fail(self):
        for payload in (self.payload([self.event(),self.event()]),dict(code=1,data={}),dict(code=0,data={'events':[],'hasMore':True}),dict(code=0,data={'events':[],'total':1})):
            with self.assertRaises(ValueError):build_markdown(payload,date(2026,10,1))
    def test_cancelled_private_and_outside_window_filtered(self):
        a=self.event('private');a['isPrivate']=True;b=self.event('cancel');b['cancelled']=True
        c=self.event('later');c['startTimeUTC']='2027-01-05T22:30:00Z';c['endTimeUTC']='2027-01-06T00:30:00Z'
        _,count=build_markdown(self.payload([a,b,c,self.event('keep')]),date(2026,10,1));self.assertEqual(count,1)
    def test_wrong_region_and_invalid_interval_fail(self):
        a=self.event();a['venueInfo']['region']='Boston'
        b=self.event();b['endTimeUTC']='2026-10-31T00:30:00Z'
        for event in(a,b):
            with self.assertRaises(ValueError):build_markdown(self.payload([event]),date(2026,10,1))
    def test_production_chunking_preserves_every_session(self):
        from extractor import chunk_content, cap_records_per_chunk, cap_occurrences_per_chunk, prune_chunks
        events=[]
        for i in range(48):
            event=self.event(f'session-{i}',f'Venue {i}, 1 Main St')
            event['description']='Make fresh pasta using traditional hand-rolling techniques. '*30
            events.append(event)
        body,count=build_markdown(self.payload(events),date(2026,10,1))
        chunks,_=chunk_content(body)
        chunks=cap_occurrences_per_chunk(cap_records_per_chunk(chunks,8))
        kept,pruned=prune_chunks(chunks,today=date(2026,10,1))
        self.assertFalse(pruned)
        import json
        actual=[json.loads(line.split(': ',1)[1])['source_id'] for chunk in kept
                for line in chunk.splitlines() if line.startswith('**Published session**: ')]
        self.assertEqual(len(actual),count)
        self.assertEqual(set(actual),{event['eventId'] for event in events})
if __name__=='__main__':unittest.main()
