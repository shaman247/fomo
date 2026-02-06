"""
Event extraction module using Gemini AI with Structured Outputs.

Extracts structured event data from crawled website content using JSON schema.
Uses a two-pass approach for large pages (>50 expected events):
1. First pass: Extract core data (name, location, dates, url) with simplified schema
2. Second pass: Enrich events with descriptions, hashtags, and emoji in batches
"""

import asyncio
import base64
import json
import os
import re
from datetime import datetime
from io import BytesIO
from typing import Optional
from urllib.parse import urljoin

import httpx
from dotenv import load_dotenv
from PIL import Image
from pydantic import BaseModel, Field

import db
from processor import extract_url_from_content

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
# Simplified Schema for Large Pages (First Pass)
# =============================================================================

class SimpleOccurrence(BaseModel):
    """Simplified occurrence schema for first-pass extraction."""
    start_date: str = Field(description="YYYY-MM-DD format")
    start_time: Optional[str] = Field(default=None, description="e.g. 8:00 PM")
    end_time: Optional[str] = Field(default=None)


class SimpleEvent(BaseModel):
    """Simplified event schema for first-pass extraction on large pages."""
    name: str
    location: str
    occurrences: list[SimpleOccurrence]
    url: Optional[str] = None


class SimpleEventList(BaseModel):
    """Simplified event list for first-pass extraction."""
    events: list[SimpleEvent] = Field(default_factory=list)


# =============================================================================
# Enrichment Schema (Second Pass)
# =============================================================================

class EventEnrichment(BaseModel):
    """Schema for enrichment data added in second pass."""
    name: str = Field(description="The event name (must match exactly)")
    description: str = Field(description="1-3 sentence description")
    hashtags: list[str] = Field(description="4-7 CamelCase tags")
    emoji: str = Field(description="Single emoji")


class EnrichmentBatch(BaseModel):
    """Batch of enrichments as a list."""
    enrichments: list[EventEnrichment] = Field(
        description="List of enrichment data for each event"
    )


# =============================================================================
# Constants
# =============================================================================

# Minimum content size (in bytes) required for extraction.
# Crawls with less content than this are likely failed crawls (e.g., JS-rendered
# pages that didn't load) and would cause the LLM to hallucinate events.
MIN_CONTENT_SIZE = 500

# Threshold for switching to chunked extraction
# Pages with more expected events than this will be split into chunks
LARGE_PAGE_THRESHOLD = 50

# Number of events per chunk for chunked extraction
EVENTS_PER_CHUNK = 50

# Batch size for enrichment (second pass)
ENRICHMENT_BATCH_SIZE = 30

# Timeout per chunk (seconds) - increased for large pages that can't be chunked
CHUNK_TIMEOUT = 300

# Maximum characters per chunk when falling back to character-based chunking
MAX_CHUNK_CHARS = 30000

# Maximum number of images to process for vision extraction
MAX_VISION_IMAGES = 10

# Maximum image dimension (images will be resized if larger)
MAX_IMAGE_DIMENSION = 1024


# =============================================================================
# Vision Processing Functions
# =============================================================================

def extract_image_urls(content, base_url=None):
    """
    Extract image URLs from markdown content.

    Looks for markdown image syntax: ![alt](url)
    Returns a list of absolute URLs.
    """
    # Match markdown image syntax
    pattern = r'!\[[^\]]*\]\(([^)]+)\)'
    urls = re.findall(pattern, content)

    # Filter and normalize URLs
    result = []
    for url in urls:
        # Skip data URLs
        if url.startswith('data:'):
            continue
        # Skip tiny images (likely icons/buttons)
        if 'icon' in url.lower() or 'button' in url.lower() or 'logo' in url.lower():
            continue
        # Make absolute if relative
        if base_url and not url.startswith(('http://', 'https://')):
            url = urljoin(base_url, url)
        if url.startswith(('http://', 'https://')):
            result.append(url)

    return result


async def download_and_encode_image(url, max_dimension=MAX_IMAGE_DIMENSION):
    """
    Download an image and encode it as base64.

    Resizes large images to reduce token usage.
    Returns tuple of (base64_data, mime_type) or (None, None) on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, follow_redirects=True)
            if response.status_code != 200:
                return None, None

            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                return None, None

            # Determine MIME type
            if 'jpeg' in content_type or 'jpg' in content_type:
                mime_type = 'image/jpeg'
            elif 'png' in content_type:
                mime_type = 'image/png'
            elif 'gif' in content_type:
                mime_type = 'image/gif'
            elif 'webp' in content_type:
                mime_type = 'image/webp'
            else:
                # Try to detect from content
                mime_type = 'image/jpeg'  # Default

            # Load and resize image if needed
            img_data = response.content
            try:
                img = Image.open(BytesIO(img_data))

                # Convert to RGB if necessary (for JPEG output)
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                    mime_type = 'image/jpeg'

                # Resize if too large
                if max(img.size) > max_dimension:
                    ratio = max_dimension / max(img.size)
                    new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)

                # Encode to bytes
                buffer = BytesIO()
                if mime_type == 'image/png':
                    img.save(buffer, format='PNG', optimize=True)
                else:
                    img.save(buffer, format='JPEG', quality=85)
                img_data = buffer.getvalue()
            except Exception:
                # If PIL fails, use original data
                pass

            # Encode to base64
            b64_data = base64.standard_b64encode(img_data).decode('utf-8')
            return b64_data, mime_type

    except Exception as e:
        return None, None


async def prepare_vision_content(content, base_url=None, max_images=MAX_VISION_IMAGES):
    """
    Prepare multimodal content with images for Gemini vision API.

    Returns a list of content parts (text and images) for the API call.
    """
    # Extract image URLs
    image_urls = extract_image_urls(content, base_url)

    if not image_urls:
        return None, 0

    # Limit number of images
    image_urls = image_urls[:max_images]

    # Download and encode images concurrently
    tasks = [download_and_encode_image(url) for url in image_urls]
    results = await asyncio.gather(*tasks)

    # Build content parts
    image_parts = []
    for (b64_data, mime_type) in results:
        if b64_data and mime_type:
            image_parts.append({
                'inline_data': {
                    'mime_type': mime_type,
                    'data': b64_data
                }
            })

    return image_parts, len(image_parts)


def get_vision_prompt(url, text_content, current_date_string, name, notes):
    """Generate a prompt for vision-based event extraction."""
    note_section = f"\n\nIMPORTANT: {notes}" if notes else ""

    return f'''Today's date is {current_date_string}. We are extracting events from {name} ({url}).

I'm showing you images from this venue's events page. These images are event flyers/posters that contain event information.

For EACH event flyer/image, extract:
- name: The event name shown in the image
- location: The venue name (default to "{name}" if not specified)
- occurrences: Array of dates/times. Look for dates in the images (e.g., "January 16, 2026" or "Jan 16 - Feb 14"). Each occurrence has:
  - start_date: Date in YYYY-MM-DD format
  - start_time: Time if shown (e.g., "6:00 PM")
  - end_date: End date if this is a multi-day event/exhibition
  - end_time: End time if shown
- description: Brief description of the event based on what you see
- url: Leave as null unless shown in image
- hashtags: 4-7 relevant CamelCase tags (e.g., ["Art", "Exhibition", "Contemporary"])
- emoji: A single emoji representing the event
{note_section}
Rules:
- Extract events from ALL the flyer images provided
- Only include events that appear to be upcoming (after {current_date_string})
- For art exhibitions, the start_date is opening day and end_date is closing day
- If you can't read a date clearly, skip that event
- Gallery hours (like "Wed-Sat 1-6pm") are NOT start/end times - those are for visitors

Additional text content from the page (for reference):
{text_content[:2000] if text_content else "No additional text"}'''


async def extract_with_vision(url, content, current_date_string, name, notes, base_url=None):
    """
    Extract events using Gemini's vision capabilities.

    Downloads images from the page and sends them to Gemini for analysis.
    Returns JSON string with extracted events.
    """
    # Prepare image content
    image_parts, image_count = await prepare_vision_content(content, base_url)

    if not image_parts:
        print("    - No valid images found for vision extraction")
        return '{"events": []}'

    print(f"    - Processing {image_count} images with vision...")

    # Build prompt
    prompt_text = get_vision_prompt(url, content, current_date_string, name, notes)

    # Build multimodal content: text prompt + images
    contents = [prompt_text] + image_parts

    try:
        response = await asyncio.wait_for(
            genai_client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": EventList,
                }
            ),
            timeout=GEMINI_TIMEOUT * 2  # Double timeout for vision
        )
        response_text = response.text.strip()

        # Validate JSON
        try:
            parsed = json.loads(response_text)
            event_count = len(parsed.get('events', []))
            print(f"    - Vision extracted {event_count} events from images")
        except json.JSONDecodeError:
            response_text = '{"events": []}'

        return response_text

    except asyncio.TimeoutError:
        print(f"    - Vision extraction timeout after {GEMINI_TIMEOUT * 2}s")
        return '{"events": []}'
    except Exception as e:
        print(f"    - Vision extraction error: {e}")
        return '{"events": []}'


# =============================================================================
# Content Chunking Functions
# =============================================================================

def chunk_content_by_events(content, events_per_chunk=EVENTS_PER_CHUNK):
    """
    Split content into chunks based on event markers.

    Looks for common event patterns like numbered markdown headers (### [Event Name])
    and splits content so each chunk has approximately events_per_chunk events.

    Returns a list of content strings, one per chunk.
    """
    lines = content.split('\n')
    chunks = []
    current_chunk = []
    event_count = 0

    for line in lines:
        # Event marker pattern: numbered list item with ### header, or standalone ### header
        if re.match(r'^\s*\d+\.\s*###\s*\[', line) or line.strip().startswith('### ['):
            if event_count >= events_per_chunk and current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                event_count = 0
            event_count += 1
        current_chunk.append(line)

    # Add remaining content
    if current_chunk:
        chunks.append('\n'.join(current_chunk))

    return chunks


def chunk_content_by_size(content, max_chars=MAX_CHUNK_CHARS):
    """
    Split content into chunks by character count, breaking at paragraph boundaries.

    Used as fallback when event markers aren't found. Tries to split at double
    newlines (paragraphs) to keep related content together.

    Returns a list of content strings, one per chunk.
    """
    if len(content) <= max_chars:
        return [content]

    chunks = []
    # Split by paragraphs (double newlines)
    paragraphs = re.split(r'\n\n+', content)

    current_chunk = []
    current_size = 0

    for para in paragraphs:
        para_size = len(para) + 2  # +2 for the newlines we'll add back

        # If single paragraph exceeds max, split it by lines
        if para_size > max_chars:
            # First, save current chunk if any
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_size = 0

            # Split large paragraph by lines
            lines = para.split('\n')
            line_chunk = []
            line_size = 0
            for line in lines:
                if line_size + len(line) + 1 > max_chars and line_chunk:
                    chunks.append('\n'.join(line_chunk))
                    line_chunk = []
                    line_size = 0
                line_chunk.append(line)
                line_size += len(line) + 1
            if line_chunk:
                chunks.append('\n'.join(line_chunk))
        elif current_size + para_size > max_chars and current_chunk:
            # Save current chunk and start new one
            chunks.append('\n\n'.join(current_chunk))
            current_chunk = [para]
            current_size = para_size
        else:
            current_chunk.append(para)
            current_size += para_size

    # Add remaining content
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))

    return chunks


def chunk_content(content, events_per_chunk=EVENTS_PER_CHUNK, max_chars=MAX_CHUNK_CHARS):
    """
    Smart chunking that tries event markers first, then falls back to size-based chunking.

    Returns a tuple of (chunks, method) where method is 'events' or 'size'.
    """
    # First try event-based chunking
    event_chunks = chunk_content_by_events(content, events_per_chunk)

    # If we got multiple chunks, use them
    if len(event_chunks) > 1:
        return event_chunks, 'events'

    # If single chunk is small enough, use it
    if len(content) <= max_chars:
        return [content], 'single'

    # Fall back to size-based chunking
    size_chunks = chunk_content_by_size(content, max_chars)
    return size_chunks, 'size'


def count_event_markers(content):
    """Count markdown event headers in content."""
    return len(re.findall(r'^\s*\d+\.\s*###\s*\[|^###\s*\[', content, re.MULTILINE))


# =============================================================================
# Extraction Functions
# =============================================================================

def estimate_event_count(content):
    """
    Estimate the number of events on a page using pattern matching.

    Looks for common event indicators like dates, "View Event" links, etc.
    Returns a rough estimate to decide whether to use two-pass extraction.
    """
    # Count date patterns (Month Day format)
    date_patterns = len(re.findall(
        r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}',
        content, re.IGNORECASE
    ))

    # Count "View Event" or similar links
    view_event_count = len(re.findall(r'View\s+Event|View\s+Details|More\s+Info', content, re.IGNORECASE))

    # Count event URL patterns
    event_url_count = len(re.findall(r'/events?/[^/\s"\']+', content))

    # Return the maximum of these indicators
    return max(date_patterns // 2, view_event_count, event_url_count // 2)


def get_simple_prompt(url, page_content, current_date_string, name, notes):
    """Generate a simplified prompt for first-pass extraction on large pages."""
    note_section = f"\n\nIMPORTANT: {notes}" if notes else ""

    return f'''Today's date is {current_date_string}. Extract ALL events from this NYC venue page.

For each event provide: name, location (venue name), occurrences (array of start_date in YYYY-MM-DD, start_time, end_time), and url if available.
{note_section}
IMPORTANT: Extract EVERY event - do not skip or summarize. There may be 100+ events.

Website content:

{page_content}'''


def get_enrichment_prompt(event_names, venue_name):
    """Generate prompt for enriching events with descriptions, hashtags, and emoji."""
    names_list = "\n".join(f"- {name}" for name in event_names)

    return f'''For each event at {venue_name}, provide:
- description: 1-3 sentence description of what the event is
- hashtags: 4-7 CamelCase tags (e.g., Comedy, Music, Outdoor, LatinJazz)
- emoji: Single emoji representing the event

Events to enrich:
{names_list}

Return a JSON object with "enrichments" key mapping each event name to its enrichment data.'''


async def enrich_events_batch(event_names, venue_name):
    """
    Enrich a batch of events with descriptions, hashtags, and emoji.

    Returns a dict mapping event names to enrichment data.
    """
    if not event_names:
        return {}

    prompt = get_enrichment_prompt(event_names, venue_name)

    try:
        response = await asyncio.wait_for(
            genai_client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": EnrichmentBatch,
                }
            ),
            timeout=GEMINI_TIMEOUT
        )
        result = json.loads(response.text.strip())
        # Convert list to dict for easy lookup
        enrichments = {}
        for item in result.get('enrichments', []):
            name = item.get('name', '')
            enrichments[name] = {
                'description': item.get('description', ''),
                'hashtags': item.get('hashtags', []),
                'emoji': item.get('emoji', '📅')
            }
        return enrichments
    except Exception as e:
        print(f"    - Enrichment batch error: {e}")
        return {}


async def extract_chunk(chunk_content, current_date_string, notes):
    """
    Extract events from a single content chunk.

    Returns a list of simple event dicts, or empty list on error.
    """
    note_section = f"\n\nIMPORTANT: {notes}" if notes else ""

    prompt = f'''Today's date is {current_date_string}. Extract ALL events from this NYC events page content.

For each event provide: name, location (venue name), occurrences (array of start_date in YYYY-MM-DD, start_time, end_time), and url if available.
{note_section}
Website content:

{chunk_content}'''

    try:
        response = await asyncio.wait_for(
            genai_client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": SimpleEventList,
                }
            ),
            timeout=CHUNK_TIMEOUT
        )
        result = json.loads(response.text.strip())
        return result.get('events', [])
    except asyncio.TimeoutError:
        print(f"      Chunk timeout after {CHUNK_TIMEOUT}s")
        return []
    except Exception as e:
        print(f"      Chunk error: {e}")
        return []


async def extract_large_page(url, content, current_date_string, name, notes):
    """
    Chunked extraction for large pages.

    1. Split content into manageable chunks (by events or by size)
    2. Extract events from each chunk sequentially
    3. Enrich all events with descriptions/hashtags/emoji in batches
    4. Combine and return results

    Returns the combined result as a JSON string.
    """
    # Split content into chunks using smart chunking
    chunks, chunk_method = chunk_content(content, EVENTS_PER_CHUNK, MAX_CHUNK_CHARS)
    print(f"    - Split into {len(chunks)} chunks using {chunk_method}-based chunking")

    # Extract events from each chunk
    all_simple_events = []
    for i, chunk in enumerate(chunks):
        chunk_events = count_event_markers(chunk)
        print(f"    - Processing chunk {i + 1}/{len(chunks)} (~{chunk_events} events, {len(chunk)} chars)...")
        events = await extract_chunk(chunk, current_date_string, notes)
        if events:
            print(f"      Got {len(events)} events")
            all_simple_events.extend(events)
        else:
            print(f"      No events extracted")

    if not all_simple_events:
        return '{"events": []}'

    print(f"    - Total from chunks: {len(all_simple_events)} events")

    # Enrich events with descriptions/hashtags/emoji in batches
    event_names = [e['name'] for e in all_simple_events]
    all_enrichments = {}

    for i in range(0, len(event_names), ENRICHMENT_BATCH_SIZE):
        batch = event_names[i:i + ENRICHMENT_BATCH_SIZE]
        print(f"    - Enriching batch {i // ENRICHMENT_BATCH_SIZE + 1} ({len(batch)} events)...")
        enrichments = await enrich_events_batch(batch, name)
        all_enrichments.update(enrichments)

    # Combine simple events with enrichments
    full_events = []
    for event in all_simple_events:
        enrichment = all_enrichments.get(event['name'], {})
        full_event = {
            'name': event['name'],
            'location': event['location'],
            'sublocation': None,  # Not extracted in chunked pass
            'occurrences': event['occurrences'],
            'url': event.get('url'),
            'description': enrichment.get('description', f"Event at {event['location']}"),
            'hashtags': enrichment.get('hashtags', ['Event']),
            'emoji': enrichment.get('emoji', '📅'),
        }
        full_events.append(full_event)

    return json.dumps({'events': full_events})


def get_prompt(url, page_content, current_date_string, name, notes, existing_events=None):
    """Generate the AI prompt for event extraction."""
    note_section = f"\n\nIMPORTANT: {notes}" if notes else ""

    # Format existing events as JSON for prompt
    existing_events_section = ""
    if existing_events:
        existing_events_json = json.dumps(existing_events, indent=2)
        existing_events_section = f"""
REFERENCE - Previously extracted events (for naming consistency only):
{existing_events_json}

NOTE: The above is ONLY for reference to maintain consistent naming. You MUST still extract ALL events from the page content below - do not limit your output to these events. Our deduplication system will handle any overlaps.

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

{note_section}
Rules:
- Extract ALL events from the page - do not skip or summarize
- Only include events in the NYC area within the next 3 months
- Ignore unrelated event sections ("Hot Events", "Similar events", etc.)
- For recurring events, expand ALL individual dates into the occurrences array
- If no events are found, return an empty events list

Website content:

{page_content}'''


async def extract_events(cursor, connection, crawl_result_id, website_name, notes="",
                         use_vision=False, base_url=""):
    """
    Extract events from crawled content using Gemini AI with structured outputs.

    Args:
        cursor: Database cursor
        connection: Database connection
        crawl_result_id: ID of the crawl result
        website_name: Name of the website
        notes: Optional notes for the AI prompt
        use_vision: If True, use vision API to analyze images in the content
        base_url: Base URL for resolving relative image URLs

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

    # Decide extraction approach
    if use_vision:
        # Vision-based extraction for image-heavy pages
        print(f"    - Using vision extraction for {website_name} ({len(content_to_process)} chars)...")
    else:
        # Estimate event count to decide text extraction approach
        estimated_events = estimate_event_count(content_to_process)
        use_two_pass = estimated_events > LARGE_PAGE_THRESHOLD

        if use_two_pass:
            print(f"    - Large page detected (~{estimated_events} events), using chunked extraction...")
        else:
            print(f"    - Extracting events using {GEMINI_MODEL} ({len(content_to_process)} chars)...")

    try:
        if use_vision:
            # Vision-based extraction - analyze images in the content
            response_text = await extract_with_vision(
                url, content_to_process, current_date_string, website_name, notes,
                base_url=base_url or url
            )
        elif use_two_pass:
            # Two-pass extraction for large pages
            response_text = await extract_large_page(
                url, content_to_process, current_date_string, website_name, notes
            )
        else:
            # Standard single-pass extraction for smaller pages
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
        if not response_text.strip():
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

    except asyncio.TimeoutError:
        error_msg = f"Timeout after {GEMINI_TIMEOUT} seconds"
        print(f"    - Extraction error: {error_msg}")
        db.update_crawl_result_failed(
            cursor, connection, crawl_result_id, f"Extraction failed: {error_msg}"
        )
        return False
    except Exception as e:
        error_msg = str(e) or type(e).__name__
        print(f"    - Extraction error: {error_msg}")
        db.update_crawl_result_failed(
            cursor, connection, crawl_result_id, f"Extraction failed: {error_msg}"
        )
        return False


def is_available():
    """Check if Gemini API is available."""
    return GEMINI_API_KEY is not None and genai_client is not None
