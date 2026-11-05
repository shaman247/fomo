"""Future same-day slots whose time the same website has since replaced
(db.prune_superseded_times).

The merge only adds occurrences, so a slot the publisher re-timed keeps its
stale time beside the new one: Snug Harbor's Compost Processing Workday 105688
read 2pm, then 12:30pm, then 1pm, then 10am for its Nov 15 session and carried
all four. The rule must never fire on a multi-slot day: Merchant's House's
listing prints one start (6:30pm) for ghost tours that leave every half hour,
which a naive "newer crawls list only T2" rule read as a retime (refuted
2026-10-07). Runs the real SQL through test_archival's SQLite shim.
"""
import os
import unittest

from test_archival import ArchivalTestBase, _days_ago, _days_ahead, db
import test_archival_crawl_coverage as coverage_tests

SITE, OTHER = 1, 2
EVENT = 100
GHOST_SLOTS = ('6:30pm', '7pm', '7:30pm', '8pm', '8:30pm', '9pm')


class SupersededTimeTests(ArchivalTestBase):
    def setUp(self):
        super().setUp()
        self.extend_schema()

    def extend_schema(self):
        self.connection.execute('ALTER TABLE events ADD COLUMN suppressed INTEGER DEFAULT 0')
        self.connection.execute('ALTER TABLE crawl_events ADD COLUMN created_at TEXT')
        self.connection.execute('ALTER TABLE crawl_event_occurrences ADD COLUMN start_time TEXT')
        self.connection.execute('ALTER TABLE event_occurrences ADD COLUMN start_time TEXT')
        self.connection.execute('ALTER TABLE event_occurrences ADD COLUMN end_time TEXT')
        self.add_website(SITE)
        self.add_website(OTHER)
        self.connection.execute(
            "INSERT INTO events (id, name, website_id, archived) VALUES (?, 'Workday', ?, 0)",
            (EVENT, SITE))

    def slots(self, *pairs, end_day=None):
        """Event occurrences: (day, time) pairs; `end_day` makes them multi-day."""
        for day, time in pairs:
            self.connection.execute(
                'INSERT INTO event_occurrences (event_id, start_date, start_time, end_date) '
                'VALUES (?, ?, ?, ?)',
                (EVENT, _days_ahead(day), time,
                 _days_ahead(end_day) if end_day is not None else None))

    def crawl(self, crawl_id, days_ago, listed, website_id=SITE, status='processed',
              filename=None, spans=()):
        """A crawl of `website_id` whose crawl_event for EVENT lists `listed`
        [(day, time)]; `listed=None` means the crawl does not list EVENT."""
        self.add_crawl(crawl_id, website_id, days_ago, status=status)
        if filename:
            self.connection.execute('UPDATE crawl_results SET filename = ? WHERE id = ?',
                                    (filename, crawl_id))
        if listed is None:
            return
        self._crawl_event_seq += 1
        ce = self._crawl_event_seq
        self.connection.execute(
            'INSERT INTO crawl_events (id, crawl_result_id, name, created_at) VALUES (?, ?, ?, ?)',
            (ce, crawl_id, 'Workday', _days_ago(days_ago)))
        self.connection.execute('INSERT INTO event_sources (event_id, crawl_event_id) VALUES (?, ?)',
                                (EVENT, ce))
        for day, time in listed:
            self.connection.execute(
                'INSERT INTO crawl_event_occurrences (crawl_event_id, start_date, start_time, end_date) '
                'VALUES (?, ?, ?, NULL)', (ce, _days_ahead(day), time))
        for start, end in spans:
            self.connection.execute(
                'INSERT INTO crawl_event_occurrences (crawl_event_id, start_date, start_time, end_date) '
                'VALUES (?, ?, ?, ?)', (ce, _days_ahead(start), None, _days_ahead(end)))

    def prune(self, website_ids=(SITE,), **kwargs):
        return db.prune_superseded_times(self.cursor, self.connection, list(website_ids),
                                         **kwargs)[0]

    def remaining(self, day=20):
        rows = self.connection.execute(
            'SELECT start_time FROM event_occurrences WHERE event_id = ? AND start_date = ? '
            'ORDER BY start_time', (EVENT, _days_ahead(day))).fetchall()
        return sorted(r[0] for r in rows)

    def retimed(self, old='2pm', new='12pm', old_ages=(40, 30), new_ages=(10, 2), day=20):
        """Swiss Institute 307503: the Sat slot moved from 2pm to 12pm."""
        self.slots((day, old), (day, new))
        for i, age in enumerate(old_ages):
            self.crawl(10 + i, age, [(day, old)])
        for i, age in enumerate(new_ages):
            self.crawl(20 + i, age, [(day, new)])

    # ── retired ──
    def test_a_retimed_slot_is_retired_and_the_new_time_kept(self):
        self.retimed()
        self.assertEqual(self.prune(), 1)
        self.assertEqual(self.remaining(), ['12pm'])

    def test_a_chain_of_retimes_keeps_only_the_latest_time(self):
        """Snug Harbor 105688: 10am, 2pm, 12:30pm, 1pm, then 10am again."""
        self.slots((20, '10am'), (20, '2pm'), (20, '12:30pm'), (20, '1pm'))
        for crawl_id, age, time in ((10, 90, '10am'), (11, 70, '2pm'), (12, 60, '12:30pm'),
                                    (13, 40, '1pm'), (14, 35, '10am'), (15, 20, '10am'),
                                    (16, 5, '10am')):
            self.crawl(crawl_id, age, [(20, time)])
        self.assertEqual(self.prune(), 3)
        self.assertEqual(self.remaining(), ['10am'])

    def test_every_retimed_day_of_a_series_is_retired(self):
        """Otto's Alice's House: every Thursday moved 9pm -> 6pm."""
        self.slots((7, '9pm'), (7, '6pm'), (14, '9pm'), (14, '6pm'))
        self.crawl(10, 40, [(7, '9pm'), (14, '9pm')])
        self.crawl(20, 10, [(7, '6pm'), (14, '6pm')])
        self.crawl(21, 2, [(7, '6pm'), (14, '6pm')])
        self.assertEqual(self.prune(), 2)
        self.assertEqual(self.remaining(7), ['6pm'])
        self.assertEqual(self.remaining(14), ['6pm'])

    def test_a_second_website_listing_only_the_new_time_does_not_block(self):
        self.retimed()
        self.crawl(30, 5, [(20, '12pm')], website_id=OTHER)
        self.assertEqual(self.prune(), 1)

    def test_time_spellings_are_compared_canonically(self):
        self.retimed(old='2:00 PM', new='12pm')
        self.assertEqual(self.prune(), 1)
        self.assertEqual(self.remaining(), ['12pm'])

    # ── multi-slot days: never ──
    def ghost_tours(self, multi_slot_website=SITE):
        """Merchant's House Candlelight Ghost Tours (205975, Oct 2026): tours
        leave every half hour 6:30-9pm. Detail crawls listed all six slots; the
        listing crawls before and after print 6:30pm only."""
        days = (20, 21)
        self.slots(*[(d, t) for d in days for t in GHOST_SLOTS])
        self.crawl(10, 95, [(d, '6:30pm') for d in days])
        self.crawl(11, 70, [(d, t) for d in days for t in GHOST_SLOTS],
                   website_id=multi_slot_website)
        self.crawl(12, 63, [(d, t) for d in days for t in GHOST_SLOTS],
                   website_id=multi_slot_website)
        for crawl_id, age in ((13, 52), (14, 43), (15, 34), (16, 20), (17, 2)):
            self.crawl(crawl_id, age, [(d, '6:30pm') for d in days])

    def test_merchants_house_one_printed_start_never_retires_the_other_slots(self):
        self.ghost_tours()
        self.assertEqual(self.prune(), 0)
        self.assertEqual(self.remaining(), sorted(GHOST_SLOTS))

    def test_a_multi_slot_listing_from_another_website_also_protects_the_slots(self):
        self.ghost_tours(multi_slot_website=OTHER)
        self.assertEqual(self.prune(), 0)

    def test_a_latest_crawl_listing_two_times_on_the_day_retires_nothing(self):
        """Merchant's House A Christmas Carol 253486: 6pm and 8pm on Nov 28."""
        self.slots((20, '6pm'), (20, '8pm'), (20, '7pm'))
        self.crawl(10, 40, [(20, '7pm')])
        self.crawl(20, 10, [(20, '6pm'), (20, '8pm')])
        self.crawl(21, 2, [(20, '6pm'), (20, '8pm')])
        self.assertEqual(self.prune(), 0)

    def test_two_times_on_one_day_anywhere_in_history_protects_the_event(self):
        """A past day with two shows marks the event as multi-slot."""
        self.retimed()
        self.crawl(5, 60, [(-30, '7pm'), (-30, '9pm')])  # older id: not the latest crawl
        self.assertEqual(self.prune(), 0)

    # ── evidence guards (mirroring prune_superseded_dates) ──
    def test_one_fresh_crawl_is_not_enough(self):
        self.retimed(new_ages=(2,))
        self.assertEqual(self.prune(), 0)

    def test_old_support_inside_the_grace_period_is_kept(self):
        self.retimed(old_ages=(12, 10), new_ages=(5, 1))
        self.assertEqual(self.prune(), 0)

    def test_old_time_backed_by_a_second_website_is_kept(self):
        self.retimed()
        self.crawl(30, 40, [(20, '2pm')], website_id=OTHER)
        self.assertEqual(self.prune(), 0)
        self.assertEqual(self.prune(website_ids=(SITE, OTHER)), 0)

    def test_picnob_support_keeps_the_old_time(self):
        self.retimed()
        self.crawl(30, 40, [(20, '2pm')], filename='picnob_venue1_1.md')
        self.assertEqual(self.prune(), 0)

    def test_a_time_with_no_crawl_support_is_kept(self):
        """Reviewed repairs have no crawl_event behind them."""
        self.slots((20, '12pm'), (20, '4pm'))
        self.crawl(20, 10, [(20, '12pm')])
        self.crawl(21, 2, [(20, '12pm')])
        self.assertEqual(self.prune(), 0)

    def test_absence_free_websites_are_skipped(self):
        self.connection.execute('UPDATE websites SET rotating_listing = 1 WHERE id = ?', (SITE,))
        self.retimed()
        self.assertEqual(self.prune(), 0)

    def test_only_websites_this_merge_reached_are_pruned(self):
        self.retimed()
        self.assertEqual(self.prune(website_ids=(OTHER,)), 0)
        self.assertEqual(self.prune(website_ids=()), 0)

    def test_latest_crawl_must_list_the_day(self):
        """Snug Harbor 86143: the latest crawl moved the tour to another day."""
        self.retimed()
        self.crawl(40, 0, [(19, '10am')])
        self.assertEqual(self.prune(), 0)

    def test_latest_crawl_listing_the_day_untimed_retires_nothing(self):
        self.retimed()
        self.crawl(40, 0, [(20, None)])
        self.assertEqual(self.prune(), 0)

    def test_unfinished_latest_attempt_blocks(self):
        self.retimed()
        self.crawl(40, 0, None, status='failed')
        self.assertEqual(self.prune(), 0)

    def test_a_flip_back_to_the_old_time_retires_nothing(self):
        """Newest support is then the latest crawl: no fresh crawls exist."""
        self.retimed(new_ages=(10, 5))
        self.crawl(30, 1, [(20, '2pm')])
        self.assertEqual(self.prune(), 0)

    def test_an_untimed_row_on_the_day_leaves_the_day_alone(self):
        self.retimed()
        self.slots((20, None))
        self.assertEqual(self.prune(), 0)

    def test_an_unparseable_time_leaves_the_day_alone(self):
        self.retimed(old='7:00', new='7pm')
        self.assertEqual(self.prune(), 0)

    def test_a_multi_day_crawl_row_covering_the_day_leaves_it_alone(self):
        self.retimed()
        self.crawl(30, 3, [(20, '12pm')], spans=[(19, 21)])
        self.assertEqual(self.prune(), 0)

    def test_suppressed_events_are_untouched(self):
        self.retimed()
        self.connection.execute('UPDATE events SET suppressed = 1 WHERE id = ?', (EVENT,))
        self.assertEqual(self.prune(), 0)

    # ── reporting ──
    def test_dry_run_reports_without_deleting(self):
        self.retimed()
        count, rows = db.prune_superseded_times(self.cursor, self.connection, [SITE],
                                                dry_run=True)
        self.assertEqual(count, 1)
        self.assertEqual([(r[0], str(r[2]), r[3]) for r in rows],
                         [(EVENT, _days_ahead(20), '2pm')])
        self.assertEqual(self.remaining(), ['12pm', '2pm'])

    def test_deletes_are_audit_logged(self):
        self.retimed()
        logged = []

        class Logger:
            def log_delete(self, table, record_id, data):
                logged.append((table, data['start_date'], data['start_time']))
        count, _ = db.prune_superseded_times(self.cursor, self.connection, [SITE],
                                             edit_logger=Logger())
        self.assertEqual(count, 1)
        self.assertEqual(logged, [('event_occurrences', _days_ahead(20), '2pm')])


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1', 'Opt in to isolated MariaDB fixtures')
class MariaSupersededTimeTests(SupersededTimeTests):
    def setUp(self):
        coverage_tests.MariaCrawlCoverageTests.setUp(self)
        self.extend_schema()


if __name__ == '__main__':
    unittest.main()
