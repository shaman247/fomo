import unittest
from datetime import date
import venue_overrides as v


class VenueOverrideTests(unittest.TestCase):
    def setUp(self):
        self.rule=dict(id=1,website_id=10,event_name='Wednesday Class',
                       source_url='https://example.org/event/wednesday-class-',url_prefix=1,
                       valid_from='2026-09-01',valid_until='2026-12-31',
                       location_id=42,location_name='Offsite Hall',sublocation='Room C')
        self.event=dict(name='Wednesday Class',urls=['https://example.org/event/wednesday-class-4/2026-09-23/'],
                        occurrences=[['2026-09-23','7pm','','8pm']])

    def test_corrected_source_identity_matches_with_case_and_spacing(self):
        self.event['name']='  WEDNESDAY  Class '
        self.assertEqual(v.for_event([self.rule],10,self.event),self.rule)

    def test_scope_and_title_are_required(self):
        self.assertIsNone(v.for_event([self.rule],11,self.event))
        self.event['name']='Thursday Class'
        self.assertIsNone(v.for_event([self.rule],10,self.event))

    def test_other_event_on_shared_listing_is_not_rewritten(self):
        rule=dict(self.rule,source_url='https://example.org/calendar',url_prefix=0)
        event=dict(self.event,name='Another Class',urls=[rule['source_url']])
        self.assertIsNone(v.for_event([rule],10,event))

    def test_later_season_and_mixed_seasons_do_not_inherit_pin(self):
        for slots in [[['2027-09-23','','','']],
                      [['2026-09-23','','',''],['2027-09-23','','','']],
                      [['2026-12-30','','2027-01-02','']]]:
            self.assertIsNone(v.for_event([self.rule],10,dict(self.event,occurrences=slots)))

    def test_dateless_or_invalid_schedule_is_not_enough(self):
        for slots in [[],[['not a date','','','']]]:
            self.assertIsNone(v.for_event([self.rule],10,dict(self.event,occurrences=slots)))

    def test_flat_extraction_and_merger_date_objects(self):
        event=dict(name=self.event['name'],url=self.event['urls'][0],start_date='2026-09-23')
        self.assertEqual(v.for_event([self.rule],10,event),self.rule)
        self.assertEqual(v.find_rule([self.rule],10,event['name'],[event['url']],
                                    [(date(2026,9,23),'7pm',None,'8pm',0)]),self.rule)

    def test_exact_url_rule_does_not_claim_siblings(self):
        rule=dict(self.rule,source_url=self.event['urls'][0],url_prefix=0)
        self.assertEqual(v.for_event([rule],10,self.event),rule)
        event=dict(self.event,urls=[self.event['urls'][0]+'other'])
        self.assertIsNone(v.for_event([rule],10,event))

    def test_lookalike_host_cannot_match_prefix(self):
        rule=dict(self.rule,source_url='https://example.org',url_prefix=1)
        event=dict(self.event,urls=['https://example.org.evil/event/wednesday-class'])
        self.assertIsNone(v.for_event([rule],10,event))

    def test_conflicting_reviewed_rules_fail_visibly(self):
        with self.assertRaisesRegex(ValueError,'Conflicting reviewed'):
            v.for_event([self.rule,dict(self.rule,location_id=43)],10,self.event)

    def test_disjoint_reviewed_dates_can_share_one_venue(self):
        rules=[dict(self.rule,valid_from=day,valid_until=day)
               for day in ('2026-09-23','2026-10-07')]
        event=dict(self.event,occurrences=[['2026-09-23'],['2026-10-07']])
        self.assertEqual(v.for_event(rules,10,event)['location_id'],42)
        event['occurrences'].append(['2026-10-14'])
        self.assertIsNone(v.for_event(rules,10,event))

    def test_dates_at_different_venues_require_separate_events(self):
        rules=[dict(self.rule,valid_from='2026-09-23',valid_until='2026-09-23'),
               dict(self.rule,valid_from='2026-10-07',valid_until='2026-10-07',location_id=43)]
        event=dict(self.event,occurrences=[['2026-09-23'],['2026-10-07']])
        self.assertIsNone(v.for_event(rules,10,event))

    def test_processor_groups_reviewed_dates_by_venue(self):
        import json
        import processor
        rules=[dict(self.rule,valid_from='2026-09-23',valid_until='2026-09-23'),
               dict(self.rule,valid_from='2026-10-07',valid_until='2026-10-07',location_id=43)]
        rows=processor._parse_json_events(json.dumps({'events':[dict(
            name=self.event['name'],url=self.event['urls'][0],
            occurrences=[dict(start_date='2026-09-23'),dict(start_date='2026-10-07')])]}))
        for row in rows:
            rule=v.for_event(rules,10,row)
            row.update(location_id=rule['location_id'],location=rule['location_name'])
        grouped=processor.group_event_occurrences(rows)
        self.assertEqual({e['location_id'] for e in grouped},{42,43})
        self.assertTrue(all(len(e['occurrences'])==1 for e in grouped))

    def test_shared_detail_preserves_reviewed_source_venue_and_dates(self):
        import processor
        from unittest.mock import Mock
        rule=dict(self.rule,emoji='X')
        statements=[]
        cursor=Mock()
        def execute(sql,params=None):
            statements.append((sql,params))
            if 'ce.location_name' in sql:
                cursor.fetchone.return_value=(1,10,'Offsite Hall','Room C',42,'Wednesday Class')
            elif sql.startswith('SELECT url'):
                cursor.fetchone.return_value=(self.event['urls'][0],)
        cursor.execute.side_effect=execute
        cursor.fetchall.return_value=[('2026-09-23','7pm',None,'8pm')]
        data=dict(name='Wednesday Class',hashtags=[],
                  occurrences=[dict(start_date='2026-09-23'),dict(start_date='2027-01-06')])
        processor.apply_crawled_details(cursor,Mock(),123,data,({}, {}, set(), []),
                                        locations_map={'venue_overrides':[rule]})
        update=next((sql,params) for sql,params in statements if sql.startswith('UPDATE crawl_events SET'))
        self.assertIn('location_id = %s',update[0])
        self.assertIn(42,update[1])
        self.assertFalse(any('DELETE FROM crawl_event_occurrences' in sql for sql,_ in statements))
        self.assertEqual(len(data['occurrences']),2, 'caller data must remain intact')


if __name__=='__main__':unittest.main()
