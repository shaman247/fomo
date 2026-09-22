"""Regression cases from the September 20 pipeline backlog pass."""
import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import crawler
import merger


PAGE = '# Concert\nSeptember 25, 2026 at 7pm\nA concert at the community arts center.'


def result(status=200, success=True, content=PAGE):
    return SimpleNamespace(status_code=status, success=success, error_message=None, html='',
                           markdown=SimpleNamespace(fit_markdown=content, raw_markdown=content))


class DetailResponseTests(unittest.TestCase):
    def fetch(self, response, **kwargs):
        client = SimpleNamespace(arun=mock.AsyncMock(return_value=response))
        return asyncio.run(crawler.crawl_event_url(client, 'https://example.org/event', object(), **kwargs))

    def test_http_errors_never_reach_enrichment(self):
        for status in (400, 404, 410, 500, 503):
            with self.subTest(status=status), mock.patch.object(crawler, '_refetch_past_challenge') as retry:
                self.assertIsNone(self.fetch(result(status)))
                retry.assert_not_called()

    def test_success_and_missing_status_are_supported(self):
        for status in (200, None):
            self.assertEqual(self.fetch(result(status)), PAGE)

    def test_http_blocks_retry_even_without_content(self):
        for status in (403, 429):
            with self.subTest(status=status), mock.patch.object(
                    crawler, '_refetch_past_challenge', new=mock.AsyncMock(return_value=PAGE)) as retry:
                self.assertEqual(self.fetch(result(status, False, ''), headed=True, use_stealth=True), PAGE)
                self.assertTrue(retry.await_args.kwargs['headed'])
                self.assertTrue(retry.await_args.kwargs['use_stealth'])

    def test_failed_crawler_block_without_http_status_retries(self):
        response = result(None, False, '')
        response.error_message = 'Blocked by anti-bot protection'
        with mock.patch.object(crawler, '_refetch_past_challenge', new=mock.AsyncMock(return_value=PAGE)):
            self.assertEqual(self.fetch(response), PAGE)

    def test_recovered_dead_page_is_discarded(self):
        with mock.patch.object(crawler, '_refetch_past_challenge', new=mock.AsyncMock(
                return_value='# Page not found\n' + 'We are sorry, but you found a page that does not exist. ' * 5)):
            self.assertIsNone(self.fetch(result(content='Just a moment... ' * 10)))

    def retry(self, responses):
        client = mock.MagicMock()
        client.__aenter__ = mock.AsyncMock(return_value=client)
        client.__aexit__ = mock.AsyncMock(return_value=False)
        client.arun = mock.AsyncMock(return_value=responses)
        with mock.patch.object(crawler, 'AsyncWebCrawler', return_value=client), \
             mock.patch.object(crawler, 'get_browser_config') as config:
            value = asyncio.run(crawler._refetch_past_challenge(
                'https://example.org/event', object(), 'custom-agent', attempts=1,
                backoff=0, headed=True, use_stealth=True))
        self.assertTrue(config.call_args.kwargs['headed'])
        self.assertTrue(config.call_args.kwargs['use_stealth'])
        self.assertEqual(config.call_args.kwargs['user_agent'], 'custom-agent')
        return value

    def test_retry_retains_browser_settings_and_returns_real_page(self):
        self.assertEqual(self.retry([result()]).strip(), PAGE)

    def test_retry_does_not_accept_failed_or_http_error_bodies(self):
        for response in (result(404), result(403), result(503), result(200, False)):
            with self.subTest(response=response):
                self.assertIsNone(self.retry([response]))

    def test_retry_does_not_accept_soft_404(self):
        self.assertIsNone(self.retry([result(content='We are sorry, but you found a page that does not exist.')]))


class ChallengeMarkersTests(unittest.TestCase):
    def test_recaptcha_challenge_is_recognized(self):
        for text in ('This site is exceeding reCAPTCHA Enterprise free quota.',
                     'Select all images with motorcycles',
                     'Slide right to secure your access'):
            self.assertTrue(crawler._is_bot_challenge(text))

    def test_signed_challenge_image_urls_do_not_defeat_size_guard(self):
        tiles = ('![](https://www.google.com/recaptcha/api2/payload?p=' + 'x' * 1000 + ')\n') * 9
        self.assertTrue(crawler._is_bot_challenge('Select all images with motorcycles\n' + tiles))
        self.assertFalse(crawler._is_bot_challenge(PAGE * 100 + tiles + 'Select all images with motorcycles'))

    def test_full_event_content_with_widget_is_preserved(self):
        self.assertFalse(crawler._is_bot_challenge(PAGE * 100 + 'Select all images with motorcycles'))


class ListingRetryTests(unittest.TestCase):
    def tearDown(self):
        crawler.reset_host_circuits()

    def test_site_settings_reach_both_retry_paths(self):
        for count in (1, crawler.HOST_BLOCK_TRIP_THRESHOLD):
            crawler.reset_host_circuits()
            blocked = result(403, False, 'Access denied')
            blocked.error_message = 'Blocked by anti-bot protection: HTTP 403'
            client = SimpleNamespace(arun=mock.AsyncMock(return_value=[blocked]))
            website = dict(id=42, name='Test Venue', headed=True, use_stealth=True,
                           urls=[f'https://example.org/{i}' for i in range(count)])
            fake_db = mock.MagicMock()
            fake_db.create_crawl_result.return_value = 99
            with mock.patch.object(crawler, 'db', fake_db), mock.patch.object(
                    crawler, '_refetch_past_challenge', new=mock.AsyncMock(return_value=None)) as retry:
                asyncio.run(crawler.crawl_website(client, website, mock.Mock(), mock.Mock(), 1))
                self.assertEqual(retry.await_count, 1)
                self.assertTrue(retry.await_args.kwargs['headed'])
                self.assertTrue(retry.await_args.kwargs['use_stealth'])

    def test_navigation_exception_records_new_attempt_failure(self):
        client = SimpleNamespace(arun=mock.AsyncMock(side_effect=RuntimeError('navigation failed')))
        fake_db = mock.MagicMock()
        fake_db.create_crawl_result.return_value = 99
        with mock.patch.object(crawler, 'db', fake_db):
            returned = asyncio.run(crawler.crawl_website(client,
                dict(id=42, name='Test Venue', urls=['https://example.org/']),
                mock.Mock(), mock.Mock(), 1))
        self.assertIsNone(returned)
        self.assertEqual(fake_db.update_crawl_result_failed.call_args.args[2:], (99, 'navigation failed'))


class SuppressedMatchingTests(unittest.TestCase):
    def candidate(self, eid, suppressed=False, location_id=77, **kwargs):
        return dict(id=eid, name='Community Concert', location_id=location_id,
                    suppressed=suppressed, **kwargs)

    def dateless(self, candidates, tier):
        indexes = [{}, {}, {}]
        keys = (77, merger._coord_key(40.7, -74.0), merger.normalize_name_for_dedup('Arts Center'))
        indexes[tier][keys[tier]] = candidates
        return merger._match_dateless_crawl_event(
            'Community Concert', 77, 40.7, -74.0, 'Arts Center', *indexes)

    def test_dateless_prefers_visible_in_every_location_index(self):
        hidden, visible = self.candidate(100, True), self.candidate(200)
        for tier in range(3):
            for candidates in ([hidden, visible], [visible, hidden]):
                self.assertEqual(self.dateless(candidates, tier), 200)

    def test_dateless_preserves_hidden_only_and_exact_name_guards(self):
        for tier in range(3):
            self.assertEqual(self.dateless([self.candidate(100, True)], tier), 100)
            other = self.candidate(200)
            other['name'] = 'Another Concert'
            self.assertEqual(self.dateless([self.candidate(100, True), other], tier), 100)

    def test_dateless_ambiguous_website_fallback_still_refuses_to_guess(self):
        self.assertIsNone(merger._match_dateless_crawl_event(
            'Community Concert', None, None, None, None, {}, {}, {}, 5,
            {5: [self.candidate(100, True), self.candidate(200, location_id=88)]}))

    def url_match(self, candidates, listing=False):
        url = 'https://example.org/events/concert'
        key = (5, merger.normalize_url_for_identity(url))
        return merger._match_by_url_identity(
            'Community Concert', url, 5, 77, {('2026-09-25', '19:00')},
            {key: candidates}, {key: 1}, {key} if listing else set(),
            {77: (40.7, -74.0), 88: (40.7001, -74.0001), 99: (41.7, -74.0)})

    def test_url_prefers_visible_over_older_hidden_same_or_nearby(self):
        for location_id in (77, 88):
            hidden = self.candidate(100, True, slots={('2026-09-25', '19:00')})
            visible = self.candidate(200, location_id=location_id, slots={('2026-09-25', '19:00')})
            for candidates in ([hidden, visible], [visible, hidden]):
                self.assertEqual(self.url_match(candidates), 200)

    def test_url_keeps_slot_distance_and_listing_guards(self):
        hidden = self.candidate(100, True, slots={('2026-09-25', '19:00')})
        wrong_slot = self.candidate(200, slots={('2026-09-25', '20:00')})
        far = self.candidate(300, location_id=99, slots={('2026-09-25', '19:00')})
        self.assertEqual(self.url_match([hidden, wrong_slot, far]), 100)
        self.assertIsNone(self.url_match([hidden], listing=True))


if __name__ == '__main__':
    unittest.main()
