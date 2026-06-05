#!/usr/bin/env python3
"""
Audit / QA the events.event_type column.

Three independent checks (run all by default, or one via flags):

  --validate   Every stored event_type must be in pipeline.event_types.
               Catches typos, retired labels, NULLs on active events.
  --drift      Name-vs-type consistency. Flags events whose NAME strongly
               implies one structural type but whose stored type disagrees
               (e.g. "Trivia Night" not typed Game). Surfaces cross-batch
               classifier drift. Reports only — does not auto-fix.
  --new-types  Finds events anywhere in the taxonomy whose name/description
               fits a newer type (Immersive Experience, Community Celebration)
               but that were forced into an older bucket before the type
               existed. Use to drive a targeted re-classification.

Scope defaults to active events (archived=0, suppressed=0). Pass --all-states
to include everything. Use --emit-ids FILE to write the union of drift +
new-type candidate IDs to a JSON file for a re-classification pass.
"""
import argparse
import json
import re
import sys

sys.path.insert(0, "pipeline")
from db import create_connection  # noqa: E402
import event_types as et  # noqa: E402

# --- Drift rules: (label, name_regex, {allowed types}) -----------------------
# A row is flagged when its name matches the regex but its event_type is NOT in
# the allowed set. Allowed sets are generous on purpose — we want real drift,
# not defensible judgment calls. Word boundaries keep "tour" out of "detour".
DRIFT_RULES = [
    ("trivia/bingo/quiz -> Game",
     r"\b(trivia|bingo|quiz|pub quiz)\b", {"Game"}),
    ("open mic / jam session -> Open Practice",
     r"\b(open mic|jam session|open jam|figure drawing|life drawing)\b", {"Open Practice"}),
    # NOTE: "bootcamp" intentionally excluded — it's as often a skill intensive
    # (Class) as a fitness session. "yoga" still catches philosophy talks; those
    # get sorted out in re-judgment.
    ("yoga/pilates/zumba/run club -> Fitness",
     r"\b(yoga|pilates|zumba|spin class|run club|hiit)\b", {"Fitness", "Class"}),
    ("book club -> Discussion Group",
     r"\bbook club\b", {"Discussion Group"}),
    ("walking/garden/boat tour -> Tour",
     r"\b(walking tour|garden tour|boat tour|guided tour|birding|bird walk)\b", {"Tour"}),
    ("trivia-style 'comedy' guard (informational)",
     r"\bstand-?up\b", {"Comedy Show", "Open Practice", "Class", "Workshop"}),
    ("exhibition / on view -> Exhibition",
     r"\b(on view|exhibition opening|now on view)\b", {"Exhibition", "Open House"}),
    ("mass/worship/shabbat -> Service",
     r"\b(sunday mass|holy mass|worship service|shabbat service|vespers)\b", {"Service"}),
]

# --- New-type candidate patterns ---------------------------------------------
# Broad nets — every hit is a *candidate* for human/AI re-judgment, not a verdict.
NEW_TYPE_PATTERNS = {
    # High precision: words that almost always denote a constructed sensory
    # environment, not a performance/exhibition that merely uses the words.
    "Immersive Experience": (
        r"(\bimmersive\b|dining in the dark|paint in the dark|\bin the dark\b|"
        r"overnight experience|night at the museum|escape room|"
        r"scent & |scent and |sensory journey|silent disco dinner)"
    ),
    # Community/civic celebration language only — NOT bare "celebration" or
    # "anniversary" (those overwhelmingly belong to Concert/Benefit/Theater/
    # Festival rows that happen to mark an occasion).
    "Community Celebration": (
        r"(\bcommunity (day|celebration|festival)\b|\bfamily (day|fun day)\b|"
        r"\bfun day\b|block party|\bday celebration\b|seasonal celebration|"
        r"summer celebration|school'?s out|juneteenth celebration|"
        r"pride celebration|lunar new year celebration)"
    ),
}


def _scope(all_states):
    return "" if all_states else " AND e.archived=0 AND e.suppressed=0"


def run_validate(cur, all_states):
    print("== VALIDATE: stored labels vs canonical set ==")
    cur.execute(
        f"SELECT event_type, COUNT(*) c FROM events e WHERE event_type IS NOT NULL"
        f"{_scope(all_states)} GROUP BY event_type ORDER BY c DESC"
    )
    invalid = []
    for label, c in cur.fetchall():
        if not et.is_valid_event_type(label):
            invalid.append((label, c))
    if invalid:
        print("  INVALID labels found:")
        for label, c in invalid:
            print(f"    {c:>5}  {label!r}")
    else:
        print("  OK — all stored labels are valid.")
    cur.execute(
        f"SELECT COUNT(*) FROM events e WHERE event_type IS NULL{_scope(all_states)}"
    )
    nulls = cur.fetchone()[0]
    print(f"  NULL event_type (in scope): {nulls}")
    return [label for label, _ in invalid]


def run_drift(cur, all_states):
    print("\n== DRIFT: name implies a type the stored value contradicts ==")
    flagged = {}
    for label, regex, allowed in DRIFT_RULES:
        allowed_sql = ",".join("%s" for _ in allowed)
        cur.execute(
            f"SELECT id, name, event_type FROM events e "
            f"WHERE e.name REGEXP %s AND e.event_type IS NOT NULL "
            f"AND e.event_type NOT IN ({allowed_sql}){_scope(all_states)} "
            f"ORDER BY e.id",
            [regex, *allowed],
        )
        rows = cur.fetchall()
        if rows:
            print(f"  [{label}] — {len(rows)} mismatch(es):")
            for rid, name, etype in rows[:8]:
                print(f"      {rid}  ({etype})  {name[:60]}")
            if len(rows) > 8:
                print(f"      ... +{len(rows) - 8} more")
        for rid, name, etype in rows:
            flagged[rid] = {"name": name, "current": etype, "rule": label}
    if not flagged:
        print("  OK — no drift flagged.")
    return flagged


def run_new_types(cur, all_states):
    print("\n== NEW-TYPE CANDIDATES (mis-bucketed before the type existed) ==")
    candidates = {}
    for new_type, regex in NEW_TYPE_PATTERNS.items():
        cur.execute(
            f"SELECT id, name, event_type FROM events e "
            f"WHERE e.name REGEXP %s AND e.event_type IS NOT NULL "
            f"AND e.event_type <> %s{_scope(all_states)} ORDER BY e.id",
            [regex, new_type],
        )
        rows = cur.fetchall()
        print(f"  [{new_type}] — {len(rows)} candidate(s) currently typed otherwise:")
        for rid, name, etype in rows[:12]:
            print(f"      {rid}  ({etype})  {name[:60]}")
        if len(rows) > 12:
            print(f"      ... +{len(rows) - 12} more")
        for rid, name, etype in rows:
            candidates[rid] = {"name": name, "current": etype, "suggests": new_type}
    return candidates


def main():
    ap = argparse.ArgumentParser(description="Audit events.event_type")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--drift", action="store_true")
    ap.add_argument("--new-types", action="store_true")
    ap.add_argument("--all-states", action="store_true",
                    help="include archived/suppressed (default: active only)")
    ap.add_argument("--emit-ids", metavar="FILE",
                    help="write union of drift+new-type candidate ids to JSON")
    args = ap.parse_args()

    run_all = not (args.validate or args.drift or args.new_types)
    conn = create_connection()
    cur = conn.cursor()

    flagged, candidates = {}, {}
    if run_all or args.validate:
        run_validate(cur, args.all_states)
    if run_all or args.drift:
        flagged = run_drift(cur, args.all_states)
    if run_all or args.new_types:
        candidates = run_new_types(cur, args.all_states)

    if args.emit_ids:
        union = {}
        union.update(candidates)
        union.update(flagged)  # drift detail wins if an id is in both
        with open(args.emit_ids, "w") as f:
            json.dump({"ids": sorted(union), "detail": {str(k): v for k, v in union.items()}}, f, indent=2)
        print(f"\nWrote {len(union)} candidate id(s) to {args.emit_ids}")

    conn.close()


if __name__ == "__main__":
    main()
