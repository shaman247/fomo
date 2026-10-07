"""Deployment-specific regressions for reviewed season envelopes."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import site_profiles
try:
    from sources import reviewed_season_envelopes as plugin
except ImportError:
    plugin = None


@unittest.skipIf(plugin is None, 'deployment-specific source plugin not installed')
class ReviewedSeasonEnvelopesTests(unittest.TestCase):
    def ticket(self, **changes):
        basic = dict(id='1987549789925', name='Greenhouse Gang', isSeries=True,
                     isParentEvent=True, endDate={'local': '2026-10-06T20:00:00'})
        basic.update(changes)
        context = dict(basicInfo=basic, display={'nextAvailableSession': '2026-10-06T17:00:00-04:00'})
        return '<script id="__NEXT_DATA__">' + json.dumps({'props': {'pageProps': {'context': context}}}) + '</script>'

    def listing(self):
        return ('<div class="eventlist--upcoming"><article class="eventlist-event">'
                '<a href="/events/2026/4/15/greenhouse-gang">Greenhouse Gang</a>'
                '<div class="eventlist-column-date">May 5 to October 6</div>'
                '<li class="eventlist-meta-date">2026-05-05 — 2026-10-06</li>'
                '<li class="eventlist-meta-export">ICS bogus parent range</li>'
                '<p>Native plants volunteer nursery.</p></article>'
                '<article class="eventlist-event"><a href="/events/other">Other workshop</a>'
                '<p>October 9, 2026 at noon</p></article></div>')

    def test_explicit_ticket_clock_wins_over_ordinal_prose(self):
        self.assertEqual(plugin.greenhouse_session(self.ticket()), {
            'start_date': '2026-10-06', 'start_time': '17:00', 'end_date': '', 'end_time': '20:00'})

    def test_changed_series_identity_and_nonfinal_session_fail_closed(self):
        for changes in (dict(id='different'), dict(isSeries=False),
                        dict(endDate={'local': '2026-10-20T20:00:00'})):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                plugin.greenhouse_session(self.ticket(**changes))

    def test_only_target_envelope_removed_and_other_card_preserved(self):
        body, count = plugin.render_kingsland(self.listing(), plugin.KINGSLAND + '/events-1', self.ticket())
        self.assertEqual(count, 2)
        self.assertNotIn('2026-05-05', body)
        self.assertNotIn('ICS bogus', body)
        self.assertIn('Native plants volunteer nursery.', body)
        self.assertIn('Other workshop', body)
        self.assertIn('October 9, 2026 at noon', body)
        self.assertIn('"start_time": "17:00"', body)

    def test_missing_ticket_fails_instead_of_reemitting_envelope(self):
        with self.assertRaises(ValueError):
            plugin.render_kingsland(self.listing(), plugin.KINGSLAND + '/events-1')

    # Off-season shape observed live 2026-10-07: /events-1 302s to /events, the
    # collection renders only its past list, and ?format=json has upcoming: [].
    OFFSEASON_HTML = ('<div class="sqs-events-collection-list"><!-- Upcoming Events -->'
                      '<!-- Past Events --><div class="eventlist eventlist--past">'
                      '<hr class="eventlist-past-upcoming-divider">'
                      '<article class="eventlist-event eventlist-event--past">'
                      '<a href="/events/2026/9/5/open-hours">Open Hours</a></article></div></div>')

    def feed(self, upcoming=(), **collection):
        coll = dict(typeName='events', type=1, fullUrl='/events')
        coll.update(collection)
        return json.dumps({'collection': coll, 'upcoming': list(upcoming),
                           'past': [{'title': 'Open Hours', 'startDate': 1788631200329}],
                           'pagination': {'nextPage': True}})

    def test_offseason_empty_upcoming_is_zero_event_success(self):
        import extractor
        page = plugin.KINGSLAND + '/events'
        self.assertTrue(plugin.kingsland_upcoming_empty(self.OFFSEASON_HTML, self.feed(), page))
        body, count = plugin.render_kingsland(self.OFFSEASON_HTML, plugin.KINGSLAND + '/events-1',
                                              upcoming_empty=True)
        self.assertEqual(count, 0)
        self.assertNotIn('Open Hours', body)
        self.assertTrue(extractor.is_empty_api_payload(body))

    def test_unconfirmed_missing_upcoming_still_fails_closed(self):
        page = plugin.KINGSLAND + '/events'
        challenge = '<html><title>Just a moment...</title><div id="challenge-form"></div></html>'
        cases = {
            'challenge page': (challenge, self.feed()),
            'garbled feed': (self.OFFSEASON_HTML, self.feed()[:120]),
            'html feed': (self.OFFSEASON_HTML, challenge),
            'json scalar': (self.OFFSEASON_HTML, 'null'),
            'feed still lists events': (self.OFFSEASON_HTML, self.feed(upcoming=[{'title': 'X'}])),
            'upcoming key missing': (self.OFFSEASON_HTML,
                                     json.dumps({'collection': {'typeName': 'events', 'fullUrl': '/events'},
                                                 'past': []})),
            'other collection type': (self.OFFSEASON_HTML, self.feed(typeName='blog')),
            'other collection path': (self.OFFSEASON_HTML, self.feed(fullUrl='/press')),
        }
        for label, (html, feed) in cases.items():
            with self.subTest(label):
                self.assertFalse(plugin.kingsland_upcoming_empty(html, feed, page))
        with self.assertRaisesRegex(ValueError, 'upcoming calendar missing'):
            plugin.render_kingsland(challenge, plugin.KINGSLAND + '/events-1')

    def fetch_with(self, responses):
        from unittest import mock
        calls = []

        def fake_get(url, timeout=None):
            calls.append(url)
            final_url, text = responses[url]
            resp = mock.Mock(url=final_url, text=text)
            resp.raise_for_status = mock.Mock()
            return resp
        with mock.patch.object(plugin.requests, 'get', side_effect=fake_get):
            result = plugin.fetch_kingsland([plugin.KINGSLAND + '/events-1'])
        return result, calls

    def test_fetch_confirms_empty_season_against_feed(self):
        listing = plugin.KINGSLAND + '/events-1'
        feed_url = plugin.KINGSLAND + '/events?format=json'
        (body, count), calls = self.fetch_with({
            listing: (plugin.KINGSLAND + '/events', self.OFFSEASON_HTML),
            feed_url: (feed_url, self.feed())})
        self.assertEqual((count, calls), (0, [listing, feed_url]))
        with self.assertRaisesRegex(ValueError, 'upcoming calendar missing'):
            self.fetch_with({listing: (plugin.KINGSLAND + '/events', self.OFFSEASON_HTML),
                             feed_url: (feed_url, '<html>Just a moment...</html>')})

    def test_fetch_populated_listing_unchanged_and_skips_feed(self):
        listing = plugin.KINGSLAND + '/events-1'
        (body, count), calls = self.fetch_with({
            listing: (plugin.KINGSLAND + '/events', self.listing()),
            plugin.TICKETS: (plugin.TICKETS, self.ticket())})
        self.assertEqual(count, 2)
        self.assertEqual(calls, [listing, plugin.TICKETS])
        self.assertEqual(body, plugin.render_kingsland(self.listing(), listing, self.ticket())[0])
        self.assertIn('"start_time": "17:00"', body)

    def test_whitney_only_exact_season_details_skipped(self):
        for floor in (5, 6):
            self.assertTrue(plugin.whitney_season_detail(f'https://whitney.org/events/tour-whitney-biennial-2026-floor{floor}'))
        for url in ('https://whitney.org/events/',
                    'https://whitney.org/exhibitions/2026-biennial',
                    'https://whitney.org/events/whitney-biennial-15-min-ffn-floor6',
                    'https://example.org/events/tour-whitney-biennial-2026-floor6'):
            self.assertFalse(plugin.whitney_season_detail(url))

    def test_registry_routes_actual_listing_and_details(self):
        import site_profiles
        for path in ('/events-1', plugin.GREENHOUSE_PATH):
            self.assertEqual(site_profiles.resolve_profile(plugin.KINGSLAND + path).fetcher,
                             plugin.fetch_kingsland)
        self.assertTrue(site_profiles.skip_detail_url('https://whitney.org/events/tour-whitney-biennial-2026-floor6'))
        self.assertTrue(site_profiles.skip_detail_url(plugin.KINGSLAND + plugin.GREENHOUSE_PATH))
        self.assertFalse(site_profiles.skip_detail_url(plugin.KINGSLAND + '/events-1'))

    def test_named_book_sibling_dates_cannot_reenrich_mulvaneys(self):
        self.assertTrue(site_profiles.skip_detail_url(
            'https://longbeachpl.librarycalendar.com/event/great-books-discussion-group-125354'))
        for url in ('https://longbeachpl.librarycalendar.com/event/great-books-discussion-group-125355',
                    'https://longbeachpl.librarycalendar.com/events/upcoming',
                    'https://example.org/event/great-books-discussion-group-125354'):
            self.assertFalse(plugin.long_beach_named_session_detail(url))


if __name__ == '__main__':
    unittest.main()
