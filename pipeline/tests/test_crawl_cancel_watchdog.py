"""Step 2 crawl: cancelled crawls must not strand 'pending' rows, and the stall
watchdog must count per-fetch progress.

2026-10-08: AMC (w4112-4118, 24 URLs x 6-15s each) never finished a SITE inside
the 300s STALL_TIMEOUT although every fetch returned, so the watchdog aborted
the batch at "0/7 done". The abort cancels crawl_website; CancelledError is a
BaseException, slipped past `except Exception`, and left each crawl_result
'pending' — a status get_incomplete_crawl_results never retries.
"""
import asyncio
import re
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import crawler
import main
from site_profiles import CrawlMode, SiteProfile


def _page():
    markdown = SimpleNamespace(fit_markdown='Showtime 7:00pm\n' + 'b' * 600, raw_markdown='')
    return [SimpleNamespace(success=True, error_message=None,
                            html='<body>Showtimes</body>', markdown=markdown)]


def _site(n_urls=1, timeout=60):
    return dict(id=4112, name='AMC Test', crawl_timeout=timeout,
                urls=[f'https://amc.example/showtimes/{i}' for i in range(n_urls)])


class _Harness:
    def __init__(self):
        self.db = MagicMock()
        self.db.create_crawl_result.return_value = 555

    def patches(self, custom=None):
        return [patch.object(crawler, 'db', self.db),
                patch.object(crawler.site_profiles, 'custom_fetch_profile',
                             side_effect=custom or (lambda urls: None)),
                patch.object(crawler.site_profiles, 'inject_js_for', return_value='')]

    def run(self, coro_factory, custom=None):
        ps = self.patches(custom)
        for p in ps:
            p.start()
        try:
            return asyncio.run(coro_factory())
        finally:
            for p in ps:
                p.stop()

    def failures(self):
        return [c.args[2:] for c in self.db.update_crawl_result_failed.call_args_list]


class TestCancelledCrawlIsMarkedFailed(unittest.TestCase):

    def test_cancel_mid_fetch_marks_row_failed_and_reraises(self):
        h = _Harness()

        async def scenario():
            fetching = asyncio.Event()

            async def wedged_arun(**kwargs):
                fetching.set()
                await asyncio.sleep(3600)  # a wedged browser never returns
            browser = SimpleNamespace(arun=AsyncMock(side_effect=wedged_arun))
            task = asyncio.create_task(crawler.crawl_website(browser, _site(), None, None, 1))
            await fetching.wait()
            task.cancel()  # what the watchdog's gather_task.cancel() does
            with self.assertRaises(asyncio.CancelledError):
                await task

        h.run(scenario)
        self.assertEqual(h.failures(), [(555, crawler.CRAWL_CANCELLED_MESSAGE)])
        self.assertFalse(h.db.update_crawl_result_crawled.called)

    def test_cancel_during_custom_fetch_marks_row_failed(self):
        h = _Harness()

        def slow_plugin():
            time.sleep(0.3)
            return 'x' * 600, 1
        slow_plugin.__module__ = 'fake_cancel_plugin'
        profile = SiteProfile('slow', re.compile('plugin.example'), crawl_mode=CrawlMode.CUSTOM,
                              fetcher=slow_plugin)

        async def scenario():
            task = asyncio.create_task(crawler.crawl_website(
                SimpleNamespace(arun=AsyncMock()),
                dict(id=2, name='Plugin Site', urls=['https://plugin.example/api']),
                None, None, 1))
            await asyncio.sleep(0.05)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        h.run(scenario, custom=lambda urls: profile)
        self.assertEqual(h.failures(), [(555, crawler.CRAWL_CANCELLED_MESSAGE)])

    def test_db_error_while_marking_does_not_swallow_the_cancel(self):
        h = _Harness()
        h.db.update_crawl_result_failed.side_effect = RuntimeError('db gone')

        async def scenario():
            async def wedged_arun(**kwargs):
                await asyncio.sleep(3600)
            browser = SimpleNamespace(arun=AsyncMock(side_effect=wedged_arun))
            task = asyncio.create_task(crawler.crawl_website(browser, _site(), None, None, 1))
            await asyncio.sleep(0.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        h.run(scenario)

    def test_ordinary_success_is_unchanged(self):
        h = _Harness()
        browser = SimpleNamespace(arun=AsyncMock(return_value=_page()))
        result = h.run(lambda: crawler.crawl_website(browser, _site(3), None, None, 1))
        self.assertEqual(result, 555)
        self.assertEqual(h.failures(), [])


class TestWatchdogCountsPerFetchProgress(unittest.TestCase):

    def test_each_returned_fetch_advances_the_progress_clock(self):
        h = _Harness()
        stamps = []

        async def arun(**kwargs):
            stamps.append(crawler.last_crawl_progress())
            await asyncio.sleep(0.01)
            return _page()
        browser = SimpleNamespace(arun=AsyncMock(side_effect=arun))
        before = time.monotonic()
        h.run(lambda: crawler.crawl_website(browser, _site(3), None, None, 1))
        # The clock moved after every fetch, before the site finished.
        self.assertGreaterEqual(stamps[1], before)
        self.assertGreater(stamps[2], stamps[1])
        self.assertGreater(crawler.last_crawl_progress(), stamps[2])

    def test_slow_multi_url_site_is_not_idle(self):
        # No site has finished for 10 minutes, but a fetch returned 20s ago.
        now = 10_000.0
        with patch.object(crawler, '_last_crawl_progress', now - 20):
            self.assertEqual(main.crawl_idle_seconds(now - 600, now=now), 20)

    def test_wedged_browser_still_goes_idle(self):
        # Neither a site nor a fetch has completed: the watchdog must still fire.
        now = 10_000.0
        with patch.object(crawler, '_last_crawl_progress', now - 900):
            self.assertGreater(main.crawl_idle_seconds(now - 400, now=now), 300)

    def test_stale_progress_from_an_earlier_batch_does_not_mask_a_new_batch(self):
        # heartbeat['last'] is reset at batch start; an older fetch stamp loses.
        now = 10_000.0
        with patch.object(crawler, '_last_crawl_progress', now - 5000):
            self.assertEqual(main.crawl_idle_seconds(now - 310, now=now), 310)


if __name__ == '__main__':
    unittest.main()
