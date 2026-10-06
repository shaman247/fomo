import unittest
try:
    from sources.wellmont import listing_records
except ImportError:
    listing_records=None

@unittest.skipIf(listing_records is None,'Deployment source not installed')
class WellmontTests(unittest.TestCase):
    def test_own_list_and_clock_labels(self):
        card='<div class="show_widget_container"><a class="show_details_button" href="https://wellmonttheater.com/shows/own/"></a><div class="show_widget_date_hover">Nov 22 2026</div><div class="show_widget_show_title_hover">Own concert</div>Doors at 6 PM Show at 7 PM Sold Out</div>'
        rows=listing_records('<main>'+card+'</main><aside>Other city concert</aside>')
        self.assertEqual(len(rows),1);self.assertIn('Doors at 6 PM Show at 7 PM Sold Out',rows[0][2])
        with self.assertRaises(ValueError):listing_records('<main>'+card+card+'</main>')
        with self.assertRaises(ValueError):listing_records('<main>'+card+'<a class="next"></a></main>')
    def test_missing_calendar_fails(self):
        with self.assertRaises(ValueError):listing_records('<main>Loading</main>')
