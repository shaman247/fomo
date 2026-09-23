"""Mixed API/browser calendars must never discard a configured source silently."""
import asyncio
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import crawler
from site_profiles import SiteProfile,CrawlMode


def run_case(*, custom_error=False, browser_error=False, timeout=False, reverse=False, empty=None):
    fetcher=MagicMock(return_value=('### API event\n'+'a'*600,1))
    if custom_error:fetcher.side_effect=ValueError('Incomplete inventory')
    profile=SiteProfile('test',re.compile('api.example'),crawl_mode=CrawlMode.CUSTOM,fetcher=fetcher)
    urls=['https://api.example/events/','https://browser.example/events/']
    if reverse:urls.reverse()
    async def arun(**kwargs):
        if timeout:await asyncio.sleep(1)
        markdown = SimpleNamespace(fit_markdown='Browser event\n'+'b'*600,raw_markdown='')
        if empty == 'missing': markdown = None
        if empty == 'blank': markdown = SimpleNamespace(fit_markdown='', raw_markdown='')
        return [SimpleNamespace(success=not browser_error,error_message='Failed' if browser_error else None,
            html='<body>Calendar</body>',markdown=markdown)]
    browser=SimpleNamespace(arun=AsyncMock(side_effect=arun))
    database=MagicMock();database.create_crawl_result.return_value=123
    def custom(urls):
        return profile if all('api.example' in u for u in urls) else None
    with patch.object(crawler,'db',database),patch.object(crawler.site_profiles,'custom_fetch_profile',side_effect=custom),patch.object(crawler.site_profiles,'inject_js_for',return_value=''):
        result=asyncio.run(crawler.crawl_website(browser,dict(id=1,name='Mixed',urls=urls,crawl_timeout=.01 if timeout else 10),None,None,1))
    return result,database,fetcher,browser



class TestMixedSources(unittest.TestCase):
    def test_empty_browser_does_not_certify_api_only_capture(self):
        for empty in ('missing', 'blank'):
            with self.subTest(empty=empty):
                result, database, *_ = run_case(empty=empty)
                self.assertIsNone(result)
                database.update_crawl_result_crawled.assert_not_called()
                database.update_crawl_result_failed.assert_called_once()

    def test_mixed_inventory_keeps_both_sources(self):
        result,db,fetcher,browser=run_case()
        assert result==123
        body=db.update_crawl_result_crawled.call_args.args[3]
        assert 'API event' in body and 'Browser event' in body
        assert browser.arun.call_count==1
        assert fetcher.call_count==1


    def test_failed_api_never_publishes_prior_browser_fragment(self):
        result,db,*_=run_case(custom_error=True,reverse=True)
        assert result is None
        db.update_crawl_result_crawled.assert_not_called()
        db.update_crawl_result_failed.assert_called_once()


    def test_failed_browser_never_publishes_api_fragment(self):
        result,db,*_=run_case(browser_error=True)
        assert result is None
        db.update_crawl_result_crawled.assert_not_called()


    def test_mixed_timeout_never_publishes_api_fragment(self):
        result,db,*_=run_case(timeout=True)
        assert result is None
        db.update_crawl_result_crawled.assert_not_called()
