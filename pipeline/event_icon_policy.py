"""Continuity of reviewed icon choices under explicitly redundant tag additions.

The original review fingerprints remain immutable. These predicates never infer
an activity, accept a proposal, or clear a deferred/merged review flag.
"""
import hashlib
import json
import re

from event_icons import input_hash, normalize

IMPLIED_TAGS = '_implied_tag_additions'
POLICY_VERSION = 1
MERGE_CONFLICT_REASON = 'Conflicting agent icon decisions after event merge.'
# Re-extractions reword the same page on every merge; measured on 2026-10-13
# re-reviews, rewrites at or above this word overlap changed the icon at the
# reviewer's own noise rate (~1%). See .claude/notes/icon-review-requeue-20261013.md.
SIMILAR_DESCRIPTION = 0.6
# Price, eligibility and occasion facets never choose an activity icon.
ICON_NEUTRAL_TAGS = frozenset({'Free', 'Age', '18+', '21+', 'All Ages', 'Young Adults', 'Occasion'})
_SCHEDULE_LINE = re.compile(r'^\s*20\d\d-\d\d-\d\d\b.*$', re.M)
_STOP_WORDS = frozenset('the and for with from are this that its your you our will join all more'.split())
_tag_view = None


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


def load_tag_view(cursor):
    """Cache the hierarchy facts icon_tags needs; callers without it compare exactly."""
    global _tag_view
    from db import build_tag_ancestor_map
    ancestors, roots = build_tag_ancestor_map(cursor)
    cursor.execute("SELECT name, type, emoji FROM tags WHERE scope='event'")
    rows = cursor.fetchall()
    _tag_view = dict(ancestors=ancestors, roots=roots,
                     curated={name for name, kind, _ in rows if kind == 'tag'},
                     places={name for name, _, emoji in rows if emoji == '\U0001f4cd'})
    return _tag_view


def icon_tags(tags, event_type=None):
    """Curated, non-derived activity tags; None when no tag view is loaded.

    Keywords are search-only extractor output and re-vote on every merge.
    Format nodes, and a shared leaf naming the event's own type, mirror
    event_type, which is compared on its own (BL23 dropped Workshop/Reading
    from 3,120 such events in one pass); ancestors are implied by a held tag;
    places and price/eligibility facets name no activity.
    """
    if _tag_view is None:
        return None
    from db import normalize_tag_key
    from tag_facets import FORMAT_EXCLUSIVE
    view, tags = _tag_view, set(tags)
    implied = set().union(*(view['ancestors'].get(normalize_tag_key(t), ()) for t in tags))
    return sorted(t for t in tags if t in view['curated'] and t not in implied
                  and t not in FORMAT_EXCLUSIVE and t != event_type and t not in ICON_NEUTRAL_TAGS
                  and t not in view['places'] and normalize_tag_key(t) not in view['roots'])


def _words(text):
    text = normalize(_SCHEDULE_LINE.sub('', text or '')) or ''
    return {w for w in re.findall(r"[a-z0-9']+", text.casefold()) if len(w) > 2 and w not in _STOP_WORDS}


def similar_description(old, new):
    """Same words once rendered session lines are dropped, or a close rewording."""
    before, after = _words(old), _words(new)
    if before == after:
        return True
    return bool(before and after) and len(before & after) / len(before | after) >= SIMILAR_DESCRIPTION


def semantic_matches(event, row):
    """The reviewed icon question is unchanged even though the stored text moved.

    Same title, emoji and Format, a similar description and the same curated
    activity tags. Location, room, URLs, source and keyword churn cannot change
    which activity the event is. Never applies without a valid saved baseline.
    """
    if row.get('origin') not in ('manual', 'agent'):
        return False
    policy = _baseline(row)
    if not policy:
        return False
    baseline = policy['context']
    if normalize(event.get('name')) != normalize(baseline.get('name')):
        return False
    if any(event.get(k) != baseline.get(k) for k in ('emoji', 'event_type')):
        return False
    if not similar_description(baseline.get('description'), event.get('description')):
        return False
    before = icon_tags(baseline['tags'], baseline.get('event_type'))
    return before is not None and before == icon_tags(event.get('tags', []), event.get('event_type'))


def review_hold(row):
    """A pending flag that no content comparison clears: an agent defer, a merge
    (held until re-reviewed with the survivor's context), or a row without a
    valid baseline (rule and legacy rows)."""
    if not row or not row['review_required']:
        return False
    info = metadata(row)
    return (row.get('origin') not in ('manual', 'agent') or _baseline(row) is None
            or info.get('decision') == 'defer' or bool(info.get('review_hold'))
            or (row['icon_id'] is None and row.get('reason') == MERGE_CONFLICT_REASON))


def input_matches(event, row):
    if row['input_hash'] == input_hash(event) or semantic_matches(event, row):
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
    if info.get('context_hash') == context_hash(event) or semantic_matches(event, row):
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
