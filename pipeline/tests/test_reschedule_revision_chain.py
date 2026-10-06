"""Obsolete notices cannot resurrect dates after a newer complete revision."""
import os
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reschedules import superseded_slots


def slot(day):
    return date.fromisoformat(day), '6:30pm', None, '7:30pm'


OLD = slot('2026-10-05')
INTERMEDIATE = slot('2026-10-06')
FINAL = slot('2026-10-07')
EVENT = dict(name='Writing Group', location_id=10)


def source(text, rows, timestamp, **kwargs):
    return dict(name=EVENT['name'], location_id=10, website_id=kwargs.get('website_id', 7),
                description=text, occurrences=rows, crawled_at=timestamp)


def sources():
    return [source('Discussion.', [OLD], '2026-09-20 10:00:00'),
            source('Rescheduled from October 5 to October 6.', [INTERMEDIATE], '2026-09-21 10:00:00'),
            source('The complete revised schedule for this course from 2026-10-01 to 2026-10-31 is October 7.',
                   [FINAL], '2026-09-22 10:00:00')]


def normalized(row):
    return row[0], row[1], row[2] or row[0], row[3]


class RevisionChainTests(unittest.TestCase):
    def test_complete_revision_retires_original_and_intermediate(self):
        for sequence in [sources(), list(reversed(sources()))]:
            self.assertEqual(superseded_slots(EVENT, [OLD, INTERMEDIATE, FINAL], sequence),
                             {normalized(OLD), normalized(INTERMEDIATE)})

    def test_each_stale_partition_is_rejected_repeatedly(self):
        for sequence in [sources(), list(reversed(sources()))]:
            for stale in [[OLD], [INTERMEDIATE], [OLD, INTERMEDIATE]]:
                for _ in range(2):
                    self.assertEqual(superseded_slots(EVENT, [FINAL] + stale, sequence),
                                     {normalized(row) for row in stale})

    def test_equal_newer_unknown_and_independent_notices_remain_conflicts(self):
        for change in [dict(crawled_at='2026-09-22 10:00:00'),
                       dict(crawled_at='2026-09-23 10:00:00'),
                       dict(crawled_at=None), dict(website_id=8),
                       dict(location_id=11), dict(name='Other Writing Group')]:
            with self.subTest(change=change):
                seq = sources()
                seq[1].update(change)
                removed = superseded_slots(EVENT, [OLD, INTERMEDIATE, FINAL], seq)
                self.assertNotIn(normalized(OLD), removed)
                self.assertNotIn(normalized(INTERMEDIATE), removed)

    def test_independently_supported_original_date_is_retained(self):
        seq = sources() + [source('Still scheduled.', [OLD], '2026-09-19 10:00:00', website_id=8)]
        self.assertNotIn(normalized(OLD), superseded_slots(EVENT, [OLD, INTERMEDIATE, FINAL], seq))

    def test_short_window_cannot_supersede_an_outside_replacement(self):
        seq = sources()
        seq[2]['description'] = 'The complete revised schedule for this course from 2026-10-01 to 2026-10-05 is October 4.'
        seq[2]['occurrences'] = [slot('2026-10-04')]
        removed = superseded_slots(EVENT, [OLD, INTERMEDIATE, slot('2026-10-04')], seq)
        self.assertNotIn(normalized(OLD), removed)
        self.assertNotIn(normalized(INTERMEDIATE), removed)

    def test_ordinary_notice_cannot_override_conflicting_history(self):
        seq = sources()
        seq[2]['description'] = 'Rescheduled from October 5 to October 7.'
        self.assertNotIn(normalized(OLD), superseded_slots(EVENT, [OLD, INTERMEDIATE, FINAL], seq))


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1', 'Connection-local MariaDB tables only')
class RevisionChainSQLTests(unittest.TestCase):
    def setUp(self):
        import test_reschedules as fixture
        fixture.DatabaseBoundaryTests.setUp(self)

    def rows(self, event_id=180336):
        import test_reschedules as fixture
        return fixture.DatabaseBoundaryTests.rows(self, event_id)

    def merge(self, source_id, incoming):
        import test_reschedules as fixture
        return fixture.DatabaseBoundaryTests.merge(self, source_id, incoming)

    def test_complete_revision_and_two_stale_replays(self):
        import test_reschedules as f
        final = slot('2026-09-30')
        self.q.execute('INSERT INTO crawl_results VALUES(3,93,%s)', ('2026-09-22 10:00:00',))
        self.q.execute('INSERT INTO crawl_events VALUES(3,3,%s,%s,7866)',
                       (f.EVENT['name'], 'The complete revised schedule for this course from 2026-09-01 to 2026-09-30 is September 30.'))
        self.q.execute('INSERT INTO event_sources VALUES(180336,3)')
        self.q.execute('INSERT INTO crawl_event_occurrences VALUES(3,%s,%s,%s,%s)', final)
        self.merge(2, [f.NEW])
        self.merge(3, [final])
        for _ in range(2):
            self.assertEqual(self.merge(1, [f.OLD])[1], [])
            self.assertEqual(self.merge(2, [f.NEW])[1], [])
        self.assertEqual([r[:4] for r in self.rows()], [f.JULY, f.AUGUST, final])
        self.assertEqual([r[:4] for r in self.rows(999)], [f.OLD])
        self.q.execute('SELECT COUNT(*) FROM crawl_event_occurrences')
        self.assertEqual(self.q.fetchone()[0], 5)


if __name__ == '__main__':
    unittest.main()
