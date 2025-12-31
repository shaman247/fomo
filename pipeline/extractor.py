"""
Event extraction module using Gemini AI.

Extracts structured event data from crawled website content.
"""

import asyncio
import os
from datetime import datetime

from dotenv import load_dotenv

import db

load_dotenv()

try:
    from google import genai
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
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


def extract_url_from_content(content):
    """Extract URL from first line of content if present."""
    if content and content.startswith('http'):
        first_newline = content.find('\n')
        if first_newline != -1:
            return content[:first_newline].strip(), content[first_newline + 1:]
    return None, content


def get_prompt(url, page_content, current_date_string, name, notes):
    """Generate the AI prompt for event extraction."""
    note_section = f"Note: {notes}" if notes else ""
    return f'''Today's date is {current_date_string}. We are assembling a database of upcoming events in New York City. To accomplish this, we are inspecting websites for details about upcoming events. Currently, we are looking at {name} ({url}). Based on the text content retrieved from the website {url}, please identify and list any upcoming events. If possible, include dates, times, locations, and descriptions (1-2 sentences) for each event. Format your output as a Markdown table with the following header:

  | name | location | sublocation | start_date | start_time | end_date | end_time | description | url | hashtags | emoji |

  Some pointers about these fields:

- "name" is the name of the event
- "location" is the name of the venue where the event is being held
- "sublocation" is optional and can be used to specify locations within the venue (e.g., rooftop, 5th floor, etc.)
- "start_date" is the date of the event in YYYY-MM-DD format.
- "start_time" is the time of the event (e.g., 4:00 PM)
- "end_date" and "end_time" are optional
- "description" should be 1-3 sentences.
- "url" should be a url for the specific event, if available. Otherwise, use {url}.
- "hashtags" are a set of 4-7 CamelCase tags to describe the event. Include a mix of high-level tags (e.g., #Comedy, #Music, #Outdoor) and more granular tags (e.g., #LatinJazz, #Ceramics, #Vegan). Avoid tags that reference a specific location or neighborhood, or that redundantly reference NYC (e.g., "#MusicNYC" should just be "#Music").
- "emoji" is a single emoji that describes the event.

Only include events that take place in the NYC area within the next 3 months. If the website content includes a section of unrelated events ("Hot Events", "Similar events", "Other events you may like", etc.), ignore those events.

Output rows for any events that are present in the content below, which has been retrieved from the website. If no events were successfully retrieved, output an empty header. Only include events that take place in the NYC area. If an event has multiple dates or times, output a separate row for each instance.

{note_section}

Here is the content:

 {page_content}'''


async def extract_events(cursor, connection, crawl_result_id, website_name, notes=""):
    """
    Extract events from crawled content using Gemini AI.

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

    current_date_string = datetime.now().strftime('%Y-%m-%d')

    # Extract URL from first line if present
    url, content_to_process = extract_url_from_content(page_content)
    url = url or ""

    print(f"    - Extracting events using {GEMINI_MODEL} ({len(content_to_process)} chars)...")

    try:
        prompt = get_prompt(url, content_to_process, current_date_string, website_name, notes)

        # Call Gemini API with timeout
        try:
            response = await asyncio.wait_for(
                genai_client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt
                ),
                timeout=GEMINI_TIMEOUT
            )
            response_text = response.text.strip()
        except asyncio.TimeoutError:
            print(f"    - Timeout after {GEMINI_TIMEOUT}s")
            raise Exception(f"Gemini API timeout after {GEMINI_TIMEOUT} seconds")

        # Handle empty responses
        if not response_text or not response_text.strip():
            response_text = '''| name | location | sublocation | start_date | start_time | end_date | end_time | description | url | hashtags | emoji |
|---|---|---|---|---|---|---|---|---|---|---|'''

        # Store extracted content in database
        db.update_crawl_result_extracted(cursor, connection, crawl_result_id, response_text)
        print(f"    - Extracted {len(response_text)} characters")
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
