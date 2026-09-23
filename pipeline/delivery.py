"""Delivery labels are source evidence, independent of physical organizer pins."""
import re

# Delivery-method detection from the raw source `location` string (stored as
# `events.location_name`). Per `.claude/rules/tag-system.md` §Virtual, virtual
# events are still pinned to their organizer's venue, so `location_name` — not
# `locations.name` — is the only reliable signal, and the `Virtual` tag is what
# lets users filter them. Ordered: first match wins for the leaf; the `Virtual`
# root is always added on top of it.
# Patterns are regexes matched against the lowercased location string.
VIRTUAL_LOCATION_PATTERNS = [
    (r'\bzoom\b(?!\s*room)', 'Zoom'),          # "Zoom", "Via Zoom Platform"; not the "Zoom Room" gyms
    (r'\bwebinars?\b', 'Webinar'),
    (r'live\s*stream|livestream|streaming', 'Live Stream'),
    (r'\bvirtual\s+tour\b', 'Virtual Tour'),
    (r'\bonline\b|microsoft\s+teams|\bms\s+teams\b|google\s+meet|\bwebex\b|google\s+hangouts?',
     'Online'),
    (r'\bvirtual\b|\bremote(?:ly)?\b', None),  # root only — no platform named
]


def virtual_tags_for_location(location_str):
    """Returns the Virtual-family tags implied by a raw source location string.

    Returns [] when the string names no online delivery, else ['Virtual'] plus
    at most one platform/format leaf. Hybrids ("Online & In-Person") are
    intentionally included: they *are* attendable online, and the `Virtual` tag
    is a delivery filter, not an exclusivity claim.
    """
    loc = (location_str or '').lower()
    if not loc:
        return []
    for pattern, leaf in VIRTUAL_LOCATION_PATTERNS:
        if re.search(pattern, loc):
            return ['Virtual', leaf] if leaf else ['Virtual']
    return []


def canonical_location_label(source_label, venue_label):
    """Keep explicit online/hybrid attendance text on a new mapped event."""
    return source_label if virtual_tags_for_location(source_label) else venue_label or source_label
