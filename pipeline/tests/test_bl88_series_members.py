"""BL88 merger routing gaps behind the 2026-11-05 hand fixes.

1. Series-subtitle members (`series_member_veto`): Sachem w6013 titles each
   screening "EVENING MOVIE (In Person) - <film>" at its own permalink beside a
   bare "Evening Movie (in Person)" card. Every name tier fused the titled
   cards onto the series row (268376; split by hand into 314917-314919).
2. Suppressed title holders (`title_holder_route`): Mehanata's old title "THE
   Y2K Parrty at the Legendary Mehanata NYC - 18" landed on hidden 156307
   although the party runs as two visible weekday series (Fri 210496, Sat
   276875) that hold that title's earlier sources.
3. Redirect program check (`redirect_program_mismatch`): hidden 224790 "Park
   Avenue Chamber Symphony" redirects to 306822 "Romeo and Juliet (Family
   Concert)"; another program of the ensemble must not follow it.

The merge tests drive `merge_crawl_events` over a fake cursor (the
`test_bl25_same_capture_partition` / `test_bl14_redirect_routing` pattern).
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

RESULT = 139075
VENUE = 10810
WEBSITE = 6013
SACHEM = 'https://sachem.librarycalendar.com/event/'
TODAY = date.today()


def run_merge(listings, events=(), *, redirects=(), dismissed=(), holders=None,
              archived=(), website=WEBSITE, listing_urls=(), event_urls=None):
    """Merge `listings` = [(ce_id, name, url, [day offsets], time)] of capture RESULT.

    `events` = [(event_id, name, suppressed, [day offsets], time)] at VENUE;
    `holders` = {event_id: [source names]} (the title-holder evidence);
    `redirects` = [(duplicate, survivor)]. Returns (links {ce: event or
    'NEW:<name>'}, stdout).
    """
    holders = holders or {}
    names = {eid: name for eid, name, *_ in events}
    states = {eid: (sup, 1 if eid in archived else 0, VENUE, name)
              for eid, name, sup, *_ in events}
    created = {}
    next_id = [900001]
    cursor = MagicMock(lastrowid=None)

    def day(d):
        return TODAY + timedelta(days=d)

    def execute(query, params=None):
        rows, one = [], None
        if 'SELECT ce.id, ce.name' in query:
            rows = [(ce, name, None, 'Desc.', '🎬', 'Library', None, VENUE, url,
                     website, None, None, RESULT) for ce, name, url, *_ in listings]
        elif 'SELECT DISTINCT e.id, e.name, e.location_id' in query:
            rows = [(eid, name, VENUE, None, None, 'Library', website, sup)
                    for eid, name, sup, *_ in events]
        elif 'SELECT event_id, start_date, start_time, end_date' in query:
            rows = [(eid, day(d), clock, None)
                    for eid, _n, _s, days, clock in events for d in days]
        elif 'SELECT ce.crawl_result_id, ce.id, ce.name, ce.url, es.event_id' in query:
            rows = [(RESULT, ce, name, url, None) for ce, name, url, *_ in listings]
        elif 'SELECT crawl_result_id, id, name FROM crawl_events' in query:
            rows = [(RESULT, ce, name) for ce, name, *_ in listings]
        elif 'SELECT website_id, url FROM website_urls' in query:
            rows = [(website, u) for u in listing_urls]
        elif 'SELECT eu.event_id, eu.url, e.name, e.website_id' in query:
            rows = [(eid, u, names[eid], website, VENUE, 0)
                    for eid, urls in (event_urls or {}).items() for u in urls]
        elif 'FROM dedupe_dismissed_pairs' in query:
            rows = list(dismissed)
        elif 'FROM event_merge_redirects' in query:
            rows = [(dup, surv, None) for dup, surv in redirects]
        elif 'SELECT id, name, emoji, lat, lng FROM locations' in query:
            rows = [(VENUE, 'Library', '🎬', None, None)]
        elif 'FROM crawl_event_occurrences' in query:
            rows = [(ce, day(d), clock, None, None, 0)
                    for ce, _n, _u, days, clock in listings for d in days]
        elif query.startswith(merger.SUPPRESSED_TITLE_HOLDERS_SQL.split('{')[0]):
            rows = [(eid, n) for eid in params for n in holders.get(eid, ())]
        elif 'INSERT INTO events (' in query:
            cursor.lastrowid = next_id[0]
            created[next_id[0]] = params[0]
            names[next_id[0]] = params[0]
            next_id[0] += 1
        elif 'SELECT suppressed, archived, location_id, name FROM events WHERE id' in query:
            one = states.get(params[0])
        elif 'SELECT archived FROM events WHERE id' in query:
            one = (1 if params[0] in archived else 0,)
        elif 'SELECT name FROM events WHERE id' in query:
            one = (names.get(params[0], ''),)
        elif 'SELECT location_id FROM events WHERE id' in query:
            one = (VENUE,)
        elif 'SELECT location_name, location_id FROM events WHERE id' in query:
            one = ('Library', VENUE)
        elif 'SELECT description, emoji, name, short_name, event_type' in query:
            one = ('Existing.', '🎬', names.get(params[0]), None, None)
        cursor.fetchall.return_value = rows
        cursor.fetchone.return_value = one

    cursor.execute.side_effect = execute
    out = io.StringIO()
    with ExitStack() as stack:
        stack.enter_context(redirect_stdout(out))
        stack.enter_context(patch.object(merger, 'EditLogger', None))
        stack.enter_context(patch.object(merger.reviewed_event_identity, 'load_index',
                                         return_value={}))
        stack.enter_context(patch.object(merger.venue_overrides, 'load_rules', return_value=[]))
        stack.enter_context(patch.object(merger, 'get_active_date_window',
                                         return_value=(TODAY, TODAY + timedelta(days=90))))
        stack.enter_context(patch.object(merger, '_empty_latest_archival_websites',
                                         return_value={}))
        database = stack.enter_context(patch.object(merger, 'db'))
        database.build_tag_ancestor_map.return_value = ({}, set())
        for fn in ('archive_dead_source_events', 'prune_superseded_dates',
                   'prune_superseded_times', 'archive_sourceless_events',
                   'archive_outdated_events'):
            getattr(database, fn).return_value = (0, [])
        # None: the stored schedule is unchanged, so the in-memory date
        # indexes keep the seeded dates for later listings of the pass.
        stack.enter_context(patch.object(merger, '_merge_occurrences_into_event',
                                         return_value=None))
        for helper in ('_merge_grouped_event_urls', 'refresh_source_metadata',
                       'refresh_source_session_details'):
            stack.enter_context(patch.object(merger, helper))
        merger.merge_crawl_events(cursor, MagicMock(), website_ids=[website])
    links = {}
    for c in cursor.execute.call_args_list:
        if 'INSERT IGNORE INTO event_sources' in c.args[0]:
            eid, ce = c.args[1][0], c.args[1][1]
            target = f'NEW:{created[eid]}' if eid in created else eid
            # One event per source, except a per-date title-holder split.
            links[ce] = target if ce not in links else sorted(
                [*(links[ce] if isinstance(links[ce], list) else [links[ce]]), target])
    return links, out.getvalue()


# ── 1. Series-subtitle members ────────────────────────────────────────────────
SERIES = 'Evening Movie (in Person)'
FRANK = 'EVENING MOVIE (In Person) - Frankenstein'
OAK = 'EVENING MOVIE (In Person) - The End of Oak Street'


class SeriesSubtitlePartsTests(unittest.TestCase):

    def test_member_titles(self):
        for name, series, sub in [
            (FRANK, 'EVENING MOVIE (In Person)', 'Frankenstein'),
            ('EVENING MOVIE (In Person) - Rom-Com Day: The Holiday',
             'EVENING MOVIE (In Person)', 'Rom-Com Day: The Holiday'),
            ('Park Avenue Chamber Symphony: Nutcracker', 'Park Avenue Chamber Symphony',
             'Nutcracker'),
            ('Evening Movie — The Holiday', 'Evening Movie', 'The Holiday'),
        ]:
            with self.subTest(name=name):
                self.assertEqual(merger.series_subtitle_parts(name), (series, sub))

    def test_not_member_titles(self):
        for name in [
            SERIES,
            'Nice Try ft: Michael Kosta, Ian Fidance, Ashley Austin Morris',
            'Fatherland – Q&A with Filmmaker Paweł Pawlikowski',  # one-word series
            'Matinee with Ry Daddy - ft. Joe List',               # lineup subtitle
            'Comedy Night Live - Joe List, Sam Morril, Mark Normand',  # bare lineup
            'Reading Rhythms Lower Manhattan: July 27',            # date label
            'Jazz Jam Session - 10:00pm',                          # clock label
            'Nocturnal Critters Club - RESCHEDULED TO 10/29',       # status mark
            'Storytime (Kindergarten - Grade 5)',                  # bracketed range
        ]:
            with self.subTest(name=name):
                self.assertIsNone(merger.series_subtitle_parts(name))

    def test_relation(self):
        rel = merger.series_member_relation
        self.assertEqual(rel(FRANK, SERIES), 'evening movie in person')
        self.assertEqual(rel(SERIES, FRANK), 'evening movie in person')
        self.assertEqual(rel(FRANK, OAK), 'evening movie in person')
        self.assertIsNone(rel(FRANK, FRANK.upper()))
        self.assertIsNone(rel('AFTERNOON MOVIE (In Person) - Frankenstein', FRANK))
        # One subtitle containing the other is a fuller spelling, not a sibling.
        self.assertIsNone(rel('Evening Movie (in Person) - The Holiday',
                              'Evening Movie (in Person) - Rom-Com Day: The Holiday'))


class SeriesMemberMergeTests(unittest.TestCase):

    def test_titled_screening_leaves_the_series_row(self):
        # cr 139075: the series row still holds day 3 from before the retitle;
        # the bare card now lists other days only.
        links, out = run_merge(
            [(1, SERIES, SACHEM + 'evening-movie-person-150184', [10, 17], '6pm'),
             (2, FRANK, SACHEM + 'evening-movie-person-150186', [3], '6pm')],
            events=[(268376, SERIES, 0, [3, 10, 17], '6pm')])
        self.assertEqual(links, {1: 268376, 2: f'NEW:{FRANK}'})
        self.assertIn('Series-subtitle veto: source 2', out)

    def test_two_titled_screenings_stay_apart(self):
        links, _ = run_merge(
            [(1, SERIES, SACHEM + 'evening-movie-person-150184', [10], '6pm'),
             (2, FRANK, SACHEM + 'evening-movie-person-150186', [3], '6pm'),
             (3, OAK, SACHEM + 'evening-movie-person-150187', [4], '6pm')],
            events=[(268376, SERIES, 0, [3, 4, 10], '6pm')])
        self.assertEqual(links[1], 268376)
        self.assertEqual(links[2], f'NEW:{FRANK}')
        self.assertEqual(links[3], f'NEW:{OAK}')

    def test_bare_series_does_not_land_on_a_titled_member_row(self):
        # 250819 "AFTERNOON MOVIE (In Person) - Carolina Caroline" absorbed the
        # bare afternoon series and four other films.
        member = 'AFTERNOON MOVIE (In Person) - Carolina Caroline'
        links, _ = run_merge(
            [(1, 'Afternoon Movie (in Person)', SACHEM + 'afternoon-movie-person-150137',
              [10], '1:30pm'),
             (2, 'AFTERNOON MOVIE (In Person) - Frankenstein',
              SACHEM + 'afternoon-movie-person-150136', [3], '1:30pm')],
            events=[(250819, member, 0, [3, 10], '1:30pm')])
        self.assertEqual(links[1], 'NEW:Afternoon Movie (in Person)')
        self.assertEqual(links[2], 'NEW:AFTERNOON MOVIE (In Person) - Frankenstein')

    def test_same_slot_under_two_titles_stays_one_event(self):
        # The bare card lists the titled card's showtime too: one screening
        # printed twice ("Fatherland" / "FATHERLAND – Q&A …" shape).
        links, out = run_merge(
            [(1, SERIES, SACHEM + 'evening-movie-person-150184', [3, 10], '6pm'),
             (2, FRANK, SACHEM + 'evening-movie-person-150186', [3], '6pm')],
            events=[(268376, SERIES, 0, [3, 10], '6pm')])
        self.assertEqual(links, {1: 268376, 2: 268376})
        self.assertNotIn('Series-subtitle veto', out)

    def test_second_session_same_day_stays_on_the_titled_row(self):
        # w6058: the bare card is the 11:45am session of the 10:30am titled
        # program on the same days; the titled row holds both times.
        titled = 'Drama with your Mama: Broadway Babies'
        lib = 'https://library.example/event?id='
        links, out = run_merge(
            [(1, titled, lib + '372151', [3, 10], '10:30am'),
             (2, 'Drama With Your Mama', lib + '372152', [3, 10], '11:45am')],
            events=[(300618, titled, 0, [3, 10], '10:30am')])
        self.assertEqual(links, {1: 300618, 2: 300618})
        self.assertNotIn('Series-subtitle veto', out)

    def test_series_row_holding_the_cards_own_page_is_the_same_record(self):
        # gemsny.org "House of Time" → "House of Time: Circle of Life" at the
        # same /house-of-time-26/ permalink: a retitle, not a new member.
        page = SACHEM + 'evening-movie-person-150186'
        links, out = run_merge(
            [(1, SERIES, SACHEM + 'evening-movie-person-150184', [10], '6pm'),
             (2, FRANK, page, [3], '6pm')],
            events=[(268376, SERIES, 0, [3, 10], '6pm')], event_urls={268376: [page]})
        self.assertEqual(links, {1: 268376, 2: 268376})
        self.assertNotIn('Series-subtitle veto', out)

    def test_without_a_sibling_in_the_capture_the_old_match_stands(self):
        links, _ = run_merge(
            [(2, FRANK, SACHEM + 'evening-movie-person-150186', [3], '6pm')],
            events=[(268376, SERIES, 0, [3, 10], '6pm')])
        self.assertEqual(links, {2: 268376})

    def test_ensemble_calendar_without_a_bare_card_keeps_the_ensemble_row(self):
        # mmc.band w2263: every card is "<ensemble>: <program>"; the
        # ensemble-named row is their reviewed home (decisions.md "PACS").
        mmc = 'https://www.mmc.band/calendar-details?recordId='
        links, out = run_merge(
            [(1, 'Park Avenue Chamber Symphony: Nutcracker', mmc + 'rec66W2mAcSYRU8yw',
              [10, 11], '2pm'),
             (2, 'Park Avenue Chamber Symphony: Romeo and Juliet', mmc + 'recqzd2fofyXUMnfr',
              [3], '5pm')],
            events=[(275775, 'Park Avenue Chamber Symphony', 1, [10, 11], '2pm')],
            website=2263)
        self.assertEqual(links[1], 275775)
        self.assertNotIn('skips 275775', out)

    def test_listing_url_is_no_evidence(self):
        cal = SACHEM.rstrip('/')
        links, _ = run_merge(
            [(1, SERIES, cal, [10], '6pm'), (2, FRANK, cal, [3], '6pm')],
            events=[(268376, SERIES, 0, [3, 10], '6pm')], listing_urls=[cal])
        self.assertEqual(links, {1: 268376, 2: 268376})

    def test_veto_unit(self):
        key = merger.normalize_url_for_identity
        listings = [(1, SERIES, merger.normalize_name_for_dedup(SERIES),
                     key(SACHEM + 'evening-movie-person-150184'))]
        slots = {1: {(str(TODAY), '6pm')}}
        veto = lambda own: merger.series_member_veto(  # noqa: E731
            FRANK, key(SACHEM + 'evening-movie-person-150186'), WEBSITE, 2, own,
            SERIES, listings, lambda ce: slots[ce], set(), {})
        self.assertEqual(veto({(str(TODAY + timedelta(days=1)), '6pm')}), SERIES)
        self.assertIsNone(veto({(str(TODAY), '6pm')}))
        self.assertIsNone(veto({(str(TODAY), '')}))  # untimed same day: shared
        # Same day, another hour: a second session of one program (w6058
        # "Drama With Your Mama" 11:45am beside "...: Broadway Babies" 10:30am).
        self.assertIsNone(veto({(str(TODAY), '11:45am')}))


# ── 2. Suppressed title holders (Mehanata) ────────────────────────────────────
OLD = 'THE Y2K Parrty at the Legendary Mehanata NYC - 18'
FRI_NAME = 'The 2000s Forever Parrty by THE Y2K Parrty - Fridays at Mehanata NYC'
SAT_NAME = 'The 2000s Forever Parrty by THE Y2K Parrty - Saturdays at Mehanata NYC'
HIDDEN, FRI, SAT = 156307, 210496, 276875


def _next(weekday, weeks=0):
    return (weekday - TODAY.weekday()) % 7 + 7 * weeks


class TitleHolderTests(unittest.TestCase):
    RA = 'https://ra.co/events/'

    def merge(self, days, *, holders=None, time='10pm', **kwargs):
        fri = [_next(4, w) for w in range(4)]
        sat = [_next(5, w) for w in range(4)]
        events = kwargs.pop('events', [
            (HIDDEN, OLD, 1, fri + sat, '10pm'),
            (FRI, FRI_NAME, 0, fri[:2], '10pm'),
            (SAT, SAT_NAME, 0, sat[:2], '10pm')])
        if holders is None:
            holders = {FRI: [FRI_NAME, OLD.replace(' - 18', ' | 18+')],
                       SAT: [SAT_NAME, OLD]}
        return run_merge([(1, OLD, self.RA + '2544439', days, time)], events,
                         holders=holders, website=388, **kwargs)

    def test_old_title_follows_its_weekday_series(self):
        links, out = self.merge([_next(5, 3)])  # a Saturday beyond SAT's dates
        self.assertEqual(links, {1: SAT})
        self.assertIn(f'Title-holder handoff: suppressed {HIDDEN} -> {SAT} (1 date(s))', out)
        links, _ = self.merge([_next(4, 0)])
        self.assertEqual(links, {1: FRI})

    def test_source_spanning_the_split_is_routed_per_date(self):
        # The live shape: one "| 18+" card lists every Friday and Saturday.
        days = [_next(4, 0), _next(5, 0), _next(5, 1)]
        links, out = self.merge(days)
        self.assertEqual(links, {1: sorted([FRI, SAT])})
        self.assertIn(f'-> {FRI} (1 date(s)), {SAT} (2 date(s))', out)

    def test_unassignable_date_stays_and_is_reported(self):
        # A Sunday: no holder has it, no holder runs on Sundays.
        links, out = self.merge([_next(5, 0), _next(6, 0)])
        self.assertEqual(links, {1: HIDDEN})
        self.assertIn(f'WEEKDAY-SPLIT e{HIDDEN}', out)

    def test_single_holder_running_the_slot_takes_the_source(self):
        # One visible holder that already runs the source's weekday at its
        # clock (the 30-day replay's Greenmarket / CRUX / Carnegie rows).
        links, out = self.merge([_next(5, 0), _next(5, 3)], holders={SAT: [SAT_NAME, OLD]})
        self.assertEqual(links, {1: SAT})
        self.assertIn(f'Title-holder handoff: suppressed {HIDDEN} -> {SAT} (2 date(s))', out)

    def test_single_holder_at_another_hour_or_day_is_only_reported(self):
        # Otto's "Wednesday Band Night" 7pm vs the 5pm/6pm open mic holding
        # the title: not shown to be the same slot, so a redirect needs review.
        for days, time in (([_next(5, 0)], '7pm'), ([_next(4, 0)], '10pm')):
            with self.subTest(time=time):
                links, out = self.merge(days, holders={SAT: [SAT_NAME, OLD]}, time=time)
                self.assertEqual(links, {1: HIDDEN})
                self.assertIn(f'TITLE-HOLDER e{HIDDEN}', out)

    def test_no_title_evidence_keeps_the_hidden_row(self):
        links, out = self.merge([_next(5, 0)], holders={FRI: [FRI_NAME], SAT: [SAT_NAME]})
        self.assertEqual(links, {1: HIDDEN})
        self.assertNotIn('Title-holder', out)
        self.assertNotIn('WEEKDAY-SPLIT', out)

    def test_redirect_dismissal_or_archived_holder_wins_over_the_rule(self):
        for kwargs in ({'redirects': [(HIDDEN, FRI)]},
                       {'dismissed': [(HIDDEN, SAT)]},
                       {'archived': [SAT]}):
            with self.subTest(**{k: str(v) for k, v in kwargs.items()}):
                links, out = self.merge([_next(5, 0)], **kwargs)
                self.assertNotIn(SAT, links[1] if isinstance(links[1], list) else [links[1]])
                self.assertNotIn(f'-> {SAT}', out)

    def test_route_unit(self):
        sat = str(TODAY + timedelta(days=_next(5, 0)))
        fri = str(TODAY + timedelta(days=_next(4, 0)))
        later_sat = str(TODAY + timedelta(days=_next(5, 2)))
        sun = str(TODAY + timedelta(days=_next(6, 0)))
        dates = {FRI: {fri}, SAT: {sat}}
        route = lambda days, hs=(FRI, SAT): merger.title_holder_route(  # noqa: E731
            set(days), list(hs), lambda e: dates[e])
        self.assertEqual(route([later_sat]), ('route', {SAT: {later_sat}}))
        self.assertEqual(route([fri, later_sat]), ('route', {FRI: {fri}, SAT: {later_sat}}))
        self.assertEqual(route([fri, sun]), ('split', [FRI, SAT]))
        self.assertEqual(route([fri], hs=()), (None, None))
        self.assertEqual(route([fri], hs=(SAT,)), ('single', SAT))
        # One holder: routed only when it runs every incoming slot.
        held = {SAT: {(sat, '8am')}}
        one = lambda slots: merger.title_holder_route(  # noqa: E731
            {d for d, _ in slots}, [SAT], lambda e: dates[e], incoming_slots=set(slots),
            holder_slots=lambda e: held[e])
        self.assertEqual(one({(later_sat, '8am')}), ('route', {SAT: {later_sat}}))
        self.assertEqual(one({(sat, '')}), ('route', {SAT: {sat}}))
        self.assertEqual(one({(later_sat, '7pm')}), ('single', SAT))
        self.assertEqual(one({(later_sat, '8am'), (fri, '8am')}), ('single', SAT))
        # Two holders on the same weekday: only an exact date decides.
        dates[FRI] = {fri, sat}
        self.assertEqual(route([sat]), ('split', [FRI, SAT]))
        self.assertEqual(route([later_sat]), ('split', [FRI, SAT]))


# ── 3. Redirect program check (mmc.band PACS) ─────────────────────────────────
PACS = 'Park Avenue Chamber Symphony'
ROMEO = 'Romeo and Juliet (Family Concert)'


class RedirectProgramTests(unittest.TestCase):
    MMC = 'https://www.mmc.band/calendar-details?recordId='

    def test_mismatch_unit(self):
        mismatch = merger.redirect_program_mismatch
        self.assertTrue(mismatch(f'{PACS}: Nutcracker', PACS, ROMEO))
        self.assertTrue(mismatch(f'{PACS}: Beethoven 7', PACS, ROMEO))
        self.assertFalse(mismatch(f'{PACS}: Romeo and Juliet', PACS, ROMEO))
        self.assertFalse(mismatch(f'{PACS}: {ROMEO}', PACS, ROMEO))
        self.assertFalse(mismatch(PACS, PACS, ROMEO))  # bare name: no program evidence
        self.assertFalse(mismatch('Chelsea Symphony: Eroica', PACS, ROMEO))  # other head

    def merge(self, name):
        return run_merge(
            [(1, name, self.MMC + 'recNEW', [3], '2pm')],
            events=[(224790, PACS, 1, [3], '2pm'), (306822, ROMEO, 0, [3], '2pm')],
            redirects=[(224790, 306822)], website=2263)

    def test_matching_program_follows_the_redirect(self):
        links, out = self.merge(f'{PACS}: Romeo and Juliet')
        self.assertEqual(links, {1: 306822})
        self.assertNotIn('Redirect program veto', out)

    def test_other_program_does_not_follow_the_redirect(self):
        links, out = self.merge(f'{PACS}: Beethoven Symphony No. 7')
        self.assertEqual(links, {1: f'NEW:{PACS}: Beethoven Symphony No. 7'})
        self.assertIn('Redirect program veto: source 1', out)

    def test_bare_ensemble_card_still_follows_the_redirect(self):
        links, _ = self.merge(PACS)
        self.assertEqual(links, {1: 306822})


if __name__ == '__main__':
    unittest.main()
