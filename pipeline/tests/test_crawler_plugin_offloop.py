"""Custom-fetch plugins must not block the crawl event loop.

2026-10-02: synchronous plugin fetchers (queens_complete ~6 min, williams,
tenement, ...) ran directly inside crawl_website's coroutine and froze the loop
for ten minutes. Eight unrelated browser crawls whose pages had already loaded
could not resume, and every one of their per-site wait_for deadlines fired the
moment the loop came back ("Crawl timed out after 180/240 seconds" x8 at one
instant; all eight succeeded on retry). These tests drive crawl_website with a
blocking plugin next to a browser crawl whose budget is shorter than the
plugin's runtime.
"""
import asyncio
import re
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import crawler
from site_profiles import CrawlMode, SiteProfile

PLUGIN_SECONDS = 0.6
BROWSER_TIMEOUT = 0.3


def _fetcher(fn, module):
    fn.__module__ = module
    return fn


def _browser():
    async def arun(**kwargs):
        # Two awaits: a loop frozen past the deadline lets the timeout land
        # between them, exactly as the real multi-step crawl4ai fetch did.
        await asyncio.sleep(0.02)
        await asyncio.sleep(0.02)
        markdown = SimpleNamespace(fit_markdown='Browser event\n' + 'b' * 600, raw_markdown='')
        return [SimpleNamespace(success=True, error_message=None,
                                html='<body>Calendar</body>', markdown=markdown)]
    return SimpleNamespace(arun=AsyncMock(side_effect=arun))


class TestPluginRunsOffLoop(unittest.TestCase):
    def test_blocking_plugin_does_not_time_out_concurrent_browser_crawl(self):
        def slow_plugin():
            time.sleep(PLUGIN_SECONDS)  # synchronous HTTP / backoff stand-in
            return '### Plugin event\n' + 'a' * 600, 1
        profile = SiteProfile('slow', re.compile('plugin.example'), crawl_mode=CrawlMode.CUSTOM,
                              fetcher=_fetcher(slow_plugin, 'fake_slow_plugin'))
        database = MagicMock()
        ids = iter(range(100, 200))
        database.create_crawl_result.side_effect = lambda *a, **k: next(ids)

        def custom(urls):
            return profile if all('plugin.example' in u for u in urls) else None

        browser_site = dict(id=1, name='Browser Site', urls=['https://browser.example/events/'],
                            crawl_timeout=BROWSER_TIMEOUT)
        plugin_site = dict(id=2, name='Plugin Site', urls=['https://plugin.example/api/'])

        async def both():
            # Browser crawl first: it starts its timed fetch, then the plugin
            # site starts while that fetch is in flight.
            return await asyncio.gather(
                crawler.crawl_website(_browser(), browser_site, None, None, 1),
                crawler.crawl_website(_browser(), plugin_site, None, None, 1))

        with patch.object(crawler, 'db', database), \
                patch.object(crawler.site_profiles, 'custom_fetch_profile', side_effect=custom), \
                patch.object(crawler.site_profiles, 'inject_js_for', return_value=''):
            browser_id, plugin_id = asyncio.run(both())

        failures = [c.args[3] for c in database.update_crawl_result_failed.call_args_list]
        self.assertEqual(failures, [], 'a blocking plugin consumed another site\'s crawl_timeout')
        self.assertIsNotNone(browser_id)
        self.assertIsNotNone(plugin_id)
        bodies = [c.args[3] for c in database.update_crawl_result_crawled.call_args_list]
        self.assertTrue(any('Browser event' in b for b in bodies))
        self.assertTrue(any('Plugin event' in b for b in bodies))

    def test_loop_keeps_running_during_plugin_fetch(self):
        seen_in_flight = []

        def slow_plugin(urls):
            time.sleep(0.3)
            return 'content ' + urls[0], 1
        profile = SiteProfile('slow', re.compile('x'), crawl_mode=CrawlMode.CUSTOM,
                              fetcher=_fetcher(slow_plugin, 'fake_ticker_plugin'))

        async def main():
            ticks = 0
            fetch = asyncio.create_task(crawler.run_custom_fetcher(profile, ['https://x/']))
            while not fetch.done():
                seen_in_flight.append(crawler.custom_fetches_in_flight())
                ticks += 1
                await asyncio.sleep(0.01)
            return ticks, await fetch

        ticks, result = asyncio.run(main())
        self.assertGreater(ticks, 5, 'event loop was blocked by the plugin fetch')
        self.assertEqual(result, ('content https://x/', 1))  # urls= passed through
        self.assertIn(1, seen_in_flight)
        self.assertEqual(crawler.custom_fetches_in_flight(), 0)

    def test_plugin_exception_propagates_and_counter_resets(self):
        def broken():
            raise ValueError('Incomplete inventory')
        profile = SiteProfile('broken', re.compile('x'), crawl_mode=CrawlMode.CUSTOM,
                              fetcher=_fetcher(broken, 'fake_broken_plugin'))
        with self.assertRaisesRegex(ValueError, 'Incomplete inventory'):
            asyncio.run(crawler.run_custom_fetcher(profile, ['https://x/']))
        self.assertEqual(crawler.custom_fetches_in_flight(), 0)

    def test_distinct_plugins_overlap_same_plugin_serializes(self):
        """Different plugins run concurrently; one plugin module runs one fetch
        at a time (many websites share a platform plugin, and before the fix
        the frozen loop serialized them implicitly)."""
        a_started, b_started = threading.Event(), threading.Event()

        def plugin_a():
            a_started.set()
            # Only returns if plugin_b runs at the same time.
            return ('a', 1) if b_started.wait(2) else ('', 0)

        def plugin_b():
            b_started.set()
            return ('b', 1) if a_started.wait(2) else ('', 0)
        pa = SiteProfile('a', re.compile('a'), crawl_mode=CrawlMode.CUSTOM,
                         fetcher=_fetcher(plugin_a, 'fake_plugin_a'))
        pb = SiteProfile('b', re.compile('b'), crawl_mode=CrawlMode.CUSTOM,
                         fetcher=_fetcher(plugin_b, 'fake_plugin_b'))

        async def run(*profiles):
            return await asyncio.gather(*(crawler.run_custom_fetcher(p, []) for p in profiles))
        self.assertEqual(asyncio.run(run(pa, pb)), [('a', 1), ('b', 1)])

        active, peak = [0], [0]
        lock = threading.Lock()

        def shared():
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.05)
            with lock:
                active[0] -= 1
            return 'ok', 1
        s1 = SiteProfile('s1', re.compile('s'), crawl_mode=CrawlMode.CUSTOM,
                         fetcher=_fetcher(shared, 'fake_shared_plugin'))
        self.assertEqual(asyncio.run(run(s1, s1, s1)), [('ok', 1)] * 3)
        self.assertEqual(peak[0], 1)


if __name__ == '__main__':
    unittest.main()
