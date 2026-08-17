"""Tests for Virtual-family tagging derived from the raw source location string.

Policy (`.claude/rules/tag-system.md` §Virtual): virtual events stay pinned to
their organizer's physical venue, so `events.location_name` — the raw string
from the source — is the only reliable delivery-method signal, and every
virtual event must carry the `Virtual` root so users can filter it.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import virtual_tags_for_location


class TestVirtualTagsForLocation(unittest.TestCase):

    def test_empty_and_physical_venues_produce_nothing(self):
        for loc in ('', None, 'Brooklyn Public Library', 'Prospect Park',
                    'Columbia University', 'The LGBT Community Center'):
            self.assertEqual(virtual_tags_for_location(loc), [], loc)

    def test_bare_zoom_is_detected(self):
        # Regression: the previous keyword list was virtual/online/livestream
        # only, so a location_name of exactly "Zoom" produced no tag at all.
        self.assertEqual(virtual_tags_for_location('Zoom'), ['Virtual', 'Zoom'])
        self.assertEqual(virtual_tags_for_location('Via Zoom Platform'), ['Virtual', 'Zoom'])
        self.assertEqual(virtual_tags_for_location('Zoom (from your home)'), ['Virtual', 'Zoom'])

    def test_platform_leaves(self):
        self.assertEqual(virtual_tags_for_location('Zoom Webinar'), ['Virtual', 'Zoom'])
        self.assertEqual(virtual_tags_for_location('Virtual Webinar'), ['Virtual', 'Webinar'])
        self.assertEqual(virtual_tags_for_location('Online Streaming, New York'),
                         ['Virtual', 'Live Stream'])
        self.assertEqual(virtual_tags_for_location('Online (Microsoft Teams)'),
                         ['Virtual', 'Online'])
        self.assertEqual(virtual_tags_for_location('Google Meet'), ['Virtual', 'Online'])

    def test_root_only_when_no_platform_named(self):
        self.assertEqual(virtual_tags_for_location('Virtual'), ['Virtual'])
        self.assertEqual(virtual_tags_for_location('Virtual Event'), ['Virtual'])
        self.assertEqual(virtual_tags_for_location('Virtual Workshop'), ['Virtual'])

    def test_hybrids_still_get_virtual(self):
        # Hybrids happen in person AND stream; `Virtual` is a delivery filter,
        # not a claim of exclusivity, so they legitimately carry it.
        self.assertEqual(virtual_tags_for_location('Online & In-Person'), ['Virtual', 'Online'])
        self.assertEqual(virtual_tags_for_location('Mary Chapel (IN PERSON) / Zoom'),
                         ['Virtual', 'Zoom'])

    def test_zoom_room_gyms_are_not_virtual(self):
        # "Zoom Room" is a physical dog-training franchise, not the platform.
        self.assertEqual(virtual_tags_for_location('Zoom Room Dog Training'), [])

    def test_virtual_root_always_leads(self):
        # Ancestor invariant: a leaf is never emitted without its root, because
        # filtering is a flat set intersection on event_tags.
        for loc in ('Zoom', 'Virtual Webinar', 'Online', 'Online Streaming',
                    'Virtual Tour of the Met'):
            tags = virtual_tags_for_location(loc)
            self.assertTrue(tags and tags[0] == 'Virtual', loc)


if __name__ == "__main__":
    unittest.main()
