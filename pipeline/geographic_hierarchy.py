"""City-agnostic geographic hierarchy validation, repair planning and coverage."""
from collections import defaultdict


def descendants(edges, root='Neighborhood'):
    children = defaultdict(set)
    for parent, child in edges:
        children[parent].add(child)
    found, pending = set(), [root]
    while pending:
        name = pending.pop()
        if name not in found:
            found.add(name)
            pending.extend(children[name])
    return found


def plan_repairs(tags, edges, config):
    """Replace only geographic parents for explicitly reviewed children."""
    old_geo = descendants(edges)
    desired = {}
    for parent, children in config.get('groups', {}).items():
        for child in children:
            if child in desired and desired[child] != parent:
                raise ValueError(f'Multiple configured parents for {child}')
            desired[child] = parent
    managed = set(desired) | set(desired.values()) | set(config.get('promote', []))
    unknown = managed - tags.keys()
    # New heading names require explicit declaration, never silently fix typos.
    if unknown - set(config.get('promote', [])):
        raise ValueError(f'Unknown tags: {sorted(unknown)}')
    remove = {(p, c) for p, c in edges if c in desired and p in old_geo and p != desired[c]}
    add = {(p, c) for c, p in desired.items()} - edges
    final = (edges - remove) | add
    geo = descendants(final)
    if managed - geo:
        raise ValueError(f'Unreachable configured geography: {sorted(managed - geo)}')
    children = defaultdict(set)
    for p, c in final:
        if p in geo:
            children[p].add(c)
    done, active = set(), set()
    def visit(n):
        if n in active:
            raise ValueError(f'Geographic cycle at {n}')
        if n in done:
            return
        active.add(n)
        for c in children[n]:
            visit(c)
        active.remove(n)
        done.add(n)
    visit('Neighborhood')
    return {'add': sorted(add), 'remove': sorted(remove), 'create': sorted(unknown),
            'promote': sorted(n for n in geo if n in tags and tags[n]['type'] != 'tag')}


def event_counts(edges, event_tags):
    """Distinct events per branch, deduped across venue/event tags and ancestors."""
    geo = descendants(edges)
    parents = defaultdict(set)
    for p, c in edges:
        if p in geo and c in geo:
            parents[c].add(p)
    counts = dict.fromkeys(geo, 0)
    for tags in event_tags.values():
        found, pending = set(), list(set(tags) & geo)
        while pending:
            n = pending.pop()
            if n not in found:
                found.add(n)
                pending.extend(parents[n])
        for n in found:
            counts[n] += 1
    return counts


def load_event_counts(cursor, edges, website_gate, date_window):
    """Same mapped/unsuppressed/source/date eligibility as export_events."""
    today, limit = date_window
    cursor.execute(f'''
        SELECT DISTINCT e.id, t.name
        FROM events e
        JOIN locations l ON l.id=e.location_id
        LEFT JOIN websites w ON w.id=e.website_id
        JOIN (
            SELECT event_id, tag_id FROM event_tags
            UNION
            SELECT e2.id, lt.tag_id FROM events e2
            JOIN location_tags lt ON lt.location_id=e2.location_id
        ) assigned ON assigned.event_id=e.id
        JOIN tags t ON t.id=assigned.tag_id
        WHERE e.archived=FALSE AND e.suppressed=FALSE
          AND l.lat IS NOT NULL AND l.lng IS NOT NULL
          AND ({website_gate})
          AND EXISTS (SELECT 1 FROM event_occurrences o WHERE o.event_id=e.id
              AND o.start_date <= %s AND COALESCE(o.end_date,o.start_date) >= %s)
    ''', (limit, today))
    geo = descendants(edges)
    events = defaultdict(set)
    for event_id, tag in cursor.fetchall():
        if tag in geo:
            events[event_id].add(tag)
    return event_counts(edges, events)
