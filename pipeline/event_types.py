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
        "Tasting",
        "Camp",
        "Fitness",
        "Game",
        "Open Practice",
        "Volunteer",
        "Drop-In Service",
        # A scheduled sitting where the attendee is formally assessed: SAT/PSAT/
        # ACT practice exams, certification/licensing exam sessions. Instruction
        # ABOUT a test ("Citizenship Exam Prep") is a Class, not an Exam.
        "Exam",
        # No gathering to attend: you participate on your own time across a
        # published window, with the venue supplying the prompt, log or
        # materials (reading challenges, film challenges, decorate-and-return
        # contests, Inktober drop-ins). An entry-by-submission open call with
        # no venue-side participation is NOT this -- it is not an event at all
        # and `processor.is_obvious_non_event` filters it upstream.
        "Self-Paced Challenge",
        # In-person voting at a designated poll site -- early-voting days and
        # Election Day poll hours. A genuine dated civic occurrence with posted
        # hours; distinct from `Civic Meeting` (no agenda, no convening) and
        # from `Drop-In Service` (a civic transaction, not a service you receive).
        "Voting",
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
        "Mixer",
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
# (Format -> category -> type) for pipeline compatibility. The public exporter
# separates formats from topic browsing; the selector uses event_type directly.
# These map the taxonomy onto legacy tag nodes. See scripts/sync_format_tags.py.

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
    "Class": "🎓", "Workshop": "🛠️", "Tasting": "🍷", "Camp": "🏕️", "Fitness": "🏋️", "Game": "🎲",
    "Open Practice": "🔄", "Volunteer": "🤝", "Drop-In Service": "🩺", "Exam": "📝",
    "Self-Paced Challenge": "🎯", "Voting": "🗳️",
    "Exhibition": "🖼️", "Open House": "🚪", "Market": "🛍️", "Fair": "🪧",
    "Pop-Up": "✨", "Immersive Experience": "🌌",
    "Club Night": "🪩", "Party": "🎉", "Mixer": "🫂", "Benefit": "🎗️", "Watch Party": "📺",
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

# Existing topic identities that also name an event format. Sports is a topic
# root, so it cannot be detected just by looking for non-Format parents.
FORMAT_TOPIC_NAMES = frozenset({
    'Concert', 'Sports', 'Reading', 'Workshop', 'Fitness', 'Volunteer', 'Party', 'Festival',
})


def separate_format_topics(tags):
    """Return the topic browse graph and format-only names, leaving DB IDs intact."""
    structural = {value[0] for value in CATEGORY_TAG.values()} | {FORMAT_ROOT_TAG}
    format_only = structural | (set(EVENT_TYPES) - FORMAT_TOPIC_NAMES)
    topics = [{**tag, 'parents': [p for p in tag.get('parents', []) if p not in format_only]}
              for tag in tags if tag['name'] not in format_only]
    return topics, format_only
