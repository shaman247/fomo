"""A shared pipe-delimited series must not merge unrelated programs."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from merger import are_names_similar, is_false_positive, _pipe_program_titles_differ


CASES = [
    ('Member Opening | Regeneration: Long Island’s History of Ecological Art and Care',
     'Talk | Regeneration: Long Island’s History of Ecological Art and Care'),
    ('Member Opening | Sanford Biggers: Drift', 'Talk | Sanford Biggers: Drift'),
    ('Exhibition | Tarot! Renaissance Symbols, Modern Visions',
     'Symposium | Tarot! Renaissance Symbols, Modern Visions'),
    ('Ghostbusters II | Big Screen at the Battery',
     'FC 26 (FIFA) Tournament | Big Screen at The Battery'),
    ('Ghostbusters II | Big Screen at the Battery',
     'West Side Story (1961)| Big Screen at The Battery'),
    ('Ghostbusters II | Big Screen at the Battery',
     'Once In A Lifetime| Big Screen at The Battery'),
    ('Keramat | Indonesian Film Forum', 'Darah Nyai | Indonesian Film Forum'),
    ('Hell’s Highway: The True Story of Highway Safety Films | Sex, Death, Cars!',
     'Titane | Sex, Death, Cars!'),
    ('Lecture | Fantasy and Reality: The Art of Johan Tobias Sergel',
     'Exhibition | Fantasy and Reality: The Art of Johan Tobias Sergel'),
    ('Exhibition | Ragtime: Cakewalk in Pianoland',
     'Curator Roundtable | Ragtime: Cakewalk in Pianoland'),
    ('The Misconceived - 35MM | Four by James N. Kienitz Wilkins',
     'The Plagiarists | Four by James N. Kienitz Wilkins'),
]


class PipeProgramNamesTest(unittest.TestCase):
    def test_saved_source_collisions_are_rejected_in_both_orders(self):
        for a, b in CASES:
            for left, right in ((a, b), (b, a)):
                with self.subTest(left=left, right=right):
                    self.assertTrue(is_false_positive(left, right))
                    self.assertFalse(are_names_similar(left, right))

    def test_battery_film_collisions_do_not_depend_on_pipe_spacing(self):
        for title in ('West Side Story (1961)', 'Once In A Lifetime'):
            for left_separator in (' | ', '| ', ' |', '|'):
                for right_separator in (' | ', '| ', ' |', '|'):
                    a = 'Ghostbusters II' + left_separator + 'Big Screen at The Battery'
                    b = title + right_separator + 'Big Screen at The Battery'
                    for left, right in ((a, b), (b, a)):
                        with self.subTest(left=left, right=right):
                            self.assertFalse(are_names_similar(left, right))

    def test_missing_spaces_do_not_split_identical_titles_or_embedded_pipes(self):
        for a, b in [
                ('"Folded" - Kehlani| One-Day Choir',
                 '"Folded" - Kehlani | One-Day Choir'),
                ('Mayor Mike Spano| Annual Mayor’s Community Service Awards',
                 'Mayor Mike Spano | Annual Mayor’s Community Service Awards'),
                ('Queer|Art X Doll Invasion Auction Exhibition',
                 'Queer|Art X Doll Invasion Auction Exhibition, Presented at Participant Inc & Salma Nyc'),
                ("Glass Lab: Mosaic + Fusing - Spring '26 (Monday|6pm)",
                 "Sold Out - Glass Lab: Mosaic + Fusing - Spring '26 (Monday|6pm)")]:
            for left, right in ((a, b), (b, a)):
                with self.subTest(left=left, right=right):
                    self.assertFalse(_pipe_program_titles_differ(left, right, '', ''))
                    self.assertTrue(are_names_similar(left, right))

    def test_abbreviations_accents_and_stemming_still_match(self):
        for a, b in [
                ('Spring Gardens | Community Art Series', 'Spring Garden | Community Art Series'),
                ('Café Painting | Community Art Series', 'Cafe Painting | Community Art Series'),
                ('All the Mornings of the World | Instruments of Desire',
                 'All the Mornings of the World + Live Performance | Instruments of Desire'),
                ('Keramat', 'Keramat | Indonesian Film Forum')]:
            for left, right in ((a, b), (b, a)):
                with self.subTest(left=left, right=right):
                    self.assertTrue(are_names_similar(left, right))

    def test_multiple_pipes_leave_changing_lineups_to_existing_matcher(self):
        for a, b in [
                ('SARIKA | Kayla Silverman | Julian Harper', 'Sarika | Sina | Julian Harper'),
                ('Fully Furnished | BUSTER | Tatters & Rags | Heavy Dose',
                 'Fully Furnished | BUSTER | The Meeks | Heavy Dose')]:
            self.assertFalse(_pipe_program_titles_differ(a, b, '', ''))
            self.assertTrue(are_names_similar(a, b))

    def test_presenter_credits_do_not_become_different_programs(self):
        for head in ["Kenneth Gartman's", 'Kenneth Gartman’s', 'Theatre Group Presents',
                     'Theatre Group Productions:', 'Hosted by Kenneth Gartman']:
            a, b = head + ' | Gotta Sing - Beyond The 4th Wall', 'Musical Theatre Pros | Gotta Sing - Beyond the 4th Wall'
            for left, right in ((a, b), (b, a)):
                with self.subTest(head=head):
                    self.assertFalse(_pipe_program_titles_differ(left, right, '', ''))

    def test_equivalent_format_labels_are_not_distinct_title_evidence(self):
        for a, b in [('Lecture', 'Talk'), ('Panel Discussion', 'Curator Roundtable'),
                     ('Exhibition', 'Display'), ('Movie', 'Film Screening'),
                     ('Member Opening', 'Preview Reception')]:
            left, right = a + ' | The Art of Example', b + ' | The Art of Example'
            self.assertFalse(_pipe_program_titles_differ(left, right, '', ''))
        self.assertTrue(are_names_similar(
            'Lecture | Fantasy and Reality: The Art of Johan Tobias Sergel',
            'Talk | Fantasy and Reality: The Art of Johan Tobias Sergel'))

    def test_other_separators_or_missing_identity_are_outside_rule(self):
        for a, b in [('Keramat - Film Forum', 'Darah Nyai - Film Forum'),
                     ('Keramat | Film Forum', 'Darah Nyai | Other Series'),
                     ('Keramat | Series', 'Darah Nyai | Series'),
                     (' | Film Forum', 'Darah Nyai | Film Forum'),
                     ('Keramat | ', 'Darah Nyai | ')]:
            self.assertFalse(_pipe_program_titles_differ(a, b, '', ''))

    def test_duplicate_review_cannot_auto_suppress_different_programs(self):
        from scripts.find_duplicate_events import classify_pairs
        for a, b in CASES:
            pair = (1, 2, a, b, 10, 'Example Venue', 7, 7)
            self.assertFalse(classify_pairs([pair], {(1, 2)}, set())[0])


if __name__ == '__main__':
    unittest.main()
