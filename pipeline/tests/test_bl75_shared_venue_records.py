"""Records that share a name (and sometimes a URL) but not a venue stay apart (BL75).

Two shapes from the 2026-10-18 / 10-30 runs:

- DOC NYC w652 cr 133321: the listing gave each theatre's screening of a
  two-venue film its own crawl_event under one /film/<slug>/ URL. The detail
  crawl of the description-less row read the film page, whose single location
  is the FIRST theatre and whose dates are both screenings, and rewrote the
  row: 21 of 169 crawl_events stored another theatre and both slots
  (ce1603122 "Union Town": IFC Center 11-15 became SVA Theatre 11-13 + 11-15).
- DSNY w594 cr 137157: every LES Ecology Center site is titled "Community
  Recycling". The first site's street-corner venue did not resolve, and every
  resolved site joined it as a MIXED id-vs-name pair (a street string reads as
  "the venue's door"), so 13 sites became one location-less crawl_event.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import processor
from processor import apply_crawled_details, group_event_occurrences

TAGS = ({}, {}, set(), [])
LES = 'https://www.lesecologycenter.org/calendar/'


def site(location, sub, slug, day, location_id=None):
    row = {'name': 'Community Recycling', 'location': location, 'sublocation': sub,
           'url': LES + slug + '/', 'start_date': day, 'start_time': '10am',
           'end_date': '', 'end_time': '2pm', 'tags': ['Recycling']}
    if location_id:
        row['location_id'] = location_id
    return row


UWS = site('Amsterdam Avenue & W. 109th Street',
           'Amsterdam Avenue between W. 110th & W. 109th Streets',
           'upper-west-side-amsterdam-avenue', '2026-10-31')
QBG = site('Queens Botanical Garden', 'Parking Lot, 42-80 Crommelin Street',
           'flushing-queens-botanical-garden', '2026-11-01', 688)
BUSHWICK = site('Maria Hernandez Park', 'Knickerbocker Avenue & Suydam Street',
                'bushwick-maria-hernandez-park', '2026-11-07', 529)
PARK_SLOPE = site('416 7th Avenue', '7th Avenue between 13th & 14th Streets',
                  'park-slope-2', '2026-12-05')
ADDRESSES = {688: 'Queens Botanical Garden, 43-50 Main St, Flushing, NY 11355, USA',
             529: 'P33G+7F Maria Hernandez Park, Brooklyn, NY 11237, USA'}


def groups(rows, addresses=ADDRESSES):
    events = group_event_occurrences([dict(r) for r in rows], LES,
                                     location_refs={688: [None, None], 529: [None, None]},
                                     location_addresses=addresses)
    return sorted((e.get('location_id') or 0, e['location'],
                   tuple(o[0] for o in e['occurrences'])) for e in events)


class StreetSiteGroupingTests(unittest.TestCase):

    def test_each_site_keeps_its_own_record(self):
        got = groups([UWS, QBG, BUSHWICK, PARK_SLOPE])
        self.assertEqual(len(got), 4, got)
        self.assertIn((0, UWS['location'], ('2026-10-31',)), got)
        self.assertIn((688, 'Queens Botanical Garden', ('2026-11-01',)), got)
        self.assertIn((529, 'Maria Hernandez Park', ('2026-11-07',)), got)

    def test_two_resolved_venues_never_share_a_group(self):
        """Even with no street evidence, a group never holds two resolved ids."""
        got = groups([UWS, QBG, BUSHWICK], addresses={})
        resolved = [g for g in got if g[0]]
        self.assertEqual(len(resolved), 2, got)

    def test_resolved_first_then_street_site(self):
        got = groups([QBG, UWS])
        self.assertEqual(len(got), 2, got)

    def test_a_door_of_the_venue_still_groups(self):
        door = site('Main Street & Crommelin Street', '', 'flushing-queens-botanical-garden-gate',
                    '2026-11-08')
        got = groups([QBG, door])
        self.assertEqual(len(got), 1, got)

    def test_per_date_pages_of_one_series_still_group(self):
        """nyc.gov per-date permalinks share a stem: the date at the park
        entrance is a date of the series, not another site."""
        base = 'https://www.nycgovparks.org/events/2026/11/0{}/stargazing'
        a = dict(QBG, url=base.format(1), sublocation='')
        b = dict(UWS, url=base.format(8), start_date='2026-11-08', sublocation='')
        got = groups([a, b])
        self.assertEqual(len(got), 1, got)

    def test_one_record_under_two_url_shapes_still_groups(self):
        """nyc.gov prints one record as /events/<slug>/<id>/1 and as
        ?permalinkName=<slug>&id=<id>: a shared record id is the same listing."""
        a = dict(QBG, url='https://www.nyc.gov/main/events/?permalinkName=farm-stand&id=1294736&sequence=1')
        b = dict(UWS, url='https://www1.nyc.gov/events/farm-stand/1294736/1', sublocation='')
        self.assertEqual(len(groups([a, b])), 1)

    def test_same_page_rows_still_group(self):
        b = dict(UWS, url=QBG['url'])
        self.assertEqual(len(groups([QBG, b])), 1)


class _SharedPageCursor:
    """apply_crawled_details stub: the row lives at `own`, siblings share its URL."""

    def __init__(self, own, siblings, occurrences=1):
        self.statements = []
        self._own = own                # (location_id, location_name)
        self._siblings = siblings      # [(id, location_id, location_name, date, time)]
        self._occurrences = occurrences
        self._one = None
        self._all = []

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        s = ' '.join(sql.split())
        self._one, self._all = None, []
        if s.startswith('SELECT c.location_id, c.location_name, s.id'):
            self._all = [self._own + sib for sib in self._siblings]
        elif 'ce.location_name' in s:
            self._one = (133321, 652, self._own[1], None, self._own[0], 'Union Town')
        elif s.startswith('SELECT ce.crawl_result_id, cr.website_id'):
            self._one = (133321, 652)
        elif s.startswith('SELECT COUNT(*)'):
            self._one = (self._occurrences,)
        elif s.startswith('SELECT raw_data'):
            self._one = (None,)

    def executemany(self, sql, seq):
        for params in seq:
            self.statements.append((sql, params))

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all


class _Conn:
    def commit(self):
        pass


LOCMAP = {
    'names': {processor._normalize_location_name(n): {'id': i, 'emoji': 'X', 'name': n}
              for n, i in (('SVA Theatre', 1436), ('IFC Center', 407))},
    'alternate_names': {}, 'short_names': {}, 'addresses': {}, 'website_scoped': {},
    'website_linked': {}, 'city_states': {},
}
DETAIL = {'description': 'Screens at SVA Theatre (Nov 13) and IFC Center (Nov 15).',
          'hashtags': [], 'emoji': '', 'location': 'SVA Theatre',
          'occurrences': [{'start_date': '2026-11-13', 'start_time': '6:30pm'},
                          {'start_date': '2026-11-15', 'start_time': '11:45am'}]}


class SharedDetailPageTests(unittest.TestCase):

    def apply(self, siblings):
        cursor = _SharedPageCursor((407, 'IFC Center'), siblings)
        apply_crawled_details(cursor, _Conn(), 1603122, dict(DETAIL), TAGS,
                              locations_map=LOCMAP, event_name='Union Town')
        update = next(s for s in cursor.statements if s[0].startswith('UPDATE crawl_events SET'))
        inserts = [p for sql, p in cursor.statements
                   if sql.startswith('INSERT INTO crawl_event_occurrences')]
        return update, inserts

    def test_union_town_keeps_ifc_and_only_its_own_screening(self):
        update, inserts = self.apply([(1603076, 1436, 'SVA Theatre', '2026-11-13', '6:30pm')])
        self.assertNotIn('location_id = %s', update[0])
        self.assertNotIn('location_name = %s', update[0])
        self.assertEqual([(p[1], p[2]) for p in inserts], [('2026-11-15', '11:45am')])

    def test_without_a_sibling_the_detail_page_still_decides(self):
        update, inserts = self.apply([])
        self.assertIn('location_id = %s', update[0])
        self.assertIn(1436, update[1])
        self.assertEqual(len(inserts), 2)

    def test_a_same_venue_sibling_is_not_another_venue(self):
        _, inserts = self.apply([(1603200, 407, 'IFC Center', '2026-11-13', '6:30pm')])
        self.assertEqual(len(inserts), 2)

    def test_detail_dates_all_belonging_to_siblings_keep_the_listing_rows(self):
        cursor = _SharedPageCursor((407, 'IFC Center'),
                                   [(1603076, 1436, 'SVA Theatre', '2026-11-13', '6:30pm')])
        data = dict(DETAIL, occurrences=[{'start_date': '2026-11-13', 'start_time': '6:30pm'}])
        apply_crawled_details(cursor, _Conn(), 1603122, data, TAGS,
                              locations_map=LOCMAP, event_name='Union Town')
        self.assertFalse([s for s in cursor.statements
                          if s[0].startswith(('DELETE FROM crawl_event_occurrences',
                                              'INSERT INTO crawl_event_occurrences'))])


if __name__ == '__main__':
    unittest.main()
