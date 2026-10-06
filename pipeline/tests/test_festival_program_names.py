"""Shared festival branding must not merge separately named productions."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger


class FestivalProgramNameTests(unittest.TestCase):
    PAIRS = (
        ('The Third Choice', 'Mother.'),
        ('Becoming Psychic', 'Hagnificent'),
        ('Fainting Couch: A One Woman Show… (With a Butler)', 'Mother.'),
    )

    def test_distinct_source_programs_are_rejected_in_both_orders(self):
        for first, second in self.PAIRS:
            for left_dash in ('-', '–', '—'):
                for right_dash in ('-', '–', '—'):
                    a = f'{first} {left_dash} NYC Fringe Festival 2026'
                    b = f'{second} {right_dash} NYC Fringe Festival 2026'
                    with self.subTest(a=a, b=b):
                        self.assertFalse(merger.are_names_similar(a, b))
                        self.assertFalse(merger.are_names_similar(b, a))

    def test_rule_is_not_tied_to_one_city_or_festival(self):
        self.assertFalse(merger.are_names_similar(
            'Glass Birds – River Theatre Festival', 'Red Moon – River Theatre Festival'))

    def test_abbreviated_program_and_suffix_spelling_keep_existing_match(self):
        self.assertTrue(merger.are_names_similar(
            'Becoming Psychic – NYC Fringe Festival 2026',
            'Becoming Psychic — Nyc Fringe Festival 2026'))
        self.assertTrue(merger.are_names_similar(
            'Fainting Couch – NYC Fringe Festival 2026',
            'Fainting Couch: A One Woman Show (With a Butler) – NYC Fringe Festival 2026'))

    def test_ambiguous_metadata_and_multiple_separators_do_not_trigger_guard(self):
        pairs = (
            ('NEW DATE – River Festival', 'SOLD OUT – River Festival'),
            ('Postponed – River Festival', 'Glass Birds – River Festival'),
            ('Tickets available – River Festival', 'Glass Birds – River Festival'),
            ('Lecture – River Festival', 'Talk – River Festival'),
            ("Alex's – River Festival", 'Company – River Festival'),
            ('Glass Birds – River Festival', 'Red Moon – Mountain Festival'),
            ('RESONANCE - Stephane Clement - Nicolaus Gelin',
             'RESSONNANCE - Stéphane Clément - Nicolaus Gelin'),
            ('Glass Birds - Matinee - River Festival', 'Red Moon - River Festival'),
            ('Glass Birds|Night - River Festival', 'Red Moon - River Festival'),
            ('Glass Birds-River Festival', 'Red Moon-River Festival'),
        )
        for a, b in pairs:
            with self.subTest(a=a, b=b):
                self.assertFalse(merger._festival_program_titles_differ(a, b, '', ''))
                self.assertFalse(merger._festival_program_titles_differ(b, a, '', ''))

    def test_general_dash_extension_counterexamples_stay_out_of_scope(self):
        pairs = (
            ('NEW DATE – Building Blocks: Networking and Maintaining Donor Relationships',
             'SOLD OUT – Building Blocks: Networking and Maintaining Donor Relationships'),
            ('Exhibition – America, the Beautiful? Opening Reception',
             'Opening – America, the Beautiful? Opening Reception'),
            ('MOCA CINEMA – The Professor: Tai Chi’s Journey West',
             'Screening – The Professor: Tai Chi’s Journey West'),
        )
        for a, b in pairs:
            with self.subTest(a=a, b=b):
                self.assertTrue(merger.are_names_similar(a, b))
                self.assertTrue(merger.are_names_similar(b, a))


if __name__ == '__main__':
    unittest.main()
