"""Helpers for reading a stored crawl body without crawl4ai.

`crawl_results.crawled_content` (and the `combined_markdown` the crawler
builds) is "<url>\\n<body>" per URL, and crawl4ai sometimes fences a raw JSON
body. Anything that wants the JSON document inside — the crawler's empty-feed
carve-out, a source plugin's payload check — unwraps it through here so the
unwrapping rule lives once. Kept free of crawl4ai imports so plugins can use it.
"""
import json
import re

URL_ONLY_LINE_RE = re.compile(r'^\s*https?://\S+\s*$')
CODE_FENCE_LINE_RE = re.compile(r'^\s*```[a-z]*\s*$', re.IGNORECASE)


def parse_json_body(content):
    """Unwrap a crawl body down to its JSON document, or None.

    Only objects and arrays are returned — a bare scalar ("null", "0", a
    quoted error string) is not a well-formed API response.
    """
    if not content:
        return None
    lines = [
        line for line in content.splitlines()
        if line.strip()
        and not URL_ONLY_LINE_RE.match(line)
        and not CODE_FENCE_LINE_RE.match(line)
    ]
    payload = '\n'.join(lines).strip()
    if not payload or payload[0] not in '{[':
        return None
    try:
        return json.loads(payload)
    except (ValueError, TypeError):
        return None
