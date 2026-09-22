import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from event_name_guards import library_program_variant_mismatch
from merger import are_names_similar,is_false_positive
from processor import group_event_occurrences
class LibraryVariants(unittest.TestCase):
 def test_short_film_title_is_identity_not_a_stopword(self):
  self.assertTrue(is_false_positive('Film Friday: It','Film Friday: Obsession'))
  self.assertFalse(are_names_similar('Film Friday: It','Film Friday: Obsession'))
 def test_book_themes_do_not_share_dates(self):
  self.assertFalse(are_names_similar('Great Books Discussion Group-The Keeper','Great Books Discussion Group-We Were the Mulvaneys'))
 def test_weekday_book_club_cannot_bridge_different_books(self):
  self.assertFalse(are_names_similar('Tuesday Book Club: Starling House','Tuesday Book Club: Black Sun'))
  for name in ['Tuesday Book Club: Starling House','Tuesday Book Club: Black Sun']:
   self.assertFalse(are_names_similar(name,'Tuesday Book Club'))
   self.assertFalse(are_names_similar('Tuesday Book Club',name))
 def test_matinee_and_craft_subjects_stay_distinct(self):
  for a,b in [('Monday Matinee: Project Hail Mary','Monday Matinee: Power Ballad'),('Teen Night: Rustic Botanical Hanging Mobile','Teen Night: Scrapbooks & Junk Journals')]:self.assertTrue(library_program_variant_mismatch(a,b))
 def test_punctuation_case_and_release_year_are_not_new_identity(self):
  self.assertFalse(library_program_variant_mismatch('Film Friday: IT','Film Friday—It (2017)'))
 def test_other_series_and_bare_titles_keep_existing_policy(self):
  self.assertFalse(library_program_variant_mismatch('Talk: It','Talk: Obsession'));self.assertFalse(library_program_variant_mismatch('Film Friday','Film Friday: It'))
 def test_processor_keeps_named_subjects_separate_even_at_one_url(self):
  rows=[dict(name=n,location='Library',location_id=1,start_date='2026-10-30',start_time='1pm',url='https://example.org/series') for n in ['Film Friday: It','Film Friday: It Happened One Night']]
  self.assertEqual(len(group_event_occurrences(rows)),2)
