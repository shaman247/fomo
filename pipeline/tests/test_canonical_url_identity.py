"""Public URL repair cannot erase history or leak across dates/events."""
import hashlib
import json
import sqlite3
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from canonical_url_identity import canonical_url_allowed, record_url_exclusion, load_url_exclusions, _snapshot

OLD='https://venue.test/reused'
NEW='https://venue.test/october'


class Cursor:
    def __init__(self,conn):self.cur=conn.cursor()
    def execute(self,sql,args=()):return self.cur.execute(sql.replace('%s','?'),args)
    def fetchone(self):return self.cur.fetchone()
    def fetchall(self):return self.cur.fetchall()


class CanonicalURLIdentityTests(unittest.TestCase):
    def setUp(self):
        self.conn=sqlite3.connect(':memory:');self.addCleanup(self.conn.close)
        self.conn.executescript('''
          CREATE TABLE events(id INTEGER PRIMARY KEY,name TEXT,location_id INT,archived INT,suppressed INT);
          INSERT INTO events VALUES (1,'Contra Connections 2',3629,0,0),(2,'Contra Connections 3',NULL,0,0);
          CREATE TABLE event_occurrences(event_id INT,start_date TEXT,start_time TEXT,end_date TEXT,end_time TEXT);
          INSERT INTO event_occurrences VALUES(1,'2026-10-04','12:00',NULL,'15:00');
          CREATE TABLE event_urls(event_id INT,url TEXT);
          CREATE TABLE event_url_exclusions(event_id INT,url_hash TEXT,url TEXT,replacement_url TEXT,event_snapshot TEXT);
          CREATE TABLE crawl_events(id INT,url TEXT,raw_data TEXT);
        ''')
        self.conn.execute('INSERT INTO event_urls VALUES(1,?)',(NEW,))
        self.conn.execute('INSERT INTO crawl_events VALUES(42,?,?)',(OLD,json.dumps({'url':OLD})))
        self.cur=Cursor(self.conn)
        self.conn.execute('INSERT INTO event_url_exclusions VALUES(?,?,?,?,?)',
            (1,hashlib.sha256(OLD.encode()).hexdigest(),OLD,NEW,json.dumps(_snapshot(self.cur,1))))

    def test_exact_review_blocks_only_public_link_and_preserves_history(self):
        before=list(self.conn.execute('SELECT * FROM crawl_events'))
        self.assertFalse(canonical_url_allowed(self.cur,1,OLD))
        self.assertEqual(before,list(self.conn.execute('SELECT * FROM crawl_events')))
        self.assertTrue(canonical_url_allowed(self.cur,1,NEW))
        self.assertTrue(canonical_url_allowed(self.cur,2,OLD))
        self.assertTrue(canonical_url_allowed(self.cur,1,OLD.upper()))

    def test_changed_name_venue_or_suppression_invalidates_review(self):
        for field,value in [('name','Changed'),('location_id',99),('archived',1),('suppressed',1)]:
            with self.subTest(field=field):
                self.conn.execute('SAVEPOINT item')
                self.conn.execute(f'UPDATE events SET {field}=? WHERE id=1',(value,))
                self.assertTrue(canonical_url_allowed(self.cur,1,OLD))
                self.conn.execute('ROLLBACK TO item')

    def test_added_or_changed_session_invalidates_review(self):
        self.conn.execute("UPDATE event_occurrences SET start_date='2026-12-05'")
        self.assertTrue(canonical_url_allowed(self.cur,1,OLD))

    def test_missing_replacement_does_not_leave_event_linkless(self):
        self.conn.execute('DELETE FROM event_urls')
        self.assertTrue(canonical_url_allowed(self.cur,1,OLD))

    def test_replacement_comparison_is_exact(self):
        self.conn.execute('UPDATE event_urls SET url=?',(NEW.upper(),))
        self.assertTrue(canonical_url_allowed(self.cur,1,OLD))

    def test_loaded_index_skips_queries_for_unaffected_urls(self):
        from unittest.mock import Mock
        index=load_url_exclusions(self.cur)
        untouched=Mock()
        self.assertTrue(canonical_url_allowed(untouched,1,NEW,index=index))
        untouched.execute.assert_not_called()
        self.assertFalse(canonical_url_allowed(self.cur,1,OLD,index=index))
        self.conn.execute("UPDATE events SET name='Renamed' WHERE id=1")
        self.assertTrue(canonical_url_allowed(self.cur,1,OLD,index=index))

    def test_recording_requires_evidence_and_existing_replacement(self):
        with self.assertRaises(ValueError):record_url_exclusion(self.cur,1,OLD,NEW,'')
        with self.assertRaises(ValueError):record_url_exclusion(self.cur,1,OLD,OLD,'review')
        with self.assertRaises(ValueError):record_url_exclusion(self.cur,1,OLD,'https://missing.test','review')


if __name__=='__main__':unittest.main()
