"""Explicit named exhibition companions must keep their own source schedules.

A broad exhibition may include its reception's date and clock. Shared slots
therefore cannot prove that its separately named reception is the same event.
This rule needs both an exact title-plus-kind relation and an explicit broad
Exhibition schedule; it does not generalize ordinary title containment.
"""

from datetime import date
import re
import unicodedata

from event_types import EVENT_TYPES

_FORMATS = frozenset(EVENT_TYPES)
_KINDS = frozenset({
    'opening reception', 'closing reception', 'artist reception',
    'artists reception', 'reception', 'opening celebration',
    'closing celebration', 'opening party', 'closing party',
    'opening night', 'closing night', 'opening weekend', 'closing weekend',
    'opening for', 'closing for',
    'vernissage', 'finissage', 'artist talk', 'artists talk', 'gallery talk',
    'curator talk', 'curators talk', 'curatorial talk', 'coffee curator',
    'artist presentation',
    'artists presentation', 'artist conversation', 'artists conversation',
    'curator tour', 'curators tour', 'curator led tour', 'gallery tour',
    'exhibition tour', 'guided exhibition tour', 'installation tour',
    'artist walkthrough', 'artists walkthrough', 'press preview',
    'vip preview', 'member preview', 'members preview', 'private view',
    'behind scenes', 'member evening viewing', 'members evening viewing',
    'member mornings last look', 'members mornings last look',
    'play sets',
})
_FILLER = frozenset({'the', 'a', 'an', 'and', 'of', 'for', 'with', 'at', 'to',
                     'on', 'in', 'event', 'events', 'exhibition', 'exhibitions',
                     'exhibit', 'exhibits', 'show', 'shows'})


def _words(value):
    # A delimited gallery label is presentation, not part of the artwork title.
    # Only a short label literally ending in Gallery qualifies.
    value = value or ''
    value = re.sub(
        r'\s+[—–]\s+(?:floor \d+,?\s*)?(?:free )?(?:second sundays|friday nights)$',
        '', value, flags=re.I)
    parts = re.split(r'\s+[—–|]\s+|:\s+', value, maxsplit=1)
    if (len(parts) == 2 and len(parts[0].split()) <= 6
            and re.search(r'\bgallery$', parts[0], re.I)
            and len(parts[1].split()) >= 3):
        value = parts[1]
    value = unicodedata.normalize('NFKC', value or '').casefold()
    value = re.sub(r"[’']s\b", 's', value)
    return ' '.join(re.findall(r'[^\W_]+', value, re.UNICODE))


def _companion_pair(left_name, right_name):
    """Return (parent side, optional access kind) for an exact named pair.

    Keep the parent text intact: generic titles, arbitrary subtitles, bare
    opening/closing/talk/tour and doubled kind labels are not evidence.
    """
    names = (_words(left_name), _words(right_name))
    if not all(names) or names[0] == names[1]:
        return None
    side = 0 if len(names[0]) < len(names[1]) else 1
    parent, companion = names[side], names[1 - side]
    if len(parent.replace(' ', '')) < 4:
        return None
    if companion.startswith(parent + ' '):
        leftover = companion[len(parent) + 1:]
    elif companion.endswith(' ' + parent):
        leftover = companion[:-(len(parent) + 1)]
    else:
        return None
    kind = ' '.join(word for word in leftover.split() if word not in _FILLER)
    # "Opening for <exact exhibition>" explicitly names the companion. A
    # bare "Opening" suffix still lacks this relation and remains ambiguous.
    if leftover in ('opening for', 'closing for') and companion.endswith(' ' + parent):
        kind = leftover
    # Preserve the format-bearing word in an explicit Exhibition Tour label.
    literal_kind = ' '.join(word for word in leftover.split()
                            if word not in _FILLER - {'exhibition', 'exhibit'})
    if literal_kind in _KINDS:
        kind = literal_kind
    # Accessibility program branding may repeat the parent's first word.
    # Its format/access tags must corroborate in exhibition_companion_mismatch.
    brand = parent.split()[0]
    access_kind = kind in (brand + ' signs', brand + ' descriptions online')
    if (kind not in _KINDS and not access_kind
            and not re.fullmatch(r'\d{1,3} minute tour(?: highlights)?', kind)):
        return None
    # A longer spelling of an already named satellite is still that satellite.
    if any(re.search(r'\b' + re.escape(k) + r'\b', parent) for k in _KINDS):
        return None
    return side, kind if access_kind else None


def companion_parent_side(left_name, right_name):
    """Cheap title-only prescreen; mismatch also verifies format/schedule evidence."""
    pair = _companion_pair(left_name, right_name)
    return pair[0] if pair is not None else None


def broad_exhibition_schedule(formats, occurrences):
    """Explicit Exhibition over >2 days, as a span or >=3 discrete dates.

    Clocks and mixed span/point rows are allowed: public exhibition hours and
    an embedded reception date do not turn the exhibition into its companion.
    All dates must parse; multiple contradictory format labels remain unknown.
    """
    if set(formats or ()) & _FORMATS != {'Exhibition'}:
        return False
    days = set()
    broad_span = False
    for start, _start_time, end, _end_time, *_ in occurrences or ():
        try:
            start = date.fromisoformat(str(start))
            end = date.fromisoformat(str(end)) if end else start
        except (TypeError, ValueError):
            return False
        if end < start:
            return False
        broad_span |= (end - start).days > 2
        days.add(start)
    return broad_span or (len(days) >= 3 and (max(days) - min(days)).days > 2)


def exhibition_companion_mismatch(left_name, left_formats, left_occurrences,
                                   right_name, right_formats, right_occurrences):
    """Whether two named records are a broad exhibition and its companion.

    Bidirectional, deliberately independent of URL equality and shared slots.
    A one-day exhibition and its opening-night spelling remain undecided.
    """
    pair = _companion_pair(left_name, right_name)
    if pair is None:
        return False
    parent, access_kind = pair
    if access_kind:
        companion_formats = set((right_formats if parent == 0 else left_formats) or ())
        if access_kind.endswith(' signs'):
            if not companion_formats & {'Tour', 'ASL', 'Sign Language', 'Accessibility'}:
                return False
        elif 'Tour' not in companion_formats:
            return False
    formats, occurrences = ((left_formats, left_occurrences) if parent == 0
                            else (right_formats, right_occurrences))
    return broad_exhibition_schedule(formats, occurrences)
