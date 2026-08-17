#!/usr/bin/env python3
"""
Mirror events.event_type into the curated tag hierarchy as a "Format" root family
so event types filter/search exactly like any other tag.

Two phases (run both by default):

  --build   Ensure the tag nodes + hierarchy edges exist:
              Format (root)
                └─ Performance / Participatory / Browsable / Social / Gathering / Excursions
                     └─ the 33 event-type leaves
            Promotes keyword tags to curated (type='tag'), fills missing emojis,
            and wires edges. Idempotent.

  --sync    Rebuild event_tags membership for the Format family from event_type
            (authoritative). For every active event, its event_type leaf +
            category + Format root are (re)applied; stale Format-axis rows are
            cleared first so reclassifications are reflected.

Authoritative vs union: 25 of the 33 leaves are Format-only nodes — their
membership becomes EXACTLY event_type. The other 8 (Concert, Sports, Reading,
Workshop, Fitness, Volunteer, Party, Festival) also exist as content-genre nodes
with their own subtrees, so they are multi-parented (kept under their genre root
AND added under Format) and their content-applied instances are preserved
(additive, not wiped) to avoid orphaning the genre subtrees.

The canonical taxonomy + emojis + category names live in pipeline/event_types.py.
"""
import argparse
import sys

sys.path.insert(0, "pipeline")
from db import create_connection  # noqa: E402
import event_types as et  # noqa: E402

# Leaves that double as established content-genre nodes (they have content
# subtrees). Multi-parented and additive — never wiped — so the genre subtrees
# and the ancestor invariant stay intact.
GENRE_HOMONYMS = {
    "Concert", "Sports", "Reading", "Workshop", "Fitness", "Volunteer",
    "Party", "Festival",
}


def _tag_id(cur, name):
    cur.execute("SELECT id FROM tags WHERE name=%s", (name,))
    r = cur.fetchone()
    return r[0] if r else None


def _ensure_tag(cur, name, emoji):
    """Ensure a curated tag exists. Promote keyword->tag; fill emoji only if empty
    (never overwrite an existing curated emoji). Returns tag id."""
    cur.execute("SELECT id, type, emoji FROM tags WHERE name=%s", (name,))
    r = cur.fetchone()
    if r:
        tid, typ, em = r
        if typ != "tag" or not (em or "").strip():
            cur.execute(
                "UPDATE tags SET type='tag', emoji=COALESCE(NULLIF(emoji,''),%s) WHERE id=%s",
                (emoji, tid),
            )
        return tid
    cur.execute("INSERT INTO tags (name, type, emoji) VALUES (%s,'tag',%s)", (name, emoji))
    return cur.lastrowid


def _ensure_edge(cur, parent_id, child_id):
    cur.execute(
        "SELECT 1 FROM tag_hierarchy WHERE parent_tag_id=%s AND child_tag_id=%s",
        (parent_id, child_id),
    )
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO tag_hierarchy (parent_tag_id, child_tag_id) VALUES (%s,%s)",
            (parent_id, child_id),
        )


def build_family(cur, conn):
    root = _ensure_tag(cur, et.FORMAT_ROOT_TAG, et.FORMAT_ROOT_EMOJI)
    cat_id = {}
    for cat, (tag_name, emoji) in et.CATEGORY_TAG.items():
        cid = _ensure_tag(cur, tag_name, emoji)
        _ensure_edge(cur, root, cid)
        cat_id[cat] = cid

    moved, multiparented, created = [], [], []
    for cat, types in et.EVENT_TYPES_BY_CATEGORY.items():
        cid = cat_id[cat]
        for t in types:
            existed = _tag_id(cur, t) is not None
            tid = _ensure_tag(cur, t, et.TYPE_EMOJI[t])
            _ensure_edge(cur, cid, tid)
            if t in GENRE_HOMONYMS:
                multiparented.append(t)  # keep genre parent(s) too
            else:
                # Move fully into Format: drop any non-Format parent edges.
                cur.execute(
                    "DELETE FROM tag_hierarchy WHERE child_tag_id=%s AND parent_tag_id<>%s",
                    (tid, cid),
                )
                (moved if existed else created).append(t)
    conn.commit()
    print(f"  build: root+{len(cat_id)} categories ensured")
    print(f"  moved into Format (sole parent): {len(moved)} -> {sorted(moved)}")
    print(f"  multi-parented genre homonyms:   {len(multiparented)} -> {sorted(multiparented)}")
    print(f"  newly created leaves:            {len(created)} -> {sorted(created)}")


def sync_event_tags(cur, conn):
    root = _tag_id(cur, et.FORMAT_ROOT_TAG)
    cat_id = {cat: _tag_id(cur, tn) for cat, (tn, _) in et.CATEGORY_TAG.items()}
    leaf_id = {t: _tag_id(cur, t) for t in et.EVENT_TYPES}
    type_cat = {t: et.category_for(t) for t in et.EVENT_TYPES}

    missing = [t for t, i in leaf_id.items() if i is None]
    if missing:
        sys.exit(f"ERROR: Format leaf tags missing (run --build first): {missing}")

    # 1) Wipe Format-axis-exclusive rows so reclassifications/category moves are
    #    reflected. Clean leaves + categories + root are wiped; genre-homonym
    #    leaves are left alone (their content membership is preserved).
    clean_leaf_ids = [leaf_id[t] for t in et.EVENT_TYPES if t not in GENRE_HOMONYMS]
    wipe_ids = clean_leaf_ids + list(cat_id.values()) + [root]
    fmt = ",".join(["%s"] * len(wipe_ids))
    cur.execute(f"DELETE FROM event_tags WHERE tag_id IN ({fmt})", wipe_ids)
    wiped = cur.rowcount

    # 2) Reapply leaf + category + root from event_type for every active event.
    fmt_t = ",".join(["%s"] * len(et.EVENT_TYPES))
    cur.execute(
        f"SELECT id, event_type FROM events "
        f"WHERE archived=0 AND suppressed=0 AND event_type IN ({fmt_t})",
        et.EVENT_TYPES,
    )
    rows = cur.fetchall()
    ins = []
    for eid, etype in rows:
        ins.append((eid, leaf_id[etype]))
        ins.append((eid, cat_id[type_cat[etype]]))
        ins.append((eid, root))
    # Insert in chunks. mysql-connector's executemany collapses the whole list
    # into ONE multi-row INSERT statement, so a single call scales with the
    # active-event count and eventually exceeds `max_allowed_packet` — which it
    # did on 2026-08-06 at ~26.5K active events (~79.6K tuples), aborting the
    # sync AFTER the wipe DELETE had run. The DELETE rolled back with the failed
    # transaction so no data was lost, but the sync silently did nothing.
    # Chunking keeps each statement small and bounded regardless of DB size.
    CHUNK = 5000
    for i in range(0, len(ins), CHUNK):
        cur.executemany(
            "INSERT IGNORE INTO event_tags (event_id, tag_id) VALUES (%s,%s)",
            ins[i:i + CHUNK],
        )
    conn.commit()
    print(f"  sync: wiped {wiped} stale Format rows; applied to {len(rows)} active events "
          f"({len(ins)} tag rows inserted in chunks of {CHUNK}, dupes ignored)")


def print_stats(cur):
    print("\n== Format family event counts (active) ==")
    cur.execute(
        """SELECT t.name, COUNT(DISTINCT et.event_id) c
           FROM tags t
           JOIN event_tags et ON et.tag_id=t.id
           JOIN events e ON e.id=et.event_id AND e.archived=0 AND e.suppressed=0
           WHERE t.name=%s OR t.name IN (%s) OR t.name IN (%s)
           GROUP BY t.name ORDER BY c DESC""" % (
            "%s",
            ",".join(["%s"] * len(et.CATEGORY_TAG)),
            ",".join(["%s"] * len(et.EVENT_TYPES)),
        ),
        [et.FORMAT_ROOT_TAG] + [tn for tn, _ in et.CATEGORY_TAG.values()] + list(et.EVENT_TYPES),
    )
    for name, c in cur.fetchall():
        print(f"  {c:>5}  {name}")


def main():
    ap = argparse.ArgumentParser(description="Mirror event_type into the Format tag family")
    ap.add_argument("--build", action="store_true", help="ensure tag nodes + edges only")
    ap.add_argument("--sync", action="store_true", help="rebuild event_tags membership only")
    ap.add_argument("--stats", action="store_true", help="print resulting counts")
    args = ap.parse_args()
    run_all = not (args.build or args.sync)

    conn = create_connection()
    cur = conn.cursor()
    if run_all or args.build:
        print("Building Format tag family...")
        build_family(cur, conn)
    if run_all or args.sync:
        print("Syncing event_tags from event_type...")
        sync_event_tags(cur, conn)
    if args.stats or run_all:
        print_stats(cur)
    conn.close()


if __name__ == "__main__":
    main()
