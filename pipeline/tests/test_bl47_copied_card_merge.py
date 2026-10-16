"""BL47 (merger side): a "Copy of <title>" card on another date is another event.

Gladys Books & Wine (w994) duplicated its Oct 30 podcast card for an Oct 31
Halloween party and kept the title "Copy of I DO the Bending Live Podcast
Recording!". The extractor now emits the copy as its own listing (COPIED CARDS
rule, `test_bl47_copy_cards.py`), but `are_names_similar` still pairs the two
titles, so the copy could land on the podcast event e284959 and give it the
party's Oct 31 date. `copied_card_differs`, consulted by every name-similarity
tier through `_program_veto`, refuses that pairing when the start dates differ.
"""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import merger
from test_bl25_same_capture_partition import run_merge

ORIGINAL = 'I DO the Bending Live Podcast Recording!'
COPY = 'Copy of I DO the Bending Live Podcast Recording!'
GLADYS = 'https://gladysbooksandwine.com/pages/events'
PODCAST_DATES = {'2026-10-30'}
PARTY_DATES = {'2026-10-31'}


class CopiedCardDiffersTests(unittest.TestCase):

    def test_the_names_alone_still_look_alike(self):
        # The guard is date-gated, so name similarity is unchanged.
        self.assertTrue(merger.are_names_similar(ORIGINAL, COPY))
        self.assertTrue(merger.are_names_similar(COPY, ORIGINAL))

    def test_a_copy_on_another_date_differs_in_either_order(self):
        self.assertTrue(merger.copied_card_differs(COPY, ORIGINAL, PARTY_DATES, PODCAST_DATES))
        self.assertTrue(merger.copied_card_differs(ORIGINAL, COPY, PODCAST_DATES, PARTY_DATES))
        self.assertTrue(merger.copied_card_differs(
            'copy of  Trivia Night', 'Trivia Night',
            [date(2026, 11, 2)], [date(2026, 11, 9)]))

    def test_two_copies_still_match(self):
        other_copy = 'COPY OF I DO the Bending Live Podcast Recording!'
        self.assertTrue(merger.are_names_similar(COPY, other_copy))
        self.assertFalse(merger.copied_card_differs(COPY, other_copy, PARTY_DATES, PODCAST_DATES))

    def test_a_copy_on_the_original_date_carries_no_verdict(self):
        self.assertFalse(merger.copied_card_differs(
            COPY, ORIGINAL, PARTY_DATES | PODCAST_DATES, PODCAST_DATES))

    def test_missing_dates_carry_no_verdict(self):
        self.assertFalse(merger.copied_card_differs(COPY, ORIGINAL, PARTY_DATES, ()))
        self.assertFalse(merger.copied_card_differs(COPY, ORIGINAL, (), PODCAST_DATES))

    def test_copy_must_open_the_title(self):
        for name in ('Hard Copy of Love', 'Copy of', 'A Copy of the Book Club'):
            with self.subTest(name=name):
                self.assertFalse(merger.copied_card_differs(
                    name, ORIGINAL, PARTY_DATES, PODCAST_DATES))


class CopiedCardMergeTests(unittest.TestCase):
    """`run_merge` dates the existing event on each of the next seven days."""

    def test_merge_consults_the_guard_with_both_date_sets(self):
        calls = []
        real = merger.copied_card_differs

        def spy(*args):
            calls.append(args)
            return real(*args)

        with patch.object(merger, 'copied_card_differs', side_effect=spy):
            links, _ = run_merge([(1570813, COPY, GLADYS, 1)],
                                 events=[(284959, ORIGINAL)], website=994)
        self.assertEqual(links[1570813], 284959)  # same date: no verdict
        today = date.today()
        self.assertIn((COPY, ORIGINAL, {str(today + timedelta(days=1))},
                       {str(today + timedelta(days=d)) for d in range(7)}), calls)

    def test_a_vetoed_copy_gets_its_own_event(self):
        with patch.object(merger, 'copied_card_differs', return_value=True):
            links, created = run_merge([(1570813, COPY, GLADYS, 1)],
                                       events=[(284959, ORIGINAL)], website=994)
        self.assertNotEqual(links[1570813], 284959)
        self.assertEqual(list(created.values()), [COPY])

    def test_without_the_guard_the_copy_was_absorbed(self):
        with patch.object(merger, 'copied_card_differs', return_value=False):
            links, created = run_merge([(1570813, COPY, GLADYS, 1)],
                                       events=[(284959, ORIGINAL)], website=994)
        self.assertEqual(links[1570813], 284959)
        self.assertEqual(created, {})


if __name__ == '__main__':
    unittest.main()
