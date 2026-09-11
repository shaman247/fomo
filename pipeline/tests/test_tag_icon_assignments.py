import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tag_icon_assignments import planned_changes, INITIAL
from event_icons import ICON_IDS

class TagIconTests(unittest.TestCase):
    def test_seed_uses_known_icons_but_not_broad_tags(self):
        # The historical seed need not grow with later, explicitly edited batches.
        self.assertTrue(set(INITIAL).issubset(ICON_IDS))
        names=[name for values in INITIAL.values() for name in values]
        self.assertEqual(len(names),len(set(names)))
        for broad in ['Games','Tabletop','Magic','Sewing','Glass Art']:
            self.assertNotIn(broad,names)

    def test_updates_only_exact_existing_records_and_preserves_emoji(self):
        tags=[dict(id=1,name='MTG',emoji='🧙',icon_id=None),
              dict(id=2,name='Magic',emoji='🪄',icon_id=None),
              dict(id=3,name='MTG Meetup',emoji='🎲',icon_id=None)]
        changes=planned_changes(tags)
        self.assertEqual(len(changes),1)
        self.assertEqual(changes[0]['icon_id'],'game-mtg')
        self.assertEqual(changes[0]['emoji'],'🧙')
        self.assertIsNone(tags[0]['icon_id'])

    def test_seed_preserves_subsequent_editorial_assignments(self):
        row=dict(id=1,name='Bingo',icon_id='music-bingo')
        self.assertEqual(planned_changes([row]),[])
        self.assertEqual(planned_changes([row],'Bingo','bingo')[0]['icon_id'],'bingo')

    def test_explicit_clear_and_invalid_targets(self):
        row=dict(id=1,name='Bingo',icon_id='bingo')
        self.assertIsNone(planned_changes([row],'Bingo',None)[0]['icon_id'])
        with self.assertRaises(ValueError): planned_changes([row],'Unknown','bingo')
        with self.assertRaises(ValueError): planned_changes([row],'Bingo','unknown')

    def test_reviewed_noto_override_preserves_flag_fallback(self):
        row=dict(id=977,name='Spanish Language',emoji='🇪🇸',icon_id=None)
        change=planned_changes([row],'Spanish Language','noto-1f5e3')[0]
        self.assertEqual(change['icon_id'],'noto-1f5e3')
        self.assertEqual(change['emoji'],'🇪🇸')
        self.assertIsNone(row['icon_id'])
        with self.assertRaises(ValueError):
            planned_changes([row],'Spanish Language','noto-unreviewed')

if __name__=='__main__':unittest.main()
