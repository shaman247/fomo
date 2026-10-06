"""Publisher co-listed films require separate exact title/permalink witnesses."""
import unittest
import merger
from test_merger_suppressed_match import _MatcherHarness

PAIRS=[('Once Upon a Time in China (黃飛鴻)','Once Upon a Time in China II (黃飛鴻之二：男兒當自強)'),('The Matrix','The Matrix Reloaded'),('Sergei Loznitsa’s Short Films: Program 1','Sergei Loznitsa’s Short Films: Program 2'),('The Kiev Trial (КИЕВСКИЙ ПРОЦЕСС)','The Trial (ПРОЦЕСС)')]

class FilmSiblingIdentityTests(unittest.TestCase):
 def context(self,a,b):
  roster=merger._CaptureRoster();roster.extend([(1,a),(2,b)])
  roster.films={1:(merger.normalize_name_for_dedup(a),'cinema.example/film/a'),2:(merger.normalize_name_for_dedup(b),'cinema.example/film/b')}
  return dict(name=a,url_key='cinema.example/film/a',website_id=62,crawl_event_id=1,candidate=dict(id=9,name=b,website_id=62),roster=roster,listing_url_keys=set(),url_key_name_counts={},event_url_keys={9:{'cinema.example/film/b'}})
 def test_four_reviewed_pairs_both_orders_despite_identical_slots(self):
  for a,b in PAIRS:
   for left,right in [(a,b),(b,a)]:
    ctx=self.context(left,right)
    self.assertTrue(merger._film_sibling_listing_veto(**ctx),(left,right))
    self.assertTrue(merger._sibling_listing_veto(**dict(ctx,crawl_event_slots={('2026-11-14','4pm')},candidate_slots={('2026-11-14','4pm')})))
 def test_real_candidate_selection_keeps_exact_owner_in_either_order(self):
  for a,b in PAIRS:
   for left,right in [(a,b),(b,a)]:
    ctx=self.context(left,right);h=_MatcherHarness(left,[9,10],location_id=1)
    h.vetoed_ids={9} if merger._film_sibling_listing_veto(**ctx)else set()
    other=dict(ctx['candidate'],location_id=1);own=dict(id=10,name=left,website_id=62,location_id=1)
    for pool in [[other,own],[own,other]]:self.assertEqual(h.find_best_match(pool),10)
 def test_same_title_and_format_spelling_remain_eligible(self):
  for a,b in [('The Matrix','THE MATRIX'),('The Matrix','The Matrix (IMAX)'),('The Matrix (Open Cap/Eng Sub)','The Matrix')]:self.assertFalse(merger._film_sibling_listing_veto(**self.context(a,b)))
 def test_requires_exact_both_film_witnesses_and_distinct_own_urls(self):
  for change in ['incoming_missing','candidate_missing','changed_title','other_publisher','shared_url','listing_url','ambiguous_url']:
   c=self.context(*PAIRS[1])
   if change=='incoming_missing':del c['roster'].films[1]
   elif change=='candidate_missing':del c['roster'].films[2]
   elif change=='changed_title':c['candidate']['name']='Matrix Reloaded with introduction'
   elif change=='other_publisher':c['candidate']['website_id']=63
   elif change=='shared_url':c['event_url_keys'][9].add(c['url_key'])
   elif change=='listing_url':c['listing_url_keys'].add((62,c['url_key']))
   else:c['url_key_name_counts'][(62,c['url_key'])]=100
   self.assertFalse(merger._film_sibling_listing_veto(**c),change)
 def test_ordinary_nonfilm_roster_is_unchanged(self):
  c=self.context(*PAIRS[1]);c['roster']=list(c['roster']);self.assertFalse(merger._film_sibling_listing_veto(**c))

if __name__=='__main__':unittest.main()
