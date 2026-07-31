"""Tests for extractor.py reliability guards (variance retry, max_batches
auto-bump), the estimate_event_count page-size estimator, and the
fix_recurring_spans course-shape classifier."""

import asyncio
import importlib.util
import json
import os
import sys
import unittest
from datetime import date
from types import SimpleNamespace
from unittest import mock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import extractor
import re
import site_profiles
from extractor import (
    PreparedExtraction,
    SimpleOccurrence,
    _variance_retry_reason,
    _fingerprint_copy_is_suspect,
    _maybe_auto_bump_max_batches,
    _normalize_extraction_response,
    chunk_content,
    chunk_content_by_events,
    chunk_content_by_size,
    estimate_event_count,
    has_event_evidence,
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


def _last_nonblank(text):
    for line in reversed(text.split('\n')):
        if line.strip():
            return line
    return ''


class ChunkBySizeHeadingBoundaryTests(unittest.TestCase):
    """The SIZE path must never end a chunk on a markdown heading.

    `chunk_content_by_events` only recognises `### [` markers, so almost every
    real listing shape (bulleted `* ### [Title](url)`, `# [Title](url)`,
    unlinked `### Title`) falls through to `chunk_content_by_size`, which knows
    nothing about event records. Measured over 3 days of crawls, 24 chunk
    boundaries landed on a bare heading line across 15 websites: the event's
    name went to Gemini in one chunk and its date in the next, and the record
    came back with `occurrences: null` (Elsewhere w75 "Klingande", cr 108131).
    """

    HEADINGS = [
        '  * ### [Klingande](https://example.com/klingande)',   # bulleted (w75)
        '# [Rhythm & Booze](https://example.com/rb)',            # h1 link (Barbès w358)
        '#### [Late Show](https://example.com/late)',            # h4 link
        '### Members Preview',                                   # unlinked
        '1. ### [Numbered Show](https://example.com/n)',          # numbered
    ]

    @staticmethod
    def _record(heading, i):
        return (f'{heading}\n\n'
                f'**Fri, September {(i % 28) + 1}, 2026 at 6:00 PM**\n\n'
                f'{"Doors at 5. " * 20}\n')

    def _page(self, heading, n=400):
        return '\n\n'.join(self._record(heading, i) for i in range(n))

    def test_no_chunk_ends_on_a_heading(self):
        for heading in self.HEADINGS:
            with self.subTest(heading=heading):
                content = self._page(heading)
                self.assertGreater(len(content), MAX_CHUNK_CHARS)
                chunks = chunk_content_by_size(content, MAX_CHUNK_CHARS)
                self.assertGreater(len(chunks), 1)
                for chunk in chunks[:-1]:
                    self.assertFalse(
                        extractor._is_heading_line(_last_nonblank(chunk)),
                        f'chunk ended on a heading: {_last_nonblank(chunk)!r}')

    def test_orphaned_heading_leads_the_next_chunk(self):
        """The peeled heading must show up at the head of the next chunk, with
        its date line, not be dropped."""
        heading = '  * ### [Klingande](https://example.com/klingande)'
        # Pad so a boundary is forced to land right after a heading.
        body = '**Fri, September 4, 2026 at 6:00 PM**'
        # Sized so the filler + heading exactly fill a chunk and the date line
        # is what tips it over -- the Elsewhere w75 shape.
        filler = 'x' * (MAX_CHUNK_CHARS - len(heading) - 8)
        content = f'{filler}\n\n{heading}\n\n{body}\n\nmore text here'
        self.assertGreater(len(content), MAX_CHUNK_CHARS)
        self.assertEqual(_legacy_chunk_by_size(content, MAX_CHUNK_CHARS)[0][-len(heading):],
                         heading)  # the bug this test pins
        chunks = chunk_content_by_size(content, MAX_CHUNK_CHARS)
        self.assertGreater(len(chunks), 1)
        self.assertNotIn(heading, chunks[0])
        self.assertIn(heading, chunks[1])
        self.assertIn(body, chunks[1])

    def test_by_line_path_no_blank_lines(self):
        """The Alamo Brooklyn shape (cr 108283): a document with NO blank lines
        at all, so the whole page is one paragraph and the cap splits it BY
        LINE. That is what severed `### The Untouchables` from its
        `Showtimes: August 5, 2026 at 6:15pm` line."""
        lines = []
        for i in range(1200):
            lines.append(f'### The Untouchables {i}')
            lines.append(f'Federal Agent Eliot Ness. Showtimes: August {(i % 28) + 1}, 2026 at 6:15pm')
            lines.append('Rated R. 119 min. ' * 3)
        content = '\n'.join(lines)
        self.assertNotIn('\n\n', content)
        self.assertGreater(len(content), MAX_CHUNK_CHARS)
        chunks = chunk_content_by_size(content, MAX_CHUNK_CHARS)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks[:-1]:
            self.assertFalse(extractor._is_heading_line(_last_nonblank(chunk)))
        # Every heading keeps its showtime line in the same chunk.
        for chunk in chunks:
            lines = chunk.split('\n')
            for idx, line in enumerate(lines):
                if line.startswith('### The Untouchables'):
                    self.assertLess(idx + 1, len(lines), 'heading stranded at chunk end')
                    self.assertTrue(lines[idx + 1].startswith('Federal Agent'),
                                    f'showtime line severed from {line!r}')

    def test_content_is_preserved(self):
        content = self._page(self.HEADINGS[0])
        chunks = chunk_content_by_size(content, MAX_CHUNK_CHARS)
        self.assertEqual(re.sub(r'\s+', '', ''.join(chunks)),
                         re.sub(r'\s+', '', content))

    def test_true_negative_content_that_already_chunked_correctly(self):
        """A page whose boundaries never land on a heading must come out
        byte-for-byte identical to the pre-fix chunker."""
        paragraphs = []
        for i in range(600):
            paragraphs.append(f'Paragraph {i}. ' + ('lorem ipsum dolor sit amet ' * 12))
        content = '\n\n'.join(paragraphs)
        self.assertGreater(len(content), MAX_CHUNK_CHARS)
        chunks = chunk_content_by_size(content, MAX_CHUNK_CHARS)
        self.assertEqual(chunks, _legacy_chunk_by_size(content, MAX_CHUNK_CHARS))

    def test_small_content_untouched(self):
        content = 'short page\n\n### [Show](https://example.com/s)'
        self.assertEqual(chunk_content_by_size(content, MAX_CHUNK_CHARS), [content])

    def test_all_heading_chunk_is_not_dropped(self):
        """A run that is nothing BUT headings has nothing to keep — it must be
        emitted rather than carried forever."""
        content = '\n\n'.join(f'### [Show {i}](https://example.com/{i})'
                              for i in range(4000))
        chunks = chunk_content_by_size(content, MAX_CHUNK_CHARS)
        self.assertEqual(re.sub(r'\s+', '', ''.join(chunks)),
                         re.sub(r'\s+', '', content))


def _legacy_chunk_by_size(content, max_chars):
    """The pre-2026-07-31 chunk_content_by_size, for true-negative comparison."""
    if len(content) <= max_chars:
        return [content]
    chunks = []
    paragraphs = re.split(r'\n\n+', content)
    current_chunk = []
    current_size = 0
    for para in paragraphs:
        para_size = len(para) + 2
        if para_size > max_chars:
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_size = 0
            line_chunk = []
            line_size = 0
            for line in para.split('\n'):
                if line_size + len(line) + 1 > max_chars and line_chunk:
                    chunks.append('\n'.join(line_chunk))
                    line_chunk = []
                    line_size = 0
                line_chunk.append(line)
                line_size += len(line) + 1
            if line_chunk:
                chunks.append('\n'.join(line_chunk))
        elif current_size + para_size > max_chars and current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            current_chunk = [para]
            current_size = para_size
        else:
            current_chunk.append(para)
            current_size += para_size
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
    return chunks


class ChunkBySizeRecordBoundaryTests(unittest.TestCase):
    """Chunks must not end mid-record either — one line past the heading is the
    same bug (Alamo Brooklyn w3253 "Where is the Friend's House?": heading +
    synopsis closed the chunk, `Showtimes: August 21, 2026 at 12:30pm` opened the
    next one). Everything after a closing chunk's last heading is carried
    forward, so every chunk after the first starts at a record boundary.
    """

    @staticmethod
    def _record(i):
        return (f'### [Show {i}](https://example.com/show-{i})\n'
                f'A synopsis line that is long enough to matter. {"detail " * 12}\n'
                f'Showtimes: August {(i % 28) + 1}, 2026 at 6:15pm')

    def test_every_chunk_starts_at_a_record(self):
        content = '\n\n'.join(self._record(i) for i in range(400))
        chunks = chunk_content_by_size(content, MAX_CHUNK_CHARS)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks[1:]:
            self.assertTrue(extractor._is_heading_line(chunk.split('\n')[0]),
                            f'chunk did not start at a record: {chunk[:120]!r}')

    def test_showtime_line_never_leaves_its_heading(self):
        content = '\n\n'.join(self._record(i) for i in range(400))
        for chunk in chunk_content_by_size(content, MAX_CHUNK_CHARS):
            lines = [l for l in chunk.split('\n') if l.strip()]
            for idx, line in enumerate(lines):
                if line.startswith('### [Show '):
                    self.assertLess(idx + 2, len(lines) + 1)
                    self.assertTrue(
                        any(l.startswith('Showtimes:') for l in lines[idx + 1:idx + 3]),
                        f'record severed after {line!r}')

    def test_oversized_record_falls_back_to_heading_peel(self):
        """A record longer than the carry cap must not ping-pong whole chunks —
        it falls back to peeling just the heading."""
        cap = int(MAX_CHUNK_CHARS * extractor.CARRY_CAP_FRACTION)
        huge_tail = '\n'.join('body line ' * 8 for _ in range(2000))
        self.assertGreater(len(huge_tail), cap)
        content = ('### [Opening Act](https://example.com/a)\n' + huge_tail + '\n\n'
                   + huge_tail + '\n\n' + huge_tail)
        chunks = chunk_content_by_size(content, MAX_CHUNK_CHARS)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), MAX_CHUNK_CHARS)
        self.assertEqual(re.sub(r'\s+', '', ''.join(chunks)),
                         re.sub(r'\s+', '', content))

    def test_carry_never_pushes_a_chunk_over_the_cap(self):
        """A paragraph too big to share a chunk with the carry puts the carry
        back rather than overflowing."""
        heading = '### [Late Show](https://example.com/late)'
        record_tail = '\n'.join(f'detail line {i}' for i in range(200))
        filler = 'y' * (MAX_CHUNK_CHARS - len(heading) - len(record_tail) - 40)
        giant_para = 'z' * (MAX_CHUNK_CHARS - 100)
        content = (f'{filler}\n\n{heading}\n{record_tail}\n\n{giant_para}\n\ntail')
        chunks = chunk_content_by_size(content, MAX_CHUNK_CHARS)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), MAX_CHUNK_CHARS)
        self.assertEqual(re.sub(r'\s+', '', ''.join(chunks)),
                         re.sub(r'\s+', '', content))

    def test_split_trailing_record_helper(self):
        cap = 10_000
        text = ('intro\n### [A](u)\nbody of A\n### [B](u)\nbody of B')
        kept, carried = extractor._split_trailing_record(text, cap)
        self.assertEqual(kept, 'intro\n### [A](u)\nbody of A')
        self.assertEqual(carried, '### [B](u)\nbody of B')

    def test_split_trailing_record_carries_the_heading_run(self):
        """A section banner travels with the record it introduces."""
        text = 'intro\n### [A](u)\nbody\n## Wednesday\n### [B](u)\nbody of B'
        kept, carried = extractor._split_trailing_record(text, 10_000)
        self.assertEqual(kept, 'intro\n### [A](u)\nbody')
        self.assertEqual(carried, '## Wednesday\n### [B](u)\nbody of B')

    def test_split_trailing_record_no_heading(self):
        text = 'just\nplain\nlines'
        self.assertEqual(extractor._split_trailing_record(text, 10_000), (text, ''))

    def test_split_trailing_record_heading_first_line(self):
        """Nothing to keep -> no carry (the chunk IS one record)."""
        text = '### [A](u)\nbody of A'
        self.assertEqual(extractor._split_trailing_record(text, 10_000), (text, ''))


class ChunkBySizeOversizedLineTests(unittest.TestCase):
    """A single line longer than max_chars used to become one whole chunk.

    Measured over crawl run 293+: Skinny Dennis w4832 handed Gemini a single
    303,877-char chunk (a minified `?format=json` calendar dump on one line)
    and got 3 events back; Climate Cafe w489 178,332; Columbia w708 176,239.
    """

    def test_single_giant_line_is_split(self):
        line = 'word ' * 40000  # ~200K on one line
        content = f'intro paragraph\n\n{line}\n\ntail paragraph'
        chunks = chunk_content_by_size(content, MAX_CHUNK_CHARS)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), MAX_CHUNK_CHARS)
        self.assertEqual(re.sub(r'\s+', '', ''.join(chunks)),
                         re.sub(r'\s+', '', content))

    def test_minified_json_splits_between_records(self):
        """The real shape of these pages: one line of minified JSON. Cuts should
        land between records (`},{`) rather than mid-object."""
        records = ','.join(
            '{"id":%d,"name":"Event %d","startDate":"2026-08-%02d","description":"%s"}'
            % (i, i, (i % 28) + 1, 'x' * 400)
            for i in range(200))
        line = '{"events":[' + records + ']}'
        content = f'https://example.com/calendar?format=json\n\n{line}'
        self.assertGreater(len(line), MAX_CHUNK_CHARS)
        chunks = chunk_content_by_size(content, MAX_CHUNK_CHARS)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), MAX_CHUNK_CHARS)
        # Every chunk after the first starts a fresh JSON object.
        for chunk in chunks[1:]:
            self.assertTrue(chunk.lstrip().startswith('{'), chunk[:80])
        self.assertEqual(re.sub(r'\s+', '', ''.join(chunks)),
                         re.sub(r'\s+', '', content))

    def test_unbreakable_line_still_capped(self):
        """No whitespace and no record boundary (a 300K URL): hard-cut rather
        than emit an oversized chunk."""
        line = 'https://example.com/x?' + ('a' * 120000)
        content = f'intro\n\n{line}'
        chunks = chunk_content_by_size(content, MAX_CHUNK_CHARS)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), MAX_CHUNK_CHARS)
        self.assertEqual(''.join(chunks).replace('\n', ''),
                         content.replace('\n', ''))

    def test_normal_lines_are_not_split(self):
        content = '\n\n'.join('a normal line of text ' * 20 for _ in range(400))
        chunks = chunk_content_by_size(content, MAX_CHUNK_CHARS)
        self.assertEqual(chunks, _legacy_chunk_by_size(content, MAX_CHUNK_CHARS))


class HeadingLineDetectionTests(unittest.TestCase):
    """_is_heading_line is deliberately broader than _EVENT_HEADING_RE."""

    def test_recognised_shapes(self):
        for line in ['# [T](u)', '## [T](u)', '### [T](u)', '#### [T](u)',
                     '##### T', '  * ### [T](u)', '1. ### [T](u)',
                     '- ## [T](u)', '\t### T']:
            self.assertTrue(extractor._is_heading_line(line), line)

    def test_non_headings(self):
        for line in ['plain text', '**Fri, September 4, 2026 at 6:00 PM**',
                     '###notaheading', '', '   ', 'a # b',
                     '####### seven hashes is not a heading']:
            self.assertFalse(extractor._is_heading_line(line), line)


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


class TestParseExtractionDirectives(unittest.TestCase):
    """`[[extraction: ...]]` lines in websites.notes are machine directives, not
    guidance — they must be parsed out AND stripped before the notes reach a
    prompt."""

    def test_no_directive_returns_notes_unchanged(self):
        notes = "Uses Eventbrite for event listings"
        self.assertEqual(extractor.parse_extraction_directives(notes), (set(), notes))

    def test_empty_notes(self):
        self.assertEqual(extractor.parse_extraction_directives(''), (set(), ''))
        self.assertEqual(extractor.parse_extraction_directives(None), (set(), ''))

    def test_directive_is_parsed_and_line_removed(self):
        notes = ("Uses Eventbrite for event listings.\n"
                 "[[extraction: force-chunked]] ~30 API cards at 43 KB sit just under "
                 "LARGE_PAGE_THRESHOLD.\n"
                 "Ignore the past-events archive.")
        directives, cleaned = extractor.parse_extraction_directives(notes)
        self.assertEqual(directives, {extractor.FORCE_CHUNKED_DIRECTIVE})
        self.assertNotIn('[[extraction', cleaned)
        self.assertNotIn('LARGE_PAGE_THRESHOLD', cleaned)  # rationale goes too
        self.assertIn('Uses Eventbrite for event listings.', cleaned)
        self.assertIn('Ignore the past-events archive.', cleaned)

    def test_tokens_are_normalised_and_comma_separated(self):
        directives, cleaned = extractor.parse_extraction_directives(
            "[[Extraction:  Force_Chunked , something-else ]]")
        self.assertEqual(directives, {'force-chunked', 'something-else'})
        self.assertEqual(cleaned, '')

    def test_unknown_token_degrades_to_no_override(self):
        """A typo must not force a mode or raise — callers test membership."""
        directives, _ = extractor.parse_extraction_directives("[[extraction: force-chunkd]]")
        self.assertNotIn(extractor.FORCE_CHUNKED_DIRECTIVE, directives)


class TestForceChunkedDirective(unittest.TestCase):
    """w950 Nook: ~30 Eventbrite-API cards, estimate 32-34 (< LARGE_PAGE_THRESHOLD)
    on 43 KB (< MAX_CHUNK_CHARS * 2) routed the page to a SINGLE call whose output
    budget cannot hold 30 events, so extracted_content collapsed 28,254 -> 7,290 ->
    8,383 chars across three crawls. The directive names the site instead of moving
    the heuristic's cliff for everyone."""

    @staticmethod
    def _content(n_cards=30):
        card = ("### [Tour of the Nook {i}](https://www.eventbrite.com/e/{i})\n"
                "**Date**: 2026-08-{d:02d}\n**Start**: 7:00 PM\n"
                "**Venue**: Nook, Brooklyn NY\n"
                + ("Filler copy about the show. " * 45) + "\n"
                "EVENT DETAIL URL: https://www.eventbrite.com/e/{i}\n\n---\n")
        return "https://www.eventbrite.com/o/nook-34738528343\n" + "".join(
            card.format(i=i, d=(i % 28) + 1) for i in range(n_cards))

    def _prepare(self, notes):
        content = self._content()
        # Guard the premise: this page really is in the danger band.
        self.assertLessEqual(estimate_event_count(content), LARGE_PAGE_THRESHOLD)
        self.assertLess(len(content), MAX_CHUNK_CHARS * 2)

        class FakeDb:
            @staticmethod
            def get_crawled_content(cursor, crid):
                return content

            @staticmethod
            def find_prior_crawl_with_same_content(cursor, crid):
                return None

            @staticmethod
            def get_existing_upcoming_events(cursor, website_id):
                return []

        with mock.patch.object(extractor, 'db', FakeDb), \
             mock.patch.object(extractor.site_profiles, 'resolve_notes',
                               lambda base_url, n: n or ''):
            return asyncio.run(extractor.prepare_extraction(
                FakeCursor((950, None), []), 77, 'Nook', notes=notes,
                base_url='https://www.eventbrite.com/o/nook-34738528343'))

    def test_without_directive_the_danger_band_page_goes_single_call(self):
        self.assertEqual(self._prepare('Uses Eventbrite for event listings').extraction_type,
                         'single')

    def test_directive_forces_chunked_extraction(self):
        prep = self._prepare('Uses Eventbrite for event listings\n'
                             '[[extraction: force-chunked]] collapses in single-call mode')
        self.assertEqual(prep.extraction_type, 'chunked')
        self.assertGreater(len(prep.chunk_prompts), 0)

    def test_directive_text_never_reaches_the_prompt(self):
        prep = self._prepare('Uses Eventbrite for event listings\n'
                             '[[extraction: force-chunked]] collapses in single-call mode')
        self.assertNotIn('[[extraction', prep.notes)
        self.assertIn('Uses Eventbrite', prep.notes)
        for prompt in prep.chunk_prompts:
            self.assertNotIn('[[extraction', prompt)

    def test_records_cap_directive_subdivides_and_stays_out_of_the_prompt(self):
        prep = self._prepare('Uses Eventbrite for event listings\n'
                             '[[extraction: force-chunked, max-records-per-chunk=10]] dense cards')
        self.assertEqual(prep.extraction_type, 'chunked')
        # 30 cards, capped at 10 per chunk -> at least 3 prompts.
        self.assertGreaterEqual(len(prep.chunk_prompts), 3)
        for prompt in prep.chunk_prompts:
            self.assertNotIn('[[extraction', prompt)

    def test_without_the_records_cap_the_same_page_is_not_subdivided(self):
        """True negative: the cap is opt-in, so the default path is unchanged."""
        plain = self._prepare('Uses Eventbrite for event listings\n'
                              '[[extraction: force-chunked]] dense cards')
        capped = self._prepare('Uses Eventbrite for event listings\n'
                               '[[extraction: force-chunked, max-records-per-chunk=10]] dense')
        self.assertLess(len(plain.chunk_prompts), len(capped.chunk_prompts))


class TestRecordsPerChunkOverride(unittest.TestCase):
    """`max-records-per-chunk=N` parsing. A malformed value must degrade to
    "no override" like every other directive, never raise."""

    def test_parsed(self):
        directives, _ = extractor.parse_extraction_directives(
            '[[extraction: max-records-per-chunk=25]]')
        self.assertEqual(extractor.records_per_chunk_override(directives), 25)

    def test_absent(self):
        directives, _ = extractor.parse_extraction_directives('[[extraction: force-chunked]]')
        self.assertIsNone(extractor.records_per_chunk_override(directives))

    def test_alongside_other_directives(self):
        directives, _ = extractor.parse_extraction_directives(
            '[[extraction: force-chunked, max_records_per_chunk=12]]')
        self.assertIn(extractor.FORCE_CHUNKED_DIRECTIVE, directives)
        self.assertEqual(extractor.records_per_chunk_override(directives), 12)

    def test_malformed_values_degrade(self):
        for bad in ('max-records-per-chunk=', 'max-records-per-chunk=abc',
                    'max-records-per-chunk=0', 'max-records-per-chunk=-5',
                    'max-records-per-chunk'):
            directives, _ = extractor.parse_extraction_directives(f'[[extraction: {bad}]]')
            self.assertIsNone(extractor.records_per_chunk_override(directives), bad)


class CapRecordsPerChunkTests(unittest.TestCase):
    """The records cap subdivides an output-heavy chunk at record boundaries.

    A chunk's response size scales with its record COUNT, not its char count:
    Film Forum w50 packs 50 dated showtime cards into 8,426 chars and three films
    (AMERICAN PACHUCO, THE THIRD MAN, WHITE NIGHTS) only come back when that
    chunk is split. Measured global cost is why this is opt-in — see
    RECORDS_PER_CHUNK_DIRECTIVE.
    """

    @staticmethod
    def _records(n, prefix='### [Film {i}](https://example.com/{i})'):
        return '\n'.join(
            (prefix + '\nShowtimes: August {d}, 2026 at 6:15pm\nRated R.').format(
                i=i, d=(i % 28) + 1)
            for i in range(n))

    def test_dense_chunk_is_subdivided(self):
        chunks = [self._records(50)]
        out = extractor.cap_records_per_chunk(chunks, 25)
        self.assertEqual(len(out), 2)
        for piece in out:
            n = sum(1 for l in piece.split('\n') if extractor._is_heading_line(l))
            self.assertLessEqual(n, 25)

    def test_pieces_are_balanced(self):
        out = extractor.cap_records_per_chunk([self._records(50)], 30)
        counts = [sum(1 for l in p.split('\n') if extractor._is_heading_line(l))
                  for p in out]
        self.assertEqual(counts, [25, 25])  # not 30/20

    def test_split_only_ever_happens_at_a_heading(self):
        out = extractor.cap_records_per_chunk([self._records(50)], 10)
        for piece in out[1:]:
            self.assertTrue(extractor._is_heading_line(piece.split('\n')[0]))
        for piece in out[:-1]:
            self.assertFalse(extractor._is_heading_line(_last_nonblank(piece)))

    def test_content_is_preserved(self):
        content = self._records(50)
        out = extractor.cap_records_per_chunk([content], 7)
        self.assertEqual(re.sub(r'\s+', '', ''.join(out)),
                         re.sub(r'\s+', '', content))

    def test_sparse_chunks_are_returned_unchanged(self):
        """True negative: content already under the cap is untouched, object
        identity and all."""
        chunks = [self._records(9), self._records(3)]
        self.assertEqual(extractor.cap_records_per_chunk(chunks, 25), chunks)

    def test_no_cap_is_a_passthrough(self):
        chunks = [self._records(80)]
        self.assertIs(extractor.cap_records_per_chunk(chunks, None), chunks)
        self.assertIs(extractor.cap_records_per_chunk(chunks, 0), chunks)

    def test_never_exceeds_max_chars_or_severs_after_chunk_content(self):
        """Composes with the size path: the cap only ever shrinks chunks, so the
        carry's guarantees survive it."""
        # Bulleted headings: invisible to chunk_content_by_events' narrow marker,
        # so this page really does take the size path (the Elsewhere w75 shape).
        content = '\n\n'.join(
            f'  * ### [Show {i}](https://example.com/{i})\n'
            f'**Fri, September {(i % 28) + 1}, 2026 at 6:00 PM**\n'
            + ('Doors at five. ' * 20)
            for i in range(600))
        chunks, method = chunk_content(content, 50, MAX_CHUNK_CHARS)
        self.assertEqual(method, 'size')
        capped = extractor.cap_records_per_chunk(chunks, 10)
        self.assertGreater(len(capped), len(chunks))
        for piece in capped:
            self.assertLessEqual(len(piece), MAX_CHUNK_CHARS)
        for piece in capped[:-1]:
            self.assertFalse(extractor._is_heading_line(_last_nonblank(piece)))
        for piece in capped[1:]:
            self.assertTrue(extractor._is_heading_line(piece.split('\n')[0]))
        self.assertEqual(re.sub(r'\s+', '', ''.join(capped)),
                         re.sub(r'\s+', '', ''.join(chunks)))


class TestNoEventsVetoEvidenceGuard(unittest.TestCase):
    """`prepare_extraction`'s "no events" short-circuit is a PAGE-level veto:
    one empty widget anywhere in the first 15K chars suppresses the whole
    document, Gemini is never called, and the crawl is stored as a healthy
    0-event result.

    Regression: w618 Freshkills renders a populated Tribe widget followed by an
    empty embedded Eventbrite widget whose i18n string is "No Upcoming Events at
    this time." — four consecutive good crawls (100144, 101658, 103843, …) were
    discarded before a per-site js_code workaround landed on 2026-07-26.

    `has_event_evidence` is the guard: the veto may only fire when the page
    shows no positive sign of real events.
    """

    TODAY = date(2026, 7, 20)

    # Verbatim shape of the Freshkills page: three dated Tribe cards, then an
    # empty Eventbrite widget.
    FRESHKILLS = (
        "# Upcoming Events\n"
        "Sat 25\n###  Terrapin Workshop w/ Staten Island Zoo \n"
        "July 25, 2026 @ 10:00 am - 12:00 pm \n"
        "Sat 25\n###  City of Water Day: Wings Over Water Walk \n"
        "July 25, 2026 @ 11:00 am - 1:00 pm \n"
        "Sat 25\n###  City of Water Day Kayak Tour \n"
        "July 25, 2026 @ 5:00 pm - 8:00 pm \n"
        "# Upcoming Events\n### No Upcoming Events at this time.\n"
    )

    # A genuinely empty calendar: navigation, a past-events archive, a footer.
    EMPTY_PAGE = (
        "# Events\nThere are no upcoming events.\n"
        "## Past events\nMarch 4, 2019 — Annual Meeting\n"
        "January 12, 2020 — Winter Social\n"
        "© 2026 Some Organization. All rights reserved.\n"
    )

    def _evidence(self, content):
        return has_event_evidence(content, today=self.TODAY)

    def test_populated_widget_beats_the_empty_one(self):
        self.assertTrue(self._evidence(self.FRESHKILLS))

    def test_genuinely_empty_page_has_no_evidence(self):
        self.assertFalse(self._evidence(self.EMPTY_PAGE))

    def test_detail_url_markers_count_as_evidence(self):
        self.assertTrue(self._evidence(
            "No upcoming events\nEVENT DETAIL URL: https://example.org/e/1\n"))

    def test_populated_squarespace_json_still_counts(self):
        # The pre-existing narrow escape hatch must keep working.
        self.assertTrue(self._evidence(
            '{"upcoming":[{"title":"A Show"}],'
            '"msg":"There are no upcoming events at this time."}'))

    def test_a_single_stray_future_date_is_not_evidence(self):
        self.assertFalse(self._evidence(
            "No upcoming events scheduled. Our next season is announced on "
            "December 1, 2026."))

    def test_iso_and_numeric_dates_count(self):
        self.assertTrue(self._evidence(
            "No events scheduled\n2026-08-04 Opening\n2026-08-11 Closing\n"))
        self.assertTrue(self._evidence(
            "No events scheduled\n8/4/2026 Opening\n8/11/2026 Closing\n"))

    def test_only_past_dates_are_not_evidence(self):
        self.assertFalse(self._evidence(
            "No upcoming events\nArchive: June 1, 2019 / June 8, 2019 / "
            "June 15, 2019 / 2020-01-01\n"))

    def test_repeated_same_day_cards_count(self):
        # Freshkills' three cards all fall on one date — distinctness must not
        # be required, only the number of dated mentions.
        self.assertTrue(self._evidence(
            "No upcoming events\nJuly 25, 2026 @ 10:00 am\nJuly 25, 2026 @ 5:00 pm\n"))

    def test_empty_content_is_safe(self):
        self.assertFalse(self._evidence(''))
        self.assertFalse(self._evidence(None))


# ---------------------------------------------------------------------------
# "All chunks failed" must not be stored as a healthy zero
# ---------------------------------------------------------------------------

class _FakeModels:
    """Stands in for genai_client.aio.models with scripted per-call outcomes."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def generate_content(self, **kwargs):
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome)


class _FakeGenaiClient:
    def __init__(self, outcomes):
        self.aio = SimpleNamespace(models=_FakeModels(outcomes))


class ChunkedFailureTestBase(unittest.TestCase):

    def _prep(self, chunks=3):
        prep = PreparedExtraction(crawl_result_id=99, website_name='Test Site',
                                  extraction_type='chunked')
        prep.max_batches = 3
        prep.website_id = 7
        prep.content = 'content'
        prep.chunk_prompts = [f'chunk prompt {i}' for i in range(chunks)]
        return prep

    def _run_chunked(self, outcomes, chunks=3):
        async def _noop_enrich(names, website_name, content=None):
            return {}
        with mock.patch.object(extractor, 'genai_client', _FakeGenaiClient(outcomes)), \
             mock.patch.object(extractor, 'enrich_events_batch', _noop_enrich):
            return asyncio.run(extractor._execute_chunked_sync(self._prep(chunks)))


class TestChunkedExtractionFailureIsNotAZero(ChunkedFailureTestBase):
    """A ~2-minute Gemini outage on 2026-07-21 stored 21 crawl_results across 15
    websites as status='processed', event_count=0 — wiping their last good crawl
    and leaving them days stale. Every chunk had raised."""

    def test_all_chunks_erroring_raises(self):
        with self.assertRaises(extractor.ChunkedExtractionFailure):
            self._run_chunked([RuntimeError('503 Service Unavailable')])

    def test_all_chunks_timing_out_raises(self):
        with self.assertRaises(extractor.ChunkedExtractionFailure):
            self._run_chunked([asyncio.TimeoutError()])

    def test_genuinely_empty_chunks_still_return_an_empty_result(self):
        """An empty calendar is a real answer — it must stay a healthy zero."""
        result = self._run_chunked(['{"events": []}'])
        self.assertEqual(json.loads(result), {"events": []})

    def test_zero_events_with_one_erroring_chunk_raises(self):
        """A zero assembled from a partly-errored run proves nothing about the page."""
        with self.assertRaises(extractor.ChunkedExtractionFailure):
            self._run_chunked([RuntimeError('503'), '{"events": []}', '{"events": []}'])

    def test_events_from_a_surviving_chunk_are_kept(self):
        event = ('{"events": [{"name": "Concert", "location": "Venue", '
                 '"occurrences": [{"start_date": "2026-08-01"}], "url": null}]}')
        result = self._run_chunked([RuntimeError('503'), event, '{"events": []}'])
        self.assertEqual(len(json.loads(result)['events']), 1)

    def test_error_message_names_the_failure(self):
        with self.assertRaises(extractor.ChunkedExtractionFailure) as ctx:
            self._run_chunked([RuntimeError('503 Service Unavailable')])
        self.assertIn('503', str(ctx.exception))


class TestVisionExtractionFailureIsNotAZero(unittest.TestCase):
    """Same defect class on the vision path: the API error was swallowed and
    stored as an empty extraction."""

    def _prep(self):
        prep = PreparedExtraction(crawl_result_id=99, website_name='Test Site',
                                  extraction_type='vision')
        prep.vision_contents = ['prompt']
        return prep

    def test_vision_api_error_raises(self):
        with mock.patch.object(extractor, 'genai_client',
                               _FakeGenaiClient([RuntimeError('503')])):
            with self.assertRaises(extractor.ExtractionCallFailure):
                asyncio.run(extractor._generate_extraction_response(self._prep(), None, None))


class TestExtractEventsMarksTheCrawlFailed(unittest.TestCase):
    """The failure must reach the DB as status='failed' (which preserves
    crawled_content for same-day `main.py --ids` recovery) rather than as a
    successful empty extraction."""

    def test_chunk_failure_is_stored_as_failed(self):
        recorded = {}

        class FakeDb:
            @staticmethod
            def update_crawl_result_failed(cursor, connection, crid, message):
                recorded['crid'] = crid
                recorded['message'] = message

            @staticmethod
            def update_crawl_result_extracted(*args, **kwargs):
                recorded['extracted'] = args

        async def _prepare(*args, **kwargs):
            prep = PreparedExtraction(crawl_result_id=42, website_name='Test Site',
                                      extraction_type='chunked')
            return prep

        async def _execute(cursor, connection, prep):
            raise extractor.ChunkedExtractionFailure('all 4 chunk request(s) failed: 503')

        with mock.patch.object(extractor, 'db', FakeDb), \
             mock.patch.object(extractor, 'prepare_extraction', _prepare), \
             mock.patch.object(extractor, 'execute_extraction_sync', _execute), \
             mock.patch.object(extractor, 'GEMINI_API_KEY', 'key'), \
             mock.patch.object(extractor, 'genai_client', object()):
            ok = asyncio.run(extractor.extract_events(None, None, 42, 'Test Site'))

        self.assertFalse(ok)
        self.assertEqual(recorded.get('crid'), 42)
        self.assertIn('503', recorded.get('message', ''))
        self.assertNotIn('extracted', recorded)


class TestBatchPathChunkFailures(unittest.TestCase):
    """The batch path had the same hole: a chunked crawl result whose chunk
    responses all errored was stored as '{"events": []}'."""

    def _prep(self, crid, extraction_type='chunked'):
        prep = PreparedExtraction(crawl_result_id=crid, website_name=f'Site {crid}',
                                  extraction_type=extraction_type)
        prep.max_batches = 3
        return prep

    def _request(self, crid, chunk_index=0):
        return SimpleNamespace(metadata={
            'crawl_result_id': str(crid),
            'type': 'chunk',
            'chunk_index': str(chunk_index),
            'website_name': f'Site {crid}',
            'request_id': f'cr-{crid}-chunk-{chunk_index}',
        })

    def _error_response(self, message='503 Service Unavailable'):
        return SimpleNamespace(error=SimpleNamespace(message=message), response=None)

    def _ok_response(self, crid, chunk_index=0, events='[]'):
        text = ('{"request_id": "cr-%d-chunk-%d", "events": %s}'
                % (crid, chunk_index, events))
        return SimpleNamespace(error=None, response=SimpleNamespace(text=text))

    def test_all_chunk_responses_errored_is_reported_as_failed(self):
        preparations = {5: self._prep(5)}
        requests = [self._request(5, 0), self._request(5, 1)]
        responses = [self._error_response(), self._error_response()]
        single, chunked, failed = extractor.process_batch_responses(
            requests, responses, preparations)
        self.assertNotIn(5, single)
        self.assertIn(5, failed)

    def test_chunks_that_answered_empty_are_not_a_failure(self):
        preparations = {5: self._prep(5)}
        requests = [self._request(5, 0)]
        responses = [self._ok_response(5, 0, events='[]')]
        single, chunked, failed = extractor.process_batch_responses(
            requests, responses, preparations)
        self.assertEqual(failed, {})
        self.assertEqual(chunked.get(5), [])

    def test_failed_crids_are_written_as_failed_not_stored(self):
        stored, failed_marks = [], []

        class FakeDb:
            @staticmethod
            def create_connection():
                return SimpleNamespace(cursor=lambda **kw: SimpleNamespace(close=lambda: None),
                                       close=lambda: None)

            @staticmethod
            def update_crawl_result_extracted(cursor, conn, crid, text):
                stored.append(crid)

            @staticmethod
            def update_crawl_result_failed(cursor, conn, crid, message):
                failed_marks.append((crid, message))

            @staticmethod
            def clear_batch_job_name(cursor, conn, crids):
                pass

        with mock.patch.object(extractor, 'db', FakeDb):
            results = extractor._store_batch_results(
                {1: '{"events": []}'}, [1, 5], failed_crids={5: 'chunk failure'})

        self.assertEqual(stored, [1])
        self.assertEqual(failed_marks, [(5, 'chunk failure')])
        self.assertIn((5, False), results)


class TestPerProfileMaxContentChars(unittest.TestCase):
    """`MAX_CONTENT_CHARS` guards against runaway extraction on HTML pages that
    carry years of archives. A structured API source builds its own payload, so
    the same truncation just silently drops real events: RA's 90-day NYC feed is
    ~620K chars (977 events) and was cut to 300K, losing half - and ~22% even at
    the old 30-day window. The override lets such a source raise it without
    weakening the default for everyone else.
    """

    def test_default_applies_to_unknown_host(self):
        self.assertEqual(
            site_profiles.max_content_chars_for('https://example.org/events', 300000), 300000)

    def test_none_url_falls_back_to_default(self):
        self.assertEqual(site_profiles.max_content_chars_for(None, 300000), 300000)

    def test_profile_override_wins(self):
        prof = site_profiles.SiteProfile(
            name='t', host_re=re.compile(r'^bigfeed\.test$'), max_content_chars=900000)
        site_profiles.PROFILES.append(prof)
        try:
            self.assertEqual(
                site_profiles.max_content_chars_for('https://bigfeed.test/x', 300000), 900000)
        finally:
            site_profiles.PROFILES.remove(prof)

    def test_profile_without_override_uses_default(self):
        prof = site_profiles.SiteProfile(
            name='t2', host_re=re.compile(r'^plainfeed\.test$'))
        site_profiles.PROFILES.append(prof)
        try:
            self.assertEqual(
                site_profiles.max_content_chars_for('https://plainfeed.test/x', 300000), 300000)
        finally:
            site_profiles.PROFILES.remove(prof)


class TestPerWebsiteMaxContentChars(unittest.TestCase):
    """Plain `websites` rows (no source plugin) hit the same silent loss: BPL,
    NYC Parks, NYPL and New York Cares all crawl past 300K and had their tails —
    real event cards — dropped before Gemini ever saw them. `websites.
    max_content_chars` is the per-site override for those, and it wins over the
    plugin default because it is the more specific decision. It may also be set
    BELOW the default (a payload that duplicates itself is not worth paying for
    twice).
    """

    def test_website_override_raises_the_default(self):
        self.assertEqual(
            site_profiles.max_content_chars_for('https://example.org/events', 300000, 800000),
            800000)

    def test_website_override_can_lower_the_default(self):
        self.assertEqual(
            site_profiles.max_content_chars_for('https://example.org/events', 300000, 120000),
            120000)

    def test_website_override_beats_profile_override(self):
        prof = site_profiles.SiteProfile(
            name='t3', host_re=re.compile(r'^bothfeed\.test$'), max_content_chars=700000)
        site_profiles.PROFILES.append(prof)
        try:
            self.assertEqual(
                site_profiles.max_content_chars_for('https://bothfeed.test/x', 300000, 450000),
                450000)
        finally:
            site_profiles.PROFILES.remove(prof)

    def test_null_website_override_falls_back_to_profile_then_default(self):
        prof = site_profiles.SiteProfile(
            name='t4', host_re=re.compile(r'^feedonly\.test$'), max_content_chars=700000)
        site_profiles.PROFILES.append(prof)
        try:
            # NULL column (the common case) leaves the profile in charge...
            self.assertEqual(
                site_profiles.max_content_chars_for('https://feedonly.test/x', 300000, None),
                700000)
            # ...and a plain site with neither keeps the global default.
            self.assertEqual(
                site_profiles.max_content_chars_for('https://example.org/x', 300000, None),
                300000)
        finally:
            site_profiles.PROFILES.remove(prof)

    def test_prepare_extraction_truncates_at_the_websites_column(self):
        """End-to-end wiring: the column travels from `websites` to the cut."""
        content = ''.join(f'### [Event {i}](https://plain.test/e/{i})\nAugust {i % 28 + 1}, 2026 '
                          f'at Some Venue. {"filler " * 40}\n\n' for i in range(1200))
        self.assertGreater(len(content), 400000)

        class FakeDb:
            @staticmethod
            def get_crawled_content(cursor, crid):
                return content

            @staticmethod
            def find_prior_crawl_with_same_content(cursor, crid):
                return None

        class FakeCursor:
            """Answers the (website_id, max_content_chars) lookup."""
            def execute(self, sql, params=None):
                pass

            def fetchone(self):
                return (4, 400000)

            def fetchall(self):
                return []

        with mock.patch.object(extractor, 'db', FakeDb):
            prep = asyncio.run(extractor.prepare_extraction(
                FakeCursor(), 1, 'Plain Site', base_url='https://plain.test/events',
                max_batches=30))

        self.assertIsNone(prep.error)
        self.assertEqual(prep.extraction_type, 'chunked')
        self.assertEqual(len(prep.content), 400000)


if __name__ == '__main__':
    unittest.main()
