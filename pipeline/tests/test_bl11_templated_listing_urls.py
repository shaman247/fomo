"""BL11: a date-templated crawl URL is a listing in its resolved form too.

`source_url_listing_set` demoted a URL only when it equalled a `website_urls`
row. A templated row (`start={{date}}&end={{date+90}}`) never equals what the
crawler fetched, so the raw feed endpoint survived as an event's popup link:
1,092 live rows on 583 events on 2026-10-12 (AMC day pages, Brooklyn Bridge
Park's admin-ajax feed, CUNY GC's date filter, monthly library calendars).
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger

BBP = ('https://brooklynbridgepark.org/wp-admin/admin-ajax.php'
       '?action=get_calendar_events&start={{date}}&end={{date+90}}')
BBP_RESOLVED = ('https://brooklynbridgepark.org/wp-admin/admin-ajax.php'
                '?action=get_calendar_events&start=2026-09-24&end=2026-12-23')
AMC = 'https://www.amctheatres.com/movie-theatres/new-york-city/amc-empire-25/showtimes?date={{date+3}}'
PUZZLE = 'https://puzzledpint.org/events/{{month}}-{{year}}/'
LIBRARY = 'https://carmellibrary.assabetinteractive.com/calendar/{{year}}-{{month}}/'
QPL = 'https://www.queenslibrary.org/search?d={{mdy}}&e={{mdy+30}}'


class ListingUrlSetTests(unittest.TestCase):

    def setUp(self):
        self.listing = merger.ListingUrlSet([BBP, AMC, PUZZLE, LIBRARY, QPL,
                                             'https://brooklynbridgepark.org/events/'])

    def test_resolved_templates_are_listings(self):
        for url in (BBP_RESOLVED,
                    BBP_RESOLVED.replace('&', '&amp;'),
                    'https://www.amctheatres.com/movie-theatres/new-york-city/amc-empire-25/showtimes?date=2026-09-30',
                    'https://puzzledpint.org/events/november-2026/',
                    'https://carmellibrary.assabetinteractive.com/calendar/2026-october/',
                    'https://www.queenslibrary.org/search?d=10%2F12%2F26&e=11%2F11%2F26'):
            with self.subTest(url=url):
                self.assertIn(url, self.listing)

    def test_exact_rows_still_match(self):
        self.assertIn('https://brooklynbridgepark.org/events', self.listing)

    def test_event_pages_are_not_listings(self):
        for url in ('https://brooklynbridgepark.org/events/movies-with-a-view',
                    'https://puzzledpint.org/events/trivia-2026/',
                    'https://www.amctheatres.com/movies/the-dream-12345',
                    'https://www.amctheatres.com/movie-theatres/new-york-city/amc-empire-25/showtimes?date=2026-09-30&movie=x'):
            with self.subTest(url=url):
                self.assertNotIn(url, self.listing)

    def test_untemplated_rows_build_no_pattern(self):
        self.assertIsNone(merger.listing_template_regex('https://ra.co/events/us/newyorkcity'))

    def test_source_url_listing_set_is_template_aware(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [(BBP,)]
        self.assertIn(BBP_RESOLVED, merger.source_url_listing_set(cursor, {}, 162))

    def test_grouped_urls_skip_the_resolved_feed(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        raw = {'urls': [BBP_RESOLVED, 'https://brooklynbridgepark.org/events/movies-with-a-view']}
        merger._merge_grouped_event_urls(cursor, 1, raw, merger.ListingUrlSet([BBP]))
        inserted = [c.args[1][1] for c in cursor.execute.call_args_list
                    if c.args[0].startswith('INSERT INTO event_urls')]
        self.assertEqual(inserted, ['https://brooklynbridgepark.org/events/movies-with-a-view'])


if __name__ == '__main__':
    unittest.main()
