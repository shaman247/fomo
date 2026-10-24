"""BL13 dead-keeper tripwire: log a hidden row without a redirect that takes
sources an archived visible row shares.

BL19 (2026-10-23) found 34 suppressed dedupe losers with no
`event_merge_redirects` row still catching fresh crawl_events after their
visible keeper was archived (renamed, delisted or re-pinned): the suppressed
fallback wins because no visible candidate qualifies, so a live program shows
nowhere. 12 were real public programs. The merger now logs `DEAD-KEEPER` for
such a landing; it changes no routing.

The helper tests run on connection-local TEMPORARY tables (FOMO_TEST_TEMP_DB=1);
no production rows are read or changed. The wiring tests drive the whole
`merge_crawl_events` path over the BL14 fake cursor.
Run: cd pipeline/tests && PYTHONPATH=..:../.. FOMO_TEST_TEMP_DB=1 ../../venv/bin/python test_bl13_dead_keeper_tripwire.py
"""
import contextlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import merger
import test_bl14_redirect_routing as bl14

URL = 'https://example.org/events/classic-mansion-tour-2026'


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1',
                     'Opt in to connection-local MariaDB tests with FOMO_TEST_TEMP_DB=1')
class ReportDeadKeepersDbTests(unittest.TestCase):
    SCHEMAS = {
        'events': ('id INT PRIMARY KEY, name VARCHAR(255), archived TINYINT DEFAULT 0, '
                   'suppressed TINYINT DEFAULT 0'),
        'event_sources': ('id INT AUTO_INCREMENT PRIMARY KEY, event_id INT, '
                          'crawl_event_id INT'),
        'event_urls': 'id INT AUTO_INCREMENT PRIMARY KEY, event_id INT, url VARCHAR(1000)',
    }

    def setUp(self):
        from db import create_connection
        self.conn = create_connection()
        self.assertIsNotNone(self.conn)
        self.addCleanup(self.conn.close)
        self.cur = self.conn.cursor()
        for table, schema in self.SCHEMAS.items():
            self.cur.execute(f'CREATE TEMPORARY TABLE {table} ({schema})')
        # 85140: the live carrier shape (Classic Mansion Tour 2026, w1675):
        # hidden, keeper 43678 archived.
        self.cur.execute("INSERT INTO events (id, name, archived, suppressed) VALUES "
                         "(85140, 'Classic Mansion Tour 2026', 0, 1), "
                         "(43678, 'Classic Mansion Tour 2026', 1, 0), "
                         "(50000, 'Other archived', 1, 0), "
                         "(50001, 'Suppressed archived', 1, 1), "
                         "(50002, 'Visible keeper', 0, 0)")

    def link(self, event_id, ce_id):
        self.cur.execute('INSERT INTO event_sources (event_id, crawl_event_id) VALUES (%s, %s)',
                         (event_id, ce_id))

    def url(self, event_id, url):
        self.cur.execute('INSERT INTO event_urls (event_id, url) VALUES (%s, %s)', (event_id, url))

    def run_report(self, landings=None, listing=(), counts=None):
        landings = landings or {85140: {'name': 'Classic Mansion Tour 2026',
                                        'sources': [(900, 1675)]}}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            report = merger.report_dead_keepers(self.cur, landings, set(listing), counts or {})
        return report, out.getvalue()

    def test_shared_source_with_archived_keeper_is_logged(self):
        self.link(85140, 101)
        self.link(43678, 101)
        report, out = self.run_report()
        self.assertEqual(report, [(85140, [(43678, 'Classic Mansion Tour 2026', 'source')])])
        self.assertIn('DEAD-KEEPER e85140 "Classic Mansion Tour 2026" (suppressed, no redirect) '
                      'took ce900; archived keeper(s): e43678 "Classic Mansion Tour 2026" '
                      '(source)', out)

    def test_shared_event_specific_url_is_logged(self):
        self.url(85140, URL)
        self.url(43678, URL)
        report, _ = self.run_report()
        self.assertEqual(report, [(85140, [(43678, 'Classic Mansion Tour 2026', 'url')])])

    def test_both_kinds_are_reported_together(self):
        self.link(85140, 101)
        self.link(43678, 101)
        self.url(85140, URL)
        self.url(43678, URL)
        report, _ = self.run_report()
        self.assertEqual(report[0][1], [(43678, 'Classic Mansion Tour 2026', 'source+url')])

    def test_listing_url_does_not_count(self):
        self.url(85140, URL)
        self.url(43678, URL)
        key = merger.normalize_url_for_identity(URL)
        self.assertEqual(self.run_report(listing={(1675, key)})[0], [])
        # Nor a URL that carries too many distinct names on its website.
        counts = {(1675, key): merger.URL_IDENTITY_MAX_DISTINCT_NAMES + 1}
        self.assertEqual(self.run_report(counts=counts)[0], [])

    def test_url_carrying_too_many_names_is_a_listing(self):
        # A branch calendar shared by unrelated programs, its holders archived
        # (QPL "Homework Help" vs "Flamenco Vivo ..." in the 2026-10-24 replay).
        self.url(85140, URL)
        self.url(43678, URL)
        self.url(50000, URL)
        self.url(50001, URL)  # a hidden holder's name counts too
        self.cur.execute("UPDATE events SET name = 'Flamenco Vivo' WHERE id = 50000")
        self.assertEqual(self.run_report()[0], [])
        # Two names (the carrier's and one other) are still an event page.
        self.cur.execute("UPDATE events SET name = 'Classic Mansion Tour 2026' WHERE id = 50000")
        report, _ = self.run_report()
        self.assertEqual([p[0] for p in report[0][1]], [43678, 50000])

    def test_visible_or_suppressed_partners_are_not_dead_keepers(self):
        for partner in (50001, 50002):
            self.link(partner, 101)
            self.url(partner, URL)
        self.link(85140, 101)
        self.url(85140, URL)
        report, out = self.run_report()
        self.assertEqual(report, [])
        self.assertEqual(out, '')

    def test_unshared_carrier_is_quiet(self):
        self.link(85140, 101)
        self.link(50000, 102)
        self.assertEqual(self.run_report(), ([], ''))

    def test_no_landings_runs_no_query(self):
        with patch.object(self.cur, 'execute') as execute:
            self.assertEqual(merger.report_dead_keepers(self.cur, {}, set(), {}), [])
        execute.assert_not_called()

    def test_writes_nothing(self):
        self.link(85140, 101)
        self.link(43678, 101)
        self.run_report()
        self.cur.execute('SELECT id, archived, suppressed FROM events ORDER BY id')
        self.assertEqual(self.cur.fetchall(), [(43678, 1, 0), (50000, 1, 0), (50001, 1, 1),
                                               (50002, 0, 0), (85140, 0, 1)])


class DeadKeeperWiringTests(unittest.TestCase):
    """Which merge landings reach the tripwire (BL14 fake-cursor harness)."""

    def landings(self, **kwargs):
        harness = bl14.RedirectRoutingMergeTests('test_cycle_declines')
        with patch.object(merger, 'report_dead_keepers', return_value=[]) as report:
            links, _, _ = harness.run_merge(**kwargs)
        report.assert_called_once()
        return links, report.call_args.args[1]

    def test_plain_suppression_without_a_redirect_is_reported(self):
        links, landings = self.landings(redirects=())
        self.assertEqual(links, [(bl14.DUP, bl14.CE)])  # routing unchanged
        self.assertEqual(landings, {bl14.DUP: {'name': bl14.DUP_NAME,
                                               'sources': [(bl14.CE, 3)]}})

    def test_redirected_duplicate_is_not_reported(self):
        links, landings = self.landings()
        self.assertEqual(links, [(bl14.SURVIVOR, bl14.CE)])
        self.assertEqual(landings, {})
        # A redirect that declines (suppressed survivor) still has a decision.
        _, landings = self.landings(survivor_state={bl14.SURVIVOR: (1, 0, bl14.VENUE,
                                                                    bl14.SURVIVOR_NAME)})
        self.assertEqual(landings, {})

    def test_reviewed_owner_and_reviewed_match_are_not_reported(self):
        _, landings = self.landings(redirects=(), reviewed_owners=(bl14.DUP,))
        self.assertEqual(landings, {})
        _, landings = self.landings(redirects=(), reviewed_match=bl14.DUP)
        self.assertEqual(landings, {})


if __name__ == '__main__':
    unittest.main()
