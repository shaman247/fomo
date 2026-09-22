import os,sys,unittest
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from schedule_envelopes import redundant_envelopes
from merger import _merge_occurrences_into_event
from db import create_connection
D=date(2026,10,1);E=date(2026,10,2)
SPAN=(D,'',E,'');SESSIONS=[(D,'1pm',None,'4pm'),(E,'1pm',None,'4pm')]
EVENT=dict(event_type='Talk',location_id=10715)
def source(id,website,rows):
    return dict(id=id,website_id=website,source_type='primary',location_id=10715,occurrences=rows)
class EnvelopePlanTests(unittest.TestCase):
    def plan(self,rows=None,sources=None,event=None):
        return redundant_envelopes(event or EVENT,rows if rows is not None else [SPAN]+SESSIONS,
            sources if sources is not None else [source(1,4766,[SPAN]),source(2,1507,SESSIONS)])
    def test_independent_publisher_complete_sessions_supersede_range(self):
        self.assertEqual(self.plan(),{SPAN})
    def test_incomplete_days_are_not_filled_from_cadence(self):
        self.assertFalse(self.plan(sources=[source(1,4766,[SPAN]),source(2,1507,SESSIONS[:1])]))
    def test_completeness_cannot_be_assembled_across_crawls(self):
        self.assertFalse(self.plan(sources=[source(1,4766,[SPAN]),source(2,1507,SESSIONS[:1]),source(3,1507,SESSIONS[1:])]))
    def test_same_publisher_range_is_not_reinterpreted(self):
        self.assertFalse(self.plan(sources=[source(1,1507,[SPAN]),source(2,1507,SESSIONS)]))
    def test_no_range_provenance_no_automatic_removal(self):
        self.assertFalse(self.plan(sources=[source(2,1507,SESSIONS)]))
    def test_exhibitions_festivals_camps_and_unknown_types_keep_ranges(self):
        for typ in ['Exhibition','Festival','Camp','Immersive Experience',None]:
            with self.subTest(typ=typ):self.assertFalse(self.plan(event=dict(EVENT,event_type=typ)))
    def test_wrong_or_unknown_venues_veto(self):
        for loc in [None,999]:
            ss=[source(1,4766,[SPAN]),source(2,1507,SESSIONS)];ss[0]['location_id']=loc
            self.assertFalse(self.plan(sources=ss))
    def test_aggregator_only_schedule_cannot_override(self):
        ss=[source(1,4766,[SPAN]),source(2,1507,SESSIONS)];ss[1]['source_type']='aggregator'
        self.assertFalse(self.plan(sources=ss))
    def test_conflicting_source_or_canonical_clocks_veto(self):
        conflict=(D,'2pm',None,'4pm')
        self.assertFalse(self.plan(rows=[SPAN]+SESSIONS+[conflict]))
        self.assertFalse(self.plan(sources=[source(1,4766,[SPAN]),source(2,1507,SESSIONS),source(3,22,[conflict])]))
    def test_missing_end_time_and_overnight_are_not_complete_daily_sessions(self):
        for row in [(D,'1pm',None,''),(D,'11pm',E,'1am'),(D,'1',None,'4pm')]:
            self.assertFalse(self.plan(sources=[source(1,4766,[SPAN]),source(2,1507,[row,SESSIONS[1]])]))
    def test_different_span_and_timed_span_are_preserved(self):
        for row in [(D,'',date(2026,10,3),''),(D,'1pm',E,'4pm')]:
            self.assertFalse(self.plan(rows=[SPAN]+SESSIONS+[row]))
    def test_clock_formats_and_same_day_end_dates_are_equivalent(self):
        sessions=[(D,'13:00',D,'16:00'),(E,'13:00',E,'16:00')]
        self.assertEqual(self.plan(rows=[SPAN]+sessions,sources=[source(1,1,[SPAN]),source(2,2,sessions)]),{SPAN})
    def test_preserves_unrelated_occurrences(self):
        self.assertEqual(self.plan(rows=[SPAN]+SESSIONS+[(date(2026,10,8),'5pm',None,'6pm')]),{SPAN})

@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB')=='1','Opt in to connection-local MariaDB tables')
class EnvelopeWriteTests(unittest.TestCase):
    def setUp(self):
        self.conn=create_connection();self.assertIsNotNone(self.conn);self.addCleanup(self.conn.close);self.q=self.conn.cursor()
        schemas={'events':'id INT,event_type VARCHAR(40),location_id INT',
          'event_occurrences':'id INT AUTO_INCREMENT PRIMARY KEY,event_id INT,start_date DATE,start_time VARCHAR(20),end_date DATE,end_time VARCHAR(20),sort_order INT DEFAULT 0',
          'crawl_events':'id INT,crawl_result_id INT,location_id INT',
          'crawl_results':'id INT,website_id INT','event_sources':'event_id INT,crawl_event_id INT',
          'crawl_event_occurrences':'crawl_event_id INT,start_date DATE,start_time VARCHAR(20),end_date DATE,end_time VARCHAR(20)'}
        for name,schema in schemas.items():self.q.execute(f'CREATE TEMPORARY TABLE {name} ({schema})')
        # Constant-only fixture: this shadows websites on this connection and
        # does not add a real website or invoke production helper side effects.
        self.q.execute("CREATE TEMPORARY TABLE websites AS SELECT 4766 AS id, 'primary' AS source_type UNION ALL SELECT 1507, 'primary'")
        self.q.execute("INSERT INTO events VALUES(1,'Talk',10715)")
        self.q.execute('INSERT INTO crawl_results VALUES(1,4766),(2,1507)')
        self.q.execute('INSERT INTO crawl_events VALUES(1,1,10715),(2,2,10715)')
        self.q.execute('INSERT INTO event_sources VALUES(1,1),(1,2)')
        for id,rows in [(1,[SPAN]),(2,SESSIONS)]:
            for o in rows:self.q.execute('INSERT INTO crawl_event_occurrences VALUES(%s,%s,%s,%s,%s)',(id,*o))
    def rows(self):
        self.q.execute('SELECT start_date,start_time,end_date,end_time FROM event_occurrences ORDER BY start_date,start_time');return self.q.fetchall()
    def seed(self,rows):
        for o in rows:self.q.execute('INSERT INTO event_occurrences(event_id,start_date,start_time,end_date,end_time) VALUES(1,%s,%s,%s,%s)',o)
    def test_organizer_arrives_after_range(self):
        self.seed([SPAN]);_merge_occurrences_into_event(self.q,1,SESSIONS,crawl_event_id=2);self.assertEqual(self.rows(),SESSIONS)
        self.q.execute('SELECT COUNT(*) FROM crawl_event_occurrences');self.assertEqual(self.q.fetchone()[0],3)
    def test_range_arrives_later_and_repeatedly(self):
        self.seed(SESSIONS)
        for _ in range(2):_merge_occurrences_into_event(self.q,1,[SPAN],crawl_event_id=1)
        self.assertEqual(self.rows(),SESSIONS)
    def test_source_link_alone_does_not_remove_only_date_information(self):
        self.seed([SPAN]);_merge_occurrences_into_event(self.q,1,[],crawl_event_id=2);self.assertEqual(self.rows(),[SPAN])
    def test_partial_incoming_and_conflicting_source_keep_range(self):
        self.seed([SPAN]);_merge_occurrences_into_event(self.q,1,SESSIONS[:1],crawl_event_id=2)
        self.assertIn(SPAN,self.rows())
        self.q.execute("UPDATE crawl_event_occurrences SET end_time='5pm' WHERE crawl_event_id=1")
        _merge_occurrences_into_event(self.q,1,SESSIONS,crawl_event_id=2);self.assertIn(SPAN,self.rows())
if __name__=='__main__':unittest.main()
