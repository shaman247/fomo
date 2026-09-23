"""List-wrapped cards retain their titles and dates under event chunking."""
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extractor import chunk_content, chunk_content_by_events, chunk_content_by_size


class BulletEventChunkingTests(unittest.TestCase):
    def test_mixed_list_wrappers_keep_complete_cards_under_the_cap(self):
        prefixes = ('### [', '  * ### [', '\t-\t###\t[', '12. ### [')
        cards = [f'{prefixes[i % 4]}Show {i}](https://example.test/{i})\n'
                 + ('Description. ' * (2 + i % 5))
                 + f'\nSeptember 25, 2026 at 7pm — slot {i}\n'
                 for i in range(16)]
        content = '\n'.join(cards)
        chunks, method = chunk_content(content, events_per_chunk=5, max_chars=400)
        self.assertEqual(method, 'events')
        self.assertTrue(all(0 < len(c) <= 400 for c in chunks))
        self.assertEqual(re.sub(r'\s+', '', ''.join(chunks)), re.sub(r'\s+', '', content))
        for card in cards:
            self.assertEqual(sum(card in c for c in chunks), 1)

    def test_bullet_wrapping_does_not_change_record_grouping(self):
        plain = '\n'.join(f'### [Show {i}](https://example.test/{i})\n'
                          f'September 25, 2026 at 7pm — slot {i}' for i in range(11))
        expected = chunk_content_by_events(plain, events_per_chunk=4)
        for wrapper in ('  * ', '  - '):
            wrapped = plain.replace('### [', wrapper + '### [')
            chunks = chunk_content_by_events(wrapped, events_per_chunk=4)
            self.assertEqual([c.replace(wrapper + '### [', '### [') for c in chunks], expected)

    def test_date_leading_h5_listings_keep_the_existing_size_boundaries(self):
        # Drom's date/door line belongs to the following linked h5 title.
        # Treating every heading level as a marker strands this line.
        content = '\n'.join(f'Fri, September {i + 10} - Doors: 7:00 PM\n'
                            f'##### [Show {i}](https://example.test/{i})\n'
                            'A concert.\n' for i in range(8))
        chunks, method = chunk_content(content, events_per_chunk=2, max_chars=300)
        self.assertEqual(method, 'size')
        self.assertEqual(chunks, chunk_content_by_size(content, 300))

    def test_small_bulleted_calendar_stays_single(self):
        content = '  * ### [One show](https://example.test/1)\nSeptember 25, 2026 at 7pm\n'
        self.assertEqual(chunk_content(content), ([content], 'single'))


if __name__ == '__main__':
    unittest.main()
