"""Iframe source remains data and retains the publisher's URL base."""
import os
import sys
import unittest
from types import MethodType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from iframe_content import (_process_iframes, _READ_BODY, _REPLACE_FRAME,
                            install_safe_iframe_processing)
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy
from crawl4ai.browser_adapter import PlaywrightAdapter


class IframeProcessingTests(unittest.IsolatedAsyncioTestCase):
    async def test_html_is_passed_as_data_without_author_id_lookup(self):
        content = '<p>C:\\users\\new `${window.changed = true}`</p>'
        frame = SimpleNamespace(wait_for_load_state=AsyncMock(),
                                evaluate=AsyncMock(return_value=content))
        element = SimpleNamespace(content_frame=AsyncMock(return_value=frame),
                                  evaluate=AsyncMock())
        page = SimpleNamespace(query_selector_all=AsyncMock(return_value=[element]))
        strategy = SimpleNamespace(logger=Mock())
        self.assertIs(await _process_iframes(strategy, page), page)
        frame.evaluate.assert_awaited_once_with(_READ_BODY)
        element.evaluate.assert_awaited_once_with(_REPLACE_FRAME, {
            'html': content, 'className': 'extracted-iframe-content-0'})
        self.assertNotIn(content, element.evaluate.call_args.args[0])
        strategy.logger.error.assert_not_called()

    async def test_missing_failed_and_empty_frames_do_not_stop_later_frame(self):
        good = SimpleNamespace(wait_for_load_state=AsyncMock(),
                               evaluate=AsyncMock(return_value='<p>Event</p>'))
        empty = SimpleNamespace(wait_for_load_state=AsyncMock(),
                                evaluate=AsyncMock(return_value=None))
        missing = SimpleNamespace(content_frame=AsyncMock(return_value=None), evaluate=AsyncMock())
        failed = SimpleNamespace(content_frame=AsyncMock(side_effect=RuntimeError('detached')), evaluate=AsyncMock())
        blank = SimpleNamespace(content_frame=AsyncMock(return_value=empty), evaluate=AsyncMock())
        final = SimpleNamespace(content_frame=AsyncMock(return_value=good), evaluate=AsyncMock())
        page = SimpleNamespace(query_selector_all=AsyncMock(return_value=[missing, failed, blank, final]))
        strategy = SimpleNamespace(logger=Mock())
        await _process_iframes(strategy, page)
        for element in (missing, failed, blank):
            element.evaluate.assert_not_awaited()
        final.evaluate.assert_awaited_once()
        strategy.logger.warning.assert_called_once()
        strategy.logger.error.assert_called_once()

    def test_install_is_per_instance_idempotent_and_preserves_custom_strategy(self):
        one = object.__new__(AsyncPlaywrightCrawlerStrategy)
        two = object.__new__(AsyncPlaywrightCrawlerStrategy)
        one.adapter = PlaywrightAdapter()
        two.adapter = PlaywrightAdapter()
        install_safe_iframe_processing(SimpleNamespace(crawler_strategy=one))
        installed = one.process_iframes
        self.assertIs(installed.__func__, _process_iframes)
        install_safe_iframe_processing(SimpleNamespace(crawler_strategy=one))
        self.assertIs(one.process_iframes, installed)
        self.assertIs(two.process_iframes.__func__, AsyncPlaywrightCrawlerStrategy.process_iframes)
        async def custom(self, page): return page
        two.process_iframes = MethodType(custom, two)
        install_safe_iframe_processing(SimpleNamespace(crawler_strategy=two))
        self.assertIs(two.process_iframes.__func__, custom)
        install_safe_iframe_processing(object())

    def test_custom_adapter_is_not_replaced(self):
        strategy = object.__new__(AsyncPlaywrightCrawlerStrategy)
        strategy.adapter = object()
        install_safe_iframe_processing(SimpleNamespace(crawler_strategy=strategy))
        self.assertIs(strategy.process_iframes.__func__, AsyncPlaywrightCrawlerStrategy.process_iframes)


@unittest.skipUnless(os.environ.get('FOMO_BROWSER_TESTS') == '1', 'set FOMO_BROWSER_TESTS=1 for Chromium iframe regressions')
class IframeBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page()

    async def asyncTearDown(self):
        await self.browser.close()
        await self.playwright.stop()

    async def test_literal_text_and_foreign_frame_urls_survive(self):
        frame_html = r'''<html><head><base href="https://booking.example/programs/"></head><body>
            <p id="literal">C:\users\new `${window.changed = true}`</p>
            <script type="application/json">{"text":"\\u","name":"Sawyer ` card"}</script>
            <a href="class/123?slot=2&amp;x=3">Reserve</a>
            <a href="#schedule">Schedule</a><a href="mailto:info@example.com">Email</a>
            <img src="../class.jpg"><video poster="poster.jpg"></video>
            <form action="register"><input name="section"></form>
            </body></html>'''
        async def route(request):
            body = frame_html if 'booking.example' in request.request.url else '<iframe id="duplicate" src="https://booking.example/embed"></iframe><div id="duplicate">Parent</div>'
            await request.fulfill(status=200, content_type='text/html', body=body)
        await self.page.route('**/*', route)
        await self.page.goto('https://venue.example/calendar', wait_until='load')
        strategy = SimpleNamespace(logger=Mock())
        await _process_iframes(strategy, self.page)
        self.assertEqual(await self.page.locator('iframe').count(), 0)
        self.assertEqual(await self.page.locator('#literal').inner_text(), r'C:\users\new `${window.changed = true}`')
        self.assertIsNone(await self.page.evaluate('window.changed'))
        self.assertEqual(await self.page.get_by_text('Reserve', exact=True).get_attribute('href'), 'https://booking.example/programs/class/123?slot=2&x=3')
        self.assertEqual(await self.page.get_by_text('Schedule', exact=True).get_attribute('href'), 'https://booking.example/programs/#schedule')
        self.assertEqual(await self.page.locator('img').get_attribute('src'), 'https://booking.example/class.jpg')
        self.assertEqual(await self.page.locator('video').get_attribute('poster'), 'https://booking.example/programs/poster.jpg')
        self.assertEqual(await self.page.locator('form').get_attribute('action'), 'https://booking.example/programs/register')
        self.assertEqual(await self.page.locator('#duplicate').inner_text(), 'Parent')
        strategy.logger.error.assert_not_called()


if __name__ == '__main__':
    unittest.main()
