"""Reviewed filter roots and validation shared by maintenance and publication.

Parentlessness is not permission to become a filter root. Validate both the
stored DAG and its public projection (which removes the Format family).
"""
from collections import defaultdict, deque

from city_config import get_config
from event_types import separate_format_topics
from tag_scopes import public_tag_key


def approved_roots(config=None, structural=True):
    cfg = config if config is not None else get_config()
    policy = cfg.get('frontend', {}).get('filter_roots')
    if not policy or not all(policy.get(key) for key in ('tag', 'venue')):
        raise ValueError('Configure frontend.filter_roots.tag and .venue before publishing')
    roots = {public_tag_key(name, scope)
             for key, scope in [('tag', 'event'), ('venue', 'venue')]
             for name in policy[key]}
    if structural:
        roots.update(public_tag_key(name, scope)
                     for scope, names in cfg.get('tag_hierarchy', {}).get('structural_roots', {}).items()
                     for name in names)
    return roots


def graph_findings(tags, roots):
    byname = {t['name']: t for t in tags}
    parents, children = defaultdict(set), defaultdict(set)
    invalid = []
    for tag in tags:
        for parent in tag.get('parents', []):
            if parent not in byname or byname[parent].get('scope', 'event') != tag.get('scope', 'event'):
                invalid.append([parent, tag['name']])
                continue
            parents[tag['name']].add(parent)
            children[parent].add(tag['name'])
    indegree = {n: len(parents[n]) for n in byname}
    queue = deque(n for n, degree in indegree.items() if not degree)
    while queue:
        for child in children[queue.popleft()]:
            indegree[child] -= 1
            if not indegree[child]:
                queue.append(child)
    reached, queue = set(), list(roots & byname.keys())
    while queue:
        name = queue.pop()
        if name in reached:
            continue
        reached.add(name)
        queue.extend(children[name])
    return {
        'unapproved_roots': sorted(n for n in byname if not parents[n] and n not in roots),
        'unreachable': sorted(byname.keys() - reached),
        'cycles_or_blocked_descendants': sorted(n for n, degree in indegree.items() if degree),
        'invalid_edges': sorted(invalid),
    }


def hierarchy_findings(tags, config=None):
    cfg = config if config is not None else get_config()
    roots = approved_roots(config)
    topics, _ = separate_format_topics(tags)
    public_roots = approved_roots(config, structural=False)
    public_names = {t['name'] for t in topics}
    return {
        'reviewed_parent_mismatches': sorted(
            public_tag_key(name, scope)
            for scope, assignments in cfg.get('tag_hierarchy', {}).get('parents', {}).items()
            for name, parents in assignments.items()
            for tag in tags if tag['name'] == public_tag_key(name, scope)
            and set(tag.get('parents', [])) != {public_tag_key(p, scope) for p in parents}
        ),
        'missing_browse_roots': sorted(public_roots - public_names),
        'stored': graph_findings(tags, roots),
        'public': graph_findings(topics, roots),
    }


def has_findings(report):
    return any(has_findings(value) if isinstance(value, dict) else bool(value)
               for value in report.values())


def validate_hierarchy(tags, config=None):
    report = hierarchy_findings(tags, config)
    if has_findings(report):
        raise ValueError(f'Tag hierarchy audit failed; run scripts/audit_tag_hierarchy.py: {report}')
    return report


def promote_tag(cursor, name, scope, parents, emoji, config=None):
    """Promote an existing keyword atomically; caller must hold write_lock.

    A reviewed root or at least one existing, same-scope curated parent is
    mandatory. Any invalid parent, cycle, or disconnected result rolls back
    this operation, including the type change. Never silently skip parents.
    """
    import db
    if scope not in ('event', 'venue') or not emoji or not emoji.strip():
        raise ValueError('An event/venue scope and emoji are required')
    if not parents and public_tag_key(name, scope) not in approved_roots(config):
        raise ValueError('A non-root promotion requires at least one curated parent')
    cursor.execute('SAVEPOINT tag_promotion')
    try:
        cursor.execute('SELECT id FROM tags WHERE name=%s AND scope=%s', (name, scope))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f'Unknown {scope} keyword: {name}')
        tag_id = db._col(row, 'id', 0)
        parent_ids = []
        for parent in parents:
            cursor.execute("SELECT id FROM tags WHERE name=%s AND scope=%s AND type='tag'", (parent, scope))
            row = cursor.fetchone()
            if row is None or parent == name:
                raise ValueError(f'Invalid {scope} parent: {parent}')
            parent_ids.append(db._col(row, 'id', 0))
        cursor.execute("UPDATE tags SET type='tag',emoji=%s WHERE id=%s", (emoji, tag_id))
        for parent_id in parent_ids:
            cursor.execute('INSERT IGNORE INTO tag_hierarchy(parent_tag_id,child_tag_id) VALUES(%s,%s)', (parent_id, tag_id))
        validate_hierarchy(db.get_tag_hierarchy_for_export(cursor), config)
    except Exception:
        cursor.execute('ROLLBACK TO SAVEPOINT tag_promotion')
        raise
    finally:
        cursor.execute('RELEASE SAVEPOINT tag_promotion')
    return tag_id
