"""A recycled dated URL must not enrich an earlier session with the next one."""
import asyncio
import hashlib
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import crawler

OLD = 'https://classes.test/event/Handmade-Pasta_2026-Sep-18'
NEW = 'https://classes.test/event/Handmade-Pasta_2026-Oct-3'
BODY = '# Handmade Pasta\nOctober 3, 2026 at 5pm, Other Venue\n' + 'Details. ' * 30


def result(final=NEW, body=BODY):
    return SimpleNamespace(success=True, redirected_url=final, status_code=200,
                           markdown=SimpleNamespace(fit_markdown=body, raw_markdown=body))


class DetailSessionIdentityTests(unittest.TestCase):
    def test_changed_session_date_is_detected(self):
        for old, new in [
            (OLD, NEW),
            ('https://venue.test/event/2026/09/18/pasta', 'https://venue.test/event/2026/10/03/pasta'),
            ('http://www.venue.test/event/pasta-2026-09-18',
             'https://venue.test/event/pasta-2026-10-03/?tracking=1'),
            (OLD, NEW.replace('Oct', 'October')),
        ]:
            with self.subTest(old=old, new=new):
                self.assertTrue(crawler._detail_redirect_changes_session(old, new))

    def test_same_day_formatting_and_canonical_redirects_survive(self):
        for final in [OLD, OLD + '/', OLD + '?nowrapper=true',
                      OLD.replace('https:', 'http:'), OLD.replace('Sep-18', '09-18'),
                      OLD.replace('classes.test', 'www.classes.test')]:
            self.assertFalse(crawler._detail_redirect_changes_session(OLD, final))

    def test_ambiguous_or_different_identity_is_not_inferred(self):
        for old, new in [
            (OLD, None), (OLD, ''), (OLD, MagicMock()),
            (OLD, NEW.replace('classes.test', 'different.test')),
            (OLD, NEW.replace('Handmade-Pasta', 'Cooking')),
            ('https://venue.test/e/12?date=2026-09-18', 'https://venue.test/e/12?date=2026-10-03'),
            ('https://venue.test/e/12', 'https://venue.test/e/13'),
            (OLD + '/2026-01-01', NEW + '/2026-01-01'),
            (OLD.replace('Sep-18', 'Feb-30'), NEW),
            (OLD.replace('2026-Sep-18', '09-18-2026'), NEW),
            (OLD.replace('2026-Sep-18', '12026-Sep-18'), NEW),
            (OLD.replace('2026-Sep-18', '2026-Sep-180'), NEW),
            (OLD, 'https://[broken'),
        ]:
            with self.subTest(old=old, new=new):
                self.assertFalse(crawler._detail_redirect_changes_session(old, new))

    def test_cross_session_detail_never_reaches_enrichment_or_retry(self):
        client = SimpleNamespace(arun=AsyncMock(return_value=result()))
        with patch.object(crawler, '_refetch_past_challenge', new=AsyncMock()) as retry:
            self.assertIsNone(asyncio.run(crawler.crawl_event_url(client, OLD, object())))
        retry.assert_not_awaited()

    def test_same_session_and_unknown_final_url_still_enrich(self):
        for final in [OLD, None]:
            client = SimpleNamespace(arun=AsyncMock(return_value=result(final)))
            self.assertEqual(asyncio.run(crawler.crawl_event_url(client, OLD, object())), BODY)

    def test_fetch_rewrite_cannot_hide_original_date_identity(self):
        client = SimpleNamespace(arun=AsyncMock(return_value=result()))
        with patch.object(crawler.site_profiles, 'detail_fetch_url', return_value=NEW):
            self.assertIsNone(asyncio.run(crawler.crawl_event_url(client, OLD, object())))

    def test_challenge_path_passes_original_identity(self):
        client = SimpleNamespace(arun=AsyncMock(return_value=result(OLD, 'Just a moment... ' * 20)))
        with patch.object(crawler, '_refetch_past_challenge', new=AsyncMock(return_value=None)) as retry:
            asyncio.run(crawler.crawl_event_url(client, OLD, object()))
        self.assertEqual(retry.await_args.kwargs['detail_identity_url'], OLD)

    def _retry(self, *, detail_identity_url, final=NEW):
        browser = MagicMock()
        browser.__aenter__ = AsyncMock(return_value=SimpleNamespace(
            arun=AsyncMock(return_value=[result(final)])))
        browser.__aexit__ = AsyncMock(return_value=False)
        with patch.object(crawler, 'AsyncWebCrawler', return_value=browser), \
                patch.object(crawler, 'get_browser_config', return_value=object()):
            return asyncio.run(crawler._refetch_past_challenge(
                OLD, object(), None, attempts=1, backoff=0,
                detail_identity_url=detail_identity_url))

    def test_recovered_challenge_cannot_import_next_session(self):
        self.assertIsNone(self._retry(detail_identity_url=OLD))

    def test_recovered_same_session_is_preserved(self):
        self.assertEqual(self._retry(detail_identity_url=OLD, final=OLD), BODY + '\n\n')

    def test_listing_challenge_behavior_is_unchanged(self):
        self.assertEqual(self._retry(detail_identity_url=None), BODY + '\n\n')

    def test_pre_guard_saved_content_cannot_bypass_new_fetch_check(self):
        import processor
        candidate = (42, 'Handmade Pasta', OLD, 7)
        identity = json.dumps({'candidate': candidate, 'settings': {},
                               'content_policy': 'complete-v1'},
                              sort_keys=True, ensure_ascii=False, default=str)
        old_key = hashlib.sha256(identity.encode()).hexdigest()
        old_path = Path('run/detail_sources') / f'{old_key}.json'
        self.assertNotEqual(processor._detail_source_path(Path('run'), candidate, {}), old_path)


if __name__ == '__main__':
    unittest.main()
