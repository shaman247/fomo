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
from dataclasses import dataclass, field
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
    from google.genai.types import (
        InlinedRequest, InlinedResponse, GenerateContentConfig, JobState
    )
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
        description="4-7 CamelCase tags. Always include at least one category (Music, Nightlife, Comedy, Art, Theater, Dance, Film, Literature, Community, Family, Wellness, Education, Outdoor, Sports, Games). Also add Free if the event is free, Virtual if online. Then add granular tags."
    )
    emoji: str = Field(description="A single emoji that represents the event")


class EventList(BaseModel):
    """Schema for a list of events extracted from website content."""
    request_id: str = Field(
        default="",
        description="Echo back the request_id from the prompt"
    )
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
    request_id: str = Field(
        default="",
        description="Echo back the request_id from the prompt"
    )
    events: list[SimpleEvent] = Field(default_factory=list)


# =============================================================================
# Enrichment Schema (Second Pass)
# =============================================================================

class EventEnrichment(BaseModel):
    """Schema for enrichment data added in second pass."""
    name: str = Field(description="The event name (must match exactly)")
    description: str = Field(description="1-3 sentence description")
    hashtags: list[str] = Field(description="4-7 CamelCase tags. Include at least one category (Music, Nightlife, Comedy, Art, Theater, Dance, Film, Literature, Community, Family, Wellness, Education, Outdoor, Sports, Games), Free if free, Virtual if online, plus granular tags")
    emoji: str = Field(description="Single emoji")


class EnrichmentBatch(BaseModel):
    """Batch of enrichments as a list."""
    request_id: str = Field(
        default="",
        description="Echo back the request_id from the prompt"
    )
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

# Default maximum number of enrichment batches for large pages
# Limits API cost by capping how many events get enriched
# Can be overridden per-website via the max_batches column
DEFAULT_MAX_BATCHES = 3

# Timeout per chunk (seconds) - increased for large pages that can't be chunked
CHUNK_TIMEOUT = 300

# Maximum characters per chunk when falling back to character-based chunking
MAX_CHUNK_CHARS = 30000

# Hard limit on total content size before extraction (characters).
# Pages exceeding this will be truncated. 120K chars ≈ 4 chunks of 30K,
# which is plenty for any events page. Prevents runaway extraction on
# pages with huge archives (e.g., years of past events).
MAX_CONTENT_CHARS = 120000

# Maximum number of images to process for vision extraction
MAX_VISION_IMAGES = 10

# Maximum image dimension (images will be resized if larger)
MAX_IMAGE_DIMENSION = 1024

# Batch API settings
BATCH_POLL_INTERVAL = int(os.environ.get("BATCH_POLL_INTERVAL", "30"))  # seconds
BATCH_TIMEOUT = int(os.environ.get("BATCH_TIMEOUT", "86400"))  # 24 hour default
BATCH_TOKEN_LIMIT = int(os.environ.get("BATCH_TOKEN_LIMIT", "2000000"))  # conservative limit (Tier 1: 3M)
CHARS_PER_TOKEN = 3  # conservative estimate (Gemini tokenizer averages ~3 chars/token for mixed content)


# =============================================================================
# Prepared Extraction Data
# =============================================================================

@dataclass
class PreparedExtraction:
    """Result of preparing a crawl result for extraction (no API calls made)."""
    crawl_result_id: int
    website_name: str
    extraction_type: str  # 'single', 'chunked', 'vision'

    # For 'single' type
    prompt: Optional[str] = None
    existing_events: list = field(default_factory=list)

    # For 'vision' type
    vision_contents: Optional[list] = None  # [prompt_text, image_part1, ...]

    # For 'chunked' type
    chunk_prompts: list = field(default_factory=list)
    max_batches: Optional[int] = None

    # Shared
    url: str = ""
    notes: str = ""

    # Pre-resolved result (set if no API call needed, e.g., vision with no images)
    resolved_result: Optional[str] = None

    # Error (set if preparation failed, e.g., content too small)
    error: Optional[str] = None


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

    except Exception:
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


def get_vision_prompt(url, text_content, current_date_string, name, notes, request_id=""):
    """Generate a prompt for vision-based event extraction."""
    note_section = f"\n\nIMPORTANT: {notes}" if notes else ""
    rid_section = f"\n\nIMPORTANT: Set request_id to \"{request_id}\" in your response." if request_id else ""

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
- hashtags: 4-7 CamelCase tags. Always include at least one category (Music, Nightlife, Comedy, Art, Theater, Dance, Film, Literature, Community, Family, Wellness, Education, Outdoor, Sports, Games). Add Free if free, Virtual if online. Then granular tags.
- emoji: A single emoji representing the event
{note_section}
Rules:
- Extract events from ALL the flyer images provided
- Only include events that appear to be upcoming (after {current_date_string})
- For art exhibitions, the start_date is opening day and end_date is closing day
- If you can't read a date clearly, skip that event
- Gallery hours (like "Wed-Sat 1-6pm") are NOT start/end times - those are for visitors
{rid_section}
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
    Returns a rough estimate to decide whether to use chunked extraction.
    """
    date_count = len(re.findall(
        r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}',
        content, re.IGNORECASE
    ))
    view_event_count = len(re.findall(r'View\s+Event|View\s+Details|More\s+Info', content, re.IGNORECASE))
    event_url_count = len(re.findall(r'/events?/[^/\s"\']+', content))
    listing_url_count = len(re.findall(r'/listings?/[^/\s"\']+', content))

    # Dates may appear 2x per event (heading + details), so halve them
    return max(date_count // 2, view_event_count, event_url_count // 2, listing_url_count // 2)


def get_enrichment_prompt(event_names, venue_name, request_id=""):
    """Generate prompt for enriching events with descriptions, hashtags, and emoji."""
    names_list = "\n".join(f"- {name}" for name in event_names)
    rid_section = f"\n\nIMPORTANT: Set request_id to \"{request_id}\" in your response." if request_id else ""

    return f'''For each event at {venue_name}, provide:
- description: 1-3 sentence description of what the event is
- hashtags: 4-7 CamelCase tags. Always include at least one category (Music, Nightlife, Comedy, Art, Theater, Dance, Film, Literature, Community, Family, Wellness, Education, Outdoor, Sports, Games). Add Free if free, Virtual if online. Then granular tags.
- emoji: Single emoji representing the event

Events to enrich:
{names_list}
{rid_section}
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
        return {
            item.get('name', ''): {
                'description': item.get('description', ''),
                'hashtags': item.get('hashtags', []),
                'emoji': item.get('emoji', '📅')
            }
            for item in result.get('enrichments', [])
        }
    except Exception as e:
        print(f"    - Enrichment batch error: {e}")
        return {}


def get_chunk_prompt(chunk_text, current_date_string, notes, request_id=""):
    """Generate prompt for a single chunk extraction."""
    note_section = f"\n\nIMPORTANT: {notes}" if notes else ""
    rid_section = f"\n\nIMPORTANT: Set request_id to \"{request_id}\" in your response." if request_id else ""
    return f'''Today's date is {current_date_string}. Extract ALL events from this NYC events page content.

For each event provide: name, location (venue name), occurrences (array of start_date in YYYY-MM-DD, start_time, end_time), and url if available.
{note_section}{rid_section}
Website content:

{chunk_text}'''


async def extract_chunk(chunk_content, current_date_string, notes):
    """
    Extract events from a single content chunk.

    Returns a list of simple event dicts, or empty list on error.
    """
    prompt = get_chunk_prompt(chunk_content, current_date_string, notes)

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


async def extract_large_page(url, content, current_date_string, name, notes, max_batches=None):
    """
    Chunked extraction for large pages.

    1. Split content into manageable chunks (by events or by size)
    2. Extract events from each chunk sequentially
    3. Enrich all events with descriptions/hashtags/emoji in batches
    4. Combine and return results

    Args:
        max_batches: Maximum enrichment batches. None uses DEFAULT_MAX_BATCHES.

    Returns the combined result as a JSON string.
    """
    if max_batches is None:
        max_batches = DEFAULT_MAX_BATCHES
    max_events = max_batches * ENRICHMENT_BATCH_SIZE

    # Split content into chunks using smart chunking
    chunks, chunk_method = chunk_content(content, EVENTS_PER_CHUNK, MAX_CHUNK_CHARS)
    print(f"    - Split into {len(chunks)} chunks using {chunk_method}-based chunking")

    # Extract events from each chunk
    all_simple_events = []
    skipped_chunks = 0
    for i, chunk in enumerate(chunks):
        # Stop extracting chunks once we have enough events for max_batches
        if len(all_simple_events) >= max_events:
            skipped_chunks = len(chunks) - i
            break
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

    if skipped_chunks > 0:
        print(f"    - Skipped {skipped_chunks} remaining chunk(s) (already have {len(all_simple_events)} events)")

    print(f"    - Total from chunks: {len(all_simple_events)} events")

    # Cap events at max_batches to limit API cost
    total_batches_needed = -(-len(all_simple_events) // ENRICHMENT_BATCH_SIZE)  # ceiling division
    if total_batches_needed > max_batches:
        print(f"    - WARNING: {len(all_simple_events)} events would need {total_batches_needed} batches, capping at {max_batches} ({max_events} events). "
              f"Set max_batches in websites table to override.")
        all_simple_events = all_simple_events[:max_events]

    # Enrich events with descriptions/hashtags/emoji in batches
    event_names = [e['name'] for e in all_simple_events]
    num_batches = -(-len(event_names) // ENRICHMENT_BATCH_SIZE)
    all_enrichments = {}

    for i in range(0, len(event_names), ENRICHMENT_BATCH_SIZE):
        batch = event_names[i:i + ENRICHMENT_BATCH_SIZE]
        print(f"    - Enriching batch {i // ENRICHMENT_BATCH_SIZE + 1}/{num_batches} ({len(batch)} events)...")
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


def get_prompt(url, page_content, current_date_string, name, notes, existing_events=None, request_id=""):
    """Generate the AI prompt for full event extraction.

    Prompt structure:
      1. Previously extracted events (reference only, for naming consistency)
      2. Website-specific notes (from websites.notes column)
      3. System instructions (extraction rules, date handling, field formats)
      4. Page content to extract from
    """
    note_section = f"\n\nIMPORTANT: {notes}" if notes else ""
    rid_section = f"\n\nIMPORTANT: Set request_id to \"{request_id}\" in your response." if request_id else ""

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
- hashtags: 4-7 CamelCase tags (e.g., ["Comedy", "StandUp", "Free"]). Always include at least one category from: Music, Nightlife, Comedy, Art, Theater, Dance, Film, Literature, Community, Family, Wellness, Education, Outdoor, Sports, Games. Also include Free if the event is free, or Virtual if online. Then add granular descriptive tags. Avoid location-specific or NYC-redundant tags.
- emoji: A single emoji representing the event

{note_section}{rid_section}
Rules:
- Extract ALL events from the page - do not skip or summarize
- Only include events in the NYC area within the next 3 months
- Ignore unrelated event sections ("Hot Events", "Similar events", etc.)
- For recurring events, expand ALL individual dates into the occurrences array
- If no events are found, return an empty events list

Website content:

{page_content}'''


async def prepare_extraction(cursor, crawl_result_id, website_name, notes="",
                              use_vision=False, base_url="", max_batches=None):
    """
    Prepare extraction request data without making API calls.

    Performs all validation, classification, and prompt building, returning
    a PreparedExtraction that can be executed via sync API calls or batched.

    Args:
        cursor: Database cursor
        crawl_result_id: ID of the crawl result
        website_name: Name of the website
        notes: Optional notes for the AI prompt
        use_vision: If True, prepare vision extraction with images
        base_url: Base URL for resolving relative image URLs
        max_batches: Maximum enrichment batches for chunked extraction

    Returns:
        PreparedExtraction with all data needed for execution
    """
    prep = PreparedExtraction(
        crawl_result_id=crawl_result_id,
        website_name=website_name,
        extraction_type='single',
        notes=notes,
    )

    # Get crawled content from database
    page_content = db.get_crawled_content(cursor, crawl_result_id)
    if not page_content:
        prep.error = "No crawled content found"
        return prep

    # Check for minimum content size to prevent hallucinations
    content_size = len(page_content)
    if content_size < MIN_CONTENT_SIZE:
        prep.error = (f"Crawled content too small ({content_size} bytes < {MIN_CONTENT_SIZE} "
                      f"minimum) - likely failed crawl, skipping to prevent hallucinations")
        return prep

    # Check for explicit "no events" indicators to prevent hallucinations.
    # Some pages (e.g., Eventbrite organizer pages with no upcoming events)
    # have substantial content (navigation, past events) but explicitly state
    # there are no upcoming events. Gemini will hallucinate events from such pages.
    no_events_patterns = [
        "upcoming (0)",
        "sorry, there are no upcoming events",
        "no upcoming events",
        "no events found",
        "no events scheduled",
    ]
    content_lower = page_content[:15000].lower()  # Only check first 15K chars
    for pattern in no_events_patterns:
        if pattern in content_lower:
            prep.resolved_result = '{"events": []}'
            print(f"    - Page explicitly states no events ('{pattern}'), skipping extraction")
            return prep

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
    prep.existing_events = existing_events

    current_date_string = datetime.now().strftime('%Y-%m-%d')

    # Extract URL from first line if present
    url, content_to_process = extract_url_from_content(page_content)
    url = url or ""
    prep.url = url

    # Hard limit on content size to prevent runaway extraction
    if len(content_to_process) > MAX_CONTENT_CHARS:
        print(f"    - Content too large ({len(content_to_process)} chars), truncating to {MAX_CONTENT_CHARS}")
        content_to_process = content_to_process[:MAX_CONTENT_CHARS]

    # Decide extraction approach and build prompts
    if use_vision:
        prep.extraction_type = 'vision'
        print(f"    - Preparing vision extraction for {website_name} ({len(content_to_process)} chars)...")

        # Download and encode images
        image_parts, image_count = await prepare_vision_content(content_to_process, base_url or url)
        if not image_parts:
            print("    - No valid images found for vision extraction")
            prep.resolved_result = '{"events": []}'
            return prep

        print(f"    - Prepared {image_count} images for vision extraction")
        prompt_text = get_vision_prompt(url, content_to_process, current_date_string, website_name, notes,
                                        request_id=f"cr-{crawl_result_id}")
        prep.vision_contents = [prompt_text] + image_parts

    else:
        estimated_events = estimate_event_count(content_to_process)
        use_two_pass = estimated_events > LARGE_PAGE_THRESHOLD or len(content_to_process) > MAX_CHUNK_CHARS * 2

        if use_two_pass:
            prep.extraction_type = 'chunked'
            prep.max_batches = max_batches if max_batches is not None else DEFAULT_MAX_BATCHES
            print(f"    - Large page detected (~{estimated_events} events, {len(content_to_process)} chars), preparing chunked extraction...")

            # Split content into chunks and build prompts
            chunks, chunk_method = chunk_content(content_to_process, EVENTS_PER_CHUNK, MAX_CHUNK_CHARS)
            print(f"    - Split into {len(chunks)} chunks using {chunk_method}-based chunking")

            prep.chunk_prompts = [
                get_chunk_prompt(chunk, current_date_string, notes,
                                 request_id=f"cr-{crawl_result_id}-chunk-{i}")
                for i, chunk in enumerate(chunks)
            ]
        else:
            prep.extraction_type = 'single'
            print(f"    - Preparing extraction using {GEMINI_MODEL} ({len(content_to_process)} chars)... [{datetime.now().strftime('%H:%M:%S')}]")
            prep.prompt = get_prompt(url, content_to_process, current_date_string,
                                     website_name, notes, existing_events,
                                     request_id=f"cr-{crawl_result_id}")

    return prep


async def execute_extraction_sync(cursor, connection, prep):
    """
    Execute extraction using individual (non-batch) API calls.

    Takes a PreparedExtraction and makes the appropriate Gemini API call(s).

    Returns:
        True if successful, False otherwise
    """
    crawl_result_id = prep.crawl_result_id

    # Handle pre-resolved results (e.g., vision with no images)
    if prep.resolved_result is not None:
        response_text = prep.resolved_result
    elif prep.extraction_type == 'vision':
        try:
            response = await asyncio.wait_for(
                genai_client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prep.vision_contents,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": EventList,
                    }
                ),
                timeout=GEMINI_TIMEOUT * 2
            )
            response_text = response.text.strip()
        except asyncio.TimeoutError:
            print(f"    - Vision extraction timeout after {GEMINI_TIMEOUT * 2}s")
            response_text = '{"events": []}'
        except Exception as e:
            print(f"    - Vision extraction error: {e}")
            response_text = '{"events": []}'

    elif prep.extraction_type == 'chunked':
        response_text = await _execute_chunked_sync(prep)

    else:  # single
        response = await asyncio.wait_for(
            genai_client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=prep.prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": EventList,
                }
            ),
            timeout=GEMINI_TIMEOUT
        )
        response_text = response.text.strip()

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
        response_text = '{"events": []}'
        event_count = 0
        occurrence_count = 0

    db.update_crawl_result_extracted(cursor, connection, crawl_result_id, response_text)
    print(f"    - Extracted {event_count} events with {occurrence_count} occurrences [{datetime.now().strftime('%H:%M:%S')}]")
    return True


async def _execute_chunked_sync(prep):
    """Execute chunked extraction synchronously (individual API calls)."""
    max_events = prep.max_batches * ENRICHMENT_BATCH_SIZE

    # Extract events from each chunk
    all_simple_events = []
    skipped_chunks = 0
    for i, chunk_prompt in enumerate(prep.chunk_prompts):
        if len(all_simple_events) >= max_events:
            skipped_chunks = len(prep.chunk_prompts) - i
            break
        print(f"    - Processing chunk {i + 1}/{len(prep.chunk_prompts)}...")
        try:
            response = await asyncio.wait_for(
                genai_client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=chunk_prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": SimpleEventList,
                    }
                ),
                timeout=CHUNK_TIMEOUT
            )
            result = json.loads(response.text.strip())
            events = result.get('events', [])
            if events:
                print(f"      Got {len(events)} events")
                all_simple_events.extend(events)
            else:
                print(f"      No events extracted")
        except asyncio.TimeoutError:
            print(f"      Chunk timeout after {CHUNK_TIMEOUT}s")
        except Exception as e:
            print(f"      Chunk error: {e}")

    if not all_simple_events:
        return '{"events": []}'

    if skipped_chunks > 0:
        print(f"    - Skipped {skipped_chunks} remaining chunk(s) (already have {len(all_simple_events)} events)")

    print(f"    - Total from chunks: {len(all_simple_events)} events")

    # Cap events at max_batches to limit API cost
    total_batches_needed = -(-len(all_simple_events) // ENRICHMENT_BATCH_SIZE)
    if total_batches_needed > prep.max_batches:
        print(f"    - WARNING: {len(all_simple_events)} events would need {total_batches_needed} batches, "
              f"capping at {prep.max_batches} ({max_events} events). "
              f"Set max_batches in websites table to override.")
        all_simple_events = all_simple_events[:max_events]

    # Enrich events with descriptions/hashtags/emoji in batches
    event_names = [e['name'] for e in all_simple_events]
    num_batches = -(-len(event_names) // ENRICHMENT_BATCH_SIZE)
    all_enrichments = {}

    for i in range(0, len(event_names), ENRICHMENT_BATCH_SIZE):
        batch = event_names[i:i + ENRICHMENT_BATCH_SIZE]
        print(f"    - Enriching batch {i // ENRICHMENT_BATCH_SIZE + 1}/{num_batches} ({len(batch)} events)...")
        enrichments = await enrich_events_batch(batch, prep.website_name)
        all_enrichments.update(enrichments)

    return _combine_chunked_results(all_simple_events, all_enrichments)


def _combine_chunked_results(simple_events, enrichments):
    """Combine simple events with enrichment data into final JSON."""
    full_events = []
    for event in simple_events:
        enrichment = enrichments.get(event['name'], {})
        full_event = {
            'name': event['name'],
            'location': event['location'],
            'sublocation': None,
            'occurrences': event['occurrences'],
            'url': event.get('url'),
            'description': enrichment.get('description', f"Event at {event['location']}"),
            'hashtags': enrichment.get('hashtags', ['Event']),
            'emoji': enrichment.get('emoji', '📅'),
        }
        full_events.append(full_event)
    return json.dumps({'events': full_events})


async def extract_events(cursor, connection, crawl_result_id, website_name, notes="",
                         use_vision=False, base_url="", max_batches=None):
    """
    Extract events from crawled content using individual Gemini API calls.

    This is the sync (non-batch) extraction path. Prepares the request data,
    then executes via individual API calls.

    Returns:
        True if successful, False otherwise
    """
    if not GEMINI_API_KEY or not genai_client:
        print("    - Skipping extraction: Gemini API not configured")
        return False

    prep = await prepare_extraction(cursor, crawl_result_id, website_name, notes,
                                     use_vision, base_url, max_batches)

    if prep.error:
        print(f"    - {prep.error}")
        db.update_crawl_result_failed(cursor, connection, crawl_result_id, prep.error)
        return False

    try:
        return await execute_extraction_sync(cursor, connection, prep)
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


# =============================================================================
# Batch API Functions
# =============================================================================

def _build_single_request(prep):
    """Build an InlinedRequest for single-pass extraction."""
    request_id = f"cr-{prep.crawl_result_id}"
    return InlinedRequest(
        contents=prep.prompt,
        config=GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=EventList,
        ),
        metadata={
            "crawl_result_id": str(prep.crawl_result_id),
            "type": "single",
            "website_name": prep.website_name,
            "request_id": request_id,
        }
    )


def _build_vision_request(prep):
    """Build an InlinedRequest for vision extraction."""
    request_id = f"cr-{prep.crawl_result_id}"
    return InlinedRequest(
        contents=prep.vision_contents,
        config=GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=EventList,
        ),
        metadata={
            "crawl_result_id": str(prep.crawl_result_id),
            "type": "vision",
            "website_name": prep.website_name,
            "request_id": request_id,
        }
    )


def _build_chunk_requests(prep):
    """Build InlinedRequests for chunked extraction (one per chunk).

    Caps the number of chunks based on max_batches to avoid over-extraction.
    In batch mode we can't do early stopping, so we add +1 chunk headroom
    since actual events-per-chunk varies. The max_events cap is applied after
    results return (in process_batch_responses).
    """
    max_events = prep.max_batches * ENRICHMENT_BATCH_SIZE
    max_chunks = max(1, -(-max_events // EVENTS_PER_CHUNK)) + 1  # ceiling division + headroom

    requests = []
    for i, chunk_prompt in enumerate(prep.chunk_prompts[:max_chunks]):
        requests.append(InlinedRequest(
            contents=chunk_prompt,
            config=GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SimpleEventList,
            ),
            metadata={
                "crawl_result_id": str(prep.crawl_result_id),
                "type": "chunk",
                "chunk_index": str(i),
                "total_chunks": str(len(prep.chunk_prompts)),
                "website_name": prep.website_name,
                "request_id": f"cr-{prep.crawl_result_id}-chunk-{i}",
            }
        ))

    if len(prep.chunk_prompts) > max_chunks:
        print(f"    - {prep.website_name}: Submitting {max_chunks}/{len(prep.chunk_prompts)} chunks "
              f"(capped by max_batches={prep.max_batches})")

    return requests


def _build_enrichment_request(crawl_result_id, batch_event_names, venue_name, batch_idx, website_name):
    """Build an InlinedRequest for enrichment."""
    request_id = f"cr-{crawl_result_id}-enrich-{batch_idx}"
    return InlinedRequest(
        contents=get_enrichment_prompt(batch_event_names, venue_name, request_id=request_id),
        config=GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=EnrichmentBatch,
        ),
        metadata={
            "crawl_result_id": str(crawl_result_id),
            "type": "enrichment",
            "batch_index": str(batch_idx),
            "website_name": website_name,
            "request_id": request_id,
        }
    )


def build_batch_requests(preparations):
    """Convert PreparedExtractions into Phase 1 InlinedRequests.

    Args:
        preparations: dict of {crawl_result_id: PreparedExtraction}

    Returns:
        list of InlinedRequest objects for all extraction types
    """
    requests = []
    for crid, prep in preparations.items():
        if prep.extraction_type == 'single':
            requests.append(_build_single_request(prep))
        elif prep.extraction_type == 'vision':
            requests.append(_build_vision_request(prep))
        elif prep.extraction_type == 'chunked':
            requests.extend(_build_chunk_requests(prep))
    return requests


def build_enrichment_requests(chunked_events, preparations):
    """Build Phase 2 InlinedRequests for enrichment of chunked results.

    Args:
        chunked_events: dict of {crawl_result_id: [simple_event_dicts]}
        preparations: dict of {crawl_result_id: PreparedExtraction}

    Returns:
        list of InlinedRequest objects for enrichment
    """
    requests = []
    for crid, events in chunked_events.items():
        prep = preparations[crid]
        event_names = [e['name'] for e in events]

        for i in range(0, len(event_names), ENRICHMENT_BATCH_SIZE):
            batch = event_names[i:i + ENRICHMENT_BATCH_SIZE]
            requests.append(_build_enrichment_request(
                crid, batch, prep.website_name,
                batch_idx=i // ENRICHMENT_BATCH_SIZE,
                website_name=prep.website_name,
            ))

    return requests


def _estimate_request_tokens(request):
    """Estimate the token count for an InlinedRequest."""
    contents = request.contents
    if isinstance(contents, str):
        return len(contents) // CHARS_PER_TOKEN
    elif isinstance(contents, list):
        # Vision requests: list of Parts (text + images)
        total = 0
        for part in contents:
            if hasattr(part, 'text') and part.text:
                total += len(part.text) // CHARS_PER_TOKEN
            elif hasattr(part, 'inline_data'):
                total += 258  # Gemini charges 258 tokens per image
        return total
    return 0


def _split_into_batches(requests, token_limit=BATCH_TOKEN_LIMIT):
    """Split requests into equal-sized batches that fit under the token limit.

    Returns:
        list of lists of InlinedRequests
    """
    if not requests:
        return []

    total_tokens = sum(_estimate_request_tokens(r) for r in requests)

    if total_tokens <= token_limit:
        return [requests]

    num_batches = -(-total_tokens // token_limit)  # ceiling division
    batch_size = -(-len(requests) // num_batches)  # equal-sized splits

    batches = [requests[i:i + batch_size] for i in range(0, len(requests), batch_size)]
    print(f"  Splitting {len(requests)} requests (~{total_tokens:,} tokens) into {len(batches)} batches "
          f"(limit: {token_limit:,} tokens)")
    return batches


async def _submit_and_poll_single_batch(requests, display_name="fomo-extraction",
                                         poll_interval=None, timeout=None):
    """Submit a single batch job and poll until completion.

    Args:
        requests: list of InlinedRequest objects
        display_name: Name for the batch job
        poll_interval: Seconds between status checks (default: BATCH_POLL_INTERVAL)
        timeout: Maximum seconds to wait (default: BATCH_TIMEOUT)

    Returns:
        list of InlinedResponse in same order as requests

    Raises:
        RuntimeError: on timeout, job failure, or cancellation
    """
    if poll_interval is None:
        poll_interval = BATCH_POLL_INTERVAL
    if timeout is None:
        timeout = BATCH_TIMEOUT

    if not requests:
        return []

    print(f"  Submitting batch '{display_name}' with {len(requests)} request(s)...")

    # Retry with backoff for transient 429 rate limits on batch creation
    batch_job = None
    for attempt in range(3):
        try:
            batch_job = await genai_client.aio.batches.create(
                model=GEMINI_MODEL,
                src=requests,
                config={"display_name": display_name},
            )
            break
        except Exception as e:
            if attempt < 2 and "429" in str(e):
                wait = 60 * (attempt + 1)
                print(f"  Rate limited on batch creation, retrying in {wait}s... (attempt {attempt + 1}/3)")
                await asyncio.sleep(wait)
            else:
                raise RuntimeError(f"Failed to create batch job: {e}") from e

    print(f"  Batch job created: {batch_job.name} (state: {batch_job.state.name})")

    elapsed = 0
    while not batch_job.done:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        try:
            batch_job = await genai_client.aio.batches.get(name=batch_job.name)
        except Exception as e:
            print(f"  Warning: Failed to poll batch status: {e}")
            # Continue polling — transient errors are expected
            continue

        state_name = batch_job.state.name if batch_job.state else "UNKNOWN"
        print(f"  Batch status: {state_name} ({elapsed}s elapsed)")

        if elapsed >= timeout:
            # Try to cancel the job before raising
            try:
                await genai_client.aio.batches.cancel(name=batch_job.name)
                print(f"  Cancelled timed-out batch job {batch_job.name}")
            except Exception:
                pass
            raise RuntimeError(
                f"Batch job {batch_job.name} timed out after {timeout}s "
                f"(state: {state_name})"
            )

    state_name = batch_job.state.name if batch_job.state else "UNKNOWN"

    if state_name == "JOB_STATE_FAILED":
        error_detail = batch_job.error.message if batch_job.error else "unknown error"
        raise RuntimeError(f"Batch job {batch_job.name} failed: {error_detail}")

    if state_name == "JOB_STATE_CANCELLED":
        raise RuntimeError(f"Batch job {batch_job.name} was cancelled")

    responses = batch_job.dest.inlined_responses or []
    succeeded = sum(1 for r in responses if r.response)
    failed = sum(1 for r in responses if r.error)
    print(f"  Batch completed: {succeeded} succeeded, {failed} failed out of {len(responses)} request(s)")

    return responses


async def submit_and_poll_batch(requests, display_name="fomo-extraction",
                                 poll_interval=None, timeout=None):
    """Submit batch requests, splitting into sub-batches if needed to stay under token limits.

    Args:
        requests: list of InlinedRequest objects
        display_name: Name prefix for batch jobs
        poll_interval: Seconds between status checks (default: BATCH_POLL_INTERVAL)
        timeout: Maximum seconds to wait per sub-batch (default: BATCH_TIMEOUT)

    Returns:
        list of InlinedResponse in same order as requests
    """
    batches = _split_into_batches(requests)
    if not batches:
        return []

    all_responses = []
    for i, batch in enumerate(batches):
        suffix = f"-{i+1}of{len(batches)}" if len(batches) > 1 else ""
        responses = await _submit_and_poll_single_batch(
            batch,
            display_name=f"{display_name}{suffix}",
            poll_interval=poll_interval,
            timeout=timeout,
        )
        all_responses.extend(responses)

    return all_responses


def _parse_request_id(response_text):
    """Extract request_id from a JSON response string.

    Returns request_id string or None if not found/parseable.
    """
    try:
        parsed = json.loads(response_text)
        rid = parsed.get('request_id', '')
        return rid if rid else None
    except (json.JSONDecodeError, AttributeError):
        return None


def _resolve_metadata(request_id, id_to_metadata):
    """Look up request metadata from a response's request_id.

    Returns (metadata, matched) tuple. If no match found, returns
    a fallback metadata dict with crid=0.
    """
    if request_id and request_id in id_to_metadata:
        return id_to_metadata[request_id], True
    return {"crawl_result_id": "0", "type": "", "website_name": "unknown"}, False


def process_batch_responses(requests, responses, preparations):
    """Map Phase 1 batch responses back to crawl results.

    Uses request_id echoed in the response JSON to match responses to requests,
    since the Gemini Batch API does NOT guarantee response ordering.

    Args:
        requests: list of InlinedRequest (for metadata)
        responses: list of InlinedResponse (unordered)
        preparations: dict of {crawl_result_id: PreparedExtraction}

    Returns:
        tuple of (single_results, chunked_events, failed_ids):
        - single_results: {crawl_result_id: json_string} for single/vision
        - chunked_events: {crawl_result_id: [simple_event_dicts]} for chunks
        - failed_ids: list of crawl_result_ids that completely failed
    """
    # Build lookup from request_id to request metadata
    id_to_metadata = {}
    for req in requests:
        metadata = req.metadata or {}
        rid = metadata.get("request_id", "")
        if rid:
            id_to_metadata[rid] = metadata

    single_results = {}  # crid -> json string
    chunk_events_by_crid = {}  # crid -> list of simple event dicts
    failed_crids = set()
    unmatched_count = 0

    for i, resp in enumerate(responses):
        # For error responses, we can't parse JSON to get request_id
        if resp.error:
            error_msg = resp.error.message if resp.error.message else str(resp.error)
            print(f"    - WARNING: Batch request {i} failed (cannot identify source): {error_msg}")
            continue

        try:
            response_text = resp.response.text.strip() if resp.response and resp.response.text else ""
            if not response_text:
                continue

            # Match response to request via request_id in the JSON
            request_id = _parse_request_id(response_text)
            metadata, matched = _resolve_metadata(request_id, id_to_metadata)

            if not matched:
                unmatched_count += 1
                print(f"    - WARNING: Response {i} has unrecognized request_id: {request_id!r}")
                continue

            crid = int(metadata.get("crawl_result_id", 0))
            req_type = metadata.get("type", "")
            website_name = metadata.get("website_name", "")

            if crid == 0:
                print(f"    - WARNING: Invalid crawl_result_id in metadata for request_id {request_id}")
                continue

            if req_type in ("single", "vision"):
                try:
                    parsed = json.loads(response_text)
                    event_count = len(parsed.get('events', []))
                    print(f"    - {website_name}: {event_count} events extracted")
                except json.JSONDecodeError:
                    response_text = '{"events": []}'
                single_results[crid] = response_text

            elif req_type == "chunk":
                parsed = json.loads(response_text)
                events = parsed.get('events', [])
                if crid not in chunk_events_by_crid:
                    chunk_events_by_crid[crid] = []
                chunk_events_by_crid[crid].extend(events)

        except Exception as e:
            print(f"    - WARNING: Error processing batch response {i}: {e}")

    if unmatched_count:
        print(f"    - WARNING: {unmatched_count} response(s) could not be matched to requests")

    # Apply max_events cap to chunked results
    for crid, events in chunk_events_by_crid.items():
        prep = preparations[crid]
        max_events = prep.max_batches * ENRICHMENT_BATCH_SIZE
        if len(events) > max_events:
            print(f"    - {prep.website_name}: Capping {len(events)} chunked events at {max_events}")
            chunk_events_by_crid[crid] = events[:max_events]
        else:
            print(f"    - {prep.website_name}: {len(events)} events from chunks")

    # Check for chunked crids with zero events (all chunks failed)
    for crid, prep in preparations.items():
        if prep.extraction_type == 'chunked' and crid not in chunk_events_by_crid and crid not in single_results:
            # All chunks failed — store empty result
            single_results[crid] = '{"events": []}'

    return single_results, chunk_events_by_crid, list(failed_crids)


def process_enrichment_responses(requests, responses, chunked_events, preparations):
    """Combine Phase 2 enrichment responses with chunked extraction results.

    Uses request_id echoed in the response JSON to match responses to requests,
    since the Gemini Batch API does NOT guarantee response ordering.

    Args:
        requests: list of enrichment InlinedRequests
        responses: list of InlinedResponse (unordered)
        chunked_events: dict of {crawl_result_id: [simple_event_dicts]}
        preparations: dict of {crawl_result_id: PreparedExtraction}

    Returns:
        dict of {crawl_result_id: json_string} with fully enriched events
    """
    # Build lookup from request_id to request metadata
    id_to_metadata = {}
    for req in requests:
        metadata = req.metadata or {}
        rid = metadata.get("request_id", "")
        if rid:
            id_to_metadata[rid] = metadata

    # Collect enrichments per crawl_result_id
    enrichments_by_crid = {}

    for i, resp in enumerate(responses):
        if resp.error:
            error_msg = resp.error.message if resp.error.message else str(resp.error)
            print(f"    - WARNING: Enrichment batch {i} failed (cannot identify source): {error_msg}")
            continue

        try:
            response_text = resp.response.text.strip() if resp.response and resp.response.text else ""
            if not response_text:
                continue

            # Match response to request via request_id
            request_id = _parse_request_id(response_text)
            metadata, matched = _resolve_metadata(request_id, id_to_metadata)

            if not matched:
                print(f"    - WARNING: Enrichment response {i} has unrecognized request_id: {request_id!r}")
                continue

            crid = int(metadata.get("crawl_result_id", 0))
            website_name = metadata.get("website_name", "")

            if crid == 0:
                continue

            if crid not in enrichments_by_crid:
                enrichments_by_crid[crid] = {}

            result = json.loads(response_text)
            for item in result.get('enrichments', []):
                enrichments_by_crid[crid][item.get('name', '')] = {
                    'description': item.get('description', ''),
                    'hashtags': item.get('hashtags', []),
                    'emoji': item.get('emoji', '📅'),
                }
        except Exception as e:
            print(f"    - WARNING: Error processing enrichment response {i}: {e}")

    # Combine chunked events with enrichments
    results = {}
    for crid, events in chunked_events.items():
        enrichments = enrichments_by_crid.get(crid, {})
        results[crid] = _combine_chunked_results(events, enrichments)
        prep = preparations[crid]
        enriched_count = sum(1 for e in events if e['name'] in enrichments)
        print(f"    - {prep.website_name}: Combined {len(events)} events ({enriched_count} enriched)")

    return results


async def run_batch_extraction(extraction_queue, poll_interval=None, timeout=None):
    """Run extraction for all queued items using the Gemini Batch API.

    Two-phase process:
      Phase 1: All extractions (single, vision, chunk) in one batch
      Phase 2: Enrichment for chunked results in a second batch

    Args:
        extraction_queue: list of dicts with crawl_result_id, name, notes, etc.
        poll_interval: Seconds between batch status checks
        timeout: Maximum seconds to wait per batch

    Returns:
        list of (crawl_result_id, success) tuples
    """
    results = []
    preparations = {}

    # Phase 0: Prepare all extraction requests
    print(f"\n  Preparing {len(extraction_queue)} extraction request(s)...")

    conn = db.create_connection()
    if not conn:
        print("  Failed to connect to database for batch preparation")
        return [(item['crawl_result_id'], False) for item in extraction_queue]
    cursor = conn.cursor(buffered=True)

    resolved_results = {}  # crid -> json string (for pre-resolved items)

    try:
        for item in extraction_queue:
            crid = item['crawl_result_id']
            prep = await prepare_extraction(
                cursor, crid, item['name'], item.get('notes', ''),
                item.get('use_vision', False), item.get('base_url', ''),
                item.get('max_batches')
            )

            if prep.error:
                print(f"    - {item['name']}: {prep.error}")
                db.update_crawl_result_failed(cursor, conn, crid, prep.error)
                results.append((crid, False))
            elif prep.resolved_result is not None:
                resolved_results[crid] = prep.resolved_result
                preparations[crid] = prep  # Keep for result tracking
            else:
                preparations[crid] = prep
    finally:
        cursor.close()
        conn.close()

    if not preparations and not resolved_results:
        return results

    # Store pre-resolved results immediately
    if resolved_results:
        conn = db.create_connection()
        cursor = conn.cursor(buffered=True)
        try:
            for crid, result_text in resolved_results.items():
                db.update_crawl_result_extracted(cursor, conn, crid, result_text)
                results.append((crid, True))
                print(f"    - {preparations[crid].website_name}: Stored pre-resolved result")
        finally:
            cursor.close()
            conn.close()
        # Remove resolved items from preparations (no batch requests needed)
        for crid in resolved_results:
            del preparations[crid]

    if not preparations:
        return results

    # Phase 1: Build and submit extraction batch
    batch_requests = build_batch_requests(preparations)
    if not batch_requests:
        return results

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    phase1_responses = await submit_and_poll_batch(
        batch_requests,
        display_name=f"fomo-extract-{timestamp}",
        poll_interval=poll_interval,
        timeout=timeout,
    )

    single_results, chunked_events, failed_ids = process_batch_responses(
        batch_requests, phase1_responses, preparations
    )

    # Phase 2: Enrichment for chunked results
    enriched_results = {}
    if chunked_events:
        enrichment_requests = build_enrichment_requests(chunked_events, preparations)
        if enrichment_requests:
            print(f"\n  Phase 2: Enriching {sum(len(e) for e in chunked_events.values())} "
                  f"events in {len(enrichment_requests)} batch(es)...")
            phase2_responses = await submit_and_poll_batch(
                enrichment_requests,
                display_name=f"fomo-enrich-{timestamp}",
                poll_interval=poll_interval,
                timeout=timeout,
            )
            enriched_results = process_enrichment_responses(
                enrichment_requests, phase2_responses, chunked_events, preparations
            )
        else:
            # No enrichment needed — combine with empty enrichments
            for crid, events in chunked_events.items():
                enriched_results[crid] = _combine_chunked_results(events, {})

    # Phase 3: Store all results in database
    all_results = {**single_results, **enriched_results}
    if all_results:
        conn = db.create_connection()
        cursor = conn.cursor(buffered=True)
        try:
            for crid, result_text in all_results.items():
                db.update_crawl_result_extracted(cursor, conn, crid, result_text)
                results.append((crid, True))
        finally:
            cursor.close()
            conn.close()

    # Mark failed items
    if failed_ids:
        conn = db.create_connection()
        cursor = conn.cursor(buffered=True)
        try:
            for crid in failed_ids:
                db.update_crawl_result_failed(cursor, conn, crid, "Batch extraction failed")
                results.append((crid, False))
        finally:
            cursor.close()
            conn.close()

    return results
