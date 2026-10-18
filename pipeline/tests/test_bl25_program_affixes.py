"""BL25 (2026-10-18): affixes that say how, when or where a program runs, not which.

The same-capture veto judges whether two listings of one capture, at different
permalinks, may share an event (`merger.same_capture_names_related`). Three
affixes lifted unrelated titles past the ratio or hid related ones:

* a shared leading "Head:" that is not the event's own name — OHNY Weekend
  (w6020) sites "OHNY Weekend: BAT Clay Studio at Brooklyn Army Terminal",
  "… BioBAT at …", "… THWACK at the …" fused onto 272123 (split by hand
  2026-10-17), Nitehawk "Nitehawk: The Others — …" / "Nitehawk: Little Shop of
  Horrors — …" (262806);
* a shared " at <venue>" tail — "icchā at Culture Lab LIC" on "Sunset Jazz at
  Culture Lab LIC" (100519); a title that is only the other's venue
  ("OHNY Weekend: Brooklyn Army Terminal") names the building, not the program;
* a scheduling-status mark — Sachem "Nocturnal Critters - RESCHEDULED TO
  10/29" is the moved session of "Mutt-i-Grees Club: Nocturnal Critters"
  (268247), which the veto would otherwise split off.

A same-URL retitle check (`retitle_names_compatible`) keeps the old relation.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import merger
from test_bl25_same_capture_partition import run_merge

OHNY = 'https://ohny.org/place/'
BAT_CLAY = ('OHNY Weekend: BAT Clay Studio at Brooklyn Army Terminal', OHNY + 'bat-clay-26')
BIOBAT = ('OHNY Weekend: BioBAT at Brooklyn Army Terminal', OHNY + 'biobat-26')
THWACK = ('OHNY Weekend: THWACK at the Brooklyn Army Terminal', OHNY + 'thwack-26')
BAT = ('OHNY Weekend: Brooklyn Army Terminal', OHNY + 'bat-26')
OHNY_SITES = (BAT_CLAY, BIOBAT, THWACK, BAT)


def related(a, b, head=''):
    return merger.same_capture_names_related(a, b, head)


class SharedLeadingHeadTests(unittest.TestCase):

    def test_ohny_sites_are_unrelated_in_every_order(self):
        for a, _ in OHNY_SITES:
            for b, _ in OHNY_SITES:
                if a == b:
                    continue
                for head in (a, b, ''):
                    with self.subTest(a=a, b=b, head=head):
                        self.assertFalse(related(a, b, head))

    def test_other_shared_heads_carry_no_verdict(self):
        for a, b in [
            ('Nitehawk: The Others — Spooky Season at Nitehawk',
             'Nitehawk: Little Shop of Horrors — Spooky Season at Nitehawk'),
            ('Central Library Teen Center: Teen Civic Collective',
             'Central Library Teen Center: Inktober: Digital Art Tech'),
            ('OHNY Weekend: MADE Bush Terminal', 'OHNY Weekend: Industry City'),
        ]:
            with self.subTest(a=a, b=b):
                self.assertFalse(related(a, b, a))
                self.assertFalse(related(b, a, a))

    def test_a_shared_head_that_is_the_event_keeps_series_nights_together(self):
        # "The Invasion: <host> Invades" nights on the event "The Invasion".
        for a, b, head in [
            ('The Invasion: Lola Michele-Kiki Invades', 'The Invasion: Sabel Scities Invades',
             'The Invasion'),
            ('Haus of Joon: Ardeshir + Friends', 'Haus of Joon: Sorä (with Ardeshir)',
             'Haus of Joon'),
        ]:
            with self.subTest(a=a, b=b):
                self.assertTrue(related(a, b, head))
                self.assertTrue(related(b, a, head))

    def test_the_same_program_under_a_shared_head_stays_related(self):
        for a, b in [
            ('OHNY Weekend: One Times Square', 'OHNY Weekend: One Times Square: Guided Tours'),
            ('Mood and Matter: Multidimensional Collage with Ye Qin Zhu', 'Mood and Matter'),
            ('Le Carrousel Extravaganza',
             'Le Carrousel Extravaganza: Repertorio Español/Scaramouches Puppets'),
            ('Tealeaf Presents', 'Tealeaf Presents: Red Girl\'s Blue / Parlor Talk / Field Trip'),
        ]:
            with self.subTest(a=a, b=b):
                self.assertTrue(related(a, b, a))
                self.assertTrue(related(b, a, a))


class SharedVenueTailTests(unittest.TestCase):

    def test_programs_sharing_only_the_venue_tail_are_unrelated(self):
        for a, b in [
            ('icchā at Culture Lab LIC', 'Sunset Jazz at Culture Lab LIC'),
            ('Yoga at Pier 35', 'Zumba at Pier 35'),
            ('WOW Café Theater at LES Arts & Culture Open House',
             'Nuyorican Poets Cafe at LES Arts & Culture Open House'),
            ('10PM Primetime Comedy Show at The Grisly Pear Greenwich Village',
             'That Thursday Night Comedy Show at The Grisly Pear Greenwich Village'),
        ]:
            with self.subTest(a=a, b=b):
                self.assertFalse(related(a, b, a))
                self.assertFalse(related(b, a, a))

    def test_a_bare_venue_title_is_not_the_program_held_there(self):
        self.assertFalse(related('Culinary Demonstration at the Holiday Market', 'Holiday Market',
                                 'Holiday Market'))
        self.assertFalse(related(BAT[0], BIOBAT[0], BAT[0]))

    def test_the_same_program_at_one_venue_stays_related(self):
        for a, b in [
            ('Comedy Night at The Stand', 'Late Comedy Night at The Stand'),
            ('Storytime at Main Library', 'Toddler Storytime at Main Library'),
            ('Halloween Party at Nexo', 'Halloween Party @ Nexo'),
            ('Jazz Night', 'Jazz Night at Smalls'),
            ('Friendly Hours', "Friendly Hours at Long Island Children's Museum"),
        ]:
            with self.subTest(a=a, b=b):
                self.assertTrue(related(a, b, a))
                self.assertTrue(related(b, a, a))


class StatusMarkTests(unittest.TestCase):

    def test_a_rescheduled_session_stays_with_its_program(self):
        for a, b in [
            ('Nocturnal Critters - RESCHEDULED TO 10/29', 'Mutt-i-Grees Club: Nocturnal Critters'),
            ('POSTPONED: Fall Concert', 'Fall Concert'),
            ('Fall Concert (Cancelled)', 'Fall Concert'),
            ('Tai Chi [New Date]', 'Tai Chi'),
        ]:
            with self.subTest(a=a, b=b):
                self.assertTrue(related(a, b, b))
                self.assertTrue(related(b, a, b))

    def test_status_strip_never_empties_a_title(self):
        self.assertEqual(merger._strip_status_marks('Cancelled'), 'Cancelled')
        self.assertEqual(merger._strip_status_marks('Sold Out'), 'Sold Out')
        self.assertEqual(merger._strip_status_marks('Moved by Music'), 'Moved by Music')

    def test_status_strip_does_not_rescue_different_programs(self):
        self.assertFalse(related('Lego Club - RESCHEDULED', 'Teen Volunteers', 'Teen Volunteers'))


class RetitleKeepsTheOldRelationTests(unittest.TestCase):

    def test_same_url_lineup_retitle_is_still_compatible(self):
        # DICE 6aa17e02…: "Ardeshir + Friends" became "Sorä (with Ardeshir)".
        self.assertTrue(merger.retitle_names_compatible(
            'Haus of Joon: Sorä (with Ardeshir)', 'Haus of Joon: Ardeshir + Friends'))


class ProgramAffixMergeTests(unittest.TestCase):

    def test_ohny_sites_create_their_own_events_in_either_order(self):
        for order in ([(1, *BAT_CLAY), (2, *BIOBAT), (3, *THWACK), (4, *BAT)],
                      [(4, *BAT), (3, *THWACK), (2, *BIOBAT), (1, *BAT_CLAY)]):
            with self.subTest(first=order[0][1]):
                links, created = run_merge(order, website=6020)
                self.assertEqual(len(set(links.values())), 4)

    def test_sites_do_not_fuse_onto_the_existing_bat_clay_event(self):
        links, created = run_merge([(1, *BAT_CLAY), (2, *BIOBAT), (3, *THWACK), (4, *BAT)],
                                   events=[(272123, BAT_CLAY[0])], website=6020)
        self.assertEqual(links[1], 272123)
        for ce in (2, 3, 4):
            self.assertNotEqual(links[ce], 272123)
        self.assertEqual(sorted(created.values()), sorted([BIOBAT[0], THWACK[0], BAT[0]]))

    def test_rescheduled_session_is_no_same_capture_conflict(self):
        # The name tiers decide whether the moved session joins; the veto
        # (and split_same_capture_fusions.py's replay of it) must not part them.
        base = 'https://sachem.librarycalendar.com/event/'
        self.assertIsNone(merger._same_capture_conflict(
            'Nocturnal Critters - RESCHEDULED TO 10/29',
            merger.normalize_url_for_identity(base + 'nocturnal-critters-rescheduled-1029-206291'),
            6013, 'Mutt-i-Grees Club: Nocturnal Critters',
            [(1, 'Mutt-i-Grees Club: Nocturnal Critters',
              merger.normalize_url_for_identity(base + 'mutt-i-grees-club-nocturnal-critters-1'))],
            set(), {}))

if __name__ == '__main__':
    unittest.main()
