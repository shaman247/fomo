import sys,json,sqlite3,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from processor import group_event_occurrences
from session_details import refresh_source_session_details
class DetailsTests(unittest.TestCase):
 def row(self,day='2026-10-01',room='Heron Room',desc='Practice tai chi.',url='1'):
  return dict(name='Tai Chi',location='Library',location_id=1,sublocation=room,description=desc,start_date=day,start_time='10am',end_time='11am',url='https://example.org/event/'+url)
 def test_rooms_remain_tied_to_their_own_dates(self):
  e,=group_event_occurrences([self.row(),self.row('2026-10-14','Leroy Room',url='2')])
  self.assertIn('2026-10-01 10am–11am — Heron Room',e['description']);self.assertIn('2026-10-14 10am–11am — Leroy Room',e['description'])
  self.assertEqual(len(e['occurrences']),2);self.assertIn('Varies',e['sublocation'])
 def test_same_time_roles_keep_both_eligibility_descriptions_and_links(self):
  e,=group_event_occurrences([self.row(desc='Grades K–2: make slime.'),self.row(desc='Teen volunteers earn service credit.',url='2')])
  self.assertIn('Grades K–2',e['description']);self.assertIn('Teen volunteers',e['description']);self.assertEqual(len(e['urls']),2)
 def test_later_restriction_and_monthly_topic_survive(self):
  e,=group_event_occurrences([self.row(desc='Book discussion: Title A.'),self.row('2026-12-12',desc='Title B. Not open to patrons registered for Baby & Me.',url='2')])
  self.assertIn('Title A',e['description']);self.assertIn('2026-12-12',e['description']);self.assertIn('Not open',e['description'])
 def test_identical_program_keeps_simple_description(self):
  e,=group_event_occurrences([self.row(),self.row('2026-10-02',url='2')]);self.assertEqual(e['description'],'Practice tai chi.');self.assertNotIn('session_details',e)
 def test_unknown_room_does_not_assign_another_dates_room(self):
  e,=group_event_occurrences([self.row(room=''),self.row('2026-10-02',room='Outside Gregorys Coffee',url='2')]);self.assertIn('Varies',e['sublocation']);self.assertIn('Outside Gregorys Coffee',e['description'])
class Cursor:
 def __init__(self,c):self.c=c.cursor()
 def execute(self,q,p=()):return self.c.execute(q.replace('%s','?'),p)
 def fetchone(self):return self.c.fetchone()
class RefreshTests(unittest.TestCase):
 def test_source_provenance_refreshes_but_manual_and_other_publisher_are_preserved(self):
  db=sqlite3.connect(':memory:');self.addCleanup(db.close);c=Cursor(db)
  for sql in ['CREATE TABLE events(id INT,description TEXT,sublocation TEXT)','CREATE TABLE crawl_results(id INT,website_id INT)','CREATE TABLE crawl_events(id INT,crawl_result_id INT,description TEXT)','CREATE TABLE event_sources(event_id INT,crawl_event_id INT)']:c.execute(sql)
  c.execute("INSERT INTO events VALUES(1,'Old source text','Room A'),(2,'Manual edit','Room A'),(3,'Other source text','Room A')")
  c.execute('INSERT INTO crawl_results VALUES(1,10),(2,10),(3,20)');c.execute("INSERT INTO crawl_events VALUES(1,1,'Old source text'),(2,2,'New details'),(3,3,'Other source text')")
  c.execute('INSERT INTO event_sources VALUES(1,1),(2,1),(3,3)')
  raw=json.dumps(dict(session_details=[{},{}],description='New details',sublocation='Varies by session; see description'))
  self.assertTrue(refresh_source_session_details(c,1,2,raw));self.assertFalse(refresh_source_session_details(c,2,2,raw));self.assertFalse(refresh_source_session_details(c,3,2,raw))
  c.execute('SELECT description FROM events WHERE id=2');self.assertEqual(c.fetchone()[0],'Manual edit')
 def test_unmarked_or_invalid_raw_data_cannot_trigger_update(self):
  from unittest.mock import Mock
  c=Mock()
  for raw in ['bad','null','{}',json.dumps({'session_details':[],'description':'text'})]:self.assertFalse(refresh_source_session_details(c,1,2,raw))
  c.execute.assert_not_called()
