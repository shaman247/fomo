"""Second-pass duplicate audit: re-check dismissals + detect umbrella/envelope events.

`find_duplicate_events.py` is the *first* pass — it surfaces fresh candidate pairs.
This script is the *second* pass over two blind spots that survive the first one:

1. --dismissed : pairs previously recorded in `dedupe_dismissed_pairs` that, on
   re-examination, look like genuine duplicates after all (a judgment call that was
   wrong, e.g. two differently-titled listings of the same event waved off as
   "concurrent programming"). Only pairs where BOTH events are still live AND share
   a concrete date+time are reconsidered, ranked by name/description similarity with
   boilerplate descriptions filtered out.

2. --umbrellas : a generic "umbrella" event that duplicates several specific
   sub-events (it holds their URLs and/or the union of their dates), or a specific
   event that has "date-bled" a whole series' dates onto itself. The merger's
   pairwise dedup can't see these because one row stands in for many.

This script only REPORTS. Apply fixes with the primitives in find_duplicate_events:
    merge_pair / apply_field_overrides / record_dismissal
plus, for umbrellas, `UPDATE events SET suppressed=1` (umbrella) or
`DELETE FROM event_occurrences` (date-bleed) — see /recheck-duplicates.

Usage:
    ./venv/bin/python scripts/recheck_duplicates.py              # both sections
    ./venv/bin/python scripts/recheck_duplicates.py --dismissed  # only re-audit
    ./venv/bin/python scripts/recheck_duplicates.py --umbrellas  # only umbrellas
    ./venv/bin/python scripts/recheck_duplicates.py --limit 60
"""
import argparse
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher

sys.path.insert(0, 'pipeline')
from db import create_connection


def _norm(s):
    return re.sub(r'[^a-z0-9 ]', '', (s or '').lower()).strip()


def get_dismissed_umbrellas(cur):
    """Set of umbrella_ids a reviewer cleared as not-a-problematic-umbrella."""
    cur.execute("SELECT umbrella_id FROM dedupe_dismissed_umbrellas")
    return {r['umbrella_id'] if isinstance(r, dict) else r[0] for r in cur.fetchall()}


def record_umbrella_dismissal(cur, umbrella_id, reason):
    """Mark an umbrella suspect as reviewed-and-cleared so it stops re-surfacing."""
    cur.execute(
        "INSERT INTO dedupe_dismissed_umbrellas (umbrella_id, reason) VALUES (%s, %s) "
        "ON DUPLICATE KEY UPDATE reason = VALUES(reason)",
        (umbrella_id, reason),
    )


def _live(cur):
    """All active (archived=0, suppressed=0) events keyed by id with fields we need."""
    cur.execute("""
        SELECT id, name, description, location_id, website_id
        FROM events WHERE archived = 0 AND suppressed = 0
    """)
    return {r['id']: r for r in cur.fetchall()}


def _occ_map(cur):
    """event_id -> set of (start_date, start_time) for active events (start_time required)."""
    cur.execute("""
        SELECT o.event_id, o.start_date, COALESCE(o.start_time,'') st
        FROM event_occurrences o
        JOIN events e ON e.id = o.event_id
        WHERE e.archived = 0 AND e.suppressed = 0
    """)
    m = defaultdict(set)
    for r in cur.fetchall():
        m[r['event_id']].add((str(r['start_date']), r['st']))
    return m


def _url_map(cur):
    """event_id -> set of urls for active events."""
    cur.execute("""
        SELECT u.event_id, u.url
        FROM event_urls u
        JOIN events e ON e.id = u.event_id
        WHERE e.archived = 0 AND e.suppressed = 0
    """)
    m = defaultdict(set)
    for r in cur.fetchall():
        m[r['event_id']].add(r['url'])
    return m


def audit_dismissed(cur, limit):
    """Re-rank dismissed pairs that may be real duplicates."""
    live = _live(cur)
    occ = _occ_map(cur)
    cur.execute("SELECT event_id_a, event_id_b, reason FROM dedupe_dismissed_pairs")
    dismissed = cur.fetchall()

    # detect templated/boilerplate descriptions reused across many events
    descfreq = Counter()
    pairs = []
    for d in dismissed:
        a, b = live.get(d['event_id_a']), live.get(d['event_id_b'])
        if not a or not b:                      # one side merged/suppressed/archived
            continue
        shared = [x for x in (occ[a['id']] & occ[b['id']]) if x[1]]  # shared date+time
        if not shared:
            continue
        pairs.append((a, b, d['reason']))
        descfreq[_norm(a['description'])[:200]] += 1
        descfreq[_norm(b['description'])[:200]] += 1

    out = []
    for a, b, reason in pairs:
        da, db = _norm(a['description'])[:200], _norm(b['description'])[:200]
        boiler = descfreq[da] > 2 or descfreq[db] > 2
        nsim = SequenceMatcher(None, _norm(a['name']), _norm(b['name'])).ratio()
        dsim = SequenceMatcher(None, _norm(a['description'])[:600], _norm(b['description'])[:600]).ratio()
        # high-signal: a genuine rename keeps most of the name, OR
        # different titles but a substantive (non-boilerplate) shared description
        flag = None
        if nsim >= 0.85 and not boiler:
            flag = 'HI-NAME'
        elif nsim >= 0.55 and dsim >= 0.9 and not boiler and len(da) > 80:
            flag = 'HI-DESC'
        if flag:
            out.append((max(nsim, dsim), flag, nsim, dsim, a, b, reason))

    out.sort(reverse=True)
    print(f"\n=== DISMISSED-PAIR RE-AUDIT ===")
    print(f"{len(pairs)} live dismissed pairs share a date+time; "
          f"{len(out)} look worth a fresh holistic review (showing {min(limit, len(out))}):\n")
    for _, flag, nsim, dsim, a, b, reason in out[:limit]:
        print(f"[{flag}] n={nsim:.2f} d={dsim:.2f} | {a['id']} vs {b['id']}")
        print(f"    {a['name'][:60]!r}")
        print(f"    {b['name'][:60]!r}")
        print(f"    dismissed-as: {reason[:90]}")
    if not out:
        print("  (nothing flagged — earlier dismissals hold up)")
    print("\nHolistically review each: same event re-listed under a new title/slug -> merge_pair;\n"
          "genuinely distinct -> leave (the dismissal still stands).")


def audit_umbrellas(cur, limit):
    """Flag umbrella events (hold sub-events' URLs/dates) and date-bled specifics."""
    live = _live(cur)
    occ = _occ_map(cur)
    urls = _url_map(cur)

    # group active events by (location_id, website_id)
    groups = defaultdict(list)
    for eid, e in live.items():
        groups[(e['location_id'], e['website_id'])].append(eid)

    umbrellas = []     # (umbrella_id, [child_ids], why)
    for key, ids in groups.items():
        if len(ids) < 2:
            continue
        for big in ids:
            big_urls, big_occ = urls.get(big, set()), occ.get(big, set())
            if len(big_occ) < 2 or not big_urls:
                continue
            # A child must BOTH share a specific URL with the umbrella AND have all
            # its occurrences inside the umbrella's date set. Requiring both signals
            # (not date-containment alone) avoids flagging unrelated events that
            # merely share a busy venue calendar.
            children = []
            for other in ids:
                if other == big:
                    continue
                ou, oo = urls.get(other, set()), occ.get(other, set())
                if ou and oo and (ou & big_urls) and oo <= big_occ and len(oo) < len(big_occ):
                    children.append(other)
            if len(children) >= 2:
                why = f"shares URLs with + date-covers {len(children)} sub-events"
                umbrellas.append((big, sorted(children), why))

    # drop umbrellas a reviewer already cleared
    dismissed = get_dismissed_umbrellas(cur)
    umbrellas = [u for u in umbrellas if u[0] not in dismissed]

    # de-dup: prefer reporting each umbrella once (largest child set wins)
    umbrellas.sort(key=lambda x: -len(x[1]))
    seen_children = set()
    final = []
    for big, children, why in umbrellas:
        if big in seen_children:
            continue
        final.append((big, children, why))
        seen_children.update(children)

    print(f"\n=== UMBRELLA / ENVELOPE SUSPECTS ===")
    print(f"{len(final)} suspect umbrella events (showing {min(limit, len(final))}):\n")
    for big, children, why in final[:limit]:
        e = live[big]
        print(f"umbrella {big}  {e['name'][:55]!r}  (loc {e['location_id']}, w{e['website_id']})")
        print(f"    {why}; {len(occ.get(big,set()))} occurrences")
        for c in children[:8]:
            print(f"      sub {c}  {live[c]['name'][:55]!r}  ({len(occ.get(c,set()))} occ)")
        print()
    if not final:
        print("  (no umbrella suspects)")
    print("Fix: if specific sub-events fully cover the umbrella's future dates,\n"
          "  `UPDATE events SET suppressed=1` on the umbrella. If a *specific* event has\n"
          "  date-bled a series onto itself, DELETE the stray occurrences. Verify coverage first.")


def main():
    p = argparse.ArgumentParser(description='Second-pass duplicate audit')
    p.add_argument('--dismissed', action='store_true', help='only the dismissed-pair re-audit')
    p.add_argument('--umbrellas', action='store_true', help='only umbrella/envelope detection')
    p.add_argument('--limit', type=int, default=50, help='max rows per section (default 50)')
    args = p.parse_args()
    both = not (args.dismissed or args.umbrellas)

    conn = create_connection()
    cur = conn.cursor(dictionary=True)
    if both or args.dismissed:
        audit_dismissed(cur, args.limit)
    if both or args.umbrellas:
        audit_umbrellas(cur, args.limit)
    conn.close()


if __name__ == '__main__':
    main()
