"""Expanded source-grounded schedules must not become latest-crawl replacement."""
import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from schedule_change_evidence import changes,identity_name
from reschedules import superseded_slots


def slot(day,clock='6pm',end='7pm'):
    return (date.fromisoformat(day),clock,None,end)
def canonical(row):return row[:2]+(row[2] or row[0],row[3])
def source(text,rows,name='Writing Group',time='2026-09-25 10:00:00',website=7,venue=10):
    return dict(name=name,description=text,occurrences=rows,crawled_at=time,website_id=website,location_id=venue)
EVENT=dict(name='Writing Group',location_id=10,suppressed=False)
OLD=slot('2026-09-28');NEW=slot('2026-09-29');OTHER=slot('2026-10-06')

class ExpandedNoticeTests(unittest.TestCase):
    def test_weekday_ordinal_abbreviation_and_self_attributed_reason(self):
        got=changes(source('This event was rescheduled from Monday, Sept. 28th to Tuesday, September 29 due to rain.',[NEW]))
        self.assertEqual(got[0]['old_days'],{OLD[0]});self.assertEqual(got[0]['replacement'],{canonical(NEW)})
    def test_compound_separate_changes_keep_own_replacement(self):
        old2=slot('2026-10-05')
        got=changes(source('Rescheduled from September 28 to September 29; rescheduled from October 5 to October 6.',[NEW,OTHER]))
        self.assertEqual(len(got),2)
        before=source('Discussion.',[OLD,old2],time='2026-09-20 10:00:00')
        self.assertEqual(superseded_slots(EVENT,[OLD,old2,NEW,OTHER],[before,source('Rescheduled from September 28 to September 29; rescheduled from October 5 to October 6.',[NEW,OTHER])]),{canonical(OLD),canonical(old2)})
    def test_grouped_heading_scopes_from_only_notice(self):
        got=changes(source('2026-09-29 6pm–7pm\nRescheduled from September 28.\n\n2026-10-06 6pm–7pm\nRegular discussion.',[NEW,OTHER]))
        self.assertEqual(len(got),1);self.assertEqual(got[0]['replacement'],{canonical(NEW)})
        self.assertFalse(changes(source('Rescheduled from September 28. Regular discussion.',[NEW,OTHER])))
    def test_multiple_explicit_replacement_sessions(self):
        notice=source('Rescheduled from September 28 to September 29 and October 6.',[NEW,OTHER])
        self.assertEqual(changes(notice)[0]['replacement'],{canonical(NEW),canonical(OTHER)})
        self.assertEqual(superseded_slots(EVENT,[OLD,NEW,OTHER],[source('Discussion.',[OLD],time='2026-09-20 10:00:00'),notice]),{canonical(OLD)})
        self.assertFalse(superseded_slots(EVENT,[OLD,NEW],[source('Discussion.',[OLD],time='2026-09-20 10:00:00'),notice]))
    def test_same_month_list_is_explicit_not_generated_recurrence(self):
        a,b=slot('2026-10-15'),slot('2026-10-22')
        got=changes(source('Rescheduled from September 28 to October 15 and 22.',[a,b]))
        self.assertEqual(got[0]['replacement'],{canonical(a),canonical(b)})
    def test_title_only_notice_preserves_exact_program_identity(self):
        name='Writing Group - Rescheduled from September 28'
        self.assertEqual(identity_name(name),'writing group')
        notice=source('Discussion.',[NEW],name=name)
        self.assertEqual(superseded_slots(EVENT,[OLD,NEW],[source('Discussion.',[OLD],time='2026-09-20 10:00:00'),notice]),{canonical(OLD)})
        self.assertEqual(identity_name('Writing Group (September edition)'),'writing group (september edition)')
    def test_numeric_ambiguity_never_uses_nearness_as_locale(self):
        self.assertFalse(changes(source('Rescheduled from 6/8.',[slot('2026-09-10')])))
        self.assertTrue(changes(source('Rescheduled from 9/28.',[NEW])))
        self.assertTrue(changes(source('Rescheduled from 9/28/26.',[NEW])))
        self.assertFalse(changes(source('Rescheduled from 9/28/25.',[NEW])))
        notice=source('Rescheduled from 9/8.',[NEW])
        self.assertFalse(changes(notice))
        self.assertFalse(changes(notice,old_days={date(2026,9,8),date(2026,8,9)}))
        self.assertEqual(changes(notice,old_days={date(2026,9,8)})[0]['old_days'],{date(2026,9,8)})
    def test_cancelled_ambiguous_multiple_from_only_and_other_program_decline(self):
        for text in ['Another event was rescheduled from September 28.',
                     'Rescheduled from September 28! Rescheduled from September 27!',
                     'Cancelled. Rescheduled from September 28.',
                     'If it rains this event will be rescheduled from September 28 to September 29.']:
            self.assertFalse(changes(source(text,[NEW])),text)
    def test_independent_old_dates_and_new_replacement_disagreement_survive(self):
        notice=source('Rescheduled from September 28 to September 29 and October 6.',[NEW,OTHER])
        old=source('Discussion.',[OLD],time='2026-09-20 10:00:00')
        for conflict in [source('Discussion.',[OLD],website=8),source('Discussion.',[slot('2026-10-06','8pm','9pm')],website=8)]:
            self.assertFalse(superseded_slots(EVENT,[OLD,NEW,OTHER],[old,notice,conflict]))
    def test_stale_replay_is_order_independent_and_never_revives_old(self):
        old=source('Discussion.',[OLD],time='2026-09-20 10:00:00')
        new=source('Rescheduled from September 28 to September 29 and October 6.',[NEW,OTHER])
        for sources in ([old,new],[new,old]):
            for _ in range(2):self.assertEqual(superseded_slots(EVENT,[NEW,OTHER,OLD],sources),{canonical(OLD)})

class CompleteReplacementTests(unittest.TestCase):
    TEXT='The complete revised schedule for this course from 2026-09-01 to 2026-10-31 is September 29 and October 6.'
    def test_complete_explicit_window_is_bounded_and_preserves_unrelated_dates(self):
        outside=slot('2026-11-05');old=source('Discussion.',[OLD,outside],time='2026-09-20 10:00:00');new=source(self.TEXT,[NEW,OTHER])
        self.assertEqual(superseded_slots(EVENT,[OLD,NEW,OTHER,outside],[old,new]),{canonical(OLD)})
    def test_missing_window_dates_incomplete_slots_and_generic_updates_decline(self):
        for text,rows in [('Updated schedule: September 29 and October 6.',[NEW,OTHER]),
                          (self.TEXT.replace('2026-09-01','September 1'),[NEW,OTHER]),
                          (self.TEXT,[NEW])]:
            self.assertFalse(changes(source(text,rows),old_days={OLD[0]}))
    def test_independent_publisher_veto_and_repeated_stale_replay(self):
        old=source('Discussion.',[OLD],time='2026-09-20 10:00:00');new=source(self.TEXT,[NEW,OTHER]);rows=[OLD,NEW,OTHER]
        self.assertFalse(superseded_slots(EVENT,rows,[old,new,source('Discussion.',[OLD],website=8)]))
        for _ in range(2):self.assertEqual(superseded_slots(EVENT,rows,[new,old]),{canonical(OLD)})

import os
@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB')=='1','Connection-local MariaDB tables only')
class ExpandedScheduleSQLTests(unittest.TestCase):
    def setUp(self):
        import test_reschedules as fixture
        fixture.DatabaseBoundaryTests.setUp(self)
    def rows(self,event_id=180336):
        import test_reschedules as fixture
        return fixture.DatabaseBoundaryTests.rows(self,event_id)
    def merge(self,source_id,incoming):
        import test_reschedules as fixture
        return fixture.DatabaseBoundaryTests.merge(self,source_id,incoming)
    def test_two_replacements_then_repeated_stale_source_preserve_original_evidence(self):
        import test_reschedules as f
        second=(date(2026,10,6),'6:30pm',None,'7:30pm')
        self.q.execute('UPDATE crawl_events SET description=%s WHERE id=2',
                       ('Rescheduled from September 28 to September 29 and October 6.',))
        self.q.execute('INSERT INTO crawl_event_occurrences VALUES(2,%s,%s,%s,%s)',second)
        self.merge(2,[f.NEW,second])
        for _ in range(2):self.assertEqual(self.merge(1,[f.OLD])[1],[])
        self.assertEqual([row[:4] for row in self.rows()],[f.JULY,f.AUGUST,f.NEW,second])
        self.assertEqual([row[:4] for row in self.rows(999)],[f.OLD])
        self.q.execute('SELECT COUNT(*) FROM crawl_event_occurrences');self.assertEqual(self.q.fetchone()[0],5)
    def test_title_only_notice_has_same_provenance_boundary(self):
        import test_reschedules as f
        self.q.execute('UPDATE crawl_events SET name=%s,description=%s WHERE id=2',
                       (f.EVENT['name']+' - Rescheduled from 9/28','A book discussion.'))
        self.merge(2,[f.NEW]);self.assertEqual(self.merge(1,[f.OLD])[1],[])
        self.assertEqual([row[:4] for row in self.rows()],[f.JULY,f.AUGUST,f.NEW])
    def test_complete_window_replacement_keeps_outside_history_and_stale_source(self):
        import test_reschedules as f
        self.q.execute('UPDATE crawl_events SET description=%s WHERE id=2',
                       ('The complete revised schedule for this course from 2026-09-01 to 2026-09-30 is September 29.',))
        self.merge(2,[f.NEW]);self.assertEqual(self.merge(1,[f.OLD])[1],[])
        self.assertEqual([row[:4] for row in self.rows()],[f.JULY,f.AUGUST,f.NEW])
    def test_newer_independent_old_slot_prevents_complete_window_deletion(self):
        import test_reschedules as f
        self.q.execute('UPDATE crawl_events SET description=%s WHERE id=2',
                       ('The complete revised schedule for this course from 2026-09-01 to 2026-09-30 is September 29.',))
        self.q.execute('INSERT INTO crawl_results VALUES(3,94,%s)',('2026-09-23 10:00:00',))
        self.q.execute('INSERT INTO crawl_events VALUES(3,3,%s,%s,7866)',(f.EVENT['name'],'Independent date announcement.'))
        self.q.execute('INSERT INTO event_sources VALUES(180336,3)')
        self.q.execute('INSERT INTO crawl_event_occurrences VALUES(3,%s,%s,%s,%s)',f.OLD)
        self.merge(2,[f.NEW]);self.assertIn(f.OLD,[row[:4] for row in self.rows()])

class ActualSourceReplayTests(unittest.TestCase):
    def test_captured_real_notice_provenance_and_second_stale_replay(self):
        import json
        cases=json.loads((Path(__file__).parent/'fixtures/reschedule_source_cases.json').read_text())
        for case in cases:
            with self.subTest(event=case['event']['id']):
                expected={tuple([date.fromisoformat(r[0]),r[1],date.fromisoformat(r[2]),r[3]]) for r in case['expected_removed']}
                rows=case['canonical'];sources=case['sources']
                self.assertEqual(superseded_slots(case['event'],rows,sources),expected)
                for ordered in (sources,list(reversed(sources))):
                    # The original source history remains intact after canonical
                    # retirement and is presented twice as a stale merge input.
                    stale=[r for s in ordered for r in s['occurrences']]
                    for _ in range(2):
                        self.assertEqual(superseded_slots(case['event'],rows+stale,ordered),expected)
