"""BL43 (2026-10-16): sessions under one title held at different venues.

Oko Farms (w5273) lists "Introduction to Aquaponics" on Oct 24 at 99 Scott
Avenue and on Dec 19 at 616 East 40th Street, both under "Venue: Oko Farms".
cr-131354 (single-call path) returned one crawl_event at "Oko Farms" carrying
both dates, so the East Flatbush session landed on the Bushwick event. The
SESSION VENUES rule must reach the single-call and chunked prompts, beside
ONE LISTING PER URL and COPIED CARDS. The "<venue>, <street address>" form
matches the existing w5273-scoped alternate name "Oko Farms, 616 East 40th
Street" (location 11472).
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extractor

OKO = """### [Introduction to Aquaponics ](https://www.okofarms.org/eventsstackedev/introduction-to-aquaponics-gz3h3)
Date and time: Saturday, October 24, 2026 at 10:00 AM to 11:00 AM
Venue: Oko Farms
Address: 99 Scott Avenue, Brooklyn, NY, 11237
### [Introduction to Aquaponics ](https://www.okofarms.org/eventsstackedev/introduction-to-aquaponics-2rg58)
Date and time: Saturday, December 19, 2026 at 10:00 AM to 11:30 AM
Venue: Oko Farms
Address: 616 East 40th Street, Brooklyn, New York, 11203"""


class SessionVenueRuleTests(unittest.TestCase):

    def rule_lines(self, prompt):
        return [line for line in prompt.splitlines() if line.startswith('- SESSION VENUES:')]

    def test_single_and_chunked_prompts_carry_the_rule_once(self):
        prompts = {
            'single': extractor.get_prompt('https://www.okofarms.org/events', OKO,
                                           '2026-10-16', 'Oko Farms', ''),
            'chunk': extractor.get_chunk_instructions(''),
        }
        for path, prompt in prompts.items():
            with self.subTest(path=path):
                lines = self.rule_lines(prompt)
                self.assertEqual(len(lines), 1)
                self.assertIn("emit one event per venue with ONLY that venue's sessions", lines[0])
                self.assertIn('"<venue>, <street address>"', lines[0])

    def test_rule_follows_copied_cards(self):
        for template in (extractor.CHUNK_RULES, extractor.SINGLE_PROMPT_TEMPLATE):
            lines = template.splitlines()
            idx = next(i for i, line in enumerate(lines) if line.startswith('- COPIED CARDS:'))
            self.assertTrue(lines[idx + 1].startswith('- SESSION VENUES:'))

    def test_rule_is_part_of_the_prompt_snapshot(self):
        templates = extractor.prompt_templates()
        self.assertIn('- SESSION VENUES:', templates['CHUNK_RULES'])
        self.assertIn('- SESSION VENUES:', templates['SINGLE_PROMPT_TEMPLATE'])


if __name__ == '__main__':
    unittest.main()
