"""Prepare a reproducible human-review sample; never classify or write to the DB.

Input is an event array or event_icon_report.py's report.json. Output is a new
directory containing population counts and a review worksheet in JSON.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re


def prepare(events, sample_size=300, seed=0, focus=None, focus_size=75):
    if sample_size < 0 or focus_size < 0:
        raise ValueError('Sample sizes must be nonnegative')
    if any(not isinstance(e.get('id'), int) for e in events):
        raise ValueError('Each event must have an integer id')
    if len({e['id'] for e in events}) != len(events):
        raise ValueError('Input must contain one row per event, not per occurrence')
    ordered = sorted(events, key=lambda e: e['id'])
    random_rows = random.Random(seed).sample(ordered, min(sample_size, len(ordered)))
    selected = {e['id'] for e in random_rows}
    pattern = re.compile(focus, re.IGNORECASE) if focus else None
    focused = [e for e in ordered if pattern and pattern.search(' '.join([
        e.get('name') or '', e.get('description') or '',
        ' '.join(e.get('tags') or []),
    ]))]
    supplement = random.Random(seed + 1).sample(
        [e for e in focused if e['id'] not in selected],
        min(focus_size, sum(e['id'] not in selected for e in focused)))

    def counts(values):
        return dict(sorted(Counter(values).items(), key=lambda pair: (-pair[1], pair[0])))

    summary = {
        'total_events': len(ordered), 'seed': seed,
        'requested_random_size': sample_size, 'random_size': len(random_rows),
        'focus_pattern': focus, 'focus_matches_population': len(focused),
        'requested_supplement_size': focus_size, 'supplement_size': len(supplement),
        # Python equality preserves exact Unicode sequences, unlike DB collations.
        'emoji': counts(e.get('emoji') or '' for e in ordered),
        'event_types': counts(e.get('event_type') or '' for e in ordered),
        'tags': counts(tag for e in ordered for tag in set(e.get('tags') or [])),
    }
    reviews = []
    for cohort, rows in [('random', random_rows), ('targeted', supplement)]:
        for event in rows:
            reviews.append({
                'cohort': cohort, 'event': event,
                'review': {'fit': None, 'route': None, 'best_icon': None,
                           'evidence': None, 'uncertainty': None},
            })
    return summary, reviews


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--sample-size', type=int, default=300)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--focus', help='Optional regex over title, description and tags')
    parser.add_argument('--focus-size', type=int, default=75)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    data = json.loads(raw)
    if isinstance(data, dict):
        events = [row['event'] for row in data['rows']]
        source_summary = data.get('summary')
    else:
        events, source_summary = data, None
    summary, reviews = prepare(events, args.sample_size, args.seed, args.focus, args.focus_size)
    summary.update(input=str(args.input), input_sha256=hashlib.sha256(raw).hexdigest(),
                   source_summary=source_summary)
    # Never overwrite an existing human review or its provenance.
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (args.output / 'review.json').write_text(json.dumps(reviews, ensure_ascii=False, indent=2))
    print(json.dumps({k: summary[k] for k in (
        'total_events', 'random_size', 'supplement_size', 'input_sha256')}, indent=2))


if __name__ == '__main__':
    main()
