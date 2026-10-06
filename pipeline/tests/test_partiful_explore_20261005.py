"""Partiful explore plugin: venue + address + local times come from __NEXT_DATA__.

Regression for 2026-10-04: the browser crawl of partiful.com/discover/NYC rendered only
"Sat, Oct 17 at 1pm · New York", so events reached the extractor with a bare city as their
venue and went unmapped, although the page's __NEXT_DATA__ carried the venue and address.
"""
import json
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from sources import partiful
except ImportError:  # deployment-specific plugin (gitignored) absent
    partiful = None


def _ev(id_, title, start, end=None, tz='America/New_York', loc=None, **kw):
    ev = {'id': id_, 'title': title, 'description': kw.pop('description', 'desc'),
          'startDate': start, 'endDate': end, 'timezone': tz, 'status': 'PUBLISHED',
          'isPublic': True,
          'locationInfo': loc or {
              'type': 'structured',
              'mapsInfo': {'name': 'Sounds of Brazil',
                           'addressLines': ['204 Varick St', 'New York, NY 10014']},
              'displayAddressLines': ['204 Varick St', 'New York, NY'],
              'neighborhood': 'SoHo'}}
    ev.update(kw)
    return ev


def _html(page_props):
    data = {'props': {'pageProps': page_props}}
    return ('<html><script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(data) + '</script></html>')


@unittest.skipIf(partiful is None, 'partiful plugin not installed')
class PartifulExploreTest(unittest.TestCase):
    def test_parse_collects_all_sections_once(self):
        a = _ev('A', 'Alpha', '2026-10-10T03:00:00.000Z')
        b = _ev('B', 'Beta', '2026-10-11T20:00:00.000Z')
        html = _html({'trendingSection': {'items': [{'event': a}]},
                      'sections': [{'items': [{'event': a}, {'event': b}]}],
                      'feedItems': [{'type': 'event', 'event': b}]})
        self.assertEqual([e['id'] for e in partiful.parse_explore_html(html)], ['A', 'B'])

    def test_parse_without_next_data_raises(self):
        with self.assertRaises(ValueError):
            partiful.parse_explore_html('<html>challenge</html>')

    def test_card_carries_venue_address_and_local_time(self):
        md = '\n'.join(partiful.build_card(
            _ev('gAw', '2000s r&b + bollywood party', '2026-10-10T03:00:00.000Z',
                '2026-10-10T06:00:00.000Z')))
        self.assertIn('**Where**: Sounds of Brazil, 204 Varick St, New York, NY 10014', md)
        self.assertIn('**Neighborhood**: SoHo', md)
        # 03:00Z is 11 PM the previous evening in New York; end is the overnight 2 AM.
        self.assertIn('**Starts**: Fri, Oct 9, 2026 at 11:00 PM', md)
        self.assertIn('**Ends**: Sat, Oct 10, 2026 at 2:00 AM', md)
        self.assertIn('EVENT DETAIL URL: https://partiful.com/e/gAw?source=discover', md)

    def test_wall_time_follows_event_timezone(self):
        # Partiful shows the host's chosen zone; the description agrees ("10:00 AM meet").
        md = '\n'.join(partiful.build_card(
            _ev('L', 'Llama trek', '2026-11-15T09:00:00.000Z', tz='Europe/Paris')))
        self.assertIn('**Starts**: Sun, Nov 15, 2026 at 10:00 AM', md)

    def test_where_variants(self):
        w = partiful._where
        self.assertEqual(w({'type': 'freeform', 'value': 'secret location'}), 'secret location')
        self.assertEqual(w({'type': 'structured', 'mapsInfo': {
            'addressLines': ['558 Kosciuszko St', 'Brooklyn, NY 11221']}}),
            '558 Kosciuszko St, Brooklyn, NY 11221')
        self.assertEqual(w({'type': 'structured', 'mapsInfo': {
            'name': 'Greenwich Village',
            'addressLines': ['Greenwich Village', 'Manhattan, New York, NY']}}),
            'Greenwich Village, Manhattan, New York, NY')
        self.assertEqual(w({'type': 'structured', 'mapsInfo': {
            'name': 'Focal Point',
            'addressLines': ['43-50 12th St', 'Long Island City,', 'Queens, NY 11101']}}),
            'Focal Point, 43-50 12th St, Long Island City, Queens, NY 11101')

    def test_bracketed_title_is_a_plain_heading(self):
        md = '\n'.join(partiful.build_card(
            _ev('T', 'rooftop art salon: [the] p[art]y', '2026-10-10T21:00:00.000Z')))
        self.assertTrue(md.startswith('### rooftop art salon: [the] p[art]y\n'))

    def test_markdown_drops_finished_and_private_events(self):
        now = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
        evs = [_ev('old', 'Old', '2026-10-01T23:00:00.000Z'),
               _ev('priv', 'Private', '2026-10-09T23:00:00.000Z', isPublic=False),
               _ev('run', 'Month Offline', '2026-09-20T22:30:00.000Z', '2026-11-06T00:00:00.000Z'),
               _ev('new', 'New', '2026-10-09T23:00:00.000Z')]
        md, n = partiful.build_markdown(evs, 'NYC', now=now)
        self.assertEqual(n, 2)
        self.assertIn('### Month Offline', md)
        self.assertNotIn('### Old', md)
        self.assertNotIn('### Private', md)

    def test_profile_scoped_to_discover_listing(self):
        p = partiful.PROFILE
        self.assertTrue(p.matches('https://partiful.com/discover/NYC'))
        self.assertFalse(p.matches('https://partiful.com/e/gAwIeQfpJrO2lKI2kB6R?source=discover'))
        self.assertEqual(partiful._region('https://partiful.com/discover/NYC'), 'NYC')


if __name__ == '__main__':
    unittest.main()
