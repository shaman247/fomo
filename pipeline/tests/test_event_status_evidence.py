"""Retain booking status and distinguish giving appeals from real gatherings."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extractor
from processor import is_obvious_non_event, which_junk_rule


class EventStatusEvidenceTests(unittest.TestCase):
    def test_all_extraction_paths_receive_status_evidence_rules(self):
        prompts = [
            extractor.get_prompt('https://example.org/', 'HOLD: mri project', '2026-09-20', 'Example', ''),
            extractor.get_vision_prompt('https://example.org/', 'HOLD: mri project', '2026-09-20', 'Example', ''),
            extractor.get_chunk_instructions(),
            extractor.detail_instructions(),
            extractor.get_enrichment_prompt(['mri project'], 'Example', content_snippets={'mri project':'HOLD: mri project'}),
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt[:60]):
                self.assertIn(extractor.EVENT_STATUS_RULE, prompt)

    def test_hold_marker_is_the_evidence_not_casing_or_sparse_body(self):
        self.assertEqual(which_junk_rule('HOLD: mri project', 'No description available.'), 'hold_placeholder')
        for name in ('mri project', 'jazz jam', 'robotics night', 'Hold Your Breath'):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, 'No description available.'))

    def test_source_confirmed_giving_tuesday_appeal(self):
        description = ('The Intrepid Museum is once again taking part in Giving Tuesday, '
                       'a global day of generosity. Donations help the Museum preserve '
                       'its historic collections, provide educational programming and '
                       'create experiences for visitors of all ages.')
        for name in ('Save the Date: Giving Tuesday', 'Giving Tuesday', 'Giving Tuesday 2026!'):
            with self.subTest(name=name):
                self.assertEqual(which_junk_rule(name, description), 'giving_tuesday_appeal')

    def test_actual_gatherings_and_uncertain_listings_survive(self):
        cases = [
            ('Save the Date: Giving Tuesday', 'No description available.'),
            ('Giving Tuesday', None),
            ('Giving Tuesday', 'Your support funds the museum. Join us for a benefit concert.'),
            ('Giving Tuesday', 'Donate at our gala dinner and auction.'),
            ('Giving Tuesday', 'A day of generosity with volunteer sessions.'),
            ('Giving Tuesday', 'Your gift includes admission to a guided tour.'),
            ('Giving Tuesday', 'Donate at our open house with live music.'),
            ('Giving Tuesday Benefit Concert', 'Your donations support music education.'),
            ('Save the Date: Community Dinner', 'Donations welcome.'),
            ('Giving Tuesday: Volunteer Day', 'Make a gift to support the community.'),
        ]
        for name, description in cases:
            with self.subTest(name=name, description=description):
                self.assertFalse(is_obvious_non_event(name, description))


if __name__ == '__main__':
    unittest.main()
