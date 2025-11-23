"""
Event Export Script

This script exports processed events to JSON files for the website.
It creates two sets of files with different filtering criteria:
- init files: Core NYC area, 7-day window (for fast initial load)
- full files: Extended area, 90-day window (for comprehensive view)

Features:
- Date range filtering (removes past events, limits future events)
- Geographic filtering (NYC area with configurable bounds)
- Deduplication based on location, name similarity, and date
- Separate location files with unique venues
- Maintains relationship between events and locations via location_id

Configuration:
- Input: event_data/processed/YYYYMMDD/*.json
- Output: public_html/data/events.{init|full}.json, locations.{init|full}.json
"""

import os
import json
from datetime import datetime, timedelta

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def _is_event_in_date_range(event, current_date, future_limit_date):
    """
    Checks if any occurrence of an event falls within the desired date range.
    An event is included if at least one of its occurrences starts before the future limit
    and ends on or after the current date.
    """
    occurrences = event.get('occurrences', [])
    if not occurrences:
        return False

    for occ in occurrences:
        start_date_str = occ[0]
        end_date_str = occ[2] if occ[2] else start_date_str

        if not start_date_str:
            continue

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

            # Condition: The event's time window must overlap with our app's time window.
            # [event_start, event_end] must overlap with [today, future_limit]
            # This is true if event_start <= future_limit AND event_end >= today.
            if start_date <= future_limit_date and end_date >= current_date:
                return True # Found at least one valid occurrence, so include the whole event
        except (ValueError, TypeError):
            # Ignore malformed dates in occurrences
            continue

    return False # No occurrences for this event are within the date range

def _deduplicate_events(events):
    """
    Deduplicates events based on lat, lng, and first start date.
    Two events are considered duplicates if their normalized names are very similar
    (ignoring punctuation, underscores, and capitalization) and they share the same
    location and start date.
    Keeps the event with the shorter name (more concise) and, as a tiebreaker, the longest description.
    """
    import re
    from collections import defaultdict

    def normalize_name(name):
        """Remove punctuation, underscores, and whitespace; convert to lowercase for comparison."""
        # Remove underscores specifically (common in event titles)
        no_underscores = name.replace('_', '')
        # Remove all punctuation except spaces
        no_punct = re.sub(r'[^\w\s]', '', no_underscores.strip().lower())
        # Collapse multiple spaces into single space and strip
        normalized = re.sub(r'\s+', ' ', no_punct).strip()
        return normalized

    def are_names_similar(name1, name2):
        """
        Check if two event names are similar enough to be considered duplicates.
        Uses a more lenient approach that handles:
        - Different punctuation (e.g., "_in the space between_" vs "in the space between")
        - Prefix matching for festivals/series (e.g., "Broke People Play Festival: X" vs "X")
        """
        norm1 = normalize_name(name1)
        norm2 = normalize_name(name2)

        # Exact match after normalization
        if norm1 == norm2:
            return True

        # Check if one is a substring of the other (for prefix/suffix variations)
        # But require at least 5 characters to avoid false positives
        if len(norm1) >= 5 and len(norm2) >= 5:
            if norm1 in norm2 or norm2 in norm1:
                return True

        return False

    # Group events by (lat, lng, start_date) for efficient comparison
    grouped_events = defaultdict(list)

    for event in events:
        # Ensure the event has the necessary fields to create a key
        if not all(k in event for k in ['name', 'lat', 'lng']) or not event.get('occurrences'):
            continue

        # Use the start date of the first occurrence for grouping
        first_occurrence_start_date = event['occurrences'][0][0]
        key = (event['lat'], event['lng'], first_occurrence_start_date)
        grouped_events[key].append(event)

    unique_events = []

    # Process each group separately
    for key, group in grouped_events.items():
        if len(group) == 1:
            # No duplicates possible in this group
            unique_events.append(group[0])
            continue

        # Deduplicate within this group
        group_unique = []
        for event in group:
            # Check if this event is a duplicate of any existing event in this group
            is_duplicate = False
            for i, existing_event in enumerate(group_unique):
                # Check if names are similar enough to be considered duplicates
                if are_names_similar(event['name'], existing_event['name']):
                    is_duplicate = True

                    # Merge URLs from both events
                    event_urls = event.get('urls', [])
                    existing_urls = existing_event.get('urls', [])
                    merged_urls = list(existing_urls)  # Start with existing URLs
                    for url in event_urls:
                        if url and url not in merged_urls:
                            merged_urls.append(url)

                    # Keep the event with the shorter name (more concise)
                    # If names are the same length, keep the one with longer description
                    if (len(event['name']) < len(existing_event['name']) or
                        (len(event['name']) == len(existing_event['name']) and
                         len(event.get('description', '')) > len(existing_event.get('description', '')))):
                        event['urls'] = merged_urls
                        group_unique[i] = event
                    else:
                        existing_event['urls'] = merged_urls
                        group_unique[i] = existing_event
                    break

            if not is_duplicate:
                group_unique.append(event)

        unique_events.extend(group_unique)

    print(f"Deduplication complete. Went from {len(events)} to {len(unique_events)} events.")
    return unique_events

def main():
    processed_dir = os.path.join(SCRIPT_DIR, '..', 'event_data', 'processed')
    output_dir = os.path.join(SCRIPT_DIR, '..', 'public_html', 'data')

    # Output filenames for initial and full datasets
    events_init_filename = os.path.join(output_dir, 'events.init.json')
    locations_init_filename = os.path.join(output_dir, 'locations.init.json')
    events_full_filename = os.path.join(output_dir, 'events.full.json')
    locations_full_filename = os.path.join(output_dir, 'locations.full.json')

    source_locations_filename = os.path.join(SCRIPT_DIR, 'data', 'locations.json')

    # Bounding box for the "init" set (NYC area)
    # Centered around 40.71799, -73.98712
    # (lat_min, lat_max), (lng_min, lng_max)
    INIT_LAT_RANGE = (40.686695, 40.749285)
    INIT_LNG_RANGE = (-74.014855, -73.959385)
    INIT_DAYS_AHEAD = 7

    if not os.path.isdir(processed_dir) or not os.path.exists(source_locations_filename):
        print(f"Error: Directory '{processed_dir}' or file '{source_locations_filename}' not found.")
        return

    all_events = []
    current_date = datetime.now().date()
    future_limit_date = (datetime.now() + timedelta(days=90)).date()

    # Iterate through dated subdirectories
    for date_subdir in os.listdir(processed_dir):
        date_path = os.path.join(processed_dir, date_subdir)
        if not os.path.isdir(date_path):
            continue

        for filename in os.listdir(date_path):
            if filename.endswith(".json"):
                file_path = os.path.join(date_path, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        events = json.load(f)
                        for event in events:
                            has_lat = event.get('lat') is not None
                            has_lng = event.get('lng') is not None
                            if has_lat and has_lng and _is_event_in_date_range(event, current_date, future_limit_date):
                                # Normalize url field to urls list
                                if 'url' in event and 'urls' not in event:
                                    url = event.pop('url').strip()
                                    event['urls'] = [url] if url else []
                                elif 'urls' not in event:
                                    event['urls'] = []
                                all_events.append(event)
                except (json.JSONDecodeError, IOError) as e:
                    print(f"Warning: Could not process file '{filename}'. Error: {e}")

    # Deduplicate events before sorting and exporting
    deduplicated_events = _deduplicate_events(all_events)

    # Sort events by the start date of their first occurrence
    deduplicated_events.sort(key=lambda event: event.get('occurrences', [[None]])[0][0] or '9999-99-99')

    # --- Split events into "init" and "full" sets ---
    init_events = []
    full_events = []
    init_limit_date = (datetime.now() + timedelta(days=INIT_DAYS_AHEAD)).date()

    for event in deduplicated_events:
        # Check if event is within the bounding box for the "init" set
        lat = event.get('lat')
        lng = event.get('lng')
        is_in_bbox = (lat is not None and lng is not None and
                      INIT_LAT_RANGE[0] <= lat <= INIT_LAT_RANGE[1] and
                      INIT_LNG_RANGE[0] <= lng <= INIT_LNG_RANGE[1])

        # Check if the event starts within the "init" time window
        first_occurrence_start_str = event.get('occurrences', [[None]])[0][0]
        is_in_init_timeframe = False
        if first_occurrence_start_str:
            try:
                start_date = datetime.strptime(first_occurrence_start_str, '%Y-%m-%d').date()
                if start_date < init_limit_date:
                    is_in_init_timeframe = True
            except (ValueError, TypeError):
                pass # Ignore malformed dates

        if is_in_bbox and is_in_init_timeframe:
            init_events.append(event)
        else:
            full_events.append(event)

    # --- Create filtered lists of locations for both sets ---
    def get_active_locations(events, all_locs):
        active_coords = set(
            (round(event['lat'], 5), round(event['lng'], 5))
            for event in events if 'lat' in event and 'lng' in event
        )
        return [loc for loc in all_locs if loc.get('lat') is not None and loc.get('lng') is not None and
                (round(loc['lat'], 5), round(loc['lng'], 5)) in active_coords]

    # Load the source locations.json
    with open(source_locations_filename, 'r', encoding='utf-8') as f:
        all_locations = json.load(f)

    init_locations = get_active_locations(init_events, all_locations)

    # Create a set of coordinate pairs from the init_locations for efficient lookup.
    init_location_coords = set(
        (round(loc['lat'], 5), round(loc['lng'], 5)) for loc in init_locations
    )
    # Filter full_locations to exclude any locations already in the init set.
    full_locations = [loc for loc in get_active_locations(full_events, all_locations) if (round(loc['lat'], 5), round(loc['lng'], 5)) not in init_location_coords]

    os.makedirs(output_dir, exist_ok=True)
    with open(events_init_filename, 'w', encoding='utf-8') as f:
        json.dump(init_events, f, indent=2, ensure_ascii=False)
    with open(locations_init_filename, 'w', encoding='utf-8') as f:
        json.dump(init_locations, f, indent=2, ensure_ascii=False)
    with open(events_full_filename, 'w', encoding='utf-8') as f:
        json.dump(full_events, f, indent=2, ensure_ascii=False)
    with open(locations_full_filename, 'w', encoding='utf-8') as f:
        json.dump(full_locations, f, indent=2, ensure_ascii=False)

    print(f"Successfully exported {len(init_events)} initial events and {len(init_locations)} locations.")
    print(f"Successfully exported {len(full_events)} full events and {len(full_locations)} locations.")

if __name__ == "__main__":
    main()