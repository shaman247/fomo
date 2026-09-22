"""Keep explicit derivative gatherings and quoted class subjects distinct."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from merger import are_names_similar, is_false_positive


class DerivativeEventNamesTest(unittest.TestCase):
    def test_parent_event_is_not_its_meetup(self):
        cases = [
            ('Chance the Rapper Coloring Book 10th Anniversary Tour Meetup',
             'Chance the Rapper: Coloring Book 10 Year Anniversary Tour / La Reezy'),
            ('AniTOMO Convention Meetup [Brooklyn]', 'AniTOMO Convention 2026'),
            ('Example Concert', 'Example Concert Meet-Up'),
            ('Example Festival', 'Example Festival meet up'),
            ('Example Tour', 'Example Tour Meetups'),
        ]
        for a, b in cases:
            for left, right in ((a, b), (b, a)):
                with self.subTest(left=left, right=right):
                    self.assertTrue(is_false_positive(left, right))
                    self.assertFalse(are_names_similar(left, right))

    def test_ordinary_meetup_and_fuller_event_names_still_match(self):
        cases = [
            ('Crux Queer Femme', 'Crux Queer Femme Meetup'),
            ('Asian Climbing Tribe', 'Asian Climbing Tribe Meetup'),
            ('Example Concert Meetup', 'Meetup for Example Concert'),
            ('Chance the Rapper', 'Chance the Rapper: Coloring Book 10 Year Anniversary Tour'),
            ('Edan', 'Edan - FREE Serengeti Afterparty'),
            ('Speed Friending', 'Speed Friending (+ After Party)'),
            ('World Cup Screenings at The Battery', 'World Cup Watch Parties | Big Screen at The Battery'),
        ]
        for a, b in cases:
            for left, right in ((a, b), (b, a)):
                with self.subTest(left=left, right=right):
                    self.assertTrue(are_names_similar(left, right))

    def test_two_explicit_meetup_spellings_are_not_vetoed(self):
        # Existing fuzzy matching need not join every spelling; this guard must
        # not classify two explicitly marked meetups as a parent/derivative pair.
        self.assertFalse(is_false_positive(
            'AniTOMO Convention Meetup', 'AniTOMO Convention Meet-Up'))
        self.assertFalse(is_false_positive(
            'AniTOMO Convention Meet-Up', 'AniTOMO Convention Meetup'))

    def test_shared_class_metadata_does_not_merge_different_subjects(self):
        cases = [
            ('"Starry Night Over the Eiffel Tower" (2hr:Harlem:Lenox)',
             '"Starry Night over Empire State Building" (2hr:Harlem:Lenox)'),
            ('“Starry Night Over the Eiffel Tower” (2hr:Harlem:Lenox)',
             '“Starry Night over Empire State Building” (2hr:Harlem:Lenox)'),
            ('"Spring Garden" (2hr:Studio)', '"Winter Garden" (2hr:Studio)'),
        ]
        for a, b in cases:
            for left, right in ((a, b), (b, a)):
                with self.subTest(left=left, right=right):
                    self.assertTrue(is_false_positive(left, right))
                    self.assertFalse(are_names_similar(left, right))

    def test_quoted_title_abbreviations_still_match(self):
        cases = [
            ('"Starry Night Over Manhattan" (2hr:Harlem:Lenox)',
             '"Starry Night Manhattan" (2hr:Harlem:Lenox)'),
            ('"Spring Gardens" (2hr:Studio)', '"Spring Garden" (2hr:Studio)'),
            ('“Café Painting” (2hr:Studio)', '"Cafe Painting" (2hr:Studio)'),
            ('"Starry Night Over Manhattan" (2hr:Harlem:Lenox)',
             'Starry Night Over Manhattan'),
        ]
        for a, b in cases:
            for left, right in ((a, b), (b, a)):
                with self.subTest(left=left, right=right):
                    self.assertTrue(are_names_similar(left, right))


if __name__ == '__main__':
    unittest.main()
