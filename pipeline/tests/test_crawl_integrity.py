"""Regression cases for partial calendar captures and shared browser state."""
import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import crawler
from crawl4ai.browser_manager import BrowserManager

BODY = '# Upcoming programs\n' + 'Concert at 7pm, community hall.\n' * 30


def page(body=BODY, *, success=True, status=200, error=None):
    return SimpleNamespace(success=success, status_code=status,
                           error_message=error, html='<body>' + body + '</body>',
                           markdown=SimpleNamespace(fit_markdown='', raw_markdown=body))


class CaptureIntegrityTests(unittest.TestCase):
    def setUp(self):
        crawler.reset_host_circuits()

    def tearDown(self):
        crawler.reset_host_circuits()

    def run_capture(self, replies, *, recovery=None, timeout=10, urls=None):
        database = MagicMock()
        database.create_crawl_result.return_value = 123
        urls = urls or [f'https://calendar.test/day/{i}' for i in range(len(replies))]
        async def fetch(**kwargs):
            reply = replies.pop(0)
            if reply == 'timeout':
                await asyncio.sleep(10)
            if isinstance(reply, Exception):
                raise reply
            return reply
        client = SimpleNamespace(arun=AsyncMock(side_effect=fetch))
        with patch.object(crawler, 'db', database), \
                patch.object(crawler, '_refetch_past_challenge', new=AsyncMock(return_value=recovery)):
            returned = asyncio.run(crawler.crawl_website(client,
                dict(id=1, name='Calendar', urls=urls, crawl_timeout=timeout), None, None, 1))
        return returned, database, client

    def assert_failed(self, replies, **kwargs):
        returned, database, client = self.run_capture(replies, **kwargs)
        self.assertIsNone(returned)
        database.update_crawl_result_crawled.assert_not_called()
        database.update_crawl_result_failed.assert_called_once()
        return database, client

    def test_timeout_does_not_publish_a_large_first_page(self):
        database, _ = self.assert_failed([[page()], 'timeout'], timeout=.01)
        self.assertIn('fetched 1 of 2', str(database.update_crawl_result_failed.call_args))

    def test_successful_sibling_does_not_mask_bad_page(self):
        failures = [page(success=False, error='Connection reset'),
                    page(status=500), page(body=''),
                    page(body='We are sorry, but you found a page that does not exist.'),
                    page(body='Just a moment... Please enable cookies.')]
        for failure in failures:
            with self.subTest(failure=failure):
                self.assert_failed([[page()], [failure]])
                self.assert_failed([[page(), failure]])  # deep-crawl child

    def test_no_result_and_browser_crash_do_not_publish_fragments(self):
        self.assert_failed([[page()], []])
        self.assert_failed([[page()], RuntimeError('Target page, context or browser has been closed')])

    def test_http_failure_cannot_be_reclassified_as_empty_json_success(self):
        self.assert_failed([[page()], [page('[]', success=False, status=500,
            error='Blocked by anti-bot protection: Structural: no_content_elements on small page')]])

    def test_circuit_skips_after_good_content_fail_the_whole_capture(self):
        denied = page(success=False, status=403, error='HTTP 403')
        database, client = self.assert_failed([[page()], [denied], [denied], [denied], [page()]])
        self.assertEqual(client.arun.await_count, 4)
        self.assertIn('fetched 1 of 5', str(database.update_crawl_result_failed.call_args))
        self.assertIn('circuit-skipped', str(database.update_crawl_result_failed.call_args))

    def test_successful_retry_restores_completeness(self):
        returned, database, _ = self.run_capture(
            [[page()], [page(success=False, status=403, error='HTTP 403')]], recovery=BODY)
        self.assertEqual(returned, 123)
        database.update_crawl_result_failed.assert_not_called()

    def test_complete_empty_json_calendar_still_succeeds(self):
        returned, database, _ = self.run_capture([[page('[]')]])
        self.assertEqual(returned, 123)
        database.update_crawl_result_crawled.assert_called_once()

    def test_retry_does_not_hide_a_failed_deep_crawl_child(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.arun = AsyncMock(return_value=[page(), page(success=False, status=500)])
        with patch.object(crawler, 'AsyncWebCrawler', return_value=client):
            result = asyncio.run(crawler._refetch_past_challenge(
                'https://calendar.test/', crawler.CrawlerRunConfig(), None,
                backoff=0, attempts=1))
        self.assertIsNone(result)


class CrawlOrderingTests(unittest.TestCase):
    def test_database_priority_survives_url_parsing_and_js_delimiters(self):
        items = crawler.db._parse_url_data(
            '0:::https://calendar.test/?date={{date+9}}:::window.x=":::";|||'
            '2:::https://calendar.test/?date={{date}}:::')
        self.assertEqual(items[0]['sort_order'], 0)
        self.assertEqual(items[0]['js_code'], 'window.x=":::";')
        self.assertEqual(items[1]['sort_order'], 2)
        self.assertEqual(crawler._order_crawl_urls(items), items)
        self.assertEqual(crawler.db._parse_url_data('https://calendar.test/:::old()'),
                         [{'url': 'https://calendar.test/', 'js_code': 'old()'}])

    def test_template_families_are_numeric_and_keep_navigation_positions(self):
        def day(offset, **kwargs):
            return dict(url=f'https://calendar.test/showtimes?date={{{{date+{offset}}}}}',
                        js_code=f'window.day={offset}', **kwargs)
        urls = [day(37), 'https://calendar.test/navigation', day(2), day(10), day(0)]
        ordered = crawler._order_crawl_urls(urls)
        self.assertEqual(ordered, [urls[4], urls[1], urls[2], urls[3], urls[0]])
        self.assertEqual(urls[0]['js_code'], 'window.day=37')

    def test_explicit_priority_and_different_venues_remain_separate(self):
        urls = [dict(url='https://calendar.test/a?date={{date+9}}', sort_order=0),
                dict(url='https://calendar.test/a?date={{date}}', sort_order=1),
                dict(url='https://calendar.test/b?date={{date+3}}', sort_order=0)]
        self.assertEqual(crawler._order_crawl_urls(urls), urls)

    def test_mdy_windows_order_by_their_first_day(self):
        urls = [f'https://calendar.test/?from={{{{mdy+{i}}}}}&to={{{{mdy+{i+7}}}}}'
                for i in [21, 0, 7]]
        self.assertEqual(crawler._order_crawl_urls(urls), [urls[1], urls[2], urls[0]])


class BrowserIsolationTests(unittest.TestCase):
    def test_stealth_uses_dedicated_pages_without_the_managed_port_killer(self):
        for stealth in [False, True]:
            config = crawler.get_browser_config(use_stealth=stealth)
            self.assertFalse(config.use_managed_browser)
            self.assertEqual(config.enable_stealth, stealth)
            if stealth:
                self.assertFalse(config.headless)
            manager = BrowserManager(browser_config=config)
            self.assertIsNone(manager.managed_browser)

    def test_concurrent_detail_fetches_do_not_mutate_shared_config(self):
        shared = crawler.CrawlerRunConfig(js_code='window.venue = "own"')
        async def fetch(url, config):
            config.url = url  # actual crawl4ai behavior before it awaits
            await asyncio.sleep(.01)
            return page(config.url + '\n' + BODY)
        async def run():
            client = SimpleNamespace(arun=AsyncMock(side_effect=fetch))
            return await asyncio.gather(*[
                crawler._fetch_event_page(client, f'https://calendar.test/{i}', shared, 1)
                for i in range(3)])
        results = asyncio.run(run())
        for i, body in enumerate(results):
            self.assertTrue(body.startswith(f'https://calendar.test/{i}\n'))
        self.assertIsNone(shared.url)


if __name__ == '__main__':
    unittest.main()
