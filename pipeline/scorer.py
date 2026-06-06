"""
Event scoring script.

Scores events on six dimensions using Gemini AI:
  - Specificity: How tied this event is to a non-interchangeable, purposeful occasion (1=generic/recurring, 5=singular occasion)
  - Novelty:     How original/unusual the concept is (1=generic, 5=one-of-a-kind)
  - Openness:    How accessible to the general public (1=restricted, 5=free/all welcome)
  - Prominence:  How big/high-profile (1=obscure, 5=city-wide/newsworthy)
  - Connection:  How participatory and human-scale (1=anonymous large crowd, 5=direct exchange is the point)
  - Substance:   Lasting impact / "I'm glad I went" (1=ephemeral, 5=expands perspective or produces real-world change)

Results are stored in the event_scores table for later analysis.

Usage:
    ./venv/bin/python pipeline/scorer.py               # Score 50 random events
    ./venv/bin/python pipeline/scorer.py --limit 100   # Score 100 events
    ./venv/bin/python pipeline/scorer.py --dry-run     # Score but don't store
    ./venv/bin/python pipeline/scorer.py --run-id 20260218-v2  # Custom run ID
    ./venv/bin/python pipeline/scorer.py --batch-size 5        # Smaller batches
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

import city_config
import db

load_dotenv()

try:
    from google import genai
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-preview-05-20")
    GEMINI_TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT", "120"))
    if GEMINI_API_KEY:
        genai_client = genai.Client(api_key=GEMINI_API_KEY)
    else:
        genai_client = None
except ImportError:
    print("Warning: google-genai not installed.")
    genai = None
    genai_client = None
    GEMINI_API_KEY = None
    GEMINI_MODEL = None
    GEMINI_TIMEOUT = 120


# =============================================================================
# Pydantic Schema for Structured Output
# =============================================================================

class EventScore(BaseModel):
    event_id: int = Field(description="The event ID being scored (from the EVENT ID field)")
    specificity: float = Field(ge=1, le=5, description="Specificity score 1-5 (integer or one decimal, e.g. 3.5)")
    specificity_reason: str = Field(description="One sentence justifying the specificity score")
    novelty: float = Field(ge=1, le=5, description="Novelty score 1-5 (integer or one decimal, e.g. 3.5)")
    novelty_reason: str = Field(description="One sentence justifying the novelty score")
    openness: float = Field(ge=1, le=5, description="Openness score 1-5 (integer or one decimal, e.g. 3.5)")
    openness_reason: str = Field(description="One sentence justifying the openness score")
    prominence: float = Field(ge=1, le=5, description="Prominence score 1-5 (integer or one decimal, e.g. 3.5)")
    prominence_reason: str = Field(description="One sentence justifying the prominence score")
    connection: float = Field(ge=1, le=5, description="Connection score 1-5 (integer or one decimal, e.g. 3.5)")
    connection_reason: str = Field(description="One sentence justifying the connection score")
    substance: float = Field(ge=1, le=5, description="Substance score 1-5 (integer or one decimal, e.g. 3.5)")
    substance_reason: str = Field(description="One sentence justifying the substance score")


class EventScoreBatch(BaseModel):
    scores: list[EventScore]


# =============================================================================
# Rubric and Prompt
# =============================================================================

RUBRIC = """
SCORING RUBRIC

SPECIFICITY — How tied is this event to a particular, non-interchangeable occasion?
  Ask: "Is this a singular, purposeful event, or just another instance of an ongoing program?"
  5 = A singular, purposeful occasion with an explicit reason for being — world premiere, farewell tour, anniversary tribute,
      once-in-a-lifetime collaboration. The event name/description makes clear this is not part of a routine series.
  4 = Has a distinct identity beyond routine programming — a one-time benefit concert, a closing night of a run,
      a special reunion of performers not regularly assembled, an explicitly named milestone event.
  3 = Part of an ongoing series with a clear identity, but this is a normal instance — a named artist residency,
      a branded monthly showcase, an annual recurring event that is clearly part of a series.
  2 = Generic recurring programming with interchangeable instances — "Tuesday jazz night," a weekly open showcase,
      a standard tour date for a working musician with no special occasion framing.
  1 = Completely interchangeable — open mics, drop-in yoga, bar trivia, weekly club nights, ongoing exhibitions
      where no specific date or performer has special significance.
  IMPORTANT: A standard tour stop by a well-known artist is NOT specificity:5. It is just a tour date (specificity:2).
  Only explicit occasion language in the name/description justifies 4-5: "farewell," "premiere," "tribute," "anniversary," etc.

NOVELTY — How original or unusual is the concept? (focus purely on originality — ignore frequency)
  5 = Completely one-of-a-kind — utterly unlike anything else on a typical event calendar
  4 = Distinctly original — a concept clearly above-average in creativity with some precedent
  3 = Creative spin on a familiar format — recognizable but with a distinctive, memorable angle
  2 = Familiar format with modest differentiation — you've seen things like this, with a slight twist
  1 = Generic, no differentiation — standard open mic, regular concert, typical panel, run-of-the-mill DJ night
  Hint: Focus on the event concept. A standard rock concert is novelty:1 even if it's a farewell show.

OPENNESS — How accessible is this event to the general public?
  5 = Free, fully open to all, broadly diverse audience expected — street fairs, free library programs, free outdoor concerts
  4 = Open to the public but with barriers — paid tickets, registration required, or primarily appeals to a particular demographic
  3 = Nominally public but significant implicit barrier — membership venue, requires specialized background knowledge, walk-ins unusual
  2 = Primarily for an established group; newcomers can attend but would be out of place — community board meetings, congregation programs
  1 = Restricted — invitation-only, requires affiliation or credential (alumni networking, private club, members-only)
  Hint: "Open to all" or "free" → lean toward 5. "Members" or "alumni" language → lean toward 1.

PROMINENCE — How big or high-profile is this event?
  5 = Large-scale, city-wide — expect press coverage, thousands of attendees (a major city-wide festival, a museum blockbuster, a flagship theater opening)
  4 = Medium-sized, established institution with real track record — recognized venue, well-known ensemble or performer
  3 = Small-to-medium, known local organization with a regular local audience — neighborhood venue, local arts org
  2 = Small event by a relatively unknown organizer — first-time organizer, small collective, new venue
  1 = Obscure, very small-scale, no institutional backing, no evident prior audience
  Hint: Venue and source website are strong signals. Prestigious major institutions → 5. Recognized niche venues → 3-4. Unknown one-off organizers → 1-2.

CONNECTION — How participatory and human-scale is this event?
  Ask: "Is direct human exchange the point, or are you anonymous in a crowd?"
  5 = Highly participatory — direct human exchange is the whole point: workshops, collaborative creation, Q&A with creator,
      community conversations where attendees contribute, civic action, volunteering where you take part alongside others
  4 = Intimate setting where human connection is naturally available — small venue performance where artist is accessible,
      participatory format, structured group activity with genuine peer interaction
  3 = Some human texture in a modest setting — small theater, panel with audience questions, neighborhood gathering
      where social interaction is possible but not structured
  2 = Standard passive consumption in social setting — medium venue concert, gallery opening, film screening
  1 = Anonymous, large-scale passive consumption — stadium concert, blockbuster film, massive festival crowd
  Hint: Workshops, civic participation, volunteering → 5. This signal tends to anti-correlate with Prominence.
  Novelty is irrelevant here — a routine block association cleanup scores connection:5.

SUBSTANCE — How lasting is the impact? Would you be glad you went, in retrospect?
  Ask: "Does this leave you with something you carry forward — a perspective, a skill, a real-world change?"
  5 = Likely to stay with you — expands how you see the world, produces real-world change, or connects to something
      meaningful beyond the event. Examples: workshop where you learn a lasting skill, civic action that changes something,
      lecture that reframes how you think about a topic, transformative performance you reflect on weeks later
  4 = Substantive and rewarding — you leave with something genuine: a new idea, emotional resonance that lingers,
      meaningful skill, or a sense of having contributed to something real
  3 = Engaging with some depth — worthwhile in the moment with some lasting impression, but impact fades within a week or two
  2 = Primarily in-the-moment — fun or entertaining but easily replaced by a similar event; gone from memory quickly
  1 = Ephemeral and interchangeable — forgettable entertainment with near-zero lasting impact
  IMPORTANT: Novelty ≠ Substance. A lookalike contest may be highly novel but scores substance:1 — it's a laugh and it's over.
  Civic participation and volunteering score HIGH on Substance even if they score low on Novelty.

{calibration_examples}

KEY: All six signals are INDEPENDENT.
  Specificity and Novelty are independent: a farewell concert can be specificity:5 and novelty:1.
  Connection and Prominence tend to anti-correlate: large prominent events are often low-connection.
  Novelty and Substance are independent: a lookalike contest can be novelty:5 and substance:1.
  Civic/community events (cleanups, block association meetings, volunteering) → connection:5, substance:4-5, but often novelty:1.
Use the FULL 1-5 scale. Do not cluster scores at 3. Give a specific one-sentence reason for each score.
Scores are normally integers (1, 2, 3, 4, 5). Use one decimal place ONLY when an event genuinely falls between two levels
(e.g., 3.5 if clearly above 3 but not quite 4). Do not use decimals for every score — reserve them for edge cases.
"""


def format_event_for_prompt(event: dict) -> str:
    """Format a single event as a compact text block for the scoring prompt."""
    lines = [
        f"EVENT ID: {event['id']}",
        f"  Name: {event['name']}",
        f"  Location: {event['location_name'] or '(unknown)'}",
        f"  Source website: {event['website_name'] or '(unknown)'}",
    ]
    if event.get('description'):
        # Truncate long descriptions
        desc = event['description']
        if len(desc) > 400:
            desc = desc[:400] + '...'
        lines.append(f"  Description: {desc}")
    if event.get('tags'):
        lines.append(f"  Tags: {event['tags']}")
    lines.append(f"  Section: {event.get('section', 'Events')}")
    lines.append(f"  Occurrences: {event['occurrence_count']} total")
    if event.get('first_occurrence') and event.get('last_occurrence'):
        if event['first_occurrence'] == event['last_occurrence']:
            lines.append(f"  Date: {event['first_occurrence']}")
        else:
            lines.append(f"  Date range: {event['first_occurrence']} to {event['last_occurrence']}")
    return '\n'.join(lines)


def build_scoring_prompt(events_batch: list[dict]) -> str:
    """Build the full Gemini prompt for a batch of events."""
    event_blocks = '\n\n'.join(format_event_for_prompt(e) for e in events_batch)
    rubric = RUBRIC.replace('{calibration_examples}', city_config.scoring_calibration_examples())
    return f"""{rubric}

Score the following {len(events_batch)} events. Return one score object per event, using the event_id from the EVENT ID field.

{event_blocks}"""


# =============================================================================
# Database Queries
# =============================================================================

def query_events(cursor, limit: int = 50, days_ahead: Optional[int] = None,
                 skip_run_id: Optional[str] = None) -> list[dict]:
    """Query events to score.

    - days_ahead: if set, restrict to events with at least one occurrence in
      [today, today + days_ahead days]. Returns all matches (no RAND/LIMIT).
    - skip_run_id: if set, exclude events already scored under that run ID.
    - limit: cap on random sample (ignored when days_ahead is set).
    """
    where_clauses = [
        "e.archived = FALSE",
        "e.suppressed = FALSE",
        "l.id IS NOT NULL",
        "l.lat IS NOT NULL",
    ]
    params = []

    if days_ahead is not None:
        where_clauses.append(
            "e.id IN (SELECT DISTINCT event_id FROM event_occurrences"
            " WHERE start_date BETWEEN CURDATE() AND CURDATE() + INTERVAL %s DAY)"
        )
        params.append(days_ahead)

    if skip_run_id:
        where_clauses.append(
            "e.id NOT IN (SELECT event_id FROM event_scores WHERE scorer_run_id = %s)"
        )
        params.append(skip_run_id)

    where_sql = " AND ".join(where_clauses)
    order_limit_sql = f"ORDER BY RAND() LIMIT {limit}"

    cursor.execute(f"""
        SELECT
            e.id,
            e.name,
            e.description,
            e.section,
            l.name AS location_name,
            w.name AS website_name,
            GROUP_CONCAT(DISTINCT t.name ORDER BY t.name SEPARATOR ', ') AS tags,
            COUNT(DISTINCT eo.id) AS occurrence_count,
            MIN(eo.start_date) AS first_occurrence,
            MAX(eo.start_date) AS last_occurrence
        FROM events e
        LEFT JOIN locations l ON e.location_id = l.id
        LEFT JOIN websites w ON e.website_id = w.id
        LEFT JOIN event_tags et ON e.id = et.event_id
        LEFT JOIN tags t ON et.tag_id = t.id
        LEFT JOIN event_occurrences eo ON e.id = eo.event_id
        WHERE {where_sql}
        GROUP BY e.id, e.name, e.description, e.section, l.name, w.name
        {order_limit_sql}
    """, params)

    rows = cursor.fetchall()
    events = []
    for row in rows:
        events.append({
            'id': row[0],
            'name': row[1],
            'description': row[2],
            'section': row[3],
            'location_name': row[4],
            'website_name': row[5],
            'tags': row[6],
            'occurrence_count': row[7],
            'first_occurrence': str(row[8]) if row[8] else None,
            'last_occurrence': str(row[9]) if row[9] else None,
        })
    return events


def query_sample_events(cursor, limit: int = 50) -> list[dict]:
    """Backward-compat wrapper: random sample, no date filter."""
    return query_events(cursor, limit=limit)


def store_scores(cursor, connection, scores: list[dict], run_id: str, model_name: str):
    """Insert scored results into the event_scores table."""
    inserted = 0
    skipped = 0
    for score in scores:
        try:
            cursor.execute("""
                INSERT INTO event_scores
                    (event_id, scorer_run_id, scorer_model, specificity, novelty, openness, prominence,
                     connection, substance,
                     specificity_reason, novelty_reason, openness_reason, prominence_reason,
                     connection_reason, substance_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    scored_at = NOW(),
                    specificity = VALUES(specificity),
                    novelty = VALUES(novelty),
                    openness = VALUES(openness),
                    prominence = VALUES(prominence),
                    connection = VALUES(connection),
                    substance = VALUES(substance),
                    specificity_reason = VALUES(specificity_reason),
                    novelty_reason = VALUES(novelty_reason),
                    openness_reason = VALUES(openness_reason),
                    prominence_reason = VALUES(prominence_reason),
                    connection_reason = VALUES(connection_reason),
                    substance_reason = VALUES(substance_reason)
            """, (
                score['event_id'], run_id, model_name,
                score['specificity'], score['novelty'], score['openness'], score['prominence'],
                score['connection'], score['substance'],
                score.get('specificity_reason'), score.get('novelty_reason'),
                score.get('openness_reason'), score.get('prominence_reason'),
                score.get('connection_reason'), score.get('substance_reason'),
            ))
            inserted += 1
        except Exception as e:
            print(f"    Warning: failed to store score for event {score['event_id']}: {e}")
            skipped += 1
    connection.commit()
    return inserted, skipped


def print_summary(cursor, run_id: str):
    """Print a summary of scoring results: top/bottom per dimension + distribution."""
    cursor.execute("""
        SELECT es.event_id, e.name, l.name as location, w.name as website,
               es.specificity, es.novelty, es.openness, es.prominence, es.connection, es.substance,
               es.composite_score,
               es.specificity_reason, es.novelty_reason, es.openness_reason, es.prominence_reason,
               es.connection_reason, es.substance_reason
        FROM event_scores es
        JOIN events e ON es.event_id = e.id
        LEFT JOIN locations l ON e.location_id = l.id
        LEFT JOIN websites w ON e.website_id = w.id
        WHERE es.scorer_run_id = %s
        ORDER BY es.composite_score DESC
    """, (run_id,))
    rows = cursor.fetchall()

    if not rows:
        print("No scores found for this run.")
        return

    total = len(rows)
    print(f"\n{'='*70}")
    print(f"SCORING SUMMARY — Run: {run_id} ({total} events scored)")
    print(f"{'='*70}")

    # Column indices: 0=event_id, 1=name, 2=location, 3=website,
    #   4=specificity, 5=novelty, 6=openness, 7=prominence, 8=connection, 9=substance,
    #   10=composite_score,
    #   11=specificity_reason, 12=novelty_reason, 13=openness_reason, 14=prominence_reason,
    #   15=connection_reason, 16=substance_reason
    dims = [
        ('SPECIFICITY', 4,  11),
        ('NOVELTY',     5,  12),
        ('OPENNESS',    6,  13),
        ('PROMINENCE',  7,  14),
        ('CONNECTION',  8,  15),
        ('SUBSTANCE',   9,  16),
    ]

    for dim_name, score_col, reason_col in dims:
        scores_for_dim = [(r[score_col], r[1], r[2], r[3], r[reason_col]) for r in rows]
        scores_for_dim_sorted = sorted(scores_for_dim, key=lambda x: -x[0])
        mean_score = sum(s[0] for s in scores_for_dim) / total

        print(f"\n{dim_name} (mean: {mean_score:.1f})")

        # Top 3
        print("  Highest:")
        seen = set()
        shown = 0
        for score, name, location, website, reason in scores_for_dim_sorted:
            if shown >= 3:
                break
            key = (name, score)
            if key in seen:
                continue
            seen.add(key)
            venue_str = f" @ {location}" if location else ""
            print(f"    [{score}] {name}{venue_str}")
            if reason:
                print(f"         → {reason}")
            shown += 1

        # Bottom 3
        print("  Lowest:")
        seen = set()
        shown = 0
        for score, name, location, website, reason in reversed(scores_for_dim_sorted):
            if shown >= 3:
                break
            key = (name, score)
            if key in seen:
                continue
            seen.add(key)
            venue_str = f" @ {location}" if location else ""
            print(f"    [{score}] {name}{venue_str}")
            if reason:
                print(f"         → {reason}")
            shown += 1

    # Score distributions
    print(f"\n{'─'*70}")
    print("Score distributions (Sp=Specificity No=Novelty Op=Openness Pr=Prominence Co=Connection Su=Substance):")
    for dim_name, score_col, _ in dims:
        counts = {i: 0 for i in range(1, 6)}
        for r in rows:
            bucket = round(float(r[score_col]))
            if 1 <= bucket <= 5:
                counts[bucket] += 1
        dist = '  '.join(f"{k}={counts[k]}" for k in range(1, 6))
        print(f"  {dim_name:<12}: {dist}")

    # Composite top/bottom 5
    print(f"\n{'─'*70}")
    print("Composite score (sum of all 6 signals, max=30):")
    print("  Top 5:")
    for r in rows[:5]:
        name, loc = r[1], r[2]
        comp = r[10]
        spc, nov, opn, pro, con, sub = r[4], r[5], r[6], r[7], r[8], r[9]
        venue_str = f" @ {loc}" if loc else ""
        print(f"    {comp:5.1f}  [Sp:{spc} No:{nov} Op:{opn} Pr:{pro} Co:{con} Su:{sub}]  {name}{venue_str}")

    print("  Bottom 5:")
    for r in rows[-5:]:
        name, loc = r[1], r[2]
        comp = r[10]
        spc, nov, opn, pro, con, sub = r[4], r[5], r[6], r[7], r[8], r[9]
        venue_str = f" @ {loc}" if loc else ""
        print(f"    {comp:5.1f}  [Sp:{spc} No:{nov} Op:{opn} Pr:{pro} Co:{con} Su:{sub}]  {name}{venue_str}")

    print(f"\n{'='*70}")


# =============================================================================
# Gemini Scoring
# =============================================================================

async def score_batch(events_batch: list[dict]) -> list[dict]:
    """Call Gemini to score a batch of events. Returns list of score dicts."""
    if not genai_client:
        raise RuntimeError("Gemini client not initialized. Set GEMINI_API_KEY.")

    prompt = build_scoring_prompt(events_batch)

    response = await asyncio.wait_for(
        genai_client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": EventScoreBatch,
            }
        ),
        timeout=GEMINI_TIMEOUT
    )

    batch_result = EventScoreBatch.model_validate_json(response.text)
    return [s.model_dump() for s in batch_result.scores]


async def run_scorer(limit: int = 50, dry_run: bool = False, run_id: Optional[str] = None,
                     batch_size: int = 10, days_ahead: Optional[int] = None,
                     skip_scored: bool = False):
    """Main orchestrator: query → batch → score → store → summarize."""
    if run_id is None:
        run_id = datetime.now().strftime('%Y%m%d')

    print(f"{'='*70}")
    print(f"EVENT SCORER")
    if dry_run:
        print(f"  (Dry run — scores will NOT be stored)")
    print(f"  Run ID: {run_id}")
    print(f"  Model:  {GEMINI_MODEL}")
    if days_ahead is not None:
        print(f"  Filter: events with an occurrence in the next {days_ahead} days")
    if skip_scored:
        print(f"  Skipping events already scored in run {run_id}")
    print(f"{'='*70}\n")

    connection = db.create_connection()
    if not connection:
        print("Failed to connect to database")
        sys.exit(1)

    cursor = connection.cursor(buffered=True)

    try:
        # Query events
        skip_run_id = run_id if skip_scored else None
        if days_ahead is not None:
            print(f"Querying events with occurrences in the next {days_ahead} days...")
        else:
            print(f"Querying {limit} random events...")
        events = query_events(cursor, limit=limit, days_ahead=days_ahead, skip_run_id=skip_run_id)
        print(f"  Found {len(events)} events.\n")

        if not events:
            print("No events found to score.")
            return

        # Build events lookup for summary
        events_by_id = {e['id']: e for e in events}

        # Score in batches
        all_scores = []
        batches = [events[i:i+batch_size] for i in range(0, len(events), batch_size)]
        total_batches = len(batches)

        for i, batch in enumerate(batches, 1):
            event_ids = [e['id'] for e in batch]
            print(f"Scoring batch {i}/{total_batches} (events: {event_ids})...")

            try:
                scores = await score_batch(batch)
                all_scores.extend(scores)
                print(f"  → Scored {len(scores)} events.")
            except Exception as e:
                print(f"  → ERROR scoring batch {i}: {e}")
                continue

        print(f"\nTotal scored: {len(all_scores)}/{len(events)} events.")

        if dry_run:
            print("\n[Dry run] Sample scores:")
            for s in all_scores[:5]:
                eid = s['event_id']
                name = events_by_id.get(eid, {}).get('name', '(unknown)')
                print(f"  {name}")
                print(f"    Specificity:{s['specificity']} ({s.get('specificity_reason','')})")
                print(f"    Novelty:{s['novelty']} ({s.get('novelty_reason','')})")
                print(f"    Openness:{s['openness']} ({s.get('openness_reason','')})")
                print(f"    Prominence:{s['prominence']} ({s.get('prominence_reason','')})")
                print(f"    Connection:{s['connection']} ({s.get('connection_reason','')})")
                print(f"    Substance:{s['substance']} ({s.get('substance_reason','')})")
            print(f"\n[Dry run] Skipping database storage.")
        else:
            print("\nStoring scores...")
            inserted, skipped = store_scores(cursor, connection, all_scores, run_id, GEMINI_MODEL)
            print(f"  Stored: {inserted}, Skipped/errors: {skipped}")

            print_summary(cursor, run_id)

    finally:
        cursor.close()
        connection.close()


# =============================================================================
# CLI
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description='Score events on Rarity, Novelty, Openness, and Prominence using Gemini AI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pipeline/scorer.py                      # Score 50 random events
  python pipeline/scorer.py --limit 100          # Score 100 events
  python pipeline/scorer.py --dry-run            # Score but don't store
  python pipeline/scorer.py --run-id 20260218-v2 # Custom run ID
  python pipeline/scorer.py --batch-size 5       # Smaller batches (more reliable)
        """
    )
    parser.add_argument('--limit', type=int, default=50,
                        help='Number of events to score (default: 50)')
    parser.add_argument('--dry-run', '-d', action='store_true',
                        help='Score events but do not store results in DB')
    parser.add_argument('--run-id', type=str, default=None,
                        help='Scoring run identifier (default: YYYYMMDD)')
    parser.add_argument('--batch-size', type=int, default=10,
                        help='Events per Gemini API call (default: 10)')
    parser.add_argument('--upcoming-days', type=int, default=None, metavar='N',
                        help='Only score events with an occurrence in the next N days (no limit applied)')
    parser.add_argument('--skip-scored', action='store_true',
                        help='Skip events already scored under --run-id')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_scorer(
        limit=args.limit,
        dry_run=args.dry_run,
        run_id=args.run_id,
        batch_size=args.batch_size,
        days_ahead=args.upcoming_days,
        skip_scored=args.skip_scored,
    ))
