"""Example source plugin: a CUSTOM-mode plugin with its own Python fetch path.

Some sources can't be crawled with a browser (anti-bot walls, JS-only apps) but
expose a reachable API. A CUSTOM profile bypasses crawl4ai and calls a fetcher
you define here, returning markdown the extractor can parse.

This template sketches a generic JSON API. Copy to `<platform>.py` (gitignored),
point it at your source's endpoint, and format the response as markdown. The real
(working) plugin is gitignored.
"""
import json
import re
import urllib.request
from datetime import date, timedelta

from constants import get_user_agent
from site_profiles import SiteProfile, CrawlMode

API_URL = "https://api.example.com/events"


def _get_json(url, params):
    """Issue a GET and parse JSON. Adapt to POST/GraphQL/auth as your API needs."""
    query = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(
        f"{url}?{query}",
        headers={"User-Agent": get_user_agent(), "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_and_build_markdown(days=30):
    """CUSTOM fetcher contract: return (markdown_str, event_count).

    Fetch the source's events for the date window, then format each as markdown
    the extractor can chunk (e.g. '### [Title](url)' headers + dated fields).
    Return ("", 0) when there are no events.
    """
    date_from = date.today().isoformat()
    date_to = (date.today() + timedelta(days=days)).isoformat()
    data = _get_json(API_URL, {"from": date_from, "to": date_to})

    events = data.get("events", [])  # adapt to your API's response shape
    if not events:
        return "", 0

    parts = ["# Events", ""]
    for ev in events:
        title = ev.get("title", "(untitled)")
        url = ev.get("url", "")
        parts += [
            f"### [{title}]({url})",
            f"**Venue**: {ev.get('venue', '')}",
            f"**Date**: {(ev.get('date') or '')[:10]}",
            "",
        ]
    return "\n".join(parts) + "\n", len(events)


PROFILE = SiteProfile(
    name="custom_api",
    label="Custom API",
    # Matched against the URL hostname (lowercased).
    host_re=re.compile(r"^(www\.)?example\.com$", re.IGNORECASE),
    crawl_mode=CrawlMode.CUSTOM,
    fetcher=fetch_and_build_markdown,
)
