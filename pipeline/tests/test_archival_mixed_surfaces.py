"""BL24: a website crawled by BOTH the Picnob IG ingest and a site crawl.

w6019 No Booze Babes (IG base_url + Luma API row), w4545 Textile Arts Center
(IG + class calendar), w4682 Lit Society and w4982 Hudson River Maritime Museum
each get two kinds of crawl_results row: `picnob_<handle>_<ts>.md` from the
Instagram mirror and `<safe name>.md` from the site crawl. Neither surface can
see the other's content (instagram.com URLs are CrawlMode.SKIP), so an event
sourced by one surface must be judged only against that surface's crawls: for
"still listed", for the finished/horizon state and for the fresh-crawl count.
Before the partition, whichever surface finished last decided all three.
"""
import os
import unittest

from test_archival import ArchivalTestBase, _days_ahead, db
import test_archival_crawl_coverage as coverage_tests

SITE = 'website_1.md'
PICNOB = 'picnob_venue1_{}.md'


class MixedSurfaceArchivalTests(ArchivalTestBase):
    def mixed_site(self):
        self.add_website(1, base_url='https://www.instagram.com/venue1/')
        self.add_website_url(1, 'https://api.lu.ma/calendar/get-items?calendar_api_id=cal-x')

    def site_crawl(self, crawl_id, days_ago, event_ids=(), status='processed'):
        self.add_crawl(crawl_id, 1, days_ago, event_ids, status=status)
        self.connection.execute('UPDATE crawl_results SET filename = ? WHERE id = ?',
                                (SITE, crawl_id))

    def picnob_crawl(self, crawl_id, days_ago, event_ids=()):
        self.add_crawl(crawl_id, 1, days_ago, event_ids)
        self.connection.execute('UPDATE crawl_results SET filename = ? WHERE id = ?',
                                (PICNOB.format(crawl_id), crawl_id))

    def listed(self, crawl_id, start_days):
        """Another program the crawl listed, which sets that crawl's horizon."""
        self._crawl_event_seq += 1
        ce = self._crawl_event_seq
        self.connection.execute('INSERT INTO crawl_events VALUES (?, ?, ?)',
                                (ce, crawl_id, 'Other listed program'))
        self.connection.execute('INSERT INTO crawl_event_occurrences VALUES (?, ?, ?)',
                                (ce, _days_ahead(start_days), None))

    def archive(self):
        return db.archive_outdated_events(self.cursor, self.connection, 1)[0]

    # ── "still listed" is judged per surface ──

    def test_ig_event_still_in_latest_bundle_survives_newer_site_crawls(self):
        """The site crawl never contains IG posts; its recency must not unlist one."""
        self.mixed_site()
        self.add_event(100, 1, future_days=20)
        self.picnob_crawl(10, 20, [100])
        self.site_crawl(11, 10)
        self.site_crawl(12, 1)
        self.assertEqual(self.archive(), 0)

    def test_web_event_still_on_latest_site_crawl_survives_newer_bundles(self):
        """A monthly calendar still lists it; three weekly IG bundles do not."""
        self.mixed_site()
        self.add_event(100, 1, future_days=40)
        self.site_crawl(10, 20, [100])
        self.picnob_crawl(11, 12)
        self.picnob_crawl(12, 6)
        self.picnob_crawl(13, 1)
        self.assertEqual(self.archive(), 0)

    def test_web_event_dropped_by_the_site_crawl_still_archives(self):
        """The calendar's silence is evidence; the IG surface must not hide it."""
        self.mixed_site()
        self.add_event(100, 1, future_days=20)
        self.site_crawl(10, 60, [100])
        self.site_crawl(11, 30)
        self.site_crawl(12, 2)
        self.picnob_crawl(13, 1)
        self.assertEqual(self.archive(), 1)

    # ── the Picnob surface carries no absence evidence ──

    def test_ig_event_aged_out_of_the_grid_is_held_while_future(self):
        """Same 12-post-grid premise as an IG-only website."""
        self.mixed_site()
        self.add_event(100, 1, future_days=20)
        self.picnob_crawl(10, 60, [100])
        self.picnob_crawl(11, 30)
        self.picnob_crawl(12, 2)
        self.site_crawl(13, 1)
        self.assertEqual(self.archive(), 0)

    def test_ig_event_is_archived_once_its_dates_pass(self):
        self.mixed_site()
        self.add_event(100, 1)  # past occurrence only
        self.picnob_crawl(10, 60, [100])
        self.picnob_crawl(11, 30)
        self.site_crawl(12, 1)
        self.assertEqual(self.archive(), 1)

    def test_ig_exemption_still_capped_at_180_days(self):
        self.mixed_site()
        self.add_event(100, 1, future_days=200)
        self.picnob_crawl(10, 60, [100])
        self.picnob_crawl(11, 30)
        self.picnob_crawl(12, 2)
        self.assertEqual(self.archive(), 1)

    def test_event_on_both_surfaces_needs_both_to_drop_it(self):
        self.mixed_site()
        self.add_event(100, 1, future_days=20)
        self.site_crawl(10, 60, [100])
        self.picnob_crawl(11, 50, [100])
        self.site_crawl(12, 30)
        self.site_crawl(13, 2)
        self.assertEqual(self.archive(), 0)  # latest bundle still lists it
        self.picnob_crawl(14, 3)
        self.picnob_crawl(15, 1)
        # Both surfaces dropped it and the calendar's silence is real evidence.
        self.assertEqual(self.archive(), 1)

    # ── finished state and source horizon are per surface ──

    def test_site_horizon_is_not_replaced_by_an_empty_bundle(self):
        """An empty IG bundle has no horizon; it must not erase the calendar's."""
        self.mixed_site()
        self.add_event(100, 1, future_days=30)
        self.site_crawl(10, 60, [100])
        self.site_crawl(11, 30)
        self.site_crawl(12, 20)
        self.listed(12, 15)
        self.assertEqual(self.archive(), 0)  # beyond the calendar's horizon
        self.picnob_crawl(13, 1)
        self.assertEqual(self.archive(), 0)

    def test_failed_site_crawl_is_not_hidden_by_a_newer_bundle(self):
        """w6019 shape: the newest site attempt failed; a bundle succeeded after it."""
        self.mixed_site()
        self.add_event(100, 1, future_days=20)
        self.site_crawl(10, 60, [100])
        self.site_crawl(11, 30)
        self.site_crawl(12, 20)
        self.site_crawl(13, 3, status='failed')
        self.picnob_crawl(14, 1)
        self.assertEqual(self.archive(), 0)

    def test_failed_site_crawl_does_not_block_the_ig_surface(self):
        """A failed site attempt says nothing about IG posts. Past the 180-day
        exemption cap an IG event archives on the normal rules again, and the
        site crawl's failure must not pin it."""
        self.mixed_site()
        self.add_event(100, 1, future_days=200)
        self.picnob_crawl(10, 60, [100])
        self.picnob_crawl(11, 30)
        self.picnob_crawl(12, 2)
        self.site_crawl(13, 1, status='failed')
        self.assertEqual(self.archive(), 1)

    def test_horizon_trim_is_per_surface(self):
        self.mixed_site()
        self.site_crawl(10, 0)
        for n in range(14):
            for _ in range(25):
                self.listed(10, n)
        for n in (30, 45, 60, 70):
            self.listed(10, n)
        self.picnob_crawl(11, 0)
        self.listed(11, 70)
        db.build_archival_temps(self.cursor)
        self.cursor.execute(
            'SELECT picnob, last_start FROM _ws_crawl_state WHERE website_id = 1')
        rows = {int(p): str(d)[:10] for p, d in self.cursor.fetchall()}
        db.drop_archival_temps(self.cursor)
        self.assertEqual(rows, {0: _days_ahead(13), 1: _days_ahead(70)})

    # ── fresh-crawl count is per surface ──

    def test_bundles_do_not_count_as_fresh_site_crawls(self):
        self.mixed_site()
        self.add_event(100, 1, future_days=20)
        self.site_crawl(10, 30, [100])
        self.site_crawl(11, 20)
        self.picnob_crawl(12, 10)
        self.picnob_crawl(13, 5)
        self.picnob_crawl(14, 1)
        self.assertEqual(self.archive(), 0)  # one fresh site crawl only
        self.site_crawl(15, 0)
        self.assertEqual(self.archive(), 1)

    # ── single-surface websites are unchanged ──

    def test_ig_only_website_with_picnob_rows_keeps_its_exemption(self):
        self.add_website(1, base_url='https://www.instagram.com/venue1/')
        self.add_event(100, 1, future_days=20)
        self.picnob_crawl(10, 60, [100])
        self.picnob_crawl(11, 30)
        self.picnob_crawl(12, 2)
        self.assertEqual(self.archive(), 0)

    def test_calendar_only_website_archives_as_before(self):
        self.add_website(1, base_url='https://venue1.com')
        self.add_event(100, 1, future_days=20)
        self.site_crawl(10, 60, [100])
        self.site_crawl(11, 30)
        self.site_crawl(12, 2)
        self.assertEqual(self.archive(), 1)


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1', 'Opt in to isolated MariaDB fixtures')
class MariaMixedSurfaceArchivalTests(MixedSurfaceArchivalTests):
    setUp = coverage_tests.MariaCrawlCoverageTests.setUp


if __name__ == '__main__':
    unittest.main()
