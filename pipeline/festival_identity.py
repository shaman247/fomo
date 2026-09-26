"""Bounded distinction between a festival span and its numbered night/day."""
import re
from datetime import date, timedelta

from occurrence_times import standardize_time

_NUMBER = r'(?:[1-9]\d?|one|two|three|four|five|six|seven|eight|nine|ten)'
_MEMBER = re.compile(r'(?:[:–—]\s*|\s-\s*|\(\s*)(?:day|night)\s+' + _NUMBER + r'\s*\)?$', re.I)
_ANY_NUMBERED = re.compile(r'\b(?:days?|nights?)\s+(?:' + _NUMBER + r'|[ivxlcdm]+)\b', re.I)
_CLOCK = re.compile(r'([1-9]|1[0-2])(?::([0-5]\d))?([ap]m)')


def _minutes(clock):
    match = _CLOCK.fullmatch(clock or '')
    if match:
        return (int(match[1]) % 12 + (12 if match[3] == 'pm' else 0)) * 60 + int(match[2] or 0)
    return None


def numbered_member_pair(left, right):
    """Require both festival labels and exactly one explicit terminal member.

    Grouped labels and bare numbers do not identify a single member. This is
    only a prefilter; names alone never establish the schedule distinction.
    """
    if not all(re.search(r'\bfestival\b', n or '', re.I) for n in (left, right)):
        return False
    a, b = (bool(_MEMBER.search(n)) and len(_ANY_NUMBERED.findall(n)) == 1
            for n in (left, right))
    return bool(a != b and not _ANY_NUMBERED.search(right if a else left))


def numbered_festival_span_mismatch(left, left_rows, right, right_rows):
    """Veto a partial match only with a broad span and a single timed member.

    The umbrella needs one explicit span of at least two elapsed days. Its
    member needs one timed occurrence lasting at most one day. Both source
    date endpoints are preserved: this function never manufactures dates or
    resolves inconsistent publisher clocks. Missing/grouped schedules decline.
    """
    if not numbered_member_pair(left, right):
        return False
    member, umbrella = ((left_rows, right_rows) if _MEMBER.search(left)
                        else (right_rows, left_rows))
    def rows(values):
        return {(date.fromisoformat(str(r[0])) if r[0] else None,
                 standardize_time(r[1]),
                 date.fromisoformat(str(r[2])) if r[2] else None,
                 standardize_time(r[3])) for r in values}
    try:
        member, umbrella = rows(member), rows(umbrella)
    except (ValueError, TypeError, IndexError):
        return False
    if len(member) != 1 or len(umbrella) != 1:
        return False
    ms, mt, me, mend = next(iter(member))
    us, _, ue, _ = next(iter(umbrella))
    start_minutes = _minutes(mt)
    if not all((ms, us, ue)) or start_minutes is None:
        return False
    me = me or ms
    if me == ms + timedelta(days=1):
        end_minutes = _minutes(mend)
        if end_minutes is None or end_minutes > start_minutes:
            return False
    return bool(ue - us >= timedelta(days=2)
                and ms <= me <= ms + timedelta(days=1)
                and us <= ms < ue and me <= ue)
