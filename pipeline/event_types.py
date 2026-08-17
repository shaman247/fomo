"""
Canonical event-type taxonomy — single source of truth for the labels.

The *prose* taxonomy (definitions + decision rules) lives in
`.claude/commands/classify-event-types.md`. This module is the machine-readable
counterpart: the exact set of valid storage strings, their grouping into the
six experience categories, and helpers for validation. Anything that reads or
writes `events.event_type` (classifier, pipeline integration, exporter,
audit/QA tooling) should import from here rather than hard-coding strings, so
the taxonomy can never silently drift between consumers.

When adding a type: add it to EVENT_TYPES_BY_CATEGORY here AND document it (with
its decision rules and boundaries vs. neighbouring types) in the command doc.
Keep the two in sync.
"""

# The organizing question is "what is the attendee doing?" — orthogonal to the
# content/venue/neighborhood tag axes. Ordered by category.
EVENT_TYPES_BY_CATEGORY = {
    # Performance — audience watches a billed showing
    "Performance": [
        "Concert",
        "Theater Show",
        "Comedy Show",
        "Screening",
        "Sports",
        "Reading",
    ],
    # Participatory — attendee is the active subject
    "Participatory": [
        "Class",
        "Workshop",
        "Camp",
        "Fitness",
        "Game",
        "Open Practice",
        "Volunteer",
        "Drop-In Service",
    ],
    # Browsable — self-paced consumption of a curated environment
    "Browsable": [
        "Exhibition",
        "Open House",
        "Market",
        "Fair",
        "Pop-Up",
        "Immersive Experience",
    ],
    # Social — open-ended gathering; being among others is the point
    "Social": [
        "Club Night",
        "Party",
        "Benefit",
        "Watch Party",
        "Festival",
        "Community Celebration",
    ],
    # Gathering — facilitated convening around topic/faith/function
    "Gathering": [
        "Talk",
        "Service",
        "Ceremony",
        "Civic Meeting",
        "Discussion Group",
    ],
    # Outing — bounded group experience anchored to a place
    "Outing": [
        "Tour",
        "Outing",
    ],
}

# Genuine event but no taxonomy fit — flag for review. Not a category member.
OTHER = "Other"
# Not an event at all (closures, submissions, marketing) — upstream junk.
UNKNOWN = "UNKNOWN"

# Flat ordered list of the real structural types (no Other/UNKNOWN).
EVENT_TYPES = [t for types in EVENT_TYPES_BY_CATEGORY.values() for t in types]

# Every string that may legally appear in events.event_type.
VALID_EVENT_TYPES = frozenset(EVENT_TYPES) | {OTHER, UNKNOWN}

# Reverse lookup: type label -> category name (Other/UNKNOWN are uncategorized).
CATEGORY_BY_TYPE = {
    t: category
    for category, types in EVENT_TYPES_BY_CATEGORY.items()
    for t in types
}


# --- Tag-system presentation ---------------------------------------------------
# event_type is mirrored into the curated tag hierarchy as a "Format" root family
# (Format -> category -> type) so it filters/searches like any tag. These map the
# taxonomy onto tag nodes. See scripts/sync_format_tags.py.

FORMAT_ROOT_TAG = "Format"
FORMAT_ROOT_EMOJI = "🎫"

# Category internal-name -> (tag node name, emoji). Tag names match the taxonomy
# category names exactly (identity) so there is no naming drift to maintain. The
# ONE unavoidable exception is "Outing": the category would collide with the leaf
# type "Outing" (tags.name is UNIQUE), so the category tag is "Outings" (plural)
# while the leaf stays "Outing".
CATEGORY_TAG = {
    "Performance":   ("Performance", "▶️"),
    "Participatory": ("Participatory", "🙌"),
    "Browsable":     ("Browsable", "👀"),
    "Social":        ("Social", "🥂"),
    "Gathering":     ("Gathering", "👥"),
    "Outing":        ("Outings", "🧭"),
}

# Per-type emoji for the Format leaf tags (curated tags must carry an emoji).
TYPE_EMOJI = {
    "Concert": "🎤", "Theater Show": "🎭", "Comedy Show": "😂", "Screening": "🎬",
    "Sports": "🏟️", "Reading": "📖",
    "Class": "🎓", "Workshop": "🛠️", "Camp": "🏕️", "Fitness": "🏋️", "Game": "🎲",
    "Open Practice": "🔄", "Volunteer": "🤝", "Drop-In Service": "🩺",
    "Exhibition": "🖼️", "Open House": "🚪", "Market": "🛍️", "Fair": "🪧",
    "Pop-Up": "✨", "Immersive Experience": "🌌",
    "Club Night": "🪩", "Party": "🎉", "Benefit": "🎗️", "Watch Party": "📺",
    "Festival": "🎡", "Community Celebration": "🎊",
    "Talk": "🗣️", "Service": "🙏", "Ceremony": "🎖️", "Civic Meeting": "🏛️",
    "Discussion Group": "💬",
    "Tour": "🧭", "Outing": "🥾",
}


def is_valid_event_type(value):
    """True if value is a storable event_type string (incl. Other/UNKNOWN)."""
    return value in VALID_EVENT_TYPES


def category_for(event_type):
    """Return the experience category for a type, or None for Other/UNKNOWN."""
    return CATEGORY_BY_TYPE.get(event_type)
