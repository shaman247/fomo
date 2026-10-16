"""BL26 tail (2026-10-16): find_review_candidates #13 cinema exemption and the
narrowed #42 library meeting-room title gate.

Names are real reviewed rows (see the #42 comment for the measurement). The
title-gate tests compile the pattern's own alternations in Python; the query
tests run the real SQL on connection-local TEMPORARY tables that shadow the
production names (FOMO_TEST_TEMP_DB=1), so no production row is read or changed.
"""
import os
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'pipeline'))
sys.path.insert(0, str(ROOT / 'scripts'))
import find_review_candidates as frc


def pattern(pid):
    return next(p for p in frc.PATTERNS if p['id'] == pid)


def title_flagged(name):
    """Python mirror of #42's two name clauses (MariaDB REGEXP is case-insensitive)."""
    program = re.compile(rf"\b({frc.ROOM_BOOKING_PROGRAM_WORDS})\b|[:|]|{frc.ROOM_BOOKING_PUBLIC_MEETING}",
                         re.I)
    org = re.compile(rf"\b({frc.ROOM_BOOKING_ORG_WORDS})\b", re.I)
    return not program.search(name) and bool(org.search(name) or not re.search(r'\s', name))


class RoomBookingTitleGateTests(unittest.TestCase):

    def test_outside_org_bookings_are_flagged(self):
        for name in ('TAB Meeting', 'TAB', 'Hafa Event', 'National Charity League NJ Bergen Blazers',
                     "Woman's Club Meeting - Art", 'Woman’s Club', 'Rotary District #7255',
                     'White Plains Beautification Foundation', 'Bergenfield School District BECAC',
                     'WOPL Friends Board Meeting', 'Haworth Tennis Committee', 'Farmingdale Quilters'):
            with self.subTest(name=name):
                self.assertTrue(title_flagged(name))

    def test_kept_library_programs_are_not_flagged(self):
        # Hobby clubs, book groups, municipal commissions and the library's own
        # board meeting were kept by reviewers.
        for name in ('Cookbook Club', 'Fiber Arts Club', 'Adult Crafting Club', 'History Club',
                     'Suffolk County Zine Club (In Person)', "Mayor's Wellness Book Group",
                     'USR Historical Preservation Commission', 'Green team & Environmental Commission',
                     'Library Board Meeting', 'Board Meeting',
                     'Friends of Sachem Library Monthly Meeting', 'Toddler Storytime'):
            with self.subTest(name=name):
                self.assertFalse(title_flagged(name))

    def test_query_uses_the_shared_alternations(self):
        query = pattern(42)['query']
        self.assertNotIn('__PROGRAM__', query)
        self.assertIn(frc.ROOM_BOOKING_ORG_WORDS, query)
        self.assertIn(frc.ROOM_BOOKING_PROGRAM_WORDS, query)


class HighOccurrenceCinemaExemptionTests(unittest.TestCase):

    def test_exemption_is_part_of_pattern_13(self):
        query = pattern(13)['query']
        self.assertIn('AND NOT ' + frc._CINEMA_SCREENING_SQL, query)
        self.assertIn("t.name = 'Cinema' AND t.scope = 'venue'", query)


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1',
                     'Opt in to connection-local MariaDB tests with FOMO_TEST_TEMP_DB=1')
class PatternQueryTests(unittest.TestCase):
    SCHEMAS = {
        'events': ("id INT PRIMARY KEY, name VARCHAR(500), description TEXT, website_id INT, "
                   "location_id INT, event_type VARCHAR(64), archived INT DEFAULT 0, "
                   "reviewed INT DEFAULT 0, suppressed INT DEFAULT 0"),
        'websites': 'id INT PRIMARY KEY, name VARCHAR(255)',
        'event_occurrences': 'id INT AUTO_INCREMENT PRIMARY KEY, event_id INT, start_date DATE',
        'location_tags': 'location_id INT, tag_id INT',
        'tags': "id INT PRIMARY KEY, name VARCHAR(100), scope VARCHAR(10)",
    }

    def setUp(self):
        from db import create_connection
        self.conn = create_connection()
        self.assertIsNotNone(self.conn)
        self.addCleanup(self.conn.close)
        self.cur = self.conn.cursor()
        for table, schema in self.SCHEMAS.items():
            self.cur.execute(f'CREATE TEMPORARY TABLE {table} ({schema})')
        # Refuse to insert anything unless every name is shadowed by an empty temp table.
        for table in self.SCHEMAS:
            self.cur.execute(f'SELECT COUNT(*) FROM {table}')
            self.assertEqual(self.cur.fetchone()[0], 0, table)

    def add(self, eid, name, website_id, location_id=None, event_type=None, dates=1,
            description='No description available.'):
        self.cur.execute('INSERT INTO events (id,name,description,website_id,location_id,event_type) '
                         'VALUES (%s,%s,%s,%s,%s,%s)',
                         (eid, name, description, website_id, location_id, event_type))
        for i in range(dates):
            self.cur.execute('INSERT INTO event_occurrences (event_id,start_date) '
                             'VALUES (%s, DATE_ADD(%s, INTERVAL %s DAY))', (eid, '2026-10-20', i))

    def run_pattern(self, pid):
        return frc.run_pattern(self.cur, pattern(pid))

    def test_pattern_13_skips_screenings_at_a_cinema_only(self):
        self.cur.execute("INSERT INTO websites VALUES (1,'Regal Union Square'),(2,'Brooklyn Academy of Music')")
        self.cur.execute("INSERT INTO tags VALUES (5,'Cinema','venue'),(6,'Cinema','event')")
        self.cur.execute('INSERT INTO location_tags VALUES (10,5),(20,6)')
        self.add(1, 'Primetime', 1, 10, 'Screening', dates=31)              # multiplex run
        self.add(2, 'Private Theatre Rental', 1, 10, None, dates=31)        # cinema, not a screening
        self.add(3, 'Retrospective', 2, 20, 'Screening', dates=31)          # event-scope tag only
        self.add(4, 'Cooking Class', 2, None, 'Workshop', dates=31)
        self.assertEqual(self.run_pattern(13), {2, 3, 4})

    def test_pattern_42_on_library_calendar(self):
        self.cur.execute("INSERT INTO websites VALUES (1,'East Meadow Public Library'),(2,'BCCLS Libraries')")
        self.add(1, 'TAB Meeting', 1)
        self.add(2, 'Cookbook Club', 2)
        self.add(3, 'Library Board Meeting', 2)
        self.add(4, 'National Charity League NJ Bergen Blazers', 2)
        self.add(5, 'Hafa Event', 2, dates=2)                                 # repeats: a program
        self.add(6, 'Rotary Club', 2, description='Rotary meets to plan the fall coat drive.')
        self.assertEqual(self.run_pattern(42), {1, 4})


if __name__ == '__main__':
    unittest.main()
