"""
Web crawling module for the event processing pipeline.

Uses Crawl4AI to crawl event websites and store content in the database.
"""

import db

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
        selector = website.get('selector')
        num_clicks = website.get('num_clicks', 2)

        if selector and num_clicks:
            js_code = f"for (let i = 0; i < {num_clicks}; i++) {{await new Promise(resolve => setTimeout(resolve, 1000)); document.querySelector('{selector}').click();}}"
        else:
            js_code = ""

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

        # Configure crawler
        crawler_config = CrawlerRunConfig(
            js_code=js_code,
            remove_overlay_elements=True,
            delay_before_return_html=3,
            scan_full_page=True,
            deep_crawl_strategy=deep_crawl_strategy,
            markdown_generator=DefaultMarkdownGenerator(
                content_filter=PruningContentFilter(
                    threshold=0.48, threshold_type="fixed", min_word_threshold=0
                ),
                options={"ignore_links": False},
            ),
        )

        print(f"  Crawling {name}...")
        combined_markdown = ""

        for url in urls:
            print(f"    - Processing {url}")
            url_content = ""

            for result in await crawler.arun(url=url, config=crawler_config):
                if result and result.markdown and result.markdown.fit_markdown:
                    url_content += result.markdown.fit_markdown + "\n\n"

            if url_content:
                combined_markdown += url + "\n" + url_content

        if not combined_markdown.strip():
            db.update_crawl_result_failed(
                cursor, connection, crawl_result_id, "No content retrieved"
            )
            # Still update last_crawled_at to prevent immediate retry
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


def get_browser_config():
    """Get the browser configuration for crawling."""
    return BrowserConfig(
        headless=False,
        java_script_enabled=True,
    )
