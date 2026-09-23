"""Reviewed duplicate redirects must not become general URL identity rules."""
import json
import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'pipeline'),str(ROOT/'scripts')]
import reviewed_event_identity as identity
from find_duplicate_events import classify_pairs, merge_pair
import test_duplicate_merge_occurrences as fixtures


class ReviewedIdentityTests(unittest.TestCase):
    URL='https://library.test/event/123'
    OCC=[('2026-10-03','3pm',None,'4pm')]
    def match(self,index=None,**overrides):
        args=dict(website_id=7,name='Adult Craft',url=self.URL,location_id=10,occurrences=self.OCC)
        args.update(overrides)
        index=index if index is not None else {(7,self.URL,'adult craft',10):{100:{('2026-10-03','3pm','2026-10-03')}}}
        return identity.match(index,**args)
    def test_exact_reviewed_identity_routes_despite_different_survivor_name(self):
        self.assertEqual(self.match(name=' ADULT   CRAFT '),100)
    def test_new_dates_clocks_spans_and_missing_dates_decline(self):
        for occ in [[],[('2026-10-04','3pm',None)], [('2026-10-03','4pm',None)],
                    [('2026-10-03','3pm','2026-10-04')],self.OCC+[('2026-11-03','3pm',None)]]:
            self.assertIsNone(self.match(occurrences=occ))
    def test_source_branch_title_and_url_query_are_identity(self):
        for change in [dict(website_id=8),dict(location_id=11),dict(location_id=None),
                       dict(name='Adult Craft (Sub)'),dict(url=self.URL+'?session=2')]:
            self.assertIsNone(self.match(**change))
    def test_ambiguous_targets_fail_closed(self):
        key=(7,self.URL,'adult craft',10)
        self.assertIsNone(self.match({key:{100:{('2026-10-03','3pm','2026-10-03')},101:set()}}))
    def test_exact_name_classification_respects_dismissal(self):
        pair=(1,2,'Craft','Craft',10,'Library',7,7)
        self.assertEqual(classify_pairs([pair],set(),set(),{(1,2)}),([],[],[],[],[]))
        self.assertEqual(len(classify_pairs([pair],set(),set())[0]),1)
    def test_nonexact_shared_url_conflicts_remain_available_for_human_review(self):
        pair=(1,2,'Concert at 7pm','Concert at 9pm',10,'Venue',7,7)
        groups=classify_pairs([pair],{(1,2)},set())
        self.assertEqual(len(groups[1]),1)
        self.assertFalse(groups[0])
    def test_normalized_film_versions_never_become_auto_duplicates(self):
        pair=(1,2,'Totoro (Dub)','Totoro (Sub)',10,'Cinema',7,7)
        self.assertEqual(classify_pairs([pair],{(1,2)},{(1,2)}),([],[],[],[],[]))


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB')=='1','Requires isolated temporary MariaDB tables')
class ReviewedIdentitySQLTests(unittest.TestCase):
    def setUp(self):
        # Reuse the fully shadowed fixture, not its occurrence-specific tests.
        fixtures.DuplicateMergeOccurrenceTests.setUp(self)
        self.cur.execute("UPDATE events SET name=IF(id=1,'If Tara can do it','Adult Craft'),website_id=7,location_id=10")
        self.cur.execute("INSERT INTO event_occurrences(event_id,start_date,start_time) VALUES (1,'2026-10-03','3pm'),(2,'2026-10-03','3pm')")
        self.cur.execute("INSERT INTO event_urls(event_id,url) VALUES (2,'https://library.test/event/123')")
        self.cur.execute('INSERT INTO crawl_results VALUES (99,7)')
        self.cur.execute("INSERT INTO crawl_events VALUES (202,'Adult Craft: Spooky Light','https://library.test/event/123',10,99)")
        self.cur.execute("INSERT INTO crawl_event_occurrences VALUES (202,'2026-10-03','3pm',NULL)")
    def merge(self):
        with patch('event_icon_assignments.merge_assignments'):
            merge_pair(self.cur,1,2)
    def result(self,name='Adult Craft'):
        return identity.match(identity.load_index(self.cur),7,name,'https://library.test/event/123',10,[('2026-10-03','3pm',None)])
    def test_merge_persists_original_and_source_alias_and_moves_support(self):
        self.merge()
        self.assertEqual(self.result(),1)
        self.assertEqual(self.result('Adult Craft: Spooky Light'),1)
        self.cur.execute('SELECT event_id FROM event_sources WHERE crawl_event_id=202')
        self.assertEqual(self.cur.fetchall(),[(1,)])
    def test_suppression_alone_is_never_a_redirect(self):
        self.cur.execute('UPDATE events SET suppressed=1,reviewed=1 WHERE id=2')
        self.assertIsNone(self.result())
    def test_backfill_uses_only_explicit_moved_source_ids(self):
        self.cur.execute('UPDATE event_sources SET event_id=1 WHERE crawl_event_id=202')
        self.cur.execute('UPDATE events SET suppressed=1,reviewed=1 WHERE id=2')
        self.cur.execute('UPDATE crawl_results SET website_id=8 WHERE id=99')
        identity.record_merge(self.cur,1,2)
        args=(8,'Adult Craft: Spooky Light',ReviewedIdentityTests.URL,10,[('2026-10-03','3pm',None)])
        self.assertIsNone(identity.match(identity.load_index(self.cur),*args))
        identity.record_merge(self.cur,1,2,reviewed_source_ids=[202])
        self.assertEqual(identity.match(identity.load_index(self.cur),*args),1)
    def test_backfill_rejects_missing_or_not_moved_sources_before_writes(self):
        for ids in ([999],[202]):
            with self.assertRaises(ValueError):
                identity.record_merge(self.cur,1,2,reviewed_source_ids=ids)
        self.cur.execute('SELECT COUNT(*) FROM event_merge_redirects')
        self.assertEqual(self.cur.fetchone()[0],0)
    def test_backfilled_sources_remain_bounded_by_venue_and_reviewed_dates(self):
        self.cur.execute('UPDATE event_sources SET event_id=1 WHERE crawl_event_id=202')
        self.cur.execute('UPDATE events SET suppressed=1,reviewed=1 WHERE id=2')
        for sql in ["UPDATE crawl_events SET location_id=20 WHERE id=202",
                    "UPDATE crawl_event_occurrences SET start_date='2026-11-03' WHERE crawl_event_id=202"]:
            self.cur.execute('SAVEPOINT backfill')
            self.cur.execute(sql)
            identity.record_merge(self.cur,1,2,reviewed_source_ids=[202])
            self.assertIsNone(self.result('Adult Craft: Spooky Light'))
            self.cur.execute('ROLLBACK TO SAVEPOINT backfill')
    def test_retired_renamed_hidden_or_relocated_survivor_declines(self):
        for sql in ['archived=1','suppressed=1',"name='Another Program'",'location_id=20']:
            self.cur.execute('SAVEPOINT scenario')
            self.merge();self.cur.execute('UPDATE events SET '+sql+' WHERE id=1')
            self.assertIsNone(self.result())
            self.cur.execute('ROLLBACK TO SAVEPOINT scenario')
    def test_removed_canonical_slot_and_later_dismissal_disable_redirect(self):
        self.merge()
        self.cur.execute('SAVEPOINT scenario')
        self.cur.execute('DELETE FROM event_occurrences WHERE event_id=1')
        self.assertIsNone(self.result())
        self.cur.execute('ROLLBACK TO SAVEPOINT scenario')
        self.cur.execute('INSERT INTO dedupe_dismissed_pairs VALUES (1,2)')
        self.assertIsNone(self.result())
    def test_dismissed_pair_cannot_be_manually_merged_by_helper(self):
        self.cur.execute('INSERT INTO dedupe_dismissed_pairs VALUES (1,2)')
        with self.assertRaises(ValueError):self.merge()
        self.cur.execute('SELECT COUNT(*) FROM event_merge_redirects')
        self.assertEqual(self.cur.fetchone()[0],0)
    def test_chained_merge_retargets_old_alias_without_widening_dates(self):
        self.merge()
        self.cur.execute("INSERT INTO events(id,name,website_id,location_id) VALUES (3,'Canonical Program',7,10)")
        with patch('event_icon_assignments.merge_assignments'):merge_pair(self.cur,3,1)
        self.assertEqual(self.result(),3)
    def test_repeated_merge_retains_original_source_alias(self):
        self.merge();self.merge()
        self.assertEqual(self.result('Adult Craft: Spooky Light'),1)
    def test_chained_redirect_respects_inherited_dismissal(self):
        self.merge()
        self.cur.execute("INSERT INTO events(id,name,website_id,location_id) VALUES (3,'Other Program',7,10)")
        self.cur.execute('INSERT INTO dedupe_dismissed_pairs VALUES (2,3)')
        with self.assertRaises(ValueError):
            with patch('event_icon_assignments.merge_assignments'):merge_pair(self.cur,3,1)
        self.assertEqual(self.result(),1)
    def test_source_repair_preserves_curated_keeper_tags_when_requested(self):
        self.cur.execute('INSERT INTO event_tags VALUES (1,100),(2,200)')
        with patch('event_icon_assignments.merge_assignments'):
            merge_pair(self.cur,1,2,merge_tags=False)
        self.cur.execute('SELECT tag_id FROM event_tags WHERE event_id=1')
        self.assertEqual(self.cur.fetchall(),[(100,)])
        self.assertEqual(self.result(),1)
    def test_cross_venue_reconsideration_revokes_the_old_target(self):
        self.merge()
        self.cur.execute("INSERT INTO events(id,name,website_id,location_id) VALUES (3,'Corrected Venue Program',7,20)")
        with patch('event_icon_assignments.merge_assignments'):merge_pair(self.cur,3,2)
        self.assertIsNone(self.result())
        self.cur.execute('SELECT COUNT(*) FROM event_merge_redirects WHERE duplicate_id=2')
        self.assertEqual(self.cur.fetchone()[0],0)
    def test_listing_url_is_not_recorded(self):
        self.cur.execute("INSERT INTO website_urls VALUES (7,'https://library.test/event/123')")
        self.merge();self.assertIsNone(self.result())

class RedirectMergePathTests(unittest.TestCase):
    def test_reviewed_identity_precedes_fuzzy_and_url_fallbacks(self):
        from contextlib import ExitStack, redirect_stdout
        from datetime import timedelta
        from unittest.mock import MagicMock
        import io
        import merger
        today=date(2026,10,3);url=ReviewedIdentityTests.URL
        cursor=MagicMock(lastrowid=999)
        def execute(query,params=None):
            rows=[];one=None
            if 'SELECT ce.id, ce.name' in query:
                rows=[(202,'Adult Craft',None,'A public craft.','🎨','Library',None,10,url,7,None,None,99)]
            elif 'FROM crawl_event_occurrences' in query:
                rows=[(202,today,'3pm',None,'4pm',0)]
            elif 'SELECT location_id FROM events WHERE id' in query:
                one=(10,)
            cursor.fetchall.return_value=rows;cursor.fetchone.return_value=one
        cursor.execute.side_effect=execute
        index={(7,url,'adult craft',10):{1:{('2026-10-03','3pm','2026-10-03')}}}
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(patch.object(merger,'EditLogger',None))
            stack.enter_context(patch.object(identity,'load_index',return_value=index))
            stack.enter_context(patch.object(merger,'get_active_date_window',return_value=(today,today+timedelta(days=90))))
            db=stack.enter_context(patch.object(merger,'db'))
            db.build_tag_ancestor_map.return_value=({},set())
            db.archive_dead_source_events.return_value=(0,[])
            fallback=stack.enter_context(patch.object(merger,'_match_by_url_identity',return_value=2))
            stack.enter_context(patch.object(merger,'_merge_occurrences_into_event'))
            stack.enter_context(patch.object(merger,'_merge_grouped_event_urls'))
            self.assertEqual(merger.merge_crawl_events(cursor,MagicMock(),website_ids=[7]),(0,1))
            fallback.assert_not_called()
        writes=[call.args[1] for call in cursor.execute.call_args_list
                if 'INSERT IGNORE INTO event_sources' in call.args[0]]
        self.assertEqual(writes,[(1,202)])

class DuplicateApplyReviewTests(unittest.TestCase):
    def test_apply_reloads_dismissals_after_acquiring_lock(self):
        from contextlib import ExitStack, nullcontext, redirect_stdout
        from unittest.mock import MagicMock
        import io
        import find_duplicate_events as dedupe
        row=(1,2,'Craft','Craft',10,'Library',7,7)
        connection=MagicMock()
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(patch.object(sys,'argv',['dedupe','--suppress']))
            stack.enter_context(patch.object(dedupe,'create_connection',return_value=connection))
            stack.enter_context(patch.object(dedupe,'find_duplicates',return_value=[row]))
            for name in ['find_shared_url_pairs','find_same_time_pairs','find_cross_location_url_pairs']:
                stack.enter_context(patch.object(dedupe,name,return_value=[]))
            stack.enter_context(patch.object(dedupe,'get_dismissed_pairs',side_effect=[set(),{(1,2)}]))
            stack.enter_context(patch('dblock.write_lock',return_value=nullcontext()))
            apply=stack.enter_context(patch.object(dedupe,'merge_exact_duplicates',return_value=0))
            dedupe.main()
            self.assertEqual(apply.call_args.args[1],[])
