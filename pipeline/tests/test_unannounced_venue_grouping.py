"""A known room on one program cannot announce another program's venue."""
import copy
import unittest
from processor import group_event_occurrences

class UnannouncedVenueGroupingTests(unittest.TestCase):
    def rows(self, unknown='Location not specified'):
        first=dict(name='Full Board Meeting',location='Van Alen Institute',location_id=1594,
                   url='https://example.org/meeting-october',start_date='2026-10-14',
                   start_time='6:30pm',end_date='',end_time='8:30pm',tags=['Community'])
        return [first,dict(first,location=unknown,location_id=None,
                          url='https://example.org/meeting-november',start_date='2026-11-11')]
    def test_separate_dated_unknown_venue_in_both_orders(self):
        for label in ('Location not specified','Venue not specified','Unannounced venue','TBA','TBD','To be announced','To be determined'):
            rows=self.rows(label)
            for ordered in (rows,rows[::-1]):
                self.assertEqual(len(group_event_occurrences(copy.deepcopy(ordered))),2)
    def test_same_program_venue_enrichment_still_groups(self):
        rows=self.rows();rows[1]['url']=rows[0]['url']
        self.assertEqual(len(group_event_occurrences(rows)),1)
    def test_room_labels_still_group_with_resolved_venue(self):
        self.assertEqual(len(group_event_occurrences(self.rows('Meeting Room'))),1)
    def test_two_unknown_sessions_can_group(self):
        rows=self.rows();rows[0].update(location='Location not specified',location_id=None)
        self.assertEqual(len(group_event_occurrences(rows)),1)
