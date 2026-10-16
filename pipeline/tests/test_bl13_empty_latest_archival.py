"""BL13 (a): a website whose latest crawl is a clean EMPTY listing is reached by archival.

The merge tail used to reach a website only through crawl_events this merge
linked from its latest crawl, so a site whose latest crawl listed zero events
never got an archival pass and the events only its older crawls carried stayed
live (DUMBO Archway & Plaza w3966, Filthy Diamond, five AMC houses). The fix
hands such websites to the same `archive_outdated_events` guards, but only for
a clean empty crawl: processed, no error, no crawl_events, and content that is
not a challenge / soft 404 / FOMO-CRAWL-INCOMPLETE capture. An event whose name
the empty crawl still prints is held (an extraction miss, not absence).

Runs the real SQL through test_archival's SQLite shim.
"""
import unittest
from unittest.mock import patch

from test_archival import ArchivalTestBase, _days_ago, db
import merger

SITE = 1
PAGE = ('# Upcoming at the venue\n\nWe have no public events scheduled right now. '
        'Check back soon for our fall programming, or sign up for the newsletter. ' * 5)


class _EmptyLatestBase(ArchivalTestBase):
    def setUp(self):
        super().setUp()
        self.connection.execute('ALTER TABLE crawl_results ADD COLUMN error_message TEXT')
        self.connection.execute('ALTER TABLE crawl_results ADD COLUMN crawled_content TEXT')
        self.add_website(SITE)

    def crawl(self, crawl_id, days_ago, event_ids=(), status='processed', error=None,
              content=PAGE, filename=None, website_id=SITE):
        self.add_crawl(crawl_id, website_id, days_ago, event_ids, status=status)
        self.connection.execute(
            'UPDATE crawl_results SET error_message = ?, crawled_content = ?, filename = ? '
            'WHERE id = ?', (error, content, filename, crawl_id))

    def selected(self, website_ids=None):
        return [(w, c) for w, c, _content in
                db.get_empty_latest_crawl_websites(self.cursor, website_ids)]


class EmptyLatestSelectionTests(_EmptyLatestBase):
    def test_clean_empty_latest_crawl_is_selected(self):
        self.add_event(100, SITE, future_days=20)
        self.crawl(10, 40, [100])
        self.crawl(11, 1)
        self.assertEqual(self.selected(), [(SITE, 11)])
        self.assertEqual(self.selected([SITE]), [(SITE, 11)])
        self.assertEqual(self.selected([2]), [])
        self.assertEqual(self.selected([]), [])

    def test_latest_crawl_with_events_is_the_normal_path(self):
        self.add_event(100, SITE, future_days=20)
        self.add_event(101, SITE, future_days=20)
        self.crawl(10, 40, [100])
        self.crawl(11, 1, [101])
        self.assertEqual(self.selected(), [])

    def test_failed_or_unfinished_latest_attempt_is_never_selected(self):
        self.add_event(100, SITE, future_days=20)
        self.crawl(10, 40, [100])
        self.crawl(11, 5)  # an empty processed crawl, but no longer the latest attempt
        for crawl_id, status in ((12, 'failed'), (13, 'pending'), (14, 'extracted')):
            with self.subTest(status=status):
                self.crawl(crawl_id, 1, status=status)
                self.assertEqual(self.selected(), [])
                self.connection.execute('DELETE FROM crawl_results WHERE id = ?', (crawl_id,))

    def test_processed_row_carrying_an_error_is_not_clean(self):
        self.add_event(100, SITE, future_days=20)
        self.crawl(10, 40, [100])
        self.crawl(11, 1, error='Bot challenge / origin error page not cleared after retries (1 URL(s))')
        self.assertEqual(self.selected(), [])

    def test_picnob_bundle_is_another_surface(self):
        """An empty IG bundle says nothing about the site calendar."""
        self.add_event(100, SITE, future_days=20)
        self.crawl(10, 40, [100])
        self.crawl(11, 1, filename='picnob_venue_1760000000.md')
        self.assertEqual(self.selected(), [])

    def test_site_with_nothing_live_is_skipped(self):
        self.add_event(100, SITE, future_days=20)
        self.crawl(10, 40, [100])
        self.crawl(11, 1)
        self.connection.execute('UPDATE events SET archived = 1')
        self.assertEqual(self.selected(), [])

    def test_disabled_site_is_skipped(self):
        self.add_event(100, SITE, future_days=20)
        self.crawl(10, 40, [100])
        self.crawl(11, 1)
        self.connection.execute('UPDATE websites SET disabled = 1')
        self.assertEqual(self.selected(), [])


class EmptyLatestArchivalGuardTests(_EmptyLatestBase):
    """The normal guards decide; the empty path adds only the name-mention hold."""

    def archive(self, content=PAGE):
        return db.archive_outdated_events(self.cursor, self.connection, SITE,
                                          absence_content=content)

    def test_past_only_event_archives_immediately(self):
        self.add_event(100, SITE)  # past date only
        self.crawl(10, 40, [100])
        self.crawl(11, 1)
        self.assertEqual(self.archive()[0], 1)
        self.assertEqual(self.archived_ids(), [100])

    def test_future_event_after_two_empty_crawls_and_grace_is_archived(self):
        self.add_event(100, SITE, future_days=30)
        self.crawl(10, 40, [100])
        self.crawl(11, 20)
        self.crawl(12, 1)
        archived, upcoming = self.archive()
        self.assertEqual(archived, 1)
        self.assertEqual([u[0] for u in upcoming], [100])

    def test_one_empty_crawl_since_last_seen_holds(self):
        self.add_event(100, SITE, future_days=30)
        self.crawl(10, 40, [100])
        self.crawl(11, 1)
        self.assertEqual(self.archive()[0], 0)

    def test_grace_period_holds(self):
        self.add_event(100, SITE, future_days=30)
        self.crawl(10, 5, [100])
        self.crawl(11, 3)
        self.crawl(12, 1)
        self.assertEqual(self.archive()[0], 0)

    def test_name_still_printed_by_the_empty_crawl_holds(self):
        """WCHS w4793: the homepage still prints the History Hunt; the extraction missed it."""
        self.add_event(100, SITE, future_days=14)
        self.connection.execute(
            "UPDATE events SET name = '250th Anniversary History Hunt: The American "
            "Revolution in Westchester' WHERE id = 100")
        self.crawl(10, 40, [100])
        self.crawl(11, 20)
        self.crawl(12, 1)
        page = PAGE + '\n### 250th Anniversary History Hunt: The American Revolution in Westchester\n'
        self.assertEqual(self.archive(content=page)[0], 0)
        self.assertEqual(self.archived_ids(), [])
        # Without the mention, the same event archives.
        self.assertEqual(self.archive()[0], 1)

    def test_mention_hold_never_keeps_a_past_event(self):
        self.add_event(100, SITE)
        self.crawl(10, 40, [100])
        self.crawl(11, 1)
        self.assertEqual(self.archive(content=PAGE + ' Event 100 ')[0], 1)

    def test_dry_run_changes_nothing(self):
        self.add_event(100, SITE)
        self.crawl(10, 40, [100])
        self.crawl(11, 1)
        count, rows = db.archive_outdated_events(self.cursor, self.connection, SITE,
                                                 dry_run=True)
        self.assertEqual((count, [r[0] for r in rows]), (1, [100]))
        self.assertEqual(self.archived_ids(), [])


class CleanEmptyCaptureTests(unittest.TestCase):
    def test_real_page_is_clean(self):
        self.assertTrue(merger._clean_empty_capture(PAGE))

    def test_missing_content_is_not_clean(self):
        for content in (None, '', '   \n'):
            self.assertFalse(merger._clean_empty_capture(content))

    def test_incomplete_sentinel_is_not_clean(self):
        self.assertFalse(merger._clean_empty_capture(
            PAGE + '\n# FOMO-CRAWL-INCOMPLETE\npage 2 returned 403\n'))

    def test_detectors_decide(self):
        import crawler
        with patch.object(crawler, '_is_bot_challenge', return_value=True):
            self.assertFalse(merger._clean_empty_capture(PAGE))
        with patch.object(crawler, '_is_soft_404', return_value=True):
            self.assertFalse(merger._clean_empty_capture(PAGE))

    def test_detector_failure_fails_closed(self):
        import crawler
        with patch.object(crawler, '_is_bot_challenge', side_effect=RuntimeError):
            self.assertFalse(merger._clean_empty_capture(PAGE))

    def test_unclean_rows_are_dropped_from_the_archival_list(self):
        rows = [(1, 11, PAGE), (2, 12, ''), (3, 13, PAGE + ' FOMO-CRAWL-INCOMPLETE: x')]
        with patch.object(merger.db, 'get_empty_latest_crawl_websites', return_value=rows):
            self.assertEqual(merger._empty_latest_archival_websites(object(), None), {1: PAGE})


class MergeReachesEmptySitesTests(unittest.TestCase):
    """A merge with nothing to link still judges its empty-latest websites."""

    def test_merge_without_crawl_events_runs_the_archival_tail(self):
        cursor = unittest.mock.MagicMock()
        cursor.fetchall.return_value = []
        calls = []
        with patch.object(merger, '_empty_latest_archival_websites',
                          return_value={7: PAGE}) as found, \
                patch.object(merger, '_run_archival_tail',
                             side_effect=lambda *a, **k: calls.append((a, k))), \
                patch.object(merger.db, 'build_tag_ancestor_map', return_value=({}, set())), \
                patch.object(merger, '_merge_edit_logger', return_value=None):
            self.assertEqual(merger.merge_crawl_events(cursor, object(), website_ids=[7]),
                             (0, 0))
        found.assert_called_once_with(cursor, [7])
        self.assertEqual(len(calls), 1)
        args, kwargs = calls[0]
        self.assertEqual(args[2], [7])
        self.assertEqual(kwargs['empty_contents'], {7: PAGE})

    def test_no_empty_sites_means_no_tail(self):
        cursor = unittest.mock.MagicMock()
        cursor.fetchall.return_value = []
        with patch.object(merger, '_empty_latest_archival_websites', return_value={}), \
                patch.object(merger, '_run_archival_tail') as tail, \
                patch.object(merger.db, 'build_tag_ancestor_map', return_value=({}, set())), \
                patch.object(merger, '_merge_edit_logger', return_value=None):
            merger.merge_crawl_events(cursor, object())
        tail.assert_not_called()


if __name__ == '__main__':
    unittest.main()
