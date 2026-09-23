"""Explicit dubbed/subtitled versions survive every fresh-source matching tier."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger


class ScreeningVersionTests(unittest.TestCase):
    def test_williams_pairs_remain_distinct_in_both_arrival_orders(self):
        for title in ("Howl's Moving Castle", 'My Neighbor Totoro',
                      'Nausicaä of the Valley of the Wind'):
            a = title + ' (Dub) in the Rivoli! *Studio Ghibli Tuesdays*'
            b = title + ' (Sub) in the Rivoli! *Studio Ghibli Tuesdays*'
            self.assertFalse(merger.are_names_similar(a, b))
            self.assertFalse(merger.are_names_similar(b, a))

    def test_long_labels_and_brackets(self):
        for a, b in [('Ninja Scroll (Dubbed)', 'Ninja Scroll (Subtitled)'),
                     ('Totoro [English Dub]', 'Totoro [Eng Sub]'),
                     ('Totoro (Dubbed Version)', 'Totoro (Japanese Subtitles)'),
                     ('Totoro (Dub)', 'Totoro (Open Cap/Eng Sub)')]:
            self.assertTrue(merger.is_false_positive(a, b))

    def test_absent_or_mixed_version_does_not_invent_a_conflict(self):
        for a, b in [('Totoro (Dub)', 'Totoro'),
                     ('Totoro (Sub)', 'Totoro (Subtitled)'),
                     ('Totoro (Dub/Sub)', 'Totoro (Sub)'),
                     ('Pressure (Open Cap/Eng Sub)', 'Pressure')]:
            self.assertTrue(merger.are_names_similar(a, b))

    def test_music_names_and_content_parentheticals_are_not_language_labels(self):
        for name in ('Ghost Dubs Live', 'Jungle, Dub, House',
                     'A Sub for Christmas', 'Music (Dub with Paul C)',
                     'A Lecture (Subcultures and Dub Music)'):
            self.assertFalse(merger._screening_language_modes(name))

    def test_dateless_match_checks_versions_even_when_normalized_names_equal(self):
        existing = {'id': 1, 'name': 'Totoro (Dub)', 'location_id': 10}
        self.assertEqual(merger.normalize_name_for_dedup(existing['name']),
                         merger.normalize_name_for_dedup('Totoro (Sub)'))
        self.assertIsNone(merger._match_dateless_crawl_event(
            'Totoro (Sub)', 10, None, None, None, {10: [existing]}, {}, {}))
        self.assertIsNone(merger._match_dateless_crawl_event(
            'Totoro (Sub)', None, None, None, None, {}, {}, {}, 7, {7: [existing]}))
        self.assertEqual(merger._match_dateless_crawl_event(
            'Totoro (Dub)', 10, None, None, None, {10: [existing]}, {}, {}), 1)

    def test_shared_url_and_slot_do_not_override_explicit_versions(self):
        url = 'https://example.org/film/totoro'; slots = {('2026-10-01', '7pm')}
        key = (7, merger.normalize_url_for_identity(url))
        index = {key: [{'id': 1, 'name': 'Totoro (Dub)', 'location_id': 10, 'slots': slots}]}
        self.assertIsNone(merger._match_by_url_identity(
            'Totoro (Sub)', url, 7, 10, slots, index, {key: 1}, set(), {}))
        self.assertEqual(merger._match_by_url_identity(
            'Totoro (Dubbed)', url, 7, 10, slots, index, {key: 1}, set(), {}), 1)

    def test_unqualified_source_does_not_erase_dedicated_version_label(self):
        for label in ('(Dub)', '(Sub)', '(Dubbed)', '[Subtitled]', '(English Dub)'):
            self.assertIsNone(merger.merged_screening_display_name('Totoro ' + label, 'Totoro'))
        self.assertEqual(merger.merged_screening_display_name(
            'Pressure (Open Cap/Eng Sub)', 'Pressure'), 'Pressure')
        self.assertIsNone(merger.merged_screening_display_name('Totoro (Dub)', 'Totoro (Sub)'))
