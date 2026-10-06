"""Bounded positive source reviews survive renames without broad URL matching."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import reviewed_event_identity as identity
import reviewed_source_aliases as aliases

class SourceAliasTests(unittest.TestCase):
    def setUp(self):
        self.index=identity.IdentityIndex()
        self.url='https://registration.test/course/123'
        self.key=(7,self.url,'intro to practice',10)
        self.slots={aliases.full_slot(('2026-10-03','3pm',None,'4pm')),
                    aliases.full_slot(('2026-10-10','3pm',None,'4pm'))}
        self.index.source_aliases={self.key:{100:[self.slots]}}
        self.index.protected_source_keys={(7,self.url,'intro to practice')}
        self.occ=[('2026-10-03','15:00',None,'16:00')]
    def match(self,**kw):
        args=dict(website_id=7,name='Intro to Practice',url=self.url,location_id=10,occurrences=self.occ)
        args.update(kw);return identity.match(self.index,**args)
    def test_exact_source_ownership_accepts_shortened_source_title(self):
        self.assertEqual(self.match(),100)
    def test_preserves_registration_branch_clock_end_and_delivery_name(self):
        for change in [dict(url=self.url+'?registration=other'),dict(location_id=11),dict(location_id=None),
                       dict(name='Intro to Practice — Online'),dict(website_id=8),
                       dict(occurrences=[('2026-10-03','3pm',None,'5pm')]),
                       dict(occurrences=[('2026-10-03','4pm',None,'5pm')])]:
            self.assertIsNone(self.match(**change))
    def test_full_source_partition_not_active_projection_is_checked(self):
        self.assertIsNone(self.match(full_source_occurrences=self.occ+[('2026-09-26','3pm',None,'4pm')]))
    def test_separately_reviewed_partitions_cannot_authorize_union(self):
        self.index.source_aliases[self.key][100]=[{slot} for slot in self.slots]
        self.assertIsNone(self.match(occurrences=[('2026-10-03','3pm',None,'4pm'),('2026-10-10','3pm',None,'4pm')]))
    def test_ambiguous_alias_and_redirect_targets_decline(self):
        self.index[self.key]={101:{('2026-10-03','3pm','2026-10-03')}}
        self.assertIsNone(self.match())
    def test_known_alias_scope_change_needs_review_and_unknown_source_does_not(self):
        self.assertTrue(aliases.needs_review(self.index,7,'Intro to Practice',self.url,None))
        self.assertFalse(aliases.needs_review(self.index,7,'Intro to Practice',self.url,100))
        self.assertFalse(aliases.needs_review(self.index,7,'Other program',self.url,None))

if __name__=='__main__':unittest.main()

class SourceAliasLoadingTests(unittest.TestCase):
    def setUp(self):
        import json
        from unittest.mock import MagicMock
        self.cursor=MagicMock()
        self.scope=dict(website_id=7,url='https://r.test/123',source_name='course',names=['course'],
                        location_id=10,target_name='course — teacher',suppressed=True,
                        slots=[['2026-10-03','3pm','2026-10-03','4pm']])
        self.rule=dict(event_id=100,crawl_event_id=200,identity=json.dumps(self.scope),
                       target_name='Course — Teacher',target_location=10,suppressed=1,archived=0,
                       source_name='Course',source_location=10,url=self.scope['url'],website_id=7,owner_id=100)
        self.slots=[dict(start_date='2026-10-03',start_time='3pm',end_date=None,end_time='4pm')]
    def load(self,**changes):
        row={**self.rule,**changes}
        with patch.object(aliases,'_rows',side_effect=[[row],self.slots,self.slots]),patch.object(aliases,'_dismissed_owner',return_value=False):
            return aliases.load_into(self.cursor,identity.IdentityIndex())
    def test_reviewed_suppression_is_preserved_as_intended_owner(self):
        ix=self.load()
        self.assertEqual(identity.match(ix,7,'Course',self.scope['url'],10,[('2026-10-03','3pm',None,'4pm')]),100)
    def test_changed_target_source_venue_suppression_or_ownership_quarantines(self):
        for change in [dict(target_location=11),dict(source_location=11),dict(suppressed=0),dict(archived=1),
                       dict(source_name='Course Online'),dict(target_name='Another course'),dict(owner_id=None)]:
            ix=self.load(**change)
            self.assertFalse(ix.source_aliases)
            self.assertTrue(aliases.needs_review(ix,7,'Course',self.scope['url'],None))

    def test_explicit_online_null_owner_loads_but_unknown_or_physical_target_does_not(self):
        import json
        self.scope.update(location_id=None,delivery='online')
        self.rule.update(identity=json.dumps(self.scope),target_location=None,source_location=None,
                         source_location_name='Online',target_location_name='Online')
        ix=self.load()
        self.assertEqual(identity.match(ix,7,'Course',self.scope['url'],None,
                                       [('2026-10-03','3pm',None,'4pm')]),100)
        for change in (dict(target_location_name='TBA'),dict(source_location_name='TBA'),
                       dict(target_location=10),dict(source_location=10),
                       dict(target_location_name='Online and In Person')):
            self.assertFalse(self.load(**change).source_aliases)

class SourceAliasOnlineRecordingTests(unittest.TestCase):
    def test_record_requires_both_explicit_online_and_no_physical_pin(self):
        from unittest.mock import MagicMock
        cursor=MagicMock()
        target=dict(id=100,name='Dance films',location_id=None,location_name='Online',suppressed=0,archived=0)
        source=dict(id=200,name='Dance films',url='https://r.test/films',location_id=None,
                    location_name='Online',website_id=7)
        slots=[dict(start_date='2026-10-05',start_time='',end_date='2026-10-25',end_time='')]
        def record(t,s):
            with patch.object(aliases,'_rows',side_effect=[[t],[s],[],slots,slots]), \
                 patch.object(aliases,'_dismissed_owner',return_value=False):
                return aliases.record(cursor,100,200,review_reason='Reviewed exact online program')
        payload=record(target,source)
        self.assertIsNone(payload['location_id']);self.assertEqual(payload['delivery'],'online')
        for t,s in ((dict(target,location_name='TBA'),source),
                    (target,dict(source,location_name='TBA')),
                    (dict(target,location_id=10),source),
                    (target,dict(source,location_id=10)),
                    (target,dict(source,location_name='In Person'))):
            with self.assertRaises(ValueError):record(t,s)

class SourceAliasMergePathTests(unittest.TestCase):
    def run_scenario(self, *, quarantined):
        from contextlib import ExitStack,redirect_stdout
        from datetime import date,timedelta
        from unittest.mock import MagicMock
        import io,merger
        today=date(2026,10,3);url='https://r.test/course/123'
        index=identity.IdentityIndex();index.source_aliases={};index.protected_source_keys={(7,url,'course')} if quarantined else set()
        cursor=MagicMock(lastrowid=999)
        def execute(query,params=None):
            rows=[]
            if 'SELECT ce.id, ce.name' in query:
                rows=[(202,'Course',None,'A course.','🎨','Library',None,10,url,7,None,None,99)]
            elif 'FROM crawl_event_occurrences' in query:
                rows=[(202,today if quarantined else today-timedelta(days=30),'3pm',None,'4pm',0)]
            elif 'SELECT DISTINCT cr.website_id' in query:rows=[(7,)]
            cursor.fetchall.return_value=rows;cursor.fetchone.return_value=None
        cursor.execute.side_effect=execute
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(patch.object(merger,'EditLogger',None))
            stack.enter_context(patch.object(identity,'load_index',return_value=index))
            stack.enter_context(patch.object(aliases,'load_into',return_value=index))
            stack.enter_context(patch.object(merger,'get_active_date_window',return_value=(today,today+timedelta(days=90))))
            db=stack.enter_context(patch.object(merger,'db'))
            db.build_tag_ancestor_map.return_value=({},set());db.archive_dead_source_events.return_value=(0,[])
            db.archive_outdated_events.return_value=(0,[])
            fallback=stack.enter_context(patch.object(merger,'_match_by_url_identity'))
            for _ in range(2):self.assertEqual(merger.merge_crawl_events(cursor,MagicMock(),website_ids=[7]),(0,0))
            fallback.assert_not_called()
            if quarantined:db.archive_outdated_events.assert_not_called()
        self.assertFalse(any('INSERT IGNORE INTO event_sources' in c.args[0] for c in cursor.execute.call_args_list))
        stamps=[c for c in cursor.execute.call_args_list if 'UPDATE crawl_results SET merged_at' in c.args[0]]
        self.assertEqual(len(stamps),2)
        for stamp in stamps:
            if quarantined:
                self.assertIn('AND id NOT IN (%s)',stamp.args[0])
                self.assertEqual(stamp.args[1],[202,99])
            else:
                self.assertNotIn('AND id NOT IN',stamp.args[0])
                self.assertEqual(stamp.args[1],[202])

    def test_changed_reviewed_identity_is_stable_and_holds_archival(self):
        self.run_scenario(quarantined=True)

    def test_ordinary_past_source_does_not_block_merge_timestamp(self):
        self.run_scenario(quarantined=False)

class SourceDeliveryTests(unittest.TestCase):
    def test_explicit_labels_not_organizer_pin_or_subject_define_delivery(self):
        self.assertEqual(aliases.delivery_mode('Online via Zoom'),'online')
        self.assertEqual(aliases.delivery_mode('In-person, Center'),'in_person')
        self.assertEqual(aliases.delivery_mode('Online & In-Person'),'hybrid')
        self.assertEqual(aliases.delivery_mode('Center','Course | In person - Topic'),'in_person')
        self.assertIsNone(aliases.delivery_mode('Center','Online Safety Course'))
    def test_opposing_raw_delivery_vetoes_same_name_url_slots_and_pin(self):
        ix=identity.IdentityIndex();key=(7,'https://r.test/123','course',10)
        ix.source_delivery={(key,100):{'online'}}
        self.assertTrue(aliases.delivery_conflicts(ix,7,'Course',key[1],10,100,'In Person'))
        self.assertTrue(aliases.delivery_conflicts(ix,7,'Course',key[1],10,100,'Online and in person'))
        self.assertFalse(aliases.delivery_conflicts(ix,7,'Course',key[1],10,100,'Online via Zoom'))
        self.assertFalse(aliases.delivery_conflicts(ix,7,'Course',key[1],10,100,'Organizer Center'))
