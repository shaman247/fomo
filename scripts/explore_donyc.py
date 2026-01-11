#!/usr/bin/env python3
"""Explore DoNYC to find venues and events we might be missing."""

import asyncio
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode


async def crawl_page(url):
    """Crawl a single page and return markdown content."""
    browser_config = BrowserConfig(headless=True, java_script_enabled=True)
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        delay_before_return_html=5,
        remove_overlay_elements=False,
        scan_full_page=True,
        page_timeout=60000,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=config)
        if result and result.markdown:
            return result.markdown.raw_markdown or ""
        return ""


def extract_venues_from_events(content):
    """Extract venue names and slugs from DoNYC events content."""
    # Pattern: [Venue Name](https://donyc.com/venues/venue-slug)
    venue_pattern = r'\[([^\]]+)\]\(https://donyc\.com/venues/([a-z0-9-]+)\)'
    matches = re.findall(venue_pattern, content)

    # Deduplicate and clean
    venues = {}
    for name, slug in matches:
        if name and len(name) > 2 and not name.startswith("!"):
            # Clean up name
            name = name.strip()
            if slug not in venues:
                venues[slug] = name

    return venues


def extract_events_from_content(content):
    """Extract event info from DoNYC content."""
    events = []

    # Pattern for event blocks - look for event title links followed by venue
    # Example: [ Event Name ](https://donyc.com/events/...) \n [Venue](https://donyc.com/venues/...)
    event_pattern = r'\[\s*([^\]]+?)\s*\]\(https://donyc\.com/events/(\d+/\d+/\d+/[^\)]+)\).*?\[([^\]]+)\]\(https://donyc\.com/venues/([a-z0-9-]+)\)'

    for match in re.finditer(event_pattern, content, re.DOTALL):
        event_name = match.group(1).strip()
        event_slug = match.group(2)
        venue_name = match.group(3).strip()
        venue_slug = match.group(4)

        if event_name and venue_name and len(event_name) > 3:
            events.append({
                "event": event_name,
                "event_url": f"https://donyc.com/events/{event_slug}",
                "venue": venue_name,
                "venue_slug": venue_slug,
                "venue_url": f"https://donyc.com/venues/{venue_slug}"
            })

    return events


async def get_venue_details(slug):
    """Get details for a specific venue from DoNYC."""
    url = f"https://donyc.com/venues/{slug}"
    content = await crawl_page(url)

    details = {"slug": slug, "url": url}

    # Extract address
    addr_match = re.search(r'(\d+[^,\n]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Way|Place|Pl)[^,\n]*,\s*(?:New York|Brooklyn|Queens|Bronx|Staten Island)[^,\n]*,\s*NY\s*\d{5})', content, re.IGNORECASE)
    if addr_match:
        details["address"] = addr_match.group(1).strip()

    # Extract website link
    website_match = re.search(r'\[(?:Website|Official Site|Visit Website)\]\((https?://[^\)]+)\)', content, re.IGNORECASE)
    if website_match:
        details["website"] = website_match.group(1)

    return details


async def main():
    import mysql.connector

    # Get our existing locations and websites
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="fomo"
    )
    cursor = conn.cursor(dictionary=True)

    # Get existing locations (including alternate names)
    cursor.execute("""
        SELECT l.id, l.name, LOWER(l.name) as lower_name
        FROM locations l
        UNION
        SELECT l.id, lan.alternate_name as name, LOWER(lan.alternate_name) as lower_name
        FROM locations l
        JOIN location_alternate_names lan ON l.id = lan.location_id
    """)
    our_locations = {}
    for row in cursor.fetchall():
        our_locations[row["lower_name"]] = row

    # Get existing websites
    cursor.execute("SELECT id, name, LOWER(name) as lower_name, base_url FROM websites")
    our_websites = {}
    for row in cursor.fetchall():
        our_websites[row["lower_name"]] = row

    print(f"We have {len(our_locations)} locations (incl. alt names) and {len(our_websites)} websites\n")

    # Crawl DoNYC events for multiple days
    print("Crawling DoNYC events...")
    pages = [
        "https://donyc.com/events/today",
        "https://donyc.com/events/tomorrow",
        "https://donyc.com/events/music/today",
        "https://donyc.com/events/comedy/today",
        "https://donyc.com/events/theatre-art-design/today",
    ]

    all_content = ""
    for page in pages:
        content = await crawl_page(page)
        all_content += "\n" + content

    # Extract venues
    venues = extract_venues_from_events(all_content)
    print(f"Found {len(venues)} unique venues on DoNYC\n")

    # Skip generic/virtual venues
    skip_slugs = {
        "dostuffathome", "virtual-music-festival", "virtual-social-justice",
        "brooklyn-various", "manhattan-various", "queens-various",
        "the-bronx-various", "staten-island-various", "new-york-various",
        "online", "virtual", "tba"
    }

    # Check which venues we're missing
    missing_venues = []
    for slug, name in venues.items():
        if slug in skip_slugs:
            continue

        name_lower = name.lower()

        # Check if we have this venue (fuzzy match)
        found = False

        # Direct match in locations
        if name_lower in our_locations:
            found = True

        # Partial match
        if not found:
            for our_name in our_locations.keys():
                # Check both directions
                if len(our_name) > 4 and len(name_lower) > 4:
                    if our_name in name_lower or name_lower in our_name:
                        found = True
                        break

        # Also check websites
        if not found:
            if name_lower in our_websites:
                found = True
            else:
                for our_name in our_websites.keys():
                    if len(our_name) > 4 and len(name_lower) > 4:
                        if our_name in name_lower or name_lower in our_name:
                            found = True
                            break

        if not found:
            missing_venues.append((name, slug))

    print(f"=== Potentially Missing Venues ({len(missing_venues)}) ===\n")

    # Get details for missing venues
    for name, slug in sorted(missing_venues):
        print(f"  {name}")
        print(f"    DoNYC: https://donyc.com/venues/{slug}")

        # Get venue details
        details = await get_venue_details(slug)
        if details.get("address"):
            print(f"    Address: {details['address']}")
        if details.get("website"):
            print(f"    Website: {details['website']}")
        print()

    # Extract and show events
    events = extract_events_from_content(all_content)
    print(f"\n=== Sample Events from DoNYC ({len(events)} total) ===")
    for e in events[:15]:
        print(f"  {e['event'][:60]}")
        print(f"    @ {e['venue']}")
        print()

    cursor.close()
    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
