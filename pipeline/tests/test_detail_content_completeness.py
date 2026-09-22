"""Detail pages must reach extraction intact, including schedules past 12K."""
import asyncio
import hashlib
import json
import unittest
from pathlib import Path
from unittest import mock

from pipeline.tests import test_crawler_guards as fixtures
import crawler
import extractor
import processor


class DetailContentCompletenessTests(unittest.TestCase):
    BODY = '# Volunteer shifts\n' + ('Program information.\n' * 900) + '\nOctober 24, 2026, 2pm–4pm'

    def test_direct_fetch_preserves_schedule_after_old_cutoff(self):
        body = asyncio.run(crawler.crawl_event_url(
            fixtures._FakeCrawler(self.BODY), 'https://example.org/event', object()))
        self.assertEqual(body, self.BODY)
        self.assertIn('October 24', body[12000:])

    def test_recovered_fetch_preserves_schedule_after_old_cutoff(self):
        with mock.patch.object(crawler, '_refetch_past_challenge',
                               new=mock.AsyncMock(return_value=self.BODY)):
            body = asyncio.run(crawler.crawl_event_url(
                fixtures._FakeCrawler(fixtures.DETAIL_CHALLENGE_BODY),
                'https://example.org/event', object()))
        self.assertEqual(body, self.BODY)

    def test_complete_source_is_in_extraction_packet(self):
        generate = mock.AsyncMock(return_value=json.dumps({
            'description': 'Program information.', 'hashtags': ['Community'], 'emoji': '📅'}))
        with mock.patch.object(extractor.llm_providers, 'is_configured', return_value=True), \
             mock.patch.object(extractor.llm_providers, 'generate_structured', generate):
            asyncio.run(extractor.extract_single_event('Volunteer shifts', self.BODY))
        self.assertIn(self.BODY, generate.call_args.args[0])

    def test_oversized_packet_fails_without_sending_a_partial_source(self):
        generate = mock.AsyncMock()
        with mock.patch.object(extractor.llm_providers, 'is_configured', return_value=True), \
             mock.patch.object(extractor.llm_providers, 'generate_structured', generate), \
             mock.patch.object(extractor, 'MAX_REQUEST_TOKENS', 1000):
            with self.assertRaisesRegex(extractor.ExtractionCallFailure, 'Detail page too large'):
                asyncio.run(extractor.extract_single_event('Volunteer shifts', self.BODY))
        generate.assert_not_awaited()

    def test_clipped_legacy_snapshot_cannot_be_reused(self):
        candidate = (1, 'Volunteer shifts', 'https://example.org/event', 7)
        settings = {'notes': 'Use explicit dates'}
        old_identity = json.dumps({'candidate': candidate, 'settings': settings},
                                  sort_keys=True, ensure_ascii=False, default=str)
        old_key = hashlib.sha256(old_identity.encode()).hexdigest()
        self.assertNotEqual(processor._detail_source_path(Path('run'), candidate, settings),
                            Path('run/detail_sources') / f'{old_key}.json')


if __name__ == '__main__':
    unittest.main()
