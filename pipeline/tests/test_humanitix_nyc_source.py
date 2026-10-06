import copy,unittest
try:
 from sources import humanitix_nyc as source
except ImportError:
 source=None

@unittest.skipIf(source is None,'Deployment source not installed')
class HumanitixSourceTests(unittest.TestCase):
 def row(self,identity='one'):
  return {'_id':identity,'hostname':'https://events.humanitix.com/','name':'Own show','slug':'own-show-'+identity,'timezone':'America/New_York','occurrenceLabel':'+1 more time','dates':[{'startDate':'Thu Oct 01 2026 23:00:00 GMT+0000 (Coordinated Universal Time)','endDate':'Fri Oct 02 2026 01:00:00 GMT+0000 (Coordinated Universal Time)'},{'startDate':'Sun Nov 01 2026 23:00:00 GMT+0000 (Coordinated Universal Time)','endDate':None}],'eventLocation':{'type':'toBeAnnounced'},'pricing':{'minimumPrice':0}}
 def test_all_dates_timezone_and_unknown_end(self):
  text=source.format_record(self.row());self.assertIn('2026-10-01T19:00:00-04:00 to 2026-10-01T21:00:00-04:00',text);self.assertIn('2026-11-01T18:00:00-05:00; end not stated',text);self.assertIn('toBeAnnounced',text)
 def test_stable_state_and_terminal_after_full_pages(self):
  calls=[]
  def post(payload):
   calls.append(payload);return [self.row(str(payload['page']))] if payload['page']<10 else []
  rows=source.collect_search(post,{},state_key='same');self.assertEqual(len(rows),10);self.assertEqual({c['stateKey'] for c in calls},{'same'});self.assertEqual([c['page'] for c in calls],list(range(11)))
 def test_duplicate_or_collapsed_schedule_fails_closed(self):
  with self.assertRaises(ValueError):source.collect_search(lambda p:[self.row()],{})
  row=self.row();row['dates'].pop()
  with self.assertRaises(ValueError):source.format_record(row)
  self.assertFalse(source.PROFILE.matches('https://humanitix.com/us/events/us--ny--new-york-other'))
 def test_ambiguous_envelope_foreign_clock_and_year_require_own_detail(self):
  row=self.row();self.assertFalse(source.needs_own_detail(row))
  row['dates'][0]['endDate']='Fri Nov 06 2026 01:00:00 GMT+0000 (Coordinated Universal Time)'
  self.assertTrue(source.needs_own_detail(row))
  row=self.row();row['eventLocation']={'type':'address','address':'New York'};row['timezone']='Australia/Perth'
  self.assertTrue(source.needs_own_detail(row))
  row['eventLocation']={'type':'online'};self.assertFalse(source.needs_own_detail(row))
  row=self.row();row['name']='Messiah2027' # only explicit bounded year tokens count
  self.assertFalse(source.needs_own_detail(row));row['name']='Messiah 2027';self.assertTrue(source.needs_own_detail(row))
 def test_own_detail_preserves_exclusions_and_rejects_missing_body(self):
  html='<h1>Own event</h1><h2>About this event</h2><p>'+('NO CLASS Nov 5; Tuesday rehearsal 4pm. '*8)+'</p><footer>Foreign footer event</footer><script>bad</script>'
  text=source.own_detail_text(html);self.assertIn('NO CLASS Nov 5',text);self.assertNotIn('Foreign footer',text);self.assertNotIn('bad',text)
  with self.assertRaises(ValueError):source.own_detail_text('<h1>Sorry</h1>')
 def test_reviewed_detail_routes_do_not_fall_under_normal_detail_cap(self):
  for slug in source.DETAIL_REQUIRED_SLUGS | source.TICKET_DETAIL_SLUGS:
   row=self.row();row['slug']=slug;self.assertTrue(source.needs_own_detail(row))
