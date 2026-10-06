"""Serialize iframe HTML as data while retaining its original link base.

Crawl4AI 0.9.3 interpolates iframe HTML into a JavaScript template literal.
Publisher backslashes/interpolation tokens can corrupt or execute that literal.
Install this replacement on each pipeline-owned default Playwright strategy;
leave custom strategies and the shared dependency installation untouched.
"""
from types import MethodType

from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy
from crawl4ai.browser_adapter import PlaywrightAdapter


_READ_BODY = """() => {
    if (!document.body) return null;
    const body = document.body.cloneNode(true);
    for (const node of body.querySelectorAll('[href], [src], [poster], [action]')) {
        for (const name of ['href', 'src', 'poster', 'action']) {
            const value = node.getAttribute(name);
            if (value === null || !value.trim()) continue;
            try { node.setAttribute(name, new URL(value, document.baseURI).href); }
            catch (_) { /* Preserve an unparseable publisher value verbatim. */ }
        }
    }
    return body.innerHTML;
}"""

_REPLACE_FRAME = """(iframe, payload) => {
    const div = document.createElement('div');
    const doc = new DOMParser().parseFromString(payload.html, 'text/html');
    while (doc.body.firstChild) div.appendChild(doc.body.firstChild);
    div.className = payload.className;
    iframe.replaceWith(div);
}"""


async def _process_iframes(self, page):
    for index, iframe in enumerate(await page.query_selector_all('iframe')):
        try:
            frame = await iframe.content_frame()
            if frame is None:
                self.logger.warning(
                    message='Could not access content frame for iframe {index}',
                    tag='SCRAPE', params={'index': index})
                continue
            await frame.wait_for_load_state('load', timeout=30000)
            content = await frame.evaluate(_READ_BODY)
            if content is None:
                continue
            # The browser transports HTML as an argument, never as source code.
            # Use the actual element handle; author IDs need not be unique.
            await iframe.evaluate(_REPLACE_FRAME, {
                'html': content,
                'className': f'extracted-iframe-content-{index}',
            })
        except Exception as error:
            # Keep the original iframe on failure, as the dependency does.
            self.logger.error(message='Error processing iframe {index}: {error}',
                              tag='ERROR', params={'index': index, 'error': str(error)})
    return page


def install_safe_iframe_processing(web_crawler):
    """Patch only an unmodified default strategy on this crawler instance."""
    strategy = getattr(web_crawler, 'crawler_strategy', None)
    if not isinstance(strategy, AsyncPlaywrightCrawlerStrategy):
        return
    if type(getattr(strategy, 'adapter', None)) is not PlaywrightAdapter:
        return
    method = getattr(strategy, 'process_iframes', None)
    if getattr(method, '__func__', None) is AsyncPlaywrightCrawlerStrategy.process_iframes:
        strategy.process_iframes = MethodType(_process_iframes, strategy)
