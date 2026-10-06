import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try:
    from sources.tribe_overflow import retained_records, fetch_and_build_markdown
    from sources.tribe_window import fetch_records
except ImportError:  # source plugins are gitignored per-city (fork contract)
    retained_records = fetch_and_build_markdown = fetch_records = None
from datetime import date

class Response:
    status_code=200  # tribe_window._get reads it (bounded retry on transient statuses)
    def __init__(self,data): self.data=data
    def raise_for_status(self): pass
    def json(self): return self.data
class Session:
    def __init__(self,pages): self.pages=iter(pages);self.calls=[]
    def get(self,url,**kw):self.calls.append(kw);return Response(next(self.pages))
def row(n):return dict(id=n,url=f'https://example.com/event/{n}',title='Public event',start_date='2026-11-10 17:00:00',end_date='2026-11-10 18:00:00')
@unittest.skipIf(fetch_records is None, 'tribe_overflow/tribe_window plugins not installed')
class TribeOverflowTests(unittest.TestCase):
    def test_fourth_page_is_retained(self):
        pages=[dict(events=[row(i) for i in range(k*50,min((k+1)*50,151))],total=151,total_pages=4) for k in range(4)]
        s=Session(pages);r=fetch_records('https://dumbo.nyc/public-spaces/',s,date(2026,10,1));self.assertEqual(len(r),151);self.assertEqual(s.calls[-1]['params']['page'],4)
        self.assertEqual(s.calls[0]['params']['end_date'],'2026-12-30 23:59:59')
    def test_no_silent_partial_inventory(self):
        s=Session([dict(events=[row(1)],total=2,total_pages=1)])
        with self.assertRaisesRegex(ValueError,'count mismatch'):fetch_records('https://dumbo.nyc/public-spaces/',s,date(2026,10,1))
    def test_preserves_archway_delegation(self):
        rows=[dict(id=1,venue=dict(id=7336)),dict(id=2,venue=[dict(id='7336')]),dict(id=3,venue=dict(id=44)),dict(id=4,venue=[])]
        self.assertEqual([r['id'] for r in retained_records('dumbo.nyc',rows)],[3,4]);self.assertEqual(retained_records('brooklyncb6.cityofnewyork.us',rows),rows)
    def test_source_url_scope(self):
        with self.assertRaisesRegex(ValueError,'Unexpected'):fetch_and_build_markdown(['https://dumbo.nyc/events/'])
if __name__=='__main__':unittest.main()
