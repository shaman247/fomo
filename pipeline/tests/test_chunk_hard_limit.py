"""Public chunk selection must enforce its cap even on the event-marker path."""
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extractor import chunk_content, chunk_content_by_events, MAX_CHUNK_CHARS


def card(i, size=9000, prefix='### ['):
    return (f'{prefix}Event {i}](https://example.test/{i})\n'
            + f'Description {i}: ' + 'x' * size
            + f'\nSeptember 25, 2026 7pm — slot {i}\n')


class EventChunkHardLimitTests(unittest.TestCase):
    def assert_preserved(self, content, chunks, cap):
        self.assertTrue(chunks)
        self.assertTrue(all(0 < len(c) <= cap for c in chunks))
        self.assertEqual(re.sub(r'\s+', '', ''.join(chunks)), re.sub(r'\s+', '', content))

    def test_records_that_fit_keep_title_description_and_date_together(self):
        records = [card(i) for i in range(60)]
        content = '\n'.join(records)
        chunks, method = chunk_content(content)
        self.assertEqual(method, 'events')
        self.assert_preserved(content, chunks, MAX_CHUNK_CHARS)
        for record in records:
            self.assertEqual(sum(record in c for c in chunks), 1)
        # Pack three 9 KB records together, respecting the original 50-record
        # grouping; do not double packet count by retaining old overfilled seams.
        self.assertEqual(len(chunks), 21)

    def test_one_huge_record_and_preamble_are_bounded_without_losing_text(self):
        for content in ('preamble ' * 7000 + '\n' + '\n'.join(card(i, 100) for i in range(60)),
                        '\n'.join(card(i, 100000 if i == 10 else 100) for i in range(60))):
            chunks, method = chunk_content(content)
            self.assertEqual(method, 'events')
            self.assert_preserved(content, chunks, MAX_CHUNK_CHARS)

    def test_safe_chunks_are_byte_identical_including_mixed_size_page(self):
        content = '\n'.join(card(i, 10 if i < 50 else 2000) for i in range(101))
        original = chunk_content_by_events(content)
        chunks, method = chunk_content(content)
        self.assertEqual(method, 'events')
        self.assertEqual(chunks[0], original[0])
        self.assertEqual(chunks[-1], original[-1])
        self.assert_preserved(content, chunks, MAX_CHUNK_CHARS)

    def test_method_selection_does_not_expand_to_other_levels_or_small_marker_counts(self):
        for content in ('\n'.join(card(i, 1000, '  * #### [') for i in range(60)),
                        '\n'.join(card(i, 10000) for i in range(4))):
            chunks, method = chunk_content(content)
            self.assertEqual(method, 'size')
            self.assert_preserved(content, chunks, MAX_CHUNK_CHARS)

    def test_numbered_markers_and_custom_cap(self):
        records = [card(i, 200, f'{i+1}. ### [') for i in range(12)]
        content = '\n'.join(records)
        chunks, method = chunk_content(content, events_per_chunk=5, max_chars=1000)
        self.assertEqual(method, 'events')
        self.assert_preserved(content, chunks, 1000)
        for record in records:
            self.assertEqual(sum(record in c for c in chunks), 1)

    def test_short_and_normal_event_pages_are_unchanged(self):
        for count in (2, 51, 101):
            content = '\n'.join(card(i, 10) for i in range(count))
            chunks, method = chunk_content(content)
            self.assertEqual(chunks, chunk_content_by_events(content))
            self.assertEqual(method, 'single' if count == 2 else 'events')


if __name__ == '__main__':
    unittest.main()
