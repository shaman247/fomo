"""Regression: SQL NULL must select the listing scroll default, not disable it."""
import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import crawler


class CrawlDefaultsTests(unittest.TestCase):
    def test_null_and_absent_scan_use_default_explicit_off_is_preserved(self):
        for settings, expected in (({}, True), ({'scan_full_page': None}, True),
                                   ({'scan_full_page': 0}, False),
                                   ({'scan_full_page': False}, False),
                                   ({'scan_full_page': 1}, True)):
            with self.subTest(settings=settings):
                result = SimpleNamespace(success=True, status_code=200, error_message=None,
                    html='', markdown=SimpleNamespace(raw_markdown='{"entries":[]}', fit_markdown=None))
                client = SimpleNamespace(arun=mock.AsyncMock(return_value=[result]))
                database = mock.MagicMock()
                database.create_crawl_result.return_value = 99
                with mock.patch.object(crawler, 'db', database):
                    returned = asyncio.run(crawler.crawl_website(client,
                        dict(id=42, name='Feed', urls=['https://example.org/feed'], **settings),
                        mock.Mock(), mock.Mock(), 1))
                self.assertEqual(returned, 99)
                self.assertEqual(client.arun.await_args.kwargs['config'].scan_full_page, expected)

    def test_click_script_needs_an_explicit_num_clicks(self):
        """NULL num_clicks is 'no clicks configured', not a hidden default of 2."""
        for settings, expects_clicks in ((dict(selector='.more'), False),
                                         (dict(selector='.more', num_clicks=None), False),
                                         (dict(selector='.more', num_clicks=0), False),
                                         (dict(selector='.more', num_clicks=3), True),
                                         (dict(num_clicks=3), False)):
            with self.subTest(settings=settings):
                result = SimpleNamespace(success=True, status_code=200, error_message=None,
                    html='', markdown=SimpleNamespace(raw_markdown='{"entries":[]}', fit_markdown=None))
                client = SimpleNamespace(arun=mock.AsyncMock(return_value=[result]))
                database = mock.MagicMock()
                database.create_crawl_result.return_value = 99
                with mock.patch.object(crawler, 'db', database):
                    asyncio.run(crawler.crawl_website(client,
                        dict(id=42, name='Feed', urls=['https://example.org/feed'], **settings),
                        mock.Mock(), mock.Mock(), 1))
                js = client.arun.await_args.kwargs['config'].js_code or ''
                self.assertEqual("querySelector('.more').click()" in js, expects_clicks)

    def test_details_keep_scrolling_disabled(self):
        for value in (None, 0, 1):
            self.assertFalse(crawler.build_event_crawl_config({'scan_full_page': value}).scan_full_page)


if __name__ == '__main__':
    unittest.main()
