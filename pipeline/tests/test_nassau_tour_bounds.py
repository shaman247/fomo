"""The source adapter retains all program cards and supplies live tour bounds."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sources import nassau_museum as source

class NassauSourceTests(unittest.TestCase):
    def test_full_listing_and_detail_bounds_are_carried_together(self):
        pages={source.LISTING:'<main><h3 class="entry-title">Exhibition Tours</h3>Tuesday–Sunday2–3pm<h3 class="entry-title">Mansion Tours</h3>Select Saturdays<h3 class="entry-title">Separate Concert</h3>October10</main>',
               source.TOURS:'<main><h2>Exhibition Tours</h2>Explore Tiffany: Artist of the Gilded Age</main>',
               source.EXHIBITIONS:'<main>Tiffany: Artist of the Gilded Age July25,2026–November8,2026</main>'}
        with patch.object(source,'get_text',side_effect=pages.__getitem__):text,count=source.fetch()
        self.assertEqual(count,3)
        for phrase in ['Separate Concert','Select Saturdays','November8,2026',source.TOURS,source.EXHIBITIONS]:self.assertIn(phrase,text)
        self.assertIn('beyond its closing date',source.PROFILE.extraction_notes)
    def test_missing_required_page_never_publishes_partial_schedule(self):
        for html in ['<body>temporarily unavailable</body>','<main>no programs</main>']:
            with patch.object(source,'get_text',return_value=html):
                with self.assertRaises(ValueError):source.fetch()
        pages=['<main><h3 class="entry-title">Exhibition Tours</h3></main>','<main>Exhibition Tours</main>','<main>Season to be announced</main>']
        with patch.object(source,'get_text',side_effect=pages):
            with self.assertRaises(ValueError):source.fetch()
    def test_unbounded_detail_does_not_overwrite_joint_season_evidence(self):
        import site_profiles
        with patch.object(site_profiles, 'PROFILES', source.PROFILES):
            self.assertTrue(site_profiles.skip_detail_url(source.TOURS))
            self.assertTrue(site_profiles.skip_detail_url(source.TOURS + '?view=print'))
            for url in [source.LISTING, source.BASE + 'programs-and-events/mansion-tours/',
                        source.TOURS.rstrip('/') + '-another-program/',
                        'https://example.org/programs-and-events/docent-exhibition-tours/']:
                self.assertFalse(site_profiles.skip_detail_url(url))

    def test_profile_only_replaces_the_public_program_listing(self):
        self.assertTrue(source.PROFILE.matches(source.LISTING))
        self.assertFalse(source.PROFILE.matches(source.TOURS))
        self.assertFalse(source.PROFILE.matches('https://example.org/programs-and-events-category/programs-and-events/'))

if __name__=='__main__':unittest.main()
