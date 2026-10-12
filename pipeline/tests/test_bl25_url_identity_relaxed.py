"""BL25 items 1 and 2: the URL tier for a listing that lost its venue or time,
or was retitled.

1. NYC-DSA w591's 10-09 crawl lost venue and time for 42 canvass rows. They
   landed on the organizer fallback (NYC-DSA Office, l1940) untimed, missed
   their twins at the greenmarkets (strict URL tier: shared date+time slot and
   venues within 2 km) and forked ("1 Candidate Canvass (2026-10-31)" 284891 vs
   273944 at Sunnyside Greenmarket).
2. A retitled listing keeps its URL and slot ("1 Candidate Canvass" -> "2
   Candidate Canvasses", "Bklyn Boo!" -> "BK Boo!") but no name tier accepts the
   new title. Titles the page still prints, generic series heads and
   sub-programs (class shows, receptions) must not be swallowed.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger

WEBSITE = 591
OFFICE = 1940
GREENMARKET = 802
COORDS = {OFFICE: (40.7506, -73.9935), GREENMARKET: (40.7466, -73.9196)}  # ~6 km apart
CANVASS = 'https://canvass.socialists.nyc/?date=%5B%222026-10-31..2026-10-31%22%5D'


def index(url, *events):
    key = (WEBSITE, merger.normalize_url_for_identity(url))
    names = {merger.normalize_name_for_dedup(e['name']) for e in events}
    return {key: list(events)}, {key: len(names)}


def event(event_id, name, location_id, slots, suppressed=False):
    return {'id': event_id, 'name': name, 'location_id': location_id,
            'slots': set(slots), 'suppressed': suppressed}


def relaxed(name, url, location_id, slots, events, *, fallback=False, capture=()):
    by_url, counts = index(url, *events)
    return merger._match_by_url_identity_relaxed(
        name, url, WEBSITE, location_id, set(slots), by_url, counts, set(), COORDS,
        incoming_is_fallback=fallback,
        capture_names={merger.normalize_name_for_dedup(n) for n in capture})


class OrganizerFallbackTests(unittest.TestCase):

    def test_fallback_detection(self):
        linked = {OFFICE}
        for label in (None, '', 'NYC-DSA', 'Online', 'TBA'):
            with self.subTest(label=label):
                self.assertTrue(merger.is_organizer_fallback_location(OFFICE, label, linked, 'NYC DSA'))
        # A venue string that names a place, or a location the site does not link.
        self.assertFalse(merger.is_organizer_fallback_location(OFFICE, 'NYC-DSA Office', linked, 'NYC DSA'))
        self.assertFalse(merger.is_organizer_fallback_location(GREENMARKET, '', linked, 'NYC DSA'))
        self.assertFalse(merger.is_organizer_fallback_location(None, '', linked, 'NYC DSA'))

    def test_untimed_fallback_twin_matches_the_real_venue(self):
        name = '1 Candidate Canvass (2026-10-31)'
        twin = event(273944, name, GREENMARKET, [('2026-10-31', '11am')])
        self.assertEqual(relaxed(name, CANVASS, OFFICE, [('2026-10-31', '')], [twin],
                                 fallback=True), 273944)
        # The strict tier misses it (no shared slot, venues 6 km apart).
        by_url, counts = index(CANVASS, twin)
        self.assertIsNone(merger._match_by_url_identity(
            name, CANVASS, WEBSITE, OFFICE, {('2026-10-31', '')}, by_url, counts, set(), COORDS))

    def test_without_the_fallback_a_distant_venue_still_refuses(self):
        name = '1 Candidate Canvass (2026-10-31)'
        twin = event(273944, name, GREENMARKET, [('2026-10-31', '11am')])
        self.assertIsNone(relaxed(name, CANVASS, OFFICE, [('2026-10-31', '')], [twin]))

    def test_untimed_date_needs_the_same_date(self):
        name = '1 Candidate Canvass (2026-10-31)'
        twin = event(273944, name, GREENMARKET, [('2026-11-01', '11am')])
        self.assertIsNone(relaxed(name, CANVASS, OFFICE, [('2026-10-31', '')], [twin],
                                  fallback=True))

    def test_two_qualifying_events_are_ambiguous(self):
        name = '1 Candidate Canvass (2026-10-31)'
        a = event(1, name, GREENMARKET, [('2026-10-31', '11am')])
        b = event(2, name, GREENMARKET, [('2026-10-31', '2pm')])
        self.assertIsNone(relaxed(name, CANVASS, OFFICE, [('2026-10-31', '')], [a, b],
                                  fallback=True))

    def test_suppressed_events_are_not_targets(self):
        name = '1 Candidate Canvass (2026-10-31)'
        twin = event(273944, name, GREENMARKET, [('2026-10-31', '11am')], suppressed=True)
        self.assertIsNone(relaxed(name, CANVASS, OFFICE, [('2026-10-31', '')], [twin],
                                  fallback=True))


class RetitleTests(unittest.TestCase):
    URL = 'https://canvass.socialists.nyc/?date=%5B%222026-10-18..2026-10-18%22%5D'

    def test_retitled_listing_with_same_url_and_slot_matches(self):
        old = event(268901, '1 Candidate Canvass (2026-10-18)', OFFICE, [('2026-10-18', '12pm')])
        self.assertEqual(relaxed('2 Candidate Canvasses (2026-10-18)', self.URL, OFFICE,
                                 [('2026-10-18', '12pm')], [old]), 268901)

    def test_retitle_needs_the_exact_slot(self):
        old = event(268901, '1 Candidate Canvass (2026-10-18)', OFFICE, [('2026-10-18', '12pm')])
        self.assertIsNone(relaxed('2 Candidate Canvasses (2026-10-18)', self.URL, OFFICE,
                                  [('2026-10-18', '')], [old]))

    def test_old_title_still_in_the_capture_is_not_a_rename(self):
        old = event(268901, '1 Candidate Canvass (2026-10-18)', OFFICE, [('2026-10-18', '12pm')])
        self.assertIsNone(relaxed('2 Candidate Canvasses (2026-10-18)', self.URL, OFFICE,
                                  [('2026-10-18', '12pm')], [old],
                                  capture=['1 Candidate Canvass (2026-10-18)']))

    def test_url_carrying_two_names_is_no_rename_evidence(self):
        # Carnegie's presenter page after a second concert bled onto it.
        url = 'https://www.carnegiehall.org/calendar/2026/12/21/oratorio-society-of-new-york-0700pm'
        a = event(259702, 'Oratorio Society of New York: Fauré, Beethoven, Brahms & Barnes',
                  177, [('2026-12-21', '7pm')])
        b = event(283187, 'Oratorio Society of New York: Handel Messiah', 177,
                  [('2026-12-21', '7pm')])
        self.assertIsNone(relaxed('Oratorio Society of New York', url, 177,
                                  [('2026-12-21', '7pm')], [a, b]))

    def test_retitle_name_shapes(self):
        for new, old in [
            ('BK Boo!', 'Bklyn Boo!'),
            ('John Coons and Jonah Wheeler - Double InDUMBnity', 'John Coons and Jonah Wheeler'),
            ('Life After Trance: Ddr Edition', 'Life After Trance VS Ddr'),
            ('The Atrium: Jump Source [Live], Hank Jackson, Mariposa',
             'The Atrium: Jump Source [Live], Special Guests'),
        ]:
            with self.subTest(new=new):
                self.assertTrue(merger.retitle_names_compatible(new, old))
        for new, old in [
            ('Monday Night Movie: "Backrooms"', 'Monday Night Movie: "Bram Stoker\'s Dracula"'),
            ('Social Seniors: DeJesus Sings', 'Social Seniors: Medicare Planning Seminar'),
            ('Clown: Body, Mask & Gag Class Show',
             "Clown: Body, Mask & Gag w/ Anya Opshinsky (Oct-Dec '26) (Wednesday)"),
            ('Artist Reception: Jeanne Menoutis — Gods Among Us',
             'Gods Among Us: Jeanne Menoutis Solo Exhibition'),
            ('Sachem Teen Volunteers: Craft Buddies', 'Craft Buddies'),
            ('Physical Storytelling 201 Class Show', 'Class Show: Taylor Gonzalez Improv Level 1'),
        ]:
            with self.subTest(new=new):
                self.assertFalse(merger.retitle_names_compatible(new, old))


if __name__ == '__main__':
    unittest.main()
