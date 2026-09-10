"""Scoped tag identities. Display names may repeat across event and venue tags."""
VENUE_PREFIX = 'venue:'


def public_tag_key(name, scope):
    return VENUE_PREFIX + name if scope == 'venue' else name


def migration_plan(tags, edges, venue_names, event_parents=None):
    """Keep existing event IDs; copy location memberships into venue identities.

    Only explicit venue types and geographic descendants become venue filters.
    Location topics become venue keywords, never implicit event memberships.
    """
    byid = {t['id']: t for t in tags}
    byname = {t['name']: t for t in tags}
    venue = set(venue_names)
    geographic = {'Neighborhood'}
    for root, names in [('Neighborhood', geographic), ('Venue', venue)]:
        queue = [byname[root]['id']] if root in byname else []
        seen = set()
        while queue:
            tid = queue.pop()
            if tid in seen:
                continue
            seen.add(tid)
            names.add(byid[tid]['name'])
            queue.extend(c for p, c in edges if p == tid and byid[c]['type'] == 'tag')
    venue |= geographic
    dual = event_parents or {}
    for name, parents in dual.items():
        if name not in byname or any(p not in byname for p in parents):
            raise ValueError(f'Unknown dual-purpose tag/parent: {name}')
    demote = {t['id'] for t in tags if t['name'] in venue and t['name'] not in dual}
    event_edges = {(p, c) for p, c in edges if p not in demote and c not in demote}
    for name, parents in dual.items():
        for parent in parents:
            event_edges.add((byname[parent]['id'], byname[name]['id']))
    venue_edges = {(p, c) for p, c in edges
                   if byid[p]['name'] in venue and byid[c]['name'] in venue}
    return dict(venue_names=venue, demote=demote, event_edges=event_edges, venue_edges=venue_edges)
