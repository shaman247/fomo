"""
Web crawling module for the event processing pipeline.

Uses Crawl4AI to crawl event websites and store content in the database.
"""

import asyncio
from crawl4ai import CacheMode
import db

# Default timeout for crawl operations (in seconds)
DEFAULT_CRAWL_TIMEOUT = 180

# Minimum content size (in bytes) to consider a crawl successful.
# Crawls with less content than this are likely failed (e.g., JS-rendered
# pages that didn't load properly) and should be marked as failed.
MIN_CRAWL_CONTENT_SIZE = 500

try:
    from crawl4ai import BrowserConfig, CrawlerRunConfig
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    from crawl4ai.content_filter_strategy import PruningContentFilter
    from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
    from crawl4ai.deep_crawling.filters import FilterChain, URLPatternFilter
except ImportError:
    print("Error: crawl4ai is required.")
    print("Install it with: pip install crawl4ai")
    raise


def create_safe_filename(name, extension=None):
    """Generate a safe filesystem name from a string."""
    safe = "".join(c for c in name if c.isalnum() or c in (' ', '_')).rstrip()
    safe = safe.replace(' ', '_').lower()
    if extension:
        safe += extension
    return safe


async def crawl_website(crawler, website, cursor, connection, crawl_run_id):
    """
    Crawl a website and store the content in the database.

    Args:
        crawler: AsyncWebCrawler instance
        website: Website dict with urls, name, selector, etc.
        cursor: Database cursor
        connection: Database connection
        crawl_run_id: ID of the current crawl run

    Returns:
        crawl_result_id if successful, None otherwise
    """
    name = website['name']
    urls = website['urls']

    if not urls:
        print(f"  Skipping {name}: no URLs configured")
        return None

    # Create safe filename from website name
    safe_filename = create_safe_filename(name, '.md')

    # Create crawl result record
    crawl_result_id = db.create_crawl_result(
        cursor, connection, crawl_run_id, website['id'], safe_filename
    )

    try:
        # Generate JavaScript code for dynamic content loading
        # Use custom js_code from database if set, otherwise generate from selector/num_clicks
        js_code = website.get('js_code') or ""
        if not js_code:
            selector = website.get('selector')
            num_clicks = website.get('num_clicks', 2)
            if selector and num_clicks:
                js_code = f"for (let i = 0; i < {num_clicks}; i++) {{await new Promise(resolve => setTimeout(resolve, 1000)); document.querySelector('{selector}').click();}}"

        # Configure deep crawling strategy based on keywords
        keywords = website.get('keywords')
        if keywords:
            filters = [f"*{k.strip()}*" for k in keywords.split(', ')]
            max_pages = website.get('max_pages', 30)
            url_filter = URLPatternFilter(patterns=filters)
            deep_crawl_strategy = BestFirstCrawlingStrategy(
                max_depth=1,
                include_external=True,
                filter_chain=FilterChain([url_filter]),
                max_pages=max_pages
            )
        else:
            deep_crawl_strategy = BestFirstCrawlingStrategy(max_depth=0)

        # Get per-website crawl settings (with defaults)
        delay_seconds = website.get('delay_before_return_html') or 5
        filter_threshold = website.get('content_filter_threshold')
        scan_full_page = website.get('scan_full_page', True)
        remove_overlays = website.get('remove_overlay_elements', False)
        scroll_delay = website.get('scroll_delay') or 0.2
        crawl_timeout = website.get('crawl_timeout') or DEFAULT_CRAWL_TIMEOUT

        # Configure markdown generator with optional content filter
        # If filter_threshold is explicitly 0 or None, disable the filter entirely
        if filter_threshold is not None and float(filter_threshold) > 0:
            md_generator = DefaultMarkdownGenerator(
                content_filter=PruningContentFilter(
                    threshold=float(filter_threshold), threshold_type="fixed", min_word_threshold=0
                ),
                options={"ignore_links": False},
            )
        else:
            # No content filter - use raw markdown
            md_generator = DefaultMarkdownGenerator(
                options={"ignore_links": False},
            )

        # Configure crawler
        # Note: Don't exclude 'form' as some sites wrap content in forms (e.g., Park Slope Parents calendar)
        # Note: Don't exclude 'header' as some sites use <header> inside articles for event titles (e.g., Prospect Park)
        crawler_config = CrawlerRunConfig(
            word_count_threshold=5,
            excluded_tags=[],
            process_iframes=True,
            cache_mode=CacheMode.BYPASS,  # Don't use cache for fresh content
            js_code=js_code,
            remove_overlay_elements=remove_overlays,
            delay_before_return_html=delay_seconds,
            scan_full_page=scan_full_page,
            scroll_delay=scroll_delay,
            page_timeout=60000,
            wait_until='domcontentloaded',  # Use domcontentloaded instead of networkidle for faster/more reliable JS navigation
            ignore_body_visibility=True,  # Don't skip invisible body elements
            deep_crawl_strategy=deep_crawl_strategy,
            markdown_generator=md_generator,
        )

        print(f"  Crawling {name} (timeout: {crawl_timeout}s)...")
        combined_markdown = ""

        async def crawl_urls():
            """Inner function to crawl all URLs, can be wrapped with timeout."""
            nonlocal combined_markdown
            for url_data in urls:
                # Handle both dict format (with js_code) and string format (legacy)
                if isinstance(url_data, dict):
                    url = url_data['url']
                    url_js_code = url_data.get('js_code')
                else:
                    url = url_data
                    url_js_code = None

                # Use per-URL js_code if set, otherwise use website-level config
                if url_js_code:
                    url_config = CrawlerRunConfig(
                        word_count_threshold=5,
                        excluded_tags=[],
                        process_iframes=True,
                        cache_mode=CacheMode.BYPASS,
                        js_code=url_js_code,
                        remove_overlay_elements=remove_overlays,
                        delay_before_return_html=delay_seconds,
                        scan_full_page=scan_full_page,
                        scroll_delay=scroll_delay,
                        page_timeout=60000,
                        wait_until='domcontentloaded',
                        ignore_body_visibility=True,
                        deep_crawl_strategy=deep_crawl_strategy,
                        markdown_generator=md_generator,
                    )
                else:
                    url_config = crawler_config

                print(f"    - Processing {url}")
                url_content = ""
                page_count = 0

                for result in await crawler.arun(url=url, config=url_config):
                    page_count += 1
                    # Debug: show what we received
                    html_len = len(result.html) if result and result.html else 0
                    has_error = bool(result.error_message) if result else False
                    print(f"      Page {page_count}: html={html_len}, success={result.success if result else False}, error={result.error_message if has_error else 'none'}")

                    # Debug: warn if HTML has no body (crawl4ai bug on some sites)
                    if result and result.html and html_len > 1000:
                        raw_len = len(result.markdown.raw_markdown) if result.markdown and result.markdown.raw_markdown else 0
                        has_body = '<body' in result.html.lower()
                        if not has_body:
                            print(f"      WARNING: HTML missing body tag (html={html_len}, raw_md={raw_len}) - possible crawl4ai bug")

                    if result and result.markdown:
                        # Use fit_markdown if available, otherwise fall back to raw_markdown
                        fit_len = len(result.markdown.fit_markdown) if result.markdown.fit_markdown else 0
                        raw_len = len(result.markdown.raw_markdown) if result.markdown.raw_markdown else 0
                        content = result.markdown.fit_markdown
                        if not content or len(content) < 500:
                            # fit_markdown too small, use raw_markdown
                            content = result.markdown.raw_markdown
                        if content:
                            url_content += content + "\n\n"
                        print(f"      Page {page_count}: fit={fit_len}, raw={raw_len}, using={len(content) if content else 0}")

                print(f"    - Crawled {page_count} page(s), {len(url_content)} chars total")
                if url_content:
                    combined_markdown += url + "\n" + url_content

        # Execute crawl with timeout
        try:
            await asyncio.wait_for(crawl_urls(), timeout=crawl_timeout)
        except asyncio.TimeoutError:
            error_msg = f"Crawl timed out after {crawl_timeout} seconds"
            print(f"    - {error_msg}")
            # If we got partial content, still save it
            if combined_markdown.strip():
                print(f"    - Saving partial content ({len(combined_markdown)} chars)")
                db.update_crawl_result_crawled(cursor, connection, crawl_result_id, combined_markdown)
                db.update_website_last_crawled(cursor, connection, website['id'])
                return crawl_result_id
            # No content at all
            db.update_crawl_result_failed(cursor, connection, crawl_result_id, error_msg)
            db.update_website_last_crawled(cursor, connection, website['id'])
            return None

        if not combined_markdown.strip():
            db.update_crawl_result_failed(
                cursor, connection, crawl_result_id, "No content retrieved"
            )
            # Still update last_crawled_at to prevent immediate retry
            db.update_website_last_crawled(cursor, connection, website['id'])
            return None

        # Check for minimum content size to catch failed crawls early
        # (e.g., JS-rendered pages that only returned the URL)
        content_size = len(combined_markdown)
        if content_size < MIN_CRAWL_CONTENT_SIZE:
            error_msg = f"Crawled content too small ({content_size} bytes < {MIN_CRAWL_CONTENT_SIZE} minimum) - likely failed to load page content"
            print(f"    - {error_msg}")
            db.update_crawl_result_failed(cursor, connection, crawl_result_id, error_msg)
            db.update_website_last_crawled(cursor, connection, website['id'])
            return None

        # Store crawled content in database
        db.update_crawl_result_crawled(cursor, connection, crawl_result_id, combined_markdown)
        db.update_website_last_crawled(cursor, connection, website['id'])

        print(f"    - Stored {len(combined_markdown)} characters of content")
        return crawl_result_id

    except Exception as e:
        error_msg = str(e)
        print(f"    - Error crawling {name}: {error_msg}")
        db.update_crawl_result_failed(cursor, connection, crawl_result_id, error_msg)
        # Still update last_crawled_at to prevent immediate retry
        db.update_website_last_crawled(cursor, connection, website['id'])
        return None


def get_browser_config(javascript_enabled=True, text_mode=True, light_mode=True, use_stealth=False):
    """
    Get the browser configuration for crawling.

    Args:
        javascript_enabled: Whether to enable JavaScript execution (default: True).
                           Set to False for sites that freeze during JS execution.
        text_mode: If True, disables images for faster text-only crawls (default: True).
        light_mode: If True, uses minimal browser features for speed (default: True).
        use_stealth: If True, uses undetected browser mode to bypass bot detection (default: False).
                    Required for sites like Resident Advisor that have verification pages.

    Note: These are browser-level settings. All websites crawled with this
          config will share the same settings.
    """
    if use_stealth:
        # Use undetected browser mode with stealth features for bot detection bypass
        return BrowserConfig(
            headless=False,
            java_script_enabled=javascript_enabled,
            text_mode=text_mode,
            light_mode=light_mode,
            use_managed_browser=True,
            enable_stealth=True,
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            extra_args=['--disable-blink-features=AutomationControlled']
        )
    else:
        # Standard browser mode
        return BrowserConfig(
            headless=False,
            java_script_enabled=javascript_enabled,
            text_mode=text_mode,
            light_mode=light_mode
        )
