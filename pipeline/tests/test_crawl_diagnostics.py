"""Empty origins and composite calendar links must not waste enrichment retries."""
import asyncio
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import crawler
import site_profiles
from site_profiles import SiteProfile
import test_detail_crawl_candidates as candidates

STRUCTURAL = 'Blocked by anti-bot protection: Structural: no_content_elements on small page (39 bytes, 0 chars visible)'
URL = 'https://calendar.test/calendar?game=123'
PROFILE = SiteProfile('calendar', re.compile(r'^calendar\.test$'),
                      skip_detail_url=lambda url: '/calendar?' in url)


def empty(**changes):
    data = dict(status_code=200, response_headers={'Content-Length': '0'},
                html='<html><head></head><body></body></html>',
                markdown=SimpleNamespace(fit_markdown='', raw_markdown=''),
                success=False, error_message=STRUCTURAL)
    data.update(changes)
    return SimpleNamespace(**data)


class EmptyOriginTests(unittest.TestCase):
    def tearDown(self):
        crawler.reset_host_circuits()

    def test_near_empty_verdict_still_requires_zero_origin_bytes(self):
        error = 'Blocked by anti-bot protection: Near-empty content (39 bytes) with HTTP 200'
        self.assertTrue(crawler._is_empty_origin_response(empty(error_message=error)))
        self.assertFalse(crawler._is_empty_origin_response(empty(error_message=error,response_headers={})))

    def test_listing_empty_origin_fails_without_retry_or_host_strike(self):
        database = MagicMock();database.create_crawl_result.return_value = 123
        client = SimpleNamespace(arun=AsyncMock(return_value=[empty()]))
        with patch.object(crawler, 'db', database), patch.object(crawler, '_refetch_past_challenge', new=AsyncMock()) as retry:
            result = asyncio.run(crawler.crawl_website(client,
                dict(id=1, name='Empty', urls=['https://empty.test/events']), None, None, 1))
        self.assertIsNone(result)
        database.update_crawl_result_crawled.assert_not_called()
        self.assertIn('Origin served empty page', database.update_crawl_result_failed.call_args.args[3])
        retry.assert_not_called()
        self.assertNotIn('empty.test', crawler._host_block_strikes)

    def test_detail_empty_origin_never_reaches_enrichment_or_retries(self):
        client = SimpleNamespace(arun=AsyncMock(return_value=empty()))
        with patch.object(crawler, '_refetch_past_challenge', new=AsyncMock()) as retry:
            self.assertIsNone(asyncio.run(crawler.crawl_event_url(client, 'https://empty.test/event', object())))
        retry.assert_not_called()

    def test_requires_affirmative_zero_length_success_status(self):
        for changes in [dict(status_code=403), dict(status_code=429), dict(status_code=None),
                        dict(response_headers={}), dict(response_headers={'Content-Length':'100'}),
                        dict(response_headers={'Content-Length':'0','cf-mitigated':'challenge'}),
                        dict(error_message='Blocked by anti-bot protection: HTTP 403; Structural: empty')]:
            with self.subTest(changes=changes):
                self.assertFalse(crawler._is_empty_origin_response(empty(**changes)))

    def test_injected_content_json_and_application_shells_are_not_empty_origins(self):
        for changes in [dict(html='<html><body><script src="app.js"></script></body></html>'),
                        dict(html='<html><body><pre>[]</pre></body></html>'),
                        dict(markdown=SimpleNamespace(raw_markdown='# Event',fit_markdown=''))]:
            self.assertFalse(crawler._is_empty_origin_response(empty(**changes)))

    def test_http_block_with_empty_body_still_retries(self):
        client = SimpleNamespace(arun=AsyncMock(return_value=empty(status_code=403)))
        with patch.object(crawler, '_refetch_past_challenge', new=AsyncMock(return_value=None)) as retry:
            self.assertIsNone(asyncio.run(crawler.crawl_event_url(client, 'https://empty.test/event', object())))
        retry.assert_awaited_once()


class DetailProfileTests(unittest.TestCase):
    def test_skip_is_host_scoped_and_detail_only(self):
        with patch.object(site_profiles,'PROFILES',[PROFILE]):
            self.assertTrue(site_profiles.skip_detail_url(URL))
            self.assertFalse(site_profiles.skip_detail_url('https://other.test/calendar?game=123'))
            self.assertFalse(site_profiles.skip_detail_url('https://calendar.test/event/123'))
            self.assertFalse(site_profiles.is_skip_url(URL))
            self.assertFalse(site_profiles.is_listing_url(URL,URL))

    def test_missing_or_broken_plugin_preserves_normal_behavior(self):
        for profiles in [[],[SiteProfile('broken',re.compile(r'^calendar\.test$'),
                           skip_detail_url=MagicMock(side_effect=ValueError('bad config')))]]:
            with patch.object(site_profiles,'PROFILES',profiles):
                self.assertFalse(site_profiles.skip_detail_url(URL))

    def test_manual_detail_fetch_also_skips_before_network(self):
        client = SimpleNamespace(arun=AsyncMock())
        with patch.object(site_profiles,'PROFILES',[PROFILE]):
            self.assertIsNone(asyncio.run(crawler.crawl_event_url(client,URL,object())))
        client.arun.assert_not_called()

    def test_candidate_filter_preserves_event_and_attempt_budget(self):
        fixture = candidates.TestSupersededCrawlEventsExcluded()
        fixture.setUp()
        try:
            fixture._add(1,'Home Game',URL,candidates.FRESH_AT)
            fixture._add(2,'Concert','https://calendar.test/event/2',candidates.FRESH_AT)
            with patch.object(site_profiles,'PROFILES',[PROFILE]):
                self.assertEqual(fixture._ids(),{2})
            self.assertEqual(fixture.conn.execute('SELECT id,detail_crawl_attempts FROM crawl_events ORDER BY id').fetchall(),[(1,0),(2,0)])
            with patch.object(site_profiles,'PROFILES',[]):self.assertEqual(fixture._ids(),{1,2})
        finally:fixture.conn.close()
