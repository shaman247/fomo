"""A dismissed pair binds the listing whose permalink one member holds (BL25/BL85).

Pratt w536 lists the 11/17 online GCPE session twice: as "Grad Center for
Planning and the Environment Virtual Information Session" and as "GCPE Graduate
Admissions Information Session" (`…-session/`, Online). The user un-merged the
virtual 278442 from the in-person 277086 on 2026-10-18 (dismissed pair 51277)
and `…-session/` stayed on 278442, yet every merge since put the online slot and
that URL back on 277086 (stripped by hand 10-24, 11-01, 11-04):

- 10-25 / 10-30: the venue tier matched the hidden dedupe loser 278408 (exact
  name at Pratt 1786); its 10-05 merge redirect sent the source to 277086, and
  the name-bound dismissed-pair veto found no "GCPE Graduate Admissions…" source
  on 278442, so it never fired;
- 11-04: the processor fused the in-person `…-session-2/` record (dates
  dropped) with the online one; the URL twin of 278408 on `…-session-2/` is
  277086, and BL52 session routing ignored the fused source because only ONE of
  its permalinks carried a date.

The merge tests drive the whole `merge_crawl_events` path over a fake cursor
(the `test_bl14_redirect_routing` pattern).
"""
import io
import json
import sys
import unittest
from contextlib import ExitStack, redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger

WEB = 536
VENUE = 1786
CE = 1683719
TODAY = date.today()
DAY = TODAY + timedelta(days=13)
HIDDEN, IN_PERSON, VIRTUAL = 278408, 277086, 278442
HIDDEN_NAME = 'GCPE Graduate Admissions Information Session'
IN_PERSON_NAME = 'Grad Center for Planning and the Environment Information Session'
VIRTUAL_NAME = 'Grad Center for Planning and the Environment Virtual Information Session'
BASE = 'https://www.pratt.edu/events/'
ONLINE_URL = BASE + 'gcpe-graduate-admissions-information-session/'
IN_PERSON_URL = BASE + 'gcpe-graduate-admissions-information-session-2/'
VIRTUAL_URL = BASE + 'grad-center-for-planning-and-the-environment-virtual-information-session-2/'
DISMISSED = [(IN_PERSON, VIRTUAL)]
REDIRECT = [(HIDDEN, IN_PERSON)]
URLS = [(HIDDEN, IN_PERSON_URL), (HIDDEN, ONLINE_URL), (IN_PERSON, IN_PERSON_URL),
        (VIRTUAL, VIRTUAL_URL), (VIRTUAL, ONLINE_URL)]
# Earlier same-name sources of the in-person event (its own `…-session-2/` page).
SOURCES = [(IN_PERSON, IN_PERSON_URL, HIDDEN_NAME, VENUE)]


def run_merge(*, url=ONLINE_URL, raw=None, event_urls=URLS, dismissed=DISMISSED,
              redirects=REDIRECT, sources=SOURCES, ce_slots=(('6pm', '8pm'),)):
    events = {HIDDEN: (HIDDEN_NAME, 1, [('6pm', DAY), ('12pm', DAY)]),
              IN_PERSON: (IN_PERSON_NAME, 0, [('12pm', DAY)]),
              VIRTUAL: (VIRTUAL_NAME, 0, [('6pm', DAY)])}
    cursor = MagicMock(lastrowid=999999)
    raw = raw or {'name': HIDDEN_NAME, 'urls': [url, BASE]}

    def execute(query, params=None):
        rows, one = [], None
        if 'SELECT ce.id, ce.name' in query:
            rows = [(CE, HIDDEN_NAME, None, 'Info session.', '🎓', 'Pratt Institute', None,
                     VENUE, url, WEB, None, None, 137273)]
        elif 'SELECT DISTINCT e.id, e.name, e.location_id' in query:
            rows = [(eid, name, VENUE, None, None, 'Pratt Institute', WEB, hidden)
                    for eid, (name, hidden, _) in events.items()]
        elif 'SELECT event_id, start_date, start_time, end_date' in query:
            rows = [(eid, day, clock, None) for eid, (_, _, slots) in events.items()
                    for clock, day in slots]
        elif 'SELECT crawl_result_id, id, name FROM crawl_events' in query:
            rows = [(137273, CE, HIDDEN_NAME)]
        elif 'SELECT id, raw_data FROM crawl_events' in query:
            rows = [(CE, json.dumps(raw))]
        elif 'SELECT eu.event_id, eu.url, e.name' in query:
            rows = [(eid, u, events[eid][0], WEB, VENUE, events[eid][1]) for eid, u in event_urls]
        elif query.startswith('SELECT website_id, url FROM website_urls'):
            rows = [(WEB, BASE)]
        elif 'FROM dedupe_dismissed_pairs' in query:
            rows = list(dismissed)
        elif 'FROM event_merge_redirects' in query:
            rows = [tuple(r) + (None,) for r in redirects]
        elif 'SELECT DISTINCT event_id FROM event_source_identities' in query:
            rows = []
        elif params and query == merger.DISMISSED_HOME_SOURCES_SQL.format(
                placeholders=','.join(['%s'] * (len(params) - 1))):
            rows = [s for s in sources if s[0] in set(params[1:])]
        elif params and query == merger.DISMISSED_SESSION_OWNERS_SQL.format(
                placeholders=','.join(['%s'] * len(params))):
            rows = [(eid, u) for eid, u in event_urls if eid in params and not events[eid][1]]
        elif params and query == merger.DISMISSED_SESSION_DATES_SQL.format(
                placeholders=','.join(['%s'] * len(params))):
            rows = [(eid, day) for eid in params for _, day in events[eid][2]]
        elif 'SELECT id, name, emoji, lat, lng FROM locations' in query:
            rows = [(VENUE, 'Pratt Institute (Brooklyn campus)', '🎓', None, None)]
        elif 'FROM crawl_event_occurrences' in query:
            rows = [(CE, DAY, start, None, end, i) for i, (start, end) in enumerate(ce_slots)]
        elif 'SELECT suppressed, archived, location_id, name FROM events WHERE id' in query:
            name, hidden, _ = events[params[0]]
            one = (hidden, 0, VENUE, name)
        elif 'SELECT location_id FROM events WHERE id' in query:
            one = (VENUE,)
        elif 'SELECT location_name, location_id FROM events WHERE id' in query:
            one = ('Pratt Institute', VENUE)
        elif 'SELECT name FROM events WHERE id' in query:
            one = (events.get(params[0], ('',))[0],)
        elif 'SELECT description, emoji, name, short_name, event_type' in query:
            one = ('Existing.', '🎓', events[params[0]][0], None, None)
        cursor.fetchall.return_value = rows
        cursor.fetchone.return_value = one

    cursor.execute.side_effect = execute
    with ExitStack() as stack:
        stack.enter_context(redirect_stdout(io.StringIO()))
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
        database.archive_dead_source_events.return_value = (0, [])
        database.prune_superseded_dates.return_value = (0, [])
        database.archive_sourceless_events.return_value = (0, [])
        database.archive_outdated_events.return_value = (0, [])
        occ_merge = stack.enter_context(patch.object(
            merger, '_merge_occurrences_into_event', return_value=None))
        url_merge = stack.enter_context(patch.object(merger, '_merge_grouped_event_urls'))
        stack.enter_context(patch.object(merger, 'compute_voted_tags', return_value=[]))
        for helper in ('refresh_source_metadata', 'refresh_source_session_details'):
            stack.enter_context(patch.object(merger, helper))
        merger.merge_crawl_events(cursor, MagicMock(), website_ids=[WEB])
    calls = cursor.execute.call_args_list
    links = [c.args[1] for c in calls if 'INSERT IGNORE INTO event_sources' in c.args[0]]
    url_inserts = [c.args[1] for c in calls if c.args[0].startswith('INSERT INTO event_urls')]
    grouped = {c.args[1]: merger._grouped_event_urls(c.args[2]) for c in url_merge.call_args_list}
    merged = {c.args[1]: sorted(str(o[1]) for o in c.args[2]) for c in occ_merge.call_args_list}
    return links, url_inserts, grouped, merged


class OnlineListingMergeTests(unittest.TestCase):
    """The 10-25 / 10-30 shape: a separate online crawl_event on `…-session/`."""

    def test_redirect_survivor_is_vetoed_and_the_page_owner_takes_it(self):
        links, url_inserts, _, merged = run_merge()
        self.assertEqual(links, [(VIRTUAL, CE)])
        self.assertNotIn(IN_PERSON, merged)
        self.assertFalse([u for u in url_inserts if u[0] == IN_PERSON])

    def test_without_the_dismissal_the_redirect_still_routes(self):
        links, _, _, _ = run_merge(dismissed=())
        self.assertEqual(links, [(IN_PERSON, CE)])

    def test_a_survivor_holding_the_page_itself_is_not_vetoed(self):
        """Contested ownership (both members hold the page) falls back to the
        name identity, which does not fire here: the old behaviour."""
        links, _, _, _ = run_merge(event_urls=URLS + [(IN_PERSON, ONLINE_URL)])
        self.assertEqual(links, [(IN_PERSON, CE)])

    def test_a_listing_url_is_not_ownership(self):
        links, _, _, _ = run_merge(url=BASE, event_urls=URLS + [(VIRTUAL, BASE)])
        self.assertEqual(links, [(IN_PERSON, CE)])


class FusedSourceMergeTests(unittest.TestCase):
    """The 11-04 shape: one crawl_event fused from both GCPE records."""

    RAW = {'name': HIDDEN_NAME,
           'urls': [IN_PERSON_URL, BASE, ONLINE_URL],
           'session_details': [
               {'description': 'In person.', 'sublocation': 'Higgins Hall, HHN 304',
                'sessions': [{'start_date': '', 'start_time': '', 'url': IN_PERSON_URL}]},
               {'description': 'Online.', 'sublocation': '',
                'sessions': [{'start_date': str(DAY), 'start_time': '6pm',
                              'end_time': '8pm', 'url': ONLINE_URL}]}]}

    def test_undated_permalink_still_lets_the_dated_session_go_home(self):
        links, url_inserts, grouped, merged = run_merge(url=IN_PERSON_URL, raw=self.RAW)
        self.assertEqual(links, [(VIRTUAL, CE)])
        self.assertNotIn(IN_PERSON, merged)
        # The in-person page is withheld from the virtual event.
        self.assertFalse([u for u in url_inserts if u[1] == IN_PERSON_URL])
        self.assertNotIn(IN_PERSON_URL, grouped.get(VIRTUAL, []))

    def test_without_the_dismissal_the_fused_source_stays_put(self):
        links, _, _, _ = run_merge(url=IN_PERSON_URL, raw=self.RAW, dismissed=())
        self.assertEqual(links, [(IN_PERSON, CE)])


class UrlOwnerVetoUnitTests(unittest.TestCase):
    KEY = merger.normalize_url_for_identity(ONLINE_URL)

    def veto(self, candidate=IN_PERSON, partners=(VIRTUAL,), keys=None, hidden=(),
             listing=(), names=None):
        keys = keys if keys is not None else {VIRTUAL: {self.KEY}, IN_PERSON: set()}
        return merger._dismissed_url_owner_veto(
            candidate, set(partners), self.KEY, WEB, keys, set(hidden),
            set(listing), names or {})

    def test_partner_owning_the_page_vetoes(self):
        self.assertEqual(self.veto(), (VIRTUAL,))

    def test_candidate_holding_the_page_is_exempt(self):
        self.assertIsNone(self.veto(keys={VIRTUAL: {self.KEY}, IN_PERSON: {self.KEY}}))

    def test_hidden_partner_and_listing_pages_do_not_count(self):
        self.assertIsNone(self.veto(hidden=(VIRTUAL,)))
        self.assertIsNone(self.veto(listing={(WEB, self.KEY)}))
        self.assertIsNone(self.veto(names={(WEB, self.KEY): 3}))
        self.assertIsNone(self.veto(partners=()))


class SourceUrlSessionsTests(unittest.TestCase):
    def sessions(self, raw):
        return merger.source_url_sessions(raw, lambda key: False)

    def test_an_undated_permalink_counts_toward_a_fused_source(self):
        got = self.sessions(FusedSourceMergeTests.RAW)
        self.assertEqual(got, {merger.normalize_url_for_identity(IN_PERSON_URL): set(),
                               merger.normalize_url_for_identity(ONLINE_URL): {str(DAY)}})

    def test_no_dated_session_means_no_map(self):
        raw = json.loads(json.dumps(FusedSourceMergeTests.RAW))
        raw['session_details'][1]['sessions'][0]['start_date'] = ''
        self.assertEqual(self.sessions(raw), {})


if __name__ == '__main__':
    unittest.main()
