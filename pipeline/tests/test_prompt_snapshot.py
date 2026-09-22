"""A resumed run uses its own rules, but never replays answers for new input."""
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_extraction as queue
import extractor


class PromptSnapshotTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.previous = queue.work_dir()
        self.addCleanup(queue.configure, self.previous)
        queue.configure(self.root)
        self.manifest = {'reference_date': '2026-09-20',
                         'prompt_snapshot': queue.snapshot_prompts(extractor.prompt_templates())}
        queue.atomic_json(self.root / 'run.json', self.manifest)

    def prompts(self, source='No upcoming events.', notes='Use the event venue.'):
        common = ('https://example.test/events', source, queue.reference_date(), 'Venue', notes)
        return [
            (extractor.get_prompt(*common, request_id='cr-1'), None),
            (extractor.get_vision_prompt(*common, request_id='cr-1'), None),
            (extractor.get_chunk_prompt(source, queue.reference_date(), request_id='cr-1'),
             extractor._prompt_rule('FULL_PASS_RULE') + '\n\n' + extractor.get_chunk_instructions(notes)),
            (extractor.get_enrichment_prompt(['Event'], 'Venue', request_id='cr-1',
                                            content_snippets={'Event': source}), None),
            (extractor._prompt_rule('DETAIL_PROMPT_TEMPLATE').format(
                current_date=queue.reference_date(), event_name='Event',
                url_section='URL: https://example.test/event', content=source),
             extractor.detail_instructions(notes)),
        ]

    def edited_rules(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        for name, text in extractor.prompt_templates().items():
            if name in vars(extractor):
                stack.enter_context(patch.object(extractor, name, text + '\nUpdated extraction rules.'))
            else:
                stack.enter_context(patch.object(extractor.city_config, 'extraction_' + name,
                                                 return_value=text + '\nUpdated city rules.'))
        stack.enter_context(patch.object(queue, 'INSTRUCTIONS', queue.INSTRUCTIONS + ' New protocol rules.'))

    def test_all_prompt_paths_and_protocol_stay_stable_after_rule_edits(self):
        before = self.prompts()
        self.edited_rules()
        queue.configure(self.root)  # A new resume reads the saved manifest.
        self.assertEqual(self.prompts(), before)
        self.assertEqual(queue._instructions(), self.manifest['prompt_snapshot']['templates']['protocol'])
        self.assertEqual(extractor._prompt_rule('COVERAGE_REVIEW_RULE'),
                         self.manifest['prompt_snapshot']['templates']['COVERAGE_REVIEW_RULE'])

    def test_accepted_packet_replays_after_edits_but_new_source_or_notes_do_not(self):
        prompt, instructions = self.prompts()[2]
        with self.assertRaises(queue.AgentExtractionPending) as raised:
            queue.request(prompt, extractor.EventList, instructions=instructions)
        pending = raised.exception
        response = self.root / 'answer.json'
        queue.atomic_json(response, {'request_id': pending.request_id, 'status': 'complete',
                                    'coverage': 'complete', 'empty_reason': 'Page explicitly has no upcoming events.',
                                    'result': {'request_id': 'cr-1', 'events': []}})
        queue.submit(pending.request_id, response)
        self.edited_rules()
        queue.configure(self.root)
        prompt, instructions = self.prompts()[2]
        self.assertEqual(json.loads(queue.request(prompt, extractor.EventList,
                                                  instructions=instructions))['events'], [])
        self.assertEqual(len(queue.status()), 1)
        for kwargs in ({'source': 'Concert on September 22, 2026.'}, {'notes': 'Use the offsite venue.'}):
            with self.subTest(kwargs=kwargs):
                prompt, instructions = self.prompts(**kwargs)[2]
                with self.assertRaises(queue.AgentExtractionPending) as changed:
                    queue.request(prompt, extractor.EventList, instructions=instructions)
                self.assertNotEqual(changed.exception.request_id, pending.request_id)

    def test_source_braces_are_literal_and_reference_data_still_changes(self):
        prompt = extractor.get_prompt('url', '{EVENT_STATUS_RULE}', '2026-09-20', 'Venue', '{notes}',
                                      existing_events=[{'name': '{name}', 'occurrences': []}])
        self.assertIn('Website content:\n\n{EVENT_STATUS_RULE}', prompt)
        self.assertIn('IMPORTANT: {notes}', prompt)
        self.assertIn('"name": "{name}"', prompt)

    def test_new_runs_pick_up_current_rules(self):
        before = self.prompts()
        self.edited_rules()
        queue.configure(self.root / 'new-run')
        queue.atomic_json(queue.work_dir() / 'run.json', {
            'reference_date': '2026-09-20',
            'prompt_snapshot': queue.snapshot_prompts(extractor.prompt_templates())})
        after = self.prompts()
        for old, new in zip(before, after):
            self.assertNotEqual(old, new)

    def test_legacy_workspace_keeps_current_rules_without_relabeling_old_work(self):
        self.manifest.pop('prompt_snapshot')
        queue.atomic_json(self.root / 'run.json', self.manifest)
        before = self.prompts()
        self.edited_rules()
        self.assertNotEqual(self.prompts(), before)
        self.assertNotIn('prompt_snapshot', queue._read_json(self.root / 'run.json'))

    def test_corrupt_or_incomplete_snapshot_fails_closed(self):
        for snapshot in (None, 'invalid', {'templates': {}, 'sha256': 'wrong'}, queue.snapshot_prompts({})):
            with self.subTest(snapshot=snapshot):
                self.manifest['prompt_snapshot'] = snapshot
                queue.atomic_json(self.root / 'run.json', self.manifest)
                with self.assertRaises(queue.AgentExtractionInvalid):
                    extractor.get_chunk_instructions()


if __name__ == '__main__':
    unittest.main()
