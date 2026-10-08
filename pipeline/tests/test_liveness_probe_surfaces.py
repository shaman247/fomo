"""BL24 residual: the liveness probe's "dropper" crawl is chosen per surface.

A mixed website (w4545 Textile Arts Center: Instagram plus a class calendar) is
crawled by a Picnob bundle (`picnob_<handle>_<ts>.md`) and by a site crawl, and
neither surface sees the other's content. `_lp_latest` was keyed per website,
so a bundle newer than the site crawl became the dropper for every calendar
event, and an IG-only event could be nominated by it too. The real candidate
SQL runs through test_archival's SQLite shim.
"""
import unittest
from unittest.mock import patch

from test_archival import ArchivalTestBase, _ShimCursor, _days_ago, _days_ahead, _translate, db
import liveness_probe as probe

SITE_URL = 'https://campscui.active.com/orgs/Venue'


class _ProbeShimCursor(_ShimCursor):
    def execute(self, sql, params=()):
        self._cursor.execute(_translate(sql).replace('BINARY ', ''), tuple(params or ()))


class LivenessSurfaceTests(ArchivalTestBase):
    def setUp(self):
        super().setUp()
        self.cursor = _ProbeShimCursor(self.connection)
        self.connection.executescript('''
            ALTER TABLE events ADD COLUMN suppressed INTEGER DEFAULT 0;
            ALTER TABLE crawl_results ADD COLUMN merged_at TEXT;
            ALTER TABLE crawl_events ADD COLUMN url TEXT;
            ALTER TABLE websites ADD COLUMN skip_reenrichment INTEGER DEFAULT 0;
            CREATE TABLE event_urls (id INTEGER PRIMARY KEY, event_id INTEGER, url TEXT,
                                     sort_order INTEGER DEFAULT 0);
            CREATE TABLE event_liveness_probes (event_id INTEGER, probed_at TEXT);
        ''')
        self.add_website(1, base_url='https://www.instagram.com/venue1/')
        self.add_website_url(1, SITE_URL)

    def crawl(self, crawl_id, days_ago, listed=(), picnob=False):
        self.add_crawl(crawl_id, 1, days_ago)
        self.connection.execute(
            'UPDATE crawl_results SET filename = ?, merged_at = processed_at WHERE id = ?',
            (f'picnob_venue1_{crawl_id}.md' if picnob else 'venue_1.md', crawl_id))
        for event_id, url in listed:
            self._crawl_event_seq += 1
            ce = self._crawl_event_seq
            self.connection.execute('INSERT INTO crawl_events (id, crawl_result_id, name, url) '
                                    'VALUES (?, ?, ?, ?)', (ce, crawl_id, f'ce{ce}', url))
            self.connection.execute('INSERT INTO event_sources VALUES (?, ?)', (event_id, ce))

    def event(self, event_id, url):
        self.add_event(event_id, 1, future_days=10)
        self.connection.execute('INSERT INTO event_urls (event_id, url) VALUES (?, ?)',
                                (event_id, url))

    def nominated(self, ids):
        with patch.object(probe, 'MAX_EVENTS_PER_WEBSITE', 100):
            cands = probe.get_candidates(self.cursor, event_ids=ids)
        # Explicit ids bypass the grace-window test; apply it here.
        return {c['event_id']: c for c in cands
                if not c['still_listed'] and c['dropper_latest'] > c['last_seen']}

    def test_newer_bundle_is_not_the_dropper_for_calendar_events(self):
        cal = f'{SITE_URL}/class/1'
        self.event(100, cal)
        self.crawl(10, 5, [(100, cal)])
        self.crawl(11, 1, picnob=True)
        self.assertEqual(self.nominated([100]), {})

    def test_ig_only_event_on_a_mixed_site_is_never_nominated(self):
        post = 'https://www.instagram.com/p/abc/'
        self.event(101, 'https://venue.example/ig-flyer')
        self.crawl(9, 10, [(101, post)], picnob=True)
        self.crawl(10, 5)
        self.crawl(11, 1, picnob=True)
        self.assertEqual(self.nominated([101]), {})

    def test_calendar_event_dropped_by_the_site_crawl_is_still_nominated(self):
        cal = f'{SITE_URL}/class/2'
        self.event(102, cal)
        self.crawl(8, 20, [(102, cal)])
        self.crawl(10, 5)
        self.crawl(11, 1, picnob=True)
        nominated = self.nominated([102])
        self.assertEqual(list(nominated), [102])
        self.assertEqual(nominated[102]['dropper_latest'], _days_ago(5))

    def test_control_url_comes_from_the_site_surface(self):
        cal = f'{SITE_URL}/class/3'
        self.event(103, cal)
        self.event(104, 'https://venue.example/post')
        self.crawl(10, 5, [(103, cal)])
        self.crawl(11, 1, [(104, 'https://www.instagram.com/p/xyz/')], picnob=True)
        self.assertEqual(probe.get_control_urls(self.cursor, [1], set()), {1: cal})


if __name__ == '__main__':
    unittest.main()
