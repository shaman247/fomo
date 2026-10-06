#!/usr/bin/env python3
"""
Surface candidate sets for the event-tag quality audit (see /audit-event-tags).

The AI tagger systematically over-applies a handful of curated tags. This script
does NOT mutate anything — it just reports, so the judged passes (which need
per-event judgment) can be scoped. Two modes:

  (default)   Print counts for each KNOWN stray-tag pattern (candidate / denominator)
              so you can tell which patterns have grown enough to warrant a pass.
              Writes each pattern's candidate event-id list to .scratch/audit_<key>.json.

  --sample N  Write a deterministic "random" sample of N live events (id + name +
              event_type + venue + desc + curated tags + keywords) to
              .scratch/audit_sample.json for the discovery spot-check (catches NEW
              patterns the known list misses). Deterministic = reproducible (orders
              by md5(id), no RNG), so a re-run audits the same sample.

  --pattern KEY  Write full review snapshots for a known candidate set, including
                 raw location labels, complete descriptions and source URLs.

Patterns are intentionally broad candidate sets — every one is heterogeneous, so
NEVER bulk-delete from these lists. Feed them to the judged pass in /audit-event-tags.
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, "pipeline")
from db import create_connection  # noqa: E402

SCRATCH = ".scratch"

LIVE = "e.archived=0 AND e.suppressed=0"


def _descendants(cur, root_name):
    cur.execute("SELECT id FROM tags WHERE name=%s AND scope='event'", (root_name,))
    row = cur.fetchone()
    if not row:
        return set()
    root = row[0]
    seen, stack = {root}, [root]
    while stack:
        p = stack.pop()
        cur.execute("SELECT child_tag_id FROM tag_hierarchy WHERE parent_tag_id=%s", (p,))
        for (c,) in cur.fetchall():
            if c not in seen:
                seen.add(c)
                stack.append(c)
    return seen


def patterns(cur):
    """Return list of (key, label, candidate_sql, denominator_sql_or_None)."""
    music = _descendants(cur, "Music")
    mfmt = ",".join(str(i) for i in music) or "0"
    # Art leaf = has Art tag but NO Art-subtag present (so it shows as a top-level chip)
    cur.execute("SELECT id FROM tags WHERE name='Art' AND scope='event'")
    art_id = (cur.fetchone() or [0])[0]
    asub = ",".join(str(i) for i in _descendants(cur, "Art") if i != art_id) or "0"

    return [
        (
            "competition_as_sports",
            "Sports/Games on spoken-word or comedy performances (judge competition meaning)",
            f"""SELECT DISTINCT e.id FROM events e
                JOIN event_tags et ON et.event_id=e.id JOIN tags t ON t.id=et.tag_id
                WHERE {LIVE} AND t.scope='event' AND t.name IN ('Sports','Games')
                  AND e.event_type IN ('Comedy Show','Reading','Talk')""",
            None,
        ),
        (
            "live_comedy_as_music",
            "Music tags on comedy (live podcast/show may not involve musicians)",
            f"""SELECT DISTINCT e.id FROM events e
                JOIN event_tags et ON et.event_id=e.id JOIN tags t ON t.id=et.tag_id
                WHERE {LIVE} AND t.scope='event' AND t.name IN ('Live Music','New Music')
                  AND e.event_type='Comedy Show'""",
            None,
        ),
        (
            "civic_topic_as_activity",
            "Outdoor/Guided Tour on civic meetings (judge attendance, not agenda topic)",
            f"""SELECT DISTINCT e.id FROM events e
                JOIN event_tags et ON et.event_id=e.id JOIN tags t ON t.id=et.tag_id
                WHERE {LIVE} AND t.scope='event' AND t.name IN ('Outdoor','Guided Tour')
                  AND e.event_type='Civic Meeting'""",
            None,
        ),
        (
            "art_on_music",
            "Art tag on music Concerts (Art shows as a top-level chip)",
            f"""SELECT DISTINCT e.id FROM events e
                JOIN event_tags art ON art.event_id=e.id AND art.tag_id={art_id}
                WHERE {LIVE} AND e.event_type='Concert'
                  AND EXISTS (SELECT 1 FROM event_tags m WHERE m.event_id=e.id AND m.tag_id IN ({mfmt}))
                  AND NOT EXISTS (SELECT 1 FROM event_tags a WHERE a.event_id=e.id AND a.tag_id IN ({asub}))""",
            f"SELECT COUNT(*) FROM events e WHERE {LIVE} AND e.event_type='Concert'",
        ),
        (
            "virtual_on_physical",
            "Virtual events with physical map pins (delivery unknown; verify source before removal)",
            f"""SELECT DISTINCT e.id FROM events e
                JOIN event_tags et ON et.event_id=e.id
                JOIN tags t ON t.id=et.tag_id AND t.name='Virtual' AND t.scope='event'
                JOIN locations l ON l.id=e.location_id
                WHERE {LIVE} AND COALESCE(l.generic_location,0)=0
                  AND COALESCE(l.name,'') NOT LIKE '%Online%' AND COALESCE(l.name,'') NOT LIKE '%Virtual%'""",
            f"""SELECT COUNT(DISTINCT e.id) FROM events e
                JOIN event_tags et ON et.event_id=e.id JOIN tags t ON t.id=et.tag_id AND t.name='Virtual' AND t.scope='event'
                WHERE {LIVE}""",
        ),
        (
            "literature_on_screening",
            "Literature tag on Screenings (keep only real adaptations)",
            f"""SELECT DISTINCT e.id FROM events e
                JOIN event_tags et ON et.event_id=e.id
                JOIN tags t ON t.id=et.tag_id AND t.name='Literature'
                WHERE {LIVE} AND e.event_type='Screening'""",
            f"SELECT COUNT(*) FROM events e WHERE {LIVE} AND e.event_type='Screening'",
        ),
        (
            # Discovered 2026-06-19 via the --sample discovery pass: the tagger
            # attaches 'Theater' to plain music concerts (held at theater venues)
            # and to film screenings. Keep only genuinely staged/dramatic work
            # (musical theater, opera, cabaret-as-theater, play, dance-theater,
            # immersive) or a filmed stage production (NT Live, filmed Broadway).
            "theater_on_concert_screening",
            "Theater tag on Concerts/Screenings (keep only staged/dramatic work)",
            f"""SELECT DISTINCT e.id FROM events e
                JOIN event_tags et ON et.event_id=e.id
                JOIN tags t ON t.id=et.tag_id AND t.name='Theater'
                WHERE {LIVE} AND e.event_type IN ('Concert','Screening')""",
            f"SELECT COUNT(*) FROM events e WHERE {LIVE} AND e.event_type IN ('Concert','Screening')",
        ),
        (
            # Discovered 2026-07-31 via the --sample discovery pass: the tagger
            # reads "free" off a program blurb and ignores that the VENUE charges
            # admission, so the program is free but *attending* is not (MoMA
            # drop-in drawing behind a ~$30 door fee; a Long Island Children's
            # Museum craft "included with admission"). Heterogeneous like every
            # other pattern here — plenty of these venues have genuinely free
            # hours/days (Whitney free Fridays, Brooklyn Museum First Saturdays)
            # and some are always free — so this needs a judged pass, never a
            # bulk delete. Remove only when admission is actually required.
            "free_at_paid_admission_venue",
            "Free tag on events at paid-admission venues (free WITH admission is not free)",
            f"""SELECT DISTINCT e.id FROM events e
                JOIN event_tags et ON et.event_id=e.id
                JOIN tags t ON t.id=et.tag_id AND t.name='Free'
                JOIN locations l ON l.id=e.location_id
                JOIN location_tags lt ON lt.location_id=l.id
                JOIN tags vt ON vt.id=lt.tag_id
                     AND vt.name IN ('Museum','Zoo','Aquarium','Botanical Garden','Science','Historic Site')
                WHERE {LIVE}""",
            f"""SELECT COUNT(DISTINCT e.id) FROM events e
                JOIN event_tags et ON et.event_id=e.id
                JOIN tags t ON t.id=et.tag_id AND t.name='Free'
                WHERE {LIVE}""",
        ),
    ]


def run_counts(cur, output_dir=SCRATCH):
    os.makedirs(output_dir, exist_ok=True)
    print("Event-tag audit — candidate counts (read-only). Feed sets to /audit-event-tags judged pass.\n")
    for key, label, cand_sql, denom_sql in patterns(cur):
        cur.execute(cand_sql)
        ids = sorted(r[0] for r in cur.fetchall())
        denom = ""
        if denom_sql:
            cur.execute(denom_sql)
            d = cur.fetchone()[0]
            denom = f" / {d} ({round(100*len(ids)/d) if d else 0}% of type)"
        path = os.path.join(output_dir, f"audit_{key}.json")
        json.dump(ids, open(path, "w"))
        print(f"  {len(ids):>5}{denom}")
        print(f"        {label}")
        print(f"        -> {path}\n")


def review_snapshots(cur, ids):
    """Keep delivery evidence separate from the organizer's physical map pin.

    Stored text can omit online delivery; these are evidence packets, never
    authorization to remove Virtual. Review the linked event pages first.
    """
    out = []
    for eid in ids:
        cur.execute(
            """SELECT e.name, e.event_type, e.description, e.location_name, l.name loc2,
                      e.sublocation, l.address
               FROM events e LEFT JOIN locations l ON l.id=e.location_id WHERE e.id=%s""",
            (eid,),
        )
        row = cur.fetchone()
        if row is None:
            continue
        name, etype, desc, locn, loc2, sublocation, address = row
        cur.execute(
            """SELECT t.name, t.type FROM event_tags et JOIN tags t ON t.id=et.tag_id
               WHERE et.event_id=%s AND t.scope='event' ORDER BY t.type, t.name""",
            (eid,),
        )
        tags = cur.fetchall()
        cur.execute("SELECT url FROM event_urls WHERE event_id=%s ORDER BY url", (eid,))
        urls = [r[0] for r in cur.fetchall()]
        out.append({
            "id": eid, "name": name, "event_type": etype,
            "venue": loc2 or "", "venue_address": address or "",
            "location_name": locn or "", "sublocation": sublocation or "",
            "desc": desc or "", "urls": urls,
            "curated_tags": [t for t, ty in tags if ty == "tag"],
            "keywords": [t for t, ty in tags if ty != "tag"],
            "virtual_review": {
                "source_verification_required_before_removal": True,
                "default_without_delivery_evidence": "review",
                "physical_map_pin_proves_in_person": False,
            } if any(t == 'Virtual' and ty == 'tag' for t, ty in tags) else None,
        })
    return out


def run_sample(cur, n, output_dir=SCRATCH):
    os.makedirs(output_dir, exist_ok=True)
    cur.execute(f"SELECT id FROM events e WHERE {LIVE}")
    ids = [r[0] for r in cur.fetchall()]
    ids.sort(key=lambda i: hashlib.md5(str(i).encode()).hexdigest())
    out = review_snapshots(cur, ids[:n])
    path = os.path.join(output_dir, "audit_sample.json")
    json.dump(out, open(path, "w"), ensure_ascii=False)
    print(f"Wrote deterministic sample of {len(out)} live events -> {path}")


def run_pattern(cur, key, output_dir=SCRATCH):
    pattern = next((p for p in patterns(cur) if p[0] == key), None)
    if pattern is None:
        raise ValueError(f'Unknown audit pattern: {key}')
    cur.execute(pattern[2])
    ids = sorted(r[0] for r in cur.fetchall())
    out = review_snapshots(cur, ids)
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f'audit_{key}_review.json')
    with open(path, 'w') as stream:
        json.dump(out, stream, ensure_ascii=False, indent=2)
    print(f'Wrote {len(out)} review snapshots -> {path}')


def main():
    ap = argparse.ArgumentParser(description="Surface event-tag audit candidates (read-only)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--sample", type=int, metavar="N",
                    help="write a deterministic random sample of N live events for the discovery spot-check")
    mode.add_argument('--pattern', help='write complete review snapshots for one known pattern')
    ap.add_argument('--output-dir', default=SCRATCH, help='directory for read-only audit output')
    args = ap.parse_args()
    if args.sample is not None and args.sample < 1:
        ap.error('--sample must be positive')
    conn = create_connection()
    cur = conn.cursor()
    if args.sample is not None:
        run_sample(cur, args.sample, args.output_dir)
    elif args.pattern:
        run_pattern(cur, args.pattern, args.output_dir)
    else:
        run_counts(cur, args.output_dir)
    conn.close()


if __name__ == "__main__":
    main()
