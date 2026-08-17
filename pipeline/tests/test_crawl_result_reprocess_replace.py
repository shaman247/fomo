"""A re-processed crawl_result REPLACES its crawl_events, it does not add to them.

`db.create_crawl_result` is `ON DUPLICATE KEY UPDATE` on
`unique_run_file (crawl_run_id, filename)`, so re-crawling a website on a day it
has already been crawled reuses the SAME `crawl_results` row: crawled_content,
extracted_content, event_count and merged_at are all overwritten in place. The
insert loop in `processor.process_events` was the one thing that did not follow,
so the second pass's crawl_events stacked on top of the first's.

w1981 Bronx Council on the Arts, cr-113663 — the row the 2026-08-17 undated pass
flagged as a "chunked-extraction double-emit":

    17 crawl_events created 2026-08-14 06:53:48   (first pass)
    crawl_results.crawled_at rewritten to 09:24:01 (re-crawl, same run 323)
    21 crawl_events created 2026-08-14 09:24:38   (second pass)
    -> 38 rows, 23 distinct names, in one crawl_result

It was never a chunking bug: the stored `extracted_content` holds ONE clean
26-record extraction, and the two crawl_event blocks differ in content
("ThriftJam" and "Sunset Wednesdays 2026" exist only in the second), i.e. they
are two separate Gemini runs over the same page.

`db.copy_crawl_events` then copied all 38 into cr-114811 on 2026-08-17 via the
content-fingerprint short-circuit, which is how the doubling propagated.

Scope measured before fixing: 237 crawl_results written since 2026-07-15 hold
rows spanning more than one pass, 223 of them with duplicated (name, url) pairs;
10,276 are single-pass.
"""

import json
import os
import sys
import unittest
from datetime import date, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import constants  # noqa: E402
import db  # noqa: E402
import processor  # noqa: E402

# Fixed relative to "today" so the two occurrences below always sit inside the
# active date window, whenever the suite runs.
_TODAY = date.today()
_D1 = (_TODAY + timedelta(days=19)).isoformat()
_D2 = (_TODAY + timedelta(days=26)).isoformat()


class _FakeCursor:
    """Enough of a MySQL cursor to drive process_events without a database."""

    def __init__(self, existing_crawl_events=0):
        self.statements = []
        self.existing_crawl_events = existing_crawl_events
        self.lastrowid = 0
        self.rowcount = 0
        self._pending = None

    def execute(self, sql, params=None):
        self.statements.append((' '.join(sql.split()), params))
        head = sql.strip().upper()
        self._pending = None
        self.rowcount = 0
        if head.startswith('DELETE FROM CRAWL_EVENTS'):
            self.rowcount = self.existing_crawl_events
            self.existing_crawl_events = 0
        elif head.startswith('INSERT INTO CRAWL_EVENTS'):
            self.lastrowid += 1
            self.rowcount = 1
        elif 'BLOCKED_LOCATION_NAMES' in head:
            self._pending = (None,)

    def fetchone(self):
        return self._pending

    def fetchall(self):
        return []

    def close(self):
        pass


def _run_process_events(existing_crawl_events):
    """Process one two-event extraction against a cursor holding stale rows."""
    extracted = json.dumps({'events': [
        {'name': 'Public Gallery Tour',
         'description': 'A guided tour of the current exhibition.',
         'location': 'Bronx Council on the Arts',
         'url': 'https://www.bronxarts.org/events/public-gallery-tour.html',
         'occurrences': [{'start_date': _D1, 'start_time': '6pm',
                          'end_date': '', 'end_time': '8pm'}]},
        {'name': 'ThriftJam',
         'description': 'A clothing swap and DJ set.',
         'location': 'Bronx Council on the Arts',
         'url': 'https://www.bronxarts.org/events/thriftjam.html',
         'occurrences': [{'start_date': _D2, 'start_time': '7pm',
                          'end_date': '', 'end_time': '10pm'}]},
    ]})
    cursor = _FakeCursor(existing_crawl_events=existing_crawl_events)
    connection = mock.Mock()
    with mock.patch.object(db, 'get_extracted_content',
                           return_value=(extracted, 1981)), \
            mock.patch.object(db, 'get_crawled_content', return_value=''), \
            mock.patch.object(db, 'update_crawl_result_processed'), \
            mock.patch.object(processor, 'log_rejection'), \
            mock.patch.object(processor, 'get_active_date_window',
                              return_value=(_TODAY, _TODAY + timedelta(days=90))):
        count = processor.process_events(
            cursor, connection, 113663, 'Bronx Council on the Arts', '20260817',
            locations_map={}, websites_map={},
            tag_context=({}, {}, set(), []),
        )
    return cursor, count


class ProcessEventsReplacesPriorPass(unittest.TestCase):
    def test_a_delete_precedes_the_inserts(self):
        cursor, count = _run_process_events(existing_crawl_events=17)
        self.assertEqual(count, 2)
        kinds = [sql.split()[0].upper() + ' ' + sql.split()[2].upper()
                 for sql, _ in cursor.statements
                 if sql.upper().startswith(('DELETE FROM CRAWL_EVENTS',
                                            'INSERT INTO CRAWL_EVENTS '))]
        self.assertTrue(kinds, 'no crawl_events statements were issued')
        self.assertEqual(kinds[0], 'DELETE CRAWL_EVENTS',
                         'the stale pass must be cleared before the new one lands')
        self.assertEqual(kinds.count('DELETE CRAWL_EVENTS'), 1,
                         'exactly one clearing delete per processing pass')

    def test_the_delete_is_scoped_to_this_crawl_result(self):
        cursor, _ = _run_process_events(existing_crawl_events=17)
        deletes = [(sql, params) for sql, params in cursor.statements
                   if sql.upper().startswith('DELETE FROM CRAWL_EVENTS')]
        self.assertEqual(len(deletes), 1)
        sql, params = deletes[0]
        self.assertIn('WHERE crawl_result_id = %s', sql)
        self.assertEqual(params, (113663,))

    def test_reprocessing_yields_the_new_pass_only(self):
        """Two passes over the same crawl_result leave two rows, not four."""
        cursor, _ = _run_process_events(existing_crawl_events=2)
        inserts = [s for s, _ in cursor.statements
                   if s.upper().startswith('INSERT INTO CRAWL_EVENTS ')]
        self.assertEqual(len(inserts), 2)
        self.assertEqual(cursor.existing_crawl_events, 0)

    def test_a_first_pass_is_unaffected(self):
        """The delete is a no-op when there is nothing to supersede."""
        cursor, count = _run_process_events(existing_crawl_events=0)
        self.assertEqual(count, 2)
        self.assertEqual(
            len([s for s, _ in cursor.statements
                 if s.upper().startswith('INSERT INTO CRAWL_EVENTS ')]), 2)


class ProcessEventsKeepsRowsWhenTheNewPassIsEmpty(unittest.TestCase):
    """A re-crawl that extracts nothing must not strip the crawl_result bare.

    An extraction failure or a transient empty page would otherwise delete every
    source the events have, and `archive_outdated_events` would then archive
    still-listed events wholesale.
    """

    def test_no_delete_when_the_extraction_is_empty(self):
        cursor = _FakeCursor(existing_crawl_events=17)
        connection = mock.Mock()
        with mock.patch.object(db, 'get_extracted_content',
                               return_value=(json.dumps({'events': []}), 1981)), \
                mock.patch.object(db, 'get_crawled_content', return_value=''), \
                mock.patch.object(db, 'update_crawl_result_processed'), \
                mock.patch.object(processor, 'log_rejection'):
            count = processor.process_events(
                cursor, connection, 113663, 'Bronx Council on the Arts',
                '20260817', locations_map={}, websites_map={},
                tag_context=({}, {}, set(), []),
            )
        self.assertEqual(count, 0)
        self.assertEqual(cursor.existing_crawl_events, 17)
        self.assertFalse([s for s, _ in cursor.statements
                          if s.upper().startswith('DELETE FROM CRAWL_EVENTS')])


class _CapturingCursor:
    """Records every execute(); returns nothing, so copy_crawl_events exits early."""

    def __init__(self):
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append((' '.join(sql.split()), params))

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class CopyCrawlEventsTakesTheLatestPassOnly(unittest.TestCase):
    """The copy path must not re-spread a pre-fix pile-up.

    `FINGERPRINT_MAX_REUSE_DAYS` is 30, so crawl_results written before the
    replace fix stay copyable for a month. Copying only the newest pass repairs
    them for free and is a no-op on every single-pass source.
    """

    def _select_sql(self):
        cursor = _CapturingCursor()
        db.copy_crawl_events(cursor, mock.Mock(), 113663, 114811)
        self.assertTrue(cursor.statements)
        return cursor.statements[0]

    def test_the_source_select_is_bounded_to_the_last_pass(self):
        sql, params = self._select_sql()
        self.assertIn('MAX(created_at)', sql)
        self.assertIn('INTERVAL %s SECOND', sql)
        self.assertIn(constants.CRAWL_EVENT_PASS_WINDOW_SECONDS, params)

    def test_the_bound_is_computed_from_the_same_source_result(self):
        sql, params = self._select_sql()
        self.assertEqual(params[0], 113663)
        self.assertEqual(params[2], 113663)

    def test_an_empty_source_still_returns_zero(self):
        cursor = _CapturingCursor()
        self.assertEqual(db.copy_crawl_events(cursor, mock.Mock(), 1, 2), 0)


class _CopySourceCursor(_CapturingCursor):
    """Returns one source row on the first fetchall, then nothing.

    Enough for copy_crawl_events to get past its `if not src_events` guard and
    reach the destination delete.
    """

    def __init__(self):
        super().__init__()
        self._fetches = 0
        self.lastrowid = 999
        self.rowcount = 21   # the destination's pre-existing pass

    def fetchall(self):
        self._fetches += 1
        if self._fetches == 1:
            return [(1, 'An Event', 'Event', 'desc', '🎪', 'Venue', None,
                     None, 'https://example.org/e/1', '{}', 'abc')]
        return []


class CopyCrawlEventsReplacesTheDestination(unittest.TestCase):
    """Bounding the SOURCE to its latest pass does not protect the DESTINATION.

    Found 2026-08-17, immediately after the process_events fix shipped: w1981
    cr-114811 already held 21 rows from that morning's full run, and a targeted
    `--ids 1981` re-crawl fingerprint-matched cr-113663 and copied 21 MORE in.
    42 rows for an event_count of 21 — the same doubling, arriving by the other
    door, because the fingerprint short-circuit returns from process_events
    before that function's own replace can run.
    """

    def _statements(self):
        cursor = _CopySourceCursor()
        db.copy_crawl_events(cursor, mock.Mock(), 113663, 114811)
        return cursor.statements

    def _delete(self):
        for sql, params in self._statements():
            if sql.startswith('DELETE FROM crawl_events'):
                return sql, params
        return None, None

    def test_the_destination_is_cleared(self):
        sql, params = self._delete()
        self.assertIsNotNone(sql, 'copy_crawl_events must clear the destination')
        self.assertEqual(params, (114811,))

    def test_the_delete_never_targets_the_source(self):
        _, params = self._delete()
        self.assertNotIn(113663, params)

    def test_the_delete_precedes_the_inserts(self):
        kinds = [s.split()[0] for s, _ in self._statements()]
        self.assertIn('DELETE', kinds)
        self.assertIn('INSERT', kinds)
        self.assertLess(kinds.index('DELETE'), kinds.index('INSERT'))

    def test_an_empty_source_leaves_the_destination_alone(self):
        # The `if not src_events` return must come FIRST, so a copy that would
        # write nothing cannot strip the destination bare and cascade its
        # event_sources away.
        cursor = _CapturingCursor()
        self.assertEqual(db.copy_crawl_events(cursor, mock.Mock(), 1, 2), 0)
        self.assertFalse([s for s, _ in cursor.statements
                          if s.startswith('DELETE FROM crawl_events')])


class PassWindowIsWiderThanAnyRealInsertLoop(unittest.TestCase):
    """The window separates passes; it must never split one.

    Measured on the biggest real results: w3 cr-114466 wrote 1,033 rows inside a
    single second, w388 cr-114119 wrote 833 in one. The re-crawl gaps that create
    a second pass are minutes to hours (w1981: 2h31m).
    """

    def test_window_is_generous_but_finite(self):
        self.assertGreaterEqual(constants.CRAWL_EVENT_PASS_WINDOW_SECONDS, 60)
        self.assertLessEqual(constants.CRAWL_EVENT_PASS_WINDOW_SECONDS, 1800)


if __name__ == '__main__':
    unittest.main()
