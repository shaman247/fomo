"""The compatibility provider always uses durable local work, without SDKs."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pydantic import BaseModel, Field
import agent_extraction as queue
import llm_providers


class Result(BaseModel):
    request_id: str = ''
    events: list[str] = Field(default_factory=list)


class AgentQueueTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = mock.patch.object(queue, '_work_dir', Path(temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.prompt = 'Set request_id to "cr-7" in your response. Source: Event A.'

    def pending(self, prompt=None, schema=Result, images=None):
        with self.assertRaises(queue.AgentExtractionPending) as raised:
            asyncio.run(llm_providers.generate_structured(prompt or self.prompt, schema,
                        provider='gemini', gemini_client=mock.Mock(), images=images))
        return raised.exception

    def response(self, pending, **changes):
        result = dict(request_id=pending.request_id, status='complete', coverage='complete',
                      result={'request_id': 'cr-7', 'events': ['Event A']})
        result.update(changes)
        return result

    def test_all_legacy_provider_overrides_are_ignored(self):
        with mock.patch.dict(os.environ, {'EXTRACTION_PROVIDER':'openai', 'EXTRACTION_PROVIDER_VISION':'gemini'}):
            self.assertEqual(llm_providers.providers_in_use(), {'agent'})
            self.assertEqual(llm_providers.unconfigured_paths(), [])
        pending = self.pending()
        self.assertTrue(pending.request_path.exists())
        self.assertEqual(queue.status()[0]['status'], 'pending')

    def test_valid_response_replays_without_new_work(self):
        pending = self.pending()
        response = queue.work_dir() / 'agent-result.json'
        queue.atomic_json(response, self.response(pending))
        queue.submit(pending.request_id, response)
        parsed = json.loads(asyncio.run(llm_providers.generate_structured(self.prompt, Result)))
        self.assertEqual(parsed['events'], ['Event A'])
        self.assertEqual(len(queue.status()), 1)
        self.assertEqual(queue.status()[0]['status'], 'complete')

    def test_hash_binds_prompt_schema_and_images(self):
        first = self.pending()
        second = self.pending(self.prompt + ' extra source')
        class NewResult(Result):
            description: str
        third = self.pending(schema=NewResult)
        fourth = self.pending(images=[{'inline_data': {'mime_type':'image/png', 'data':'dGVzdA=='}}])
        self.assertEqual(len({p.request_id for p in [first, second, third, fourth]}), 4)
        self.assertTrue((fourth.request_path.parent / 'image-1.png').exists())

    def test_invalid_stale_partial_and_empty_responses_never_succeed(self):
        pending = self.pending()
        invalid = [self.response(pending, request_id='stale'),
                   self.response(pending, status='partial'),
                   self.response(pending, coverage='partial'),
                   self.response(pending, result={'request_id':'cr-7'}),
                   self.response(pending, result={'request_id':'cr-8','events':['A']}),
                   self.response(pending, result={'request_id':'cr-7','events':[]}),
                   self.response(pending, result={'request_id':'cr-7','events':[123]}),
                   self.response(pending, result={'request_id':'cr-7','events':['A'],'unknown':1})]
        for response in invalid:
            with self.subTest(response=response):
                queue.atomic_json(pending.request_path.with_name('response.json'), response)
                with self.assertRaises(queue.AgentExtractionInvalid):
                    asyncio.run(llm_providers.generate_structured(self.prompt, Result))
                self.assertEqual(queue.status()[0]['status'], 'invalid')

    def test_truncated_json_never_counts_as_empty(self):
        pending = self.pending()
        pending.request_path.with_name('response.json').write_text('{"result":')
        with self.assertRaises(queue.AgentExtractionInvalid):
            asyncio.run(llm_providers.generate_structured(self.prompt, Result))

    def test_explicit_empty_is_accepted_with_reason(self):
        pending = self.pending()
        queue.atomic_json(pending.request_path.with_name('response.json'), self.response(
            pending, result={'request_id':'cr-7', 'events':[]}, empty_reason='Source states no upcoming events.'))
        self.assertEqual(json.loads(asyncio.run(llm_providers.generate_structured(self.prompt, Result)))['events'], [])

    def test_mutated_request_packet_is_rejected(self):
        pending = self.pending()
        packet = json.loads(pending.request_path.read_text())
        packet['prompt'] += ' changed'
        queue.atomic_json(pending.request_path, packet)
        with self.assertRaises(queue.AgentExtractionInvalid):
            asyncio.run(llm_providers.generate_structured(self.prompt, Result))

    def test_reference_date_is_frozen(self):
        queue.atomic_json(queue.work_dir() / 'run.json', {'reference_date':'2026-09-15'})
        self.assertEqual(queue.reference_date(), '2026-09-15')


if __name__ == '__main__':
    unittest.main()


class AgentExtractionIntegrationTests(AgentQueueTests):
    def test_all_chunks_are_queued_before_pausing(self):
        import extractor
        prep = extractor.PreparedExtraction(crawl_result_id=7, website_name='Example',
            extraction_type='chunked', max_batches=1,
            chunk_prompts=['first source', 'second source', 'third source'])
        with self.assertRaises(queue.AgentExtractionPending):
            asyncio.run(extractor._execute_chunked_sync(prep))
        self.assertEqual(len(queue.status()), 3)
        self.assertTrue(all(item['status'] == 'pending' for item in queue.status()))

    def test_pending_listing_does_not_mark_crawl_failed(self):
        import extractor
        prep = extractor.PreparedExtraction(crawl_result_id=7, website_name='Example',
                                             extraction_type='single', prompt=self.prompt)
        with mock.patch.object(extractor, 'prepare_extraction', mock.AsyncMock(return_value=prep)), \
             mock.patch.object(extractor.db, 'update_crawl_result_failed') as failed:
            with self.assertRaises(queue.AgentExtractionPending):
                asyncio.run(extractor.extract_events(mock.Mock(), mock.Mock(), 7, 'Example'))
        failed.assert_not_called()

    def test_enrichment_requires_all_requested_names_at_submit(self):
        import extractor
        with self.assertRaises(queue.AgentExtractionPending) as raised:
            asyncio.run(extractor.enrich_events_batch(['First', 'Second'], 'Venue'))
        pending = raised.exception
        response = self.response(pending, result={'request_id':'', 'enrichments':[
            {'name':'First', 'description':'No description available.', 'hashtags':['Art'], 'emoji':'🎨'}]})
        source = queue.work_dir() / 'answer.json'
        queue.atomic_json(source, response)
        with self.assertRaisesRegex(queue.AgentExtractionInvalid, 'each requested event name'):
            queue.submit(pending.request_id, source)

    def test_invalid_calendar_date_is_rejected_before_submit(self):
        import extractor
        pending = self.pending(schema=extractor.SimpleEventList)
        source = queue.work_dir() / 'answer.json'
        queue.atomic_json(source, self.response(pending, result={'request_id':'cr-7','events':[
            {'name':'Event', 'location':'Venue', 'occurrences':[{'start_date':'2026-02-30'}]}]}))
        with self.assertRaises(queue.AgentExtractionInvalid):
            queue.submit(pending.request_id, source)

    def test_detail_pending_is_not_silently_skipped(self):
        import extractor
        with self.assertRaises(queue.AgentExtractionPending):
            asyncio.run(extractor.extract_single_event('Event', 'The event is on September 22, 2026.'))
