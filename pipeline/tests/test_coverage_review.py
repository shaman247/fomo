"""Collapsed extraction retries must change mode and keep source coverage."""
import asyncio
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import extractor


class CoverageReviewTests(unittest.TestCase):
    def prep(self):
        return extractor.PreparedExtraction(
            crawl_result_id=7, website_name='Test Venue', extraction_type='single',
            prompt='Original prompt', notes='Use the venue stated in each listing.',
            content='\n\n'.join(f'### [Event {i}](https://example.org/{i})\n'
                                'September 25, 2026, 7pm\n' + 'Description. ' * 150
                                for i in range(30)))

    def test_single_review_becomes_chunked_without_mutating_original(self):
        prep = self.prep()
        review = extractor._prepare_coverage_review(prep, '\nCOVERAGE REVIEW')
        self.assertEqual(prep.extraction_type, 'single')
        self.assertEqual(prep.chunk_prompts, [])
        self.assertEqual(review.extraction_type, 'chunked')
        self.assertGreater(len(review.chunks), 1)
        for i in range(30):
            self.assertTrue(any(f'### [Event {i}]' in c for c in review.chunks))
        self.assertTrue(all(len(c) <= extractor.MAX_CHUNK_CHARS for c in review.chunks))
        self.assertIn(prep.notes, review.chunk_instructions)
        self.assertTrue(all('COVERAGE REVIEW' in p for p in review.chunk_prompts))
        self.assertEqual(review.chunk_prompts,
                         extractor._prepare_coverage_review(prep, '\nCOVERAGE REVIEW').chunk_prompts)

    def test_site_record_cap_is_honored(self):
        prep = self.prep()
        prep.max_records_per_chunk = 2
        review = extractor._prepare_coverage_review(prep, 'review')
        self.assertTrue(all(c.count('### [Event') <= 2 for c in review.chunks))

    def test_chunked_review_preserves_boundaries(self):
        prep = self.prep()
        prep.extraction_type = 'chunked'
        prep.chunks = ['source A', 'source B']
        prep.chunk_prompts = ['prompt A', 'prompt B']
        review = extractor._prepare_coverage_review(prep, ' REVIEW')
        self.assertEqual(review.chunks, prep.chunks)
        self.assertEqual(review.chunk_prompts, ['prompt A REVIEW', 'prompt B REVIEW'])

    def test_execution_keeps_the_better_result_and_retries_only_once(self):
        first = json.dumps({'events': [{'name': 'first', 'occurrences': []}]})
        better = json.dumps({'events': [{'name': 'first'}, {'name': 'second'}]})
        for retry_text, expected in ((better, better), ('{"events": []}', first)):
            with mock.patch.object(extractor, '_generate_extraction_response',
                    new=mock.AsyncMock(side_effect=[first, retry_text])) as generate, \
                 mock.patch.object(extractor, '_variance_retry_reason', return_value='count collapsed'), \
                 mock.patch.object(extractor.db, 'update_crawl_result_extracted') as store:
                asyncio.run(extractor.execute_extraction_sync(mock.Mock(), mock.Mock(), self.prep()))
                self.assertEqual(generate.await_count, 2)
                self.assertEqual(generate.await_args_list[1].args[0].extraction_type, 'chunked')
                self.assertEqual(store.call_args.args[-1], expected)

    def test_schedule_notices_reach_every_description_path(self):
        prompts = [extractor.detail_instructions(), extractor.get_chunk_instructions(),
                   extractor.get_prompt('url', 'content', '2026-09-20', 'venue', ''),
                   extractor.get_vision_prompt('url', 'content', '2026-09-20', 'venue', ''),
                   extractor.get_enrichment_prompt(['event'], 'venue')]
        for prompt in prompts:
            self.assertIn(extractor.SCHEDULE_EXCEPTIONS_RULE, prompt)


if __name__ == '__main__':
    unittest.main()
