"""
Export scoring results to JSON for the scoring viewer.

Exports the most recent (or specified) scoring run from event_scores to
dist/admin/scores.json, which is loaded by dist/admin/scores.html.

Usage:
    ./venv/bin/python pipeline/export_scores.py                      # most recent run
    ./venv/bin/python pipeline/export_scores.py --run-id 20260218-v4
    ./venv/bin/python pipeline/export_scores.py --out /path/to/output.json
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal

import db


def get_latest_run_id(cursor) -> str | None:
    cursor.execute("""
        SELECT scorer_run_id
        FROM event_scores
        ORDER BY scored_at DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    return row[0] if row else None


def export_run(cursor, run_id: str) -> dict:
    """Fetch all scored events for a run and return as a dict."""
    cursor.execute("""
        SELECT
            e.id, e.name, e.emoji, e.description,
            l.name AS location_name,
            w.name AS website_name, w.base_url,
            es.scorer_run_id, es.scored_at, es.scorer_model,
            es.specificity, es.novelty, es.openness, es.prominence,
            es.connection, es.substance,
            es.specificity_reason, es.novelty_reason, es.openness_reason,
            es.prominence_reason, es.connection_reason, es.substance_reason,
            es.composite_score,
            GROUP_CONCAT(DISTINCT t.name ORDER BY t.name SEPARATOR ', ') AS tags,
            MIN(eo.start_date) AS first_date,
            MAX(eo.start_date) AS last_date,
            COUNT(DISTINCT eo.id) AS occurrence_count
        FROM event_scores es
        JOIN events e ON es.event_id = e.id
        LEFT JOIN locations l ON e.location_id = l.id
        LEFT JOIN websites w ON e.website_id = w.id
        LEFT JOIN event_tags et ON e.id = et.event_id
        LEFT JOIN tags t ON et.tag_id = t.id
        LEFT JOIN event_occurrences eo ON e.id = eo.event_id
        WHERE es.scorer_run_id = %s
        GROUP BY es.id
        ORDER BY es.composite_score DESC
    """, (run_id,))

    rows = cursor.fetchall()
    if not rows:
        return {}

    def to_float(v):
        if isinstance(v, Decimal):
            return float(v)
        return v

    def to_str(v):
        if isinstance(v, (date, datetime)):
            return str(v)
        return v

    events = []
    scored_at = None
    model = None

    for row in rows:
        (event_id, name, emoji, description,
         location_name, website_name, base_url,
         run_id_col, row_scored_at, scorer_model,
         specificity, novelty, openness, prominence, connection, substance,
         specificity_reason, novelty_reason, openness_reason,
         prominence_reason, connection_reason, substance_reason,
         composite_score, tags,
         first_date, last_date, occurrence_count) = row

        if scored_at is None:
            scored_at = str(row_scored_at)
        if model is None:
            model = scorer_model

        events.append({
            "id": event_id,
            "name": name or "",
            "emoji": emoji or "",
            "description": description or "",
            "location": location_name or "",
            "website": website_name or "",
            "website_url": base_url or "",
            "tags": tags or "",
            "first_date": to_str(first_date),
            "last_date": to_str(last_date),
            "occurrence_count": occurrence_count or 0,
            "scores": {
                "specificity": to_float(specificity),
                "novelty":     to_float(novelty),
                "openness":    to_float(openness),
                "prominence":  to_float(prominence),
                "connection":  to_float(connection),
                "substance":   to_float(substance),
            },
            "reasons": {
                "specificity": specificity_reason or "",
                "novelty":     novelty_reason or "",
                "openness":    openness_reason or "",
                "prominence":  prominence_reason or "",
                "connection":  connection_reason or "",
                "substance":   substance_reason or "",
            },
            "composite_score": to_float(composite_score),
        })

    return {
        "run_id": run_id,
        "scored_at": scored_at,
        "model": model,
        "event_count": len(events),
        "events": events,
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description='Export scoring run to JSON for the scoring viewer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pipeline/export_scores.py                        # most recent run
  python pipeline/export_scores.py --run-id 20260218-v4  # specific run
  python pipeline/export_scores.py --out /tmp/scores.json
        """
    )
    parser.add_argument('--run-id', type=str, default=None,
                        help='Scoring run ID to export (default: most recent)')
    parser.add_argument('--out', type=str, default=None,
                        help='Output path (default: dist/admin/scores.json)')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    conn = db.create_connection()
    if not conn:
        print("Failed to connect to database")
        sys.exit(1)

    cursor = conn.cursor(buffered=True)

    try:
        run_id = args.run_id
        if run_id is None:
            run_id = get_latest_run_id(cursor)
            if run_id is None:
                print("No scoring runs found in event_scores.")
                sys.exit(1)
            print(f"Using most recent run: {run_id}")

        print(f"Exporting run '{run_id}'...")
        data = export_run(cursor, run_id)

        if not data:
            print(f"No scores found for run '{run_id}'.")
            sys.exit(1)

        out_path = args.out or os.path.join(
            os.path.dirname(__file__), '..', 'dist', 'admin', 'scores.json'
        )
        out_path = os.path.normpath(out_path)

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"Exported {data['event_count']} events to {out_path}")

    finally:
        cursor.close()
        conn.close()
