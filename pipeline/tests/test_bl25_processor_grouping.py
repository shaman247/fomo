"""BL25 (a) processor grouping changes (2026-10-24).

A1 — w2439 "Animation Fundamentals" (cr 134373): the gcal feed lists the bare
course name without a URL; the containment branch let it absorb every URL-less
"…II" date and then the "…I" row's URL (14 rows -> 2 groups, II's dates on I).
A trailing sequence marker (Roman I–X, a 1–2 digit number, Part / Level /
Book / Session N) after the full shorter title now refuses containment.

A2 — w536 Pratt "GCPE Graduate Admissions Information Session" (cr 134005):
an in-person listing and an Online listing with different URLs fused in the
exact-name branch. In the MIXED branch (one side unresolved) the pair now
splits when the URLs differ and exactly one side is a delivery-only label.
A same-id pair (both fell back to the organizer pin) is left alone: that is
the shape of one venue's per-date series with alternating delivery.

Run: ./venv/bin/python pipeline/tests/test_bl25_processor_grouping.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import (group_event_occurrences, _trailing_sequence_marker_only,
                       _delivery_only_location)

DRAW = 5278
CORS = 'https://draw.corsizio.com/event/'


def _row(name, loc, loc_id, url, date, start='6pm', end='9pm'):
    return {'name': name, 'location': loc, 'location_id': loc_id, 'url': url,
            'start_date': date, 'start_time': start, 'end_date': '', 'end_time': end}


II_DATES = ['2026-11-02', '2026-11-09', '2026-11-16', '2026-11-23', '2026-11-30', '2026-12-07']


class TestAnimationFundamentals(unittest.TestCase):

    def rows(self):
        rows = [_row('Animation Fundamentals', '', DRAW, '', '2026-10-26')]
        rows += [_row('Animation Fundamentals II', '', DRAW, '', d) for d in II_DATES]
        rows.append(_row('Animation Fundamentals I', 'The DRAW Studio', DRAW,
                         CORS + '6a3187c6138765a4237765d3', '2026-10-26'))
        rows += [_row('Animation Fundamentals II', 'The DRAW Studio', DRAW,
                      CORS + '6a3188f6138765a423780346', d) for d in II_DATES]
        return rows

    def test_w2439_shape_three_groups(self):
        events = group_event_occurrences(self.rows(), 'https://www.thedrawstudio.org/')
        by_name = {e['name']: e for e in events}
        self.assertEqual(sorted(by_name), ['Animation Fundamentals', 'Animation Fundamentals I',
                                           'Animation Fundamentals II'])
        self.assertEqual([o[0] for o in by_name['Animation Fundamentals']['occurrences']],
                         ['2026-10-26'])
        self.assertEqual([o[0] for o in by_name['Animation Fundamentals I']['occurrences']],
                         ['2026-10-26'])
        self.assertEqual(sorted(o[0] for o in by_name['Animation Fundamentals II']['occurrences']),
                         II_DATES)
        self.assertIn(CORS + '6a3188f6138765a423780346', by_name['Animation Fundamentals II']['urls'])
        self.assertNotIn(CORS + '6a3187c6138765a4237765d3',
                         by_name['Animation Fundamentals']['urls'])

    def test_marker_shapes(self):
        for long in ('Animation Fundamentals II', 'Animation Fundamentals I',
                     'Pilates 2', 'Figure Drawing: Part 3', 'Ballet (Level 1)',
                     'Book Club Book IV', 'Ceramics Session 2', 'Watercolor Part Two'):
            short = {'Pilates 2': 'Pilates', 'Figure Drawing: Part 3': 'Figure Drawing',
                     'Ballet (Level 1)': 'Ballet', 'Book Club Book IV': 'Book Club',
                     'Ceramics Session 2': 'Ceramics',
                     'Watercolor Part Two': 'Watercolor'}.get(long, 'Animation Fundamentals')
            self.assertTrue(_trailing_sequence_marker_only(short, long), long)
            self.assertTrue(_trailing_sequence_marker_only(long, short), long)

    def test_not_markers(self):
        pairs = [('Halloween Party', 'Halloween Party 2026'),     # a year
                 ('Album Night', 'Album Night Vol. 2'),            # not in the spec list
                 ('Jazz Jam', 'Jazz Jam with Ari'),
                 ('Dance Party', 'Dance Party x'),                 # lowercase x
                 ('Open Studio', 'Open Studio'),
                 ('Storytime', 'Toddler Storytime 2'),             # prefix, not tail
                 ('Ballet', 'Ballet Level Up')]
        for a, b in pairs:
            self.assertFalse(_trailing_sequence_marker_only(a, b), (a, b))

    def test_url_less_series_still_collapses(self):
        rows = [_row('Life Drawing', 'Studio', DRAW, '', d) for d in II_DATES[:3]]
        rows.append(_row('Life Drawing Open Session', 'Studio', DRAW, '', '2026-12-14'))
        events = group_event_occurrences(rows, 'https://example.org/')
        self.assertEqual(len(events), 1)


PRATT = 1786
HIGGINS = 12185
P = 'https://www.pratt.edu/events/'


class TestPrattGcpe(unittest.TestCase):

    def rows(self, higgins_id, online_id):
        return [
            _row('GCPE Graduate Admissions Information Session', 'Higgins Hall', higgins_id,
                 P + 'gcpe-graduate-admissions-information-session-2/', '2026-10-24', '12pm', '2pm'),
            _row('GCPE Graduate Admissions Information Session', 'Online', online_id,
                 P + 'gcpe-graduate-admissions-information-session/', '2026-11-17', '6pm', '8pm'),
        ]

    def check_split(self, rows):
        events = group_event_occurrences(rows, 'https://www.pratt.edu/events/',
                                         location_refs={PRATT: ['Pratt Institute (Brooklyn campus)']})
        self.assertEqual(len(events), 2)
        by_loc = {e['location']: e for e in events}
        self.assertEqual([o[0] for o in by_loc['Higgins Hall']['occurrences']], ['2026-10-24'])
        self.assertEqual([o[0] for o in by_loc['Online']['occurrences']], ['2026-11-17'])

    def test_two_resolved_venues(self):
        # Since loc 12185 (Higgins Hall) exists, the ids differ.
        self.check_split(self.rows(HIGGINS, PRATT))

    def test_same_id_shape_is_out_of_scope(self):
        # cr 134005 as processed on 10-20: both rows fell back to loc 1786.
        # A same-id pair reads as one venue's per-date series (Riverside
        # Church alternates Online / in-person dates), so A2 leaves it.
        events = group_event_occurrences(self.rows(PRATT, PRATT), 'https://www.pratt.edu/events/')
        self.assertEqual(len(events), 1)

    def test_mixed_shape(self):
        self.check_split(self.rows(PRATT, None))
        self.check_split(list(reversed(self.rows(PRATT, None))))

    def test_same_url_keeps_grouping(self):
        rows = self.rows(PRATT, PRATT)
        rows[1]['url'] = rows[0]['url']
        events = group_event_occurrences(rows, 'https://www.pratt.edu/events/')
        self.assertEqual(len(events), 1)

    def test_room_label_mixed_still_groups(self):
        # nyc.gov "Play Area" per-date URLs: not a delivery label.
        rows = [_row('Kids in Motion', 'Bloomingdale Playground', 7000,
                     'https://www.nyc.gov/e?id=1', '2026-11-01'),
                _row('Kids in Motion', 'Play Area', None,
                     'https://www.nyc.gov/e?id=2', '2026-11-08')]
        events = group_event_occurrences(rows, 'https://www.nyc.gov',
                                         location_refs={7000: ['Bloomingdale Playground']})
        self.assertEqual(len(events), 1)

    def test_both_online_still_group(self):
        rows = [_row('Webinar Series', 'Zoom', None, 'https://x.org/e/1', '2026-11-01'),
                _row('Webinar Series', 'Online', None, 'https://x.org/e/2', '2026-11-08')]
        # Two different bare names: incompatible by name already; same name groups.
        rows[1]['location'] = 'Zoom'
        self.assertEqual(len(group_event_occurrences(rows, 'https://x.org/')), 1)

    def test_two_delivery_labels_still_group(self):
        # NYC Parks cr 132379: "Online" (unresolved) vs "Virtual/Online
        # Events" (resolved loc 2211) on per-date URLs is one virtual class.
        rows = [_row('Virtual Zumba', 'Virtual/Online Events', 2211,
                     'https://www.nycgovparks.org/events/2026/10/15/virtual-zumba', '2026-10-15'),
                _row('Virtual Zumba', 'Online', None,
                     'https://www.nycgovparks.org/events/2026/10/22/virtual-zumba', '2026-10-22')]
        events = group_event_occurrences(rows, 'https://www.nycgovparks.org/',
                                         location_refs={2211: ['Virtual/Online Events']})
        self.assertEqual(len(events), 1)

    def test_delivery_only_labels(self):
        for loc in ('Online', 'Zoom', 'Online Event', 'Virtual', 'Livestream',
                    'Online via Zoom', 'Microsoft Teams', 'Virtual Event (Zoom)',
                    'Virtual/Online Events'):
            self.assertTrue(_delivery_only_location(loc), loc)
        for loc in ('Higgins Hall', 'Online and Pratt Manhattan on 14th Street',
                    'Zoom Room Astoria', 'Virtual Tour of the Met', '', 'Mary Chapel / Zoom'):
            self.assertFalse(_delivery_only_location(loc), loc)


if __name__ == '__main__':
    unittest.main()
