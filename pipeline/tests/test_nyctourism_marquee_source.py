import unittest
try:
 from sources import nyctourism_marquee as source
except ImportError:source=None

@unittest.skipIf(source is None,'Deployment source not installed')
class TourismSourceTests(unittest.TestCase):
 def test_visible_owner_date_excludes_hydration_status_and_neighbor(self):
  html='<script>AlreadyOccurred.Label This event has already occurred Dec 5, 1999</script><div class="DetailPageTemplate_container__x"><h1>Own Program</h1><p class="BroadwaySummary_detailText__x">Nov 27, 2026 - Jan 3, 2027</p><p>Own venue and prose</p></div><aside>Other show January 3</aside>'
  text=source.parse_detail(html,'https://www.nyctourism.com/events/george-balanchines-the-nutcracker/')
  self.assertIn('Nov 27, 2026 - Jan 3, 2027',text);self.assertNotIn('already occurred',text);self.assertNotIn('Other show',text)
 def test_scope_and_unknown_date_fail_closed(self):
  self.assertFalse(source.PROFILE.matches('https://www.nyctourism.com/annual-events/'))
  self.assertFalse(source.PROFILE.matches('https://www.nyctourism.com/events/unreviewed'))
  with self.assertRaises(ValueError):source.parse_detail('<div class="DetailPageTemplate_container"><h1>Own show</h1><p>December</p></div>','x')

 def test_tree_contract_keeps_season_and_lighting_evidence_without_inference(self):
  url='https://www.nyctourism.com/events/rockefeller-center-christmas-tree-lighting/'
  self.assertTrue(source.PROFILE.matches(url))
  html='<div class="DetailPageTemplate_container__x"><h1>Park Center Christmas Tree Lighting</h1><p class="BroadwaySummary_detailText__x">Dec 2, 2026 - Jan 9, 2027</p><p>Lighting occasion on December 2. The tree remains on display until January 9. Viewing hours not supplied.</p></div>'
  text=source.parse_detail(html,url)
  self.assertIn('Lighting occasion on December 2.',text)
  self.assertIn('display until January 9',text)
  self.assertIn('Viewing hours not supplied',text)
  self.assertIn('ceremony date is not supported',source.PROFILE.extraction_notes)
