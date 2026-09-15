"""Tests for scripts/fix_recurring_spans.py's cadence generator.

Ground truth comes from the 2026-08-03 /run-pipeline date-shape pass, where the
script correctly deleted a 186-day envelope on ev196587 "Mahjong Parlor" and
then INVENTED a date the source never published:

    source (Eventbrite crawl_events 1070414):  7/24, 8/21, 9/18  — 28-day Fridays
    generated (nth-weekday-of-month):          7/24, 8/28        — 4th Friday

Both readings explain 7/24, but only the 28-day one explains 8/21 and 9/18. The
generator picked the calendar-monthly model, so `--apply` inserted a 2026-08-28
occurrence that does not exist. The two defences below:

  * a `four_weekly` verdict (step 28) that fires before `monthly` when every
    observed gap is a multiple of 7 and the median is ~28;
  * an evidence guard — a cadence model whose generated series fails to explain
    an observed date is refused outright, so no fabricated occurrence is written.

The guard must NOT block filling an observed GAP (a weekly series that missed a
week is still weekly), which is the whole point of the tool.
"""

import datetime as dt
import importlib.util
import os
import sys
import unittest

# Repo root, three levels up: pipeline/tests/this_file.py
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(_ROOT, 'pipeline'))

_spec = importlib.util.spec_from_file_location(
    'fix_recurring_spans',
    os.path.join(_ROOT, 'scripts', 'fix_recurring_spans.py'))
frs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(frs)


def _occ(start, end=None, start_time='19:00:00', end_time='21:00:00'):
    return {'start_date': dt.date.fromisoformat(start),
            'end_date': dt.date.fromisoformat(end) if end else None,
            'start_time': start_time, 'end_time': end_time}


def _points(*dates):
    return [_occ(d) for d in dates]


class TestFourWeeklyCadence(unittest.TestCase):
    """ev196587 "Mahjong Parlor": 28-day Fridays + the envelope that blanketed them."""

    # 7/24, 8/21, 9/18 are Fridays 28 days apart; the span is the envelope.
    MAHJONG = _points('2026-07-24', '2026-08-21', '2026-09-18') + [
        _occ('2026-03-16', '2026-09-18')]

    def test_classified_as_four_weekly_not_monthly(self):
        verdict, _ = frs.classify(196587, 'Mahjong Parlor', self.MAHJONG)
        self.assertEqual(verdict, 'four_weekly')

    def test_generator_does_not_invent_a_calendar_month_date(self):
        """The regression: 2026-08-28 (4th Friday of August) must never appear."""
        verdict, info = frs.classify(196587, 'Mahjong Parlor', self.MAHJONG)
        dates = frs.planned_dates(verdict, info)
        self.assertNotIn(dt.date(2026, 8, 28), dates)
        self.assertEqual(dates, [dt.date(2026, 7, 24), dt.date(2026, 8, 21),
                                 dt.date(2026, 9, 18)])

    def test_nth_weekday_generator_would_have_invented_it(self):
        """Pins WHY this test exists: the old model really does produce 8/28."""
        old = frs.gen_monthly_nth_weekday(
            dt.date(2026, 7, 24), 4, frs.nth_weekday(dt.date(2026, 7, 24)),
            dt.date(2026, 9, 18))
        self.assertIn(dt.date(2026, 8, 28), old)


class TestEvidenceGuard(unittest.TestCase):
    """A cadence that cannot explain an observed date is refused, not applied."""

    def test_monthly_model_contradicting_observed_dates_is_skipped(self):
        # Same shape as Mahjong but with a gap pattern that lands in the monthly
        # band (35, 28 -> median 31.5), where nth-weekday-of-month is generated.
        # 3rd Thursdays: 7/16, 8/20, 9/17 — the model explains all three.
        occ = _points('2026-07-16', '2026-08-20', '2026-09-17') + [
            _occ('2026-03-01', '2026-09-17')]
        verdict, info = frs.classify(1, 'Monthly Book Club', occ)
        self.assertEqual(verdict, 'monthly')
        self.assertEqual(frs.unexplained_observed(verdict, info), [])

    def test_unexplained_observed_reports_the_contradiction(self):
        info = {'disc': [dt.date(2026, 7, 24), dt.date(2026, 8, 21),
                         dt.date(2026, 9, 18)],
                'wd': 4, 'span_start': dt.date(2026, 3, 16),
                'span_end': dt.date(2026, 9, 18), 'time': ('19:00:00', '21:00:00')}
        missing = frs.unexplained_observed('monthly', info)
        self.assertEqual(missing, [dt.date(2026, 8, 21)])

    def test_guard_still_fills_a_missed_week(self):
        """A weekly series that skipped a week is STILL weekly — the generated
        series is a superset of the evidence, so the gap gets filled."""
        # 8/21 is missing from an otherwise weekly Friday series.
        occ = _points('2026-08-07', '2026-08-14', '2026-08-28', '2026-09-04') + [
            _occ('2026-08-07', '2026-09-11')]
        verdict, info = frs.classify(2, 'Weekly Open Mic', occ)
        self.assertEqual(verdict, 'weekly')
        self.assertEqual(frs.unexplained_observed(verdict, info), [])
        self.assertIn(dt.date(2026, 8, 21), frs.planned_dates(verdict, info))

    def test_observed_dates_are_never_dropped(self):
        # 8/21 is missing from an otherwise weekly Friday series.
        occ = _points('2026-08-07', '2026-08-14', '2026-08-28', '2026-09-04') + [
            _occ('2026-08-07', '2026-09-11')]
        verdict, info = frs.classify(3, 'Weekly Open Mic', occ)
        dates = set(frs.planned_dates(verdict, info))
        self.assertTrue(set(info['disc']).issubset(dates))


class TestGeneratedSeriesIsPure(unittest.TestCase):
    """The guard is only meaningful if generated_series excludes the evidence."""

    def test_generated_series_excludes_unexplained_observed_dates(self):
        info = {'disc': [dt.date(2026, 7, 24), dt.date(2026, 8, 21),
                         dt.date(2026, 9, 18)],
                'wd': 4, 'span_start': dt.date(2026, 3, 16),
                'span_end': dt.date(2026, 9, 18), 'time': ('19:00:00', '21:00:00')}
        gen = frs.generated_series('monthly', info)
        self.assertNotIn(dt.date(2026, 8, 21), gen)
        # ...while planned_dates, which the apply path uses, keeps them.
        self.assertIn(dt.date(2026, 8, 21), frs.planned_dates('monthly', info))


class TestExhibitKeyword(unittest.TestCase):
    """ev214863 "Then and Now" (Lagstein Gallery): a continuous gallery show that
    reached COURSE_WEEKLY because EXHIBITION_KW carried only 'exhibition' while
    the description says "The exhibit features...". Aug 9 and Sep 6 are both
    Sundays — the 1-in-7 coincidence — so `--apply` would have deleted the run
    and written 5 invented Sundays."""

    DESC = ('The exhibit features Joy Katheryn Bird’s stylized contemporary '
            'versions of iconic cultural designs and Don Bradford’s classical work.')
    # 28-day span, Sunday -> Sunday, with a clock time (the corroborating signal).
    OCC = [_occ('2026-08-09', '2026-09-06', '14:00:00', '16:00:00')]

    def test_bare_exhibit_stem_is_in_the_keyword_list(self):
        self.assertIn('exhibit', frs.EXHIBITION_KW)

    def test_gallery_show_is_not_a_course(self):
        verdict, info = frs.classify_course('Then and Now', self.OCC, self.DESC)
        self.assertEqual(verdict, 'skip')
        self.assertIn('exhibition', info['reason'])

    def test_gallery_show_buckets_as_likely_ok(self):
        cat, _ = frs.categorize_for_review(214863, 'Then and Now', self.OCC, self.DESC)
        self.assertEqual(cat, 'LIKELY_OK')

    def test_exhibition_still_matches_too(self):
        """The stem must not have narrowed what it already caught."""
        occ = [_occ('2026-08-09', '2026-09-06', '14:00:00', '16:00:00')]
        verdict, _ = frs.classify_course(
            'Jump', occ, 'An exhibition by artist Hyunjin Park.')
        self.assertEqual(verdict, 'skip')


class TestMultiWeekdayCourse(unittest.TestCase):
    """ev208309 HRMM "Youth After-School Intro to Woodworking": an explicit
    six-week course meeting Tuesdays AND Wednesdays, Oct 13 -> Nov 18. The span
    endpoints fall on different weekdays, which the detector rejected outright;
    and the generator stepped a flat 7 days, so even once accepted it would have
    emitted 6 Tuesdays and silently dropped 6 Wednesdays."""

    NAME = 'Youth After-School Intro to Woodworking'
    DESC = ('Teens ages 13–18 can learn woodworking from expert boat builder '
            'Max Smith in this six-week after-school course at HRMM.')
    # Tue 2026-10-13 -> Wed 2026-11-18 = 36 days; ceil(36/7) == 6 == "six-week".
    OCC = [_occ('2026-10-13', '2026-11-18', '16:15:00', '17:45:00')]

    def test_endpoints_really_are_tuesday_and_wednesday(self):
        self.assertEqual(dt.date(2026, 10, 13).weekday(), 1)
        self.assertEqual(dt.date(2026, 11, 18).weekday(), 2)

    def test_classified_as_a_course(self):
        verdict, info = frs.classify_course(self.NAME, self.OCC, self.DESC)
        self.assertEqual(verdict, 'course_weekly')
        self.assertEqual(info['wds'], [1, 2])

    def test_generates_all_twelve_sessions_not_six(self):
        verdict, info = frs.classify_course(self.NAME, self.OCC, self.DESC)
        dates = frs.planned_dates(verdict, info)
        self.assertEqual(len(dates), 12)
        self.assertEqual(sorted(dates), [
            dt.date(2026, 10, 13), dt.date(2026, 10, 14),
            dt.date(2026, 10, 20), dt.date(2026, 10, 21),
            dt.date(2026, 10, 27), dt.date(2026, 10, 28),
            dt.date(2026, 11, 3), dt.date(2026, 11, 4),
            dt.date(2026, 11, 10), dt.date(2026, 11, 11),
            dt.date(2026, 11, 17), dt.date(2026, 11, 18)])

    def test_six_of_each_weekday(self):
        verdict, info = frs.classify_course(self.NAME, self.OCC, self.DESC)
        dates = frs.planned_dates(verdict, info)
        self.assertEqual(sum(1 for d in dates if d.weekday() == 1), 6)
        self.assertEqual(sum(1 for d in dates if d.weekday() == 2), 6)

    def test_apply_path_would_insert_all_twelve(self):
        """What --apply actually writes: planned_dates filtered to >= TODAY.
        The whole course is in the future, so nothing may be trimmed."""
        verdict, info = frs.classify_course(self.NAME, self.OCC, self.DESC)
        dates = frs.planned_dates(verdict, info)
        new_dates = [d for d in dates if d >= dt.date(2026, 8, 9)]
        self.assertEqual(len(new_dates), 12)

    def test_review_bucket_reports_the_arc(self):
        cat, note = frs.categorize_for_review(208309, self.NAME, self.OCC, self.DESC)
        self.assertEqual(cat, 'COURSE_WEEKLY')
        self.assertIn('arc', note)
        self.assertIn('12 weekly dates', note)

    def test_no_stated_week_count_is_still_rejected(self):
        """Without an explicit "N-week", a different-weekday span is a run."""
        verdict, info = frs.classify_course(
            self.NAME, self.OCC, 'Teens learn woodworking with expert boat builder Max Smith.')
        self.assertEqual(verdict, 'skip')
        self.assertIn('no stated week count', info['reason'])

    def test_wrong_week_count_is_rejected(self):
        """ev199141 "Tartuffe": a theatre run whose "in just two weeks" does not
        describe its 38-day span. ceil(days/7) != N is the festival filter."""
        occ = [_occ('2026-07-09', '2026-08-16', '19:00:00', '21:00:00')]
        verdict, info = frs.classify_course(
            'Tartuffe by Moliere', occ,
            'The Teen Troupe create and perform Molière’s Tartuffe in just two weeks.')
        self.assertEqual(verdict, 'skip')
        self.assertIn('!=', info['reason'])

    def test_untimed_multi_weekday_span_is_rejected(self):
        occ = [_occ('2026-10-13', '2026-11-18', None, None)]
        verdict, info = frs.classify_course(self.NAME, occ, self.DESC)
        self.assertEqual(verdict, 'skip')
        self.assertIn('no clock time', info['reason'])

    def test_non_adjacent_weekdays_are_rejected(self):
        """A Mon->Wed arc would have to invent a Tuesday nobody published."""
        # Mon 2026-10-12 -> Wed 2026-11-18 = 37d, ceil == 6, "six-week", timed.
        occ = [_occ('2026-10-12', '2026-11-18', '16:15:00', '17:45:00')]
        verdict, info = frs.classify_course(self.NAME, occ, self.DESC)
        self.assertEqual(verdict, 'skip')
        self.assertIn('adjacent', info['reason'])

    def test_generated_series_emits_every_weekday_in_the_arc(self):
        """Guards gap 3 directly: the flat 7-day step must be gone."""
        info = {'disc': [], 'wd': 1, 'wds': [1, 2],
                'span_start': dt.date(2026, 10, 13),
                'span_end': dt.date(2026, 11, 18),
                'time': ('16:15:00', '17:45:00')}
        gen = frs.generated_series('course_weekly', info)
        self.assertEqual(len(gen), 12)
        self.assertIn(dt.date(2026, 11, 18), gen)   # the last Wednesday

    def test_generator_tolerates_info_without_wds(self):
        """Back-compat: a single-weekday info dict still expands weekly."""
        info = {'disc': [], 'wd': 1, 'span_start': dt.date(2026, 10, 13),
                'span_end': dt.date(2026, 11, 17), 'time': ('16:15:00', None)}
        gen = frs.generated_series('course_weekly', info)
        self.assertEqual(len(gen), 6)
        self.assertTrue(all(d.weekday() == 1 for d in gen))


class TestSingleWeekdayCourseUnchanged(unittest.TestCase):
    """The Bhakti Sastri shape — the case the course detector was built for.
    A same-weekday span must behave exactly as before the arc was added."""

    NAME = 'Bhakti Sastri Course'
    DESC = 'Weekly live and interactive sessions, personal reading and homework.'
    # Tue 2026-08-11 -> Tue 2026-12-15 = 126 days = 18 weeks -> 19 Tuesdays.
    OCC = [_occ('2026-08-11', '2026-12-15', '18:30:00', '20:30:00')]

    def test_still_a_course(self):
        verdict, info = frs.classify_course(self.NAME, self.OCC, self.DESC)
        self.assertEqual(verdict, 'course_weekly')
        self.assertEqual(info['wds'], [1])
        self.assertNotIn('arc', info['signal'])

    def test_still_nineteen_tuesdays(self):
        verdict, info = frs.classify_course(self.NAME, self.OCC, self.DESC)
        dates = frs.planned_dates(verdict, info)
        self.assertEqual(len(dates), 19)
        self.assertTrue(all(d.weekday() == 1 for d in dates))
        self.assertEqual(dates[0], dt.date(2026, 8, 11))
        self.assertEqual(dates[-1], dt.date(2026, 12, 15))


class TestKnownFalsePositivesStillRejected(unittest.TestCase):
    """The two shapes the command doc names as COURSE_WEEKLY hazards. Neither may
    become auto-fixable, and neither may acquire a multi-weekday arc."""

    def test_quarterly_ppv_listing_gains_no_arc(self):
        """ev98631 "Ufc Ppvs": Sun 4/26 1pm -> Sun 7/26, a bar showing PPVs all
        year. Same-weekday, so it stays in COURSE_WEEKLY needing per-id approval
        (unchanged behaviour) — but it must stay a SINGLE weekday."""
        occ = [_occ('2026-04-26', '2026-07-26', '13:00:00', '14:00:00')]
        verdict, info = frs.classify_course(
            'Ufc Ppvs', occ, 'We show every UFC event here all year round. Free admission!')
        self.assertEqual(verdict, 'course_weekly')
        self.assertEqual(info['wds'], [6])       # Sunday only, no arc
        self.assertEqual(len(frs.planned_dates(verdict, info)), 14)
        cat, _ = frs.categorize_for_review(98631, 'Ufc Ppvs', occ,
                                           'We show every UFC event here all year round.')
        self.assertEqual(cat, 'COURSE_WEEKLY')   # never FIX_SPAN / auto-applied

    def test_different_weekday_ppv_quarter_is_rejected(self):
        occ = [_occ('2026-04-26', '2026-07-25', '13:00:00', '14:00:00')]
        verdict, info = frs.classify_course(
            'Ufc Ppvs', occ, 'We show every UFC event here all year round. Free admission!')
        self.assertEqual(verdict, 'skip')

    def test_daily_summer_camp_is_rejected(self):
        """ev188620 "HRMM Voyager Summer Camp": Mon 7/6 9am -> Fri 8/14 4pm."""
        occ = [_occ('2026-07-06', '2026-08-14', '09:00:00', '16:00:00')]
        verdict, info = frs.classify_course(
            'HRMM Voyager Summer Camp', occ,
            'An all-day summer camp for kids ages 9-17 featuring sailing and boatbuilding. '
            'Sessions run Monday to Friday.')
        self.assertEqual(verdict, 'skip')

    def test_daily_camp_claiming_six_weeks_is_still_rejected(self):
        """The hostile version: 7/6 -> 8/14 is 39d, ceil == 6, so a stated
        "six-week" WOULD satisfy the count check. The daily keyword and the
        Mon->Fri (non-adjacent) arc must both hold the line."""
        occ = [_occ('2026-07-06', '2026-08-14', '09:00:00', '16:00:00')]
        verdict, info = frs.classify_course(
            'HRMM Voyager Summer Camp', occ,
            'A six-week all-day summer camp. Sessions run Monday to Friday.')
        self.assertEqual(verdict, 'skip')
        self.assertIn('daily-program keyword', info['reason'])

    def test_real_mon_fri_summer_program_rejected_by_adjacency(self):
        """ev177196 "Lead The Change": Mon 7/6 6pm -> Fri 8/14 8pm, "six-week
        empowerment program", timed, and NO daily keyword — the count check and
        the time check both pass. Only weekday adjacency rejects it."""
        occ = [_occ('2026-07-06', '2026-08-14', '18:00:00', '20:00:00')]
        verdict, info = frs.classify_course(
            'Lead The Change Summer Youth Empowerment', occ,
            'Lead the Change is a six-week empowerment program for youth ages 14-21 focused '
            'on career readiness, college preparation, and leadership development.')
        self.assertEqual(verdict, 'skip')
        self.assertIn('adjacent', info['reason'])

    def test_real_three_week_summer_program_rejected_by_adjacency(self):
        """ev81777 "El Barrio Raíces": Mon 7/6 9am -> Fri 7/24 3pm, 18d,
        "runs for three weeks" == ceil(18/7). Same story."""
        occ = [_occ('2026-07-06', '2026-07-24', '09:00:00', '15:00:00')]
        verdict, info = frs.classify_course(
            'El Barrio Raíces Summer Program 2026', occ,
            'A free summer program for children aged 9-12. The program runs for three weeks '
            'and features instruction in theater, arts, and performance.')
        self.assertEqual(verdict, 'skip')
        self.assertIn('adjacent', info['reason'])


class TestRedundantShortSpans(unittest.TestCase):
    """2-4 day envelope spans, below the main scan's >4 day threshold.

    e209894 "The Premiere Interface" (BRIC) carried points on 11/03 and 11/05 plus
    an 11/03->11/05 envelope, so it rendered on 11/04 — a day the class does not
    meet. `fix_recurring_spans` never saw it (too short) and
    `fix_single_occasion_events` parked it in REVIEW as a polysemous "Premiere".

    The redundancy test is exact, not heuristic: a span is droppable only if EVERY
    day it covers is already a discrete point, so deleting it cannot change what
    renders. A span adding even one day is a genuine multi-day run and is kept —
    which is what spares Mon-Fri summer camps.
    """

    def _hits(self, rows):
        """Drive find_redundant_short_spans over a fake cursor."""
        class FakeCur:
            def execute(self_inner, sql, params=None):
                pass

            def fetchall(self_inner):
                return rows
        return frs.find_redundant_short_spans(FakeCur())

    def _row(self, oid, start, end=None, start_time='', eid=1, name='E'):
        return {'id': eid, 'name': name, 'oid': oid,
                'start_date': dt.date.fromisoformat(start),
                'end_date': dt.date.fromisoformat(end) if end else None,
                'start_time': start_time, 'end_time': ''}

    def test_span_fully_covered_by_points_is_redundant(self):
        hits = self._hits([
            self._row(1, '2026-11-03'),
            self._row(2, '2026-11-05'),
            self._row(3, '2026-11-03', '2026-11-05'),
        ])
        # 11/04 is NOT a point, so this span ADDS a day and must be kept.
        self.assertEqual(hits, [])

    def test_true_envelope_over_contiguous_points(self):
        hits = self._hits([
            self._row(1, '2026-09-05'),
            self._row(2, '2026-09-06'),
            self._row(3, '2026-09-07'),
            self._row(4, '2026-09-05', '2026-09-07', start_time='12pm'),
        ])
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][2], 4)          # the span occurrence id
        self.assertEqual(hits[0][5], '12pm')     # its time, for propagation
        self.assertEqual(sorted(hits[0][7]), [1, 2, 3])   # points inheriting it

    def test_time_is_only_inherited_by_points_that_lack_one(self):
        # DATEDIFF of 2 -> 09-05 through 09-07, the shortest in-scope span.
        hits = self._hits([
            self._row(1, '2026-09-05', start_time='7pm'),
            self._row(2, '2026-09-06'),
            self._row(3, '2026-09-07'),
            self._row(4, '2026-09-05', '2026-09-07', start_time='12pm'),
        ])
        self.assertEqual(len(hits), 1)
        self.assertEqual(sorted(hits[0][7]), [2, 3])   # not 1, which has 7pm

    def test_camp_span_that_fills_missing_days_is_kept(self):
        """Mon-Fri camp: points on 3 days, span covers 5 — must NOT be dropped."""
        hits = self._hits([
            self._row(1, '2026-07-06'),
            self._row(2, '2026-07-08'),
            self._row(3, '2026-07-10'),
            self._row(4, '2026-07-06', '2026-07-10'),
        ])
        self.assertEqual(hits, [])

    def test_span_longer_than_the_short_window_is_out_of_scope(self):
        """>4 days belongs to the main FIX_SPAN path, not this one."""
        rows = [self._row(i + 1, f'2026-07-0{i + 1}') for i in range(9)]
        rows.append(self._row(99, '2026-07-01', '2026-07-09'))
        self.assertEqual(self._hits(rows), [])

    def test_single_point_is_not_enough_evidence(self):
        """A 2-day span with ONE point may be a real two-day run."""
        hits = self._hits([
            self._row(1, '2026-09-05'),
            self._row(2, '2026-09-05', '2026-09-06'),
        ])
        self.assertEqual(hits, [])


class TestStatedWeekdayContradiction(unittest.TestCase):
    """A weekday NAMED in the text beats one INFERRED from the span endpoints.

    ev215602 "2026 Williamsburg Softball Fall League Season 13": Oct 1 -> Dec 10,
    both THURSDAYS, description "co-ed slow pitch DRAFT league on Sundays ONLY".
    The endpoints are administrative season bounds, not game days. Because
    "Sundays" matches RECUR_RE it CORROBORATED the course shape, so without this
    guard the fix would have written 11 Thursday dates for a Sundays-only league —
    confidently, and on a bucket the operator is told is safe after a glance.
    """

    NAME = '2026 Williamsburg Softball Fall League Season 13'
    DESC = ('Williamsburg Softball Fall League is a co-ed slow pitch DRAFT league on '
            'Sundays ONLY at McCarren Park in Williamsburg, Brooklyn. The 2026 season '
            'runs from October 1st with championship on Dec 10th.')
    OCC = [_occ('2026-10-01', '2026-12-10', '', '')]

    def test_contradicted_span_is_not_a_course(self):
        verdict, info = frs.classify_course(self.NAME, self.OCC, self.DESC)
        self.assertEqual(verdict, 'skip')
        self.assertIn('contradicted', info['reason'])

    def test_it_leaves_the_auto_fixable_bucket(self):
        cat, _ = frs.categorize_for_review(215602, self.NAME, self.OCC, self.DESC)
        self.assertNotIn(cat, ('FIX_SPAN', 'COURSE_WEEKLY'))

    def test_agreeing_weekday_is_still_a_course(self):
        """The guard must only fire on DISAGREEMENT, not on any stated weekday."""
        # Tue 2026-08-11 -> Tue 2026-12-15, and the text says Tuesdays.
        occ = [_occ('2026-08-11', '2026-12-15', '18:30:00', '20:30:00')]
        verdict, info = frs.classify_course(
            'Bhakti Sastri Course', occ, 'Weekly sessions on Tuesdays.')
        self.assertEqual(verdict, 'course_weekly')
        self.assertEqual(info['wds'], [1])

    def test_unstated_weekday_is_unaffected(self):
        """No weekday named -> nothing to contradict -> previous behaviour."""
        occ = [_occ('2026-08-11', '2026-12-15', '18:30:00', '20:30:00')]
        verdict, _ = frs.classify_course(
            'Bhakti Sastri Course', occ, 'Weekly live and interactive sessions.')
        self.assertEqual(verdict, 'course_weekly')

    def test_multi_weekday_arc_matches_on_either_day(self):
        """A Tue+Wed arc states both days; matching one of them is agreement."""
        occ = [_occ('2026-10-13', '2026-11-18', '16:00:00', '18:00:00')]
        verdict, info = frs.classify_course(
            'After-School Course', occ,
            'A six-week after-school course meeting Tuesdays and Wednesdays.')
        self.assertEqual(verdict, 'course_weekly')
        self.assertEqual(sorted(info['wds']), [1, 2])

    def test_stated_weekdays_parser(self):
        self.assertEqual(frs.stated_weekdays('games on Sundays ONLY'), {6})
        self.assertEqual(frs.stated_weekdays('Tuesdays and Wednesdays'), {1, 2})
        self.assertEqual(frs.stated_weekdays('every Thursday night'), {3})
        self.assertEqual(frs.stated_weekdays('a weekly class'), set())


class TestSkipPhraseGuard(unittest.TestCase):
    """Announced breaks must never be regenerated — on EITHER path.

    Ground truth: the 2026-09-15 weekly sweep, where 6 of the 8 FIX_SPAN
    candidates were classes whose own title states the weeks they do NOT meet,
    and the envelope regenerator proposed exactly those dates. The COURSE_WEEKLY
    detector already consulted `skipped_dates`; `classify` (the envelope path)
    did not, which is where the damage landed. Each fixture below carries the
    real phrasing and asserts the announced date is absent from the plan.

    WINDOW_END is pinned so the fixtures do not decay as the crawl window slides.
    """

    def setUp(self):
        self._window_end = frs.WINDOW_END
        frs.WINDOW_END = dt.date(2027, 12, 31)

    def tearDown(self):
        frs.WINDOW_END = self._window_end

    def _plan(self, name, occ, desc=''):
        verdict, info = frs.classify(1, name, occ, desc)
        self.assertNotEqual(verdict, 'skip', msg=info.get('reason'))
        return verdict, frs.planned_dates(verdict, info)

    # ---- ev240463: "(NO CLASS on November 11th)" ------------------------------
    N_240463 = ('Little Designers: Fall Semester: 6-9 year-olds, Wednesdays, '
                'September 16th - December 23rd, 3:30- 5:00PM (NO CLASS on November 11th)')
    O_240463 = _points('2026-09-16', '2026-09-23', '2026-09-30') + [
        _occ('2026-09-16', '2026-12-23')]

    def test_no_class_on_named_date_is_not_regenerated(self):
        verdict, dates = self._plan(self.N_240463, self.O_240463)
        self.assertEqual(verdict, 'weekly')
        self.assertNotIn(dt.date(2026, 11, 11), dates)
        # the weeks either side of the break are still there
        self.assertIn(dt.date(2026, 11, 4), dates)
        self.assertIn(dt.date(2026, 11, 18), dates)
        self.assertIn(dt.date(2026, 12, 23), dates)

    def test_without_the_guard_the_date_would_be_generated(self):
        """Pins WHY: the raw cadence really does propose 2026-11-11."""
        _v, info = frs.classify(1, self.N_240463, self.O_240463)
        self.assertIn(dt.date(2026, 11, 11), frs._generated_series_raw('weekly', info))
        self.assertEqual(info['skips'], {dt.date(2026, 11, 11)})

    # ---- ev240464: "(Skip Thanksgiving)" -------------------------------------
    N_240464 = ('Little Designers: Fall Semester: 10-14 year-olds, Thursdays, '
                'September 17th - December 17th, 3:30-5:30pm (Skip Thanksgiving)')
    O_240464 = _points('2026-09-17', '2026-09-24', '2026-10-01') + [
        _occ('2026-09-17', '2026-12-17')]

    def test_named_holiday_resolves_to_a_date_and_is_dropped(self):
        verdict, dates = self._plan(self.N_240464, self.O_240464)
        self.assertEqual(verdict, 'weekly')
        # Thanksgiving 2026 = 4th Thursday of November = Nov 26, and this is a
        # Thursday class, so the naive series lands squarely on it.
        self.assertNotIn(dt.date(2026, 11, 26), dates)
        self.assertIn(dt.date(2026, 11, 19), dates)
        self.assertIn(dt.date(2026, 12, 3), dates)

    # ---- ev240486: "(SKIP 11/29 and 12/27)" ----------------------------------
    N_240486 = ('Dressmaking Class: Weekly Class: Sundays, November 15th - '
                'January 3rd, 2 - 4 PM (SKIP 11/29 and 12/27)')
    O_240486 = _points('2026-11-15', '2026-11-22', '2026-12-06', '2026-12-13') + [
        _occ('2026-11-15', '2027-01-03')]

    def test_two_slash_dates_in_one_phrase_both_dropped(self):
        verdict, dates = self._plan(self.N_240486, self.O_240486)
        self.assertEqual(verdict, 'weekly')
        # exactly the 6 Sundays the venue actually publishes
        self.assertEqual(dates, [dt.date(2026, 11, 15), dt.date(2026, 11, 22),
                                 dt.date(2026, 12, 6), dt.date(2026, 12, 13),
                                 dt.date(2026, 12, 20), dt.date(2027, 1, 3)])

    def test_bare_month_day_gets_its_year_from_the_span(self):
        """11/29 and 12/27 carry no year; the span (Nov 2026 -> Jan 2027) supplies it."""
        self.assertEqual(
            frs.skipped_dates(self.N_240486, dt.date(2026, 11, 15), dt.date(2027, 1, 3)),
            {dt.date(2026, 11, 29), dt.date(2026, 12, 27)})

    # ---- ev240487: "(SKIP 11/25 for Thanksgiving)" ---------------------------
    N_240487 = ('Sewing 101: Weekly Class: Wednesdays, November 18th - '
                'December 16th, 6 - 9 PM (SKIP 11/25 for Thanksgiving)')
    O_240487 = _points('2026-11-18', '2026-12-02', '2026-12-09', '2026-12-16') + [
        _occ('2026-11-18', '2026-12-16')]

    def test_explicit_date_plus_holiday_name_in_one_phrase(self):
        verdict, dates = self._plan(self.N_240487, self.O_240487)
        self.assertEqual(verdict, 'weekly')
        # A WEDNESDAY class skipping Thanksgiving EVE: the explicit 11/25 is the
        # session, 11/26 is the holiday itself. Resolving both is harmless
        # (11/26 is not a Wednesday) and the explicit date is what matters.
        self.assertNotIn(dt.date(2026, 11, 25), dates)
        self.assertEqual(dates, [dt.date(2026, 11, 18), dt.date(2026, 12, 2),
                                 dt.date(2026, 12, 9), dt.date(2026, 12, 16)])

    # ---- ev241692: "(skipping 11/26 for Thanksgiving)" -----------------------
    N_241692 = 'Riso II: Analog and Digital Workflows for Multipage Zines'
    D_241692 = ('A four week workshop, Thursdays, November 19th - December 17th '
                '(skipping 11/26 for Thanksgiving).')
    O_241692 = _points('2026-11-19', '2026-12-03', '2026-12-10', '2026-12-17') + [
        _occ('2026-11-19', '2026-12-17')]

    def test_skip_phrase_in_the_description_counts_too(self):
        verdict, dates = self._plan(self.N_241692, self.O_241692, self.D_241692)
        self.assertEqual(verdict, 'weekly')
        self.assertNotIn(dt.date(2026, 11, 26), dates)
        self.assertEqual(len(dates), 4)

    def test_same_phrase_still_guards_the_course_path(self):
        """The original COURSE_WEEKLY case must not have regressed."""
        occ = [_occ('2026-11-19', '2026-12-17', '18:00:00', '21:00:00')]
        verdict, info = frs.classify_course(self.N_241692, occ, self.D_241692)
        self.assertEqual(verdict, 'course_weekly', msg=info.get('reason'))
        dates = frs.planned_dates(verdict, info)
        self.assertNotIn(dt.date(2026, 11, 26), dates)
        self.assertEqual(len(dates), 4)     # "four week", not five

    # ---- ev251879: "NO SESSION NOV 9" ---------------------------------------
    N_251879 = 'Practice Space: Fall 2026 Season'
    D_251879 = ('Practice Space: Fall 2026 Season is presented by SUPR OMEN. '
                'Mondays at 6:45pm through December 14th. NO SESSION NOV 9.')
    O_251879 = _points('2026-09-21', '2026-09-28', '2026-10-05') + [
        _occ('2026-09-21', '2026-12-14')]

    def test_no_session_abbreviated_month_is_dropped(self):
        verdict, dates = self._plan(self.N_251879, self.O_251879, self.D_251879)
        self.assertEqual(verdict, 'weekly')
        self.assertNotIn(dt.date(2026, 11, 9), dates)
        self.assertIn(dt.date(2026, 11, 2), dates)
        self.assertIn(dt.date(2026, 11, 16), dates)

    # ---- the unresolvable arm ----------------------------------------------
    UNRESOLVABLE = ('Open Studio: Weekly Drawing Salon, Mondays, September 21st - '
                    'December 14th (no class on holidays)')
    O_UNRES = _points('2026-09-21', '2026-09-28', '2026-10-05') + [
        _occ('2026-09-21', '2026-12-14')]

    def test_unresolvable_skip_phrase_vetoes_the_autofix(self):
        verdict, info = frs.classify(1, self.UNRESOLVABLE, self.O_UNRES)
        self.assertEqual(verdict, 'skip')
        self.assertEqual(info['skip_veto'], 'unresolved')
        self.assertIn('no resolvable date', info['reason'])
        self.assertIn('no class on holidays', info['reason'])

    def test_unresolvable_lands_in_the_new_review_bucket(self):
        cat, note = frs.categorize_for_review(1, self.UNRESOLVABLE, self.O_UNRES)
        self.assertEqual(cat, 'SKIP_PHRASE_UNRESOLVED')
        self.assertIn('no resolvable date', note)

    def test_resolvable_cases_stay_in_fix_span(self):
        """The guard must not evict the six real events from the auto bucket —
        it only removes the fabricated date."""
        for name, occ, desc in (
                (self.N_240463, self.O_240463, ''),
                (self.N_240464, self.O_240464, ''),
                (self.N_240486, self.O_240486, ''),
                (self.N_240487, self.O_240487, ''),
                (self.N_241692, self.O_241692, self.D_241692),
                (self.N_251879, self.O_251879, self.D_251879)):
            cat, _ = frs.categorize_for_review(1, name, occ, desc)
            self.assertEqual(cat, 'FIX_SPAN', msg=name[:40])

    def test_course_path_also_vetoes_an_unresolvable_phrase(self):
        occ = [_occ('2026-08-11', '2026-12-15', '18:30:00', '20:30:00')]
        verdict, info = frs.classify_course(
            'Bhakti Sastri Course', occ,
            'Weekly live sessions on Tuesdays, except holidays.')
        self.assertEqual(verdict, 'skip')
        self.assertEqual(info['skip_veto'], 'unresolved')
        cat, _ = frs.categorize_for_review(1, 'Bhakti Sastri Course', occ,
                                            'Weekly live sessions on Tuesdays, except holidays.')
        self.assertEqual(cat, 'SKIP_PHRASE_UNRESOLVED')

    def test_skip_date_that_is_also_an_occurrence_is_a_contradiction(self):
        """Text says 11/11 is off but a row exists on 11/11 — regenerate nothing."""
        occ = _points('2026-11-04', '2026-11-11', '2026-11-18') + [
            _occ('2026-09-16', '2026-12-23')]
        verdict, info = frs.classify(1, self.N_240463, occ)
        self.assertEqual(verdict, 'skip')
        self.assertEqual(info['skip_veto'], 'conflict')
        self.assertIn('contradicted', info['reason'])

    def test_clean_weekly_event_is_untouched(self):
        """No skip phrase -> no skips, no veto, previous behaviour."""
        occ = _points('2026-09-16', '2026-09-23', '2026-09-30') + [
            _occ('2026-09-16', '2026-12-23')]
        verdict, info = frs.classify(1, 'Wednesday Night Open Mic', occ)
        self.assertEqual(verdict, 'weekly')
        self.assertEqual(info['skips'], set())
        self.assertIn(dt.date(2026, 11, 11), frs.planned_dates(verdict, info))


class TestUnresolvedSkipPhrases(unittest.TestCase):
    """The veto arm fires on announcements it cannot date, and only on those."""

    def test_phrases_with_no_date(self):
        for text in ('a weekly class, except holidays',
                     'runs weekly, skipping some weeks for holidays',
                     'no class during the winter break',
                     'weekly, excluding the last two weeks of December',
                     'no sessions on major holidays'):
            self.assertTrue(frs.unresolved_skip_phrases(text), msg=text)

    def test_week_of_anchor_is_unresolvable_not_a_date(self):
        """"no class the week of 11/24" names a WEEK — the cancelled session is
        some other day inside it, so dropping 11/24 would cancel the wrong one."""
        text = 'Weekly on Thursdays; no class the week of 11/24.'
        self.assertTrue(frs.unresolved_skip_phrases(text))
        self.assertEqual(frs.skipped_dates(text, dt.date(2026, 11, 1),
                                           dt.date(2026, 12, 31)), set())

    def test_datable_phrases_do_not_veto(self):
        for text in ('Thursdays (skipping 11/26 for Thanksgiving)',
                     '(NO CLASS on November 11th)',
                     '(SKIP 11/29 and 12/27)',
                     'Skip Thanksgiving',
                     'no session Nov 9',
                     'no class Dec 24'):
            self.assertEqual(frs.unresolved_skip_phrases(text), [], msg=text)

    def test_ordinary_prose_does_not_veto(self):
        for text in ('A dark comedy about a Brooklyn family',
                     'Tickets 50% off for members',
                     'Kick off the fall season with us',
                     'Open to all except children under 12',
                     "Skip's Jazz Trio plays every Tuesday",
                     'The show is dark on the last night'):
            self.assertEqual(frs.unresolved_skip_phrases(text), [], msg=text)


class TestHolidayResolution(unittest.TestCase):
    """A publisher writes the holiday NAME where a date belongs ("Skip
    Thanksgiving"), so the guard is only useful if it can resolve them."""

    def test_floating_holidays(self):
        self.assertEqual(frs.holiday_date('Thanksgiving', 2026), dt.date(2026, 11, 26))
        self.assertEqual(frs.holiday_date('Thanksgiving', 2027), dt.date(2027, 11, 25))
        self.assertEqual(frs.holiday_date('Labor Day', 2026), dt.date(2026, 9, 7))
        self.assertEqual(frs.holiday_date('Memorial Day', 2026), dt.date(2026, 5, 25))

    def test_fixed_holidays(self):
        self.assertEqual(frs.holiday_date('Christmas', 2026), dt.date(2026, 12, 25))
        self.assertEqual(frs.holiday_date('Christmas Eve', 2026), dt.date(2026, 12, 24))
        self.assertEqual(frs.holiday_date("New Year's Day", 2027), dt.date(2027, 1, 1))
        self.assertEqual(frs.holiday_date("New Year's Eve", 2026), dt.date(2026, 12, 31))
        self.assertEqual(frs.holiday_date('July 4th', 2026), dt.date(2026, 7, 4))
        self.assertEqual(frs.holiday_date('Independence Day', 2026), dt.date(2026, 7, 4))
        self.assertEqual(frs.holiday_date('Fourth of July', 2026), dt.date(2026, 7, 4))

    def test_christmas_eve_is_not_read_as_christmas(self):
        """Longest-first alternation: the 'eve' must win."""
        m = frs.HOLIDAY_RE.search('no class Christmas Eve')
        self.assertEqual(m.group(1).lower(), 'christmas eve')

    def test_holiday_outside_the_span_is_not_dropped(self):
        """A holiday named in prose but falling outside the course is irrelevant."""
        self.assertEqual(
            frs.skipped_dates('no class Thanksgiving', dt.date(2026, 1, 5),
                              dt.date(2026, 3, 30)), set())

    def test_unknown_holiday_is_unresolved_rather_than_guessed(self):
        self.assertIsNone(frs.holiday_date('Arbor Day', 2026))


class TestStatedWeekCount(unittest.TestCase):
    def test_word_and_digit_forms(self):
        self.assertEqual(frs.stated_week_count('a six-week after-school course'), 6)
        self.assertEqual(frs.stated_week_count('an 8-week workshop'), 8)
        self.assertEqual(frs.stated_week_count('runs for three weeks'), 3)
        self.assertEqual(frs.stated_week_count('a 12 week intensive'), 12)

    def test_no_claim(self):
        self.assertIsNone(frs.stated_week_count('a woodworking course for teens'))

    def test_weekend_is_not_a_week_count(self):
        self.assertIsNone(frs.stated_week_count('three weekend sessions'))

    def test_conflicting_claims_are_no_claim(self):
        self.assertIsNone(frs.stated_week_count('a six-week course with two weeks off'))


if __name__ == '__main__':
    unittest.main()
