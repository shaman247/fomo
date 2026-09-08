"""Prepare full-context icon reviews and apply agent decisions; never call a model.

prepare --output DIR writes an incremental queue in complete, bounded batches.
apply --packet FILE --decisions FILE validates a complete batch (dry run by
default). --apply --backup FILE writes under the shared lock; --init-schema
allows the idempotent agent-origin migration. opportunities --output DIR builds
a read-only discovery backlog from saved reviews. No command publishes site data.
"""
import argparse
from collections import Counter
from contextlib import nullcontext
from datetime import date
import hashlib
import json
from pathlib import Path
import re

from event_icons import ROOT, CATALOG, ICON_IDS, input_hash, propose
from event_icon_assignments import (fetch_events, load_assignments, manual_assignment,
                                    retained_assignment, require_lock, save)

OPPORTUNITY_REVIEW_VERSION = 1
OPPORTUNITY_CATEGORIES = {'instrument', 'genre', 'dance-style', 'cuisine', 'craft',
                         'sport', 'activity', 'equipment', 'format', 'other'}


def validate_opportunities(value):
    if not isinstance(value, list):
        raise ValueError('opportunities must be a list; use [] only after considering icon gaps')
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError('Each opportunity must be an object')
        concept = item.get('concept')
        if not isinstance(concept, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', concept):
            raise ValueError('Opportunity concept must be a lowercase semantic slug')
        if concept in seen:
            raise ValueError('Duplicate opportunity concept for one event')
        seen.add(concept)
        if item.get('category') not in OPPORTUNITY_CATEGORIES:
            raise ValueError('Unknown opportunity category')
        for key in ('label', 'visual', 'rationale', 'existing_alternative'):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f'Opportunity {key} is required')
        evidence = item.get('evidence')
        if not isinstance(evidence, list) or not evidence or any(not isinstance(e, str) or not e.strip() for e in evidence):
            raise ValueError('Opportunity evidence must contain nonempty text')
    return value


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), default=str).encode()).hexdigest()


def catalog_revision():
    # Artwork-only edits do not require reassignment. Meaning and new IDs do.
    return fingerprint(sorted([{key: icon.get(key) for key in
        ('id', 'label', 'fallback_emoji', 'use_for', 'avoid_for')}
        for icon in CATALOG['icons']], key=lambda i: i['id']))


def metadata(row):
    try:
        data = json.loads(row['evidence_json']) if isinstance(row['evidence_json'], str) else row['evidence_json']
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError, KeyError):
        return {}


def context_hash(event):
    # Stable across fetch order; the ID itself is not semantic context.
    values = {k: v for k, v in event.items() if k != 'id'}
    for key in ('tags', 'urls'):
        values[key] = sorted(values.get(key, []))
    return fingerprint(values)


def review_reason(event, row, revision):
    if not row:
        return 'unreviewed'
    if row['review_required'] or row['input_hash'] != input_hash(event):
        return 'changed-or-deferred'
    if row['icon_id'] is not None and row['icon_id'] not in ICON_IDS:
        return 'unknown-icon'
    info = metadata(row)
    if row['origin'] == 'manual':
        # Discovery can still inspect the event; validation protects its choice.
        return None if info.get('opportunity_review_version') == OPPORTUNITY_REVIEW_VERSION else 'icon-opportunities'
    if row['origin'] != 'agent':
        return 'legacy-rule'
    if info.get('context_hash') != context_hash(event):
        return 'changed-context'
    if info.get('catalog_revision') != revision:
        return 'changed-catalog'
    if info.get('opportunity_review_version') != OPPORTUNITY_REVIEW_VERSION:
        return 'icon-opportunities'
    return None


def fetch_review_events(cursor, event_date=None):
    events = fetch_events(cursor)  # Full publishable population, no keyword gate.
    if event_date is not None:
        cursor.execute('''SELECT DISTINCT event_id FROM event_occurrences
            WHERE start_date <= %s AND COALESCE(end_date,start_date) >= %s''', (event_date,event_date))
        today_ids = {r[0] for r in cursor.fetchall()}
        events = [e for e in events if e['id'] in today_ids]
    lookup = {e['id']: e for e in events}
    ids = list(lookup)
    for offset in range(0, len(ids), 1000):
        chunk = ids[offset:offset+1000]
        slots = ','.join(['%s'] * len(chunk))
        cursor.execute(f'''SELECT e.id,e.short_name,e.emoji,e.event_type,
            e.location_name,e.sublocation,l.name,l.address,w.name
            FROM events e LEFT JOIN locations l ON l.id=e.location_id
            LEFT JOIN websites w ON w.id=e.website_id WHERE e.id IN ({slots})''', tuple(chunk))
        for eid, short_name, emoji, event_type, location_name, sublocation, venue, address, source in cursor.fetchall():
            lookup[eid].update(short_name=short_name, emoji=emoji, event_type=event_type,
                location_name=location_name, sublocation=sublocation, venue=venue,
                address=address, source=source, urls=[])
        cursor.execute(f'SELECT event_id,url FROM event_urls WHERE event_id IN ({slots}) ORDER BY event_id,url', tuple(chunk))
        for eid, url in cursor.fetchall():
            lookup[eid]['urls'].append(url)
    return events


def refresh_review_state(cursor, apply=False):
    """Invalidate changed saved choices without accepting heuristic proposals."""
    if apply:
        require_lock(cursor)
    rows = load_assignments(cursor)
    revision = catalog_revision()
    stats = Counter()
    for event in fetch_review_events(cursor):
        old = rows.get(event['id'])
        new = retained_assignment(event, old)
        reason = review_reason(event, old, revision)
        if reason:
            stats['pending'] += 1
        if new and old['origin'] == 'agent' and reason == 'changed-context':
            new['review_required'] = 1
        if new != old:
            stats['invalidated'] += 1
            if apply:
                save(cursor, new)
    return dict(stats)


def make_packets(events, rows, batch_size=100):
    if batch_size < 1:
        raise ValueError('Batch size must be positive')
    revision = catalog_revision()
    pending, reasons = [], Counter()
    for event in sorted(events, key=lambda e: e['id']):
        old = rows.get(event['id'])
        reason = review_reason(event, old, revision)
        if not reason:
            continue
        reasons[reason] += 1
        pending.append(dict(event=event, input_hash=input_hash(event), context_hash=context_hash(event),
            previous_assignment=old, review_reason=reason, heuristic_proposal=propose(event)))
    return [dict(schema_version=1, catalog_revision=revision, icons=CATALOG['icons'],
                 opportunity_review=dict(version=OPPORTUNITY_REVIEW_VERSION,
                     instruction='For every event, also consider more specific future icons: instruments, genres, '
                     'styles, techniques, equipment and formats. Record grounded visual concepts even if the '
                     'current assignment is acceptable. Include opportunities: [] when no useful gap is found.'),
                 events=pending[i:i+batch_size]) for i in range(0, len(pending), batch_size)], dict(reasons)


def validate_decisions(packet, decisions, current_events, current_rows):
    revision = catalog_revision()
    if packet.get('schema_version') != 1 or packet.get('catalog_revision') != revision:
        raise ValueError('Packet catalog changed; prepare a fresh review')
    if packet.get('icons') != CATALOG['icons']:
        raise ValueError('Packet catalog contents do not match')
    if decisions.get('catalog_revision') != revision:
        raise ValueError('Decision catalog revision does not match')
    expected = {r['event']['id']: r for r in packet['events']}
    if len(expected) != len(packet['events']):
        raise ValueError('Duplicate packet event IDs')
    by_id = {}
    for choice in decisions['decisions']:
        eid = choice['event_id']
        if type(eid) is not int or eid in by_id:
            raise ValueError('Invalid or duplicate decision event ID')
        by_id[eid] = choice
    if by_id.keys() != expected.keys():
        raise ValueError('Decisions must cover exactly every event in this packet')
    result = []
    for eid, entry in expected.items():
        choice = by_id[eid]
        event = current_events.get(eid)
        if event is None:
            raise ValueError(f'{eid}: event is no longer publishable')
        if (entry['context_hash'] != context_hash(event) or
                entry['context_hash'] != context_hash(entry['event']) or
                entry['input_hash'] != input_hash(event)):
            raise ValueError(f'{eid}: event changed since review; prepare a fresh packet')
        if choice.get('input_hash') != entry['input_hash']:
            raise ValueError(f'{eid}: decision input hash does not match')
        action, icon = choice.get('decision'), choice.get('icon_id')
        if action not in ('assign', 'fallback', 'defer'):
            raise ValueError(f'{eid}: expected assign, fallback, or defer')
        if (action == 'assign' and icon not in ICON_IDS) or (action != 'assign' and icon is not None):
            raise ValueError(f'{eid}: invalid icon for decision')
        reason, evidence = choice.get('reason'), choice.get('evidence')
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f'{eid}: a reason is required')
        if not isinstance(evidence, list) or not evidence or any(not isinstance(e, str) or not e.strip() for e in evidence):
            raise ValueError(f'{eid}: nonempty text evidence is required')
        opportunities = validate_opportunities(choice.get('opportunities'))
        old = current_rows.get(eid)
        # Agent can revalidate the same stale human choice, but cannot replace it.
        if old and old['origin'] == 'manual' and icon != old['icon_id'] and action != 'defer':
            raise ValueError(f'{eid}: would replace a protected manual decision')
        row = manual_assignment(event, icon, reason)
        row.update(origin='agent', review_required=int(action == 'defer'), evidence_json=json.dumps(dict(
            reviewer='run-pipeline-agent', catalog_revision=revision, context_hash=context_hash(event),
            decision=action, evidence=evidence, opportunities=opportunities,
            opportunity_review_version=OPPORTUNITY_REVIEW_VERSION), ensure_ascii=False, sort_keys=True))
        if old and old['origin'] == 'manual':
            row['origin'] = 'manual'
            if action == 'defer':
                row.update(icon_id=old['icon_id'], input_hash=old['input_hash'])
        if old != entry['previous_assignment'] and old != row:
            raise ValueError(f'{eid}: assignment changed concurrently; prepare a fresh packet')
        result.append(row)
    return result


def collect_opportunities(events, rows):
    """Aggregate saved, current evidence once per event/concept, never per occurrence."""
    concepts = {}
    reviewed, stale = 0, 0
    for event in sorted(events, key=lambda e: e['id']):
        row = rows.get(event['id'])
        if not row:
            continue
        info = metadata(row)
        if info.get('opportunity_review_version') != OPPORTUNITY_REVIEW_VERSION:
            continue
        if row['review_required'] or row['input_hash'] != input_hash(event) or info.get('context_hash') != context_hash(event):
            stale += 1
            continue
        reviewed += 1
        for suggestion in validate_opportunities(info.get('opportunities')):
            key = suggestion['concept']
            group = concepts.setdefault(key, dict(concept=key, event_ids=[], venues=set(),
                categories=set(), labels=set(), variants={}, tags=Counter(), examples=[]))
            group['event_ids'].append(event['id'])
            if event.get('venue'):
                group['venues'].add((event['venue'], event.get('address') or ''))
            group['categories'].add(suggestion['category'])
            group['labels'].add(suggestion['label'])
            group['tags'].update(set(event.get('tags', [])))
            variant = {k: suggestion[k] for k in ('visual','rationale','existing_alternative')}
            group['variants'][fingerprint(variant)] = variant
            group['examples'].append(dict(event_id=event['id'], name=event['name'],
                emoji=event.get('emoji'), current_icon_id=row['icon_id'], venue=event.get('venue'),
                urls=event.get('urls', []), evidence=suggestion['evidence']))
    output = []
    for group in concepts.values():
        group['event_count'] = len(group['event_ids'])
        group['venue_count'] = len(group['venues'])
        group['venues'] = [dict(name=name, address=address) for name,address in sorted(group['venues'])]
        for field in ('labels', 'categories'):
            group[field] = sorted(group[field])
        group['variants'] = list(group['variants'].values())
        group['tags'] = dict(group['tags'].most_common())
        group['catalog_id_exists'] = group['concept'] in ICON_IDS
        output.append(group)
    output.sort(key=lambda g: (-g['event_count'], g['concept']))
    return dict(population=len(events), reviewed_events=reviewed, stale_reviews_excluded=stale,
                concepts=output, concept_count=len(output))


def opportunity_markdown(report):
    lines = ['# Icon opportunities', '',
        f"Reviewed events: {report['reviewed_events']} / {report['population']}. "
        f"Stale/deferred reviews excluded: {report['stale_reviews_excluded']}.", '',
        'Counts are unique event records, not occurrences. Frequency order is not a quality ranking. '
        'Consolidate equivalent concept keys editorially; all evidence and variants are in opportunities.json.', '']
    for group in report['concepts']:
        lines.extend([f"## {group['concept']}", '',
            f"{group['event_count']} events · {group['venue_count']} venues · {', '.join(group['categories'])}", ''])
        for variant in group['variants']:
            lines.extend([f"- Visual: {variant['visual']}", f"- Benefit: {variant['rationale']}",
                          f"- Existing alternative: {variant['existing_alternative']}"])
        lines.extend(['', 'Example events: ' + '; '.join(f"{e['event_id']} — {e['name']}" for e in group['examples'][:5]), ''])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    prepare = modes.add_parser('prepare')
    prepare.add_argument('--output', type=Path, required=True)
    prepare.add_argument('--batch-size', type=int, default=100)
    prepare.add_argument('--date', type=date.fromisoformat, help='Only events occurring on this date (YYYY-MM-DD)')
    opportunities = modes.add_parser('opportunities', help='Read-only backlog from saved agent reviews')
    opportunities.add_argument('--output', type=Path, required=True)
    opportunities.add_argument('--date', type=date.fromisoformat, help='Scope opportunity coverage to this date')
    apply = modes.add_parser('apply')
    apply.add_argument('--packet', type=Path, required=True)
    apply.add_argument('--decisions', type=Path, required=True)
    apply.add_argument('--apply', action='store_true')
    apply.add_argument('--init-schema', action='store_true')
    apply.add_argument('--backup', type=Path)
    args = parser.parse_args()
    writing = args.mode == 'apply' and args.apply
    if args.mode == 'apply' and ((args.init_schema and not writing) or (writing and not args.backup)):
        parser.error('--init-schema requires --apply; writes require a unique --backup file')
    from db import create_connection
    from dblock import write_lock
    conn = create_connection()
    if conn is None:
        raise RuntimeError('Database unavailable')
    try:
        with write_lock(conn, label='agent_icon_review') if writing else nullcontext():
            cursor = conn.cursor()
            if not writing:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                cursor.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
            events, rows = fetch_review_events(cursor, getattr(args,'date',None)), load_assignments(cursor)
            if args.mode == 'opportunities':
                report = collect_opportunities(events, rows)
                report['event_date'] = str(args.date) if args.date else None
                args.output.mkdir(parents=True, exist_ok=False)
                (args.output / 'opportunities.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
                (args.output / 'opportunities.md').write_text(opportunity_markdown(report))
                summary = {k:v for k,v in report.items() if k != 'concepts'}
            elif args.mode == 'prepare':
                packets, reasons = make_packets(events, rows, args.batch_size)
                args.output.mkdir(parents=True, exist_ok=False)
                for i, packet in enumerate(packets):
                    (args.output / f'batch-{i:04d}.json').write_text(json.dumps(packet, ensure_ascii=False, indent=2))
                summary = dict(population=len(events), pending=sum(reasons.values()), reasons=reasons,
                               batches=len(packets), catalog_revision=catalog_revision(),
                               event_date=str(args.date) if args.date else None)
                (args.output / 'manifest.json').write_text(json.dumps(summary, indent=2))
            else:
                packet, decisions = json.loads(args.packet.read_text()), json.loads(args.decisions.read_text())
                planned = validate_decisions(packet, decisions, {e['id']: e for e in events}, rows)
                changes = [r for r in planned if r != rows.get(r['event_id'])]
                summary = dict(applied=writing, reviewed=len(planned), changes=len(changes),
                               assigned=sum(r['icon_id'] is not None and not r['review_required'] for r in planned),
                               fallback=sum(r['icon_id'] is None and not r['review_required'] for r in planned),
                               deferred=sum(bool(r['review_required']) for r in planned),
                               opportunities=sum(len(metadata(r)['opportunities']) for r in planned))
                if writing:
                    args.backup.parent.mkdir(parents=True, exist_ok=True)
                    with args.backup.open('x') as backup:
                        json.dump({r['event_id']: rows.get(r['event_id']) for r in planned}, backup, ensure_ascii=False, indent=2)
                    if args.init_schema:
                        cursor.execute("SHOW COLUMNS FROM event_icon_assignments LIKE 'origin'")
                        if "'agent'" not in cursor.fetchone()[1]:
                            cursor.execute((ROOT/'database/migrations/20260908_agent_event_icons.sql').read_text())
                    require_lock(cursor)
                    for row in changes:
                        save(cursor, row)
                    conn.commit()
            print(json.dumps(summary, indent=2))
    finally:
        conn.rollback()
        conn.close()


if __name__ == '__main__':
    main()
