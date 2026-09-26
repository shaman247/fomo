"""Equivalent overnight slots, using an explicit next-day counterpart only."""

from datetime import date, timedelta

from occurrence_times import TWELVE_HOUR_RE, standardize_time


def _clock_minutes(value):
    match = TWELVE_HOUR_RE.fullmatch(standardize_time(value))
    if not match:
        return None
    hour, minute = int(match[1]), int(match[2] or 0)
    if not (1 <= hour <= 12 and 0 <= minute < 60):
        return None
    return (hour % 12 + (12 if match[3] == 'pm' else 0)) * 60 + minute


def _signature(row):
    """A fully timed slot whose clock crosses midnight, without guessing dates."""
    sd, st, _ed, et = row[:4]
    if not isinstance(sd, date):
        return None
    start, end = _clock_minutes(st), _clock_minutes(et)
    if start is None or end is None or end >= start:
        return None
    return sd, start, end


def coalesce_overnight_occurrences(existing, incoming):
    """Return retained existing/incoming rows and exact existing rows to remove.

    An accepted row with an explicit next-day end can absorb its exact timed
    null-end twin. Unknown clocks, different clocks, and other date spans stay
    independent. Only signatures present in this incoming batch are touched;
    unrelated historical duplicates are not swept. Original tuples and source
    evidence are preserved, including any trailing fields.
    """
    existing, incoming = list(existing), list(incoming)
    touched = {_signature(row) for row in incoming} - {None}
    if not touched:
        return existing, incoming, []
    # The downstream merge keeps the first nonempty end clock per date key.
    # If a competing clock exists, an incoming explicit twin may not actually
    # survive that merge. Keep the null-date evidence too in that case.
    end_clocks = {}
    ambiguous_ends = set()
    for row in existing + incoming:
        start, end = _clock_minutes(row[1]), _clock_minutes(row[3])
        if start is not None and end is not None:
            end_clocks.setdefault((row[0], start), set()).add(end)
        elif start is not None and row[3]:
            # Existing first-writer checks use the stored string's truthiness.
            # Even a sentinel that standardizes to empty (e.g. legacy 'TBA')
            # can therefore prevent the explicit qualified twin from landing.
            # Actual empty/NULL clocks remain safely promotable.
            ambiguous_ends.add((row[0], start))
    explicit = {
        sig for row in existing + incoming
        if (sig := _signature(row)) in touched
        and (sig[0], sig[1]) not in ambiguous_ends
        and len(end_clocks[(sig[0], sig[1])]) == 1
        and row[2] == row[0] + timedelta(days=1)
    }

    def redundant(row):
        return row[2] is None and _signature(row) in explicit

    removed = [row for row in existing if redundant(row)]
    return ([row for row in existing if not redundant(row)],
            [row for row in incoming if not redundant(row)], removed)


def reconcile_overnights(cursor, event_id, existing, incoming):
    """Delete only evidenced null-end twins; never mutate crawl evidence."""
    retained, incoming, removed = coalesce_overnight_occurrences(existing, incoming)
    for row in removed:
        cursor.execute(
            'DELETE FROM event_occurrences WHERE event_id = %s '
            'AND start_date = %s AND start_time = %s AND end_date IS NULL '
            'AND end_time = %s', (event_id, row[0], row[1], row[3]))
    return retained, incoming
