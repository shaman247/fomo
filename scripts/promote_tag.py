#!/usr/bin/env python3
"""Preview/promote an existing keyword with validated same-scope parents.

Example: --scope event --name Example --parent Art --emoji 🎨 [--apply]
The default preview runs the exact transaction and rolls it back.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from db import create_connection
from dblock import write_lock
from tag_hierarchy_policy import promote_tag


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--scope', choices=['event', 'venue'], required=True)
    ap.add_argument('--name', required=True)
    ap.add_argument('--parent', action='append', default=[])
    ap.add_argument('--emoji', required=True)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    conn = create_connection()
    if conn is None:
        raise SystemExit('Database unavailable')
    try:
        with write_lock(conn, timeout=45, label='promote_tag'):
            try:
                tag_id = promote_tag(conn.cursor(), args.name, args.scope, args.parent, args.emoji)
                if args.apply:
                    conn.commit()
                else:
                    conn.rollback()
                print(f'{"Applied" if args.apply else "Valid preview (rolled back)"}: '
                      f'{args.scope}:{args.name} [{tag_id}] → {args.parent}')
            except Exception:
                conn.rollback()
                raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
