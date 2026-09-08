"""A partitioned public export must retain the complete searchable event data."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_chunks import split_events, write_remainder_chunks


class ExportChunksTests(unittest.TestCase):
    def test_partition_retains_order_occurrences_and_unicode(self):
        events = [{'id': i, 'name': '🎵 音楽', 'occurrences': [['2026-09-07', '', '2026-12-07', '']]}
                  for i in range(40)]
        descriptions = {str(i): '長い説明' * 20 for i in range(40)}
        chunks = split_events(events, descriptions, max_bytes=1024)
        self.assertGreater(len(chunks), 1)
        self.assertEqual([event for chunk in chunks for event in chunk], events)
        for chunk in chunks:
            self.assertLessEqual(len(json.dumps(chunk, ensure_ascii=False).encode()), 1024)

    def test_oversized_event_is_never_dropped_or_split(self):
        events = [{'id': 1, 'name': 'x' * 1000}, {'id': 2, 'name': 'small'}]
        self.assertEqual(split_events(events, {}, max_bytes=100), [[events[0]], [events[1]]])
        self.assertEqual(split_events([], {}), [])

    def test_companions_reconstruct_descriptions_and_keep_legacy_files(self):
        events = [{'id': i, 'name': 'Event', 'lat': 40, 'lng': -74} for i in range(5)]
        descriptions = {i: 'description' * 20000 for i in range(5)}
        with tempfile.TemporaryDirectory() as directory:
            legacy = Path(directory) / 'events.remainder.json'
            legacy.write_text(json.dumps(events))
            names = write_remainder_chunks(directory, events, descriptions)
            loaded, desc = [], {}
            for name in names:
                loaded.extend(json.loads((Path(directory) / f'events.{name}.json').read_text()))
                desc.update(json.loads((Path(directory) / f'events.{name}.desc.json').read_text()))
                self.assertFalse((Path(directory) / f'locations.{name}.json').exists())
            self.assertEqual(loaded, events)
            self.assertEqual(desc, {str(k): v for k, v in descriptions.items()})
            self.assertEqual(json.loads(legacy.read_text()), events)


if __name__ == '__main__':
    unittest.main()
