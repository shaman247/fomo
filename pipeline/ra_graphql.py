"""
Query Resident Advisor's public GraphQL API for upcoming NYC events.

RA's HTML pages are blocked by DataDome (https://ra.co/events/us/newyorkcity → 403),
but the GraphQL endpoint at https://ra.co/graphql is reachable with a normal
Chrome User-Agent. This module provides the fetch + markdown-format functions
used by:
  - scripts/ra_to_pipeline.py (CLI one-off ingestion)
  - pipeline/crawler.py (regular periodic crawl integration)

NYC events live under areaId=8.
"""
import json
import re
import time
import urllib.request
from datetime import date, datetime, timedelta

GRAPHQL_URL = "https://ra.co/graphql"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
NYC_AREA_ID = 8

EVENTS_QUERY = """
query GET_EVENT_LISTINGS($filters: FilterInputDtoInput, $pageSize: Int, $page: Int) {
  eventListings(filters: $filters, pageSize: $pageSize, page: $page) {
    totalResults
    data {
      event {
        id
        title
        date
        startTime
        endTime
        cost
        content
        contentUrl
        minimumAge
        venue { id name address contentUrl }
        artists { name }
        promotionalLinks { url }
      }
    }
  }
}
""".strip()

# Match any ra.co URL — these all get routed to the GraphQL handler instead
# of going through crawl4ai (which hits DataDome). We currently only know
# how to query area-scoped event listings (NYC areaId=8 for w388). Per-venue
# RA URLs (e.g. /clubs/19281) aren't supported yet and will return empty
# markdown if matched.
_RA_URL_RE = re.compile(r'^https?://(www\.)?ra\.co/', re.IGNORECASE)


def is_ra_url(url: str | None) -> bool:
    return bool(url) and bool(_RA_URL_RE.match(url))


def _gql(query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "ra-content-language": "en",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_nyc_events(date_from: str, date_to: str, page_size: int = 100) -> list[dict]:
    """Paginate through eventListings until the full window is captured."""
    events: list[dict] = []
    page = 1
    while True:
        resp = _gql(EVENTS_QUERY, {
            "filters": {
                "areas": {"eq": NYC_AREA_ID},
                "listingDate": {"gte": date_from, "lte": date_to},
            },
            "pageSize": page_size,
            "page": page,
        })
        if "errors" in resp:
            print(f"  ! RA GraphQL errors on page {page}: {json.dumps(resp['errors'])[:300]}")
            break
        listings = resp["data"]["eventListings"]
        total = listings["totalResults"]
        batch = [item["event"] for item in listings["data"] if item.get("event")]
        events.extend(batch)
        print(f"    page {page}: +{len(batch)} (total {len(events)}/{total})")
        if len(events) >= total or not batch:
            break
        page += 1
        time.sleep(0.5)
    return events


def _fmt_time(iso: str | None) -> str:
    """Convert ISO datetime like '2026-05-27T19:30:00.000' to '7:30pm'."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "").split(".")[0])
    except Exception:
        return ""
    h = dt.hour
    m = dt.minute
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    if m:
        return f"{h12}:{m:02d}{suffix}"
    return f"{h12}{suffix}"


_MONTHS = ["", "January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]


def build_markdown(events: list[dict], date_from: str, date_to: str) -> str:
    """Format events as one markdown document.

    Matches the chunked-extraction pattern (`### [Title](url)` headers + 'View
    Event Details' anchors + month-name dates + unique URLs) so the extractor
    uses chunked mode rather than single-call mode.
    """
    parts: list[str] = []
    parts.append("# Resident Advisor — NYC events")
    parts.append("")
    parts.append(
        f"Pulled from ra.co GraphQL API for area 8 (New York City), "
        f"listingDate window {date_from} to {date_to}. "
        f"{len(events)} events returned."
    )
    parts.append("")
    parts.append(
        "Each section below is one event with structured fields (Venue, Date, "
        "Start, End, Cost, Min Age, Artists, URL). Use those exact fields — "
        "they are already validated against RA's database."
    )
    parts.append("")
    parts.append("---")
    parts.append("")

    for ev in events:
        title = (ev.get("title") or "").strip() or "(untitled event)"
        date_str = (ev.get("date") or "")[:10]
        try:
            y, m, d = date_str.split("-")
            date_human = f"{_MONTHS[int(m)]} {int(d)}, {y}"
        except Exception:
            date_human = date_str
        start_t = _fmt_time(ev.get("startTime"))
        end_t = _fmt_time(ev.get("endTime"))
        venue = ev.get("venue") or {}
        venue_name = (venue.get("name") or "").strip()
        venue_addr = (venue.get("address") or "").strip()
        cost = (ev.get("cost") or "").strip()
        min_age = ev.get("minimumAge")
        artists = ", ".join(a["name"] for a in (ev.get("artists") or []) if a.get("name"))
        content_url = ev.get("contentUrl") or ""
        url = f"https://ra.co{content_url}" if content_url else ""
        promo = (ev.get("promotionalLinks") or [{}])[0].get("url") or ""
        body = (ev.get("content") or "").strip()

        parts.append(f"### [{title}]({url})")
        parts.append("")
        if venue_name:
            line = f"**Venue**: {venue_name}"
            if venue_addr:
                line += f" — {venue_addr}"
            parts.append(line)
        parts.append(f"**Date**: {date_human}")
        if start_t:
            line = f"**Start**: {start_t}"
            if end_t and end_t != start_t:
                line += f" — **End**: {end_t}"
            parts.append(line)
        if cost:
            parts.append(f"**Cost**: {cost}")
        if min_age:
            parts.append(f"**Min Age**: {min_age}+")
        if artists:
            parts.append(f"**Artists**: {artists}")
        if promo:
            parts.append(f"**Tickets**: {promo}")
        if body:
            parts.append("")
            # 350-char snippet keeps the bundle under MySQL max_allowed_packet=1MB
            # at full 60-day windows (~1000 NYC events). Full text isn't needed —
            # title + venue + artists already carry the extraction signal.
            snippet = body[:350].rstrip()
            if len(body) > 350:
                snippet += "…"
            parts.append(snippet)
        parts.append("")
        parts.append(f"[View Event Details]({url})")
        parts.append("")
        parts.append("---")
        parts.append("")

    return "\n".join(parts) + "\n"


def fetch_and_build_markdown(days: int = 30, page_size: int = 100) -> tuple[str, int]:
    """Fetch + format in one call. Returns (markdown, event_count)."""
    date_from = date.today().isoformat()
    date_to = (date.today() + timedelta(days=days)).isoformat()
    print(f"  RA GraphQL: fetching NYC events {date_from} → {date_to}")
    events = fetch_nyc_events(date_from, date_to, page_size=page_size)
    if not events:
        return "", 0
    md = build_markdown(events, date_from, date_to)
    print(f"  RA GraphQL: {len(events)} events, {len(md)} bytes of markdown")
    return md, len(events)
