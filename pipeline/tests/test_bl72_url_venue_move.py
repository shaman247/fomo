"""BL72 (a): a publisher's record id moves its event between the publisher's own venues.

Middle Country PL w6058 is linked to Centereach (12082) and Selden (12083),
about 4 km apart. Programs past the per-building RSS window are pinned to
Centereach, and when they enter the window the RSS names Selden with the same
BookIt `event?id=`. The URL tiers stop at URL_IDENTITY_MAX_KM, so each move
created a Selden twin and archived the original as "upcoming" (2026-10-23 and
2026-11-02: 14 pairs). `_match_url_venue_move` waives the distance bound, and
nothing else, for that shape; the merge then re-pins via should_repin_location
and logs URL-VENUE-MOVE.

Pure tests on the matcher plus two whole-merge tests over a fake cursor
(`test_suppressed_url_twin` pattern). No database.
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
from location_containment import LocationContainment

MCPL = 6058
CENTEREACH, SELDEN, PICKLR = 12082, 12083, 99001
NAMES = {CENTEREACH: 'Middle Country Public Library Centereach',
         SELDEN: 'Middle Country Public Library Selden', PICKLR: 'The Picklr'}
COORDS = {CENTEREACH: (40.864762, -73.080003), SELDEN: (40.867521, -73.032663),
          PICKLR: (40.8655, -73.0790)}
URL = 'https://mcplibrary.events.mylibrary.digital/event?id=370337'
KEY = merger.normalize_url_for_identity(URL)
NAME = 'SNAP Enrollment'
DATES = {'2026-11-18', '2026-12-09'}
LISTING = 'https://bookit.mcplibrary.org/iii/viewCalendar.php'


def holder(event_id=294274, location_id=CENTEREACH, name=NAME, suppressed=False,
           slots=frozenset({('2026-11-18', '11am'), ('2026-12-09', '11am')})):
    return {'id': event_id, 'name': name, 'location_id': location_id,
            'slots': set(slots), 'suppressed': suppressed}


def no_containment():
    containment = MagicMock(spec=LocationContainment)
    containment.contains.return_value = False
    return containment


def move(url=URL, website=MCPL, location=SELDEN, holders=None, name=NAME, dates=DATES,
         linked=(CENTEREACH, SELDEN), listing=(), capture=None, event_keys=None,
         dismissed=None, fallback=False, archived=(), sourced_at=()):
    index_key = (MCPL, merger.normalize_url_for_identity(url))
    holders = [holder()] if holders is None else holders
    existing = {index_key: holders}
    names = {index_key: len({merger.normalize_name_for_dedup(h['name']) for h in holders})}
    return merger._match_url_venue_move(
        name, url, website, location, set(dates), existing, names,
        {(MCPL, merger.normalize_url_for_identity(u)) for u in listing},
        COORDS, set(linked), no_containment(),
        capture_key_venues=capture if capture is not None else {KEY: {location}},
        event_url_keys=event_keys or {}, dismissed_neighbors=dismissed or {},
        incoming_is_fallback=fallback,
        is_archived=lambda eid: eid in archived,
        has_source_at=lambda eid, w, loc: (eid, loc) in sourced_at)


class RecordIdTests(unittest.TestCase):

    def test_publisher_record_ids(self):
        for key in (KEY, 'jclibrary.libcal.com/event/17531322', 'bklynlibrary.org/node/843069',
                    'smallslive.com/events/34018-frank-lacy-quartet',
                    'farmingdale.librarycalendar.com/event/soccer-shots-25560',
                    'yonkersny.gov/calendar.aspx?caltype=0&day=3&eid=1228&month=9&year=2026',
                    'anthologyfilmarchives.org/film_screenings/calendar?month=11#showing-58210'):
            with self.subTest(key=key):
                self.assertTrue(merger.url_key_has_record_id(key))

    def test_slugs_years_and_date_stamps_are_not_ids(self):
        for key in ('nypl.org/events/programs/2026/12/01/south-bronx-history-keepers',
                    'nycgovparks.org/events/2026/09/03/kids-in-motion-metcalf-playground',
                    'zencare.org/events/beginners-mind-sesshin-2027',
                    'dorotusa.org/event/navigating-retirement-decisions-20260908',
                    'grislypearstandup.com/events/8pm-comedy-show-2026-11-01200000',
                    'pratt.edu/events/building-with-writing-stan-allen'):
            with self.subTest(key=key):
                self.assertFalse(merger.url_key_has_record_id(key))


class VenueMoveMatchTests(unittest.TestCase):

    def test_mcpl_program_moving_to_selden_matches_the_centereach_row(self):
        self.assertEqual(move(), (294274, CENTEREACH))

    def test_whole_event_moves_with_every_record_it_holds(self):
        # Yoga Time 294290 holds two session ids; both now list at Selden.
        other = merger.normalize_url_for_identity(URL.replace('370337', '370101'))
        self.assertEqual(move(capture={KEY: {SELDEN}, other: {SELDEN}},
                              event_keys={294274: {KEY, other}}), (294274, CENTEREACH))

    def test_retitled_listing_still_moves(self):
        self.assertEqual(move(name='SNAP Enrollment Assistance',
                              holders=[holder(name='SNAP Enrollment')]), (294274, CENTEREACH))

    def test_visible_row_beats_a_suppressed_one_at_the_same_old_venue(self):
        self.assertEqual(move(holders=[holder(294274, suppressed=True), holder(294280)]),
                         (294280, CENTEREACH))

    # ── None of these get the waiver ──
    def test_same_url_key_from_another_website(self):
        self.assertIsNone(move(website=5242))

    def test_incoming_venue_the_website_is_not_linked_to(self):
        self.assertIsNone(move(location=PICKLR))

    def test_old_venue_the_website_is_not_linked_to(self):
        # The row sits at a venue another publisher named (The Picklr, 4 km
        # from Selden), not at one of MCPL's own buildings.
        self.assertIsNone(move(holders=[holder(location_id=PICKLR)]))

    def test_listing_url(self):
        self.assertIsNone(move(url=LISTING, holders=[holder()], listing=[LISTING],
                               capture={merger.normalize_url_for_identity(LISTING): {SELDEN}}))

    def test_dismissed_pair(self):
        # A human ruled the Centereach row and the Selden row holding this URL distinct.
        self.assertIsNone(move(holders=[holder(294274), holder(300608, location_id=SELDEN)],
                               dismissed={294274: {300608}, 300608: {294274}}))
        # An unrelated dismissal (another program at the branch) does not block.
        self.assertEqual(move(dismissed={294274: {293545}}), (294274, CENTEREACH))

    def test_slug_url_without_a_record_id(self):
        url = 'https://www.nycgovparks.org/events/2026/11/18/snap-enrollment'
        self.assertIsNone(move(url=url, capture={merger.normalize_url_for_identity(url): {SELDEN}}))

    def test_nearby_venues_belong_to_the_ordinary_url_tiers(self):
        self.assertIsNone(move(location=PICKLR, linked=(CENTEREACH, PICKLR),
                               holders=[holder()], capture={KEY: {PICKLR}}))

    def test_one_url_listed_at_two_branches_is_a_shared_program_page(self):
        # Queens Library 002424-0826: one capture lists the URL at several branches.
        self.assertIsNone(move(capture={KEY: {SELDEN, CENTEREACH}}))
        # ...or events at two venues already hold it.
        self.assertIsNone(move(holders=[holder(294274), holder(300608, location_id=SELDEN)]))

    def test_event_with_another_session_still_at_the_old_venue_stays(self):
        # Nighttime Animals 294278: id=380553 moved to Selden, id=380554 is still Centereach.
        other = merger.normalize_url_for_identity(URL.replace('370337', '380554'))
        self.assertIsNone(move(capture={KEY: {SELDEN}, other: {CENTEREACH}},
                               event_keys={294274: {KEY, other}}))
        self.assertIsNone(move(capture={KEY: {SELDEN}}, event_keys={294274: {KEY, other}}))

    def test_organizer_fallback_venue_is_not_a_move(self):
        self.assertIsNone(move(fallback=True))

    def test_no_shared_date(self):
        self.assertIsNone(move(dates={'2027-01-13'}))

    def test_archived_row_is_not_resurrected(self):
        self.assertIsNone(move(archived={294274}))

    def test_second_move_back_is_refused(self):
        # The row already took a source at the incoming venue: two feeds disagree.
        self.assertIsNone(move(sourced_at={(294274, SELDEN)}))

    def test_different_program_on_the_url_is_refused(self):
        self.assertIsNone(move(name='Veterans Resources Fair'))


def run_merge(*, event_website=MCPL, ce_venue=SELDEN, ce_label=NAMES[SELDEN]):
    """One Selden listing of SNAP Enrollment against Centereach row 294274."""
    today = date.today()
    day = today + timedelta(days=16)
    ce = 1634438
    cursor = MagicMock(lastrowid=900001)

    def execute(query, params=None):
        rows, one = [], None
        if 'SELECT ce.id, ce.name' in query:
            rows = [(ce, NAME, None, 'Help.', '🍎', ce_label, None, ce_venue, URL, MCPL,
                     None, None, 134979)]
        elif 'SELECT DISTINCT e.id, e.name, e.location_id' in query:
            rows = [(294274, NAME, CENTEREACH, *COORDS[CENTEREACH], NAMES[CENTEREACH],
                     event_website, 0)]
        elif 'SELECT event_id, start_date, start_time, end_date' in query:
            rows = [(294274, day, '11am', None)]
        elif 'SELECT eu.event_id, eu.url, e.name' in query:
            rows = [(294274, URL, NAME, event_website, CENTEREACH, 0)]
        elif 'SELECT crawl_result_id, id, name FROM crawl_events' in query:
            rows = [(134979, ce, NAME)]
        elif 'SELECT ce.crawl_result_id, ce.id, ce.name, ce.url, es.event_id' in query:
            rows = [(134979, ce, NAME, URL, None)]
        elif 'SELECT website_id, location_id FROM website_locations' in query:
            rows = [(MCPL, CENTEREACH), (MCPL, SELDEN)]
        elif 'SELECT website_id, url FROM website_urls' in query:
            rows = [(MCPL, LISTING)]
        elif 'SELECT id, name FROM websites' in query:
            rows = [(MCPL, 'Middle Country Public Library')]
        elif 'SELECT id, name, emoji, lat, lng FROM locations' in query:
            rows = [(lid, NAMES[lid], '📚', *COORDS[lid]) for lid in (CENTEREACH, SELDEN)]
        elif 'FROM crawl_event_occurrences' in query:
            rows = [(ce, day, '11am', None, None, 0)]
        elif 'SELECT archived FROM events' in query:
            one = (0,)
        elif 'SELECT 1 FROM event_sources es' in query:
            one = None
        elif 'SELECT location_id FROM events WHERE id' in query:
            one = (CENTEREACH,)
        elif 'SELECT location_name, location_id FROM events WHERE id' in query:
            # Read after the re-pin: the stored label is still Centereach's.
            one = (NAMES[CENTEREACH], SELDEN)
        elif 'SELECT name FROM events WHERE id' in query:
            one = (NAME,)
        elif 'SELECT description, emoji, name, short_name, event_type' in query:
            one = ('Help.', '🍎', NAME, None, None)
        cursor.fetchall.return_value = rows
        cursor.fetchone.return_value = one

    cursor.execute.side_effect = execute
    out = io.StringIO()
    with ExitStack() as stack:
        stack.enter_context(redirect_stdout(out))
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
        merger.merge_crawl_events(cursor, MagicMock(), website_ids=[MCPL])
    calls = cursor.execute.call_args_list
    return dict(
        links=[c.args[1] for c in calls if 'INSERT IGNORE INTO event_sources' in c.args[0]],
        repins=[c.args[1] for c in calls if c.args[0].startswith('UPDATE events SET location_id')],
        labels=[c.args[1] for c in calls if c.args[0].startswith('UPDATE events SET location_name')],
        created=any('INSERT INTO events (' in c.args[0] for c in calls),
        log=out.getvalue())


class VenueMoveMergeTests(unittest.TestCase):

    def test_selden_listing_moves_the_centereach_row(self):
        result = run_merge()
        self.assertFalse(result['created'])
        self.assertEqual(result['links'], [(294274, 1634438)])
        self.assertEqual(result['repins'], [(SELDEN, 294274)])
        self.assertEqual(result['labels'], [(NAMES[SELDEN], 294274)])
        self.assertIn(f'URL-VENUE-MOVE e294274 l{CENTEREACH}→l{SELDEN} (w{MCPL}, {KEY})',
                      result['log'])
        self.assertIn('URL venue move: 1 event(s)', result['log'])

    def test_another_publishers_row_on_the_same_url_gets_a_twin(self):
        result = run_merge(event_website=5242)
        self.assertTrue(result['created'])
        self.assertNotIn('URL-VENUE-MOVE', result['log'])
        self.assertEqual(result['repins'], [])

    def test_organizer_fallback_listing_does_not_move_the_row(self):
        result = run_merge(ce_label='Middle Country Public Library')
        self.assertNotIn('URL-VENUE-MOVE', result['log'])
        self.assertEqual(result['repins'], [])


if __name__ == '__main__':
    unittest.main()
