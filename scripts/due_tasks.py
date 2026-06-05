#!/usr/bin/env python3
"""List scheduled tasks that are due, from .claude/scheduled-tasks.md.

The daily /run-pipeline command runs this at Step 0 to find date-triggered
maintenance tasks (recrawls, annual gate bumps, deferred-site tests, etc.) that
should be performed today. Detection is deterministic here rather than relying
on the model eyeballing dates.

Task file format (.claude/scheduled-tasks.md) — one task per `## ` heading:

    ## <title>
    - Due: YYYY-MM-DD
    - Status: pending          # pending | done
    - Recur: none              # none | annual | <N>d  (e.g. 365d)
    <freeform action steps, SQL, commands ...>

A task is DUE when Status == pending and Due <= today. After performing a task,
mark `Status: done` (or, for a recurring task, bump `Due` forward by the Recur
interval and leave Status: pending) — see /run-pipeline Step 0.

Usage:
    python scripts/due_tasks.py            # human-readable list of due tasks
    python scripts/due_tasks.py --all      # every task with computed state
    python scripts/due_tasks.py --json     # machine-readable due tasks
Exit code: 0 if any task is due, 1 if none (so callers can branch on it).
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".claude", "scheduled-tasks.md",
)

FIELD_RE = re.compile(r"^-\s*(Due|Status|Recur)\s*:\s*(.+?)\s*$", re.IGNORECASE)
# Trailing inline comment in a field value, e.g. "pending   # pending | done".
INLINE_COMMENT_RE = re.compile(r"\s+#.*$")


def parse_tasks(text):
    """Return a list of {title, due, status, recur, body, line} task dicts.

    Tasks are the `## ` headings BELOW the first `---` horizontal rule (the
    header/format docs sit above it). Lines inside ``` fenced code blocks are
    ignored so the format example doesn't get parsed as a real task.
    """
    tasks = []
    current = None
    started = False   # have we passed the first `---` rule?
    in_fence = False
    for lineno, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not started:
            if stripped == "---":
                started = True
            continue
        if raw.startswith("## "):
            if current:
                tasks.append(current)
            current = {
                "title": raw[3:].strip(),
                "due": None, "status": "pending", "recur": "none",
                "body": [], "line": lineno,
            }
            continue
        if current is None:
            continue
        m = FIELD_RE.match(stripped)
        if m:
            key = m.group(1).lower()
            val = INLINE_COMMENT_RE.sub("", m.group(2)).strip()
            current[key] = val
        else:
            current["body"].append(raw)
    if current:
        tasks.append(current)
    return tasks


def parse_due(val):
    if not val:
        return None
    try:
        return dt.date.fromisoformat(val.strip())
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--path", default=DEFAULT_PATH)
    ap.add_argument("--all", action="store_true", help="show every task, not just due")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    if not os.path.exists(args.path):
        print(f"No scheduled-tasks file at {args.path}", file=sys.stderr)
        return 1

    today = dt.date.today()
    with open(args.path) as f:
        tasks = parse_tasks(f.read())

    rows = []
    for t in tasks:
        due = parse_due(t["due"])
        status = (t["status"] or "pending").lower()
        is_due = status == "pending" and due is not None and due <= today
        rows.append({
            "title": t["title"],
            "due": t["due"],
            "status": status,
            "recur": t["recur"],
            "is_due": is_due,
            "malformed_due": due is None,
        })

    selected = rows if args.all else [r for r in rows if r["is_due"]]

    if args.json:
        print(json.dumps({"today": today.isoformat(), "tasks": selected}, indent=2))
    else:
        # Warn about unparseable Due dates so they never silently never-fire.
        bad = [r for r in rows if r["malformed_due"] and r["status"] == "pending"]
        for r in bad:
            print(f"  ⚠ task '{r['title']}' has missing/invalid Due: {r['due']!r}", file=sys.stderr)
        if not selected:
            print(f"No scheduled tasks due as of {today.isoformat()}.")
        else:
            label = "ALL TASKS" if args.all else "DUE TASKS"
            print(f"{label} (as of {today.isoformat()}): {len(selected)}")
            for r in selected:
                flag = "DUE" if r["is_due"] else r["status"].upper()
                print(f"  [{r['due']}] {flag:8} {r['title']}")

    any_due = any(r["is_due"] for r in rows)
    return 0 if any_due else 1


if __name__ == "__main__":
    sys.exit(main())
