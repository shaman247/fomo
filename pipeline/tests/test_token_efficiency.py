"""Smaller agent views retain evidence, validation, and interrupted paid work."""
import asyncio
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_extraction as queue
import extractor
import event_icon_review as icons


class ExtractionEfficiencyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch.object(queue, '_work_dir', Path(temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_reader_preserves_prompt_and_schema_and_repairs_image(self):
        prompt = 'Full source: café\nFinal event on September 30, 2026.'
        with self.assertRaises(queue.AgentExtractionPending) as raised:
            queue.request(prompt, extractor.EventList,
                          images=[{'inline_data': {'mime_type': 'image/png', 'data': 'dGVzdA=='}}])
        request = raised.exception
        image = request.request_path.with_name('image-1.png')
        image.write_bytes(b'changed')
        rendered = queue.read_request(request.request_id)
        self.assertIn(prompt, rendered)
        self.assertNotIn('dGVzdA==', rendered)
        self.assertEqual(image.read_bytes(), b'test')
        header = json.loads(rendered.split('\n\n')[0])
        self.assertEqual(json.loads(Path(header['schema_path']).read_text()),
                         json.loads(request.request_path.read_text())['schema'])
        self.assertIn(str(image.resolve()), header['images'])
        self.assertLess(len(queue.read_request(request.request_id, False)), len(rendered))
        with self.assertRaises(queue.AgentExtractionInvalid):
            queue.read_request('../invalid')
        packet = json.loads(request.request_path.read_text())
        packet['prompt'] += 'tampered'
        queue.atomic_json(request.request_path, packet)
        with self.assertRaises(queue.AgentExtractionInvalid):
            queue.read_request(request.request_id)

    def test_new_chunks_finish_without_enrichment_and_keep_distinct_metadata(self):
        prep = extractor.PreparedExtraction(crawl_result_id=7, website_name='Venue',
            extraction_type='chunked', chunk_prompts=['source one', 'source two'])
        with self.assertRaises(queue.AgentExtractionPending):
            asyncio.run(extractor._execute_chunked_sync(prep))
        pending = queue.status()
        self.assertEqual(len(pending), 2)
        for index, item in enumerate(pending):
            self.assertEqual(item['schema'], 'EventList')
            event = dict(name='Same name', location='Venue', sublocation=f'Room {index}',
                         description=f'Distinct source description {index}', hashtags=['Art'],
                         emoji='🎨', url=f'https://example.com/{index}',
                         occurrences=[dict(start_date='2026-09-30')])
            response = queue.work_dir() / f'answer-{index}.json'
            queue.atomic_json(response, dict(request_id=item['request_id'], status='complete',
                coverage='complete', result=dict(request_id='', events=[event])))
            queue.submit(item['request_id'], response)
        with patch.object(extractor, 'enrich_events_batch') as enrichment:
            result = json.loads(asyncio.run(extractor._execute_chunked_sync(prep)))
        enrichment.assert_not_called()
        self.assertEqual(len(result['events']), 2)
        self.assertEqual({e['sublocation'] for e in result['events']}, {'Room 0', 'Room 1'})
        self.assertEqual(len({e['description'] for e in result['events']}), 2)
        self.assertEqual(len(queue.status()), 2)

    def test_legacy_pending_packet_is_reused_and_enriched_after_acceptance(self):
        prompt = 'Old source'
        with self.assertRaises(queue.AgentExtractionPending) as raised:
            queue.request(prompt, extractor.SimpleEventList)
        old = raised.exception
        prep = extractor.PreparedExtraction(crawl_result_id=7, website_name='Venue',
            extraction_type='chunked', chunk_prompts=[prompt])
        with self.assertRaises(queue.AgentExtractionPending) as resumed:
            asyncio.run(extractor._execute_chunked_sync(prep))
        self.assertEqual(resumed.exception.request_id, old.request_id)
        response = queue.work_dir() / 'answer.json'
        queue.atomic_json(response, dict(request_id=old.request_id, status='complete',
            coverage='complete', result=dict(request_id='', events=[dict(name='Show', location='Venue')])) )
        queue.submit(old.request_id, response)
        with patch.object(extractor, 'enrich_events_batch', return_value={
                'Show': dict(description='Source detail', hashtags=['Art'], emoji='🎨')}) as enrich:
            result = json.loads(asyncio.run(extractor._execute_chunked_sync(prep)))
        enrich.assert_awaited_once()
        self.assertEqual(result['events'][0]['description'], 'Source detail')
        self.assertEqual(len(queue.status()), 1)


class IconEfficiencyTests(unittest.TestCase):
    def event(self, eid=1):
        return dict(id=eid, name='Go club', description='Play Go with boards and stones. ' * 80,
                    tags=['Games'], venue='Community Center', urls=['https://example.com/go'])

    def test_views_keep_all_context_and_full_catalog_without_baseline_duplication(self):
        event = self.event()
        packet = icons.make_packets([event], {})[0][0]
        view = [json.loads(line) for line in icons.review_text(packet).splitlines()]
        self.assertEqual(view[1]['event'], event)
        catalog = [json.loads(line) for line in icons.catalog_text(packet).splitlines()]
        self.assertEqual(catalog[1:], packet['icons'])
        self.assertEqual(view[0]['packet_hash'], icons.fingerprint(packet))
        self.assertLess(len(icons.review_text(packet)), len(json.dumps(packet)))

    def test_size_budget_splits_without_truncating_or_losing_events(self):
        events = [self.event(i) for i in range(3)]
        packets, reasons = icons.make_packets(events, {}, max_review_chars=3000)
        self.assertEqual(len(packets), 3)
        self.assertEqual([e['event'] for p in packets for e in p['events']], events)
        self.assertEqual(reasons, {'unreviewed': 3})

    def test_short_decisions_require_exact_packet_binding_and_still_reject_stale_context(self):
        event = self.event()
        packet = icons.make_packets([event], {})[0][0]
        choices = dict(catalog_revision=packet['catalog_revision'], packet_hash=icons.fingerprint(packet),
            decisions=[dict(event_id=1, decision='assign', icon_id='game-go',
                            reason='Go play', evidence=['Boards and stones'], opportunities=[])])
        rows = icons.validate_decisions(packet, choices, {1: event}, {})
        self.assertEqual(rows[0]['icon_id'], 'game-go')
        unbound = copy.deepcopy(choices)
        del unbound['packet_hash']
        with self.assertRaisesRegex(ValueError, 'input hash'):
            icons.validate_decisions(packet, unbound, {1: event}, {})
        wrong = dict(choices, packet_hash='wrong')
        with self.assertRaisesRegex(ValueError, 'packet hash'):
            icons.validate_decisions(packet, wrong, {1: event}, {})
        with self.assertRaisesRegex(ValueError, 'event changed'):
            icons.validate_decisions(packet, choices, {1: dict(event, venue='Changed')}, {})
        with self.assertRaisesRegex(ValueError, 'exactly every event'):
            icons.validate_decisions(packet, dict(choices, decisions=[]), {1: event}, {})


if __name__ == '__main__':
    unittest.main()


class SharedInstructionsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch.object(queue, '_work_dir', Path(temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_task_instructions_are_hashed_shared_and_omittable(self):
        rules = 'CRITICAL — DESCRIPTION: only from the page.'
        ids = []
        for body in ('Page one body', 'Page two body'):
            with self.assertRaises(queue.AgentExtractionPending) as raised:
                queue.request(f'Extract "X" from this page.\n\n{body}', extractor.SingleEventExtraction,
                              instructions=rules)
            ids.append(raised.exception.request_id)
        self.assertNotEqual(ids[0], ids[1])
        full = queue.read_request(ids[0])
        self.assertIn(rules, full)
        self.assertIn(queue.INSTRUCTIONS, full)
        header = json.loads(full.split('\n\n')[0])
        self.assertEqual(Path(header['instructions_path']).read_text(), queue.INSTRUCTIONS + '\n\n' + rules)
        header2 = json.loads(queue.read_request(ids[1]).split('\n\n')[0])
        self.assertEqual(header['instructions_path'], header2['instructions_path'])
        compact = queue.read_request(ids[1], include_schema=False, include_instructions=False)
        self.assertNotIn(rules, compact)
        self.assertIn('Page two body', compact)
        self.assertIn('instructions_path', compact)
        self.assertLess(len(compact), len(full) // 2)
        # Different rules => different packet, even for identical source text.
        with self.assertRaises(queue.AgentExtractionPending) as raised:
            queue.request('Extract "X" from this page.\n\nPage one body', extractor.SingleEventExtraction,
                          instructions=rules + ' Extra rule.')
        self.assertNotEqual(raised.exception.request_id, ids[0])
        self.assertTrue(queue.has_request('Extract "X" from this page.\n\nPage one body',
                                          extractor.SingleEventExtraction, instructions=rules))
        status = {item['request_id']: item for item in queue.status()}
        self.assertEqual(len({item['instructions_hash'] for item in status.values()}), 2)
        self.assertTrue(all(item['prompt_chars'] > 0 for item in status.values()))


class BatchReadSubmitTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch.object(queue, '_work_dir', Path(temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _queue(self, n, rules='Shared rules.'):
        ids = []
        for i in range(n):
            with self.assertRaises(queue.AgentExtractionPending) as raised:
                queue.request(f'Extract "E{i}" from this page.\n\nBody {i} on October 3, 2026.',
                              extractor.SingleEventExtraction, instructions=rules)
            ids.append(raised.exception.request_id)
        return ids

    def test_read_batch_writes_shared_text_once_and_every_packet(self):
        ids = self._queue(3)
        manifest = queue.work_dir() / 'm.json'
        queue.atomic_json(manifest, [dict(request_id=i, response_path=str(queue.work_dir() / f'r-{i}.json')) for i in ids])
        output, toc, chars = queue.read_batch(manifest)
        text = output.read_text()
        self.assertEqual(len(toc), 3)
        self.assertEqual(text.count('Shared rules.'), 1)
        self.assertEqual(text.count('----- SCHEMA SingleEventExtraction'), 1)
        for i, rid in enumerate(ids):
            self.assertEqual(text.count(f'===== PACKET {rid} ====='), 1)
            self.assertIn(f'Body {i} on October 3, 2026.', text)
        self.assertEqual(chars, len(text))
        compact_out, _, compact_chars = queue.read_batch(manifest, include_schema=False, include_instructions=False,
                                                        output=queue.work_dir() / 'compact.txt')
        self.assertLess(compact_chars, chars)
        self.assertNotIn('Shared rules.', compact_out.read_text())
        with self.assertRaises(queue.AgentExtractionInvalid):
            queue.read_batch(self._bad_manifest())

    def _bad_manifest(self):
        bad = queue.work_dir() / 'bad.json'
        queue.atomic_json(bad, [dict(nope=1)])
        return bad

    def test_submit_batch_accepts_good_and_reports_each_rejection(self):
        ids = self._queue(3)
        rdir = queue.work_dir() / 'responses'
        rdir.mkdir()
        def result(i):
            return dict(description=f'Prose {i}.', emoji='🎭', hashtags=['Theater', 'Free'],
                        location='Venue', sublocation=None,
                        occurrences=[dict(start_date='2026-10-03', start_time='7pm', end_date=None, end_time=None)])
        queue.atomic_json(rdir / f'{ids[0]}.json', dict(request_id=ids[0], status='complete', coverage='complete', result=result(0)))
        # ids[1]: schema violation (missing required emoji); ids[2]: no file at all
        queue.atomic_json(rdir / f'{ids[1]}.json', dict(request_id=ids[1], status='complete', coverage='complete',
                                                        result={k: v for k, v in result(1).items() if k != 'emoji'}))
        manifest = queue.work_dir() / 'm.json'
        queue.atomic_json(manifest, ids)
        accepted, rejected = queue.submit_batch(manifest, responses_dir=rdir)
        self.assertEqual(accepted, [ids[0]])
        self.assertEqual([r for r, _ in rejected], [ids[1], ids[2]])
        self.assertIn('missing', rejected[1][1])
        statuses = {item['request_id']: item['status'] for item in queue.status()}
        self.assertEqual(statuses[ids[0]], 'complete')
        self.assertEqual(statuses[ids[1]], 'pending')
        # A second pass with the fixed file accepts it; the first stays idempotent.
        queue.atomic_json(rdir / f'{ids[1]}.json', dict(request_id=ids[1], status='complete', coverage='complete', result=result(1)))
        queue.atomic_json(rdir / f'{ids[2]}.json', dict(request_id=ids[2], status='complete', coverage='complete', result=result(2)))
        accepted, rejected = queue.submit_batch(manifest, responses_dir=rdir)
        self.assertEqual(len(accepted), 3)
        self.assertEqual(rejected, [])
