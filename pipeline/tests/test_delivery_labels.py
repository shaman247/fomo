"""Mapped online programs keep attendance labels without inferring transitions."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from delivery import canonical_location_label
from source_metadata import plan_source_metadata_refresh


class DeliveryLabelTests(unittest.TestCase):
    def test_new_online_and_hybrid_labels_survive_physical_pin(self):
        for source in ('Online (Zoom)', 'Virtual Webinar', 'Online & In-Person',
                       'Mary Chapel (IN PERSON) / Zoom'):
            self.assertEqual(canonical_location_label(source, 'Organizer Center'), source)

    def test_normal_venue_spelling_and_zoom_room_are_unchanged(self):
        self.assertEqual(canonical_location_label('Branch A, NYC', 'Branch A'), 'Branch A')
        self.assertEqual(canonical_location_label('Zoom Room Dog Training', 'Zoom Room'), 'Zoom Room')
        self.assertEqual(canonical_location_label('Online (Zoom)', None), 'Online (Zoom)')
        self.assertEqual(canonical_location_label(None, 'Branch A'), 'Branch A')

    def setUp(self):
        self.old = dict(id=20, website_id=10, location_id=5, location_name='School',
                        crawled_at='2026-09-20 10:00:00', raw_data='{}')
        self.event = dict(id=1, website_id=10, location_id=5, location_name='School',
                          reviewed=0, suppressed=0)
        self.new = dict(self.old, id=21, crawled_at='2026-09-23 10:00:00',
                        location_name='Online (Zoom)')
        self.sources = [self.old]
        self.slots = [dict(start_date='2026-10-01', start_time='6pm', end_date=None)]

    def plan(self, incoming_slots=None):
        return plan_source_metadata_refresh(self.event, self.new, self.sources,
                                            self.slots, self.slots if incoming_slots is None else incoming_slots,
                                            today=date(2026, 9, 23))

    def test_fresh_same_publisher_restores_source_owned_label(self):
        self.assertEqual(self.plan(), {'location_name': 'Online (Zoom)'})

    def test_reviewed_or_manual_labels_are_preserved(self):
        self.event['reviewed'] = 1
        self.assertEqual(self.plan(), {})
        self.event.update(reviewed=0, location_name='Editorial meeting place')
        self.assertEqual(self.plan(), {})

    def test_missing_online_label_does_not_imply_in_person(self):
        self.event['location_name'] = self.old['location_name'] = 'Online (Zoom)'
        self.new['location_name'] = 'School'
        self.assertEqual(self.plan(), {})

    def test_existing_hybrid_details_are_not_replaced_by_online_only(self):
        self.event['location_name'] = self.old['location_name'] = 'School / Zoom'
        self.assertEqual(self.plan(), {})

    def test_other_publishers_and_partial_series_cannot_override(self):
        self.sources.append(dict(self.old, id=30, website_id=99))
        self.assertEqual(self.plan(), {})
        self.sources.pop()
        self.assertEqual(self.plan([]), {})

    def test_same_timestamp_or_grouped_history_does_not_override(self):
        self.new['crawled_at'] = self.old['crawled_at']
        self.assertEqual(self.plan(), {})
        self.new['crawled_at'] = '2026-09-23 10:00:00'
        self.old['raw_data'] = '{"session_details":[{},{}]}'
        self.assertEqual(self.plan(), {})
