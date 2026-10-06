"""Vision evidence remains complete while reviewers read shared rules once."""
import asyncio
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_extraction as queue
import extractor


class VisionPacketTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        previous = queue.work_dir()
        self.addCleanup(queue.configure, previous)
        queue.configure(self.root)
        self.templates = extractor.prompt_templates()
        self.snapshot(self.templates)
        self.images = [{'inline_data': {'mime_type': 'image/png',
                                       'data': base64.b64encode(b'flyer bytes').decode()}}]
        self.source = ('Caption text.\n' * 20000) + 'Last event October 31 at 9pm. {EVENT_STATUS_RULE}'

    def snapshot(self, templates):
        queue.atomic_json(self.root / 'run.json', {
            'reference_date': '2026-09-26',
            'prompt_snapshot': queue.snapshot_prompts(templates)})

    def prepare(self, name='Venue A', notes='Use the stated room.', source=None):
        cursor = MagicMock()
        cursor.fetchone.return_value = (1, None, None, False, None)
        with patch.object(extractor, '_profile_candidate_urls', return_value=[]), \
                patch.object(extractor.db, 'get_crawled_content', return_value=source or self.source), \
                patch.object(extractor.db, 'find_prior_crawl_with_same_content', return_value=None), \
                patch.object(extractor, 'prepare_vision_content', new=AsyncMock(return_value=(self.images, 1))):
            return asyncio.run(extractor.prepare_extraction(
                cursor, 7, name, notes=notes, use_vision=True, base_url='https://example.test/'))

    def pending(self, prep):
        with self.assertRaises(queue.AgentExtractionPending) as raised:
            asyncio.run(extractor._generate_extraction_response(prep, None, None))
        pending = raised.exception
        return pending, queue._packet(pending.request_path)

    def test_prepared_path_keeps_all_evidence_and_shares_rules_across_venues(self):
        first, a = self.pending(self.prepare())
        second, b = self.pending(self.prepare('Venue B', 'This event is offsite.'))
        self.assertNotEqual(first.request_id, second.request_id)
        self.assertEqual(a['instructions'], b['instructions'])
        self.assertEqual(a['images'], self.images)
        self.assertIn(self.source, a['prompt'])
        self.assertIn('Use the stated room.', a['prompt'])
        self.assertIn('Venue B', b['prompt'])
        self.assertIn('This event is offsite.', b['prompt'])
        self.assertEqual(a['source_request_id'], 'cr-7')
        for rule in (extractor.WEEKLY_SCHEDULE_RULE, extractor.EVENT_STATUS_RULE,
                     'Use BOTH.', 'Do NOT fabricate.', 'Gallery hours'):
            self.assertIn(rule, a['instructions'])
            self.assertNotIn(rule, a['prompt'])
        manifest = self.root / 'batch.json'
        queue.atomic_json(manifest, [{'request_id': first.request_id}, {'request_id': second.request_id}])
        output, toc, _ = queue.read_batch(manifest)
        text = output.read_text()
        self.assertEqual(text.count('----- INSTRUCTIONS '), 1)
        self.assertEqual(text.count('Use BOTH.'), 1)
        self.assertEqual(text.count(self.source), 2)
        self.assertEqual([entry['images'] for entry in toc], [1, 1])
        compact = queue.read_request(first.request_id, include_schema=False, include_instructions=False)
        self.assertNotIn('Use BOTH.', compact)
        self.assertIn(self.source, compact)
        header = json.loads(compact.splitlines()[0])
        self.assertEqual(Path(header['images'][0]).read_bytes(), b'flyer bytes')
        self.assertIn('Use BOTH.', Path(header['instructions_path']).read_text())

    def test_direct_path_queues_the_same_shared_rules_and_full_source(self):
        with patch.object(extractor, 'prepare_vision_content', new=AsyncMock(return_value=(self.images, 1))):
            with self.assertRaises(queue.AgentExtractionPending) as raised:
                asyncio.run(extractor.extract_with_vision(
                    'https://example.test/', self.source, '2026-09-26', 'Venue', 'Venue notes'))
        packet = queue._packet(raised.exception.request_path)
        self.assertIn(self.source, packet['prompt'])
        self.assertIn('Venue notes', packet['prompt'])
        self.assertIn(extractor.get_vision_instructions(), packet['instructions'])
        self.assertEqual(packet['images'], self.images)

    def test_changed_captions_notes_or_image_bytes_never_replay_an_answer(self):
        prep = self.prepare()
        first, _ = self.pending(prep)
        response = self.root / 'answer.json'
        queue.atomic_json(response, dict(request_id=first.request_id, status='complete',
            coverage='complete', empty_reason='Transport fixture; no real event asserted.',
            result={'request_id': 'cr-7', 'events': []}))
        queue.submit(first.request_id, response)
        self.assertEqual(json.loads(asyncio.run(
            extractor._generate_extraction_response(prep, None, None)))['events'], [])
        changed_source, _ = self.pending(self.prepare(source=self.source + '\nNew caption.'))
        changed_notes, _ = self.pending(self.prepare(notes='New venue notes.'))
        self.images = [{'inline_data': {'mime_type': 'image/png',
                                       'data': base64.b64encode(b'changed flyer').decode()}}]
        changed_image, _ = self.pending(self.prepare())
        self.assertEqual(len({p.request_id for p in (first, changed_source, changed_notes, changed_image)}), 4)

    def test_inline_snapshot_replays_byte_identical_packet_without_new_template_key(self):
        inline = (Path(__file__).parent / 'fixtures' / 'vision_inline_prompt.txt').read_text()
        old = {k: v for k, v in self.templates.items() if k != 'VISION_INSTRUCTIONS_TEMPLATE'}
        old['VISION_PROMPT_TEMPLATE'] = inline
        self.snapshot(old)
        prompt = inline.format(current_date_string='2026-09-26', name='Venue A', url='',
            note_section='\n\nIMPORTANT: Use the stated room.',
            rid_section='\n\nIMPORTANT: Set request_id to "cr-7" in your response.',
            SCHEDULE_EXCEPTIONS_RULE=old['SCHEDULE_EXCEPTIONS_RULE'],
            EVENT_STATUS_RULE=old['EVENT_STATUS_RULE'], text_content=self.source)
        with self.assertRaises(queue.AgentExtractionPending) as raised:
            queue.request(prompt, extractor.EventList, images=self.images)
        first = raised.exception
        original = first.request_path.read_bytes()
        prep = self.prepare()
        self.assertIsNone(prep.vision_instructions)
        replay, _ = self.pending(prep)
        self.assertEqual(replay.request_id, first.request_id)
        self.assertEqual(first.request_path.read_bytes(), original)
        response = self.root / 'old-answer.json'
        queue.atomic_json(response, dict(request_id=first.request_id, status='complete',
            coverage='complete', empty_reason='Transport fixture; no real event asserted.',
            result={'request_id': 'cr-7', 'events': []}))
        queue.submit(first.request_id, response)
        with patch.object(extractor, 'VISION_INSTRUCTIONS_TEMPLATE', 'Future rules.'), \
                patch.object(extractor, 'VISION_PROMPT_TEMPLATE', 'Future prompt.'):
            self.assertEqual(json.loads(asyncio.run(extractor._generate_extraction_response(
                self.prepare(), None, None)))['events'], [])
        self.assertEqual(len(queue.status()), 1)

    def test_compact_snapshot_missing_its_instructions_fails_closed(self):
        self.templates.pop('VISION_INSTRUCTIONS_TEMPLATE')
        self.snapshot(self.templates)
        with self.assertRaises(queue.AgentExtractionInvalid):
            self.prepare()


if __name__ == '__main__':
    unittest.main()
