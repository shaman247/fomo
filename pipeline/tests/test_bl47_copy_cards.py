"""BL47 (2026-10-16): a "Copy of <title>" card is its own listing.

Gladys Books & Wine (w994) duplicated its Oct 30 podcast card for an Oct 31
Halloween party and left the title "Copy of I DO the Bending Live Podcast
Recording!". Both extractions (cr-130400, cr-131751, single-call path) folded
Oct 31 into the podcast event. The rule must reach the single-call and chunked
prompts, the two paths that carry ONE LISTING PER URL.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extractor

GLADYS = """Fri, 30 Oct
* * *
06:30 PM - 09:00 PM
### I DO the Bending Live Podcast Recording!
GLADYS BOOKS AND WIN...
Sat, 31 Oct - Sun, 01 Nov
* * *
07:00 PM - 01:00 AM
### Copy of I DO the Bending Live Podcast Recording!
GLADYS BOOKS AND WIN..."""


class CopiedCardRuleTests(unittest.TestCase):

    def rule_lines(self, prompt):
        return [line for line in prompt.splitlines() if line.startswith('- COPIED CARDS:')]

    def test_single_and_chunked_prompts_carry_the_rule_once(self):
        prompts = {
            'single': extractor.get_prompt('https://gladysbooksandwine.com/pages/events', GLADYS,
                                           '2026-10-16', 'Gladys Books & Wine', ''),
            'chunk': extractor.get_chunk_instructions(''),
        }
        for path, prompt in prompts.items():
            with self.subTest(path=path):
                lines = self.rule_lines(prompt)
                self.assertEqual(len(lines), 1)
                self.assertIn('never fold its dates into <title>', lines[0])
                self.assertIn('including "Copy of"', lines[0])

    def test_rule_sits_next_to_one_listing_per_url(self):
        for template in (extractor.CHUNK_RULES, extractor.SINGLE_PROMPT_TEMPLATE):
            lines = template.splitlines()
            idx = next(i for i, line in enumerate(lines) if line.startswith('- ONE LISTING PER URL:'))
            self.assertTrue(lines[idx + 1].startswith('- COPIED CARDS:'))


if __name__ == '__main__':
    unittest.main()
