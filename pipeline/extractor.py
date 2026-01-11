"""
Event extraction module using Gemini AI with Structured Outputs.

Extracts structured event data from crawled website content using JSON schema.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

import db

load_dotenv()

try:
    from google import genai
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-preview-05-20")
    GEMINI_TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT", "120"))
    if GEMINI_API_KEY:
        genai_client = genai.Client(api_key=GEMINI_API_KEY)
    else:
        genai_client = None
except ImportError:
    print("Warning: google-genai not installed. Extraction will be skipped.")
    genai = None
    genai_client = None
    GEMINI_API_KEY = None
    GEMINI_MODEL = None
    GEMINI_TIMEOUT = 120


# =============================================================================
# Pydantic Schema for Structured Output
# =============================================================================

class EventOccurrence(BaseModel):
    """Schema for a single occurrence (date/time) of an event."""
    start_date: str = Field(description="The date of this occurrence in YYYY-MM-DD format")
    start_time: Optional[str] = Field(
        default=None,
        description="The start time (e.g., 4:00 PM)"
    )
    end_date: Optional[str] = Field(
        default=None,
        description="The end date if different from start_date, in YYYY-MM-DD format"
    )
    end_time: Optional[str] = Field(
        default=None,
        description="The end time (e.g., 7:00 PM)"
    )


class Event(BaseModel):
    """Schema for a single event extracted from website content."""
    name: str = Field(description="The name of the event")
    location: str = Field(description="The name of the venue where the event is being held")
    sublocation: Optional[str] = Field(
        default=None,
        description="Optional location within the venue (e.g., rooftop, 5th floor)"
    )
    occurrences: list[EventOccurrence] = Field(
        description="List of date/time occurrences for this event. Include ALL specific dates if the event repeats."
    )
    description: str = Field(description="A 1-3 sentence description of the event")
    url: Optional[str] = Field(
        default=None,
        description="URL for the specific event, if available"
    )
    hashtags: list[str] = Field(
        description="4-7 CamelCase tags describing the event (e.g., Comedy, LatinJazz, Outdoor)"
    )
    emoji: str = Field(description="A single emoji that represents the event")


class EventList(BaseModel):
    """Schema for a list of events extracted from website content."""
    events: list[Event] = Field(
        default_factory=list,
        description="List of upcoming events found in the content"
    )


# =============================================================================
# Constants
# =============================================================================

# Minimum content size (in bytes) required for extraction.
# Crawls with less content than this are likely failed crawls (e.g., JS-rendered
# pages that didn't load) and would cause the LLM to hallucinate events.
MIN_CONTENT_SIZE = 500


# =============================================================================
# Extraction Functions
# =============================================================================

def extract_url_from_content(content):
    """Extract URL from first line of content if present."""
    if content and content.startswith('http'):
        first_newline = content.find('\n')
        if first_newline != -1:
            return content[:first_newline].strip(), content[first_newline + 1:]
    return None, content


def get_prompt(url, page_content, current_date_string, name, notes, existing_events=None):
    """Generate the AI prompt for event extraction."""
    note_section = f"\n\nNote: {notes}" if notes else ""

    # Format existing events as JSON for prompt
    existing_events_section = ""
    if existing_events:
        existing_events_json = json.dumps(existing_events, indent=2)
        existing_events_section = f"""
EXISTING EVENTS IN DATABASE:
The following upcoming events from this website are already in our database. If you see these events in the new content and the details are still accurate, you may return them with details unchanged. This ensures consistency across crawls. Only create a new event if it's genuinely different, or update the event if key details have changed:

{existing_events_json}

"""

    return f'''Today's date is {current_date_string}. We are assembling a database of upcoming events in New York City. Currently, we are inspecting {name} ({url}).
{existing_events_section}
Based on the website content below, extract all upcoming events. For each event, provide:
- name: The event name
- location: The venue name
- sublocation: Optional location within the venue (rooftop, 5th floor, etc.)
- occurrences: An array of date/time objects. IMPORTANT: For recurring events (e.g., "every Wednesday" or "Jan 11, 18, 25"), list EACH specific date as a separate occurrence within the next 3 months. Each occurrence has:
  - start_date: Date in YYYY-MM-DD format
  - start_time: Time like "4:00 PM" (optional)
  - end_date: End date if different from start (optional)
  - end_time: End time (optional)
- description: 1-3 sentence description
- url: Specific event URL if available
- hashtags: 4-7 CamelCase tags (e.g., ["Comedy", "Music", "Outdoor", "LatinJazz"]). Include a mix of high-level and granular tags. Avoid location-specific or NYC-redundant tags.
- emoji: A single emoji representing the event

Rules:
- Only include events in the NYC area within the next 3 months
- Ignore unrelated event sections ("Hot Events", "Similar events", etc.)
- For recurring events, expand ALL individual dates into the occurrences array
- For consistency, if an event matches one in EXISTING EVENTS above, use the same details to avoid creating duplicates
- If no events are found, return an empty events list{note_section}

Website content:

{page_content}'''


async def extract_events(cursor, connection, crawl_result_id, website_name, notes=""):
    """
    Extract events from crawled content using Gemini AI with structured outputs.

    Args:
        cursor: Database cursor
        connection: Database connection
        crawl_result_id: ID of the crawl result
        website_name: Name of the website
        notes: Optional notes for the AI prompt

    Returns:
        True if successful, False otherwise
    """
    if not GEMINI_API_KEY or not genai_client:
        print("    - Skipping extraction: Gemini API not configured")
        return False

    # Get crawled content from database
    page_content = db.get_crawled_content(cursor, crawl_result_id)
    if not page_content:
        print("    - No crawled content found")
        return False

    # Check for minimum content size to prevent hallucinations
    # When crawled content is too small (e.g., just a URL), the LLM will
    # hallucinate plausible-sounding events based on the venue name
    content_size = len(page_content)
    if content_size < MIN_CONTENT_SIZE:
        error_msg = f"Crawled content too small ({content_size} bytes < {MIN_CONTENT_SIZE} minimum) - likely failed crawl, skipping to prevent hallucinations"
        print(f"    - {error_msg}")
        db.update_crawl_result_failed(cursor, connection, crawl_result_id, error_msg)
        return False

    # Get website_id for this crawl result
    cursor.execute(
        "SELECT website_id FROM crawl_results WHERE id = %s",
        (crawl_result_id,)
    )
    result = cursor.fetchone()
    website_id = result[0] if result else None

    # Get existing upcoming events from this website
    existing_events = []
    if website_id:
        existing_events = db.get_existing_upcoming_events(cursor, website_id)
        if existing_events:
            print(f"    - Found {len(existing_events)} existing upcoming events to include in prompt")

    current_date_string = datetime.now().strftime('%Y-%m-%d')

    # Extract URL from first line if present
    url, content_to_process = extract_url_from_content(page_content)
    url = url or ""

    print(f"    - Extracting events using {GEMINI_MODEL} ({len(content_to_process)} chars)...")

    try:
        prompt = get_prompt(url, content_to_process, current_date_string, website_name, notes, existing_events)

        # Call Gemini API with structured output
        try:
            response = await asyncio.wait_for(
                genai_client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": EventList,
                    }
                ),
                timeout=GEMINI_TIMEOUT
            )
            response_text = response.text.strip()
        except asyncio.TimeoutError:
            print(f"    - Timeout after {GEMINI_TIMEOUT}s")
            raise Exception(f"Gemini API timeout after {GEMINI_TIMEOUT} seconds")

        # Handle empty responses
        if not response_text or not response_text.strip():
            response_text = '{"events": []}'

        # Validate JSON
        try:
            parsed = json.loads(response_text)
            event_count = len(parsed.get('events', []))
            occurrence_count = sum(
                len(e.get('occurrences', [])) for e in parsed.get('events', [])
            )
        except json.JSONDecodeError:
            # If somehow invalid JSON, wrap in empty structure
            response_text = '{"events": []}'
            event_count = 0
            occurrence_count = 0

        # Store extracted content in database
        db.update_crawl_result_extracted(cursor, connection, crawl_result_id, response_text)
        print(f"    - Extracted {event_count} events with {occurrence_count} occurrences")
        return True

    except Exception as e:
        error_msg = str(e)
        print(f"    - Extraction error: {error_msg}")
        db.update_crawl_result_failed(
            cursor, connection, crawl_result_id, f"Extraction failed: {error_msg}"
        )
        return False


def is_available():
    """Check if Gemini API is available."""
    return GEMINI_API_KEY is not None and genai_client is not None
