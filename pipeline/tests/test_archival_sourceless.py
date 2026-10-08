"""Visible events with NO event_sources rows (db.archive_sourceless_events).

A crawl_events purge cascades every event_sources row of an event away
(CLAUDE.md "Crawler Debugging"). Both archival passes start from an event's
sources, so such an event could never be archived: Film-Maker's Co-op E238043
kept an invented 2026-11-30 date live after its five bogus crawl_events were
purged (2026-10-07). Runs the real SQL through test_archival's SQLite shim.
"""
import os
import unittest

from test_archival import ArchivalTestBase, _days_ago, _days_ahead, db
import test_archival_crawl_coverage as coverage_tests

SITE = 1


class SourcelessArchivalTests(ArchivalTestBase):
    def setUp(self):
        super().setUp()
        self.extend_schema()

    def extend_schema(self):
        self.connection.execute('ALTER TABLE events ADD COLUMN suppressed INTEGER DEFAULT 0')
        self.connection.execute('ALTER TABLE events ADD COLUMN created_at TEXT')
        self.add_website(SITE)

    def sourceless(self, event_id, future_days=None, created_days_ago=60, suppressed=False,
                   website_id=SITE, name=None):
        self.add_event(event_id, website_id, future_days=future_days)
        self.connection.execute(
            'UPDATE events SET created_at = ?, suppressed = ?, name = COALESCE(?, name) WHERE id = ?',
            (_days_ago(created_days_ago), int(suppressed), name, event_id))

    def site_crawls(self, *days_ago, status='processed', listed_days=None):
        """Site crawls of SITE; each lists one OTHER program to set its horizon."""
        for i, age in enumerate(days_ago):
            crawl_id = 50 + i
            self.add_crawl(crawl_id, SITE, age, status=status)
            if listed_days is not None:
                self._crawl_event_seq += 1
                ce = self._crawl_event_seq
                self.connection.execute('INSERT INTO crawl_events VALUES (?, ?, ?)',
                                        (ce, crawl_id, 'Other program'))
                self.connection.execute('INSERT INTO crawl_event_occurrences VALUES (?, ?, ?)',
                                        (ce, _days_ahead(listed_days), None))

    def sweep(self, website_ids=(SITE,)):
        return db.archive_sourceless_events(self.cursor, self.connection,
                                            website_ids=list(website_ids))

    # ── past-only: nothing left to show ──

    def test_past_only_sourceless_event_is_archived_without_any_crawl(self):
        self.sourceless(100)
        self.assertEqual(self.sweep(website_ids=()), (1, []))
        self.assertEqual(self.archived_ids(), [100])

    def test_suppressed_dedupe_losers_are_left_to_the_dedupe_workflow(self):
        self.sourceless(100, suppressed=True)
        self.sourceless(101, future_days=20, suppressed=True)
        self.site_crawls(30, 10)
        self.assertEqual(self.sweep()[0], 0)

    def test_sourced_events_are_not_this_sweeps_business(self):
        self.add_event(100, SITE)
        self.add_crawl(10, SITE, 40, [100])
        self.add_crawl(11, SITE, 1)
        self.assertEqual(self.sweep()[0], 0)

    # ── future dates: only on the merged website's own evidence ──

    def test_purged_event_is_archived_once_its_website_crawls_without_it(self):
        """The FMC E238043 shape: sources purged, the site keeps crawling."""
        self.sourceless(100, future_days=50)
        self.site_crawls(30, 10)
        archived, upcoming = self.sweep()
        self.assertEqual(archived, 1)
        self.assertEqual([u[0] for u in upcoming], [100])

    def test_future_event_waits_until_its_website_is_merged(self):
        self.sourceless(100, future_days=50)
        self.site_crawls(30, 10)
        self.assertEqual(self.sweep(website_ids=(2,))[0], 0)
        self.assertEqual(self.sweep(website_ids=())[0], 0)

    def test_never_crawled_website_keeps_it_until_the_dates_pass(self):
        """E99969 Gender Experts Party at Metropolitan Bar: no crawl_results at all."""
        self.sourceless(100, future_days=20)
        self.assertEqual(self.sweep()[0], 0)

    def test_recently_created_event_gets_the_grace(self):
        self.sourceless(100, future_days=50, created_days_ago=5)
        self.site_crawls(4, 1)
        self.assertEqual(self.sweep()[0], 0)

    def test_needs_two_finished_crawls_since_creation(self):
        self.sourceless(100, future_days=50, created_days_ago=20)
        self.site_crawls(30, 10)  # only the second is after creation
        self.assertEqual(self.sweep()[0], 0)

    def test_unfinished_latest_attempt_blocks(self):
        self.sourceless(100, future_days=50)
        self.site_crawls(30, 10)
        self.add_crawl(60, SITE, 0, status='failed')
        self.assertEqual(self.sweep()[0], 0)

    def test_short_horizon_cannot_speak_for_a_far_event(self):
        self.sourceless(100, future_days=60)
        self.site_crawls(30, 10, listed_days=7)
        self.assertEqual(self.sweep()[0], 0)
        self.connection.execute('UPDATE crawl_event_occurrences SET start_date = ?',
                                (_days_ahead(70),))
        self.assertEqual(self.sweep()[0], 1)

    def test_instagram_only_and_mixed_websites_hold_until_past(self):
        self.add_website(2, base_url='https://www.instagram.com/venue2/')
        self.sourceless(100, future_days=20, website_id=2)
        self.add_crawl(20, 2, 30)
        self.add_crawl(21, 2, 10)
        self.assertEqual(self.sweep(website_ids=(2,))[0], 0)
        # Mixed: a site crawl plus a Picnob bundle. The sourceless row may be an
        # IG post, which the site crawl can never list.
        self.sourceless(101, future_days=20)
        self.site_crawls(30, 10)
        self.add_crawl(61, SITE, 5)
        self.connection.execute(
            "UPDATE crawl_results SET filename = 'picnob_venue1_1.md' WHERE id = 61")
        self.assertEqual(self.sweep()[0], 0)

    def test_recent_start_too_future_rejection_holds_it(self):
        self.sourceless(100, future_days=50, name='Winter Gala')
        self.site_crawls(30, 10)
        self.connection.execute(
            "INSERT INTO extraction_rejections (website_id, rejection_type, event_name, created_at) "
            "VALUES (?, 'start_too_future', 'Winter Gala', ?)", (SITE, _days_ago(2)))
        self.assertEqual(self.sweep()[0], 0)


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1', 'Opt in to isolated MariaDB fixtures')
class MariaSourcelessArchivalTests(SourcelessArchivalTests):
    def setUp(self):
        coverage_tests.MariaCrawlCoverageTests.setUp(self)
        self.extend_schema()


if __name__ == '__main__':
    unittest.main()
