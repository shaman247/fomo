import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

async def test_sites():
    """Test problematic sites with improved crawler settings"""

    # Sites to test with their URLs
    test_sites = [
        {"id": 795, "name": "Asteri Entertainment", "url": "https://asterientertainment.com"},
        {"id": 833, "name": "Dorsey's Fine Art Gallery", "url": "https://dorseysartgallery.com"},
        {"id": 856, "name": "Gowanus Gallery by Larisa", "url": "https://larisadaiga.com"},
        {"id": 902, "name": "Purgatory", "url": "https://purgatory.love"},
        {"id": 903, "name": "QCC Art Gallery / CUNY", "url": "https://qcc.cuny.edu/artgallery/"},
        {"id": 917, "name": "The Greenpoint Loft", "url": "https://thegreenpointloft.com"},
        {"id": 920, "name": "The Living Gallery", "url": "https://thelivinggallery.com"},
        {"id": 1003, "name": "The Woods", "url": "https://www.thewoodsbk.com/events-1"},
    ]

    browser_config = BrowserConfig(
        headless=False,
        java_script_enabled=True,
        text_mode=True,
        light_mode=True
    )

    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        delay_before_return_html=15,
        scan_full_page=True,
        scroll_delay=0.5,
        page_timeout=60000,
        markdown_generator=DefaultMarkdownGenerator(options={'ignore_links': False})
    )

    results = []

    async with AsyncWebCrawler(config=browser_config) as crawler:
        for site in test_sites:
            print(f"\n{'='*60}")
            print(f"Testing: {site['name']} (ID: {site['id']})")
            print(f"URL: {site['url']}")
            print(f"{'='*60}")

            try:
                result = await crawler.arun(url=site['url'], config=crawler_config)

                content_length = len(result.markdown.raw_markdown) if result.markdown else 0
                success = result.success
                error = result.error_message if not success else None

                print(f"Status: {'✅ SUCCESS' if success else '❌ FAILED'}")
                print(f"Content Length: {content_length:,} bytes")
                if error:
                    print(f"Error: {error}")

                # Check for event-related keywords
                if success and result.markdown:
                    content_lower = result.markdown.raw_markdown.lower()
                    event_indicators = ['event', 'calendar', 'schedule', 'upcoming', 'show']
                    found_indicators = [ind for ind in event_indicators if ind in content_lower]
                    print(f"Event indicators found: {', '.join(found_indicators) if found_indicators else 'None'}")

                results.append({
                    'id': site['id'],
                    'name': site['name'],
                    'url': site['url'],
                    'success': success,
                    'content_length': content_length,
                    'error': error
                })

            except Exception as e:
                print(f"❌ EXCEPTION: {str(e)}")
                results.append({
                    'id': site['id'],
                    'name': site['name'],
                    'url': site['url'],
                    'success': False,
                    'content_length': 0,
                    'error': str(e)
                })

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for r in results:
        status = '✅' if r['success'] and r['content_length'] > 5000 else '❌'
        print(f"{status} {r['name']} (ID: {r['id']}): {r['content_length']:,} bytes")
        if r['error']:
            print(f"   Error: {r['error'][:100]}")

    return results

if __name__ == "__main__":
    asyncio.run(test_sites())
