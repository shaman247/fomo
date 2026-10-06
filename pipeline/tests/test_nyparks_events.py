"""Complete region pagination and recurring dates for NY Parks source intake."""
import os
import sys
import unittest
from urllib.parse import parse_qs, urlparse
from urllib.error import HTTPError, URLError
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from sources import nyparks_events as parks
except ImportError:
    parks = None

BASE = 'https://parks.ny.gov/visit/events?region%5B0%5D=Taconic&page=0'
NEXT = 'https://parks.ny.gov/visit/events?region%5BTaconic%5D=Taconic&page=1'
URL = 'https://parks.ny.gov/visit/events/farm-market'


def listing(day='Oct 3, 2026', summary='1 - 1 of 1 results', following=None):
    return (f'<div class="c-results-summary">{summary}</div>'
            '<div class="c-card--event"><a class="c-card__title-link" href="/visit/events/farm-market">Farm Market</a>'
            f'<div class="c-card__eyebrow">Park</div><div class="c-card__date-mobile">{day}</div></div>'
            + (f'<a class="c-pager__link--next" href="{following}">Next</a>' if following else ''))


DETAIL = '''<article class="c-article--event"><h1>Farm Market</h1>
<div class="c-intro__content">Saturday, October 3, 2026</div>
<div class="c-intro__content">9am–2pm Weekly on Saturday until October 31, 2026</div>
<div class="c-byline--large"><strong>Park</strong></div>
<div class="c-add-to-calendar"><a href="https://calendar.google.com/calendar/render?dates=20261003T090000%2F20261003T140000&amp;ctz=America%2FNew_York&amp;recur=RRULE%3AFREQ%3DWEEKLY">Google</a></div>
<div class="l-page__main"><p>Fresh produce.</p><a href="https://example.org/register">Register</a></div></article>'''


@unittest.skipIf(parks is None, 'deployment-specific source plugin not installed')
class NYParksSourceTests(unittest.TestCase):
    def test_transient_fetch_failure_retries_without_empty_fallback(self):
        with patch.object(parks, 'get_text', side_effect=[URLError('network unreachable'), 'complete']) as fetch, patch.object(parks.time, 'sleep'):
            self.assertEqual(parks._get_text(BASE), 'complete')
            self.assertEqual(fetch.call_count, 2)
        with patch.object(parks, 'get_text', side_effect=URLError('network unreachable')) as fetch, patch.object(parks.time, 'sleep'):
            with self.assertRaises(URLError):
                parks._get_text(BASE)
            self.assertEqual(fetch.call_count, 3)

    def test_missing_detail_http_response_is_not_retried(self):
        with patch.object(parks, 'get_text', side_effect=HTTPError(URL, 404, 'missing', {}, None)) as fetch, patch.object(parks.time, 'sleep'):
            with self.assertRaises(HTTPError):
                parks._get_text(URL)
            self.assertEqual(fetch.call_count, 1)

    def test_rate_limit_requires_publisher_retry_delay(self):
        for headers in ({}, {'Retry-After': '120'}, {'Retry-After': 'Thu, 01 Oct 2026 23:00:00 GMT'}):
            with patch.object(parks, 'get_text', side_effect=HTTPError(URL, 429, 'limited', headers, None)) as fetch, patch.object(parks.time, 'sleep') as sleep:
                with self.assertRaises(HTTPError):
                    parks._get_text(URL)
                self.assertEqual(fetch.call_count, 1)
                sleep.assert_not_called()
        with patch.object(parks, 'get_text', side_effect=[HTTPError(URL, 429, 'limited', {'Retry-After': '12'}, None), 'complete']), patch.object(parks.time, 'sleep') as sleep:
            self.assertEqual(parks._get_text(URL), 'complete')
            sleep.assert_called_once_with(12)

    def test_configured_facets_only_and_no_redundant_tail_fetch(self):
        seeds = parks._seeds([BASE.replace('page=0', 'page=6'), BASE,
                              BASE.replace('Taconic', 'Palisades')])
        self.assertEqual(len(seeds), 2)
        self.assertTrue(all(parse_qs(urlparse(s).query)['page'] == ['0'] for s in seeds))
        for url in ['https://parks.ny.gov/visit/events?lct=0',
                    BASE + '&region%5B1%5D=Palisades', BASE.replace('parks.ny.gov', 'evil.example')]:
            with self.assertRaises(ValueError):
                parks._seeds([url])

    def test_same_url_new_date_is_preserved_as_published_recurrence(self):
        pages = {BASE: listing(summary='1 - 1 of 2 results', following=NEXT),
                 NEXT: listing('Oct 10, 2026', summary='2 - 2 of 2 results'), URL: DETAIL}
        details, totals = parks.capture([BASE], getter=pages.__getitem__)
        self.assertEqual(totals, {'Taconic': 2})
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]['listing_dates'], ['Oct 3, 2026', 'Oct 10, 2026'])
        self.assertIn('RRULE:', details[0]['calendar']['recur'])
        markdown, count = parks.markdown(details, totals)
        self.assertEqual(count, 1)
        self.assertIn('Oct 10, 2026', markdown)
        self.assertIn('https://example.org/register', markdown)

    def test_missing_tail_does_not_publish_partial_region(self):
        with self.assertRaisesRegex(ValueError, 'incomplete region'):
            parks._region_cards(BASE, lambda _: listing(summary='1 - 1 of 2 results'))

    def test_repeated_identical_occurrence_is_not_recurrence(self):
        pages = {BASE: listing(summary='1 - 1 of 2 results', following=NEXT),
                 NEXT: listing(summary='2 - 2 of 2 results')}
        with self.assertRaisesRegex(ValueError, 'repeated event occurrences'):
            parks._region_cards(BASE, pages.__getitem__)

    def test_duplicate_occurrence_within_one_page_cannot_satisfy_total(self):
        html = listing(summary='1 - 2 of 2 results')
        html += html[html.index('<div class="c-card--event">'):]
        with self.assertRaisesRegex(ValueError, 'repeated event occurrences'):
            parks._region_cards(BASE, lambda _: html)

    def test_changed_result_count_is_not_complete_capture(self):
        pages = {BASE: listing(summary='1 - 1 of 2 results', following=NEXT),
                 NEXT: listing('Oct 10, 2026', summary='2 - 2 of 3 results')}
        with self.assertRaisesRegex(ValueError, 'total changed'):
            parks._region_cards(BASE, pages.__getitem__)

    def test_next_cannot_change_region_or_repeat_url(self):
        for following in [NEXT.replace('Taconic', 'Palisades'), BASE]:
            with self.assertRaises(ValueError):
                parks._region_cards(BASE, lambda _: listing(summary='1 - 1 of 2 results', following=following))

    def test_missing_detail_aborts_whole_capture(self):
        pages = {BASE: listing(), URL: '<main>Oops, lost your way?</main>'}
        with self.assertRaisesRegex(ValueError, 'missing/unpublished'):
            parks.capture([BASE], getter=pages.__getitem__)

    def test_detail_requires_published_year_and_matching_identity(self):
        card = dict(url=URL, title='Farm Market', venue='Park')
        for html in [DETAIL.replace('2026', ''), DETAIL.replace('<h1>Farm Market', '<h1>Other program'),
                     DETAIL.replace('<strong>Park', '<strong>Elsewhere')]:
            with self.assertRaises(ValueError):
                parks._detail(card, html)

    def test_absent_clock_does_not_acquire_inferred_time(self):
        html = DETAIL.replace('<div class="c-intro__content">9am–2pm Weekly on Saturday until October 31, 2026</div>', '')
        result = parks._detail(dict(url=URL, title='Farm Market', venue='Park'), html)
        self.assertEqual(result['time'], '')

    def test_singular_result_summary_is_parsed(self):
        # Live markup for a one-event listing (Robert Moses, 2026-10-03).
        cards, count, following = parks._listing(listing(summary='1 - 1 of 1 result'), BASE)
        self.assertEqual((len(cards), count, following), (1, 1, None))
        details, totals = parks.capture([BASE], getter={BASE: listing(summary='1 - 1 of 1 result'), URL: DETAIL}.__getitem__)
        self.assertEqual((len(details), totals), (1, {'Taconic': 1}))

    def test_couldnt_find_any_matches_is_a_valid_empty_listing(self):
        # Live empty-state markup (Jones Beach, 2026-10-03): no summary, no cards, no facet.
        for apostrophe in ("'", '’'):
            html = ('<form>Filter Events</form><div class="c-view c-view--search-listings">'
                    f'<div class="c-view__empty"><p><strong>Sorry, we couldn{apostrophe}t find any matches.'
                    '</strong></p>\n</div></div>')
            self.assertEqual(parks._listing(html, BASE), ([], 0, None))
            self.assertEqual(parks._region_cards(BASE, lambda _: html), ('Taconic', []))
            self.assertEqual(parks.capture([BASE], getter=lambda _: html), ([], {'Taconic': 0}))

    def test_page_without_cards_or_empty_state_is_still_rejected(self):
        for html in ['<main>Oops, lost your way?</main>', '<div class="c-view__empty"></div>',
                     '<div class="c-results-summary">1 - 1 of 1 result</div>']:
            with self.assertRaisesRegex(ValueError, 'unrecognized or incomplete'):
                parks._listing(html, BASE)

    def test_profile_targets_listings_not_individual_details(self):
        self.assertTrue(parks.PROFILE.matches(BASE))
        self.assertFalse(parks.PROFILE.matches(URL))
        # Per-park location[] siblings (w2775 Jones Beach etc.) stay on the generic crawl.
        self.assertFalse(parks.PROFILE.matches(
            'https://parks.ny.gov/visit/events?location%5BJones+Beach+State+Park%5D=Jones+Beach+State+Park'))


if __name__ == '__main__':
    unittest.main()
