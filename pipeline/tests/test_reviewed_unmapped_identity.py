"""An explicit unmapped umbrella review must never become fuzzy alias authority."""
import io
import json
import os
import sys
import unittest
from contextlib import ExitStack, redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'pipeline'), str(ROOT/'pipeline/tests'), str(ROOT/'scripts')]
import reviewed_event_identity as identity
import test_duplicate_merge_occurrences as fixtures

URL = 'https://venue.test/nylx'
NAME = 'Nylx 2026'
DAYS = [('2026-10-09', '', None, ''), ('2026-10-10', '', None, ''), ('2026-10-11', '', None, '')]
SPAN = [('2026-10-09', '', '2026-10-11', '')]


def test_index(venue=None):
    index = identity.IdentityIndex()
    index.unmapped[(7, URL, 'nylx 2026', venue)] = {1: {frozenset(r[0] for r in DAYS)}}
    index.unmapped_schedules[1] = [identity._full_slot(r) for r in DAYS]
    return index


class UnmappedMatchTests(unittest.TestCase):
    def match(self, index=None, **overrides):
        args = dict(website_id=7, name=NAME, url=URL, location_id=None, occurrences=DAYS)
        args.update(overrides)
        return identity.match(test_index() if index is None else index, **args)

    def test_complete_edition_accepts_points_or_explicit_untimed_span(self):
        self.assertEqual(self.match(), 1)
        self.assertEqual(self.match(occurrences=SPAN), 1)
        self.assertEqual(self.match(occurrences=DAYS*2), 1)

    def test_source_publisher_name_url_and_venue_are_exact(self):
        for change in [dict(website_id=8), dict(name='New York Lindy Exchange'),
                       dict(url=URL+'?party=1'), dict(location_id=10)]:
            self.assertIsNone(self.match(**change))
        self.assertEqual(self.match(test_index(10), location_id=10), 1)
        self.assertIsNone(self.match(test_index(10), location_id=None))

    def test_partial_extra_clocked_and_new_edition_decline(self):
        for rows in [[], DAYS[:1], DAYS[:2], DAYS+[('2026-10-12','',None,'')],
                     [('2027-10-09','','2027-10-11','')],
                     [('2026-10-09','7:30pm','2026-10-11','')],
                     [('2026-10-09','','2026-10-11','12am')],
                     [('2026-10-09','TBA','2026-10-11','')],
                     [('2026-10-09','','2026-10-11','TBA')]]:
            self.assertIsNone(self.match(occurrences=rows), rows)

    def test_active_subset_needs_complete_original_source_evidence(self):
        self.assertEqual(self.match(occurrences=DAYS[1:], full_source_occurrences=DAYS), 1)
        self.assertEqual(self.match(occurrences=DAYS[2:], full_source_occurrences=DAYS), 1)
        self.assertIsNone(self.match(occurrences=DAYS[1:], full_source_occurrences=DAYS[1:]))
        self.assertIsNone(self.match(occurrences=DAYS[2:], full_source_occurrences=DAYS[2:]))

    def test_full_source_schedule_does_not_change_ordinary_redirect_coverage(self):
        plain = {(7,URL,'nylx 2026',10):{1:{identity.slot(DAYS[2])}}}
        self.assertEqual(identity.match(plain,7,NAME,URL,10,DAYS[2:],full_source_occurrences=DAYS),1)

    def test_nonreviewed_null_venue_does_not_gain_ordinary_redirect(self):
        plain = {(7,URL,'nylx 2026',None):{1:{identity.slot(r) for r in DAYS}}}
        self.assertIsNone(self.match(plain))

    def test_ambiguous_targets_decline_even_when_one_covers_schedule(self):
        index=test_index(); index.unmapped[(7,URL,'nylx 2026',None)][2]={frozenset(['2027-10-09'])}
        self.assertIsNone(self.match(index))

    def test_original_canonical_partition_is_returned_without_span_inflation(self):
        self.assertEqual(identity.unmapped_schedule(test_index(),1),
                         [(date.fromisoformat(d),'',None,'') for d,_,_,_ in DAYS])

    def test_unknown_or_excessive_date_ranges_decline(self):
        for rows in [[('wrong','','2026-10-11','')], [('2026-10-11','','2026-10-09','')],
                     [('2026-10-09','','2027-10-11','')], [(None,'',None,'')]]:
            self.assertIsNone(self.match(occurrences=rows))


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1', 'Connection-local MariaDB tables')
class UnmappedSQLTests(unittest.TestCase):
    def setUp(self):
        fixtures.DuplicateMergeOccurrenceTests.setUp(self)
        self.cur.execute('ALTER TABLE crawl_event_occurrences ADD COLUMN end_time VARCHAR(20)')
        self.cur.execute("UPDATE events SET name='Festival 2026',reviewed=1,website_id=7,location_id=NULL WHERE id=1")
        self.cur.execute("UPDATE events SET name='Nylx 2026',reviewed=1,suppressed=1,website_id=7,location_id=10 WHERE id=2")
        self.cur.execute('INSERT INTO crawl_results VALUES(99,7)')
        self.cur.execute('INSERT INTO crawl_events VALUES(202,%s,%s,NULL,99)',(NAME,URL))
        self.cur.execute('UPDATE event_sources SET event_id=1 WHERE crawl_event_id=202')
        for row in DAYS:
            self.cur.execute('INSERT INTO event_occurrences(event_id,start_date,start_time,end_date,end_time) VALUES(1,%s,%s,%s,%s)',row)
            self.cur.execute('INSERT INTO crawl_event_occurrences VALUES(202,%s,%s,%s,%s)',row)
        self.legacy = dict(website_id=7,url=URL,name='nylx 2026',location_id=10,
                           slots=[['2026-10-09','','2026-10-11']])
        self.cur.execute('INSERT INTO event_merge_redirects VALUES(2,1,%s,%s)',
                         ('Festival 2026',json.dumps([self.legacy])))

    def record(self, **extra):
        return identity.record_unmapped_aliases(self.cur,1,2,reviewed_source_ids=[202],
                                               review_reason='Explicit review: multi-venue 2026 edition.',**extra)

    def result(self, **overrides):
        args=dict(website_id=7,name=NAME,url=URL,location_id=None,occurrences=DAYS)
        args.update(overrides)
        return identity.match(identity.load_index(self.cur),**args)

    def test_default_legacy_rule_stays_inactive_without_new_explicit_review(self):
        self.assertIsNone(self.result())
        self.assertIsNone(self.result(location_id=10,occurrences=SPAN))

    def test_record_pins_review_provenance_and_preserves_ordinary_scope(self):
        scopes=self.record()
        self.assertEqual(len(scopes),1)
        self.assertEqual(scopes[0]['reviewed_source_ids'],[202])
        self.assertEqual(scopes[0]['reviewed_target_id'],1)
        self.assertEqual(self.result(),1)
        self.cur.execute('SELECT source_identities FROM event_merge_redirects')
        self.assertIn(self.legacy,json.loads(self.cur.fetchone()[0]))

    def test_prepolicy_slot_reader_can_safely_ignore_new_scopes(self):
        self.record(include_captured_venues=True)
        self.cur.execute('SELECT source_identities FROM event_merge_redirects')
        scopes=json.loads(self.cur.fetchone()[0])
        canonical={identity.slot(r) for r in DAYS}
        # The old loader knows only the exact-venue/slots contract. It must
        # neither raise on this additive format nor gain an unmapped redirect.
        allowed=[{tuple(s) for s in scope['slots']} & canonical
                 for scope in scopes if scope['location_id'] is None]
        self.assertTrue(allowed)
        self.assertFalse(any(allowed))

    def test_old_venue_requires_explicit_captured_venue_enrollment(self):
        self.record(); self.assertIsNone(self.result(location_id=10))
        self.record(include_captured_venues=True)
        self.assertEqual(self.result(location_id=10,occurrences=SPAN),1)
        self.assertIsNone(self.result(location_id=20))

    def test_listing_homepage_requires_exact_publisher_url_approval(self):
        home='https://festival.test/'
        self.cur.execute('UPDATE crawl_events SET url=%s WHERE id=202',(home,))
        self.cur.execute('INSERT INTO website_urls VALUES(7,%s)',(home,))
        with self.assertRaises(ValueError): self.record()
        with self.assertRaises(ValueError): self.record(allow_listing_urls=[(8,home)])
        self.record(allow_listing_urls=[(7,home)])
        self.assertEqual(self.result(url=home),1)
        self.assertIsNone(self.result(url=home+'?session=1'))

    def test_later_listing_classification_revokes_unapproved_detail_scope(self):
        self.record();self.cur.execute('INSERT INTO website_urls VALUES(7,%s)',(URL,))
        self.assertIsNone(self.result())

    def test_target_venue_review_name_schedule_or_status_change_disables(self):
        self.record()
        for sql in ["UPDATE events SET location_id=10 WHERE id=1", "UPDATE events SET reviewed=0 WHERE id=1",
                    "UPDATE events SET name='Renamed' WHERE id=1", "UPDATE events SET suppressed=1 WHERE id=1",
                    "UPDATE events SET archived=1 WHERE id=1", "UPDATE event_occurrences SET start_time='12am' WHERE event_id=1",
                    "UPDATE event_occurrences SET end_time='12am' WHERE event_id=1",
                    "UPDATE event_occurrences SET end_time='TBA' WHERE event_id=1",
                    "DELETE FROM event_occurrences WHERE event_id=1 AND start_date='2026-10-11'"]:
            self.cur.execute('SAVEPOINT scenario');self.cur.execute(sql)
            self.assertIsNone(self.result(),sql);self.cur.execute('ROLLBACK TO SAVEPOINT scenario')

    def test_source_provenance_change_or_removal_disables(self):
        self.record()
        for sql in ["UPDATE crawl_events SET name='Party' WHERE id=202", "UPDATE crawl_events SET location_id=10 WHERE id=202",
                    "UPDATE crawl_results SET website_id=8 WHERE id=99", "DELETE FROM event_sources WHERE crawl_event_id=202",
                    "UPDATE crawl_event_occurrences SET end_time='TBA' WHERE crawl_event_id=202"]:
            self.cur.execute('SAVEPOINT scenario');self.cur.execute(sql)
            self.assertIsNone(self.result(),sql);self.cur.execute('ROLLBACK TO SAVEPOINT scenario')

    def test_later_dismissal_or_duplicate_unhide_disables(self):
        self.record();self.cur.execute('SAVEPOINT scenario')
        self.cur.execute('INSERT INTO dedupe_dismissed_pairs VALUES(1,2)');self.assertIsNone(self.result())
        self.cur.execute('ROLLBACK TO SAVEPOINT scenario')
        self.cur.execute('UPDATE events SET suppressed=0 WHERE id=2');self.assertIsNone(self.result())

    def test_writer_rejects_unreviewed_or_incomplete_evidence_before_write(self):
        for sql in ["UPDATE events SET reviewed=0 WHERE id=1", "UPDATE events SET location_id=10 WHERE id=1",
                    "DELETE FROM event_sources WHERE crawl_event_id=202", "UPDATE crawl_events SET location_id=10 WHERE id=202",
                    "DELETE FROM crawl_event_occurrences WHERE crawl_event_id=202 AND start_date='2026-10-11'"]:
            self.cur.execute('SAVEPOINT scenario');self.cur.execute(sql)
            with self.assertRaises(ValueError):self.record()
            self.cur.execute('SELECT source_identities FROM event_merge_redirects')
            self.assertEqual(json.loads(self.cur.fetchone()[0]),[self.legacy])
            self.cur.execute('ROLLBACK TO SAVEPOINT scenario')

    def test_repeated_enrollment_is_idempotent(self):
        one=self.record(include_captured_venues=True);two=self.record(include_captured_venues=True)
        self.assertEqual(one,two)
        self.cur.execute('SELECT source_identities FROM event_merge_redirects')
        self.assertEqual(len(json.loads(self.cur.fetchone()[0])),3)


class UnmappedFullMergePathTests(unittest.TestCase):
    def run_merge(self, venue, occurrences, today=None, reject_reviewed_target=False):
        import merger
        cursor=MagicMock(lastrowid=999)
        today=today or date(2026,10,1)
        existing=[(1,'Festival 2026',None,None,None,'Multiple venues',7,0),
                  (2,NAME,10,None,None,'Venue',7,1),
                  (3,'NYLX: Friday Social Dance',10,None,None,'Venue',7,0)]
        def execute(query,params=None):
            rows=[];one=None
            if 'SELECT ce.id, ce.name' in query:
                rows=[(202,NAME,None,'Umbrella','💃','Venue','Studio',venue,URL,7,None,None,99)]
            elif 'FROM crawl_event_occurrences' in query:
                rows=[(202,date.fromisoformat(sd),st,date.fromisoformat(ed) if ed else None,et,i)
                      for i,(sd,st,ed,et) in enumerate(occurrences)]
            elif 'SELECT DISTINCT e.id, e.name' in query: rows=existing
            elif 'SELECT event_id, start_date, start_time, end_date FROM event_occurrences' in query:
                rows=[(1,date.fromisoformat(d),'',None) for d,_,_,_ in DAYS]
            elif 'SELECT location_id FROM events WHERE id' in query:
                one=(20 if params[0]==1 else venue,) if reject_reviewed_target else (None,)
            elif 'SELECT location_name, location_id FROM events' in query:
                one=('',venue) if reject_reviewed_target else ('',None)
            elif 'SELECT start_date, start_time, end_date, end_time' in query:
                rows=[(date.fromisoformat(d),'',None,'',i) for i,(d,_,_,_) in enumerate(DAYS)]
            cursor.fetchall.return_value=rows;cursor.fetchone.return_value=one
        cursor.execute.side_effect=execute
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(patch.object(merger,'EditLogger',None))
            stack.enter_context(patch.object(identity,'load_index',return_value=test_index(venue)))
            stack.enter_context(patch.object(merger,'get_active_date_window',return_value=(today,today+timedelta(days=90))))
            db=stack.enter_context(patch.object(merger,'db'))
            db.build_tag_ancestor_map.return_value=({},set());db.archive_dead_source_events.return_value=(0,[])
            fallback=stack.enter_context(patch.object(merger,'_match_by_url_identity',return_value=3))
            metadata=stack.enter_context(patch.object(merger,'refresh_source_metadata'))
            session=stack.enter_context(patch.object(merger,'refresh_source_session_details'))
            stack.enter_context(patch.object(merger,'_merge_grouped_event_urls'))
            self.assertEqual(merger.merge_crawl_events(cursor,MagicMock(),website_ids=[7]),(0,1))
            if reject_reviewed_target:
                fallback.assert_called_once();metadata.assert_called_once();session.assert_called_once()
                self.assertEqual(metadata.call_args.args[1],3)
                db.insert_event_occurrences.assert_called_once()
                self.assertEqual(db.insert_event_occurrences.call_args.args[1],3)
            else:
                fallback.assert_not_called();metadata.assert_not_called();session.assert_not_called()
                db.insert_event_occurrences.assert_not_called()
        statements=[(c.args[0],c.args[1] if len(c.args)>1 else None) for c in cursor.execute.call_args_list]
        self.assertEqual([args for sql,args in statements if 'INSERT IGNORE INTO event_sources' in sql],
                         [(3 if reject_reviewed_target else 1,202)])
        venue_writes=[sql for sql,args in statements if 'UPDATE events SET location' in sql]
        self.assertEqual(bool(venue_writes),reject_reviewed_target)
        self.assertFalse([sql for sql,args in statements if sql.lstrip().startswith(('DELETE FROM event_occurrences','INSERT INTO event_occurrences'))])

    def test_null_source_alias_wins_before_party_partial(self):self.run_merge(None,DAYS)
    def test_reviewed_old_venue_span_does_not_repin_or_inflate_target(self):self.run_merge(10,SPAN)
    def test_second_day_retains_complete_source_identity(self):self.run_merge(None,DAYS,date(2026,10,10))
    def test_last_day_retains_complete_source_identity(self):self.run_merge(None,DAYS,date(2026,10,11))
    def test_rejected_policy_cannot_protect_an_ordinary_url_fallback(self):
        self.run_merge(10,SPAN,reject_reviewed_target=True)
