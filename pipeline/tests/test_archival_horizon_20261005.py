"""Source horizon must not be stretched by a few far-dated outlier occurrences.

2026-10-04: BCCLS Libraries (w3530) fetches a 14-day LibCal window (~120
occurrences/day), but reviewers correctly kept ~30 Nov/Dec dates spelled out in
listing prose. The archival guard took the horizon as MAX(start_date) = +71d, so
32 monthly programs whose next date fell just past the real window counted as
"absent" and were archived (23 verified live). `db.source_horizon` trims a sparse
outlier tail; far-listing sites with steady or tapering density keep MAX.
"""
import unittest
from datetime import date, timedelta

from test_archival import ArchivalTestBase, _days_ahead, db

CRAWL = date(2026, 10, 4)


def day(n):
    return CRAWL + timedelta(days=n)


def bccls_shape():
    """14 dense days, then the real cr-128988 outlier tail (+16d .. +71d)."""
    dense = [13, 173, 179, 189, 172, 85, 77, 19, 58, 209, 195, 196, 81, 66]
    counts = [(day(i), c) for i, c in enumerate(dense)]
    tail = [16, 17, 18, 20, 23, 24, 25, 27, 29, 31, 31, 34, 36, 37, 37, 38, 40,
            41, 44, 45, 45, 46, 52, 59, 60, 65, 65, 69, 71]
    for n in tail:
        counts.append((day(n), 1))
    return counts


class SourceHorizonTests(unittest.TestCase):
    def test_bccls_window_plus_outliers_trims_to_window_edge(self):
        self.assertEqual(db.source_horizon(CRAWL, bccls_shape()), day(13))

    def test_steady_far_listing_keeps_max(self):
        # Lincoln Center Theater / Carnegie Hall shape: ~10-25 a week for 13 weeks.
        counts = [(day(i), 2) for i in range(0, 91, 1) if i % 7 in (1, 3, 4, 5, 6)]
        self.assertEqual(db.source_horizon(CRAWL, counts), day(90))

    def test_natural_taper_keeps_max(self):
        # RA / BAM shape: dense first month, tapering but continuous to +90d.
        weekly = [189, 162, 129, 139, 58, 47, 39, 24, 32, 29, 19, 16, 37]
        counts = []
        for w, total in enumerate(weekly):
            per_day, extra = divmod(total, 7)
            for d in range(7):
                c = per_day + (1 if d < extra else 0)
                if c:
                    counts.append((day(w * 7 + d), c))
        self.assertEqual(db.source_horizon(CRAWL, counts), counts[-1][0])

    def test_small_crawl_keeps_max(self):
        counts = [(day(i), 1) for i in range(10)] + [(day(80), 1)]
        self.assertEqual(db.source_horizon(CRAWL, counts), day(80))

    def test_tail_too_large_to_be_outliers_keeps_max(self):
        # 10% of everything sits in the far tail: a real second listing, not noise.
        counts = [(day(i), 9) for i in range(14)] + [(day(30 + i), 1) for i in range(14)]
        self.assertEqual(db.source_horizon(CRAWL, counts), day(43))

    def test_past_only_and_degenerate_inputs(self):
        self.assertIsNone(db.source_horizon(CRAWL, []))
        self.assertIsNone(db.source_horizon(CRAWL, [(None, 3)]))
        past = [(day(-40), 30), (day(-2), 30)]
        self.assertEqual(db.source_horizon(CRAWL, past), day(-2))
        self.assertEqual(db.source_horizon(None, bccls_shape()), day(71))

    def test_accepts_iso_strings_and_datetimes(self):
        counts = [(d.isoformat(), c) for d, c in bccls_shape()]
        self.assertEqual(db.source_horizon('2026-10-04 19:17:10', counts), day(13))

    def test_never_exceeds_raw_max(self):
        for counts in (bccls_shape(), [(day(i), 5) for i in range(30)]):
            self.assertLessEqual(db.source_horizon(CRAWL, counts),
                                 max(d for d, _ in counts))


class ArchivalHorizonOutlierTests(ArchivalTestBase):
    """Run the real archival SQL with a BCCLS-shaped latest crawl."""

    def listed(self, crawl_id, start, count=1):
        for _ in range(count):
            self._crawl_event_seq += 1
            ce = self._crawl_event_seq
            self.connection.execute('INSERT INTO crawl_events VALUES (?, ?, ?)',
                                    (ce, crawl_id, 'Other listed program'))
            self.connection.execute('INSERT INTO crawl_event_occurrences VALUES (?, ?, ?)',
                                    (ce, _days_ahead(start), None))

    def build(self, *, next_occurrence):
        self.add_website(1)
        self.add_event(100, 1, future_days=next_occurrence)
        self.add_crawl(10, 1, 60, [100])
        self.add_crawl(11, 1, 20)
        self.add_crawl(12, 1, 0)

    def bccls_latest(self):
        for n in range(14):
            self.listed(12, n, 25)
        for n in (30, 45, 60, 70):
            self.listed(12, n)

    def archive(self):
        return db.archive_outdated_events(self.cursor, self.connection, 1)

    def test_monthly_program_past_window_is_not_archived(self):
        self.build(next_occurrence=20)
        self.bccls_latest()
        self.assertEqual(self.archive()[0], 0)
        self.assertEqual(self.archived_ids(), [])

    def test_missing_event_inside_window_still_archives(self):
        self.build(next_occurrence=5)
        self.bccls_latest()
        self.assertEqual(self.archive()[0], 1)

    def test_far_listing_site_keeps_far_horizon(self):
        self.build(next_occurrence=40)
        for n in range(80):
            self.listed(12, n, 1 + (n % 3 == 0))
        self.assertEqual(self.archive()[0], 1)

    def test_trim_only_touches_the_trimmed_site(self):
        self.build(next_occurrence=20)
        self.bccls_latest()
        self.add_website(2)
        self.add_crawl(20, 2, 0)
        for n in range(80):
            self.listed(20, n, 1)
        db.build_archival_temps(self.cursor)
        self.cursor.execute('SELECT website_id, last_start FROM _ws_crawl_state ORDER BY website_id')
        rows = dict(self.cursor.fetchall())
        db.drop_archival_temps(self.cursor)
        self.assertEqual(rows[1], _days_ahead(13))
        self.assertEqual(rows[2], _days_ahead(79))


if __name__ == '__main__':
    unittest.main()
