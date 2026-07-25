"""Tests for extractor.py reliability guards (variance retry, max_batches
auto-bump), the estimate_event_count page-size estimator, and the
fix_recurring_spans course-shape classifier."""

import importlib.util
import os
import sys
import unittest
from datetime import date

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extractor import (
    PreparedExtraction,
    SimpleOccurrence,
    _variance_retry_reason,
    _fingerprint_copy_is_suspect,
    _maybe_auto_bump_max_batches,
    _normalize_extraction_response,
    chunk_content,
    chunk_content_by_events,
    estimate_event_count,
    AUTO_MAX_BATCHES_CEILING,
    DEFAULT_MAX_BATCHES,
    LARGE_PAGE_THRESHOLD,
    MAX_CHUNK_CHARS,
)


class FakeCursor:
    """Routes the two _variance_retry_reason queries to canned results."""

    def __init__(self, current_row, history_rows):
        self.current_row = current_row
        self.history_rows = history_rows
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.current_row

    def fetchall(self):
        return self.history_rows


class FakeConnection:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class TestVarianceRetryReason(unittest.TestCase):
    HISTORY = [(20, 60000), (22, 61000), (18, 59000), (21, 60500), (19, 60200)]

    def test_collapse_on_stable_content_triggers_retry(self):
        cur = FakeCursor((42, 60000), self.HISTORY)
        reason = _variance_retry_reason(cur, 1, new_count=5)
        self.assertIsNotNone(reason)
        self.assertIn("5 events", reason)

    def test_healthy_count_no_retry(self):
        cur = FakeCursor((42, 60000), self.HISTORY)
        self.assertIsNone(_variance_retry_reason(cur, 1, new_count=15))

    def test_exact_half_median_no_retry(self):
        # median count is 20; 10 == 20 * 0.5 is NOT below half
        cur = FakeCursor((42, 60000), self.HISTORY)
        self.assertIsNone(_variance_retry_reason(cur, 1, new_count=10))

    def test_content_size_changed_no_retry(self):
        # Page shrank 50% — a real change, not extraction variance
        cur = FakeCursor((42, 30000), self.HISTORY)
        self.assertIsNone(_variance_retry_reason(cur, 1, new_count=5))

    def test_too_little_history_no_retry(self):
        cur = FakeCursor((42, 60000), self.HISTORY[:2])
        self.assertIsNone(_variance_retry_reason(cur, 1, new_count=5))

    def test_tiny_site_no_retry(self):
        # median 3 < 4: too noisy to judge
        cur = FakeCursor((42, 2700), [(3, 2700), (3, 2700), (2, 2700)])
        self.assertIsNone(_variance_retry_reason(cur, 1, new_count=1))

    def test_missing_crawl_result_no_retry(self):
        cur = FakeCursor(None, self.HISTORY)
        self.assertIsNone(_variance_retry_reason(cur, 1, new_count=0))

    def test_cursor_error_fails_open(self):
        class BoomCursor:
            def execute(self, *a, **k):
                raise RuntimeError("boom")
        self.assertIsNone(_variance_retry_reason(BoomCursor(), 1, new_count=0))


class TestFingerprintCopyIsSuspect(unittest.TestCase):
    """The fingerprint short-circuit must refuse to copy a frozen
    under-extraction. Reference = median of per-content_hash event counts, so
    propagated copies (same hash) collapse to one vote and can't poison it."""

    # Blue Note shape: per-hash best counts; freeze = 12, real level ~33.
    # sorted [12,33,33,37,65] → median 33 → suspect threshold 16.5
    HEALTHY_HASHES = [(12,), (65,), (37,), (33,), (33,)]

    def test_frozen_low_count_is_suspect(self):
        cur = FakeCursor((67, 12), self.HEALTHY_HASHES)
        self.assertTrue(_fingerprint_copy_is_suspect(cur, prior_id=93406))

    def test_zero_count_is_suspect(self):
        # Topos shape: per-hash counts [0,9,10,5,24] → median 9; prior 0
        cur = FakeCursor((2656, 0), [(0,), (9,), (10,), (5,), (24,)])
        self.assertTrue(_fingerprint_copy_is_suspect(cur, prior_id=94136))

    def test_normal_count_not_suspect(self):
        # A normal 30-event crawl vs median 33 is not a freeze
        cur = FakeCursor((67, 30), self.HEALTHY_HASHES)
        self.assertFalse(_fingerprint_copy_is_suspect(cur, prior_id=85455))

    def test_exact_half_median_not_suspect(self):
        # median 20, prior 10 == half → strict < means NOT suspect
        cur = FakeCursor((67, 10), [(10,), (20,), (20,), (25,), (18,)])
        self.assertFalse(_fingerprint_copy_is_suspect(cur, prior_id=1))

    def test_freeze_propagation_does_not_poison_reference(self):
        # The live table may be full of copied 12s, but dedup-by-hash keeps the
        # reference distribution intact, so the guard still fires.
        cur = FakeCursor((67, 12), self.HEALTHY_HASHES)
        self.assertTrue(_fingerprint_copy_is_suspect(cur, prior_id=95857))

    def test_too_few_distinct_hashes_not_suspect(self):
        cur = FakeCursor((67, 1), [(40,), (38,)])  # only 2 distinct page states
        self.assertFalse(_fingerprint_copy_is_suspect(cur, prior_id=1))

    def test_tiny_site_not_suspect(self):
        # median 3 < 4 → too noisy to judge
        cur = FakeCursor((9, 0), [(3,), (3,), (2,), (4,)])
        self.assertFalse(_fingerprint_copy_is_suspect(cur, prior_id=1))

    def test_missing_prior_row_not_suspect(self):
        cur = FakeCursor(None, self.HEALTHY_HASHES)
        self.assertFalse(_fingerprint_copy_is_suspect(cur, prior_id=1))

    def test_null_event_count_fails_open(self):
        cur = FakeCursor((67, None), self.HEALTHY_HASHES)
        self.assertFalse(_fingerprint_copy_is_suspect(cur, prior_id=1))

    def test_cursor_error_fails_open(self):
        class BoomCursor:
            def execute(self, *a, **k):
                raise RuntimeError("boom")
        self.assertFalse(_fingerprint_copy_is_suspect(BoomCursor(), prior_id=1))


class TestMaybeAutoBumpMaxBatches(unittest.TestCase):
    def _prep(self, max_batches, website_id=99):
        return PreparedExtraction(
            crawl_result_id=1, website_name="Test Site", extraction_type='chunked',
            max_batches=max_batches, website_id=website_id,
        )

    def test_bumps_default_capped_site(self):
        cur, conn = FakeCursor(None, []), FakeConnection()
        new_cap = _maybe_auto_bump_max_batches(cur, conn, self._prep(3), batches_needed=10)
        self.assertEqual(new_cap, 11)
        self.assertEqual(conn.commits, 1)
        self.assertIn("UPDATE websites SET max_batches", cur.executed[0][0])
        self.assertEqual(cur.executed[0][1], (11, 99))

    def test_respects_deliberate_throttle_below_default(self):
        cur, conn = FakeCursor(None, []), FakeConnection()
        self.assertIsNone(_maybe_auto_bump_max_batches(cur, conn, self._prep(2), batches_needed=10))
        self.assertEqual(cur.executed, [])

    def test_clamps_to_ceiling(self):
        cur, conn = FakeCursor(None, []), FakeConnection()
        new_cap = _maybe_auto_bump_max_batches(cur, conn, self._prep(DEFAULT_MAX_BATCHES), batches_needed=100)
        self.assertEqual(new_cap, AUTO_MAX_BATCHES_CEILING)

    def test_no_bump_when_already_at_ceiling(self):
        cur, conn = FakeCursor(None, []), FakeConnection()
        self.assertIsNone(_maybe_auto_bump_max_batches(
            cur, conn, self._prep(AUTO_MAX_BATCHES_CEILING), batches_needed=100))

    def test_no_bump_without_website_id(self):
        cur, conn = FakeCursor(None, []), FakeConnection()
        self.assertIsNone(_maybe_auto_bump_max_batches(
            cur, conn, self._prep(3, website_id=None), batches_needed=10))

    def test_no_bump_when_not_needed(self):
        cur, conn = FakeCursor(None, []), FakeConnection()
        self.assertIsNone(_maybe_auto_bump_max_batches(cur, conn, self._prep(10), batches_needed=8))


class TestEstimateEventCount(unittest.TestCase):
    """estimate_event_count routes pages to chunked extraction when the
    estimate exceeds LARGE_PAGE_THRESHOLD. Under-estimation makes single-call
    mode truncate at its ~8K output-token cap (extraction collapse, e.g.
    NYC DSA 108->4, Metrograph 87->14, Jacob Burns 38->2 on 2026-06-11), so
    each per-event signal format must be counted — while staying max-based so
    healthy small pages are not promoted into the costlier chunked mode."""

    # --- newly counted formats (2026-06-11 collapse bug) ---

    def test_iso_labeled_date_lines_counted(self):
        # NYC DSA / Action Network calendar style: one `Date: YYYY-MM-DD`
        # line per event card. Counted unhalved.
        content = '\n'.join(
            f'### Event Number {i}\nDate: 2026-06-{(i % 28) + 1:02d}\n'
            for i in range(60)
        )
        self.assertEqual(estimate_event_count(content), 60)
        self.assertGreater(estimate_event_count(content), LARGE_PAGE_THRESHOLD)

    def test_iso_date_line_label_variants(self):
        content = ('When: 2026-07-04\n'
                   '**Date:** 2026-07-05\n'
                   'Dates: 2026-07-06\n'
                   '2026-07-07\n')  # bare line-start ISO date
        self.assertEqual(estimate_event_count(content), 4)

    def test_inline_iso_timestamps_not_counted(self):
        # Mid-line ISO dates (e.g. Metrograph's "Now time 2026-06-11 12:14:55"
        # banner) are not per-event signals.
        content = 'Now time 2026-06-11 12:14:55 Now time local 2026-06-11\n' * 30
        self.assertEqual(estimate_event_count(content), 0)

    def test_booking_urls_counted_unhalved(self):
        # Jacob Burns style: one /booking/ link per film-day entry, plus
        # bare showtime links that carry no countable text.
        content = '\n'.join(
            f'[Film Title {i}](https://example.org/booking/film-{i}/)\n'
            f'[5:20](https://shop.example.org/{i}/1)[7:35](https://shop.example.org/{i}/2)\n'
            for i in range(60)
        )
        self.assertEqual(estimate_event_count(content), 60)

    def test_buy_tickets_links_halved(self):
        # Metrograph style: one "Buy Tickets" link per showtime, several
        # showtimes per film — halved to approximate the entry count.
        content = ('[3:00pm](https://t.example.com/x?id=1 "Buy Tickets")\n'
                   '[5:10pm](https://t.example.com/x?id=2 "Buy Tickets")\n') * 60
        self.assertEqual(estimate_event_count(content), 60)

    def test_event_detail_url_markers_counted(self):
        # Markers injected by our own js_code: exactly one per event card.
        content = '\n'.join(
            f'EVENT DETAIL URL: https://example.org/e/{i}\nSome Event {i}\n'
            for i in range(55)
        )
        self.assertEqual(estimate_event_count(content), 55)

    def test_linked_headings_halved(self):
        # `#### [Title](url)` event cards (Metrograph, Alvin Ailey).
        content = '\n'.join(
            f'#### [Event {i}](https://example.org/x/{i})\nDescription text.\n'
            for i in range(120)
        )
        self.assertEqual(estimate_event_count(content), 60)

    def test_plain_and_empty_headings_not_counted(self):
        content = ('## Quick Links\n'
                   '### About Us\n'
                   '## [ ](https://example.org/banner)\n'  # empty link text
                   '## [Navigation](https://example.org/nav)\n')  # ## excluded
        self.assertEqual(estimate_event_count(content), 0)

    # --- conservatism: max, not sum ---

    def test_overlapping_signals_take_max_not_sum(self):
        # 30 cards each carrying a linked heading + ISO date line + ticket
        # link must estimate ~30, not 30 * 3.
        content = '\n'.join(
            f'#### [Event {i}](https://example.org/booking/ev-{i}/)\n'
            f'Date: 2026-06-{(i % 28) + 1:02d}\n'
            f'[7:00pm](https://t.example.com/x?id={i} "Buy Tickets")\n'
            for i in range(30)
        )
        self.assertEqual(estimate_event_count(content), 30)
        self.assertLessEqual(estimate_event_count(content), LARGE_PAGE_THRESHOLD)

    # --- regressions: healthy small pages stay below the threshold ---

    def test_small_month_name_listing_stays_small(self):
        # Classic small listing: month-name date + View Details + /events/
        # URL (twice: image link + title link) per card.
        content = '\n'.join(
            f'### [Concert {i}](https://example.org/events/concert-{i})\n'
            f'June {(i % 28) + 1}, 2026 at 7pm\n'
            f'[View Details](https://example.org/events/concert-{i})\n'
            for i in range(8)
        )
        self.assertLessEqual(estimate_event_count(content), 10)

    def test_small_iso_date_listing_stays_small(self):
        content = '\n'.join(
            f'### Workshop {i}\nDate: 2026-07-{i + 1:02d}\n'
            for i in range(6)
        )
        self.assertEqual(estimate_event_count(content), 6)

    def test_small_cinema_listing_stays_small(self):
        content = '\n'.join(
            f'[Film {i}](https://example.org/booking/film-{i}/)\n'
            f'[7:30](https://shop.example.org/{i}/1 "Buy Tickets")\n'
            for i in range(9)
        )
        self.assertEqual(estimate_event_count(content), 9)

    def test_threshold_boundary(self):
        at_cap = '\n'.join(f'EVENT DETAIL URL: https://x.org/{i}' for i in range(LARGE_PAGE_THRESHOLD))
        over_cap = '\n'.join(f'EVENT DETAIL URL: https://x.org/{i}' for i in range(LARGE_PAGE_THRESHOLD + 1))
        self.assertLessEqual(estimate_event_count(at_cap), LARGE_PAGE_THRESHOLD)
        self.assertGreater(estimate_event_count(over_cap), LARGE_PAGE_THRESHOLD)

    def test_empty_content(self):
        self.assertEqual(estimate_event_count(''), 0)


class TestNormalizeExtractionResponse(unittest.TestCase):
    def test_valid(self):
        text = '{"events": [{"name": "A", "occurrences": [["2026-01-01"]]}]}'
        out, n, occ = _normalize_extraction_response(text)
        self.assertEqual((out, n, occ), (text, 1, 1))

    def test_empty_and_invalid(self):
        self.assertEqual(_normalize_extraction_response(''), ('{"events": []}', 0, 0))
        self.assertEqual(_normalize_extraction_response('not json'), ('{"events": []}', 0, 0))


def _load_fix_recurring_spans():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), 'scripts', 'fix_recurring_spans.py')
    spec = importlib.util.spec_from_file_location('fix_recurring_spans', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestClassifyCourse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frs = _load_fix_recurring_spans()

    @staticmethod
    def _occ(start, end, st='', et=''):
        return {'start_date': start, 'end_date': end, 'start_time': st, 'end_time': et}

    def test_bhakti_shape_timed_span(self):
        # Aug 11 -> Dec 15 2026 are both Tuesdays; 6:30pm class
        occ = [self._occ(date(2026, 8, 11), date(2026, 12, 15), '6:30pm', '8:30pm')]
        verdict, info = self.frs.classify_course('Bhakti Sastri Module 4', occ)
        self.assertEqual(verdict, 'course_weekly')
        dates = self.frs.planned_dates('course_weekly', info)
        self.assertEqual(len(dates), 19)
        self.assertEqual(dates[0], date(2026, 8, 11))
        self.assertEqual(dates[-1], date(2026, 12, 15))
        self.assertTrue(all(d.weekday() == 1 for d in dates))

    def test_bisr_shape_recurrence_keyword_no_time(self):
        # Jul 6 -> Jul 27 2026 are both Mondays; no time but explicit "weekly"
        occ = [self._occ(date(2026, 7, 6), date(2026, 7, 27))]
        verdict, info = self.frs.classify_course(
            'Literature and Catastrophe', occ, 'A four-week course meeting weekly.')
        self.assertEqual(verdict, 'course_weekly')
        self.assertEqual(len(self.frs.planned_dates('course_weekly', info)), 4)

    def test_program_keyword_alone_does_not_corroborate(self):
        # Daily summer programs match PROGRAM_RE but are NOT weekly — "program"/
        # "camp" wording without a time or explicit recurrence keyword must skip
        occ = [self._occ(date(2026, 7, 6), date(2026, 8, 3))]
        verdict, _ = self.frs.classify_course(
            '2026 International Summer Program', occ, 'A four-week intensive program for students.')
        self.assertEqual(verdict, 'skip')

    def test_exhibition_keyword_vetoes(self):
        occ = [self._occ(date(2026, 8, 11), date(2026, 12, 15), '6:30pm')]
        verdict, _ = self.frs.classify_course('Group Show', occ, 'An exhibition on view daily.')
        self.assertEqual(verdict, 'skip')

    def test_different_weekday_endpoints_skip(self):
        occ = [self._occ(date(2026, 8, 11), date(2026, 12, 14), '6:30pm')]
        verdict, _ = self.frs.classify_course('Some Class', occ)
        self.assertEqual(verdict, 'skip')

    def test_no_time_no_keyword_skip(self):
        occ = [self._occ(date(2026, 7, 6), date(2026, 7, 27))]
        verdict, _ = self.frs.classify_course('Some Long Thing', occ)
        self.assertEqual(verdict, 'skip')

    def test_multiple_occurrences_skip(self):
        occ = [self._occ(date(2026, 7, 6), date(2026, 7, 27), '6pm'),
               self._occ(date(2026, 7, 6), None, '6pm')]
        verdict, _ = self.frs.classify_course('Weekly Course', occ)
        self.assertEqual(verdict, 'skip')

    def test_span_too_long_skip(self):
        occ = [self._occ(date(2026, 1, 6), date(2026, 12, 29), '6pm')]  # 358d
        verdict, _ = self.frs.classify_course('Weekly Course', occ)
        self.assertEqual(verdict, 'skip')

    def test_one_week_span_skip(self):
        occ = [self._occ(date(2026, 7, 6), date(2026, 7, 13), '6pm')]  # 7d < 14
        verdict, _ = self.frs.classify_course('Weekly Course', occ)
        self.assertEqual(verdict, 'skip')


class ChunkSizeGuardTests(unittest.TestCase):
    """The event chunker must cap chunk SIZE, not just marker count.

    A dense listing (a cinema's showtime calendar) can pack `events_per_chunk`
    markers into a chunk far larger than Gemini can answer in one response; it
    then drops the tail of that chunk silently. Regression for Film Forum w50,
    where 50 markers landed in one 34,260-char chunk and 18 of 50 events came back.
    """

    @staticmethod
    def _card(i, body_lines=1):
        body = '\n'.join(f'2026-07-{(i % 28) + 1:02d}: 12:15PM, 2:20PM, 4:30PM'
                         for _ in range(body_lines))
        return f'### [FILM {i}](https://example.com/film-{i})\nShowtimes:\n{body}'

    def test_marker_count_still_splits(self):
        content = '\n'.join(self._card(i) for i in range(120))
        chunks = chunk_content_by_events(content, events_per_chunk=50)
        self.assertEqual(len(chunks), 3)

    def test_uncapped_by_default(self):
        """max_chars=None keeps the historical marker-only behaviour."""
        content = '\n'.join(self._card(i, body_lines=100) for i in range(12))
        self.assertGreater(len(content), MAX_CHUNK_CHARS)
        chunks = chunk_content_by_events(content, events_per_chunk=50)
        self.assertEqual(len(chunks), 1)

    def test_size_cap_subdivides_dense_chunk(self):
        """Under the marker limit but over the byte limit -> still splits."""
        content = '\n'.join(self._card(i, body_lines=100) for i in range(12))
        chunks = chunk_content_by_events(content, events_per_chunk=50,
                                         max_chars=MAX_CHUNK_CHARS)
        self.assertGreater(len(chunks), 1)
        # Splitting only ever happens at a marker line, so no card is cut in half.
        for chunk in chunks:
            self.assertTrue(chunk.lstrip().startswith('### ['))

    def test_split_never_severs_a_single_oversized_event(self):
        """One event bigger than max_chars has no internal marker to split on."""
        content = self._card(0, body_lines=4000)
        self.assertGreater(len(content), MAX_CHUNK_CHARS)
        chunks = chunk_content_by_events(content, events_per_chunk=50,
                                         max_chars=MAX_CHUNK_CHARS)
        self.assertEqual(len(chunks), 1)

    def test_chunk_content_does_not_flip_method(self):
        """The size guard must not promote a size-chunked page to event-chunked.

        Method selection runs on the UNCAPPED split, so a page with too few
        markers keeps falling through to size-based chunking as before.
        """
        content = self._card(0, body_lines=4000) + '\n' + ('filler paragraph\n\n' * 2000)
        self.assertGreater(len(content), MAX_CHUNK_CHARS)
        _, method = chunk_content(content, 50, MAX_CHUNK_CHARS)
        self.assertEqual(method, 'size')

    def test_chunk_content_applies_cap_on_event_path(self):
        content = '\n'.join(self._card(i, body_lines=40) for i in range(120))
        chunks, method = chunk_content(content, 50, MAX_CHUNK_CHARS)
        self.assertEqual(method, 'events')
        # Marker-only chunking would have produced exactly 3 oversized chunks.
        self.assertGreater(len(chunks), 3)


class SimpleOccurrenceEndDateTests(unittest.TestCase):
    """The chunked first-pass schema must be able to express a run range.

    get_chunk_prompt instructs Gemini to return `end_date` for exhibitions, but
    the structured-output schema omitted the field, so the closing date was
    silently dropped and every ranged exhibition on a chunked page landed as a
    single-day event that archived the moment its opening date passed.
    """

    def test_end_date_field_exists(self):
        self.assertIn('end_date', SimpleOccurrence.model_fields)

    def test_end_date_round_trips(self):
        occ = SimpleOccurrence(start_date='2026-06-05', end_date='2026-08-18')
        self.assertEqual(occ.start_date, '2026-06-05')
        self.assertEqual(occ.end_date, '2026-08-18')

    def test_end_date_defaults_to_none(self):
        self.assertIsNone(SimpleOccurrence(start_date='2026-06-05').end_date)

    def test_end_date_uses_the_date_cleaner(self):
        """Same validator as start_date — junk values become None, not garbage."""
        self.assertIsNone(SimpleOccurrence(start_date='2026-06-05',
                                           end_date='ongoing').end_date)


if __name__ == '__main__':
    unittest.main()
