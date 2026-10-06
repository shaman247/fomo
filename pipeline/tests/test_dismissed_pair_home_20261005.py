"""A crawl_event must not attach to an event that `dedupe_dismissed_pairs`
rules DIFFERENT from the event its own listing belongs to.

Weekly recheck 2026-10-04: every real defect was a merge-time bleed, where a
sibling listing's crawl_event fused onto the wrong event. Several pairs were
already dismissed (RU Open House 225277 vs OHNY Climate Imaginarium 226662,
Halloween del Perreo 265861 vs the Thursday series 184837), yet the merger never
read the table, so the same pair re-fused on the next merge.

The merge tests drive the whole `merge_crawl_events` path over a fake cursor
(`test_suppressed_url_twin` pattern), so the index builders, the tier ladder,
the cross-location guard and the lazy source loader all run for real.
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

CE_ID = 1600001
TAMI_WEB = 2549
TAMI_LOC = 3689
TAMI_CLOSING = 'Closing Event: The Next Leg of Tami Luchow’s Dis Tour'
TAMI_CLOSING_URL = 'https://positiveexposure.org/event/closing-event-the-next-leg-of-tami-luchows-dis-tour/'
TAMI_EXHIBIT = (254561, 'The Next Leg of Tami Luchow’s Dis Tour: Vision Quest', TAMI_LOC)
TAMI_TALK = (277552, 'Tami Luchow’s Dis Tour: Aging with PIZAZZ!', TAMI_LOC)

RU_WEB = 301
RU_DAY1 = 'Open House New York Weekend: The Climate Imaginarium, Day 1'
RU_URL = 'https://www.govisland.com/things-to-do/events/open-house-new-york-weekend-the-climate-imaginarium-day-1'
RU_OPEN_HOUSE = (225277, 'RU Open House Weekends', 356)
RU_OHNY = (226662, 'Open House New York Weekend: The Climate Imaginarium (Day 1)', 4659)


def run_merge(*, ce_name, url, website, ce_venue, events, sources=(), dismissed=(),
              home_days=0, website_pins=()):
    """Merge one crawl_event against `events` = [(id, name, venue), ...].

    `sources` = [(event_id, url, name, venue)] are earlier crawl_events of
    `website` already linked to those events. Every event has an occurrence
    today except the LAST one, which sits `home_days` out. Returns
    (links, created, relocations).
    """
    today = date.today()
    venues = {eid: venue for eid, _, venue in events}
    names = {eid: name for eid, name, _ in events}
    cursor = MagicMock(lastrowid=999999)

    def execute(query, params=None):
        rows, one = [], None
        if 'SELECT ce.id, ce.name' in query:
            rows = [(CE_ID, ce_name, None, 'Desc.', '🎨', 'Venue', None,
                     ce_venue, url, website, None, None, 128000)]
        elif 'SELECT DISTINCT e.id, e.name, e.location_id' in query:
            rows = [(eid, name, venue, None, None, 'Venue', website, 0)
                    for eid, name, venue in events]
        elif 'SELECT event_id, start_date, start_time, end_date' in query:
            rows = [(eid, today + timedelta(days=home_days if i == len(events) - 1 else 0),
                     '5pm', None) for i, (eid, _, _) in enumerate(events)]
        elif 'SELECT crawl_result_id, id, name FROM crawl_events' in query:
            rows = [(128000, CE_ID, ce_name)]
        elif 'FROM website_locations' in query:
            rows = list(website_pins)
        elif 'FROM dedupe_dismissed_pairs' in query:
            rows = list(dismissed)
        elif params and query == merger.DISMISSED_HOME_SOURCES_SQL.format(
                placeholders=','.join(['%s'] * (len(params) - 1))):
            wanted = set(params[1:])
            assert params[0] == website
            rows = [s for s in sources if s[0] in wanted]
        elif 'SELECT id, name, emoji, lat, lng FROM locations' in query:
            rows = [(v, f'Venue {v}', '📍', None, None) for v in set(venues.values()) | {ce_venue}]
        elif 'FROM crawl_event_occurrences' in query:
            rows = [(CE_ID, today, '5pm', None, None, 0)]
        elif 'SELECT name FROM events WHERE id' in query:
            one = (names.get(params[0], ''),)
        elif 'SELECT location_id FROM events WHERE id' in query:
            one = (venues.get(params[0]),)
        elif 'SELECT location_name, location_id FROM events WHERE id' in query:
            one = ('Venue', venues.get(params[0]))
        elif 'SELECT description, emoji, name, short_name, event_type' in query:
            one = ('Existing.', '🎨', names.get(params[0]), None, None)
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
        for helper in ('_merge_occurrences_into_event', '_merge_grouped_event_urls',
                       'refresh_source_metadata', 'refresh_source_session_details'):
            stack.enter_context(patch.object(merger, helper))
        merger.merge_crawl_events(cursor, MagicMock(), website_ids=[website])
    calls = cursor.execute.call_args_list
    links = [c.args[1] for c in calls if 'INSERT IGNORE INTO event_sources' in c.args[0]]
    created = any('INSERT INTO events (' in c.args[0] for c in calls)
    relocations = [c.args[1] for c in calls if c.args[0].startswith('UPDATE events SET location_id')]
    return links, created, relocations


class DismissedPairMergeTests(unittest.TestCase):

    # ── Tami Luchow (254561 vs 277552): sibling listing, home not name-similar ──
    def tami(self, **kw):
        args = dict(ce_name=TAMI_CLOSING, url=TAMI_CLOSING_URL, website=TAMI_WEB,
                    ce_venue=TAMI_LOC, events=[TAMI_EXHIBIT, TAMI_TALK],
                    sources=[(277552, TAMI_CLOSING_URL, TAMI_CLOSING, TAMI_LOC)],
                    dismissed=[(254561, 277552)])
        args.update(kw)
        return run_merge(**args)

    def test_closing_event_goes_home_not_to_the_dismissed_exhibition(self):
        self.assertTrue(merger.are_names_similar(TAMI_CLOSING, TAMI_EXHIBIT[1]))
        self.assertFalse(merger.are_names_similar(TAMI_CLOSING, TAMI_TALK[1]))
        links, created, _ = self.tami()
        self.assertEqual(links, [(277552, CE_ID)])
        self.assertFalse(created)

    def test_without_the_dismissal_the_old_bleed_still_happens(self):
        links, _, _ = self.tami(dismissed=[])
        self.assertEqual(links, [(254561, CE_ID)])

    def test_without_prior_home_evidence_nothing_changes(self):
        # First sighting of the listing: no earlier source speaks for it.
        links, _, _ = self.tami(sources=[])
        self.assertEqual(links, [(254561, CE_ID)])

    def test_home_without_overlapping_dates_creates_instead_of_bleeding(self):
        links, created, _ = self.tami(home_days=5)
        self.assertTrue(created)
        self.assertEqual(links, [(999999, CE_ID)])

    # ── INSTINCTS: one page carries the run and its reception ──
    def test_shared_page_other_names_are_not_this_listing(self):
        # The exhibition's own sources sit on the SAME URL under other names;
        # the reception's home (276644) holds the reception name.
        url = 'https://www.huntingtonarts.org/event/artist-member-jo-wadler-featured-in-instincts/'
        run = (276485, 'Instincts: Schery Markee-Sullivan, Gina Mars and Jo Wadler', 7832)
        talk = (276645, 'Artist Member Jo Wadler featured in Instincts: Art Talk', 7832)
        links, _, _ = run_merge(
            ce_name='Instincts ArTalk', url=url + 'art-talk/', website=1716, ce_venue=7832,
            events=[run, talk],
            sources=[(276485, url, run[1], 7832),
                     (276485, url, 'Artist Member Jo Wadler featured in Instincts', 7832),
                     (276645, url + 'art-talk/', 'Instincts ArTalk', 7832)],
            dismissed=[(276485, 276645)])
        self.assertEqual(links, [(276645, CE_ID)])

    # ── RU Open House (225277 vs 226662): contested, cross-website home ──
    def ru(self, **kw):
        args = dict(ce_name=RU_DAY1, url=RU_URL, website=RU_WEB, ce_venue=356,
                    events=[RU_OPEN_HOUSE, RU_OHNY],
                    sources=[(225277, RU_URL, RU_DAY1, 356), (226662, RU_URL, RU_DAY1, 356)],
                    dismissed=[(225277, 226662)])
        args.update(kw)
        return run_merge(**args)

    def test_contested_listing_goes_to_the_exact_named_dismissed_partner(self):
        links, created, relocations = self.ru()
        self.assertEqual(links, [(226662, CE_ID)])
        self.assertFalse(created)
        # Home kept at its own venue; the source's pin must not move it.
        self.assertEqual(relocations, [])

    def test_contested_listing_stays_when_candidate_holds_more_evidence(self):
        links, _, _ = self.ru(sources=[(225277, RU_URL, RU_DAY1, 356),
                                       (225277, RU_URL, RU_DAY1, 356),
                                       (226662, RU_URL, RU_DAY1, 356)])
        self.assertEqual(links, [(225277, CE_ID)])

    def test_undismissed_pair_is_untouched(self):
        links, _, _ = self.ru(dismissed=[])
        self.assertEqual(links, [(225277, CE_ID)])


class DismissedHomeVetoUnitTests(unittest.TestCase):
    NAME = merger.normalize_name_for_dedup('Instincts ArTalk')

    def veto(self, group, candidate=1, partners=frozenset({2}), url_key='site/e/1',
             location_id=7, names=None):
        names = names or {}
        return merger._dismissed_home_veto(candidate, set(partners), group, url_key,
                                           self.NAME, location_id,
                                           lambda eid: names.get(eid, 'Other'))

    def test_listing_identity_is_name_plus_url_or_venue(self):
        self.assertEqual(self.veto({1: [], 2: [('site/e/1', self.NAME, None)]}), (2,))
        self.assertEqual(self.veto({1: [], 2: [('', self.NAME, 7)]}), (2,))
        # same name, different URL and venue: a different listing
        self.assertIsNone(self.veto({1: [], 2: [('site/e/9', self.NAME, 8)]}))

    def test_url_alone_is_not_identity(self):
        # A festival umbrella's URL carried by every show (United Solo w195).
        self.assertIsNone(self.veto({1: [], 2: [('site/e/1', 'festival', 8)]}))
        # A listing URL never counts.
        self.assertIsNone(self.veto({1: [], 2: [('site/e/1', self.NAME, 8)]}, url_key=''))

    def test_candidate_carrying_the_incoming_name_is_never_skipped(self):
        self.assertIsNone(self.veto({1: [], 2: [('site/e/1', self.NAME, 7)]},
                                    names={1: 'Instincts: ArTalk'}))

    def test_contested_needs_exact_name_partner_and_at_least_equal_evidence(self):
        group = {1: [('site/e/1', self.NAME, 7)], 2: [('site/e/1', self.NAME, 7)]}
        self.assertEqual(self.veto(group, names={2: 'Instincts: ArTalk'}), (2,))
        self.assertIsNone(self.veto(group))  # partner name not exact
        group[1] = group[1] * 2
        self.assertIsNone(self.veto(group, names={2: 'Instincts: ArTalk'}))

    def test_no_partners_no_veto(self):
        self.assertIsNone(self.veto({1: []}, partners=frozenset()))


if __name__ == '__main__':
    unittest.main()
