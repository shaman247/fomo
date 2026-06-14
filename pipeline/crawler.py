"""
Web crawling module for the event processing pipeline.

Uses Crawl4AI to crawl event websites and store content in the database.
"""

import asyncio
import re
from datetime import datetime, timedelta
from crawl4ai import CacheMode
import db
import site_profiles
from constants import MAX_PAGES_DEFAULT, get_user_agent

# Default timeout for crawl operations (in seconds)
DEFAULT_CRAWL_TIMEOUT = 180


def _combine_js(*parts):
    """Concatenate js snippets into one script, dropping empties."""
    return "\n".join(p for p in parts if p)

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


def _build_md_generator(filter_threshold, ignore_links):
    """Build a DefaultMarkdownGenerator with an optional pruning content filter.

    If filter_threshold is explicitly 0 or None, the filter is disabled entirely
    and raw markdown is used.
    """
    if filter_threshold is not None and float(filter_threshold) > 0:
        threshold = float(filter_threshold)
        return DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(
                threshold=threshold, threshold_type="fixed", min_word_threshold=0
            ),
            options={"ignore_links": ignore_links},
        )
    # No content filter - use raw markdown
    return DefaultMarkdownGenerator(
        options={"ignore_links": ignore_links},
    )


_DATE_OFFSET_RE = re.compile(r'\{\{date([+-]\d+)?\}\}')


def resolve_url_templates(url):
    """Resolve date template placeholders in URLs.

    Supported placeholders:
        {{month}}           - current month name, lowercase (e.g. "february")
        {{year}}            - current year (e.g. "2026")
        {{next_month}}      - next month name, lowercase
        {{next_month_year}} - year of the next month (handles Dec→Jan rollover)
        {{date}}            - today's date in ISO format (YYYY-MM-DD)
        {{date+N}}          - today + N days, ISO format (e.g. {{date+7}})
        {{date-N}}          - today - N days, ISO format
    """
    if '{{' not in url:
        return url
    now = datetime.now()
    today = now.date()
    next_month_date = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
    replacements = {
        '{{month}}': now.strftime('%B').lower(),
        '{{year}}': str(now.year),
        '{{next_month}}': next_month_date.strftime('%B').lower(),
        '{{next_month_year}}': str(next_month_date.year),
    }
    for placeholder, value in replacements.items():
        url = url.replace(placeholder, value)
    url = _DATE_OFFSET_RE.sub(
        lambda m: (today + timedelta(days=int(m.group(1) or 0))).isoformat(),
        url,
    )
    return url


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

    def _url_of(u):
        return u['url'] if isinstance(u, dict) else u

    # Drop URLs handled out-of-band.
    crawlable = [u for u in urls if not site_profiles.is_skip_url(_url_of(u))]
    if not crawlable:
        reason = site_profiles.all_skip([_url_of(u) for u in urls]) or "all URLs skipped"
        print(f"  Skipping {name}: {reason}")
        return None
    urls = crawlable

    # Some platforms short-circuit crawl4ai entirely and fetch via a custom Python path.
    # If every URL resolves to one such fetcher, run it instead of the browser crawl.
    custom_profile = site_profiles.custom_fetch_profile([_url_of(u) for u in urls])
    if custom_profile is not None:
        label = custom_profile.display_label
        crawl_result_id = db.create_crawl_result(
            cursor, connection, crawl_run_id, website['id'], create_safe_filename(name, '.md')
        )
        try:
            md, n_events = custom_profile.fetcher()
        except Exception as exc:
            print(f"  ! {name}: {label} fetch failed: {exc}")
            db.update_crawl_result_failed(cursor, connection, crawl_result_id, f"{label}: {exc}")
            return None
        if not md:
            print(f"  ! {name}: {label} returned 0 events")
            db.update_crawl_result_failed(cursor, connection, crawl_result_id, f"{label} returned 0 events")
            return None
        db.update_crawl_result_crawled(cursor, connection, crawl_result_id, md)
        db.update_website_last_crawled(cursor, connection, website['id'])
        print(f"  + {name}: {label} → {n_events} events, {len(md)} bytes")
        return crawl_result_id

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
            max_pages = website.get('max_pages', MAX_PAGES_DEFAULT)
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
        page_timeout_ms = max(60000, crawl_timeout * 1000)  # At least 60s, scale with crawl_timeout

        # Configure markdown generator with optional content filter
        md_generator = _build_md_generator(filter_threshold, ignore_links=False)

        # Configure crawler
        # Note: Don't exclude 'form' as some sites wrap content in forms (e.g., Park Slope Parents calendar)
        # Note: Don't exclude 'header' as some sites use <header> inside articles for event titles (e.g., Prospect Park)
        def _make_config(js):
            return CrawlerRunConfig(
                word_count_threshold=5,
                excluded_tags=[],
                process_iframes=True,
                cache_mode=CacheMode.BYPASS,  # Don't use cache for fresh content
                js_code=js,
                remove_overlay_elements=remove_overlays,
                delay_before_return_html=delay_seconds,
                scan_full_page=scan_full_page,
                scroll_delay=scroll_delay,
                page_timeout=page_timeout_ms,
                wait_until='domcontentloaded',  # Use domcontentloaded instead of networkidle for faster/more reliable JS navigation
                ignore_body_visibility=True,  # Don't skip invisible body elements
                deep_crawl_strategy=deep_crawl_strategy,
                markdown_generator=md_generator,
            )

        crawler_config = _make_config(js_code)

        print(f"  Crawling {name} (timeout: {crawl_timeout}s)...")
        combined_markdown = ""

        async def crawl_urls():
            """Inner function to crawl all URLs, can be wrapped with timeout."""
            nonlocal combined_markdown
            for url_data in urls:
                # Handle both dict format (with js_code) and string format (legacy)
                if isinstance(url_data, dict):
                    url = resolve_url_templates(url_data['url'])
                    url_js_code = url_data.get('js_code')
                else:
                    url = resolve_url_templates(url_data)
                    url_js_code = None

                # Append platform-specific in-page js (e.g. Meetup listing URL
                # disambiguation) to whatever js_code is already configured for this
                # URL/website. See site_profiles.
                host_js = site_profiles.inject_js_for(url)
                effective_js = _combine_js(url_js_code or js_code, host_js)

                # Use a per-URL config when this URL needs js_code different from the
                # shared website-level config (custom per-URL js or a host-specific add-on).
                if effective_js != js_code:
                    url_config = _make_config(effective_js)
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


def get_browser_config(javascript_enabled=True, text_mode=True, light_mode=True, use_stealth=False, headed=False, user_agent=None):
    """
    Get the browser configuration for crawling.

    Args:
        javascript_enabled: Whether to enable JavaScript execution (default: True).
                           Set to False for sites that freeze during JS execution.
        text_mode: If True, disables images for faster text-only crawls (default: True).
        light_mode: If True, uses minimal browser features for speed (default: True).
        use_stealth: If True, uses undetected browser mode to bypass bot detection (default: False).
        headed: If True, run browser with a visible window (default: False, i.e. headless).
                Use this for sites that need a real window to render correctly.
        user_agent: Custom User-Agent string. If set, overrides the default browser UA.
                   Use this for sites that block the default headless Chrome UA with 403.

    Note: These are browser-level settings. All websites crawled with this
          config will share the same settings.
    """
    # Crawl4AI's default UA is Chrome/116 on Linux, which creates a UA/TLS fingerprint
    # mismatch that some CDNs (e.g. Fastly) detect and reject with 403. Always set a
    # realistic UA matching the actual browser to avoid this (see constants.get_user_agent).
    DEFAULT_USER_AGENT = get_user_agent()

    if use_stealth:
        # Stealth requires a real (headed) browser instance.
        return BrowserConfig(
            headless=False,
            java_script_enabled=javascript_enabled,
            text_mode=text_mode,
            light_mode=light_mode,
            use_managed_browser=True,
            enable_stealth=True,
            user_agent=user_agent or DEFAULT_USER_AGENT,
            extra_args=['--disable-blink-features=AutomationControlled']
        )
    else:
        config_kwargs = {
            'headless': not headed,
            'java_script_enabled': javascript_enabled,
            'text_mode': text_mode,
            'light_mode': light_mode,
            'user_agent': user_agent or DEFAULT_USER_AGENT,
        }
        return BrowserConfig(**config_kwargs)


def get_browser_key(settings):
    """Return a hashable key for grouping websites by browser settings.

    Websites with the same browser key can share a single AsyncWebCrawler
    instance (same text_mode, light_mode, stealth, headed, user_agent).
    Stealth implies headed, so `headed` is OR'd with `use_stealth` here to
    keep stealth sites from splitting into a redundant headless batch.
    """
    use_stealth = settings.get('use_stealth') if settings.get('use_stealth') is not None else False
    headed_setting = settings.get('headed') if settings.get('headed') is not None else False
    return (
        settings.get('text_mode') if settings.get('text_mode') is not None else True,
        settings.get('light_mode') if settings.get('light_mode') is not None else True,
        bool(use_stealth),
        bool(use_stealth) or bool(headed_setting),
        settings.get('user_agent'),
    )


def build_event_crawl_config(website_settings):
    """
    Build a CrawlerRunConfig for crawling an individual event URL.

    Uses the same per-website settings as the main crawl, but without
    js_code, deep crawling, or click-based pagination (those are for
    listing pages, not individual event pages).

    Args:
        website_settings: Dict with keys like delay_before_return_html,
            content_filter_threshold, scan_full_page, remove_overlay_elements,
            scroll_delay.
    """
    ws = website_settings
    delay = min(ws.get('delay_before_return_html') or 5, 10)  # Cap at 10s for individual event pages
    filter_threshold = ws.get('content_filter_threshold')
    scan = False  # Don't scroll full page for individual event pages
    overlays = ws.get('remove_overlay_elements', False)
    sd = ws.get('scroll_delay') or 0.2

    md_generator = _build_md_generator(filter_threshold, ignore_links=True)

    return CrawlerRunConfig(
        word_count_threshold=5,
        excluded_tags=[],
        process_iframes=True,
        cache_mode=CacheMode.BYPASS,
        remove_overlay_elements=overlays,
        delay_before_return_html=delay,
        scan_full_page=scan,
        scroll_delay=sd,
        page_timeout=60000,
        wait_until='domcontentloaded',
        ignore_body_visibility=True,
        markdown_generator=md_generator,
    )


async def crawl_event_url(web_crawler, url, crawl_config, timeout=120):
    """
    Crawl a single event URL and return its markdown content.

    Wraps the crawl in a hard ``asyncio.wait_for`` ceiling so a single hung
    page (e.g. a broken/slow iframe under ``process_iframes=True``) cannot
    block forever and starve the shared worker semaphore in Step 5. The
    page-level ``page_timeout`` is 60s; this outer ceiling (default 120s)
    covers iframe processing and any browser-level wedge crawl4ai's own
    timeout fails to interrupt.

    Returns the page content (truncated to 12K chars) or None on failure.
    """
    try:
        result = await asyncio.wait_for(
            web_crawler.arun(url=url, config=crawl_config),
            timeout=timeout,
        )
        if result.success and result.markdown:
            content = result.markdown.fit_markdown or result.markdown.raw_markdown
            if content and len(content) > 50:
                return content[:12000]
    except asyncio.TimeoutError:
        print(f"    Crawl timed out after {timeout}s for {url}")
    except Exception as e:
        print(f"    Crawl error for {url}: {e}")
    return None
