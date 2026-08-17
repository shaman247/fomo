"""
Shared constants for the pipeline.

Centralizes magic numbers used across multiple pipeline modules
to prevent drift and improve discoverability.
"""

import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

# Browser/HTTP User-Agent used for crawling and direct API/image fetches.
# Crawl4AI's default UA (Chrome on Linux) creates a UA/TLS fingerprint mismatch
# that some CDNs detect and 403, so we always send a realistic, current UA.
# Override per-deployment with the USER_AGENT env var.
# KEEP THE MAJOR VERSION IN SYNC WITH THE INSTALLED PLAYWRIGHT CHROMIUM:
# Cloudflare rejects UAs whose claimed major version lags the real browser
# fingerprint (observed on High Line w15, 2026-06-11: Chrome/131 and /143
# claims blocked while the bundled Chromium was 148). A recurring task in
# .claude/scheduled-tasks.md re-pins this after Playwright upgrades.
DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36'
)


def get_user_agent():
    """Return the configured User-Agent (USER_AGENT env var, else default)."""
    return os.environ.get('USER_AGENT') or DEFAULT_USER_AGENT


# How far into the future to include events (used by processor, merger, exporter)
FUTURE_WINDOW_DAYS = 90


def get_active_date_window():
    """Return (current_date, future_limit_date) for the active event window.

    Both dates derive from a single datetime.now() call so they can never
    straddle midnight relative to each other. Equivalent to the previous
    per-module `datetime.now().date()` / `(datetime.now() + timedelta(...)).date()`
    pair (adding whole days then truncating to date == truncating then adding).
    """
    now = datetime.now().date()
    return now, now + timedelta(days=FUTURE_WINDOW_DAYS)


# How long a content fingerprint may be reused before extraction is re-run, even
# though the page's bytes have not changed.
#
# Without a bound, a byte-stable page is extracted exactly ONCE, ever: every later
# crawl matches its `content_hash` and copies that first extraction verbatim. That
# is fine for the page's content but wrong for the DATE WINDOW, which slides. An
# event that sat beyond FUTURE_WINDOW_DAYS at the moment the hash was first cached
# was rejected then as `start_too_future`, and is never re-offered — so it is
# invisible forever, not merely late. Observed on w2813 Crown Hill: its November
# and December shows were on the page the whole time and never published.
#
# 30 days re-reads a frozen page ~monthly, so an event just outside the window is
# picked up with ~60 days of lead time. Cost is bounded and small: it only touches
# pages that never change, and only once a cycle.
#
# Distinct from the 2026-06-29 fingerprint fix, which stopped a BAD extraction
# being frozen. This is a CORRECT extraction going stale as the window moves.
FINGERPRINT_MAX_REUSE_DAYS = 30

# Substring stamped into `crawl_results.extracted_content` when a crawl COPIED a
# prior extraction instead of running one. Written by
# `extractor._apply_fingerprint_marker_and_status`, read by
# `db.find_prior_crawl_with_same_content`.
#
# It is what makes FINGERPRINT_MAX_REUSE_DAYS work at all. Reuse must chain to the
# crawl that was really EXTRACTED, never to another copy: every crawl writes a new
# row carrying the same content_hash and a fresh `crawled_at`, so "most recent twin"
# is always young and an age bound alone would never expire — the chain refreshes
# itself forever. Skipping copies makes the bound measure the age of the actual
# extraction, so a frozen page genuinely re-reads once per cycle.
FINGERPRINT_COPY_MARKER = '"skipped": "fingerprint match: cr-'

# How close together two `crawl_events` rows must be written to count as the same
# processing pass. `processor.process_events` writes a crawl_result's rows in one
# tight loop — 1,033 rows for w3 (cr-114466) took a single second — while a
# re-crawl of the same website inside one crawl run comes minutes or hours later
# and, before the replace fix, stacked its rows on the first pass's. Used by
# `db.copy_crawl_events` to copy only the newest pass out of a source written
# before that fix. Generous on purpose: the cost of being too wide is copying a
# stale pass we would have copied anyway.
CRAWL_EVENT_PASS_WINDOW_SECONDS = 300

# Default max pages for deep crawling (used by crawler, db)
MAX_PAGES_DEFAULT = 30

# Location matching thresholds (used by processor)
FUZZY_MATCH_THRESHOLD = 0.90       # Levenshtein ratio for fuzzy name matching
PREFIX_MATCH_COVERAGE = 0.70       # Minimum fraction of name covered by prefix match
