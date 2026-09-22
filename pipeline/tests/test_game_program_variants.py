import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from event_name_guards import game_program_variant_mismatch
from processor import group_event_occurrences
from merger import are_names_similar


class GameProgramVariantTests(unittest.TestCase):
    def test_generic_and_named_sessions_stay_distinct_in_both_orders(self):
        for first, second in [('RPG SideQuest', 'RPG SideQuest | Business Wizards'),
                              ('MTG PreRelease | Reality Fracture', 'MTG PreRelease | Star Trek'),
                              ('Game Night | Trouble Brewing', 'Game Night | Bad Moon Rising'),
                              ('RPG Night | Black Dice: The Black Dinner', 'RPG Night | Black Dice: Red Red Wine')]:
            for names in ((first, second), (second, first)):
                with self.subTest(names=names):
                    self.assertFalse(are_names_similar(*names))
                    rows = [dict(name=n, location_id=1, location='Game Store', url='https://example.org/calendar',
                                 start_date=d, tags=['Games']) for n,d in zip(names,['2026-10-01','2026-10-08'])]
                    grouped = group_event_occurrences(rows,'https://example.org/calendar')
                    self.assertEqual(len(grouped),2)
                    self.assertEqual([len(x['occurrences']) for x in grouped],[1,1])

    def test_same_subject_punctuation_and_case_variants_match(self):
        for pair in [('RPG Night | Delta Green', 'RPG Night | DELTA GREEN'),
                     ('RPG Night | Café Games', 'RPG Night | Cafe Games'),
                     ('RPG Night | Black Dice: Red Red Wine', 'RPG Night | Black Dice - Red Red Wine')]:
            self.assertFalse(game_program_variant_mismatch(*pair))
            self.assertTrue(are_names_similar(*pair))

    def test_ordinary_title_and_venue_suffix_unaffected(self):
        self.assertFalse(game_program_variant_mismatch('Example Concert', 'Example Concert | Main Hall'))

    def test_repeated_same_named_game_groups_its_dates(self):
        rows=[dict(name='RPG Night | Delta Green',location_id=1,start_date=d) for d in ['2026-10-01','2026-10-08']]
        self.assertEqual(len(group_event_occurrences(rows)[0]['occurrences']),2)


if __name__=='__main__':unittest.main()
