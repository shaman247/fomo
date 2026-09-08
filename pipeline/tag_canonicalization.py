"""Pure tag identity helpers shared by ingestion, export and data repair.

Display spellings stay intact. Lookup keys follow the existing tag contract;
real homonyms still belong to context-based disambiguation, not fuzzy matching.
"""
from collections import defaultdict


def normalize_tag_key(name):
    return (name or '').lower().replace(' ', '')


class TagResolutionError(ValueError):
    pass


def canonical_names(tags):
    """Prefer a unique curated spelling; never choose between curated homonyms."""
    groups = defaultdict(list)
    for tag in tags:
        groups[normalize_tag_key(tag['name'])].append(tag)
    result = {}
    for key, group in groups.items():
        curated = [t for t in group if t['type'] == 'tag']
        candidates = curated or group
        if len(candidates) == 1:
            result[key] = candidates[0]['name']
    return result


def resolve_aliases(pairs, canonical=None):
    """Flatten alias chains and reject cycles or conflicting terminal targets.

    Several display aliases may share a key if they reach the same destination.
    A self-key edge (e.g. Maker Space -> Makerspace) is a spelling correction.
    """
    canonical = canonical or {}
    graph = defaultdict(set)
    for alias, target in pairs:
        key = normalize_tag_key(alias)
        if not key or not target:
            raise TagResolutionError('Alias and target must be nonempty')
        graph[key].add(target)
    resolved = {}

    def visit(key, path):
        if key in resolved:
            return resolved[key]
        if key in path:
            raise TagResolutionError('Tag alias cycle: ' + ' -> '.join((*path, key)))
        destinations = set()
        for target in sorted(graph[key]):
            target_key = normalize_tag_key(target)
            if target_key != key and target_key in graph:
                destinations.add(visit(target_key, (*path, key)))
            else:
                destinations.add(canonical.get(target_key, target))
        if len(destinations) != 1:
            raise TagResolutionError(f'Conflicting tag alias {key!r}: {sorted(destinations)}')
        resolved[key] = destinations.pop()
        return resolved[key]

    for key in sorted(graph):
        visit(key, ())
    return resolved


def resolve_tag_name(name, rewrites, canonical=None, ambiguous=()):
    """Resolve formatting/alias chains, stopping at context-dependent names."""
    canonical = canonical or {}
    seen = set()
    while True:
        key = normalize_tag_key(name)
        if key in ambiguous:
            return name
        if key in seen:
            raise TagResolutionError(f'Tag rewrite cycle at {name!r}')
        seen.add(key)
        target = rewrites.get(key)
        if target is None or normalize_tag_key(target) == key:
            return canonical.get(key, target or name)
        name = target


def stored_tag_mapping(tags, aliases, ambiguous=()):
    """Safe historical spelling/alias repairs; curated identities are immutable.

    Do not rewrite curated Format/topic nodes (Game -> Games, for example) or
    context-dependent raw homonyms. These require the separate facet redesign.
    """
    canonical = canonical_names(tags)
    known = {t['name'] for t in tags}
    result = {}
    for tag in tags:
        name = tag['name']
        if tag['type'] == 'tag' or normalize_tag_key(name) in ambiguous:
            continue
        target = resolve_tag_name(name, aliases, canonical, ambiguous)
        if target != name and target in known and normalize_tag_key(target) not in ambiguous:
            result[name] = target
    return result
