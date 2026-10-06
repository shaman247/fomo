"""An explicit reviewed TBD session must not inherit its organizer's home pin."""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import venue_overrides as v

class UnknownVenueOverrideTests(unittest.TestCase):
    def setUp(self):
        self.rule=dict(id=99,website_id=2588,event_name='Contra Connections 3',
            source_url='https://example.test/reused',url_prefix=0,
            valid_from='2026-12-05',valid_until='2026-12-05',location_id=None,
            location_name='TBD',sublocation=None,lat=None,lng=None,emoji=None)

    def test_exact_source_session_returns_truthy_unknown_venue_rule(self):
        found=v.find_rule([self.rule],2588,'Contra Connections 3',
            ['https://example.test/reused'],[(date(2026,12,5),'2pm',None,'5pm')])
        self.assertTrue(found);self.assertIsNone(found['location_id'])
        self.assertIsNone(v.find_rule([self.rule],999,'Contra Connections 3',
            ['https://example.test/reused'],[(date(2026,12,5),'2pm',None,'5pm')]))
        self.assertIsNone(v.find_rule([self.rule],2588,'Another Workshop',
            ['https://example.test/reused'],[(date(2026,12,5),'2pm',None,'5pm')]))
        self.assertIsNone(v.find_rule([self.rule],2588,'Contra Connections 3',
            ['https://example.test/reused'],[(date(2026,10,4),'12pm',None,'3pm')]))

    def test_loader_keeps_null_location_and_never_requires_a_place_row(self):
        cursor=Mock();cursor.fetchall.return_value=[self.rule]
        self.assertEqual(v.load_rules(cursor),[self.rule])
        self.assertIn('LEFT JOIN locations',cursor.execute.call_args.args[0])

    def test_detail_enrichment_preserves_reviewed_unknown_venue(self):
        import processor
        cursor=Mock();statements=[]
        def execute(sql,params=None):
            statements.append((sql,params))
            if 'ce.location_name' in sql:
                cursor.fetchone.return_value=(1,2588,'TBD',None,172,'Contra Connections 3')
            elif sql.startswith('SELECT url'):
                cursor.fetchone.return_value=('https://example.test/reused',)
        cursor.execute.side_effect=execute
        cursor.fetchall.return_value=[('2026-12-05','2pm',None,'5pm')]
        processor.apply_crawled_details(cursor,Mock(),123,
            dict(name='Contra Connections 3',location='Organizer Home',location_id=172,hashtags=[],
                 occurrences=[dict(start_date='2026-12-05',start_time='2pm',end_time='5pm')]),
            ({},{},set(),[]),locations_map={'venue_overrides':[self.rule]})
        sql,params=next((sql,params) for sql,params in statements if sql.startswith('UPDATE crawl_events SET'))
        self.assertIn('location_id = %s',sql)
        fields=[f for f in sql.split(' SET ')[1].split(' WHERE ')[0].split(', ') if '%s' in f]
        assigned=dict(zip([f.split(' = ')[0] for f in fields],params))
        self.assertIsNone(assigned['location_id'])
        self.assertEqual(assigned['location_name'],'TBD')

if __name__=='__main__':unittest.main()
