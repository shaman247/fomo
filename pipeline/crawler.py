"""
Web crawling module for the event processing pipeline.

Uses Crawl4AI to crawl event websites and store content in the database.
"""

import asyncio
import json
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

# Bot-challenge interstitials (Cloudflare, Imperva) render as a tiny page that
# slips past MIN_CRAWL_CONTENT_SIZE (observed 505-870 bytes), so without an
# explicit check they get stored as a *successful* crawl that extracts 0 events
# — which then feeds the merger's archival logic and can retire live events.
# These challenges are transient and IP-reputation scored: the same URL that is
# challenged mid-run fetches cleanly minutes later, so detection triggers a
# retry rather than a permanent per-site setting change.
BOT_CHALLENGE_MARKERS = (
    'performing security verification',
    'verification successful. waiting for',
    'sorry, you have been blocked',
    'checking your browser before accessing',
    'attention required! | cloudflare',
    'just a moment...',
    'please enable cookies',
)

# Cloudflare's 5xx interstitials are the same class of problem: the origin (or
# the CF edge) failed, but CF serves a small, well-formed HTML *error* page with
# a 200-ish body from the crawler's perspective. Observed at 953 bytes for
# website 88 on 2026-07-20 — comfortably past MIN_CRAWL_CONTENT_SIZE, so it was
# stored as a successful 0-event crawl and the merger archived live events.
# These are transient too (bad gateway / origin timeout), so they route through
# the same detect-and-retry path rather than any permanent site change.
CLOUDFLARE_ERROR_CODES = ('502', '503', '520', '521', '522', '523', '524')

# "Error code 502", "Error code: 522", etc. CF renders the code next to the
# human-readable title ("Bad gateway", "Web server is down", ...).
_CF_ERROR_CODE_RE = re.compile(
    r'error\s*code[:\s]*(?:' + '|'.join(CLOUDFLARE_ERROR_CODES) + r')\b'
)

# Corroborating evidence that the small page came from Cloudflare rather than
# being a real page that happens to mention an error code.
CLOUDFLARE_MARKERS = (
    'cloudflare',
    '5xx-error-landing',
)

# Challenge interstitials are tiny; requiring a small page avoids false
# positives on real event pages that happen to quote one of the phrases.
BOT_CHALLENGE_MAX_CHARS = 4000


def _is_cloudflare_error_page(lowered):
    """True if the (lowercased) body is a Cloudflare 5xx error interstitial.

    Requires BOTH a Cloudflare fingerprint and a 5xx code from the CF-origin
    family, so a genuine page quoting "error code 502" is not flagged.
    """
    if not any(marker in lowered for marker in CLOUDFLARE_MARKERS):
        return False
    return bool(_CF_ERROR_CODE_RE.search(lowered))


def _is_bot_challenge(content):
    """True if content is an interstitial (bot challenge or CF 5xx), not real content."""
    if not content or len(content) > BOT_CHALLENGE_MAX_CHARS:
        return False
    lowered = content.lower()
    if any(marker in lowered for marker in BOT_CHALLENGE_MARKERS):
        return True
    return _is_cloudflare_error_page(lowered)


# A JSON API feed that legitimately has nothing to serve right now
# ({"data":{"events":[],"has_next_page":false},"success":true} = 65 bytes) turns
# into a ~163-byte combined_markdown (the URL line plus the payload) and trips
# MIN_CRAWL_CONTENT_SIZE, so a *successful* crawl whose correct answer is "0
# events" is stored as status='failed'. That is only cosmetically safe today (a
# failed status blocks archival), but it fires on every JSON-feed source that
# empties out and it buries genuine failures in the same bucket.
#
# The carve-out is deliberately narrow so it cannot widen the Cloudflare hole:
# challenge and 5xx interstitials are HTML rendered to markdown and never parse
# as JSON, and _is_bot_challenge() is still consulted here (as well as per-URL,
# earlier). A truncated/garbled body also fails json.loads, so it keeps failing.
_URL_ONLY_LINE_RE = re.compile(r'^\s*https?://\S+\s*$')
_CODE_FENCE_LINE_RE = re.compile(r'^\s*```[a-z]*\s*$', re.IGNORECASE)


def _is_json_api_payload(content):
    """True if the crawl body is nothing but a well-formed JSON API document.

    `combined_markdown` is built as "<url>\\n<body>" per URL, and crawl4ai
    sometimes fences a raw JSON body, so both are stripped before parsing.
    Only objects and arrays count — a bare scalar ("null", "0", a quoted error
    string) is not a well-formed API response and must keep failing.
    """
    if not content or _is_bot_challenge(content):
        return False
    lines = [
        line for line in content.splitlines()
        if line.strip()
        and not _URL_ONLY_LINE_RE.match(line)
        and not _CODE_FENCE_LINE_RE.match(line)
    ]
    payload = '\n'.join(lines).strip()
    if not payload or payload[0] not in '{[':
        return False
    try:
        parsed = json.loads(payload)
    except (ValueError, TypeError):
        return False
    if isinstance(parsed, dict):
        # An empty object carries no API shape at all — treat like garbage.
        return bool(parsed)
    return isinstance(parsed, list)

try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
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
_MDY_OFFSET_RE = re.compile(r'\{\{mdy([+-]\d+)?\}\}')


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
        {{mdy}} / {{mdy+N}} / {{mdy-N}}
                            - same offsets in MM/DD/YY form (e.g. "08/15/26"),
                              for query strings that expect US short dates
                              (e.g. the Queens Public Library Solr filter)
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
    url = _MDY_OFFSET_RE.sub(
        lambda m: (today + timedelta(days=int(m.group(1) or 0))).strftime('%m/%d/%y'),
        url,
    )
    return url


async def _refetch_past_challenge(url, url_config, user_agent, attempts=2, backoff=15,
                                  timeout=120):
    """Re-fetch a URL that returned a bot-challenge interstitial.

    Uses a fresh, full-featured browser: ``text_mode``/``light_mode`` strip the
    image, font and canvas machinery Cloudflare's JS challenge needs to finish
    (that is the "Verification successful. Waiting for X to respond" dead end),
    and a new browser instance drops any challenge cookie that got wedged in the
    shared crawler. Returns recovered markdown, or None if still challenged.

    Called *after* the main crawl loop's timeout window so the backoff sleeps
    never eat into ``crawl_timeout``. ``timeout`` bounds each individual
    re-fetch; the detail-crawl path passes a smaller value so its total retry
    budget stays inside Step 5's stall watchdog (see ``crawl_event_url``).
    """
    for attempt in range(1, attempts + 1):
        await asyncio.sleep(backoff * attempt)
        browser_config = get_browser_config(
            javascript_enabled=True,
            text_mode=False,
            light_mode=False,
            use_stealth=False,
            user_agent=user_agent,
        )
        try:
            async with AsyncWebCrawler(config=browser_config) as retry_crawler:
                content = ""
                results = await asyncio.wait_for(
                    retry_crawler.arun(url=url, config=url_config), timeout=timeout
                )
                for result in results:
                    if result and result.markdown:
                        chunk = result.markdown.fit_markdown
                        if not chunk or len(chunk) < 500:
                            chunk = result.markdown.raw_markdown
                        if chunk:
                            content += chunk + "\n\n"
            if content and not _is_bot_challenge(content):
                print(f"      Challenge cleared on retry {attempt} ({len(content)} chars)")
                return content
            print(f"      Retry {attempt}: still challenged")
        except Exception as exc:
            print(f"      Retry {attempt} errored: {exc}")
    return None


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
        # URLs that came back as a bot-challenge interstitial, retried after the
        # timed crawl loop so the backoff doesn't count against crawl_timeout.
        challenged_urls = []

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
                if _is_bot_challenge(url_content):
                    print(f"    - Challenge/error interstitial ({len(url_content)} chars) - queued for retry")
                    challenged_urls.append((url, url_config))
                    continue
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

        # Retry any URL that hit a bot challenge. Runs outside the crawl_timeout
        # window above so the backoff sleeps don't truncate the crawl.
        unresolved_challenges = 0
        for challenged_url, challenged_config in challenged_urls:
            print(f"    - Retrying challenged URL: {challenged_url}")
            recovered = await _refetch_past_challenge(
                challenged_url, challenged_config, website.get('user_agent')
            )
            if recovered:
                combined_markdown += challenged_url + "\n" + recovered
            else:
                unresolved_challenges += 1

        if not combined_markdown.strip():
            # Distinguish a genuine empty crawl from an unbeaten bot challenge:
            # storing the challenge page as content would look like a successful
            # crawl with 0 events and feed the merger's archival logic.
            error_msg = (
                f"Bot challenge / origin error page not cleared after retries ({unresolved_challenges} URL(s))"
                if unresolved_challenges else "No content retrieved"
            )
            db.update_crawl_result_failed(
                cursor, connection, crawl_result_id, error_msg
            )
            # Still update last_crawled_at to prevent immediate retry
            db.update_website_last_crawled(cursor, connection, website['id'])
            return None

        # Check for minimum content size to catch failed crawls early
        # (e.g., JS-rendered pages that only returned the URL)
        content_size = len(combined_markdown)
        if content_size < MIN_CRAWL_CONTENT_SIZE:
            # A JSON feed that legitimately returned no events is short but not
            # broken — store it as the successful 0-event crawl it is.
            if _is_json_api_payload(combined_markdown):
                print(f"    - Small ({content_size} bytes) but a well-formed JSON API response - accepting as an empty feed")
            else:
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


# Minimum body length for a detail page to count as real content. Detail pages
# are legitimately short (a title, a date, two sentences), so this floor is much
# lower than MIN_CRAWL_CONTENT_SIZE — which is exactly why a 505-870 byte
# Cloudflare interstitial sailed through it and got stored as the event page.
MIN_EVENT_PAGE_SIZE = 50

# Retry budget for a challenged detail page, spent *inside* one detail-crawl
# attempt. Step 5 increments `crawl_events.detail_crawl_attempts` once per
# candidate regardless of outcome, and `db.get_detail_crawl_candidates` caps at
# `detail_crawl_attempts < 2` — so a challenge that returns None with no retry
# permanently burns 1 of only 2 chances on a page that was never actually read.
# Retrying in-call makes the attempt count for a real fetch instead.
#
# Bound (no infinite loop): at most 1 initial fetch + DETAIL_CHALLENGE_RETRIES
# re-fetches per attempt, and Step 5 still allows only 2 attempts per event, so
# a genuinely blocked site costs at most 6 fetches ever, then stops.
#
# Sizing: Step 5's watchdog aborts a batch after 300s with no progress, so the
# worst case here must stay under that — 120s initial + (5s + 60s) +
# (10s + 60s) = 255s. Hence the short backoff and the reduced per-retry timeout.
DETAIL_CHALLENGE_RETRIES = 2
DETAIL_CHALLENGE_BACKOFF = 5
DETAIL_CHALLENGE_TIMEOUT = 60


async def crawl_event_url(web_crawler, url, crawl_config, timeout=120, user_agent=None):
    """
    Crawl a single event URL and return its markdown content.

    Wraps the crawl in a hard ``asyncio.wait_for`` ceiling so a single hung
    page (e.g. a broken/slow iframe under ``process_iframes=True``) cannot
    block forever and starve the shared worker semaphore in Step 5. The
    page-level ``page_timeout`` is 60s; this outer ceiling (default 120s)
    covers iframe processing and any browser-level wedge crawl4ai's own
    timeout fails to interrupt.

    A bot-challenge / Cloudflare-error interstitial is *not* content: storing it
    would hand Gemini an interstitial to "enrich" from and would burn one of the
    two detail-crawl attempts an event ever gets. Challenges are transient and
    IP-reputation scored, so they route through the same
    ``_refetch_past_challenge`` recovery the main crawl loop uses (fresh browser,
    ``text_mode``/``light_mode`` off) before giving up.

    Returns the page content (truncated to 12K chars) or None on failure.
    """
    content = await _fetch_event_page(web_crawler, url, crawl_config, timeout)
    if not content:
        return None

    if not _is_bot_challenge(content):
        return content[:12000]

    # Spend the retry budget here rather than losing the whole attempt.
    print(f"    Challenge/error interstitial ({len(content)} chars) for {url} - retrying")
    recovered = await _refetch_past_challenge(
        url, crawl_config, user_agent,
        attempts=DETAIL_CHALLENGE_RETRIES,
        backoff=DETAIL_CHALLENGE_BACKOFF,
        timeout=DETAIL_CHALLENGE_TIMEOUT,
    )
    if recovered and len(recovered) > MIN_EVENT_PAGE_SIZE:
        return recovered[:12000]
    print(f"    Still challenged after retries - discarding interstitial for {url}")
    return None


async def _fetch_event_page(web_crawler, url, crawl_config, timeout):
    """One detail-page fetch. Returns raw content, or None if it failed/was empty."""
    try:
        result = await asyncio.wait_for(
            web_crawler.arun(url=url, config=crawl_config),
            timeout=timeout,
        )
        if result.success and result.markdown:
            content = result.markdown.fit_markdown or result.markdown.raw_markdown
            if content and len(content) > MIN_EVENT_PAGE_SIZE:
                return content
    except asyncio.TimeoutError:
        print(f"    Crawl timed out after {timeout}s for {url}")
    except Exception as e:
        print(f"    Crawl error for {url}: {e}")
    return None
    return None
