import sys,json,unittest
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try:
 from sources.embedded_google_companions import corsizio_records,corsizio_evidence,fetch_companions
except ImportError:corsizio_records=None
@unittest.skipIf(corsizio_records is None,'city-specific source plugin unavailable')
class CalendarCompanionTests(unittest.TestCase):
 def html(self,events,links=('one',),count=1):
  return '<p>Filtered items found ('+str(count)+')</p>'+''.join('<a href="/event/'+x+'">Class</a>'for x in links)+'<script>events:'+json.dumps(events)+'</script>'
 def event(self,identity='one'):
  return dict(id=identity,name='Class',isPublished=True,status='published',timeZone='America/New_York',dates={'breakdown':[{'start':'2026-11-02T23:00:00Z','end':'2026-11-03T01:30:00Z','label':'Snow Make-Up Date'}]},location={'name':'Studio','street':'1 Main St'})
 def test_visible_scope_and_local_dates_preserve_condition(self):
  body,count=corsizio_evidence(self.html([self.event(),self.event('hidden')]),date(2026,10,1))
  self.assertEqual(count,1);self.assertIn('2026-11-02T18:00:00-05:00',body);self.assertIn('Snow Make-Up Date',body);self.assertNotIn('/event/hidden',body)
 def test_incomplete_or_duplicate_visible_inventory_fails(self):
  for html in [self.html([self.event()],count=2),self.html([]),self.html([self.event(),self.event()])]:
   with self.assertRaises(ValueError):corsizio_records(html)
 def test_javascript_is_data_and_never_executed(self):
  html=self.html([self.event()]).replace('"Class"','(()=>{throw Error("execute")})()')
  with self.assertRaises(ValueError):corsizio_records(html)
 def test_boathouse_companion_preserves_season_and_location(self):
  class R:
   text='<main>Community Rowing at Pier 40, April through November.</main>'
   def raise_for_status(self):pass
  class S:
   def get(self,url,**kwargs):self.url=url;return R()
  session=S();text,count=fetch_companions('villagecommunityboathouse.org','',session)
  self.assertEqual(session.url,'https://villagecommunityboathouse.org/');self.assertIn('April through November',text);self.assertIn('Pier 40',text)
if __name__=='__main__':unittest.main()
