"""Dates printed above their cards stay with those cards across chunk cuts (BL11).

Fixtures are trimmed real crawl excerpts (`fixtures/bl11_card_boundaries.json`).
Each positive case records the smallest `max_chars` at which the pre-change
chunker separated a card title from its date (or venue); the engine must now
keep every listed string in the title's chunk. Negative cases are pages whose
dates belong to the card ABOVE them and must be split exactly as before.
"""
from collections import Counter
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extractor as ex
from extractor import (carry_boundary_context, chunk_content, chunk_for_extraction,
                       cap_occurrences_per_chunk)

FIXTURES = json.loads((Path(__file__).parent / 'fixtures' / 'bl11_card_boundaries.json')
                      .read_text(encoding='utf-8'))


def chunk_holding(chunks, anchor, occurrence):
    """The chunk holding the `occurrence`-th (0-based) copy of `anchor`."""
    seen = 0
    for chunk in chunks:
        n = chunk.count(anchor)
        if seen + n > occurrence:
            return chunk
        seen += n
    raise AssertionError(f'{anchor!r} occurrence {occurrence} not found')


def nonblank(chunks):
    return Counter(l.strip() for c in chunks for l in c.split('\n') if l.strip())


class RealSourceCardBoundaryTests(unittest.TestCase):
    def test_titles_keep_their_dates_and_venues(self):
        for case in FIXTURES['positive']:
            with self.subTest(case['key']):
                chunks, _ = chunk_for_extraction(case['content'],
                                                 events_per_chunk=case['events_per_chunk'],
                                                 max_chars=case['max_chars'])
                self.assertGreater(len(chunks), 1)
                for anchor, occurrence, required in case['expect']:
                    chunk = chunk_holding(chunks, anchor, occurrence)
                    for text in required:
                        self.assertIn(text, chunk, f'{case["key"]}: {anchor} lost {text}')

    def test_no_content_lost_no_title_duplicated_and_cap_respected(self):
        for case in FIXTURES['positive']:
            with self.subTest(case['key']):
                content, cap = case['content'], case['max_chars']
                chunks, _ = chunk_for_extraction(content, events_per_chunk=case['events_per_chunk'],
                                                 max_chars=cap)
                self.assertTrue(all(len(c) <= cap for c in chunks))
                source = Counter(l.strip() for l in content.split('\n') if l.strip())
                out = nonblank(chunks)
                self.assertEqual(source - out, Counter(), 'source lines lost')
                extra = out - source
                # Only lead-in lines (dates, times, images, empty cells) are copied.
                self.assertTrue(all(ex._is_leadin_line(l) for l in extra), list(extra))

    def test_roxy_final_dated_card_keeps_its_day_and_showtime(self):
        # cr124464: the last Misconceived showing (Saturday, October 03, 8:30PM,
        # ticket 7778) was extracted as an undated duplicate in two captures.
        case = next(c for c in FIXTURES['positive'] if c['key'] == 'roxy')
        chunks, _ = chunk_for_extraction(case['content'], max_chars=case['max_chars'])
        chunk = chunk_holding(chunks, '###  The Misconceived', 3)
        head = chunk[:chunk.index('###  The Misconceived')]
        self.assertIn('Saturday, October 03', head)
        self.assertIn('8:30PM', head)
        self.assertIn('purchase/7778', head)


class TrailingDatePagesAreUntouched(unittest.TestCase):
    def test_own_date_pages_learn_no_card_and_split_as_before(self):
        # Regal lists each film's own dates BELOW it; Levittown's featured cards
        # print title, own date, then `#### Age Group:` labels.
        for case in FIXTURES['negative']:
            with self.subTest(case['key']):
                content = case['content']
                self.assertIsNone(ex._leadin_card_signature(content.split('\n')))
                cap = max(1200, len(content) // 3)
                expected, _ = chunk_content(content, max_chars=cap)
                expected = cap_occurrences_per_chunk(expected)
                self.assertEqual(chunk_for_extraction(content, max_chars=cap)[0], expected)

    def test_card_own_date_under_its_title_is_not_carried(self):
        cards = '\n'.join(f'### [Show {i}](https://example.test/{i})\n'
                          f'Fri, September {i + 4}, 2026\n'
                          'A description of the show.\n' for i in range(6))
        chunks = [c for c in cards.split('\n\n')]
        self.assertEqual(carry_boundary_context(chunks), chunks)


class SyntheticLeadInTests(unittest.TestCase):
    def _cards(self, n):
        return '\n'.join(f'Sat, Oct {i + 1}, 2026\n![](https://img.test/{i}.jpg)\n'
                         f'### [Show {i}](https://example.test/{i})\n'
                         'Body text for this show. ' * 3 + '\n' for i in range(n))

    def test_section_header_reaches_mid_day_cards(self):
        # One day heading governs several cards (Roxy, GreenThumb, Grolier).
        content = '## Saturday, October 3, 2026\n' + '\n'.join(
            f'7:{i}0PM  [Buy](https://t.test/{i})\n### Film {i}\nA film. ' * 4 + '\n'
            for i in range(8)) + '\n## Sunday, October 4, 2026\n' + '\n'.join(
            f'8:{i}0PM  [Buy](https://t.test/s{i})\n### Late {i}\nA film. ' * 4 + '\n'
            for i in range(8))
        chunks, _ = chunk_for_extraction(content, max_chars=1500)
        self.assertGreater(len(chunks), 2)
        for chunk in chunks:
            first_title = next((l for l in chunk.split('\n') if l.startswith('### ')), None)
            if first_title is None:
                continue
            head = chunk[:chunk.index(first_title)]
            self.assertTrue('October 3' in head or 'October 4' in head, chunk[:200])

    def test_dangling_date_is_copied_only_onto_a_card(self):
        listing = self._cards(6)
        onto_card = [listing + 'Sat, Oct 20, 2026',
                     '### [Show 20](https://example.test/20)\nBody text.']
        self.assertTrue(carry_boundary_context(onto_card)[1].startswith('Sat, Oct 20, 2026\n'))
        # A footer heading has another shape (level 2, unlinked) than the cards.
        onto_footer = [listing + 'Sat, Oct 20, 2026',
                       '## Supported By\n[Sponsor](https://sponsor.test)']
        self.assertEqual(carry_boundary_context(onto_footer), onto_footer)

    def test_small_or_single_chunk_pages_are_unchanged(self):
        content = self._cards(2)
        self.assertEqual(chunk_for_extraction(content), ([content], 'single'))
        self.assertEqual(carry_boundary_context([content]), [content])


if __name__ == '__main__':
    unittest.main()
