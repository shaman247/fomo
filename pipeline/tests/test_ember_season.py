"""Season discovery must not guess a year or combine venues."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from sources import ember_season
except ImportError:
    ember_season = None


@unittest.skipIf(ember_season is None, 'deployment-specific source plugin not installed')
class EmberSeasonTests(unittest.TestCase):
    def test_link_discovery_tracks_published_year(self):
        self.assertEqual(ember_season._current_season('<a href="/20272028-season">Explore</a>'),
                         'https://www.emberarts.org/20272028-season')

    def test_missing_ambiguous_and_foreign_links_fail(self):
        for html in ['', '<a href="https://example.org/20262027-season">Season</a>',
                     '<a href="/20262027-season">Now</a><a href="/20252026-season">Past</a>']:
            with self.subTest(html=html), self.assertRaises(ValueError):
                ember_season._current_season(html)

    def test_performances_are_separate_cards(self):
        html = '''<main><div class="sqs-html-content"><h1>GLOW</h1></div>
        <div class="sqs-html-content">
        <h4>Friday, December 4, 7:30PM at St. John's in the Village</h4>
        <h4>Sunday, December 6, 5:00PM at Trinity Episcopal Church, Asbury Park</h4>
        <p>A choral concert.</p><h4>PAY WHAT YOU WILL:</h4></div></main>'''
        text, count = ember_season._season_cards(html, 'https://www.emberarts.org/20262027-season')
        self.assertEqual(count, 2)
        cards = text.split('### ')[1:]
        self.assertIn('December 4', cards[0])
        self.assertNotIn('December 6', cards[0])
        self.assertIn('December 6', cards[1])
        self.assertNotIn('December 4', cards[1])

    def test_changed_program_structure_fails(self):
        for html in ['', '<div class="sqs-html-content"><h1>New concert</h1></div>']:
            with self.assertRaises(ValueError):
                ember_season._season_cards(html, 'https://www.emberarts.org/20262027-season')

    def test_composite_season_is_not_a_detail_page(self):
        self.assertTrue(ember_season.PROFILE.skip_detail_url('https://www.emberarts.org/20262027-season'))
        self.assertFalse(ember_season.PROFILE.skip_detail_url('https://www.emberarts.org/concert-glow'))

    def test_homepage_only_announcements_survive_without_duplicate_summary(self):
        home = '''<a href="/20262027-season">Season</a><main>
        <div class="sqs-html-content"><h3>Cabaret!</h3><h4>Tuesday, September 22</h4>
        <a href="https://tickets.example/cabaret">Get tickets</a></div>
        <div class="sqs-html-content"><h3>GLOW</h3><h4>December 4 and 6</h4></div></main>'''
        season = '''<div class="sqs-html-content"><h1>GLOW</h1>
        <h4>Friday, December 4, 7:30PM at NYC church</h4></div>'''
        with patch.object(ember_season, 'get_text', side_effect=[home, season]):
            text, count = ember_season.fetch_and_build_markdown()
        self.assertEqual(count, 2)
        self.assertIn('Cabaret!', text)
        self.assertIn('https://tickets.example/cabaret', text)
        self.assertNotIn('December 4 and 6', text)


if __name__ == '__main__':
    unittest.main()
