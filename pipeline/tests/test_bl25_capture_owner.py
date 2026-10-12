"""BL25 repair follow-up: which listing of a capture owns an event whose title
neither listing carries exactly.

Talon Bar 110256 is titled "Slander Factory at Talon Bar! Free Stand-Up Comedy
Every Thurs. in Bushwick"; the site now says "… in Brooklyn", and one capture
also lists "Slander Factory Comedy" at another Eventbrite page. The reservation
only knew the exact title, so the first listing by id ("Slander Factory
Comedy") owned the event and the re-worded copy of the event's own title was
split into a duplicate (289415, merged back 2026-10-12).
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import merger
from test_bl25_same_capture_partition import run_merge

EB = 'https://www.eventbrite.com/e/'
BUSHWICK = 'Slander Factory at Talon Bar! Free Stand-Up Comedy Every Thurs. in Bushwick'
BROOKLYN = ('Slander Factory at Talon Bar! Free Stand-Up Comedy Every Thurs. in Brooklyn',
            EB + 'slander-factory-at-talon-bar-free-stand-up-comedy-every-thurs-in-brooklyn-tickets-1986320575311')
COMEDY = ('Slander Factory Comedy', EB + 'slander-factory-comedy-tickets-1462083513289')


class CaptureOwnerTests(unittest.TestCase):

    def test_reworded_copy_of_the_title_owns_the_event_in_either_order(self):
        for order in ([(1, *COMEDY), (2, *BROOKLYN)], [(2, *BROOKLYN), (1, *COMEDY)]):
            links, created = run_merge(order, events=[(110256, BUSHWICK)], website=3199)
            self.assertEqual(links[2], 110256)
            self.assertNotEqual(links[1], 110256)
            self.assertEqual(list(created.values()), [COMEDY[0]])

    def test_variant_needs_a_near_identical_title(self):
        listings = [(2, *BROOKLYN)]
        rows = [(i, n, merger.normalize_name_for_dedup(n), merger.normalize_url_for_identity(u))
                for i, n, u in listings]
        self.assertEqual(len(merger.same_capture_reserving(COMEDY[0], BUSHWICK, rows)), 1)
        # A sibling that is merely related (ratio >= 0.5) does not take over.
        loose = [(3, 'Le Freak Halloween at The Tippler NYC', 'le freak halloween at the tippler nyc',
                  'mtsproductions.com/event/le-freak')]
        self.assertEqual(merger.same_capture_reserving(
            'Standard Biergarten NYC Halloween Party | Oct 30',
            'Halloween at The Standard Biergarten', loose), [])

    def test_incoming_related_to_the_title_keeps_it(self):
        rows = [(2, BROOKLYN[0], merger.normalize_name_for_dedup(BROOKLYN[0]), 'b')]
        self.assertEqual(merger.same_capture_reserving(
            'Slander Factory at Talon Bar! Free Stand-Up Comedy', BUSHWICK, rows), [])

    def test_a_variant_with_its_own_event_does_not_reserve(self):
        rows = [(2, BROOKLYN[0], merger.normalize_name_for_dedup(BROOKLYN[0]), 'b')]
        own = {merger.normalize_name_for_dedup(BROOKLYN[0])}
        self.assertEqual(merger.same_capture_reserving(COMEDY[0], BUSHWICK, rows, own), [])

    def test_exact_title_still_reserves(self):
        rows = [(2, BUSHWICK, merger.normalize_name_for_dedup(BUSHWICK), 'b')]
        self.assertEqual(len(merger.same_capture_reserving(COMEDY[0], BUSHWICK, rows)), 1)


if __name__ == '__main__':
    unittest.main()
