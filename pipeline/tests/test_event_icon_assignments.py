"""Assignment lifetime, editorial overrides, stale export and dedupe regressions."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from event_icon_assignments import (desired_assignment, export_icon, manual_assignment,
                                    merge_manual_decisions, require_lock)

EVENT=dict(id=1,name='Go Club',description='Play the board game.',tags=['Games'])

class AssignmentTests(unittest.TestCase):
    def test_clear_rule_is_exported_and_repeat_is_idempotent(self):
        row=desired_assignment(EVENT)
        self.assertEqual(row,desired_assignment(EVENT,row))
        self.assertEqual(export_icon(EVENT,row),'game-go')

    def test_changed_content_replaces_or_removes_automatic_choice(self):
        old=desired_assignment(EVENT)
        new=dict(EVENT,name='Trivia Night')
        self.assertIsNone(export_icon(new,old))
        self.assertEqual(desired_assignment(new,old)['icon_id'],'trivia')
        self.assertIsNone(desired_assignment(dict(EVENT,name='Community Party'),old))

    def test_ambiguous_is_stored_for_review_and_not_exported(self):
        event=dict(EVENT,name='Scrabble and Mahjong')
        row=desired_assignment(event)
        self.assertTrue(row['review_required'])
        self.assertIsNone(export_icon(event,row))

    def test_manual_fallback_blocks_automatic_replacement(self):
        row=manual_assignment(EVENT,None,'Use broad fallback')
        self.assertEqual(desired_assignment(EVENT,row),row)
        self.assertIsNone(export_icon(EVENT,row))

    def test_changed_manual_choice_is_preserved_but_needs_review(self):
        old=manual_assignment(EVENT,'game-go','Reviewed event')
        changed=dict(EVENT,description='New primary activity')
        new=desired_assignment(changed,old)
        self.assertEqual(new['icon_id'],'game-go')
        self.assertEqual(new['input_hash'],old['input_hash'])
        self.assertTrue(new['review_required'])
        self.assertIsNone(export_icon(changed,new))

    def test_unknown_id_and_old_rule_version_fall_back(self):
        row=desired_assignment(EVENT)
        self.assertIsNone(export_icon(EVENT,dict(row,icon_id='unknown')))
        self.assertIsNone(export_icon(EVENT,dict(row,rule_version='old')))

    def test_manual_must_be_known_and_explained(self):
        with self.assertRaises(ValueError): manual_assignment(EVENT,'no-such-icon','Reason')
        with self.assertRaises(ValueError): manual_assignment(EVENT,None,' ')

    def test_merge_preserves_a_single_manual_choice(self):
        old=manual_assignment(dict(EVENT,id=2),'game-go','Reviewed on duplicate')
        row=merge_manual_decisions(EVENT,[desired_assignment(EVENT),old])
        self.assertEqual(row['event_id'],1)
        self.assertEqual(export_icon(EVENT,row),'game-go')

    def test_merge_does_not_revalidate_a_stale_manual_choice(self):
        old=manual_assignment(dict(EVENT,id=2,description='Different content'),'game-go','Old review')
        row=merge_manual_decisions(EVENT,[old])
        self.assertTrue(row['review_required'])
        self.assertIsNone(export_icon(EVENT,row))

    def test_merge_conflict_stays_manual_and_cannot_auto_reassign(self):
        a=manual_assignment(EVENT,'game-go','Go is primary')
        b=manual_assignment(dict(EVENT,id=2),None,'Mixed games')
        row=merge_manual_decisions(EVENT,[a,b])
        self.assertEqual(row['origin'],'manual')
        self.assertTrue(row['review_required'])
        self.assertIsNone(row['icon_id'])
        self.assertEqual(desired_assignment(EVENT,row),row)

    def test_writes_require_connection_owned_shared_lock(self):
        class Cursor:
            def execute(self, sql): pass
            def fetchone(self): return (0,)
        with self.assertRaises(RuntimeError): require_lock(Cursor())

if __name__=='__main__': unittest.main()
