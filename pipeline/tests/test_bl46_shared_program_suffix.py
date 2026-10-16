"""BL46: library classes that share only a format/branch tail are different events.

Half Hollow Hills (w3880) capture cr-131738 listed "CardioFit - Virtual Program
- Zoom", "Arthritis Exercise - Virtual Program - Zoom" (ce 1570502) and
"Wednesday Zumba - Virtual Program - Zoom" (ce 1570507), each at its own
permalink. The shared 23-character " - Virtual Program - Zoom" tail lifted the
normalized ratio past SAME_CAPTURE_MIN_NAME_RATIO, so the same-capture veto
let both classes fuse onto e290122 (split by hand in BL45 as e290268/e290269).
`same_capture_names_related` now sets a shared trailing " - …" run aside and
judges the program names in front of it.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import merger
from test_bl25_same_capture_partition import run_merge

HHH = 'https://hhhlibrary.libcal.com/event/'
CARDIO = ('CardioFit - Virtual Program - Zoom', HHH + '15700001')
ARTHRITIS = ('Arthritis Exercise - Virtual Program - Zoom', HHH + '15700002')
ZUMBA = ('Wednesday Zumba - Virtual Program - Zoom', HHH + '15700003')
CLASSES = (CARDIO, ARTHRITIS, ZUMBA)


def related(a, b, head=''):
    return merger.same_capture_names_related(a, b, head)


class SharedProgramSuffixNameTests(unittest.TestCase):

    def test_the_three_classes_are_unrelated_in_every_order(self):
        for a, _ in CLASSES:
            for b, _ in CLASSES:
                if a == b:
                    continue
                for head in (a, b, ''):
                    with self.subTest(a=a, b=b, head=head):
                        self.assertFalse(related(a, b, head))

    def test_other_shared_tails_carry_no_verdict(self):
        for a, b in [
            ('Lego Club - Dix Hills', 'Teen Volunteers - Dix Hills'),
            ('Chair Yoga - Virtual Program', 'Tai Chi - Virtual Program'),
            ('Chairobics & Strength - Sept/Oct', 'Gentle Yoga - Sept/Oct'),
            ('Adult Kickball - North Jersey', 'Bowling Night - North Jersey'),
        ]:
            with self.subTest(a=a, b=b):
                self.assertFalse(related(a, b, a))
                self.assertFalse(related(b, a, a))

    def test_the_same_class_with_a_shared_tail_stays_related(self):
        for a, b in [
            ('Storytime (AM) - Dix Hills', 'Storytime (PM) - Dix Hills'),
            ('Chair Yoga - Dix Hills', 'Chair Yoga for Seniors - Dix Hills'),
            (CARDIO[0], 'CardioFit - Virtual Program'),
            ('CardioFit - Session 2 - Virtual Program - Zoom', CARDIO[0]),
        ]:
            with self.subTest(a=a, b=b):
                self.assertTrue(related(a, b, a))
                self.assertTrue(related(b, a, a))

    def test_nights_of_a_series_named_by_the_shared_tail_stay_related(self):
        # The tail is the event itself: "<DJ> - Friends In High Places".
        a, b = 'Alex Wann - Friends In High Places', 'Jazzy - Friends In High Places'
        self.assertTrue(related(a, b, 'Friends In High Places'))
        self.assertFalse(related(a, b, a))

    def test_a_stripped_core_is_not_read_as_a_bare_lineup(self):
        # RA "<lineup> - <venue>" nights and comma-titled programs keep their
        # verdict: only a whole title can be a bare performer list.
        for a, b in [
            ("Jean d'Armes, Lord Fascinator, Laura Lynn, Mr. Handyman - Dead Letter No.9",
             'Ultra Violet, La Máquina del Tiempo - Dead Letter No.9'),
            ("Fania's World of Flavors, Smells, and Colors - In-person Program",
             "A Staged Reading of 'The Dybbuk' – In-person Program"),
        ]:
            with self.subTest(a=a, b=b):
                self.assertFalse(related(a, b, a))
                self.assertFalse(related(b, a, a))

    def test_a_dash_inside_brackets_is_not_a_segment_break(self):
        self.assertEqual(
            merger._title_segments('Not a Stick Storycraft (Kindergarten - Grade 5) - Dix Hills'),
            ['Not a Stick Storycraft (Kindergarten - Grade 5)', 'Dix Hills'])
        self.assertEqual(merger._strip_shared_trailing_segments(
            'Bebés of the Island (6 - 36 months)', 'Intro to Dance (18 - 36 Months)')[2], [])


class BL25KeepTogetherGuardTests(unittest.TestCase):
    """The BL25 related-title cases must survive the suffix strip."""

    def test_bl25_one_event_under_two_titles_stays_related(self):
        for a, b, head in [
            ('Fatherland', 'FATHERLAND – Q&A with Filmmaker Paweł Pawlikowski', ''),
            ('Sunday Platform with Jean Rohe',
             'Sunday Platform with Curt Collier: The Undiscovered Country', 'Sunday Platform'),
            ('Sunday Platform with Jean Rohe - Zoom',
             'Sunday Platform with Curt Collier - Zoom', 'Sunday Platform - Zoom'),
            ('Storytime (AM)', 'Storytime (PM)', ''),
            ('Nice Try', 'Nice Try ft: Michael Kosta, Ian Fidance, Ashley Austin Morris', ''),
            ('Matinee with Ry Daddy ft: Olivia Stadler, Gibran Saleem, Dean David',
             'Matinee with Ry Daddy', 'Matinee with Ry Daddy'),
        ]:
            with self.subTest(a=a, b=b):
                self.assertTrue(related(a, b, head))
                self.assertTrue(related(b, a, head))

    def test_bl25_distinct_programs_stay_unrelated(self):
        self.assertFalse(related('West Long Branch Book Club',
                                 'Families, Books, and Tunes Storytime - West Long Branch'))
        self.assertFalse(related("Child's Play - Holiday Camp (Veterans Day)",
                                 "Child's Play: Legally Blonde Jr. — Wednesday Class",
                                 "Child's Play: Legally Blonde Jr. — Wednesday Class"))


class SharedProgramSuffixMergeTests(unittest.TestCase):

    def test_three_new_classes_create_three_events_in_either_order(self):
        for order in ([(1, *CARDIO), (2, *ARTHRITIS), (3, *ZUMBA)],
                      [(3, *ZUMBA), (2, *ARTHRITIS), (1, *CARDIO)]):
            with self.subTest(first=order[0][1]):
                links, created = run_merge(order, website=3880)
                self.assertEqual(len(set(links.values())), 3)
                self.assertEqual(sorted(created.values()),
                                 sorted(name for name, _ in CLASSES))

    def test_classes_do_not_fuse_onto_the_existing_cardiofit_event(self):
        links, created = run_merge([(1, *CARDIO), (1570502, *ARTHRITIS, 1),
                                    (1570507, *ZUMBA, 2)],
                                   events=[(290122, CARDIO[0])], website=3880)
        self.assertEqual(links[1], 290122)
        self.assertNotEqual(links[1570502], 290122)
        self.assertNotEqual(links[1570507], 290122)
        self.assertEqual(sorted(created.values()), sorted([ARTHRITIS[0], ZUMBA[0]]))

    def test_multi_date_listing_with_a_permalink_per_date_still_groups(self):
        links, created = run_merge([(1, CARDIO[0], HHH + '1', 0),
                                    (2, CARDIO[0], HHH + '2', 1),
                                    (3, CARDIO[0], HHH + '3', 2)],
                                   events=[(290122, CARDIO[0])], website=3880)
        self.assertEqual(set(links.values()), {290122})
        self.assertEqual(created, {})


if __name__ == '__main__':
    unittest.main()
