"""BL43 producer fix (2026-10-23): a "<venue>, <street address>" session that
did not resolve must not fuse into a same-titled session at a resolved venue.

BCCLS w3530 "Novels at Night" (cr 135010): the extraction obeyed the SESSION
VENUES rule and emitted two records with separate libcal URLs, one at "Upper
Saddle River Public Library" (resolved) and one at "Bonefish Grill, 601 From
Road" (unresolved). `group_event_occurrences` fused them, because
`_venue_shaped_mismatch` read the street tail as an address of the library and
the exact-name MIXED branch skips the URL check. The comma head ("Bonefish
Grill") is now judged on its own; the whole string must still share nothing
with the resolved venue.

Run: ./venv/bin/python pipeline/tests/test_bl43_mixed_session_grouping.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import group_event_occurrences, _venue_shaped_mismatch

USR = 5555
USR_REFS = {USR: ['Upper Saddle River Public Library',
                  '245 Lake St, Upper Saddle River, NJ 07458']}
SRC = 'https://bccls.libcal.com/calendar'


def _row(name, loc, loc_id, url, date):
    return {'name': name, 'location': loc, 'location_id': loc_id, 'url': url,
            'start_date': date, 'start_time': '7:00 PM',
            'end_date': '', 'end_time': '8:00 PM'}


class TestNovelsAtNight(unittest.TestCase):

    def test_two_session_venues_stay_two_groups(self):
        rows = [
            _row('Novels at Night', 'Upper Saddle River Public Library', USR,
                 'https://bccls.libcal.com/event/17161059', '2026-11-05'),
            _row('Novels at Night', 'Bonefish Grill, 601 From Road', None,
                 'https://bccls.libcal.com/event/17197435', '2026-11-12'),
        ]
        events = group_event_occurrences(rows, SRC, location_refs=USR_REFS)
        self.assertEqual(len(events), 2)
        by_loc = {e['location']: e for e in events}
        self.assertEqual([o[0] for o in by_loc['Bonefish Grill, 601 From Road']['occurrences']],
                         ['2026-11-12'])
        self.assertEqual([o[0] for o in by_loc['Upper Saddle River Public Library']['occurrences']],
                         ['2026-11-05'])

    def test_comma_head_is_judged(self):
        refs = USR_REFS[USR]
        self.assertTrue(_venue_shaped_mismatch('Bonefish Grill, 601 From Road', refs,
                                               judge_comma_head=True))
        self.assertTrue(_venue_shaped_mismatch('Bonefish Grill', refs))
        # Only the different-URL check judges the head; plain compatibility
        # keeps the street exemption.
        self.assertFalse(_venue_shaped_mismatch('Bonefish Grill, 601 From Road', refs))

    def test_other_nyc_gov_session_venue(self):
        # cr 120054: the Oct 3 Nostrand Playground session (own sequence URL)
        # was fused into the unresolved Farah Louis office row.
        base = 'https://www.nyc.gov/main/events/?permalinkName=hpd-cd45&id=951676&sequence='
        rows = [
            _row('HPD in Your District - Council District 45',
                 'Council Member Farah Louis office, 1434 Flatbush Avenue, Brooklyn',
                 None, base + '3', '2026-09-10'),
            _row('HPD in Your District - Council District 45',
                 'Nostrand Playground, 3002 Foster Avenue, Brooklyn', 7294,
                 base + '5', '2026-10-03'),
        ]
        events = group_event_occurrences(
            rows, 'https://www.nyc.gov', location_refs={7294: ['Nostrand Playground']})
        self.assertEqual(len(events), 2)


class TestStillGroups(unittest.TestCase):
    """Shapes the street exemption exists for keep grouping."""

    def test_own_address_written_out(self):
        refs = USR_REFS[USR]
        for text in ('245 Lake Street, Upper Saddle River',
                     'Upper Saddle River Public Library, 245 Lake Street',
                     'Community Room, 245 Lake Street',
                     'Upper Saddle River, 245 Lake Street'):
            with self.subTest(text=text):
                self.assertFalse(_venue_shaped_mismatch(text, refs))

    def test_street_head_sharing_the_area(self):
        # nyc.gov cr 129764: the same Oct 17 recycling event under two URL
        # forms, one resolved, one "Alameda Ave, Little Neck".
        rows = [
            _row('Community Recycling Event - Little Neck',
                 'Alameda Ave, Little Neck', None,
                 'https://www.nyc.gov/main/events/?permalinkName=x&id=1290756', '2026-10-17'),
            _row('Community Recycling Event - Little Neck',
                 'Little Neck church parking lot', 11576,
                 'https://www1.nyc.gov/site/dsny/events/x/1290756/1', '2026-10-17'),
        ]
        events = group_event_occurrences(
            rows, 'https://www.nyc.gov', location_refs={11576: ['Little Neck church parking lot']})
        self.assertEqual(len(events), 1)

    def test_same_url_duplicate_with_room_address(self):
        # cr 119538: one Hunter listing extracted twice, once as "Hunter
        # College", once as its gallery's address. One URL, one event.
        url = 'https://www.hunter.cuny.edu/event/humanities-action-lab/'
        rows = [
            _row('Humanities Action Lab', 'Hunter College', 77, url, '2026-10-07'),
            _row('Humanities Action Lab',
                 'Bertha and Karl Leubsdorf Gallery, 132 East 68th St, New York',
                 None, url, '2026-10-07'),
        ]
        events = group_event_occurrences(
            rows, 'https://www.hunter.cuny.edu', location_refs={77: ['Hunter College']})
        self.assertEqual(len(events), 1)

    def test_entrance_without_comma(self):
        self.assertFalse(_venue_shaped_mismatch(
            'Entrance—Parkside & Ocean Avenues', ['Prospect Park']))

    def test_same_url_room_with_address(self):
        # A room of the resolved venue plus its address, same permalink.
        url = 'https://bccls.libcal.com/event/1'
        rows = [
            _row('Book Club', 'Upper Saddle River Public Library', USR, url, '2026-11-05'),
            _row('Book Club', 'Meeting Room, 245 Lake St', None, url, '2026-11-12'),
        ]
        events = group_event_occurrences(rows, SRC, location_refs=USR_REFS)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0]['occurrences']), 2)


if __name__ == '__main__':
    unittest.main()
