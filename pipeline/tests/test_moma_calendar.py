"""The optional deployment pager awaits complete growth, including scroll paging."""
import json,shutil,subprocess,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try:
 from sources.moma_calendar import PAGER_JS, check_payload
except ImportError:
 PAGER_JS=None

@unittest.skipUnless(PAGER_JS and shutil.which('node'),'optional MoMA deployment plugin and Node required')
class MoMAPagerTests(unittest.TestCase):
 def run_pager(self,mode):
  harness=r'''
  let n=36, now=0, calls=0, dataset={};
  Date.now=()=>now;
  global.setTimeout=(callback,ms)=>{now+=ms;callback();};
  global.location={pathname:'/calendar/'};
  const counts=[36,72,108,144,180,216,230];
  function grow(){n=counts[Math.min(++calls,counts.length-1)];}
  const button={textContent:'Show more events',scrollIntoView(){if(MODE==='scroll')grow();},querySelector(){return this;},click(){if(MODE==='click')grow();}};
  global.document={createElement(){return{};},body:{appendChild(){}},querySelector(){return{dataset,querySelectorAll(){return Array(n).fill({});}};},querySelectorAll(){return n===230?[]:[button];}};
  global.getComputedStyle=()=>({visibility:'visible',opacity:'1'});
  (async()=>{try{ SCRIPT; console.log(JSON.stringify({n,calls,complete:dataset.fomoCalendarComplete}));}catch(e){console.log(JSON.stringify({error:e.message,n,calls}));}})();
  '''.replace('MODE',json.dumps(mode)).replace('SCRIPT',PAGER_JS)
  p=subprocess.run(['node','-e',harness],capture_output=True,text=True,check=True,timeout=10)
  return json.loads(p.stdout)
 def test_click_pages_exhaust(self):
  self.assertEqual(self.run_pager('click'),{'n':230,'calls':6,'complete':'true'})
 def test_scroll_can_load_before_click(self):
  self.assertEqual(self.run_pager('scroll'),{'n':230,'calls':6,'complete':'true'})
 def test_incomplete_calendar_cannot_be_stored(self):
  with self.assertRaises(ValueError):
   check_payload('https://www.moma.org/calendar/\n36 partial cards','MoMA')
  self.assertFalse(check_payload('https://www.moma.org/calendar/\nFOMO_MOMA_CALENDAR_COMPLETE 230','MoMA'))
  self.assertFalse(check_payload('https://www.moma.org/calendar/exhibitions\nExhibitions','MoMA'))
 def test_stalled_page_is_failure(self):
  self.assertIn('stalled',self.run_pager('stalled')['error'])

if __name__=='__main__':unittest.main()
