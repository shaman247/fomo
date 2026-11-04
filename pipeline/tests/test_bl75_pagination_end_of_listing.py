"""BL75: a 404 on a trailing `/page/N/` row is the end of a shrunk listing.

Live at the Barbershop (w6044) is crawled as `/events/` + `/page/2/`..`/page/6/`.
When the listing shrank to five pages, `/page/6/` 404'd and the whole crawl was
stored failed ("Incomplete crawl: fetched 5 of 6 URLs"), so nothing merged.
Every other failure shape must still fail the crawl as incomplete (BL01/BL29).
"""
import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import crawler

BODY = '# Upcoming shows\n' + 'Comedy at 8pm in the back room.\n' * 30
NOT_FOUND = '# Page not found\nSorry, nothing here.\n'
SOFT_404 = 'We are sorry, but you found a page that does not exist.'
BASE = 'https://greatestshowever.test/events/'


def page(body=BODY, *, success=True, status=200, error=None):
    return SimpleNamespace(success=success, status_code=status,
                           error_message=error, html='<body>' + body + '</body>',
                           markdown=SimpleNamespace(fit_markdown='', raw_markdown=body))


def missing():
    return page(NOT_FOUND, status=404)


def listing(pages, base=BASE):
    return [base] + [f'{base}page/{n}/' for n in range(2, pages + 1)]


class EndOfListingCrawlTests(unittest.TestCase):
    def setUp(self):
        crawler.reset_host_circuits()

    def tearDown(self):
        crawler.reset_host_circuits()

    def run_capture(self, replies, urls, *, recovery=None):
        database = MagicMock()
        database.create_crawl_result.return_value = 123
        replies = list(replies)

        async def fetch(**kwargs):
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        client = SimpleNamespace(arun=AsyncMock(side_effect=fetch))
        with patch.object(crawler, 'db', database), \
                patch.object(crawler, '_refetch_past_challenge', new=AsyncMock(return_value=recovery)):
            returned = asyncio.run(crawler.crawl_website(client,
                dict(id=6044, name='Barbershop', urls=urls, crawl_timeout=10), None, None, 1))
        return returned, database

    def assert_stored(self, replies, urls, **kwargs):
        returned, database = self.run_capture(replies, urls, **kwargs)
        self.assertEqual(returned, 123)
        database.update_crawl_result_failed.assert_not_called()
        database.update_crawl_result_crawled.assert_called_once()
        return database.update_crawl_result_crawled.call_args[0][3]

    def assert_incomplete(self, replies, urls, **kwargs):
        returned, database = self.run_capture(replies, urls, **kwargs)
        self.assertIsNone(returned)
        database.update_crawl_result_crawled.assert_not_called()
        database.update_crawl_result_failed.assert_called_once()
        return str(database.update_crawl_result_failed.call_args)

    def test_w6044_trailing_page_404_is_end_of_listing(self):
        urls = listing(6)
        stored = self.assert_stored([[page()]] * 5 + [[missing()]], urls)
        self.assertNotIn('page/6/', stored)
        self.assertIn(urls[4], stored)

    def test_two_trailing_404s_chain_off_the_last_good_page(self):
        self.assert_stored([[page()]] * 4 + [[missing()], [missing()]], listing(6))

    def test_404_with_failed_crawl4ai_result_still_counts(self):
        gone = page(NOT_FOUND, success=False, status=404, error='HTTP 404')
        self.assert_stored([[page()], [page()], [gone]], listing(3))

    def test_soft_404_and_410_count_as_not_found(self):
        self.assert_stored([[page()], [page()], [page(SOFT_404)]], listing(3))
        self.assert_stored([[page()], [page()], [page(NOT_FOUND, status=410)]], listing(3))

    def test_query_string_pagination(self):
        for key in ('page', 'paged'):
            with self.subTest(key=key):
                urls = ['https://club.test/calendar?view=list',
                        f'https://club.test/calendar?view=list&{key}=2',
                        f'https://club.test/calendar?{key}=3&view=list']
                self.assert_stored([[page()], [page()], [missing()]], urls)

    def test_404_after_a_failed_previous_page_stays_incomplete(self):
        message = self.assert_incomplete(
            [[page()], [page()], [page(status=500)], [missing()]], listing(4))
        self.assertIn('Incomplete crawl: fetched 2 of 4', message)
        self.assertIn('2 failed or skipped', message)

    def test_404_after_a_timed_out_or_challenged_previous_page_stays_incomplete(self):
        challenge = page('Just a moment... Please enable cookies.')
        self.assert_incomplete([[page()], [challenge], [missing()]], listing(3))
        self.assert_incomplete([[page()], RuntimeError('Timeout 30000ms exceeded')], listing(2))

    def test_404_on_a_page_before_a_live_page_stays_incomplete(self):
        # Page 3 is gone but page 4 still lists events: a broken page, not the end.
        self.assert_incomplete([[page()], [page()], [missing()], [page()]], listing(4))

    def test_404_on_a_non_pagination_url_stays_incomplete(self):
        urls = ['https://venue.test/events/', 'https://venue.test/festival/']
        self.assert_incomplete([[page()], [missing()]], urls)

    def test_other_failures_on_a_pagination_url_stay_incomplete(self):
        for failure in (page(status=500), page(success=False, error='Connection reset'),
                        page(status=403, success=False, error='HTTP 403'),
                        page(SOFT_404, status=500)):
            with self.subTest(failure=failure):
                crawler.reset_host_circuits()
                self.assert_incomplete([[page()], [page()], [failure]], listing(3))

    def test_404_without_any_good_earlier_page_stays_failed(self):
        self.assert_incomplete([[page()], [missing()]],
                               ['https://other.test/a/', f'{BASE}page/2/'])

    def test_partial_deep_crawl_404_is_not_a_clear_not_found(self):
        self.assert_incomplete([[page()], [page(), missing()]], listing(2))


class ListingPageParsingTests(unittest.TestCase):
    def test_positions(self):
        key, number, paginated = crawler._listing_page(BASE)
        self.assertEqual((number, paginated), (1, False))
        self.assertEqual(crawler._listing_page(BASE + 'page/6/'), (key, 6, True))
        self.assertEqual(crawler._listing_page(BASE.rstrip('/') + '/page/6'), (key, 6, True))
        self.assertEqual(crawler._listing_page('https://x.test/e?paged=3&a=1')[1:], (3, True))
        self.assertEqual(crawler._listing_page('https://x.test/e?a=1')[0],
                         crawler._listing_page('https://x.test/e?page=4&a=1')[0])
        self.assertFalse(crawler._listing_page('https://x.test/pages/2/')[2])

    def test_page_one_is_never_end_of_listing(self):
        urls = [BASE, BASE + 'page/1/']
        self.assertEqual(crawler._end_of_listing_urls(urls, {BASE}, [BASE + 'page/1/']), set())


if __name__ == '__main__':
    unittest.main()
