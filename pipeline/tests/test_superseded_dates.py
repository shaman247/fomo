"""Future dates only a superseded crawl ever listed (db.prune_superseded_dates).

The merge only adds occurrences, so when a website moves to a better source the
dates the old one invented survive: Laugh Tour w1367's homepage synthesized
weekly shows on Thanksgiving, Christmas and New Year's Day that the Ticket
Tailor feed replacing it never listed (16 dates removed by hand, 2026-10-07).
Runs the real SQL through test_archival's SQLite shim.
"""
import os
import unittest

from test_archival import ArchivalTestBase, _days_ago, _days_ahead, db
import test_archival_crawl_coverage as coverage_tests

SITE, OTHER = 1, 2
EVENT = 100


class SupersededDateTests(ArchivalTestBase):
    def setUp(self):
        super().setUp()
        self.extend_schema()

    def extend_schema(self):
        self.connection.execute('ALTER TABLE events ADD COLUMN suppressed INTEGER DEFAULT 0')
        self.connection.execute('ALTER TABLE crawl_events ADD COLUMN created_at TEXT')
        self.add_website(SITE)
        self.add_website(OTHER)
        self.connection.execute(
            "INSERT INTO events (id, name, website_id, archived) VALUES (?, 'Comedy Show', ?, 0)",
            (EVENT, SITE))

    def dates(self, *days):
        for d in days:
            self.connection.execute(
                'INSERT INTO event_occurrences (event_id, start_date, end_date) VALUES (?, ?, NULL)',
                (EVENT, _days_ahead(d)))

    def crawl(self, crawl_id, days_ago, listed_days, website_id=SITE, status='processed',
              filename=None, spans=()):
        """A crawl of `website_id` whose crawl_event for EVENT lists `listed_days`."""
        self.add_crawl(crawl_id, website_id, days_ago, status=status)
        if filename:
            self.connection.execute('UPDATE crawl_results SET filename = ? WHERE id = ?',
                                    (filename, crawl_id))
        if listed_days is None:
            return
        self._crawl_event_seq += 1
        ce = self._crawl_event_seq
        self.connection.execute(
            'INSERT INTO crawl_events (id, crawl_result_id, name, created_at) VALUES (?, ?, ?, ?)',
            (ce, crawl_id, 'Comedy Show', _days_ago(days_ago)))
        self.connection.execute('INSERT INTO event_sources (event_id, crawl_event_id) VALUES (?, ?)',
                                (EVENT, ce))
        for d in listed_days:
            self.connection.execute('INSERT INTO crawl_event_occurrences VALUES (?, ?, ?)',
                                    (ce, _days_ahead(d), None))
        for start, end in spans:
            self.connection.execute('INSERT INTO crawl_event_occurrences VALUES (?, ?, ?)',
                                    (ce, _days_ahead(start), _days_ahead(end)))

    def prune(self, website_ids=(SITE,)):
        return db.prune_superseded_dates(self.cursor, self.connection, list(website_ids))[0]

    def remaining(self):
        rows = self.connection.execute(
            'SELECT start_date FROM event_occurrences WHERE event_id = ? ORDER BY start_date',
            (EVENT,)).fetchall()
        return [r[0] for r in rows]

    def laugh_tour(self, new_listing=(7, 14, 28, 35), fresh=(10, 2)):
        """Old homepage crawls list day 21 (the holiday); the new feed never does."""
        self.dates(7, 14, 21, 28, 35)
        self.crawl(10, 40, [7, 14, 21, 28, 35])
        self.crawl(11, 30, [7, 14, 21, 28, 35])
        for i, age in enumerate(fresh):
            self.crawl(20 + i, age, list(new_listing))

    def test_source_switch_drops_the_date_the_new_feed_never_lists(self):
        self.laugh_tour()
        self.assertEqual(self.prune(), 1)
        self.assertNotIn(_days_ahead(21), self.remaining())
        self.assertEqual(len(self.remaining()), 4)

    def test_listing_that_shows_only_the_next_date_supersedes_nothing(self):
        self.laugh_tour(new_listing=(7,))
        self.assertEqual(self.prune(), 0)

    def test_first_and_last_date_alone_do_not_bracket_the_middle(self):
        self.laugh_tour(new_listing=(7, 35))
        self.assertEqual(self.prune(), 0)

    def test_one_fresh_crawl_is_not_enough(self):
        self.laugh_tour(fresh=(2,))
        self.assertEqual(self.prune(), 0)

    def test_support_inside_the_grace_period_is_kept(self):
        self.dates(7, 14, 21, 28)
        self.crawl(10, 5, [7, 14, 21, 28])
        self.crawl(20, 3, [7, 14, 28])
        self.crawl(21, 1, [7, 14, 28])
        self.assertEqual(self.prune(), 0)

    def test_support_from_a_second_website_keeps_the_date(self):
        self.laugh_tour()
        self.crawl(30, 40, [21], website_id=OTHER)
        self.assertEqual(self.prune(), 0)

    def test_picnob_support_keeps_the_date(self):
        self.laugh_tour()
        self.crawl(30, 40, [21], filename='picnob_venue1_1.md')
        self.assertEqual(self.prune(), 0)

    def test_dates_without_crawl_support_are_kept(self):
        """Reviewed repairs and envelopes have no crawl_event behind them."""
        self.laugh_tour()
        self.dates(17)
        self.assertEqual(self.prune(), 1)
        self.assertIn(_days_ahead(17), self.remaining())

    def test_only_websites_this_merge_reached_are_pruned(self):
        self.laugh_tour()
        self.assertEqual(self.prune(website_ids=(OTHER,)), 0)
        self.assertEqual(self.prune(website_ids=()), 0)

    def test_unfinished_latest_attempt_blocks(self):
        self.laugh_tour()
        self.crawl(40, 0, None, status='failed')
        self.assertEqual(self.prune(), 0)

    def test_event_missing_from_the_latest_crawl_is_archivals_job(self):
        self.laugh_tour()
        self.crawl(40, 0, None)
        self.assertEqual(self.prune(), 0)

    def test_absence_free_websites_are_skipped(self):
        self.connection.execute('UPDATE websites SET rotating_listing = 1 WHERE id = ?', (SITE,))
        self.laugh_tour()
        self.assertEqual(self.prune(), 0)

    def test_a_multi_day_row_covering_the_date_supports_it(self):
        self.dates(7, 14, 21, 28, 35)
        self.crawl(10, 40, [7, 14, 21, 28, 35])
        self.crawl(20, 10, [7, 14, 28, 35], spans=[(20, 22)])
        self.crawl(21, 2, [7, 14, 28, 35], spans=[(20, 22)])
        self.assertEqual(self.prune(), 0)

    def test_suppressed_events_are_untouched(self):
        self.laugh_tour()
        self.connection.execute('UPDATE events SET suppressed = 1 WHERE id = ?', (EVENT,))
        self.assertEqual(self.prune(), 0)

    def test_deletes_are_audit_logged(self):
        self.connection.execute('ALTER TABLE event_occurrences ADD COLUMN start_time TEXT')
        self.connection.execute('ALTER TABLE event_occurrences ADD COLUMN end_time TEXT')
        self.laugh_tour()
        logged = []

        class Logger:
            def log_delete(self, table, record_id, data):
                logged.append((table, data['start_date']))
        count, rows = db.prune_superseded_dates(self.cursor, self.connection, [SITE],
                                                edit_logger=Logger())
        self.assertEqual(count, 1)
        self.assertEqual(logged, [('event_occurrences', _days_ahead(21))])
        self.assertEqual([(r[0], str(r[2])) for r in rows], [(EVENT, _days_ahead(21))])


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1', 'Opt in to isolated MariaDB fixtures')
class MariaSupersededDateTests(SupersededDateTests):
    def setUp(self):
        coverage_tests.MariaCrawlCoverageTests.setUp(self)
        self.extend_schema()


if __name__ == '__main__':
    unittest.main()
