"""Regression coverage for event-identity boundaries in enrichment context."""
import json
import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extractor import extract_content_snippets
import extractor


class EnrichmentContextTests(unittest.TestCase):
    def test_saved_corruption_cases_recover_their_own_prose(self):
        cases = json.loads((Path(__file__).parent / 'fixtures' / 'enrichment_context_cards.json').read_text())
        for case in cases:
            with self.subTest(event=case['event_id']):
                snippet = extract_content_snippets([case['name']], case['content'])[case['name']]
                self.assertIn(case['must_contain'], snippet)
                self.assertNotIn(case['must_not_contain'], snippet)
                self.assertNotIn('https://', snippet)
                self.assertLessEqual(len(snippet), 500)

    def test_caption_before_heading_and_next_card_date_are_excluded(self):
        content = '''## [Previous](https://example.org/old)
Other event prose.
![Target](https://example.org/target.png)
Dec 5
## [Target](https://example.org/target)
Correct description.
![Next](https://example.org/next.png)
Dec 12
## [Next](https://example.org/next)
Next event prose.
'''
        self.assertEqual(extract_content_snippets(['Target'], content), {'Target': 'Target\nCorrect description.'})

    def test_presentation_normalization_preserves_all_words_and_numbers(self):
        content = '### [* IN PERSON *1:1 Advice](https://example.org/advice)\nBusiness advice.'
        self.assertIn('Business advice.', extract_content_snippets(['IN-PERSON 1:1 Advice'], content)['IN-PERSON 1:1 Advice'])
        self.assertEqual(extract_content_snippets(['IN PERSON 2:1 Advice', 'Advice'], content), {})

    def test_generic_word_does_not_select_another_event(self):
        self.assertEqual(extract_content_snippets(['IN PERSON Finance'], '## [IN PERSON Maker Lab](https://example.org/maker)\nArt tools.'), {})

    def test_mention_inside_another_card_is_not_an_identity(self):
        content = '## [Other](https://example.org/other)\nWe also host Target next week.'
        self.assertEqual(extract_content_snippets(['Target'], content), {})

    def test_same_title_at_distinct_urls_is_ambiguous(self):
        content = '## [Tour](https://example.org/one)\nRussian language.\n## [Tour](https://example.org/two)\nEnglish language.'
        self.assertEqual(extract_content_snippets(['Tour'], content), {})

    def test_repeated_same_url_is_not_ambiguous(self):
        card = '## [Tour](https://example.org/tour)\nExplore the gallery.\n'
        self.assertEqual(extract_content_snippets(['Tour'], card * 2), {'Tour': 'Tour\nExplore the gallery.'})

    def test_plain_and_bulleted_headings_and_html_entities(self):
        content = '## Other\nOther prose.\n* ### Art &amp; Music\nCreate and listen.\n### Next\nDo not include.'
        self.assertEqual(extract_content_snippets(['Art & Music'], content), {'Art & Music': 'Art &amp; Music\nCreate and listen.'})

    def test_nested_brackets_in_linked_heading(self):
        content = '## [ADVENTURE[s]](https://example.org/adventures)\nJoin the dance.'
        self.assertIn('Join the dance.', extract_content_snippets(['ADVENTURE[s]'], content)['ADVENTURE[s]'])

    def test_no_boundaries_means_no_guessed_context(self):
        self.assertEqual(extract_content_snippets(['Target'], 'Target\nSome text\nAnother event\nUnrelated prose'), {})
        self.assertEqual(extract_content_snippets(['Target'], ''), {})
        self.assertEqual(extract_content_snippets(['Target'], '# Target\nText', 0), {})

    def test_generic_subheading_stops_context_conservatively(self):
        content = '## Target\nFocal prose.\n## More Events\nOther programs.'
        self.assertEqual(extract_content_snippets(['Target'], content), {'Target': 'Target\nFocal prose.'})

    def test_sync_enrichment_rejects_description_without_verified_context(self):
        result = {'enrichments': [{'name': 'Target', 'description': 'Made up details.'}]}
        with patch.object(extractor.llm_providers, 'generate_structured',
                          AsyncMock(return_value=json.dumps(result))):
            out = asyncio.run(extractor.enrich_events_batch(
                ['Target'], 'Venue', content='## Other\nTarget is mentioned here.'))
        self.assertEqual(out['Target']['description'], 'No description available.')

    def test_batch_enrichment_applies_the_same_context_guard(self):
        request = SimpleNamespace(metadata={'request_id': 'cr-1-enrich-0',
                                           'crawl_result_id': '1', 'website_name': 'Venue'})
        response = SimpleNamespace(error=None, response=SimpleNamespace(text=json.dumps({
            'request_id': 'cr-1-enrich-0',
            'enrichments': [{'name': 'Target', 'description': 'Made up details.'},
                            {'name': 'Known', 'description': 'Verified description.'}],
        })))
        prep = extractor.PreparedExtraction(1, 'Venue', 'chunked', content='## Known\nVerified description.')
        events = [{'name': name, 'location': 'Venue'} for name in ['Target', 'Known']]
        result = extractor.process_enrichment_responses([request], [response], {1: events}, {1: prep})
        records = {e['name']: e for e in json.loads(result[1])['events']}
        self.assertEqual(records['Target']['description'], 'No description available.')
        self.assertEqual(records['Known']['description'], 'Verified description.')


if __name__ == '__main__':
    unittest.main()
