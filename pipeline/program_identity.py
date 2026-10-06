"""Conservative format/schedule evidence for exhibitions and timed companions."""

from datetime import date
import re
import unicodedata

from event_types import EVENT_TYPES

_EVENT_FORMATS = frozenset(EVENT_TYPES)
_CLOCK = re.compile(r'(?:[1-9]|1[0-2])(?::[0-5]\d)?[ap]m')


def volunteer_program_mismatch(left_name, right_name):
    """An explicit volunteer registration is distinct from its exact program.

    This only handles the named registration prefix, not generic volunteer
    wording, ordinary registration labels, or titles that merely share words.
    """
    def words(value):
        value = unicodedata.normalize('NFKC', value or '').casefold()
        return ' '.join(re.findall(r'[^\W_]+', value, re.UNICODE))

    left, right = words(left_name), words(right_name)
    prefix = 'volunteer registration for '
    if not left or not right or left.startswith(prefix) == right.startswith(prefix):
        return False
    volunteer, program = (left, right) if left.startswith(prefix) else (right, left)
    return volunteer[len(prefix):] == program


def program_profile(formats, occurrences):
    """Return a profile only for one explicit format and a uniform schedule.

    Occurrences are (start_date, start_time, end_date, end_time, ...).
    Topic/category tags are harmless; multiple event formats are ambiguous.
    Missing clocks, mixed schedules and receptions remain undecided.
    """
    formats = set(formats) & _EVENT_FORMATS
    if formats not in ({'Exhibition'}, {'Talk'}, {'Tour'}) or not occurrences:
        return None
    for start, start_time, end, end_time, *_ in occurrences:
        try:
            start = date.fromisoformat(str(start))
            end = date.fromisoformat(str(end)) if end else start
        except (TypeError, ValueError):
            return None
        if formats == {'Exhibition'}:
            if start_time or end_time or end <= start:
                return None
        elif not _CLOCK.fullmatch(start_time or '') or end != start:
            return None
    return next(iter(formats))


def conflicting_program_profiles(left, right):
    """A timed talk or tour is distinct from an untimed exhibition run."""
    return ({left, right} == {'Exhibition', 'Talk'}
            or {left, right} == {'Exhibition', 'Tour'})
