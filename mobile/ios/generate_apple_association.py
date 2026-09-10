#!/usr/bin/env python3
"""Generate the site association after the owner supplies their Apple Team ID.

This only writes a local artifact; it never uploads or changes signing settings.
"""
import argparse
import json
import re
from pathlib import Path


def association(team_id, bundle_id):
    if not re.fullmatch(r'[A-Z0-9]{10}', team_id):
        raise ValueError('Apple Team ID must contain ten uppercase letters/digits')
    if not re.fullmatch(r'[A-Za-z0-9.-]+', bundle_id):
        raise ValueError('Invalid bundle ID')
    return {'applinks': {'details': [{'appIDs': [f'{team_id}.{bundle_id}'],
            'components': [{'/': '/', '?': {'qv': '1', 'q': '*'},
                            'comment': 'Open version 1 structured searches in the installed app.'}]}]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--team-id', required=True)
    parser.add_argument('--bundle-id', default='fomocity.fomo')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[2] / 'src/.well-known/apple-app-site-association')
    args = parser.parse_args()
    result = association(args.team_id, args.bundle_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'Wrote {args.output}; publish through the normal site release.')


if __name__ == '__main__':
    main()
