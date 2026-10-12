"""BL25: two listings of ONE capture, at different permalinks and under
unrelated titles, must not land on one event.

The 2026-10-11 recheck found 75 live events in a week that had absorbed a
second, differently named listing from the same crawl_result (Regal "Sos26: Us"
+ "SOS26: The Addams Family (1991)" at six theaters, Oceanside's three Monday
programs, Hunterdon's laser and garment-printing classes, FUUB's Child's Play
camps). `are_names_similar` accepts all of those pairs, so the second listing's
dates and URL bled onto the first one's event and its own event never existed.

The merge tests drive the whole `merge_crawl_events` path over a fake cursor
(`test_dismissed_pair_home_20261005` pattern) with several crawl_events from one
capture, so the in-pass claims, the exact-name reservation and the tier ladder
all run for real.
"""
import io
import sys
import unittest
from contextlib import ExitStack, redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger

RESULT = 129692
VENUE = 4100
WEBSITE = 4183
REGAL = 'https://www.regmovies.com/movies/'
US = ('Sos26: Us', REGAL + 'sos26-us-ho00022616')
ADDAMS = ('SOS26: The Addams Family (1991)', REGAL + 'sos26-the-addams-family-1991-ho00022621')


def run_merge(listings, events=(), linked=(), website=WEBSITE, listing_urls=()):
    """Merge `listings` = [(ce_id, name, url[, day])] from capture RESULT.

    `events` = [(event_id, name)] exist at VENUE at 5pm on each of the next
    seven days; `linked` = [(ce_id, name, url, event_id)] are listings of the
    same capture merged by an earlier pass. A listing is dated `day` days from
    today (default 0) at 5pm. Returns (links {ce_id: event_id}, created
    {event_id: name}).
    """
    today = date.today()
    days = {item[0]: (item[3] if len(item) > 3 else 0) for item in listings}
    listings = [item[:3] for item in listings]
    names = dict(events)
    next_id = [900001]
    created = {}

    cursor = MagicMock(lastrowid=None)

    def execute(query, params=None):
        rows, one = [], None
        if 'SELECT ce.id, ce.name' in query:
            rows = [(ce_id, name, None, 'Desc.', '🎬', 'Venue', None, VENUE, url,
                     website, None, None, RESULT) for ce_id, name, url in listings]
        elif 'SELECT DISTINCT e.id, e.name, e.location_id' in query:
            rows = [(eid, name, VENUE, None, None, 'Venue', website, 0)
                    for eid, name in events]
        elif 'SELECT event_id, start_date, start_time, end_date' in query:
            rows = [(eid, today + timedelta(days=d), '5pm', None)
                    for eid, _ in events for d in range(7)]
        elif 'SELECT ce.crawl_result_id, ce.id, ce.name, ce.url, es.event_id' in query:
            rows = ([(RESULT, ce_id, name, url, None) for ce_id, name, url in listings]
                    + [(RESULT, ce_id, name, url, eid) for ce_id, name, url, eid in linked])
        elif 'SELECT crawl_result_id, id, name FROM crawl_events' in query:
            rows = ([(RESULT, ce_id, name) for ce_id, name, _ in listings]
                    + [(RESULT, ce_id, name) for ce_id, name, _, _ in linked])
        elif 'SELECT website_id, url FROM website_urls' in query:
            rows = [(website, u) for u in listing_urls]
        elif 'SELECT id, name, emoji, lat, lng FROM locations' in query:
            rows = [(VENUE, 'Venue', '🎬', None, None)]
        elif 'FROM crawl_event_occurrences' in query:
            rows = [(ce_id, today + timedelta(days=days[ce_id]), '5pm', None, None, 0)
                    for ce_id, _, _ in listings]
        elif 'INSERT INTO events (' in query:
            cursor.lastrowid = next_id[0]
            created[next_id[0]] = params[0]
            names[next_id[0]] = params[0]
            next_id[0] += 1
        elif 'SELECT name FROM events WHERE id' in query:
            one = (names.get(params[0], ''),)
        elif 'SELECT location_id FROM events WHERE id' in query:
            one = (VENUE,)
        elif 'SELECT location_name, location_id FROM events WHERE id' in query:
            one = ('Venue', VENUE)
        elif 'SELECT description, emoji, name, short_name, event_type' in query:
            one = ('Existing.', '🎬', names.get(params[0]), None, None)
        cursor.fetchall.return_value = rows
        cursor.fetchone.return_value = one

    cursor.execute.side_effect = execute
    with ExitStack() as stack:
        stack.enter_context(redirect_stdout(io.StringIO()))
        stack.enter_context(patch.object(merger, 'EditLogger', None))
        stack.enter_context(patch.object(merger.reviewed_event_identity, 'load_index', return_value={}))
        stack.enter_context(patch.object(merger.venue_overrides, 'load_rules', return_value=[]))
        stack.enter_context(patch.object(merger, 'get_active_date_window',
                                         return_value=(today, today + timedelta(days=90))))
        database = stack.enter_context(patch.object(merger, 'db'))
        database.build_tag_ancestor_map.return_value = ({}, set())
        database.archive_dead_source_events.return_value = (0, [])
        database.prune_superseded_dates.return_value = (0, [])
        database.archive_sourceless_events.return_value = (0, [])
        for helper in ('_merge_occurrences_into_event', '_merge_grouped_event_urls',
                       'refresh_source_metadata', 'refresh_source_session_details'):
            stack.enter_context(patch.object(merger, helper))
        merger.merge_crawl_events(cursor, MagicMock(), website_ids=[website])
    links = {c.args[1][1]: c.args[1][0] for c in cursor.execute.call_args_list
             if 'INSERT IGNORE INTO event_sources' in c.args[0]}
    return links, created


class SameCaptureMergeTests(unittest.TestCase):

    def test_regal_double_feature_stays_two_events_in_either_order(self):
        # The live shape: E252587 "Sos26: Us", Addams merged first.
        self.assertTrue(merger.are_names_similar(*[n for n, _ in (ADDAMS, US)]))
        for order in ([(1, *ADDAMS), (2, *US)], [(1, *US), (2, *ADDAMS)]):
            links, created = run_merge(order, events=[(252587, US[0])])
            us_ce = next(ce for ce, n, _ in order if n == US[0])
            addams_ce = next(ce for ce, n, _ in order if n == ADDAMS[0])
            self.assertEqual(links[us_ce], 252587)
            self.assertNotEqual(links[addams_ce], 252587)
            self.assertEqual(created, {links[addams_ce]: ADDAMS[0]})

    def test_two_new_listings_create_two_events(self):
        # Hunterdon w5240 227807: nothing exists yet, both classes arrive together.
        url = 'https://hclibrary.libcal.com/event/'
        links, created = run_merge([
            (1, 'Intro to: Direct To Garment Printing - Learn How to Design a Shirt', url + '17676898'),
            (2, 'Intro to xTool Fiber Laser', url + '17650944'),
        ])
        self.assertEqual(len(created), 2)
        self.assertNotEqual(links[1], links[2])

    def test_sibling_linked_by_an_earlier_pass_still_holds_the_event(self):
        # Oceanside w5247 228478: the game night was merged before this pass.
        url = 'https://oceansidelibrary.libcal.com/event/'
        links, created = run_merge(
            [(2, 'Monday Meditation', url + '17145049')],
            events=[(228478, 'Monday: Open Game Time for Adults')],
            linked=[(1, 'Monday: Open Game Time for Adults', url + '15563376', 228478)])
        self.assertNotEqual(links[2], 228478)
        self.assertEqual(list(created.values()), ['Monday Meditation'])

    def test_multi_date_listing_with_a_permalink_per_date_still_groups(self):
        # LibCal mints a fresh id per occurrence: same title, different URLs.
        url = 'https://sachem.librarycalendar.com/event/'
        links, created = run_merge(
            [(1, 'Lego Club', url + 'lego-club-193997'),
             (2, 'Lego Club', url + 'lego-club-193998')],
            events=[(268200, 'Lego Club')])
        self.assertEqual(links, {1: 268200, 2: 268200})
        self.assertEqual(created, {})

    def test_shared_listing_url_is_no_evidence(self):
        # Two titles on the site's own calendar URL: nothing to tell them apart.
        cal = 'https://www.regmovies.com/theatres/regal-ua-court-street'
        links, created = run_merge(
            [(1, ADDAMS[0], cal), (2, US[0], cal)],
            events=[(252587, US[0])], listing_urls=[cal])
        self.assertEqual(links, {1: 252587, 2: 252587})
        self.assertEqual(created, {})

    def assert_guard_inert(self, listings, events):
        """The same links with and without the same-capture veto."""
        with_guard = run_merge(listings, events=events)
        with patch.object(merger, '_same_capture_conflict', return_value=None):
            without_guard = run_merge(listings, events=events)
        self.assertEqual(with_guard, without_guard)
        return with_guard

    def test_series_editions_named_after_the_event_are_not_vetoed(self):
        # NYCC E99521: each night's lineup at its own permalink. The lineups
        # share only the show's name, which is the event's name. (Whether the
        # second lineup groups is decided by the older tiers; this guard adds
        # nothing either way.)
        url = 'https://newyorkcomedyclub.com/events/'
        links, _ = self.assert_guard_inert(
            [(1, 'Matinee with Ry Daddy ft: Olivia Stadler, Gibran Saleem, Dean David',
              url + 'matinee-with-ry-daddy-ft-olivia-stadler-gibran-saleem-dean', 0),
             (2, 'Matinee with Ry Daddy ft: Daniel Simonsen, Olivia Stadler, Jeff Arcuri',
              url + 'matinee-with-ry-daddy-ft-daniel-simonsen-olivia-stadler-je', 1),
             (3, 'Matinee with Ry Daddy', url + 'matinee-with-ry-daddy-2026-10-17170000', 2)],
            events=[(99521, 'Matinee with Ry Daddy')])
        self.assertEqual(links[1], 99521)
        self.assertEqual(links[3], 99521)

    def test_lineup_titled_nights_are_not_vetoed(self):
        # East Ville w955: a night of "Stand Up Shenanigans" titled by its lineup.
        url = 'https://www.eastvillecomedy.com/events/'
        self.assert_guard_inert(
            [(1, 'Ayanna Dookie, Dara Jemmott, Liam Dalton, Paul Valdes-Rodriguez',
              url + 'ayanna-dookie-dara-jemmott-liam-dalton-pa', 0),
             (2, 'Stand Up Shenanigans', url + 'stand-up-shenanigans-17', 1)],
            events=[(55527, 'Stand Up Shenanigans')])

    def test_other_captures_are_untouched(self):
        # Without a sibling from the same capture the old match stands.
        links, created = run_merge([(1, *ADDAMS)], events=[(252587, US[0])])
        self.assertEqual(links, {1: 252587})
        self.assertEqual(created, {})


class SameCaptureNamesRelatedTests(unittest.TestCase):

    def related(self, a, b, head=''):
        return merger.same_capture_names_related(a, b, head)

    def test_distinct_programs_are_unrelated(self):
        for a, b, head in [
            (US[0], ADDAMS[0], US[0]),
            ('Monday Meditation', 'Monday: Open Game Time for Adults', ''),
            ('Lego Club', 'Sachem Teen Volunteers: Lego Club Helpers', ''),
            ('Dominican Open Bar (21+)', 'SUBELO - Dembow • Bachata • Mambo • Tipico (21+)', ''),
            ('West Long Branch Book Club',
             'Families, Books, and Tunes Storytime - West Long Branch', ''),
            # A shared program prefix that is not the event's own name.
            ("Child's Play - Holiday Camp (Veterans Day)",
             "Child's Play: Legally Blonde Jr. — Wednesday Class",
             "Child's Play: Legally Blonde Jr. — Wednesday Class"),
            ('The Nightmare Before Halloween Colombian Parrty at Ritmos 60',
             'Ritmos: Sabado de Parranda - Colombian Salsa, Vallenato Reggaeton Party NYC', ''),
        ]:
            with self.subTest(a=a, b=b):
                self.assertFalse(self.related(a, b, head))

    def test_relation_does_not_depend_on_argument_order(self):
        # difflib scores this pair 0.53 one way and 0.49 the other.
        a, b = 'Potluck Halloween', 'Jacobdior Presents Halloween'
        self.assertFalse(self.related(a, b, b))
        self.assertFalse(self.related(b, a, b))

    def test_one_event_under_two_titles_is_related(self):
        for a, b, head in [
            ('Nice Try', 'Nice Try ft: Michael Kosta, Ian Fidance, Ashley Austin Morris', ''),
            ('Fatherland', 'FATHERLAND – Q&A with Filmmaker Paweł Pawlikowski', ''),
            ('Unzipped', 'Isaac Mizrahi in UNZIPPED', ''),
            ('Everybody Sew!', 'Everybody Sews! With Meagan Woods and Heather Warfel', ''),
            ('Storytime (AM)', 'Storytime (PM)', ''),
            ('Sunday Platform with Jean Rohe',
             'Sunday Platform with Curt Collier: The Undiscovered Country', 'Sunday Platform'),
            # A bare performer list is a night of the named show, not a title.
            ('Ayanna Dookie, Dara Jemmott, Liam Dalton, Paul Valdes-Rodriguez',
             'Stand Up Shenanigans', 'Stand Up Shenanigans'),
        ]:
            with self.subTest(a=a, b=b):
                self.assertTrue(self.related(a, b, head))

    def test_lineup_detection_needs_a_bare_list(self):
        self.assertTrue(merger._lineup_only_title('Shed (Live), 1Morning, Lydo, + Tba'))
        for title in ('Families, Books, and Tunes Storytime - West Long Branch',
                      'Elsewhere Halloween - Major League DJz, SAIDAH, D Stone + more',
                      'Refuge Saturday Daytime with Notre Dame, FALYN B2B Ramyen, Papyon',
                      'Roger Kellaway, John Goldsby & Terry Clarke Autumn Reunion Masterclass'):
            with self.subTest(title=title):
                self.assertFalse(merger._lineup_only_title(title))


class SameCaptureConflictTests(unittest.TestCase):
    US_KEY = merger.normalize_url_for_identity(US[1])
    ADDAMS_KEY = merger.normalize_url_for_identity(ADDAMS[1])

    def conflict(self, url_key, siblings, listing=(), counts=None):
        return merger._same_capture_conflict(
            ADDAMS[0], url_key, WEBSITE, US[0], siblings,
            {(WEBSITE, k) for k in listing}, counts or {})

    def test_distinct_permalinks_and_titles_conflict(self):
        self.assertEqual(self.conflict(self.ADDAMS_KEY, [(1, US[0], self.US_KEY)]), US[0])

    def test_same_or_missing_permalink_is_no_conflict(self):
        self.assertIsNone(self.conflict(self.US_KEY, [(1, US[0], self.US_KEY)]))
        self.assertIsNone(self.conflict(self.ADDAMS_KEY, [(1, US[0], '')]))
        self.assertIsNone(self.conflict('', [(1, US[0], self.US_KEY)]))

    def test_listing_or_crowded_url_is_no_conflict(self):
        self.assertIsNone(self.conflict(self.ADDAMS_KEY, [(1, US[0], self.US_KEY)],
                                        listing=[self.US_KEY]))
        self.assertIsNone(self.conflict(
            self.ADDAMS_KEY, [(1, US[0], self.US_KEY)],
            counts={(WEBSITE, self.US_KEY): merger.URL_IDENTITY_MAX_DISTINCT_NAMES + 1}))


if __name__ == '__main__':
    unittest.main()
