"""
Website Crawler Script

This script crawls event websites and saves their content as markdown files.
It includes intelligent features like:
- Frequency-based crawling to avoid redundant requests
- Automatic archiving of old crawl data
- Deep crawling with keyword filtering
- JavaScript execution for dynamic content

Configuration:
- Website list is loaded from data/websites.json
- Each website can specify crawl frequency, keywords, and custom JavaScript
"""

import asyncio
import json
import os
import glob
from datetime import datetime
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from crawl4ai.deep_crawling.filters import (
    FilterChain,
    URLPatternFilter,
    DomainFilter,
    ContentTypeFilter,
    ContentRelevanceFilter,
    SEOFilter,
)

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def _archive_old_files(date_str, filename):
    """
    Archive old crawl data before re-crawling a website.

    Moves old files from crawled/, extracted/, and processed/ directories
    to archived/YYYYMMDD/ to keep a history of past crawls.

    Args:
        date_str: Date string in YYYYMMDD format
        filename: Base filename to archive (without extension)
    """
    archive_base_dir = os.path.join(SCRIPT_DIR, "..", "event_data", "archived")

    # Map directories to their file extensions
    dirs_to_check = {
        os.path.join(SCRIPT_DIR, "..", "event_data", "crawled"): ".md",
        os.path.join(SCRIPT_DIR, "..", "event_data", "extracted"): ".md",
        os.path.join(SCRIPT_DIR, "..", "event_data", "processed"): ".json"
    }

    # Create archive directory structure: archived/YYYYMMDD/crawled/, etc.
    archive_date_dir = os.path.join(archive_base_dir, date_str)
    for dir_name in dirs_to_check:
        os.makedirs(os.path.join(archive_date_dir, os.path.basename(dir_name)), exist_ok=True)

    # Move old files to archive
    for dir_name, extension in dirs_to_check.items():
        old_file_path = os.path.join(dir_name, date_str, f"{filename}{extension}")
        if os.path.exists(old_file_path):
            archive_path = os.path.join(archive_date_dir, os.path.basename(dir_name), f"{filename}{extension}")
            print(f"  - Archiving old file: {old_file_path} to {archive_path}")
            os.rename(old_file_path, archive_path)

    # Clean up empty directories after archiving
    for dir_name in dirs_to_check:
        date_dir = os.path.join(dir_name, date_str)
        if os.path.exists(date_dir) and os.path.isdir(date_dir):
            if not os.listdir(date_dir):
                print(f"  - Deleting empty directory: {date_dir}")
                os.rmdir(date_dir)

async def crawl_website(crawler, website_info):
    """
    Crawl a single website and save its content as markdown.

    Implements frequency-based crawling: if a recent crawl exists (within crawl_frequency days),
    the crawl is skipped. Otherwise, old files are archived and a new crawl is performed.

    Args:
        crawler: AsyncWebCrawler instance
        website_info: Dictionary containing website configuration from websites.json
    """
    name = website_info.get("name")
    if not name:
        print(f"Skipping entry due to missing 'name': {website_info}")
        return

    # Create safe filename from website name
    safe_filename = "".join(c for c in name if c.isalnum() or c in (' ', '_')).rstrip()
    safe_filename_pattern = safe_filename.replace(' ', '_').lower()
    current_date = datetime.now()
    crawl_frequency = website_info.get("crawl_frequency", 7)  # Default: crawl every 7 days

    output_dir = os.path.join(SCRIPT_DIR, "..", "event_data", "crawled")
    os.makedirs(output_dir, exist_ok=True)

    # Check for existing crawl files and skip if recent
    for date_subdir in glob.glob(os.path.join(output_dir, "????????")):
        if not os.path.isdir(date_subdir):
            continue

        date_str = os.path.basename(date_subdir)
        existing_file = os.path.join(date_subdir, f"{safe_filename_pattern}.md")

        if os.path.exists(existing_file):
            try:
                file_date = datetime.strptime(date_str, '%Y%m%d')
                days_since_crawl = (current_date - file_date).days

                if days_since_crawl < crawl_frequency:
                    # Skip crawling - file is recent enough
                    #print(f"Skipping {name} as it was crawled {days_since_crawl} day(s) ago (frequency: {crawl_frequency} days).")
                    return
                else:
                    # File is old, archive it before re-crawling
                    _archive_old_files(date_str, safe_filename_pattern)
            except (ValueError, IndexError):
                # Ignore files with malformed date strings
                continue


    urls_to_crawl = website_info.get("urls", [])

    # Generate JavaScript code for dynamic content loading
    # If selector and num_clicks are specified, generate click automation code
    selector = website_info.get("selector")
    num_clicks = website_info.get("num_clicks")
    if not num_clicks: num_clicks = 2

    if selector and num_clicks:
        # Auto-generate JS to click "Load More" buttons or similar elements
        js_code = f"for (let i = 0; i < {num_clicks}; i++) {{await new Promise(resolve => setTimeout(resolve, 1000)); document.querySelector('{selector}').click();}}"
    else:
        # Use custom JS code if provided
        js_code = website_info.get("js_code", "")

    print(js_code)

    # Configure deep crawling strategy based on keywords
    keywords = website_info.get("keywords")
    if keywords:
        # Deep crawl with keyword filtering to find relevant event pages
        filters = [f"*{k.strip()}*" for k in keywords.split(', ')]
        max_pages = website_info.get("max_pages", 30)
        url_filter = URLPatternFilter(patterns=filters)
        deep_crawl_strategy = BestFirstCrawlingStrategy(
            max_depth=1,
            include_external=True,
            filter_chain=FilterChain([url_filter]),
            max_pages=max_pages
        )
    else:
        # No deep crawl - only process the initial URLs
        deep_crawl_strategy = BestFirstCrawlingStrategy(max_depth=0)

    # Configure crawler with content filtering and markdown generation
    crawler_config = CrawlerRunConfig(
        js_code=js_code,
        remove_overlay_elements=True,  # Remove popups, modals, etc.
        delay_before_return_html=3,    # Wait for dynamic content to load
        scan_full_page=True,            # Scroll through entire page
        deep_crawl_strategy=deep_crawl_strategy,
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(
                threshold=0.48, threshold_type="fixed", min_word_threshold=0
            ),
            options={"ignore_links": False},
        ),
    )

    if not urls_to_crawl:
        print(f"Skipping entry due to missing 'urls' or 'name': {website_info}")
        return

    # Crawl all URLs and combine the markdown content
    print(f"Crawling {name}...")
    combined_markdown = ""
    for url in urls_to_crawl:
        print(f"  - Processing {url}")
        for result in await crawler.arun(
            url=url,
            config=crawler_config,
        ):
            if result and result.markdown and result.markdown.fit_markdown:
                score = result.metadata.get("score", 0)
                print(f"Score: {score:.2f} | {result.url}")
                combined_markdown += result.markdown.fit_markdown + "\n\n"
                print(f"    - Fit Markdown Length: {len(result.markdown.fit_markdown)}")
            else:
                print(f"    - Failed to retrieve markdown for {result.url if result else url}. Skipping.")

    # Save combined markdown to dated directory
    current_date_str = current_date.strftime('%Y%m%d')
    dated_output_dir = os.path.join(output_dir, current_date_str)
    os.makedirs(dated_output_dir, exist_ok=True)

    output_filename = os.path.join(dated_output_dir, f"{safe_filename.replace(' ', '_').lower()}.md")

    with open(output_filename, 'w', encoding='utf-8') as f:
        # Write source URL as first line for reference
        if urls_to_crawl:
            f.write(urls_to_crawl[0] + "\n")
        f.write(combined_markdown)

    print(f"Saved content for {name} to {output_filename}")
    print(f"  - Total Combined Markdown Length: {len(combined_markdown)}")

async def main():
    """
    Main function to crawl all configured websites.

    Reads website configurations from data/websites.json and crawls each
    non-disabled website using a headless browser with stealth mode.
    """
    # Configure browser for crawling
    browser_config = BrowserConfig(
        headless=False,           # Set to True to run without UI
        enable_stealth=True,      # Avoid bot detection
        java_script_enabled=True, # Required for dynamic content
        text_mode=True,           # Optimize for text extraction
    )

    # Load website configurations
    with open(os.path.join(SCRIPT_DIR, 'data', 'websites.json'), 'r') as f:
        websites = json.load(f)

    # Crawl each website
    async with AsyncWebCrawler(config=browser_config) as crawler:
        for website in websites:
            if not website.get("disabled", False):
                await crawl_website(crawler, website)
            else:
                print(f"Skipping {website.get('name', 'Unnamed site')} because it is disabled.")


if __name__ == "__main__":
    asyncio.run(main())