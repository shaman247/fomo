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

# Default max pages for deep crawling (used by crawler, db)
MAX_PAGES_DEFAULT = 30

# Location matching thresholds (used by processor)
FUZZY_MATCH_THRESHOLD = 0.90       # Levenshtein ratio for fuzzy name matching
PREFIX_MATCH_COVERAGE = 0.70       # Minimum fraction of name covered by prefix match
