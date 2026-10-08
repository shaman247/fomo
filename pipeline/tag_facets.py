"""Facet semantics for event tags: topic ancestry versus authoritative Format.

Format membership (the Format root, its six categories and the 30 exclusive
type leaves) comes only from `events.event_type`. Topic ancestry and keyword
inference never reach those nodes. The eight shared names in
`event_types.FORMAT_TOPIC_NAMES` are also topics: content evidence derives their
topic parents, but a leaf added only because of `event_type` does not (a kids'
craft Workshop is not thereby Education). See .claude/notes/backlog-bl15-tags-20261007.md.
"""
from collections import defaultdict

import event_types as et

FORMAT_ROOT = et.FORMAT_ROOT_TAG
FORMAT_CATEGORIES = frozenset(name for name, _ in et.CATEGORY_TAG.values())
SHARED_LEAVES = et.FORMAT_TOPIC_NAMES
FORMAT_EXCLUSIVE = frozenset({FORMAT_ROOT} | FORMAT_CATEGORIES
                             | (set(et.EVENT_TYPES) - SHARED_LEAVES))
# Names that may belong to the Format family at all (exclusive + shared leaves).
FORMAT_FAMILY = FORMAT_EXCLUSIVE | SHARED_LEAVES


def format_membership(event_type):
    """Exact Format-family names implied by an event_type (empty for Other/None)."""
    category = et.category_for(event_type)
    if not category:
        return frozenset()
    return frozenset({event_type, et.CATEGORY_TAG[category][0], FORMAT_ROOT})


def topic_edges(edges):
    """Drop parent->child edges that touch a Format-exclusive node."""
    return [(p, c) for p, c in edges if p not in FORMAT_EXCLUSIVE and c not in FORMAT_EXCLUSIVE]


def parent_map(edges):
    parents = defaultdict(set)
    for parent, child in edges:
        parents[child].add(parent)
    return parents


def ancestors(name, parents):
    found, queue = set(), list(parents.get(name, ()))
    while queue:
        parent = queue.pop()
        if parent not in found:
            found.add(parent)
            queue.extend(parents.get(parent, ()))
    return found


def topic_closure(names, parents, event_type=None):
    """Names plus topic ancestors; a format-implied shared leaf adds no parents."""
    result = set(names)
    for name in names:
        if name in SHARED_LEAVES and name == event_type:
            continue
        result |= ancestors(name, parents)
    return result


def derive_event_tags(direct, event_type, parents, roots, blocked=()):
    """Idempotent membership: topic closure + authoritative Format − blocks.

    `parents` must already exclude Format-exclusive edges (see topic_edges).
    The keyword `Other` is added when no topic root is present, matching
    process_tags. Blocks are binding, as in db.upsert_event_tags.
    """
    names = {n for n in direct if n not in FORMAT_EXCLUSIVE}
    names = topic_closure(names, parents, event_type) | format_membership(event_type)
    if not names & set(roots) and 'Other' not in names:
        names.add('Other')
    return names - set(blocked)


def missing_topic_ancestors(names, event_type, parents, blocked=()):
    """Topic ancestors that closure requires but the membership lacks."""
    names = set(names)
    return topic_closure(names - FORMAT_EXCLUSIVE, parents, event_type) - names - set(blocked)


def format_drift(names, event_type, blocked=()):
    """(extra, missing) Format-exclusive names relative to event_type."""
    want = format_membership(event_type) - set(blocked)
    have = set(names) & FORMAT_EXCLUSIVE
    return have - want, {n for n in want - set(names) if n in FORMAT_FAMILY}


def shadowing_aliases(aliases, curated):
    """Alias rows whose key names a *different* curated tag.

    `aliases`: iterable of (alias, target); `curated`: curated event tag names.
    Returns (alias, target, shadowed, rewrites_topic_into_format) tuples.
    """
    from tag_canonicalization import normalize_tag_key
    bykey = {normalize_tag_key(n): n for n in curated}
    found = []
    for alias, target in aliases:
        shadowed = bykey.get(normalize_tag_key(alias))
        if shadowed and shadowed != target:
            found.append((alias, target, shadowed,
                          shadowed not in FORMAT_EXCLUSIVE and target in FORMAT_EXCLUSIVE))
    return sorted(found)
