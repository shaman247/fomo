"""
Shared constants for the pipeline.

Centralizes magic numbers used across multiple pipeline modules
to prevent drift and improve discoverability.
"""

# How far into the future to include events (used by processor, merger, exporter)
FUTURE_WINDOW_DAYS = 90

# Default max pages for deep crawling (used by crawler, db)
MAX_PAGES_DEFAULT = 30

# Location matching thresholds (used by processor)
FUZZY_MATCH_THRESHOLD = 0.90       # Levenshtein ratio for fuzzy name matching
PREFIX_MATCH_COVERAGE = 0.70       # Minimum fraction of name covered by prefix match
