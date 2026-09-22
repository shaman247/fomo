"""Public calendar sessions need neither an individual URL nor a blurb."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from processor import _is_source_listing_metadata


class ListingMetadataDatesTests(unittest.TestCase):
    def check(self, row, listing=True):
        with patch('processor.site_profiles.is_listing_url', return_value=listing):
            return _is_source_listing_metadata(row, 'https://example.org/calendar', 'https://example.org/calendar')

    def test_dated_session_with_no_blurb_survives(self):
        self.assertFalse(self.check({'name': 'MTG Draft', 'start_date': '2026-10-02',
                                    'description': 'No description available.'}))

    def test_closing_only_exhibition_survives(self):
        self.assertFalse(self.check({'end_date': '2026-10-02', 'description': ''}))

    def test_undated_blank_listing_metadata_still_rejected(self):
        for blank in (None, '', 'No description available.'):
            self.assertTrue(self.check({'start_date': None, 'end_date': '', 'description': blank}))

    def test_undated_program_with_prose_survives(self):
        self.assertFalse(self.check({'description': 'A public screening with filmmaker discussion.'}))

    def test_individual_detail_url_survives(self):
        self.assertFalse(self.check({}, listing=False))


if __name__ == '__main__':
    unittest.main()
