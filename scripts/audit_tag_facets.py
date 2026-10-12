#!/usr/bin/env python3
"""Event tag scope/facet health check (BL15). Read-only unless --apply.

Exit 0: converged (no findings). Exit 1: findings. Informational counts never
fail the check. `--apply --backup <new.json>` repairs the two derivable findings
(Format mirror drift, missing topic ancestors and the Other fallback) through db.upsert_event_tags
under the shared write lock, then re-checks inside the transaction and commits
only if both reach zero. Everything else needs review, not a blanket rewrite.

    ./venv/bin/python scripts/audit_tag_facets.py --output .scratch/<run>/facets.json
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
import db
import tag_facets as tf
from dblock import write_lock

# Eligibility/skill terms that must not imply family intent. BL23 ruling: they
# live under Age (Beginner Friendly under Education), and Family needs intent.
ELIGIBILITY = ('All Ages', 'Young Adults', 'Beginner Friendly', '18+', '21+')
DELIVERY_ROOT = 'Virtual'


def read(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def load(cur):
    tags = {r[0]: dict(name=r[1], type=r[2], scope=r[3])
            for r in read(cur, 'SELECT id, name, type, scope FROM tags')}
    event = {i: t['name'] for i, t in tags.items() if t['scope'] == 'event'}
    edges = [(event[p], event[c]) for p, c in read(cur, 'SELECT parent_tag_id, child_tag_id FROM tag_hierarchy')
             if p in event and c in event]
    types = dict(read(cur, 'SELECT id, event_type FROM events WHERE archived=0 AND suppressed=0'))
    mem, wrong_scope = defaultdict(set), 0
    for eid, tid in read(cur, 'SELECT et.event_id, et.tag_id FROM event_tags et JOIN events e ON e.id=et.event_id '
                              'WHERE e.archived=0 AND e.suppressed=0'):
        if tid in event:
            mem[eid].add(event[tid])
        else:
            wrong_scope += 1
    blocks = defaultdict(set)
    for eid, tid in read(cur, 'SELECT event_id, tag_id FROM event_tag_blocks'):
        if tid in event:
            blocks[eid].add(event[tid])
    location_wrong_scope = read(cur, "SELECT COUNT(*) FROM location_tags lt JOIN tags t ON t.id=lt.tag_id "
                                     "WHERE t.scope<>'venue'")[0][0]
    aliases = read(cur, "SELECT a.alias, t.name FROM tag_aliases a JOIN tags t ON t.id=a.tag_id "
                        "WHERE a.scope='event' AND t.scope='event'")
    curated = {t['name'] for t in tags.values() if t['scope'] == 'event' and t['type'] == 'tag'}
    _, roots = db.build_tag_ancestor_map(cur)
    return dict(types=types, mem=mem, blocks=blocks, edges=edges, aliases=aliases, curated=curated, roots=roots,
                event_wrong_scope=wrong_scope, location_wrong_scope=location_wrong_scope)


def check(state):
    types, mem, blocks = state['types'], state['mem'], state['blocks']
    parents = tf.parent_map(tf.topic_edges(state['edges']))
    drift, missing = {}, {}
    extra, lacking, missing_pairs = Counter(), Counter(), Counter()
    for eid, event_type in types.items():
        have = mem.get(eid, set())
        more, less = tf.format_drift(have, event_type, blocks.get(eid, ()))
        if more or less:
            drift[eid] = (sorted(more), sorted(less))
            extra.update(more)
            lacking.update(less)
        need = tf.missing_topic_ancestors(have, event_type, parents, blocks.get(eid, ()))
        # Same fallback as process_tags/backfill: no topic root -> Other keyword.
        closed = have | need
        if ('Other' not in closed and 'Other' not in blocks.get(eid, ())
                and not any(db.normalize_tag_key(n) in state['roots'] for n in closed)):
            need = need | {'Other'}
        if need:
            missing[eid] = sorted(need)
            missing_pairs.update(need)
    blocked_present = sum(len(mem.get(e, set()) & b) for e, b in blocks.items() if e in types)
    shadows = tf.shadowing_aliases(state['aliases'], state['curated'])
    into_format = sorted({(p, c) for p, c in state['edges'] if p in tf.FORMAT_EXCLUSIVE
                          and c not in tf.FORMAT_FAMILY})
    virtual_kids = {c for c in mem_names(state) if DELIVERY_ROOT in tf.ancestors(c, parents)}
    under_blocked_virtual = sorted(e for e in types if DELIVERY_ROOT in blocks.get(e, ())
                                   and mem.get(e, set()) & virtual_kids)
    # Family held beside an eligibility tag with no family-intent descendant
    # (Kids, Storytime, ...): eligibility, not intent, is what supports it.
    family_intent = {c for c in mem_names(state) if 'Family' in tf.ancestors(c, parents)} - set(ELIGIBILITY)
    eligibility_only = sorted(e for e in types if 'Family' in mem.get(e, set())
                              and mem[e] & set(ELIGIBILITY) and not mem[e] & family_intent)
    format_implied_shared = Counter(t for e, t in types.items() if t in tf.SHARED_LEAVES and t in mem.get(e, set()))
    findings = {
        'format_drift_events': len(drift),
        'missing_topic_ancestor_rows': sum(map(len, missing.values())),
        'event_tags_on_venue_scope': state['event_wrong_scope'],
        'location_tags_on_event_scope': state['location_wrong_scope'],
        'blocked_pairs_present': blocked_present,
        'aliases_rewriting_topic_into_format': [list(s[:3]) for s in shadows if s[3]],
    }
    info = {
        'active_events': len(types),
        'format_extra': extra.most_common(), 'format_missing': lacking.most_common(),
        'missing_topic_ancestors': missing_pairs.most_common(),
        'aliases_shadowing_other_curated': [list(s[:3]) for s in shadows if not s[3]],
        'topic_edges_into_format_ignored_by_derivation': [list(e) for e in into_format],
        'delivery_tags_under_blocked_virtual': under_blocked_virtual,
        'family_only_via_eligibility': {'count': len(eligibility_only), 'events': eligibility_only[:200]},
        'format_implied_shared_leaf_members': dict(format_implied_shared),
    }
    return findings, info, drift, missing


def mem_names(state):
    names = set()
    for v in state['mem'].values():
        names |= v
    return names


def failing(findings):
    return any(v for v in findings.values())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--backup', type=Path)
    args = ap.parse_args()
    if args.output.exists() or (args.apply and (not args.backup or args.backup.exists())):
        raise SystemExit('Use new --output (and, with --apply, a new --backup) paths')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    conn = db.create_connection()
    cur = conn.cursor()
    try:
        if not args.apply:
            findings, info, drift, missing = check(load(cur))
            report = dict(findings=findings, info=info)
        else:
            with write_lock(conn, timeout=120, label='audit_tag_facets'):
                state = load(cur)
                findings, info, drift, missing = check(state)
                touched = sorted(set(drift) | set(missing))
                args.backup.parent.mkdir(parents=True, exist_ok=True)
                args.backup.write_text(json.dumps({str(e): sorted(state['mem'].get(e, ())) for e in touched}))
                for eid in drift:
                    db.sync_event_format_tags(cur, eid)
                for eid, names in missing.items():
                    db.upsert_event_tags(cur, eid, names)
                after, info, _, _ = check(load(cur))
                if after['format_drift_events'] or after['missing_topic_ancestor_rows']:
                    conn.rollback()
                    raise SystemExit(f'Did not converge; rolled back: {after}')
                conn.commit()
                report = dict(before=findings, findings=after, info=info, repaired_events=len(touched))
                findings = after
    finally:
        conn.close()
    args.output.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print(json.dumps(report['findings'], indent=1, ensure_ascii=False))
    print(f"info: {report['info']['active_events']} active events; "
          f"family-only-via-eligibility {report['info']['family_only_via_eligibility']['count']}; "
          f"delivery tags under blocked Virtual {len(report['info']['delivery_tags_under_blocked_virtual'])}; "
          f"other shadowing aliases {len(report['info']['aliases_shadowing_other_curated'])}")
    sys.exit(1 if failing(findings) else 0)


if __name__ == '__main__':
    main()
