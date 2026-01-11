#!/usr/bin/env python3
"""Parse Met Museum events from MHTML file and insert into database."""

import re
import sys
import os
from datetime import datetime

# Add pipeline directory to path for db module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pipeline'))

def parse_met_mhtml(filepath):
    """Extract events from Met Museum MHTML file."""

    # Read the mhtml file
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Decode quoted-printable encoding
    content = content.replace("=\n", "")  # Line continuations
    content = re.sub(r"=([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), content)
    content = content.replace("=3D", "=")

    events = []

    # Find date headers like "Sunday, January 11"
    date_pattern = r'class="events-and-tours-app_date__mnAac">((?:Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday), (?:January|February|March|April|May|June|July|August|September|October|November|December) \d+)</h3>'

    # Find all date sections
    date_matches = list(re.finditer(date_pattern, content))

    for i, match in enumerate(date_matches):
        date_str = match.group(1)
        start_pos = match.end()
        end_pos = date_matches[i + 1].start() if i + 1 < len(date_matches) else len(content)

        section = content[start_pos:end_pos]

        # Parse date
        # e.g., "Sunday, January 11" -> "2026-01-11"
        parts = date_str.replace(",", "").split()
        day_name, month_name, day = parts[0], parts[1], parts[2]

        month_map = {
            "January": 1, "February": 2, "March": 3, "April": 4,
            "May": 5, "June": 6, "July": 7, "August": 8,
            "September": 9, "October": 10, "November": 11, "December": 12
        }
        month = month_map.get(month_name, 1)
        year = 2026  # From the MHTML date header

        try:
            event_date = datetime(year, month, int(day)).strftime("%Y-%m-%d")
        except:
            continue

        # Find event cards in this section
        # Title pattern
        title_matches = re.finditer(
            r'class="event-card_title__pXwvu"><a[^>]+href="([^"]+)"[^>]*><span[^>]*>([^<]+)</span>',
            section
        )

        for title_match in title_matches:
            url = title_match.group(1)
            name = title_match.group(2).strip()

            # Find time near this title (search backwards and forwards)
            pos = title_match.start()
            nearby = section[max(0, pos-2000):pos+2000]

            time_match = re.search(r'<span>(\d{1,2}:\d{2} [AP]M)</span>', nearby)
            time_str = time_match.group(1).lower().replace(" ", "") if time_match else None

            # Find location
            loc_match = re.search(r'<span>(The Met (?:Fifth Avenue|Cloisters)[^<]*)</span>', nearby)
            location = loc_match.group(1) if loc_match else "The Met Fifth Avenue"

            events.append({
                "name": name,
                "date": event_date,
                "time": time_str,
                "location": location,
                "url": url
            })

    return events


def insert_met_events(events, dry_run=True):
    """Insert Met events into database."""
    import mysql.connector

    # Website IDs for Met
    MET_FIFTH_AVENUE_ID = 114  # The Metropolitan Museum of Art
    MET_CLOISTERS_ID = 115     # The Met Cloisters

    # Location IDs (look these up or create them)
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="fomo"
    )
    cursor = conn.cursor(dictionary=True)

    # Get or create location IDs
    cursor.execute("SELECT id, name FROM locations WHERE name LIKE '%Metropolitan%' OR name LIKE '%Met Cloisters%'")
    locations = {row["name"]: row["id"] for row in cursor.fetchall()}

    met_fifth_loc_id = None
    met_cloisters_loc_id = None

    for name, loc_id in locations.items():
        if "Cloisters" in name:
            met_cloisters_loc_id = loc_id
        elif "Metropolitan" in name:
            met_fifth_loc_id = loc_id

    print(f"Met Fifth Avenue location_id: {met_fifth_loc_id}")
    print(f"Met Cloisters location_id: {met_cloisters_loc_id}")

    inserted = 0
    skipped = 0

    for event in events:
        # Determine website and location based on event location
        if "Cloisters" in event["location"]:
            website_id = MET_CLOISTERS_ID
            location_id = met_cloisters_loc_id
        else:
            website_id = MET_FIFTH_AVENUE_ID
            location_id = met_fifth_loc_id

        # Check if event already exists (by name and date)
        cursor.execute("""
            SELECT e.id FROM events e
            JOIN event_occurrences eo ON e.id = eo.event_id
            WHERE e.name = %s AND eo.start_date = %s
            LIMIT 1
        """, (event["name"], event["date"]))

        if cursor.fetchone():
            skipped += 1
            continue

        if dry_run:
            print(f"Would insert: {event['date']} {event['time'] or 'tba':8} | {event['name'][:50]}")
            inserted += 1
            continue

        # Insert event
        cursor.execute("""
            INSERT INTO events (name, location_id, location_name, website_id)
            VALUES (%s, %s, %s, %s)
        """, (event["name"], location_id, event["location"], website_id))
        event_id = cursor.lastrowid

        # Insert occurrence
        cursor.execute("""
            INSERT INTO event_occurrences (event_id, start_date, start_time)
            VALUES (%s, %s, %s)
        """, (event_id, event["date"], event["time"]))

        # Insert URL
        if event["url"]:
            cursor.execute("""
                INSERT INTO event_urls (event_id, url)
                VALUES (%s, %s)
            """, (event_id, event["url"]))

        inserted += 1

    if not dry_run:
        conn.commit()

    cursor.close()
    conn.close()

    return inserted, skipped


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse Met Museum events from MHTML file")
    parser.add_argument("--file", default="/Applications/XAMPP/xamppfiles/htdocs/fomo/public_html/The Metropolitan Museum of Art.mhtml",
                        help="Path to MHTML file")
    parser.add_argument("--insert", action="store_true", help="Actually insert events (default is dry run)")
    parser.add_argument("--preview", action="store_true", help="Preview extracted events")

    args = parser.parse_args()

    events = parse_met_mhtml(args.file)
    print(f"Extracted {len(events)} events from MHTML\n")

    if args.preview:
        # Group by date
        from collections import defaultdict
        by_date = defaultdict(list)
        for e in events:
            by_date[e["date"]].append(e)

        for date in sorted(by_date.keys())[:10]:
            print(f"\n=== {date} ===")
            for e in by_date[date]:
                time_str = e["time"] or "tba"
                print(f"  {time_str:8} | {e['name'][:60]}")
                print(f"           @ {e['location']}")
    else:
        dry_run = not args.insert
        if dry_run:
            print("DRY RUN - use --insert to actually insert events\n")

        inserted, skipped = insert_met_events(events, dry_run=dry_run)
        print(f"\n{'Would insert' if dry_run else 'Inserted'}: {inserted} events")
        print(f"Skipped (already exist): {skipped} events")
