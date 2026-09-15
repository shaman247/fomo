"""Continuity of reviewed icon choices under explicitly redundant tag additions.

The original review fingerprints remain immutable. These predicates never infer
an activity, accept a proposal, or clear a deferred/merged review flag.
"""
import hashlib
import json

from event_icons import input_hash, normalize

IMPLIED_TAGS = '_implied_tag_additions'
POLICY_VERSION = 1


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), default=str).encode()).hexdigest()


def metadata(row):
    try:
        data = row['evidence_json']
        data = json.loads(data) if isinstance(data, str) else data
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError, KeyError):
        return {}


def context_values(event):
    values = {k: v for k, v in event.items() if k not in ('id', IMPLIED_TAGS)}
    for key in ('tags', 'urls'):
        values[key] = sorted(values.get(key, []))
    return values


def context_hash(event):
    return fingerprint(context_values(event))


def review_baseline(event, approved_additions=()):
    return dict(version=POLICY_VERSION, context=context_values(event),
                implied_tags=sorted(set(event.get(IMPLIED_TAGS, []))),
                approved_additions=list(approved_additions))


def _baseline(row):
    info = metadata(row)
    policy = info.get('tag_enrichment')
    if not isinstance(policy, dict) or policy.get('version') != POLICY_VERSION:
        return None
    baseline = policy.get('context')
    if (not isinstance(baseline, dict) or not isinstance(baseline.get('tags'), list)
            or any(baseline.get(k) is not None and not isinstance(baseline[k], str)
                   for k in ('name', 'description'))
            or any(not isinstance(t, str) for t in baseline['tags'])
            or not isinstance(baseline.get('urls', []), list)
            or any(not isinstance(u, str) for u in baseline.get('urls', []))):
        return None
    if (input_hash(baseline) != row['input_hash'] or
            context_hash(baseline) != info.get('context_hash')):
        return None
    return policy


def input_matches(event, row):
    if row['input_hash'] == input_hash(event):
        return True
    if row.get('origin') not in ('manual', 'agent'):
        return False
    policy = _baseline(row)
    if not policy:
        return False
    baseline = policy['context']
    if any(normalize(event.get(k)) != normalize(baseline.get(k))
           for k in ('name', 'description')):
        return False
    old, current = set(baseline['tags']), set(event.get('tags', []))
    if not old <= current:  # Removals and replacements always need review.
        return False
    implied, approved = policy.get('implied_tags'), policy.get('approved_additions')
    if (not isinstance(implied, list) or any(not isinstance(t, str) for t in implied)
            or not isinstance(approved, list) or any(
                not isinstance(a, dict) or not isinstance(a.get('tag'), str)
                or not a['tag'].strip() or a['tag'] != a['tag'].strip()
                or not isinstance(a.get('reason'), str) or not a['reason'].strip()
                or not isinstance(a.get('evidence'), list) or not a['evidence']
                or any(not isinstance(e, str) or not e.strip() for e in a['evidence'])
                for a in approved)):
        return False
    return current - old <= set(implied) | {a['tag'] for a in approved}


def context_matches(event, row):
    info = metadata(row)
    if info.get('context_hash') == context_hash(event):
        return True
    policy = _baseline(row)
    if not policy or not input_matches(event, row):
        return False
    current = context_values(event)
    current['tags'] = policy['context']['tags']
    return context_hash(current) == info['context_hash']


def seed_review_baseline(event, row):
    """Upgrade only an exactly current review; never bless a changed context."""
    info = dict(metadata(row))
    if (row['review_required'] or row['input_hash'] != input_hash(event)
            or info.get('context_hash') != context_hash(event)):
        return row
    if 'tag_enrichment' in info:
        return row
    info['tag_enrichment'] = review_baseline(event)
    return dict(row, evidence_json=json.dumps(info, ensure_ascii=False, sort_keys=True))
