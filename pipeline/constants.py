"""
Shared constants for the pipeline.

Centralizes magic numbers used across multiple pipeline modules
to prevent drift and improve discoverability.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# Browser/HTTP User-Agent used for crawling and direct API/image fetches.
# Crawl4AI's default UA (Chrome on Linux) creates a UA/TLS fingerprint mismatch
# that some CDNs detect and 403, so we always send a realistic, current UA.
# Override per-deployment with the USER_AGENT env var.
DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
)


def get_user_agent():
    """Return the configured User-Agent (USER_AGENT env var, else default)."""
    return os.environ.get('USER_AGENT') or DEFAULT_USER_AGENT


# How far into the future to include events (used by processor, merger, exporter)
FUTURE_WINDOW_DAYS = 90

# Default max pages for deep crawling (used by crawler, db)
MAX_PAGES_DEFAULT = 30

# Location matching thresholds (used by processor)
FUZZY_MATCH_THRESHOLD = 0.90       # Levenshtein ratio for fuzzy name matching
PREFIX_MATCH_COVERAGE = 0.70       # Minimum fraction of name covered by prefix match
