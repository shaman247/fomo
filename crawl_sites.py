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

def _archive_old_files(date_str, filename, source_dir):
    """Moves old files from crawled, extracted, and processed directories to an archive."""
    archive_base_dir = "archived"
    dirs_to_check = {
        "crawled": ".md",
        "extracted": ".md",
        "processed": ".json"
    }

    # Create archive structure: archived/YYYYMMDD/crawled/, etc.
    archive_date_dir = os.path.join(archive_base_dir, date_str)
    for dir_name in dirs_to_check:
        os.makedirs(os.path.join(archive_date_dir, dir_name), exist_ok=True)

    for dir_name, extension in dirs_to_check.items():
        # Old file is in: crawled/YYYYMMDD/filename.md
        old_file_path = os.path.join(dir_name, date_str, f"{filename}{extension}")
        if os.path.exists(old_file_path):
            # Archive to: archived/YYYYMMDD/crawled/filename.md
            archive_path = os.path.join(archive_date_dir, dir_name, f"{filename}{extension}")
            print(f"  - Archiving old file: {old_file_path} to {archive_path}")
            os.rename(old_file_path, archive_path)

    # Delete empty date directories after archiving
    for dir_name in dirs_to_check:
        date_dir = os.path.join(dir_name, date_str)
        if os.path.exists(date_dir) and os.path.isdir(date_dir):
            # Check if directory is empty
            if not os.listdir(date_dir):
                print(f"  - Deleting empty directory: {date_dir}")
                os.rmdir(date_dir)

async def crawl_website(crawler, website_info):
    name = website_info.get("name")
    if not name:
        print(f"Skipping entry due to missing 'name': {website_info}")
        return

    # Check if a recent crawl file exists based on crawl_frequency
    safe_filename = "".join(c for c in name if c.isalnum() or c in (' ', '_')).rstrip()
    safe_filename_pattern = safe_filename.replace(' ', '_').lower()
    current_date = datetime.now()
    crawl_frequency = website_info.get("crawl_frequency", 7)  # Default to 7 days

    output_dir = "crawled"
    os.makedirs(output_dir, exist_ok=True)

    # Check for existing files in dated subdirectories and skip if a recent one is found
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
                    #print(f"Skipping {name} as it was crawled {days_since_crawl} day(s) ago (frequency: {crawl_frequency} days).")
                    return
                else:
                    # File is old, so we'll archive it before re-crawling.
                    _archive_old_files(date_str, safe_filename_pattern, output_dir)
            except (ValueError, IndexError):
                # Ignore files with malformed names
                continue


    urls_to_crawl = website_info.get("urls", [])

    # Check for selector and num_clicks to generate js_code, otherwise use existing js_code
    selector = website_info.get("selector")
    num_clicks = website_info.get("num_clicks")
    if not num_clicks: num_clicks = 2
    if selector and num_clicks:
        js_code = f"for (let i = 0; i < {num_clicks}; i++) {{await new Promise(resolve => setTimeout(resolve, 1000)); document.querySelector('{selector}').click();}}"
    else:
        js_code = website_info.get("js_code", "")

    print(js_code)

    keywords = website_info.get("keywords")
    if keywords:
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
        deep_crawl_strategy = BestFirstCrawlingStrategy(max_depth=0)

    crawler_config = CrawlerRunConfig(
        js_code=js_code,
        remove_overlay_elements=True,
        delay_before_return_html=3,
        scan_full_page=True,
        #magic=True,
        #process_iframes=True,
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

    print(f"Crawling {name}...")
    combined_markdown = ""
    for url in urls_to_crawl:
        print(f"  - Processing {url}")
        for result in  await crawler.arun(
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

    current_date_str = current_date.strftime('%Y%m%d')
    # Create dated subdirectory: crawled/YYYYMMDD/
    dated_output_dir = os.path.join(output_dir, current_date_str)
    os.makedirs(dated_output_dir, exist_ok=True)

    output_filename = os.path.join(dated_output_dir, f"{safe_filename.replace(' ', '_').lower()}.md")

    with open(output_filename, 'w', encoding='utf-8') as f:
        if urls_to_crawl:
            f.write(urls_to_crawl[0] + "\n")
        f.write(combined_markdown)

    print(f"Saved content for {name} to {output_filename}")
    print(f"  - Total Combined Markdown Length: {len(combined_markdown)}")

async def main():
    browser_config = BrowserConfig(
        headless=False,
        enable_stealth=True,
        java_script_enabled=True,
        text_mode=True,
    )
    with open('websites.json', 'r') as f:
        websites = json.load(f)
    async with AsyncWebCrawler(config=browser_config) as crawler:
        for website in websites:
            if not website.get("disabled", False):
                await crawl_website(crawler, website)
            else:
                print(f"Skipping {website.get('name', 'Unnamed site')} because it is disabled.")

if __name__ == "__main__":
    asyncio.run(main())