"""Cross-session DB write serialization via MySQL advisory locks.

Multiple Claude Code sessions run against the SAME MariaDB. Concurrent writes to
shared tables (events, event_urls, event_occurrences, event_sources, crawl_*,
dedupe_dismissed_pairs) cause double-merges, FK races, and reads that see half of
another session's work. Reads are fine concurrently; only *writes* must serialize.

Usage — wrap any bulk-mutating section:

    import sys; sys.path.insert(0, 'pipeline')
    from db import create_connection
    from dblock import write_lock

    conn = create_connection()
    with write_lock(conn):          # blocks until no other session holds it
        ...                          # do all your INSERT/UPDATE/DELETE
        conn.commit()
    conn.close()

The lock is a MySQL named lock (GET_LOCK), scoped to the connection — it auto-
releases if the process dies or the connection drops, so a crashed session can't
wedge everyone else. Use ONE long-lived connection for the locked section.

`acquired_by()` reports which session/PID currently holds it, for diagnostics.
"""

import contextlib
import os
import socket

LOCK_NAME = "fomo_write"
DEFAULT_TIMEOUT = 600  # seconds to wait for the lock before giving up


def _holder_tag():
    """A human-readable tag for who is taking the lock (host:pid)."""
    return f"{socket.gethostname()}:{os.getpid()}"


@contextlib.contextmanager
def write_lock(conn, timeout=DEFAULT_TIMEOUT, name=LOCK_NAME, label=None):
    """Acquire the shared write lock for the duration of the block.

    Blocks up to `timeout` seconds. Raises TimeoutError if another session holds
    it longer than that (better to fail loudly than corrupt data by proceeding).
    """
    cur = conn.cursor()
    who = label or _holder_tag()
    cur.execute("SELECT GET_LOCK(%s, %s)", (name, timeout))
    got = cur.fetchone()[0]
    if got != 1:
        holder = acquired_by(conn, name)
        raise TimeoutError(
            f"Could not acquire DB write lock '{name}' within {timeout}s "
            f"(held by {holder or 'another session'}). Aborting to avoid a "
            f"concurrent-write conflict; retry when the other session is idle."
        )
    # Record who holds it so other sessions can see it in diagnostics.
    try:
        _set_holder(conn, name, who)
    except Exception:
        pass
    try:
        yield
    finally:
        try:
            _set_holder(conn, name, None)
        except Exception:
            pass
        rc = conn.cursor()
        rc.execute("SELECT RELEASE_LOCK(%s)", (name,))
        rc.fetchall()


def try_write_lock(conn, name=LOCK_NAME):
    """Non-blocking acquire. Returns True if acquired, False if already held.

    Caller is responsible for RELEASE via `release(conn)` on the SAME connection.
    """
    cur = conn.cursor()
    cur.execute("SELECT GET_LOCK(%s, 0)", (name,))
    return cur.fetchone()[0] == 1


def release(conn, name=LOCK_NAME):
    cur = conn.cursor()
    cur.execute("SELECT RELEASE_LOCK(%s)", (name,))
    cur.fetchall()


def is_locked(conn, name=LOCK_NAME):
    """True if ANY session currently holds the lock."""
    cur = conn.cursor()
    cur.execute("SELECT IS_USED_LOCK(%s)", (name,))
    return cur.fetchone()[0] is not None


# Holder tracking is best-effort metadata in a tiny table so `acquired_by` can
# report a useful name. The GET_LOCK itself is the source of truth for mutual
# exclusion; this is purely for diagnostics.
def _ensure_holder_table(conn):
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS db_write_lock_holder ("
        "  lock_name VARCHAR(64) PRIMARY KEY,"
        "  holder VARCHAR(128),"
        "  taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        ")"
    )
    conn.commit()


def _set_holder(conn, name, who):
    _ensure_holder_table(conn)
    cur = conn.cursor()
    if who is None:
        cur.execute("DELETE FROM db_write_lock_holder WHERE lock_name=%s", (name,))
    else:
        cur.execute(
            "INSERT INTO db_write_lock_holder (lock_name, holder) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE holder=VALUES(holder)",
            (name, who),
        )
    conn.commit()


def acquired_by(conn, name=LOCK_NAME):
    """Return the holder tag (host:pid) if the lock is held, else None."""
    if not is_locked(conn, name):
        return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT holder FROM db_write_lock_holder WHERE lock_name=%s", (name,))
        row = cur.fetchone()
        return row[0] if row else "unknown"
    except Exception:
        return "unknown"


if __name__ == "__main__":
    # `python pipeline/dblock.py status` — is another session writing right now?
    import sys
    from db import create_connection
    conn = create_connection()
    if is_locked(conn):
        print(f"LOCKED — held by {acquired_by(conn)}")
        sys.exit(1)
    print("free — no session is holding the write lock")
    conn.close()
