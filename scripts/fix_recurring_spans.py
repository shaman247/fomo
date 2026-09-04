#!/usr/bin/env python3
"""Identify events whose recurring (weekly/monthly) meetings were captured as a
single long contiguous date-range occurrence (an "envelope span"), which makes
the event render on the map every day of the range instead of only on its real
meeting dates.

Strategy: an event is a "periodic meeting" (not a continuous exhibition/run) when
it has discrete point occurrences spaced at a regular cadence (weekly / biweekly /
monthly), AND a long-span occurrence that is essentially the envelope of those
points. For such events we:
  - regenerate the discrete series at the detected cadence up to min(span_end,
    future-window), so no in-window meeting is lost, then
  - delete the envelope span occurrence(s).

A second shape, COURSE_WEEKLY, covers weekly classes/courses captured as ONE bare
span with no discrete dates at all (so the envelope scan can't see them): exactly
one occurrence, a 2-week..6-month span whose endpoints fall on the SAME weekday,
corroborated by a clock time on the span or an explicit recurrence keyword. The
fix expands the span into the weekly series at the span's time (e.g. "Aug 11 –
Dec 15, 6:30pm Tuesdays" -> 19 Tuesday occurrences). Because a same-weekday span
can still be non-weekly (quarterly PPV listings, daily summer programs), course
fixes apply ONLY with explicit `--apply --ids <ids>` after a source check —
a blanket `--apply` lists them and moves on.

Dry-run by default. Pass --apply to write changes.
"""
import sys, argparse, statistics, re
from collections import Counter
from datetime import date, timedelta

sys.path.insert(0, 'pipeline')
from db import create_connection
from dblock import write_lock
from constants import FUTURE_WINDOW_DAYS

TODAY = date.today()
WINDOW_END = TODAY + timedelta(days=FUTURE_WINDOW_DAYS)
SPAN_THRESHOLD = 14  # >14 days = "Ongoing"-triggering span (matches exporter)


def nth_weekday(d):
    """Return which ordinal (1-5) occurrence of its weekday `d` is within its month."""
    return (d.day - 1) // 7 + 1


def gen_monthly_nth_weekday(first, weekday, ordinal, end):
    """Generate dates that are the `ordinal`-th `weekday` of each month from
    `first`'s month through `end`."""
    out = []
    y, m = first.year, first.month
    while True:
        # find ordinal-th weekday of (y, m)
        d = date(y, m, 1)
        offset = (weekday - d.weekday()) % 7
        cand = d + timedelta(days=offset + 7 * (ordinal - 1))
        if cand.month == m and cand >= first and cand <= end:
            out.append(cand)
        if cand > end:
            break
        m += 1
        if m > 12:
            m = 1; y += 1
        if date(y, m, 1) > end:
            break
    return out


# Continuously-on-view events: a long span is CORRECT for these; their discrete
# dates are receptions/markers, not the only days they're open. Never touch them.
# NOTE the bare stem 'exhibit' (not 'exhibition'): galleries write "the exhibit
# features..." as often as "exhibition", and the longer form let ev214863 "Then
# and Now" (Lagstein Gallery) reach COURSE_WEEKLY as a 28-day same-weekday span
# — applying would have replaced a continuous show with 5 invented Sundays.
# 'exhibit' subsumes exhibition/exhibits/exhibiting and only ever pushes an
# event toward LIKELY_OK, which is the safe direction.
EXHIBITION_KW = ('exhibit', 'on view', 'on display', 'available for viewing',
                 'retrospective', 'installation', 'survey of', 'biennial', 'group show',
                 'solo show', 'now on view')

# STRONG recurrence signal — a single thing that meets on a fixed cadence. The
# fix is to make the dates discrete. (e.g. "every Saturday", "weekly class")
RECUR_RE = re.compile(
    r'\b(weekly|bi-?weekly|monthly|every (?:other )?(?:week|month|mon|tues|wednes|thurs|fri|satur|sun)\w*|'
    r'each (?:week|month)|recurring|mondays|tuesdays|wednesdays|thursdays|fridays|saturdays|sundays)\b',
    re.I)

# Weekday names STATED in the text, used to contradict a weekday inferred from a
# span's endpoints.
#
# COURSE_WEEKLY reads the meeting day off the span endpoints, and accepts a
# recurrence keyword as corroboration. Those two can disagree, and when they do the
# endpoints are the ones lying: e215602 "2026 Williamsburg Softball Fall League"
# runs Oct 1 -> Dec 10, both THURSDAYS, while its own description says games are
# "on Sundays ONLY" (Oct 1 / Dec 10 are administrative season bounds, not game
# days). The keyword "Sundays" corroborated the shape, so the fix would have
# confidently written 11 Thursday dates for a league that never plays Thursdays.
#
# So: if the text names weekdays at all, an inferred day that is not among them is
# a contradiction, not a match. Stated evidence beats inferred structure.
WEEKDAY_NAMES = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                 'friday': 4, 'saturday': 5, 'sunday': 6}
STATED_WEEKDAY_RE = re.compile(
    r'\b(mon|tues|wednes|thurs|fri|satur|sun)day s?\b'.replace(' ', ''), re.I)


def stated_weekdays(blob):
    """Set of weekday numbers explicitly named in the text (empty if none)."""
    return {WEEKDAY_NAMES[m.group(0).lower().rstrip('s')]
            for m in STATED_WEEKDAY_RE.finditer(blob)}


# A weekly course that BREAKS for a holiday states it in prose — "(skipping 11/26
# for Thanksgiving)", "no class Dec 24". The generator fills a same-weekday span
# uniformly and cannot see that, so it fabricates a session the venue explicitly
# cancels. Measured 2026-09-04 on ev241692 (Center for Book Arts, "Riso II"):
# the source says "four week ... Thursdays, November 19th – December 17th
# (skipping 11/26 for Thanksgiving)" and the expander emitted 5 Thursdays.
#
# The failure is SILENT — the event looks well-formed, just with one extra date —
# so this is a guard, not a nicety. Two arms, both conservative:
#   1. drop dates the text explicitly excludes;
#   2. veto entirely when an explicit session count still disagrees afterwards.
MONTH_NAMES = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
               'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
# The cue must be close to the date — a bare "except" three sentences away is not
# evidence about this date. 40 chars covers "skipping 11/26 for Thanksgiving" and
# "no class on Thursday, December 24th" without spanning clauses.
SKIP_CUE_RE = re.compile(
    r'\b(?:skip(?:s|ping|ped)?|no\s+(?:class|session|meeting|workshop)e?s?|'
    r'except|excluding|dark|off)\b', re.I)
_MD_SLASH_RE = re.compile(r'\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b')
_MD_NAME_RE = re.compile(
    r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b',
    re.I)


def skipped_dates(blob, span_start, span_end):
    """Dates the text explicitly excludes from a series, restricted to the span.

    Only dates appearing within SKIP_WINDOW chars AFTER a skip cue count, so an
    ordinary date mention ("starts November 19th") is never read as an exclusion.
    Years are inferred from the span, which is what makes a bare "11/26" usable.
    """
    SKIP_WINDOW = 40
    out = set()
    years = {span_start.year, span_end.year}
    for cue in SKIP_CUE_RE.finditer(blob):
        seg = blob[cue.end():cue.end() + SKIP_WINDOW]
        cands = [(int(m.group(1)), int(m.group(2)), m.group(3)) for m in _MD_SLASH_RE.finditer(seg)]
        cands += [(MONTH_NAMES[m.group(1).lower()[:3]], int(m.group(2)), None)
                  for m in _MD_NAME_RE.finditer(seg)]
        for mon, day, yr in cands:
            for y in ([int(yr) + 2000 if int(yr) < 100 else int(yr)] if yr else sorted(years)):
                try:
                    d = date(y, mon, day)
                except ValueError:
                    continue
                if span_start <= d <= span_end:
                    out.add(d)
                    break
    return out


# Multi-session PROGRAM signal — a thing that meets on specific (sparse) days but
# was captured as one range: camps, intensives, clinics, multi-week courses. The
# fix is judgment: make discrete from source, or accept.
PROGRAM_RE = re.compile(
    r'\b(program|camp|intensive|clinics?|tournaments?|league|cohort|semester|'
    r'multi-?session|sessions|workshops?|classes|course|learning|symphony|seminar|lessons|rehearsals?)\b',
    re.I)
# Genuinely CONTINUOUS multi-day events — every-day rendering is CORRECT for these
# (like exhibitions). A festival/fair/retreat runs daily; not a sparse-meeting bug.
CONTINUOUS_RE = re.compile(
    r'\b(festival|fair|expo|biennial|fan village|fan fest|retreat|sesshin|world cup|us open|open week)\b',
    re.I)
# Only the specific exhibition phrases — NOT loose words like "gallery"/"sculpture"
# /"paintings", which false-match class titles (e.g. "ceramic sculpture: a course").
EXHIB_RE = re.compile('|'.join(re.escape(k) for k in EXHIBITION_KW), re.I)

REVIEW_SPAN_MIN = 4   # surface spans > 4 days (>=5) in --review; auto-fix still gated at >14

# Course-shape detection (COURSE_WEEKLY): a weekly class/course captured as ONE
# span occurrence. The give-away is that the span starts and ends on the SAME
# weekday — publishers state a weekly series as "Aug 11 – Dec 15" where both
# endpoints are class days (1-in-7 odds by chance). Bounds keep it to
# course-plausible lengths: >= 2 weeks (3+ sessions), <= ~6 months (a semester).
COURSE_SPAN_MIN_DAYS = 14
COURSE_SPAN_MAX_DAYS = 190

# An EXPLICIT session count: "six-week after-school course", "8-week workshop",
# "12 weeks". Only used to license the multi-weekday arc below, where the
# endpoints alone can't tell a weekly course from a continuous run.
NWEEK_RE = re.compile(
    r'\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)'
    r'[-\s]?weeks?\b', re.I)
_WEEK_WORDS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
               'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12}
# Programs that run EVERY day of their range — camps, daily practice series,
# Mon-Fri sessions. Their endpoints legitimately fall on different weekdays, so
# they are the main hazard for the arc path and are vetoed there outright.
DAILY_RE = re.compile(
    r'\b(camps?|daily|every ?day|all[- ]day|all week|week-?long|'
    r'days? a week|weekdays?|mon(?:day)?s?\s*(?:-|–|—|to|through|thru)\s*fri(?:day)?s?)\b',
    re.I)


def stated_week_count(blob):
    """The explicit week count in an "N-week course" phrase, or None.

    Returns None when the text states more than one distinct count ("a six-week
    course with two weeks off") — an ambiguous claim is no claim.
    """
    found = set()
    for m in NWEEK_RE.finditer(blob):
        tok = m.group(1).lower()
        found.add(int(tok) if tok.isdigit() else _WEEK_WORDS[tok])
    return found.pop() if len(found) == 1 else None


def classify(eid, name, occ, description=''):
    """Return (verdict, info-dict) for an event's occurrences.
    verdict in {weekly, biweekly, monthly, skip}."""
    blob = (name + ' ' + (description or '')).lower()
    if any(k in blob for k in EXHIBITION_KW):
        return 'skip', {'reason': 'exhibition/continuous keyword'}
    spans = [(o['start_date'], o['end_date'], o['start_time'], o['end_time'])
             for o in occ if o['end_date'] and (o['end_date'] - o['start_date']).days > SPAN_THRESHOLD]
    disc = sorted(set(o['start_date'] for o in occ
                      if not o['end_date'] or (o['end_date'] - o['start_date']).days <= 2))
    if not spans or len(disc) < 3:
        return 'skip', {'reason': 'needs >=3 discrete + a span'}

    gaps = [(disc[i + 1] - disc[i]).days for i in range(len(disc) - 1)]
    weekdays = Counter(d.weekday() for d in disc)
    common_wd, common_wd_n = weekdays.most_common(1)[0]
    same_weekday = common_wd_n == len(disc)
    med = statistics.median(gaps)

    # span must be an envelope: its range overlaps the discrete cluster
    span_start = min(s[0] for s in spans)
    span_end = max(s[1] for s in spans)
    envelope = span_start <= disc[-1] and span_end >= disc[0]
    if not envelope:
        return 'skip', {'reason': 'span not an envelope of discrete dates'}

    info = {'disc': disc, 'gaps': gaps, 'med': med, 'wd': common_wd,
            'span_start': span_start, 'span_end': span_end,
            'time': next((o['start_time'], o['end_time']) for o in occ
                         if (not o['end_date'] or (o['end_date'] - o['start_date']).days <= 2)),
            'spans': spans}

    verdict = None
    if same_weekday and all(g % 7 == 0 for g in gaps):
        if 6 <= med <= 8:
            verdict = 'weekly'
        elif 13 <= med <= 15:
            verdict = 'biweekly'
        elif 27 <= med <= 29:
            # A 4-WEEKLY rhythm, NOT calendar-monthly. These are only
            # distinguishable by the generator you then run: the nth-weekday-of-month
            # generator drifts to 35-day gaps and invents dates a 28-day series
            # never has (ev196587 "Mahjong Parlor" gained a bogus 2026-08-28 that
            # way). Keep the step at exactly 28.
            verdict = 'four_weekly'
    if verdict is None and same_weekday and 27 <= med <= 35:
        verdict = 'monthly'
    # NOTE: a "same day-of-month" verdict was tried but every match was an
    # exhibition with monthly markers, never a real meeting — dropped as unsafe.
    if verdict is None:
        return 'skip', {'reason': f'irregular cadence med={med} gaps={gaps} same_wd={same_weekday}'}

    # EVIDENCE GUARD: a cadence model is only trustworthy if it explains every
    # date we actually observed. If the generator's own rhythm omits an observed
    # date, the model is wrong and any date it *adds* is an invention — refuse
    # rather than write fabricated occurrences. (Filling an observed GAP is still
    # fine: the generated series is a superset of the evidence there.)
    missing = unexplained_observed(verdict, info)
    if missing:
        return 'skip', {'reason': f'{verdict} cadence does not explain observed dates '
                                  f'{[str(d) for d in missing]} (gaps={gaps} med={med})'}
    return verdict, info


def unexplained_observed(verdict, info):
    """Observed discrete dates the generated cadence fails to produce.

    Only dates inside the generator's own range are considered — dates past
    `end` (span_end / the crawl future window) are out of scope by construction,
    not evidence against the model.
    """
    disc = info.get('disc') or []
    if not disc:
        return []
    gen = set(generated_series(verdict, info))
    if not gen:
        return []
    last = max(gen)
    return [d for d in disc if disc[0] <= d <= last and d not in gen]


def classify_course(name, occ, description=''):
    """Span-only course detector. Returns ('course_weekly', info) or ('skip', info).

    Deliberately the most conservative shape that covers the real cases (BISR
    courses, Bhakti Center modules): the event has EXACTLY ONE occurrence, and it
    is a single span of COURSE_SPAN_MIN..MAX days whose start and end fall on the
    same weekday, plus at least one corroborating signal — a start_time on the
    span (exhibitions don't publish a clock time on their run) or an EXPLICIT
    recurrence keyword ("weekly", "Tuesdays"...) in the name/description.
    Program/camp keywords deliberately do NOT corroborate: summer programs and
    camps run DAILY, so a same-weekday span + "program" is usually not weekly.
    Exhibition/continuous keywords veto.

    A course meeting on TWO weekdays ("six-week course, Tuesdays and
    Wednesdays") ends on a different weekday than it starts; that shape is
    accepted only under the much stricter gate below, and info['wds'] then
    carries both weekdays so the generator emits both series.

    Even matches are NOT blanket-applied — a timed same-weekday span can still be
    a non-weekly series (e.g. a bar's "UFC PPVs" quarter with a 1pm time), so the
    fix requires explicit --apply --ids approval after a source check.
    """
    blob = name + ' ' + (description or '')
    if EXHIB_RE.search(blob) or CONTINUOUS_RE.search(blob):
        return 'skip', {'reason': 'exhibition/continuous keyword'}
    if len(occ) != 1:
        return 'skip', {'reason': f'{len(occ)} occurrence rows (course shape = exactly 1 span)'}
    o = occ[0]
    if not o['end_date']:
        return 'skip', {'reason': 'no end_date'}
    days = (o['end_date'] - o['start_date']).days
    if not (COURSE_SPAN_MIN_DAYS <= days <= COURSE_SPAN_MAX_DAYS):
        return 'skip', {'reason': f'span {days}d outside course bounds'}
    has_time = bool(o['start_time'])
    has_kw = bool(RECUR_RE.search(blob))
    wds = [o['start_date'].weekday()]
    arc = False
    if o['start_date'].weekday() != o['end_date'].weekday():
        # A course that meets on TWO weekdays ends on a different weekday than
        # it starts ("six-week after-school course", Tuesdays AND Wednesdays,
        # Oct 13 -> Nov 18 — ev208309). Rejecting that outright lost those; but
        # a different-weekday span is far more often a festival or a daily camp,
        # so accept only the tightest shape that cannot invent a session:
        #   * an EXPLICIT week count N that equals ceil(days/7) — the range is
        #     exactly N weeks of a weekly rhythm, which is what keeps festivals
        #     and open-ended runs out (they don't state N, or N doesn't match);
        #   * a published clock time (daily programs and continuous runs rarely
        #     put one on the range);
        #   * no daily-program keyword (camp / Mon-Fri / "daily");
        #   * endpoint weekdays ADJACENT, so BOTH are observed session days and
        #     nothing between them is invented. A Mon->Fri arc is a camp; a
        #     Mon->Wed arc would have to fabricate a Tuesday that no source
        #     published, which is exactly what the evidence guard forbids.
        n = stated_week_count(blob)
        if n is None:
            return 'skip', {'reason': 'span endpoints on different weekdays, no stated week count'}
        weeks = -(-days // 7)  # ceil
        if n != weeks:
            return 'skip', {'reason': f'different-weekday span: stated {n} weeks != ceil({days}d/7)={weeks}'}
        if not has_time:
            return 'skip', {'reason': 'different-weekday span with no clock time'}
        if DAILY_RE.search(blob):
            return 'skip', {'reason': 'different-weekday span with daily-program keyword'}
        if o['end_date'].weekday() != (o['start_date'].weekday() + 1) % 7:
            return 'skip', {'reason': 'different-weekday span endpoints are not adjacent weekdays'}
        wds.append(o['end_date'].weekday())
        arc = True
    if not (has_time or has_kw):
        return 'skip', {'reason': 'no time and no explicit recurrence keyword'}
    # Stated weekdays veto an inferred one that contradicts them. The endpoints
    # are structure; a named day is evidence, and evidence wins. Without this the
    # generator writes sessions on a day the source explicitly excludes — see
    # STATED_WEEKDAY_RE for the softball league that would have got 11 Thursdays.
    stated = stated_weekdays(blob)
    if stated and not (set(wds) & stated):
        names = sorted(n for n, i in WEEKDAY_NAMES.items() if i in stated)
        got = sorted(n for n, i in WEEKDAY_NAMES.items() if i in set(wds))
        return 'skip', {'reason': f'span endpoints are {"/".join(got)} but the text '
                                  f'states {"/".join(names)} — contradicted'}
    # Holiday / stated break weeks. Drop them from the generated series, then
    # cross-check against an explicit session count: if the source says "four
    # week" and we still plan 5, the model disagrees with the publisher and we
    # must not write it. Vetoing is right here — a fabricated session is worse
    # than leaving the span for a human, and this bucket already requires
    # per-id approval.
    skips = skipped_dates(blob, o['start_date'], o['end_date'])
    info = {'disc': [], 'wd': wds[0], 'wds': wds,
            'span_start': o['start_date'], 'span_end': o['end_date'],
            'time': (o['start_time'], o['end_time']),
            'skips': skips,
            'signal': ('time' if has_time else '') + ('+kw' if has_kw else '')
                      + (f'+{len(wds)}-weekday arc' if arc else '')
                      + (f'+{len(skips)} skipped' if skips else '')}
    stated_n = stated_week_count(blob)
    if stated_n is not None and not arc:
        # (the arc path already required stated_n == ceil(days/7) above)
        planned_n = len(generated_series('course_weekly', info))
        if planned_n != stated_n:
            return 'skip', {'reason': f'stated {stated_n} sessions but the weekly model plans '
                                      f'{planned_n}{" after dropping " + str(len(skips)) + " stated skip(s)" if skips else ""} '
                                      f'— publisher disagrees, needs a human'}
    return 'course_weekly', info


def generated_series(verdict, info):
    """The dates the cadence model produces on its own, WITHOUT unioning in the
    observed discrete dates. This is what the evidence guard tests: unioning
    first would hide a generator that disagrees with what the source published."""
    if verdict == 'course_weekly':
        # Expand the full published series (span_end is the course's real last
        # session — don't truncate to the crawl future-window). A course that
        # meets on more than one weekday carries every weekday of its arc in
        # info['wds']; stepping a flat 7 days from span_start would emit only
        # the first weekday and SILENTLY DROP the rest (ev208309 would have
        # lost all 6 of its Wednesdays).
        out = []
        for wd in info.get('wds') or [info['span_start'].weekday()]:
            d = info['span_start'] + timedelta(days=(wd - info['span_start'].weekday()) % 7)
            while d <= info['span_end']:
                out.append(d)
                d += timedelta(days=7)
        # Never emit a session the source explicitly cancels (holiday break weeks).
        return sorted(set(out) - (info.get('skips') or set()))
    disc = info['disc']
    first = disc[0]
    end = min(info['span_end'], WINDOW_END)
    if verdict == 'weekly':
        step = 7
    elif verdict == 'biweekly':
        step = 14
    elif verdict == 'four_weekly':
        step = 28
    elif verdict == 'monthly':
        ordinal = nth_weekday(first)
        return gen_monthly_nth_weekday(first, info['wd'], ordinal, end)
    elif verdict == 'monthly_dom':
        # approximate: keep existing discrete, extend by ~30-day steps preserving day
        out = list(disc)
        d = disc[-1]
        while True:
            m = d.month + 1; y = d.year
            if m > 12: m = 1; y += 1
            try:
                d = date(y, m, disc[0].day)
            except ValueError:
                break
            if d > end: break
            out.append(d)
        return sorted(set(out))
    else:
        return disc
    out = []
    d = first
    while d <= end:
        out.append(d)
        d = d + timedelta(days=step)
    return sorted(set(out))


def planned_dates(verdict, info):
    """The dates the event should end up with: the generated series plus the
    observed discrete dates it was built from (never drop published evidence)."""
    return sorted(set(generated_series(verdict, info)) | set(info.get('disc') or []))


def categorize_for_review(eid, name, occ, description=''):
    """Bucket a span-bearing event into a review category with a recommended action.

    Returns (category, note). Categories:
      FIX_SPAN        — auto-fixable: regular cadence + envelope span (handled by --apply)
      RECURRING_RANGE — one thing on a fixed cadence flattened into a range (strong
                        recurrence keyword, or a regular discrete grid). Make the dates
                        discrete (build from source if needed). MANUAL.
      PROGRAM_RANGE   — an umbrella/multi-session program captured as one range
                        (festival lineup, multi-week camp/intensive/series). Triage from
                        source: split into sub-events, make discrete, or accept. MANUAL.
      INVERSE         — exhibition + a regular discrete grid: the span is correct but
                        the regular discrete dates are bogus. Delete the discrete rows,
                        keep the span. MANUAL.
      LIKELY_OK       — continuous exhibition/run or irregular; leave alone.
    """
    blob = name + ' ' + (description or '')
    recur_kw = bool(RECUR_RE.search(blob))
    program_kw = bool(PROGRAM_RE.search(blob))
    continuous_kw = bool(CONTINUOUS_RE.search(blob))
    exhib_kw = bool(EXHIB_RE.search(blob))
    disc = sorted(set(o['start_date'] for o in occ
                      if not o['end_date'] or (o['end_date'] - o['start_date']).days <= 2))
    longest = max((( o['end_date'] - o['start_date']).days for o in occ if o['end_date']), default=0)

    verdict, _ = classify(eid, name, occ, description)
    if verdict != 'skip':
        return 'FIX_SPAN', verdict

    cverdict, cinfo = classify_course(name, occ, description)
    if cverdict == 'course_weekly':
        n = len(planned_dates('course_weekly', cinfo))
        st = cinfo['time'][0] or 'no time'
        return 'COURSE_WEEKLY', (f'same-weekday {longest}d span ({cinfo["signal"]}) '
                                 f'-> {n} weekly dates @ {st}')

    # regular discrete grid? (same weekday, 7/14/28-31 day gaps)
    regular = False
    if len(disc) >= 3:
        gaps = [(disc[i + 1] - disc[i]).days for i in range(len(disc) - 1)]
        same_wd = len({d.weekday() for d in disc}) == 1
        regular = same_wd and (all(g % 7 == 0 for g in gaps) or all(27 <= g <= 31 for g in gaps))

    span_note = f'{longest}d span'
    if exhib_kw and regular:
        return 'INVERSE', f'exhibition + {len(disc)} regular discrete dates'
    if exhib_kw:
        return 'LIKELY_OK', 'exhibition/continuous'
    if recur_kw and len(disc) <= 2:
        return 'RECURRING_RANGE', f'{len(disc)} discrete + recurrence keyword, {span_note}'
    if regular:
        # a regular weekly/monthly grid the auto-fixer rejected (e.g. the span
        # extends past the discrete dates rather than enveloping them) — a real
        # recurring series whose tail was captured as a range.
        return 'RECURRING_RANGE', f'{len(disc)} regular discrete + non-envelope span'
    # Festivals/fairs/retreats run daily — every-day rendering is correct, like an
    # exhibition. Only flag SPARSE programs (a multi-session class/camp captured as
    # one range, ≤2 discrete dates) — those genuinely shouldn't span every day.
    if program_kw and not continuous_kw and len(disc) <= 2:
        return 'PROGRAM_RANGE', f'program keyword, {len(disc)} discrete, {span_note}'
    return 'LIKELY_OK', 'continuous/exhibition or irregular'


def review_scan(cur, recent_only=False, ids=None):
    """Scan active events with a future-ending multi-day span and print the
    ambiguous review buckets (auto-fixable, plus the manual ones).

    recent_only=True restricts to events created or updated in the last day —
    i.e. envelope spans *just added* by the current pipeline run (used by
    /run-pipeline to catch fresh every-day-blanketing bugs the same day).
    ids restricts to a specific event id list.
    """
    where = ["e.archived=0", "e.suppressed=0",
             "o.end_date IS NOT NULL", "DATEDIFF(o.end_date,o.start_date) > %s",
             "o.end_date >= CURDATE()"]
    params = [REVIEW_SPAN_MIN]
    if recent_only:
        where.append("(e.created_at >= (NOW() - INTERVAL 1 DAY) OR e.updated_at >= (NOW() - INTERVAL 1 DAY))")
    if ids:
        where.append("e.id IN (%s)" % ",".join(["%s"] * len(ids)))
        params.extend(ids)
    cur.execute(
        "SELECT DISTINCT e.id, e.name, e.description FROM events e "
        "JOIN event_occurrences o ON o.event_id = e.id WHERE " + " AND ".join(where),
        tuple(params),
    )
    events = cur.fetchall()
    scope = " created/updated in the last day" if recent_only else ""
    buckets = {'FIX_SPAN': [], 'COURSE_WEEKLY': [], 'RECURRING_RANGE': [], 'PROGRAM_RANGE': [], 'INVERSE': [], 'LIKELY_OK': []}
    for e in events:
        cur.execute('SELECT start_date,start_time,end_date,end_time FROM event_occurrences WHERE event_id=%s ORDER BY start_date', (e['id'],))
        occ = cur.fetchall()
        cat, note = categorize_for_review(e['id'], e['name'], occ, e.get('description'))
        buckets[cat].append((e['id'], e['name'], note))

    print(f"\nScanned {len(events)} active events with a future-ending >{REVIEW_SPAN_MIN}-day span{scope}.\n")
    actions = {
        'FIX_SPAN': 'auto-fixable — run with --apply (review first as usual)',
        'COURSE_WEEKLY': 'same-weekday course span -> weekly dates; verify cadence via --show/source, then --apply --ids <ids>',
        'RECURRING_RANGE': 'MANUAL — build the real meeting dates from the source, then delete the span',
        'PROGRAM_RANGE': 'MANUAL — umbrella/program: split into sub-events, make discrete, or accept as ongoing',
        'INVERSE': 'MANUAL — delete the bogus regular discrete rows, KEEP the span',
    }
    for cat in ('FIX_SPAN', 'COURSE_WEEKLY', 'RECURRING_RANGE', 'PROGRAM_RANGE', 'INVERSE'):
        rows = buckets[cat]
        print(f"### {cat} ({len(rows)}) — {actions[cat]}")
        for eid, name, note in rows:
            print(f"  {eid:>7}  {name[:52]:52}  {note}")
        print()
    print(f"### LIKELY_OK ({len(buckets['LIKELY_OK'])}) — left alone (continuous/exhibition or irregular)")
    print("\nInspect any id with:  --show <ids>")


def show_events(cur, ids):
    """Print full occurrence + description detail for manual review of ambiguous cases."""
    for eid in ids:
        cur.execute('SELECT name, location_name, section, description FROM events WHERE id=%s', (eid,))
        e = cur.fetchone()
        if not e:
            print(f'=== {eid} | (not found)'); continue
        print(f"=== {eid} | {e['name']} | {e['location_name'] or '(no location)'} | section={e['section']}")
        print(f"    {(e['description'] or '(no description)')[:240].replace(chr(10), ' ')}")
        cur.execute('SELECT start_date,start_time,end_date,end_time FROM event_occurrences WHERE event_id=%s ORDER BY start_date', (eid,))
        for o in cur.fetchall():
            sp = (o['end_date'] - o['start_date']).days if o['end_date'] else 0
            tag = '  <-- SPAN' if sp > SPAN_THRESHOLD else ''
            print(f"    {o['start_date']} {o['start_time'] or '--':>7} -> {o['end_date']} {o['end_time'] or '--':>7}  span={sp}{tag}")
        print()


# Short envelope spans: 2-4 days. Below SPAN_THRESHOLD, so the main scan above
# never sees them, and `fix_single_occasion_events.py` parks them in REVIEW when
# the name happens to look single-occasion. That gap let e209894 "The Premiere
# Interface" (BRIC) render on 11/04 — it carried points on 11/03 and 11/05 plus
# an 11/03->11/05 envelope, and the class does not meet on the 4th.
#
# The map error per event is small (1-3 phantom days rather than 70), but the
# shape is identical to FIX_SPAN and a 2-3 day run is a very ordinary way to
# publish a short course or a two-night bill.
SHORT_SPAN_MIN_DAYS = 2
SHORT_SPAN_MAX_DAYS = 4


def find_redundant_short_spans(cur, recent_only=False, ids=None):
    """Short spans that cover no date the event's discrete points don't already have.

    Returns [(event_id, name, occurrence_id, start, end)].

    The redundancy test is the whole safety argument, and it is exact rather than
    heuristic: expand the span day by day and require EVERY day to be present as a
    discrete point. Then deleting the span cannot change what renders — the same
    days are still covered — so this is pure de-duplication.

    A span that adds even ONE day is left alone, because that is the shape of a
    genuine multi-day run: a Mon-Fri summer camp publishes 5 points and a 4-day
    span, and the span legitimately fills days the points skip. Measured over the
    live corpus: 55 redundant vs 71 date-adding, and every camp landed on the
    date-adding side.
    """
    where = ["e.archived=0", "e.suppressed=0"]
    params = []
    if recent_only:
        where.append("(e.created_at >= (NOW() - INTERVAL 1 DAY)"
                     " OR e.updated_at >= (NOW() - INTERVAL 1 DAY))")
    if ids:
        where.append("e.id IN (%s)" % ",".join(["%s"] * len(ids)))
        params.extend(ids)
    cur.execute("SELECT e.id, e.name, o.id oid, o.start_date, o.end_date, "
                "o.start_time, o.end_time "
                "FROM events e JOIN event_occurrences o ON o.event_id=e.id "
                "WHERE " + " AND ".join(where), tuple(params))
    per_event = {}
    for r in cur.fetchall():
        per_event.setdefault(r['id'], {'name': r['name'], 'rows': []})['rows'].append(r)

    out = []
    for eid, data in per_event.items():
        rows = data['rows']
        point_rows = [r for r in rows
                      if not r['end_date'] or (r['end_date'] - r['start_date']).days <= 1]
        points = {r['start_date'] for r in point_rows}
        if len(points) < 2:
            continue
        for r in rows:
            if not r['end_date']:
                continue
            length = (r['end_date'] - r['start_date']).days
            if not (SHORT_SPAN_MIN_DAYS <= length <= SHORT_SPAN_MAX_DAYS):
                continue
            covered, d = set(), r['start_date']
            while d <= r['end_date']:
                covered.add(d)
                d += timedelta(days=1)
            if covered - points:
                continue
            # The span may carry a clock time the points lack (Richmond County
            # Fair: span "12pm", points blank). Deleting it would silently drop
            # that time, so hand back the point rows that should inherit it.
            inherit = []
            if r['start_time']:
                inherit = [p['oid'] for p in point_rows
                           if p['start_date'] in covered and not p['start_time']]
            out.append((eid, data['name'], r['oid'], r['start_date'], r['end_date'],
                        r['start_time'], r['end_time'], inherit))
    return sorted(out)


def short_span_scan(conn, cur, apply_changes=False, recent_only=False, ids=None, exclude=None):
    """Review (default) or delete redundant 2-4 day envelope spans."""
    hits = find_redundant_short_spans(cur, recent_only=recent_only, ids=ids)
    if exclude:
        hits = [h for h in hits if h[0] not in exclude]
    scope = " created/updated in the last day" if recent_only else ""
    print(f"\nRedundant short ({SHORT_SPAN_MIN_DAYS}-{SHORT_SPAN_MAX_DAYS}d) envelope "
          f"spans{scope}: {len(hits)} across {len({h[0] for h in hits})} events.\n")
    for eid, name, oid, sd, ed, st, _et, inherit in hits:
        note = f"   [time {st!r} -> {len(inherit)} point(s)]" if inherit else ""
        print(f"  e{eid:<7} occ{oid:<8} {sd} -> {ed}  {name[:52]}{note}")
    if not hits:
        return
    if not apply_changes:
        print(f"\n(dry run — nothing written. Re-run with --short-spans --apply)")
        return
    # Delete by explicit occurrence id, never by a DATEDIFF range: the range form
    # used by the long-span path would also take sibling spans on the same event
    # that were NOT proved redundant.
    inherited = 0
    with write_lock(conn):
        for eid, _name, oid, _sd, _ed, st, et, inherit in hits:
            for pid in inherit:
                # `inherit` was computed against the ORIGINAL rows, so when one
                # event has several redundant spans carrying DIFFERENT times
                # (e165319: a 5pm span and a 6pm span over the same days) a naive
                # write lets the last one silently overwrite the first. Re-assert
                # the blank test in SQL so this is first-writer-wins and stable.
                cur.execute("UPDATE event_occurrences SET start_time=%s, "
                            "end_time=COALESCE(NULLIF(end_time,''),%s) "
                            "WHERE id=%s AND (start_time IS NULL OR start_time='')",
                            (st, et or '', pid))
                inherited += cur.rowcount
            cur.execute('DELETE FROM event_occurrences WHERE id=%s', (oid,))
            cur.execute('UPDATE events SET section=NULL WHERE id=%s', (eid,))
        conn.commit()
    print(f"\n[APPLIED] Deleted {len(hits)} redundant short span(s) across "
          f"{len({h[0] for h in hits})} events; propagated a time onto {inherited} "
          f"point(s) that would otherwise have lost it; section reset.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--apply', action='store_true', help='write changes (default is dry-run)')
    ap.add_argument('--ids', help='comma-separated event ids: restrict the scan to only these')
    ap.add_argument('--exclude', help='comma-separated event ids to drop from the fix set (manual-review escape hatch)')
    ap.add_argument('--show', help='comma-separated event ids: print full occurrence+description detail and exit (review aid)')
    ap.add_argument('--skipped', action='store_true', help='also list candidates that were skipped, with the reason')
    ap.add_argument('--review', action='store_true', help='broad scan: bucket ALL span-bearing events into review categories (FIX_SPAN / RECURRING_RANGE / INVERSE) and exit')
    ap.add_argument('--new', action='store_true', help='restrict to events created/updated in the last day (envelope spans just added by the current run). Scopes --review, the dry run AND --apply.')
    ap.add_argument('--short-spans', action='store_true',
                    help=f'scan for REDUNDANT {SHORT_SPAN_MIN_DAYS}-{SHORT_SPAN_MAX_DAYS} day '
                         'envelope spans (below the main threshold, so the normal scan misses '
                         'them). Only spans covering no date the discrete points already have '
                         'are listed. Combine with --apply to delete them.')
    args = ap.parse_args()

    conn = create_connection()
    cur = conn.cursor(dictionary=True)

    if args.show:
        show_events(cur, [int(x) for x in args.show.split(',')])
        return

    if args.short_spans:
        short_span_scan(
            conn, cur,
            apply_changes=args.apply,
            recent_only=args.new,
            ids=[int(x) for x in args.ids.split(',')] if args.ids else None,
            exclude=set(int(x) for x in args.exclude.split(',')) if args.exclude else None,
        )
        return

    if args.review:
        ids = [int(x) for x in args.ids.split(',')] if args.ids else None
        review_scan(cur, recent_only=args.new, ids=ids)
        return

    # --new must scope the APPLY path too, not just --review. Without this an
    # `--apply --new` silently writes across the entire backlog (the flag reads
    # as "only this run's events" and is used that way by /run-pipeline).
    recent_sql = (" AND (e.created_at >= (NOW() - INTERVAL 1 DAY)"
                  " OR e.updated_at >= (NOW() - INTERVAL 1 DAY))") if args.new else ""

    cur.execute('''
        SELECT e.id, e.name, e.description FROM events e
        WHERE e.archived=0 AND e.suppressed=0
          AND EXISTS (SELECT 1 FROM event_occurrences o WHERE o.event_id=e.id
                      AND o.end_date IS NOT NULL AND DATEDIFF(o.end_date,o.start_date)>%s)
          AND (SELECT COUNT(*) FROM event_occurrences o2 WHERE o2.event_id=e.id
               AND (o2.end_date IS NULL OR DATEDIFF(o2.end_date,o2.start_date)<=2)) >= 3
    ''' + recent_sql, (SPAN_THRESHOLD,))
    events = cur.fetchall()
    if args.ids:
        keep = set(int(x) for x in args.ids.split(','))
        events = [e for e in events if e['id'] in keep]
    exclude = set(int(x) for x in args.exclude.split(',')) if args.exclude else set()

    by_verdict = Counter()
    to_fix = []
    skipped = []
    for e in events:
        cur.execute('SELECT start_date,start_time,end_date,end_time FROM event_occurrences WHERE event_id=%s ORDER BY start_date', (e['id'],))
        occ = cur.fetchall()
        verdict, info = classify(e['id'], e['name'], occ, e.get('description'))
        by_verdict[verdict] += 1
        if verdict == 'skip':
            skipped.append((e['id'], e['name'], info.get('reason', '')))
            continue
        if e['id'] in exclude:
            by_verdict['excluded'] += 1
            skipped.append((e['id'], e['name'], 'EXCLUDED by --exclude'))
            continue
        dates = planned_dates(verdict, info)
        st, et = info['time']
        existing_disc = set(info['disc'])
        new_dates = [d for d in dates if d not in existing_disc and d >= TODAY]
        to_fix.append((e['id'], e['name'], verdict, info, dates, new_dates, st, et))

    # Second scan: course-shaped span-only events (exactly one occurrence, a
    # course-length span). These have no discrete dates, so the envelope scan
    # above never sees them; classify_course applies the same-weekday + signal
    # gates and the fix expands the span into the weekly series.
    cur.execute('''
        SELECT e.id, e.name, e.description FROM events e
        WHERE e.archived=0 AND e.suppressed=0
          AND (SELECT COUNT(*) FROM event_occurrences o WHERE o.event_id=e.id) = 1
          AND EXISTS (SELECT 1 FROM event_occurrences o WHERE o.event_id=e.id
                      AND o.end_date IS NOT NULL
                      AND DATEDIFF(o.end_date,o.start_date) BETWEEN %s AND %s)
    ''' + recent_sql, (COURSE_SPAN_MIN_DAYS, COURSE_SPAN_MAX_DAYS))
    course_events = cur.fetchall()
    if args.ids:
        keep = set(int(x) for x in args.ids.split(','))
        course_events = [e for e in course_events if e['id'] in keep]
    course_needs_ids = []  # COURSE_WEEKLY matches not approved via --ids
    for e in course_events:
        cur.execute('SELECT start_date,start_time,end_date,end_time FROM event_occurrences WHERE event_id=%s ORDER BY start_date', (e['id'],))
        occ = cur.fetchall()
        verdict, info = classify_course(e['name'], occ, e.get('description'))
        by_verdict[verdict if verdict != 'skip' else 'course_skip'] += 1
        if verdict == 'skip':
            skipped.append((e['id'], e['name'], 'course-scan: ' + info.get('reason', '')))
            continue
        if e['id'] in exclude:
            by_verdict['excluded'] += 1
            skipped.append((e['id'], e['name'], 'EXCLUDED by --exclude'))
            continue
        if not args.ids:
            # A same-weekday timed span can still be non-weekly (UFC PPV quarters);
            # course fixes need explicit per-id approval after a source check.
            course_needs_ids.append((e['id'], e['name'], info))
            continue
        dates = planned_dates(verdict, info)
        st, et = info['time']
        new_dates = [d for d in dates if d >= TODAY]
        to_fix.append((e['id'], e['name'], verdict, info, dates, new_dates, st, et))

    print(f"\nScanned {len(events)} envelope + {len(course_events)} course-shape candidates. "
          f"Verdicts: {dict(by_verdict)}\n")
    print(f"{'id':>7} {'verdict':10} {'name':46} discrete  span_end    +new_in_window")
    for eid, name, verdict, info, dates, new_dates, st, et in to_fix:
        tm = f"{st or '--'}-{et or '--'}"
        print(f"{eid:>7} {verdict:10} {name[:46]:46} n={len(info['disc']):<3} {tm:13} span_end={info['span_end']}  +{len(new_dates)} {[str(d) for d in new_dates] if new_dates else ''}")

    if course_needs_ids:
        print(f"\nCOURSE_WEEKLY matches needing per-id approval (verify weekly cadence via --show/source, "
              f"then re-run with --apply --ids <ids>):")
        for eid, name, info in course_needs_ids:
            n = len(planned_dates('course_weekly', info))
            print(f"  {eid:>7}  {name[:50]:50}  {info['span_start']}..{info['span_end']} "
                  f"({info['signal']}) -> {n} weekly dates")

    if args.skipped:
        print(f"\nSkipped {len(skipped)} candidates (use --show <ids> to inspect, --ids to force-include after review):")
        for eid, name, reason in skipped:
            print(f"  {eid:>7}  {name[:50]:50}  {reason}")

    if not args.apply:
        print(f"\n[DRY RUN] {len(to_fix)} events would be fixed. Review ambiguous cases with --show <ids>;\n"
              f"drop false positives with --exclude <ids>, then re-run with --apply.")
        return

    fixed = 0
    with write_lock(conn):  # shared DB: serialize the event_occurrences mutation
        for eid, name, verdict, info, dates, new_dates, st, et in to_fix:
            if verdict == 'course_weekly':
                # delete the single course span (>= COURSE_SPAN_MIN_DAYS, shorter
                # than the envelope threshold can catch)
                cur.execute('''DELETE FROM event_occurrences WHERE event_id=%s
                               AND end_date IS NOT NULL
                               AND DATEDIFF(end_date,start_date) BETWEEN %s AND %s''',
                            (eid, COURSE_SPAN_MIN_DAYS, COURSE_SPAN_MAX_DAYS))
            else:
                # delete envelope span occurrences
                cur.execute('''DELETE FROM event_occurrences WHERE event_id=%s
                               AND end_date IS NOT NULL AND DATEDIFF(end_date,start_date)>%s''', (eid, SPAN_THRESHOLD))
            # insert missing in-window discrete dates at the cadence time
            for d in new_dates:
                cur.execute('''INSERT INTO event_occurrences (event_id,start_date,start_time,end_date,end_time,sort_order)
                               VALUES (%s,%s,%s,NULL,%s,0)''', (eid, d, st or '', et or ''))
            # reset section so exporter reclassifies
            cur.execute('UPDATE events SET section=NULL WHERE id=%s', (eid,))
            fixed += 1
        conn.commit()
    print(f"\n[APPLIED] Fixed {fixed} events (deleted spans, added {sum(len(x[5]) for x in to_fix)} in-window dates, reset section).")


if __name__ == '__main__':
    main()
