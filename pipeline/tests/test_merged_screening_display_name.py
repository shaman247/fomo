"""A mixed film run must not inherit one showing's accessibility promise."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from merger import merged_screening_display_name, are_names_similar

class MergedScreeningDisplayNameTests(unittest.TestCase):
    def test_captioned_survivor_with_standard_showing(self):
        title='Spider-Man: Brand New Day'
        self.assertEqual(merged_screening_display_name(title+' (Open Cap/Eng Sub)',title),title)
        self.assertTrue(are_names_similar(title,title+' (Open Cap/Eng Sub)'))

    def test_projection_variant_with_standard_showing(self):
        self.assertEqual(merged_screening_display_name('The Odyssey [IMAX]','The Odyssey'),'The Odyssey')

    def test_caption_only_run_retains_claim(self):
        self.assertIsNone(merged_screening_display_name('Pressure (Open Cap/Eng Sub)','Pressure (Open Cap/Eng Sub)'))

    def test_standard_survivor_stays_standard(self):
        self.assertIsNone(merged_screening_display_name('Pressure','Pressure (Open Cap/Eng Sub)'))

    def test_different_films_cannot_rename_each_other(self):
        self.assertIsNone(merged_screening_display_name('Pressure (Open Cap/Eng Sub)','Wicked'))

    def test_meaningful_parenthetical_survives(self):
        self.assertIsNone(merged_screening_display_name('Hamlet (with live commentary)','Hamlet'))

    def test_short_alias_is_not_replaced_by_full_title(self):
        self.assertIsNone(merged_screening_display_name('Spider-Man (Open Cap/Eng Sub)','Spider-Man: Brand New Day'))

    def test_absent_names(self):
        self.assertIsNone(merged_screening_display_name(None,'Pressure'))
        self.assertIsNone(merged_screening_display_name('Pressure (IMAX)',None))

class BeginnerRegistrationIdentityTests(unittest.TestCase):
    def test_separate_registration_cohorts_do_not_merge(self):
        self.assertFalse(are_names_similar(
            'Beginning Instruction on Sunday Mornings at Zen Mountain Monastery',
            'Sunday Mornings at Zen Mountain Monastery'))

    def test_same_beginner_cohort_still_matches(self):
        self.assertTrue(are_names_similar(
            'Beginning Instruction on Sunday Mornings at Zen Mountain Monastery',
            'Beginning Instruction: Sunday Mornings at Zen Mountain Monastery'))
