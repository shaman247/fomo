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
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from typing import Optional
from urllib.parse import urljoin

import httpx
from dotenv import load_dotenv
from PIL import Image
from pydantic import BaseModel, Field, field_validator

import city_config
import constants
import db
import site_profiles
from processor import _standardize_time, extract_url_from_content


_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_CANONICAL_TIME_RE = re.compile(r'^\d{1,2}(:\d{2})?(am|pm)$')


def _clean_extracted_date(value):
    """Field validator: keep only YYYY-MM-DD strings, drop everything else.

    Gemini occasionally emits a free-form blob (e.g. a paragraph of description text)
    in a date field. Reject these silently so the row keeps its other fields.
    """
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        if _DATE_RE.fullmatch(v):
            return v
    return None


def _clean_extracted_time(value):
    """Field validator: canonicalize Gemini-emitted time strings.

    Routes the value through `_standardize_time`. If the result isn't a recognizable
    time (e.g. Gemini hallucinated 'pulitzerprizewinning' or a YYYY-MM-DD date into
    a time field), we return None rather than persisting garbage.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    canonical = _standardize_time(value)
    if not canonical:
        return None
    # Accept only the canonical shape. The standardizer preserves ambiguous strings
    # like '6:30' for downstream manual review; reject those at the extractor since
    # Gemini should have included AM/PM if the source did.
    if _CANONICAL_TIME_RE.fullmatch(canonical):
        return canonical
    return None

load_dotenv()

try:
    from google import genai
    from google.genai.types import InlinedRequest, GenerateContentConfig
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
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
    start_date: Optional[str] = Field(
        default=None,
        description="REQUIRED — the date of this occurrence in YYYY-MM-DD format (e.g. 2026-06-15). Set to null only if no specific date is given."
    )
    start_time: Optional[str] = Field(
        default=None,
        description="The start time as a clock time in 12-hour AM/PM format only (e.g. '7pm', '7:30pm', '11am'). Leave null if no specific time is given."
    )
    end_date: Optional[str] = Field(
        default=None,
        description="The end date if different from start_date, in YYYY-MM-DD format. "
                    "REQUIRED for multi-day events and for art exhibitions / gallery "
                    "shows / installations that run over a period — set it to the "
                    "closing date (e.g. 'On view through July 5' -> end_date "
                    "2026-07-05). Leave null only for genuinely single-day events."
    )
    end_time: Optional[str] = Field(
        default=None,
        description="The end time as a clock time in 12-hour AM/PM format only (e.g. '7pm', '9:30pm'). Leave null if no end time is given."
    )

    _v_start_date = field_validator('start_date', mode='before')(_clean_extracted_date)
    _v_end_date = field_validator('end_date', mode='before')(_clean_extracted_date)
    _v_start_time = field_validator('start_time', mode='before')(_clean_extracted_time)
    _v_end_time = field_validator('end_time', mode='before')(_clean_extracted_time)


class Event(BaseModel):
    """Schema for a single event extracted from website content."""
    name: str = Field(description="The name of the event")
    location: str = Field(description="The venue name ONLY — exact spelling, no typos. If the source lists '<Branch>, <Room>' (e.g. 'Highlawn, Meeting Room'), the branch is the location and the room belongs in sublocation — never concatenate them.")
    sublocation: Optional[str] = Field(
        default=None,
        description="Optional location within the venue (e.g., rooftop, 5th floor, specific meeting room)"
    )
    occurrences: Optional[list[EventOccurrence]] = Field(
        default=None,
        description="List of date/time occurrences for this event, or null if no date information is provided on the page. Include ALL specific dates if the event repeats. Do NOT fabricate dates — use null if no dates are found."
    )
    description: str = Field(description="A 1-3 sentence description of the event based ONLY on what is stated in the source content. If no descriptive details are provided beyond the event name, use 'No description available.' Do NOT fabricate or infer descriptions.")
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
    start_date: Optional[str] = Field(
        default=None,
        description="REQUIRED — YYYY-MM-DD format. Null only if no specific date given; never a non-date value."
    )
    start_time: Optional[str] = Field(
        default=None,
        description="12-hour clock time only, e.g. '8pm', '8:30pm', '10am'."
    )
    end_date: Optional[str] = Field(
        default=None,
        description="Closing date of a CONTINUOUS multi-day run, YYYY-MM-DD. Use ONLY "
                    "when the page states a range for something that runs every day in "
                    "between — an art exhibition / gallery show / installation ('On view "
                    "through July 5' -> end_date 2026-07-05) or a multi-day festival. "
                    "NEVER use it to summarise a list of separate dates: if the page "
                    "enumerates individual dates or showtimes (a film's play dates, "
                    "'Jan 11, 18, 25'), emit ONE occurrence PER DATE with end_date null. "
                    "Leave null for single-day events."
    )
    end_time: Optional[str] = Field(
        default=None,
        description="12-hour clock time only, e.g. '10pm'."
    )

    _v_start_date = field_validator('start_date', mode='before')(_clean_extracted_date)
    _v_start_time = field_validator('start_time', mode='before')(_clean_extracted_time)
    _v_end_date = field_validator('end_date', mode='before')(_clean_extracted_date)
    _v_end_time = field_validator('end_time', mode='before')(_clean_extracted_time)


class SimpleEvent(BaseModel):
    """Simplified event schema for first-pass extraction on large pages."""
    name: str
    location: str
    occurrences: Optional[list[SimpleOccurrence]] = Field(
        default=None,
        description="List of date/time occurrences, or null if no date information is provided on the page. Do NOT fabricate dates."
    )
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
    description: str = Field(description="1-3 sentence description based ONLY on source content. If no details available beyond the event name, use 'No description available.' Do NOT fabricate.")
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

# When a chunked extraction yields more events than the website's max_batches
# allows, the sync path auto-raises websites.max_batches (ceil(N/30)+1, the same
# formula triage applied by hand) instead of silently dropping events — but never
# above this ceiling, so a runaway page can't burn unbounded enrichment quota.
# Websites deliberately throttled BELOW the default are never auto-bumped.
AUTO_MAX_BATCHES_CEILING = 40

# Timeout per chunk (seconds) - increased for large pages that can't be chunked
CHUNK_TIMEOUT = 300

# Maximum characters per chunk when falling back to character-based chunking
MAX_CHUNK_CHARS = 30000

# Hard limit on total content size before extraction (characters).
# Pages exceeding this will be truncated. 300K chars ≈ 10 chunks of 30K,
# accommodating multi-week event aggregators like NYC Parks date-windowed
# crawls. Prevents runaway extraction on pages with huge archives.
MAX_CONTENT_CHARS = 300000

# Maximum number of images to process for vision extraction
MAX_VISION_IMAGES = 10

# Maximum image dimension (images will be resized if larger)
MAX_IMAGE_DIMENSION = 1024

# Batch API settings
BATCH_POLL_INTERVAL = int(os.environ.get("BATCH_POLL_INTERVAL", "30"))  # seconds
BATCH_TIMEOUT = int(os.environ.get("BATCH_TIMEOUT", "86400"))  # 24 hour default
BATCH_TOKEN_LIMIT = int(os.environ.get("BATCH_TOKEN_LIMIT", "10000000"))  # Tier 1 limit for Flash models
CHARS_PER_TOKEN = 3  # conservative estimate (Gemini tokenizer averages ~3 chars/token for mixed content)
# Maximum estimated tokens per individual request. Typical prompts are 40K-55K tokens.
# Gemini's context window is 1M tokens, but we cap at 100K to catch data bugs early
# (the largest legitimate prompt is ~55K tokens, so 100K gives ~2x headroom for growth
# while still catching runaway inputs well before they hit the API limit).
MAX_REQUEST_TOKENS = int(os.environ.get("MAX_REQUEST_TOKENS", "100000"))


# =============================================================================
# Extraction failure signals
# =============================================================================

class ExtractionCallFailure(RuntimeError):
    """A Gemini call failed outright, so this extraction produced no answer.

    The distinction that matters downstream is "the page has no events" versus
    "we never got to ask". Both used to be stored as `{"events": []}` with
    status='processed', which is a lie the rest of the pipeline believes: the
    zero becomes the website's newest successful crawl, so it wipes the site's
    last good result, feeds archival as evidence that every event is gone, and
    hides the outage from triage. On 2026-07-21 a ~2-minute Gemini outage stored
    21 such zeros across 15 websites; 16 of them were still stale five days
    later.

    Raising instead routes the result to db.update_crawl_result_failed
    (status='failed'), which preserves crawled_content — so `main.py --ids <id>`
    can re-extract the same content the same day without re-crawling — and keeps
    the poisoned zero out of archival.
    """


class ChunkedExtractionFailure(ExtractionCallFailure):
    """A chunked extraction returned nothing because its chunk calls failed."""


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
    content: Optional[str] = None  # Original page content for enrichment context

    # Shared
    url: str = ""
    notes: str = ""
    website_id: Optional[int] = None

    # Pre-resolved result (set if no API call needed, e.g., vision with no images)
    resolved_result: Optional[str] = None

    # Content fingerprint match: if set, copy crawl_events from this prior crawl
    # instead of calling Gemini. Used when the new crawl produced identical
    # content_hash to a previously-processed crawl.
    copy_from_crawl_result_id: Optional[int] = None
    skip_extraction_reason: Optional[str] = None

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
        # Some image CDNs 403 the default httpx user-agent. Use a real browser
        # UA + any platform-specific headers so vision extraction can actually
        # fetch the bytes. See site_profiles.image_headers_for.
        headers = {
            "User-Agent": constants.get_user_agent(),
            "Accept": "image/webp,image/avif,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        }
        headers.update(site_profiles.image_headers_for(url))
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
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
- description: Brief description of the event based on what you see. If the image provides no descriptive details beyond the event name, use "No description available." Do NOT fabricate.
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

def chunk_content_by_events(content, events_per_chunk=EVENTS_PER_CHUNK,
                            max_chars=None):
    """
    Split content into chunks based on event markers.

    Looks for common event patterns like numbered markdown headers (### [Event Name])
    and splits content so each chunk has approximately events_per_chunk events.

    When `max_chars` is given, a chunk is also closed once it grows past that
    size. The size guard matters because event density varies enormously: a
    cinema/box-office page can pack 50 markers plus hundreds of showtime lines
    into one 34K chunk, and Gemini then exhausts its output budget partway
    through and silently drops the REST of that chunk's events (Film Forum w50:
    50 markers in one 34,260-char chunk -> 18 of 50 extracted, while the 428-char
    tail chunk extracted 3 of 3). Splitting on size keeps each call's output
    within budget.

    Splits only ever happen AT a marker line, so a single event's content is
    never cut in half — an oversized run with no internal markers is left intact.

    `max_chars=None` (the default) disables the size guard. chunk_content() uses
    that uncapped form to decide WHETHER a page is event-chunkable at all, so
    that adding the guard cannot flip a page from size-based to event-based
    chunking — it only subdivides pages already on the event path.

    Returns a list of content strings, one per chunk.
    """
    lines = content.split('\n')
    chunks = []
    current_chunk = []
    event_count = 0
    current_size = 0

    for line in lines:
        # Event marker pattern: numbered list item with ### header, or standalone ### header
        if re.match(r'^\s*\d+\.\s*###\s*\[', line) or line.strip().startswith('### ['):
            oversized = max_chars is not None and current_size >= max_chars
            if current_chunk and (event_count >= events_per_chunk or oversized):
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                event_count = 0
                current_size = 0
            event_count += 1
        current_chunk.append(line)
        current_size += len(line) + 1

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
    # First try event-based chunking. Method selection uses the UNCAPPED split
    # (marker count only) so the size guard below can never promote a page from
    # size-based to event-based chunking — it only subdivides pages that were
    # already going to be event-chunked.
    event_chunks = chunk_content_by_events(content, events_per_chunk)

    # If we got multiple chunks, use them — but re-split with the size guard when
    # any chunk is too big for Gemini to answer in one response. The common case
    # (no oversized chunk) skips the second pass and is byte-for-byte unchanged.
    if len(event_chunks) > 1:
        if any(len(chunk) > max_chars for chunk in event_chunks):
            event_chunks = chunk_content_by_events(content, events_per_chunk, max_chars)
        return event_chunks, 'events'

    # If single chunk is small enough, use it
    if len(content) <= max_chars:
        return [content], 'single'

    # Fall back to size-based chunking
    size_chunks = chunk_content_by_size(content, max_chars)
    return size_chunks, 'size'


# =============================================================================
# Extraction Functions
# =============================================================================

def estimate_event_count(content):
    """
    Estimate the number of events on a page using pattern matching.
    Returns a rough estimate to decide whether to use chunked extraction.

    Signals are combined with max() (not summed) so overlapping signals on the
    same page don't inflate the estimate and push small pages into the more
    expensive chunked mode. Under-estimation is the dangerous direction: a
    many-event page routed to single-call mode hits the ~8K output-token cap
    and the extraction silently collapses to a fraction of the real events.
    """
    date_count = len(re.findall(
        r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}',
        content, re.IGNORECASE
    ))
    view_event_count = len(re.findall(r'View\s+Event|View\s+Details|More\s+Info', content, re.IGNORECASE))
    event_url_count = len(re.findall(r'/events?/[^/\s"\']+', content))
    listing_url_count = len(re.findall(r'/listings?/[^/\s"\']+', content))

    # ISO-format date lines: calendar exports and synthetic cards emit one
    # `Date: 2026-06-14` (or a bare `2026-06-14` line start) per event card,
    # so these are counted unhalved.
    iso_date_line_count = len(re.findall(
        r'^[ \t>*_-]*(?:(?:Dates?|When)[:*_ \t]+)?\d{4}-\d{2}-\d{2}\b',
        content, re.MULTILINE | re.IGNORECASE
    ))

    # Cinema/box-office listings: each film-day entry links to one /booking/
    # page (one link per entry, so unhalved), and/or carries one
    # "Buy Tickets" link per showtime (several showtimes per entry, halved).
    booking_url_count = len(re.findall(r'/booking/[^/\s"\']+', content))
    ticket_link_count = len(re.findall(r'Buy\s+Tickets?|Get\s+Tickets?|Book\s+Now', content, re.IGNORECASE))

    # `EVENT DETAIL URL:` markers are injected by our own js_code exactly
    # once per event card.
    detail_marker_count = len(re.findall(r'EVENT\s+DETAIL\s+URL:', content))

    # Markdown linked headings (`### [Title](url)` .. `##### [...]`) mark one
    # event card each on most listing pages; `##` is excluded as it is mostly
    # navigation. Halved since some sites also use them for non-event sections.
    linked_heading_count = len(re.findall(
        r'^[ \t]*(?:[\*\-]\s+|\d+\.\s+)?#{3,5}\s*\[[^\]\s]',
        content, re.MULTILINE
    ))

    # Dates may appear 2x per event (heading + details), so halve them
    return max(
        date_count // 2,
        view_event_count,
        event_url_count // 2,
        listing_url_count // 2,
        iso_date_line_count,
        booking_url_count,
        ticket_link_count // 2,
        detail_marker_count,
        linked_heading_count // 2,
    )


# =============================================================================
# "No events" veto guard
# =============================================================================
#
# The `no_events_patterns` short-circuit in prepare_extraction is a PAGE-level
# veto: a literal "No Upcoming Events" anywhere in the first 15K chars stops
# Gemini being called at all and stores a bare `{"events": []}`. That is exactly
# right for a genuinely empty calendar (it saves real Gemini spend) and exactly
# wrong for a page that renders a POPULATED widget plus a second empty one —
# the empty widget's i18n string vetoes the whole document and the crawl looks
# like a perfectly healthy 0-event result.
#
# Measured failure: w618 Freshkills renders three dated Tribe cards followed by
# an embedded Eventbrite widget reading "No Upcoming Events at this time.";
# four consecutive good crawls were discarded before a per-site js_code
# workaround landed on 2026-07-26.
#
# has_event_evidence() is the guard. It is deliberately conservative — measured
# over 60 days of crawls (26,597 results) the veto fired 206 times and this
# guard spares only 9 of them, all three websites verified as real false
# vetoes (618 Freshkills, 4123 Scenic Hudson, 995 The Nonbinarian Bookstore).
# The remaining 197 are cleanly separated: 196 have ZERO future-dated mentions.

# Injected by our own js_code / source plugins, exactly once per event card.
_DETAIL_URL_MARKER_RE = re.compile(r'EVENT\s+DETAIL\s+URL:', re.IGNORECASE)

# Fully-qualified dates (day AND year). A bare "July 25" is not enough — page
# furniture and past-event archives are full of those; a year pins the mention
# to a specific day we can test against today.
_MONTH_ABBREVS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}
_MONTH_DAY_YEAR_RE = re.compile(
    r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+'
    r'(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})\b', re.IGNORECASE)
_ISO_DATE_RE = re.compile(r'\b(20\d{2})-(\d{1,2})-(\d{1,2})\b')
_NUMERIC_DATE_RE = re.compile(r'\b(\d{1,2})/(\d{1,2})/(20\d{2})\b')

# Two dated mentions, not two DISTINCT dates: a one-day festival legitimately
# lists several cards on the same date (Freshkills' three City of Water Day
# events all read "July 25, 2026").
MIN_DATED_MENTIONS_FOR_EVIDENCE = 2


def _future_dated_mentions(content, today=None):
    """Count fully-qualified date mentions that are today or later."""
    today = today or datetime.now().date()
    count = 0
    for m in _MONTH_DAY_YEAR_RE.finditer(content):
        try:
            parsed = date(int(m.group(3)), _MONTH_ABBREVS[m.group(1).lower()[:3]],
                          int(m.group(2)))
        except (ValueError, KeyError):
            continue
        if parsed >= today:
            count += 1
    for rx, order in ((_ISO_DATE_RE, (1, 2, 3)), (_NUMERIC_DATE_RE, (3, 1, 2))):
        for m in rx.finditer(content):
            try:
                parsed = date(int(m.group(order[0])), int(m.group(order[1])),
                              int(m.group(order[2])))
            except ValueError:
                continue
            if parsed >= today:
                count += 1
    return count


def has_event_evidence(page_content, today=None):
    """True when the page shows positive evidence that real events are listed.

    Used to veto the veto: `prepare_extraction`'s "no events" short-circuit must
    not fire on a page that is visibly full of events. Three signals, any one of
    which is enough:

      1. `EVENT DETAIL URL:` markers — emitted once per card by our own js_code
         and source plugins, so their presence is unambiguous.
      2. A populated Squarespace `?format=json` `upcoming[]` array. Squarespace
         embeds the i18n string "There are no upcoming events at this time."
         even when the array is full; this was the original narrow escape hatch.
      3. At least MIN_DATED_MENTIONS_FOR_EVIDENCE fully-qualified dates (day +
         year) that are today or later. Past-only dates don't count — a
         genuinely empty calendar with a past-events archive still gets vetoed.
    """
    if not page_content:
        return False
    if _DETAIL_URL_MARKER_RE.search(page_content):
        return True
    if '"upcoming":[{' in page_content:
        return True
    return _future_dated_mentions(page_content, today) >= MIN_DATED_MENTIONS_FOR_EVIDENCE


# Markdown markers that signal the start of a new event card on a listing page.
# Covers `### [...]`, `#### [...]`, and bulleted/numbered variants like
# `* ### [...]` or `1. ### [...]`.
_EVENT_HEADING_RE = re.compile(
    r'(?:^|\n)[ \t]*(?:[\*\-]\s+|\d+\.\s+)?#{2,5}\s*\[',
    re.MULTILINE,
)


def extract_content_snippets(event_names, content, snippet_chars=500):
    """Extract content snippets surrounding each event name from page content.

    For each event name, finds its position in the content and extracts the
    surrounding text bounded by adjacent event headings, so neighboring events'
    descriptions don't leak into the focal event's context. Returns a dict
    mapping event names to snippets.
    """
    if not content:
        return {}

    # Pre-compute heading positions so we can bound each snippet to a single event.
    heading_positions = sorted({m.start() for m in _EVENT_HEADING_RE.finditer(content)})

    content_lower = content.lower()
    snippets = {}

    for name in event_names:
        # Try exact match first, then case-insensitive
        pos = content.find(name)
        if pos == -1:
            pos = content_lower.find(name.lower())
        if pos == -1:
            # Try matching first significant words (skip short words)
            words = [w for w in name.split() if len(w) > 3]
            if words:
                # Search for the first long word to get approximate position
                pos = content_lower.find(words[0].lower())

        if pos == -1:
            continue

        # Find the nearest event heading at/before pos and the next one after.
        prev_heading = 0
        next_heading = len(content)
        for hp in heading_positions:
            if hp <= pos:
                prev_heading = hp
            else:
                next_heading = hp
                break

        # Cap by the char budget so very long entries don't dominate the prompt.
        start = max(prev_heading, pos - snippet_chars // 4)
        end = min(next_heading, pos + snippet_chars)

        snippet = content[start:end].strip()
        if snippet:
            snippets[name] = snippet

    return snippets


_BOILERPLATE_DESC_PATTERNS = [
    # Pure "visit the website" deflections
    re.compile(r'please\s+visit\s+the\s+official\s+website', re.IGNORECASE),
    re.compile(r'visit\s+the\s+official\s+website\s+for\s+(?:more\s+)?(?:specific\s+)?(?:event\s+)?details', re.IGNORECASE),
    re.compile(r'check\s+the\s+official\s+website\s+for\s+(?:more\s+)?(?:specific\s+)?details', re.IGNORECASE),
    re.compile(r'more\s+specific\s+event\s+details', re.IGNORECASE),
    re.compile(r'for\s+more\s+(?:event\s+)?details(?:\s+about\s+(?:the\s+event|this\s+event))?', re.IGNORECASE),
    # Generic "is a … community/special event" boilerplate
    re.compile(r'\bis\s+a(?:n)?\s+(?:local|special|recurring|informational|community)\s+(?:community\s+)?event\b', re.IGNORECASE),
    re.compile(r'\bis\s+a\s+community\s+(?:gathering|event)\b', re.IGNORECASE),
]


def _looks_like_boilerplate_fabrication(desc):
    """Detect descriptions that are obviously generic fillers Gemini wrote when
    the page had no real content. Conservative — only matches phrases that
    legitimate event descriptions almost never include verbatim."""
    if not desc:
        return False
    return any(p.search(desc) for p in _BOILERPLATE_DESC_PATTERNS)


def get_enrichment_prompt(event_names, venue_name, request_id="", content_snippets=None):
    """Generate prompt for enriching events with descriptions, hashtags, and emoji."""
    rid_section = f"\n\nIMPORTANT: Set request_id to \"{request_id}\" in your response." if request_id else ""

    content_snippets = content_snippets or {}
    events_section_parts = []
    for name in event_names:
        snippet = content_snippets.get(name)
        if snippet:
            events_section_parts.append(f"- {name}\n  Context: {snippet}")
        else:
            events_section_parts.append(f"- {name}")
    events_section = "\n".join(events_section_parts)

    return f'''For each event at {venue_name}, provide:
- description: 1-3 sentence description built from words and sentences that actually appear in the event's own Context block. If the Context only has the name, date/time, venue, and links — with no descriptive prose — return EXACTLY "No description available." Do NOT paraphrase the event name. Do NOT write generic filler like "is a local community event" or "visit the official website for more details". Do NOT use background knowledge about the artist, venue, or topic. Each event's description must come from THAT event's Context block, not a neighbor's.
- hashtags: 4-7 CamelCase tags. Always include at least one category (Music, Nightlife, Comedy, Art, Theater, Dance, Film, Literature, Community, Family, Wellness, Education, Outdoor, Sports, Games). Add Free if free, Virtual if online. Then granular tags.
- emoji: Single emoji representing the event

Examples:
  Context only has name + date + venue → description="No description available."
  Context has a sentence describing the event → use that sentence (lightly compressed if needed)

Events to enrich:
{events_section}
{rid_section}
Return a JSON object with "enrichments" key mapping each event name to its enrichment data.'''


async def enrich_events_batch(event_names, venue_name, content=None):
    """
    Enrich a batch of events with descriptions, hashtags, and emoji.

    If content is provided, extracts relevant snippets around each event name
    to give the AI context for writing descriptions.

    Returns a dict mapping event names to enrichment data.
    """
    if not event_names:
        return {}

    content_snippets = extract_content_snippets(event_names, content) if content else None
    prompt = get_enrichment_prompt(event_names, venue_name, content_snippets=content_snippets)

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
        out = {}
        for item in result.get('enrichments', []):
            desc = (item.get('description') or '').strip()
            if _looks_like_boilerplate_fabrication(desc):
                desc = 'No description available.'
            out[item.get('name', '')] = {
                'description': desc,
                'hashtags': item.get('hashtags', []),
                'emoji': item.get('emoji', '📅'),
            }
        return out
    except Exception as e:
        print(f"    - Enrichment batch error: {e}")
        return {}


class SingleEventExtraction(BaseModel):
    """Schema for extracting event details from a single event page."""
    description: str = Field(
        description="1-3 sentence description based ONLY on source content. "
                    "If no details available beyond the event name, use "
                    "'No description available.' Do NOT fabricate."
    )
    location: Optional[str] = Field(
        default=None,
        description="The venue name ONLY — exact spelling, no typos. If the source "
                    "lists '<Branch>, <Room>' (e.g. 'Highlawn, Meeting Room'), the "
                    "branch is the location and the room belongs in sublocation — "
                    "never concatenate them. Null if not specified on the page."
    )
    sublocation: Optional[str] = Field(
        default=None,
        description="Optional location within the venue (e.g., rooftop, 5th floor, specific meeting room)"
    )
    occurrences: Optional[list[EventOccurrence]] = Field(
        default=None,
        description="List of date/time occurrences for this event. Set to null "
                    "if no specific calendar dates are explicitly stated on the "
                    "page. Do NOT fabricate dates, do NOT use today's date as a "
                    "fallback, and do NOT approximate from descriptive text "
                    "like 'spring' or 'ongoing'. For permanent exhibits, "
                    "ongoing installations, or pages describing recurring "
                    "weekly schedules without a specific calendar date, return null."
    )
    hashtags: list[str] = Field(
        description="4-7 CamelCase tags. Include at least one category "
                    "(Music, Nightlife, Comedy, Art, Theater, Dance, Film, "
                    "Literature, Community, Family, Wellness, Education, "
                    "Outdoor, Sports, Games), Free if free, Virtual if online, "
                    "plus granular tags"
    )
    emoji: str = Field(description="Single emoji representing the event")


async def extract_single_event(event_name, content):
    """
    Extract event details from a single event page.

    Used by the detail crawl step for events that got "No description
    available." or missing location/times from the listing page. Uses Gemini
    structured output for reliable parsing.

    Returns dict with 'description', 'hashtags', 'emoji', and optionally
    'location', 'sublocation', 'occurrences', or None on failure.
    """
    if not genai_client:
        return None

    current_date = datetime.now().strftime("%Y-%m-%d")
    prompt = (
        f'Today\'s date is {current_date}. '
        f'Extract information about the event "{event_name}" from this web page. '
        f'Include the venue name if it appears on the page.\n\n'
        f'CRITICAL — DESCRIPTION: The description MUST be derived from words '
        f'and sentences actually present on the page. If the page only contains '
        f'the event name, date/time, venue, and links (no descriptive prose), '
        f'set description to exactly "No description available." Do NOT '
        f'paraphrase the event name. Do NOT write generic filler like "is a '
        f'local community event" or "visit the official website for more '
        f'details". Do NOT use background knowledge about the artist, venue, '
        f'or topic. If you would only be guessing, return "No description '
        f'available." instead.\n\n'
        f'CRITICAL: Only return occurrences for SPECIFIC calendar dates that are '
        f'EXPLICITLY stated on the page. If the page describes a permanent '
        f'exhibit, ongoing installation, recurring schedule (e.g. "Fridays 7pm"), '
        f'or has no specific date listed, return occurrences=null. Do NOT '
        f'fabricate dates, do NOT default to today, do NOT approximate from '
        f'descriptive text like "spring 2026" or "ongoing". An approximate or '
        f'invented date is worse than no date.\n\n'
        f'OCCURRENCES = WHEN THE EVENT ITSELF HAPPENS. If the page lists a '
        f'multi-day schedule that mixes the actual event with preparatory or '
        f'ancillary days (e.g. expo, packet/bib pickup, registration, vendor '
        f'setup, rehearsal, soundcheck, load-in, after-party, awards ceremony), '
        f'return ONLY the day(s) the event itself takes place. Pickup/expo/setup '
        f'days are logistics, not occurrences of the event. Example: a race page '
        f'showing "Wed-Fri Expo / Sat Race" should return only Saturday.\n\n'
        f'RECEPTION vs EXHIBITION RUN: If the named event is an opening/closing '
        f'reception, opening night, preview, or launch tied to an exhibition, '
        f'occurrences = ONLY that reception\'s own date and time (a single-day '
        f'event). Do NOT add the exhibition\'s broader on-view run (e.g. "on view '
        f'June 4 – July 10") as an additional occurrence — that run belongs to the '
        f'exhibition itself, which is a separate event.\n\n'
        f'{content}'
    )

    try:
        response = await asyncio.wait_for(
            genai_client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": SingleEventExtraction,
                },
            ),
            timeout=30,
        )
        data = json.loads(response.text.strip())
        desc = data.get('description', '').strip().strip('"')
        if not desc or 'No description available' in desc:
            return None
        if _looks_like_boilerplate_fabrication(desc):
            return None
        result = {
            'description': desc,
            'hashtags': data.get('hashtags', []),
            'emoji': data.get('emoji', ''),
        }
        # Include location if extracted
        location = data.get('location')
        if location and location.strip().lower() not in ('', 'null', 'not specified', 'none'):
            result['location'] = location.strip()
        sublocation = data.get('sublocation')
        if sublocation and sublocation.strip().lower() not in ('', 'null', 'not specified', 'none'):
            result['sublocation'] = sublocation.strip()
        # Include occurrences if extracted
        occurrences = data.get('occurrences')
        if occurrences:
            result['occurrences'] = occurrences
        return result
    except Exception as e:
        print(f"    - AI error for {event_name}: {e}")
        return None


def get_chunk_prompt(chunk_text, current_date_string, notes, request_id=""):
    """Generate prompt for a single chunk extraction."""
    note_section = f"\n\nIMPORTANT: {notes}" if notes else ""
    rid_section = f"\n\nIMPORTANT: Set request_id to \"{request_id}\" in your response." if request_id else ""
    return f'''{city_config.extraction_chunk_intro().format(date=current_date_string)}

For each event provide: name, location (venue name), occurrences (array of start_date in YYYY-MM-DD, start_time, end_date, end_time), and url if available.

CRITICAL DATE RULES:
- Only return occurrences for SPECIFIC calendar dates EXPLICITLY shown on the page near the event (e.g. "May 7, 2026", "Sat Jun 14", "9/22").
- EXHIBITIONS: for an art exhibition / gallery show / installation with a stated date range ("March 1 – July 5", "On view through June 30"), return ONE occurrence with start_date = opening date and end_date = closing date. Never collapse the run to a single day, and never stamp today's date as the exhibition date. An exhibition whose OPENING date has already passed is STILL on view as long as its closing date is today or later — keep it, using the original (past) opening date as start_date; do NOT null it or skip it because it already opened.
- RECEPTION vs RUN: a timed opening/closing reception, opening night, or preview is a SEPARATE single-day event, NOT an occurrence of the exhibition. If a page lists both a dated+timed reception and a broader exhibition run, emit TWO events — the reception (one single-day occurrence: its date + time) and the exhibition (one start→end run occurrence) — never the full run as a second occurrence of the reception, and never the reception's time on the run.
- If an event is described as "monthly", "weekly", "ongoing", "permanent", "recurring", or has no specific date listed, set occurrences=null. Do NOT invent a next-occurrence date.
- A LIST of specific calendar dates is NOT "recurring" — when the page enumerates actual dates (e.g. "June 18, June 19, June 20, ...", a film's showtimes across many days, or "Jan 11, 18, 25"), emit EACH listed date as its own occurrence. The null-occurrences rule above applies ONLY when a cadence is described in words ("weekly", "every Thursday") WITHOUT the dates being listed, or when no dates appear at all. A missing start_time NEVER justifies dropping a date that IS shown — set start_time to null and keep the date.
- NEVER collapse an enumerated list of dates into one start_date/end_date range. end_date is ONLY for something that genuinely runs every day in between (an exhibition run, a multi-day festival). A film playing on 12 listed dates is TWELVE occurrences with end_date null — NOT one occurrence spanning first-to-last. Collapsing is wrong even when the dates look contiguous, and it silently invents dates whenever the list has gaps (a film showing Aug 10-13 and Aug 17-20 must never become Aug 10 -> Aug 20).
- Do NOT default to today's date when no date is listed.
- Do NOT extract dates from URLs or Google Calendar/iCal links — those often reference past instances. Only use dates visible in the page text adjacent to the event.
- Past dates (before today) should also be set to null — those events have already happened. EXCEPTION: a multi-day exhibition / gallery show / installation whose closing date (end_date) is today or later is still on view — keep its original (past) opening date as start_date and its closing date as end_date; do NOT null it.
- An empty/null occurrences field is much better than a fabricated date.
{note_section}{rid_section}
Website content:

{chunk_text}'''


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

    # Format existing events as JSON for prompt (with size guardrails)
    existing_events_section = ""
    if existing_events:
        # Trim occurrences to max 3 per event — we only need these for naming
        # consistency, not full scheduling data. This prevents prompt bloat from
        # highly-recurring events (e.g., library programs with 100s of occurrences).
        trimmed = []
        for ev in existing_events:
            trimmed_ev = {k: v for k, v in ev.items() if k != 'occurrences'}
            occs = ev.get('occurrences', [])
            trimmed_ev['occurrences'] = occs[:3]
            trimmed.append(trimmed_ev)
        existing_events_json = json.dumps(trimmed, indent=2)

        # Hard cap: if existing events JSON still exceeds 50K chars, drop it entirely
        if len(existing_events_json) > 50000:
            print(f"    - WARNING: Existing events JSON too large ({len(existing_events_json)} chars), omitting from prompt")
            existing_events_section = ""
        else:
            existing_events_section = f"""
REFERENCE - Previously extracted events (for naming consistency only):
{existing_events_json}

NOTE: The above is ONLY for reference to maintain consistent naming. You MUST still extract ALL events from the page content below - do not limit your output to these events. Our deduplication system will handle any overlaps.

"""

    return f'''{city_config.extraction_intro().format(date=current_date_string, name=name, url=url)}
{existing_events_section}
Based on the website content below, extract all upcoming events. For each event, provide:
- name: The event name
- location: The venue name ONLY (e.g. "Brooklyn Heights Library", "Le Petit Versailles"). Preserve the exact spelling — do not introduce typos. If the source lists "<Branch>, <Room>" (e.g. "Highlawn, Meeting Room"), the branch is the location and the room is the sublocation — do not concatenate them into one field.
- sublocation: Optional location within the venue (rooftop, 5th floor, specific meeting room, etc.)
- occurrences: An array of date/time objects. IMPORTANT: For recurring events (e.g., "every Wednesday" or "Jan 11, 18, 25"), list EACH specific date as a separate occurrence within the next 3 months. Each occurrence has:
  - start_date: Date in YYYY-MM-DD format
  - start_time: Time like "4:00 PM" (optional)
  - end_date: End date if different from start (optional)
  - end_time: End time (optional)
  EXHIBITIONS: For an art exhibition, gallery show, or installation that runs over a date range (e.g. "March 1 – July 5", "On view through June 30"), create ONE occurrence spanning the run: start_date = opening date, end_date = closing date. Do NOT collapse the run to a single day, and do NOT stamp today's date as the exhibition date. An exhibition whose OPENING date has already passed is STILL on view as long as its closing date is today or later — keep it, using the original (past) opening date as start_date; do NOT null it or skip it because it already opened. If the page gives no opening or closing date at all (a permanent / date-less display), set occurrences=null instead of inventing a single date.
  RECEPTION vs RUN: A timed opening/closing reception, opening night, or preview is a DISTINCT single-day event — NOT an occurrence of the exhibition it celebrates. When a page describes both a dated, timed reception AND a broader exhibition run (e.g. "Opening reception June 4, 6–8pm" for a show "on view June 4 – July 10"), emit TWO separate events: (1) the reception, with ONE single-day occurrence (its date + time), and (2) the exhibition, with ONE run occurrence (start_date = opening, end_date = closing). Never attach the exhibition's full run as a second occurrence of the reception event, and never put the reception's time on the exhibition run.
- description: 1-3 sentence description based ONLY on what is stated in the source content. If the listing only has a name/date/time with no further details, use "No description available." Do NOT make up or infer descriptions.
- url: Specific event URL if available
- hashtags: 4-7 CamelCase tags (e.g., ["Comedy", "StandUp", "Free"]). Always include at least one category from: Music, Nightlife, Comedy, Art, Theater, Dance, Film, Literature, Community, Family, Wellness, Education, Outdoor, Sports, Games. Also include Free if the event is free, or Virtual if online. Then add granular descriptive tags. {city_config.extraction_tag_avoidance()}
- emoji: A single emoji representing the event

{note_section}{rid_section}
Rules:
- Extract ALL events from the page - do not skip or summarize
- Do NOT extract things that are not attendable public events. Skip: venue/program closures and holiday-closure notices ("Museum Closed", "Park Closes at 5pm", "Office Closed for Juneteenth"); calls for submissions, applications, or grants ("Open Call for Artists", "Submission Deadline", "Micro Grants Round 3"); casting calls and talent-recruitment notices ("Casting Call", "Models Wanted", "Dancers Needed"); civic date markers ("Election Day", "Primary Day", "Election Day 2026") — an attendable election-night watch party IS an event; venue marketing (space/room rentals, "Private Events", "Available for Booking", dining service like "Signature Breakfast"); season passes and ticketing placeholders ("Summer Pass 2026", "Showtimes"); fundraising campaigns and donation-match drives ("Match Campaign", "Giving Day") — an attendable benefit concert or gala IS an event; submit-your-work contests with an entry deadline ("Library Card Art Contest") — a contest held live in front of an audience (trivia, dance, pie-eating) IS an event; info-booth or vendor-table marketing listings inside a festival program ("Our Info Booths"); childcare offered as an amenity during another activity ("Nursery Care" during worship services, babysitting while parents attend) — a children's program or childcare-related class that is itself the event ("Toddler Storytime", "Babysitting 101 Training", "Preschool Open House") IS an event; and content placeholders or unrelated spam. These are not events — leave them out entirely.
- {city_config.extraction_region_rule()}
- Ignore unrelated event sections ("Hot Events", "Similar events", etc.)
- For recurring events, expand ALL individual dates into the occurrences array
- If no events are found, return an empty events list
- IMPORTANT: Do NOT fabricate or guess dates. If a listing has no date information on the page, set occurrences to null.

Website content:

{page_content}'''


# =============================================================================
# Per-site extraction directives
# =============================================================================
#
# `websites.notes` (plus a SiteProfile's extraction_notes, which resolve_notes
# prepends to it) is the only site-scoped text every extraction path already
# receives, so it doubles as the place to record an EXPLICIT per-site override
# of the automatic single-vs-chunked mode choice. A directive is a line of the
# form
#
#     [[extraction: force-chunked]] optional free-text rationale
#
# The whole line is stripped from the notes before they are handed to Gemini,
# so a directive never leaks into a prompt as if it were guidance.
#
# WHY this exists: mode selection is a heuristic (estimate_event_count >
# LARGE_PAGE_THRESHOLD, or content > MAX_CHUNK_CHARS * 2). A site whose real
# event count sits just under the threshold on content just under 2x the chunk
# size — w950 Nook: ~30 Eventbrite-API cards, estimate 32-34, 43 KB — is routed
# to a single call whose ~8K output-token budget cannot hold 30 full events, so
# the extraction collapses to a random fraction (28,254 -> 7,290 -> 8,383 chars
# over three crawls, 14 of ~30 events surviving). Nudging the heuristic's inputs
# (padding the estimate, lowering the threshold) would move that cliff for every
# site; naming the site that needs chunking does not.
FORCE_CHUNKED_DIRECTIVE = 'force-chunked'

_EXTRACTION_DIRECTIVE_RE = re.compile(
    r'^[ \t]*\[\[[ \t]*extraction[ \t]*:([^\]\n]*)\]\].*$', re.MULTILINE | re.IGNORECASE)


def parse_extraction_directives(notes):
    """Split `[[extraction: ...]]` directive lines out of a site's notes.

    Returns (directives, notes_without_directive_lines). Directives are
    lower-cased, `_`-normalised tokens; a line may carry several, comma
    separated. Unknown tokens are returned as-is and simply ignored by callers,
    so a typo degrades to "no override" rather than an exception.
    """
    if not notes or not _EXTRACTION_DIRECTIVE_RE.search(notes):
        return set(), notes or ""
    directives = set()
    for match in _EXTRACTION_DIRECTIVE_RE.finditer(notes):
        for token in match.group(1).split(','):
            token = token.strip().lower().replace('_', '-')
            if token:
                directives.add(token)
    cleaned = _EXTRACTION_DIRECTIVE_RE.sub('', notes)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    return directives, cleaned


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
    notes = site_profiles.resolve_notes(base_url, notes)
    # Directives are stripped here, before the notes reach ANY prompt builder.
    directives, notes = parse_extraction_directives(notes)

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

    # Content fingerprinting: if a prior crawl from this website produced
    # identical content (same SHA-256 hash), reuse its extraction instead of
    # calling Gemini again. Saves significant cost on stale-content sites.
    prior_id = db.find_prior_crawl_with_same_content(cursor, crawl_result_id)
    if prior_id and _fingerprint_copy_is_suspect(cursor, prior_id):
        # The cached extraction we'd copy is anomalously low vs the site's
        # history — the fingerprint-freeze failure mode (one unlucky
        # under-extraction cached and re-copied forever on a byte-stable page,
        # mass-archiving still-listed events). Refuse the cache hit and force a
        # fresh extraction; the freshly extracted result still passes through
        # the post-extraction variance guard below.
        print(f"    - ⚠️  FINGERPRINT VARIANCE GUARD: prior crawl {prior_id} extraction is "
              f"anomalously low vs site history; forcing fresh extraction")
        prior_id = None
    if prior_id:
        prep.skip_extraction_reason = f"identical content to crawl {prior_id} — copied {{count}} events"
        prep.copy_from_crawl_result_id = prior_id
        return prep

    # Check for explicit "no events" indicators to prevent hallucinations.
    # Some pages (e.g., Eventbrite organizer pages with no upcoming events)
    # have substantial content (navigation, past events) but explicitly state
    # there are no upcoming events. Gemini will hallucinate events from such pages.
    no_events_patterns = [
        "upcoming (0)",
        "sorry, there are no upcoming events",
        "no upcoming events",
        "no events scheduled",
    ]
    # The veto is page-level, so a single empty widget can suppress an entire
    # document that also renders a populated one (w618 Freshkills: three dated
    # Tribe cards followed by an empty embedded Eventbrite widget). Only trust
    # the shortcut when the page shows no positive evidence of real events —
    # see has_event_evidence() for the three signals and their calibration.
    page_has_event_evidence = has_event_evidence(page_content)
    content_lower = page_content[:15000].lower()  # Only check first 15K chars
    for pattern in no_events_patterns:
        if pattern in content_lower:
            if page_has_event_evidence:
                print(f"    - Page says '{pattern}' but also shows real event "
                      f"evidence — ignoring the no-events shortcut")
                break
            prep.resolved_result = '{"events": []}'
            print(f"    - Page explicitly states no events ('{pattern}'), skipping extraction")
            return prep

    # Get website_id (and its content-cap override) for this crawl result
    cursor.execute(
        """SELECT cr.website_id, w.max_content_chars
             FROM crawl_results cr
             LEFT JOIN websites w ON w.id = cr.website_id
            WHERE cr.id = %s""",
        (crawl_result_id,)
    )
    result = cursor.fetchone()
    website_id = result[0] if result else None
    website_max_content_chars = result[1] if result else None
    prep.website_id = website_id

    current_date_string = datetime.now().strftime('%Y-%m-%d')

    # Extract URL from first line if present
    url, content_to_process = extract_url_from_content(page_content)
    url = url or ""
    prep.url = url

    # Hard limit on content size to prevent runaway extraction. Structured API
    # sources can raise it via their SiteProfile — truncating a payload we built
    # ourselves silently drops real events rather than trimming an archive.
    # Plain websites raise (or lower) it via websites.max_content_chars, which
    # wins over the plugin default; both are per-site decisions made after
    # checking what actually sits past the cut.
    max_chars = site_profiles.max_content_chars_for(
        base_url or url, MAX_CONTENT_CHARS, website_max_content_chars)
    if len(content_to_process) > max_chars:
        print(f"    - Content too large ({len(content_to_process)} chars), truncating to {max_chars}")
        content_to_process = content_to_process[:max_chars]

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
        forced_chunked = FORCE_CHUNKED_DIRECTIVE in directives
        use_two_pass = (forced_chunked
                        or estimated_events > LARGE_PAGE_THRESHOLD
                        or len(content_to_process) > MAX_CHUNK_CHARS * 2)

        if use_two_pass:
            prep.extraction_type = 'chunked'
            prep.max_batches = max_batches if max_batches is not None else DEFAULT_MAX_BATCHES
            if forced_chunked:
                print(f"    - [[extraction: force-chunked]] for {website_name} "
                      f"(~{estimated_events} events, {len(content_to_process)} chars), "
                      f"preparing chunked extraction...")
            else:
                print(f"    - Large page detected (~{estimated_events} events, {len(content_to_process)} chars), preparing chunked extraction...")

            # Split content into chunks and build prompts
            chunks, chunk_method = chunk_content(content_to_process, EVENTS_PER_CHUNK, MAX_CHUNK_CHARS)
            print(f"    - Split into {len(chunks)} chunks using {chunk_method}-based chunking")

            prep.content = content_to_process  # Store for enrichment context
            prep.chunk_prompts = [
                get_chunk_prompt(chunk, current_date_string, notes,
                                 request_id=f"cr-{crawl_result_id}-chunk-{i}")
                for i, chunk in enumerate(chunks)
            ]
        else:
            prep.extraction_type = 'single'
            print(f"    - Preparing extraction using {GEMINI_MODEL} ({len(content_to_process)} chars)...")

            # Get existing upcoming events from this website (single-prompt path only —
            # neither the chunked nor vision prompts consume them, so skip the
            # expensive query for those heavier-content sites).
            existing_events = []
            if website_id:
                existing_events = db.get_existing_upcoming_events(cursor, website_id)
                if existing_events:
                    print(f"    - Found {len(existing_events)} existing upcoming events to include in prompt")
            prep.existing_events = existing_events

            prep.prompt = get_prompt(url, content_to_process, current_date_string,
                                     website_name, notes, existing_events,
                                     request_id=f"cr-{crawl_result_id}")

    return prep


def _apply_fingerprint_marker_and_status(cursor, connection, prep, copied):
    """Store the fingerprint-match skip marker and advance the crawl result to
    'processed' after its crawl_events were copied from a prior identical crawl.

    The caller runs db.copy_crawl_events first (so it can emit its own log line
    using the returned count) and passes that count here.
    """
    marker = f'{{"events": [], "skipped": "fingerprint match: cr-{prep.copy_from_crawl_result_id}"}}'
    db.update_crawl_result_extracted(cursor, connection, prep.crawl_result_id, marker)
    db.update_crawl_result_processed(cursor, connection, prep.crawl_result_id, copied)


async def execute_extraction_sync(cursor, connection, prep):
    """
    Execute extraction using individual (non-batch) API calls.

    Takes a PreparedExtraction and makes the appropriate Gemini API call(s).

    Returns:
        True if successful, False otherwise
    """
    crawl_result_id = prep.crawl_result_id

    # Content fingerprint match: copy events from prior identical crawl, no API call.
    # Skip directly to 'processed' state — bypasses both Gemini extraction and the
    # processor's parse/insert step.
    if prep.copy_from_crawl_result_id is not None:
        copied = db.copy_crawl_events(
            cursor, connection, prep.copy_from_crawl_result_id, crawl_result_id
        )
        reason = (prep.skip_extraction_reason or "identical content").format(count=copied)
        print(f"    - {reason}")
        _apply_fingerprint_marker_and_status(cursor, connection, prep, copied)
        return True

    # Handle pre-resolved results (e.g., vision with no images)
    if prep.resolved_result is not None:
        response_text = prep.resolved_result
    else:
        response_text = await _generate_extraction_response(prep, cursor, connection)

    response_text, event_count, occurrence_count = _normalize_extraction_response(response_text)

    # Variance guard: Gemini's per-run yield on near-identical content can swing
    # wildly (observed 4 -> 24 events run-to-run on stable pages). A collapsed
    # extraction cascades into false archivals downstream. When the count drops
    # below half the website's trailing median while the crawled content size is
    # stable, retry the extraction once and keep the better result.
    if prep.resolved_result is None and prep.extraction_type in ('single', 'chunked'):
        retry_reason = _variance_retry_reason(cursor, prep.crawl_result_id, event_count)
        if retry_reason:
            print(f"    - ⚠️  VARIANCE GUARD: {retry_reason}; retrying extraction once...")
            try:
                retry_text = await _generate_extraction_response(prep, cursor, connection)
            except ExtractionCallFailure as e:
                # The retry hit the API wall; the first attempt is still a real
                # answer, so keep it rather than failing the whole crawl result.
                print(f"    - Variance retry could not reach the API ({e}); keeping first attempt")
                retry_text = None
            retry_text, retry_count, retry_occ = _normalize_extraction_response(retry_text)
            if retry_count > event_count:
                print(f"    - Variance retry recovered {retry_count} events (first attempt: {event_count}); keeping retry")
                response_text, event_count, occurrence_count = retry_text, retry_count, retry_occ
            else:
                print(f"    - Variance retry yielded {retry_count} events (no better); keeping first attempt")

    db.update_crawl_result_extracted(cursor, connection, crawl_result_id, response_text)
    print(f"    - Extracted {event_count} events with {occurrence_count} occurrences")
    return True


async def _generate_extraction_response(prep, cursor, connection):
    """Make the Gemini API call(s) for one extraction attempt and return raw text.

    Shared by the first attempt and the variance-guard retry in
    execute_extraction_sync. cursor/connection are only used by the chunked
    path's max_batches auto-bump.
    """
    if prep.extraction_type == 'vision':
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
            return response.text.strip()
        # A failed vision call is the same lie as a failed chunk: the images were
        # never read, so an empty result says nothing about the post. Fail the
        # crawl result instead of storing a zero (see ExtractionCallFailure).
        except asyncio.TimeoutError:
            print(f"    - Vision extraction timeout after {GEMINI_TIMEOUT * 2}s")
            raise ExtractionCallFailure(
                f"vision extraction timed out after {GEMINI_TIMEOUT * 2}s")
        except Exception as e:
            print(f"    - Vision extraction error: {e}")
            raise ExtractionCallFailure(
                f"vision extraction failed: {e or type(e).__name__}")

    if prep.extraction_type == 'chunked':
        return await _execute_chunked_sync(prep, cursor, connection)

    # single
    estimated_tokens = len(prep.prompt) // CHARS_PER_TOKEN
    if estimated_tokens > MAX_REQUEST_TOKENS:
        error_msg = f"Prompt too large (~{estimated_tokens:,} est. tokens, limit {MAX_REQUEST_TOKENS:,})"
        print(f"    ⚠️  ERROR: {error_msg}, skipping extraction")
        raise RuntimeError(error_msg)
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
    return response.text.strip()


def _normalize_extraction_response(response_text):
    """Validate extraction JSON; return (response_text, event_count, occurrence_count).

    Falls back to an empty result on missing/invalid JSON.
    """
    if not response_text or not response_text.strip():
        return '{"events": []}', 0, 0
    try:
        parsed = json.loads(response_text)
        event_count = len(parsed.get('events', []))
        occurrence_count = sum(
            len(e.get('occurrences') or []) for e in parsed.get('events', [])
        )
        return response_text, event_count, occurrence_count
    except json.JSONDecodeError:
        return '{"events": []}', 0, 0


def _fingerprint_copy_is_suspect(cursor, prior_id):
    """Guard the content-fingerprint short-circuit against propagating a frozen
    under-extraction.

    Failure mode (the "fingerprint freeze"): on a byte-stable page, a single
    unlucky Gemini under-extraction is cached, and every later crawl with the
    same content_hash copies it verbatim via find_prior_crawl_with_same_content
    — so the merger keeps archiving real, still-listed events. The ordinary
    post-extraction variance guard (_variance_retry_reason) can't catch this:
    the short-circuit runs *before* extraction, and the propagated copies poison
    a plain trailing median.

    We compare the count we'd copy (the prior crawl's event_count) against the
    website's typical level, computed as the median of the per-content_hash
    event counts over recent distinct page states. Deduping by content_hash
    collapses all the propagated copies into a single vote, so the freeze can't
    poison the reference no matter how many times it has already been copied.

    Returns True (refuse the cache hit, force a fresh extraction) when the prior
    count is < half that median, on a site with enough distinct-page history to
    judge (>= 3 distinct hashes, median >= 4 — tiny/noisy sites are exempt).
    Fails open (returns False) on any error so extraction is never broken.
    """
    try:
        cursor.execute(
            "SELECT website_id, event_count FROM crawl_results WHERE id = %s",
            (prior_id,)
        )
        row = cursor.fetchone()
        if not row or row[0] is None or row[1] is None:
            return False
        website_id, prior_count = row[0], row[1]

        # One representative (best) count per distinct content_hash, most-recent
        # pages first. GROUP BY content_hash collapses the freeze's copies so a
        # long-running freeze still only contributes one low data point.
        cursor.execute("""
            SELECT MAX(event_count) AS cnt
            FROM crawl_results
            WHERE website_id = %s AND status = 'processed'
              AND event_count IS NOT NULL AND content_hash IS NOT NULL
            GROUP BY content_hash
            ORDER BY MAX(id) DESC
            LIMIT 8
        """, (website_id,))
        counts = [r[0] for r in cursor.fetchall()]
        if len(counts) < 3:
            return False

        median_count = statistics.median(counts)
        if median_count < 4:
            return False
        return prior_count < median_count * 0.5
    except Exception as e:
        # The guard must never break extraction — fail open (accept the hit).
        print(f"    - Fingerprint variance check failed ({e}); accepting cache hit")
        return False


def _variance_retry_reason(cursor, crawl_result_id, new_count):
    """Decide whether an extraction's event count collapsed vs the site's history.

    Returns a human-readable reason string when ALL of these hold (else None):
    - the website has >= 3 prior successfully-processed crawls,
    - the trailing median event count is >= 4 (tiny sites are too noisy to judge),
    - this extraction yielded < half the trailing median,
    - the current crawled content size is within ±20% of the trailing median size
      (a size change means the page really changed — that's not variance).
    """
    try:
        cursor.execute(
            "SELECT website_id, LENGTH(crawled_content) FROM crawl_results WHERE id = %s",
            (crawl_result_id,)
        )
        row = cursor.fetchone()
        if not row or not row[0] or not row[1]:
            return None
        website_id, current_size = row[0], row[1]

        cursor.execute("""
            SELECT event_count, LENGTH(crawled_content)
            FROM crawl_results
            WHERE website_id = %s AND id != %s
              AND status = 'processed'
              AND event_count IS NOT NULL
              AND crawled_content IS NOT NULL
            ORDER BY id DESC
            LIMIT 5
        """, (website_id, crawl_result_id))
        rows = cursor.fetchall()
        if len(rows) < 3:
            return None

        median_count = statistics.median([r[0] for r in rows])
        median_size = statistics.median([r[1] for r in rows])
        if median_count < 4 or not median_size:
            return None
        if new_count >= median_count * 0.5:
            return None
        if abs(current_size - median_size) > median_size * 0.2:
            return None
        return (f"extracted {new_count} events vs trailing median {median_count:.0f} "
                f"on similar-size content ({current_size} vs ~{median_size:.0f} chars)")
    except Exception as e:
        # The guard must never break extraction — fail open (no retry).
        print(f"    - Variance guard check failed ({e}); skipping retry")
        return None


async def _execute_chunked_sync(prep, cursor=None, connection=None):
    """Execute chunked extraction synchronously (individual API calls).

    cursor/connection enable the max_batches auto-bump when the chunk yield
    exceeds the website's cap; omit them (e.g. in tests) to disable the bump.
    """
    max_events = prep.max_batches * ENRICHMENT_BATCH_SIZE

    # Extract events from each chunk
    all_simple_events = []
    skipped_chunks = 0
    attempted_chunks = 0
    failed_chunks = 0
    last_chunk_error = None
    for i, chunk_prompt in enumerate(prep.chunk_prompts):
        if len(all_simple_events) >= max_events:
            skipped_chunks = len(prep.chunk_prompts) - i
            break
        print(f"    - Processing chunk {i + 1}/{len(prep.chunk_prompts)}...")
        attempted_chunks += 1
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
            failed_chunks += 1
            last_chunk_error = f"timeout after {CHUNK_TIMEOUT}s"
            print(f"      Chunk timeout after {CHUNK_TIMEOUT}s")
        except Exception as e:
            failed_chunks += 1
            last_chunk_error = str(e) or type(e).__name__
            print(f"      Chunk error: {e}")

    if not all_simple_events:
        # Nothing came back. Only call that an empty page when every chunk we
        # asked actually ANSWERED "no events" — a zero assembled from chunks
        # that raised is evidence about the API, not about the page, and storing
        # it as a successful extraction wipes the site's last good crawl and
        # feeds archival (see ChunkedExtractionFailure). One erroring chunk is
        # enough to disqualify the zero: whatever that chunk covered is simply
        # unknown.
        if failed_chunks:
            raise ChunkedExtractionFailure(
                f"{failed_chunks}/{attempted_chunks} chunk request(s) failed and no chunk "
                f"returned events (last error: {last_chunk_error})")
        return '{"events": []}'

    if skipped_chunks > 0:
        print(f"    - Skipped {skipped_chunks} remaining chunk(s) (already have {len(all_simple_events)} events)")

    print(f"    - Total from chunks: {len(all_simple_events)} events")

    # Cap events at max_batches to limit API cost — but first try to auto-raise
    # the website's cap (triage previously did this by hand every run it fired).
    total_batches_needed = -(-len(all_simple_events) // ENRICHMENT_BATCH_SIZE)
    if total_batches_needed > prep.max_batches and cursor is not None and connection is not None:
        bumped = _maybe_auto_bump_max_batches(cursor, connection, prep, total_batches_needed)
        if bumped:
            prep.max_batches = bumped
            max_events = bumped * ENRICHMENT_BATCH_SIZE
    if total_batches_needed > prep.max_batches:
        print(f"    - WARNING: [{prep.website_name}] {len(all_simple_events)} events would need {total_batches_needed} batches, "
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
        enrichments = await enrich_events_batch(batch, prep.website_name, content=prep.content)
        all_enrichments.update(enrichments)

    return _combine_chunked_results(all_simple_events, all_enrichments)


def _maybe_auto_bump_max_batches(cursor, connection, prep, batches_needed):
    """Persistently raise websites.max_batches when a site outgrows its cap.

    Returns the new cap, or None when no bump applies. Rules:
    - never touch a site deliberately throttled BELOW the default (a low cap is
      an explicit decision to limit a noisy source);
    - new cap = batches_needed + 1 (one batch of headroom — the same formula
      triage previously applied by hand), clamped to AUTO_MAX_BATCHES_CEILING;
    - only ever bumps upward.

    Chunk extraction stops early once the current cap's event budget is reached,
    so a single bump may not cover the site's full listing — the next run starts
    with the raised cap and converges over a few runs.
    """
    if not prep.website_id:
        return None
    current = prep.max_batches or DEFAULT_MAX_BATCHES
    if current < DEFAULT_MAX_BATCHES:
        return None
    new_cap = min(batches_needed + 1, AUTO_MAX_BATCHES_CEILING)
    if new_cap <= current:
        return None
    try:
        cursor.execute(
            "UPDATE websites SET max_batches = %s WHERE id = %s",
            (new_cap, prep.website_id)
        )
        connection.commit()
    except Exception as e:
        print(f"    - max_batches auto-bump failed ({e}); keeping cap {current}")
        return None
    print(f"    - AUTO-BUMP: [{prep.website_name}] max_batches {current} -> {new_cap} "
          f"(this run needed {batches_needed}); persisted to websites table.")
    return new_cap


def _combine_chunked_results(simple_events, enrichments):
    """Combine simple events with enrichment data into final JSON."""
    full_events = []
    for event in simple_events:
        enrichment = enrichments.get(event['name'], {})
        full_event = {
            'name': event['name'],
            'location': event['location'],
            'sublocation': None,
            'occurrences': event.get('occurrences'),
            'url': event.get('url'),
            'description': enrichment.get('description', 'No description available.'),
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

def _build_eventlist_request(prep, contents, req_type):
    """Build an InlinedRequest for single-pass or vision EventList extraction."""
    request_id = f"cr-{prep.crawl_result_id}"
    return InlinedRequest(
        contents=contents,
        config=GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=EventList,
        ),
        metadata={
            "crawl_result_id": str(prep.crawl_result_id),
            "type": req_type,
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


def _build_enrichment_request(crawl_result_id, batch_event_names, venue_name, batch_idx, website_name, content=None):
    """Build an InlinedRequest for enrichment."""
    request_id = f"cr-{crawl_result_id}-enrich-{batch_idx}"
    content_snippets = extract_content_snippets(batch_event_names, content) if content else None
    return InlinedRequest(
        contents=get_enrichment_prompt(batch_event_names, venue_name, request_id=request_id, content_snippets=content_snippets),
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


def _validate_request_size(request, source_label):
    """Check if a request exceeds the per-request token limit.

    Returns the request if within limits, or None if it exceeds the limit.
    Logs a warning for rejected requests.
    """
    estimated_tokens = _estimate_request_tokens(request)
    if estimated_tokens > MAX_REQUEST_TOKENS:
        print(f"    - WARNING: Dropping request for {source_label}: "
              f"~{estimated_tokens:,} tokens exceeds {MAX_REQUEST_TOKENS:,} limit")
        return None
    return request


def build_batch_requests(preparations):
    """Convert PreparedExtractions into Phase 1 InlinedRequests.

    Args:
        preparations: dict of {crawl_result_id: PreparedExtraction}

    Returns:
        tuple of (requests, dropped_crids) where:
        - requests: list of InlinedRequest objects for all extraction types
        - dropped_crids: dict of {crawl_result_id: error_message} for oversized requests
    """
    requests = []
    dropped_crids = {}
    for crid, prep in preparations.items():
        label = f"{prep.website_name} (cr-{crid})"
        if prep.extraction_type == 'single':
            req = _validate_request_size(_build_eventlist_request(prep, prep.prompt, 'single'), label)
            if req:
                requests.append(req)
            else:
                dropped_crids[crid] = (f"Prompt too large (~{len(prep.prompt) // CHARS_PER_TOKEN:,} est. tokens, "
                                       f"limit {MAX_REQUEST_TOKENS:,})")
        elif prep.extraction_type == 'vision':
            req = _validate_request_size(_build_eventlist_request(prep, prep.vision_contents, 'vision'), label)
            if req:
                requests.append(req)
            else:
                dropped_crids[crid] = "Vision request too large"
        elif prep.extraction_type == 'chunked':
            for req in _build_chunk_requests(prep):
                validated = _validate_request_size(req, f"{label} chunk")
                if validated:
                    requests.append(validated)
                # Note: individual chunk drops don't fail the whole extraction
    return requests, dropped_crids


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
                content=prep.content,
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


async def _poll_batch_until_done(batch_job, poll_interval, timeout):
    """Poll a batch job until completion, timeout, or failure.

    Args:
        batch_job: The batch job object (from create or get)
        poll_interval: Seconds between status checks
        timeout: Maximum seconds to wait

    Returns:
        list of InlinedResponse

    Raises:
        RuntimeError: on timeout, job failure, or cancellation
    """
    elapsed = 0
    while not batch_job.done:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        try:
            # Bound the status GET: the genai client sets no HTTP read timeout,
            # so a hung poll would freeze `elapsed` here and the loop would never
            # reach its own timeout check below. wait_for cancels a stuck HTTP
            # await; on timeout we just poll again (elapsed keeps advancing).
            batch_job = await asyncio.wait_for(
                genai_client.aio.batches.get(name=batch_job.name), timeout=120
            )
        except Exception as e:
            print(f"  Warning: Failed to poll batch status: {e}")
            continue

        state_name = batch_job.state.name if batch_job.state else "UNKNOWN"
        print(f"  Batch status: {state_name} ({elapsed}s elapsed)")

        if elapsed >= timeout:
            try:
                await asyncio.wait_for(
                    genai_client.aio.batches.cancel(name=batch_job.name), timeout=60
                )
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


async def _submit_and_poll_single_batch(requests, display_name="fomo-extraction",
                                         poll_interval=None, timeout=None,
                                         crawl_result_ids=None):
    """Submit a single batch job and poll until completion.

    Args:
        requests: list of InlinedRequest objects
        display_name: Name for the batch job
        poll_interval: Seconds between status checks (default: BATCH_POLL_INTERVAL)
        timeout: Maximum seconds to wait (default: BATCH_TIMEOUT)
        crawl_result_ids: Optional list of crawl_result_ids to tag with the batch
                          job name for crash recovery

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
            # Bound the submit: create uploads the request payload, so allow
            # generous time (300s) but never hang forever on a stuck connection.
            batch_job = await asyncio.wait_for(
                genai_client.aio.batches.create(
                    model=GEMINI_MODEL,
                    src=requests,
                    config={"display_name": display_name},
                ),
                timeout=300,
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

    # Tag crawl results with batch job name for crash recovery
    if crawl_result_ids:
        conn = db.create_connection()
        cursor = conn.cursor(buffered=True)
        try:
            db.set_batch_job_name(cursor, conn, crawl_result_ids, batch_job.name)
        finally:
            cursor.close()
            conn.close()

    return await _poll_batch_until_done(batch_job, poll_interval, timeout)


async def submit_and_poll_batch(requests, display_name="fomo-extraction",
                                 poll_interval=None, timeout=None,
                                 crawl_result_ids=None):
    """Submit batch requests, splitting into sub-batches if needed to stay under token limits.

    Args:
        requests: list of InlinedRequest objects
        display_name: Name prefix for batch jobs
        poll_interval: Seconds between status checks (default: BATCH_POLL_INTERVAL)
        timeout: Maximum seconds to wait per sub-batch (default: BATCH_TIMEOUT)
        crawl_result_ids: Optional list of crawl_result_ids to tag with batch job
                          names for crash recovery

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
            crawl_result_ids=crawl_result_ids,
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


def _build_request_id_index(requests):
    """Build a lookup from request_id to request metadata."""
    id_to_metadata = {}
    for req in requests:
        metadata = req.metadata or {}
        rid = metadata.get("request_id", "")
        if rid:
            id_to_metadata[rid] = metadata
    return id_to_metadata


def _resolve_metadata(request_id, id_to_metadata):
    """Look up request metadata from a response's request_id.

    Returns the metadata dict, or None if no match is found.
    """
    if request_id:
        return id_to_metadata.get(request_id)
    return None


def process_batch_responses(requests, responses, preparations):
    """Map Phase 1 batch responses back to crawl results.

    Uses request_id echoed in the response JSON to match responses to requests,
    since the Gemini Batch API does NOT guarantee response ordering.

    Args:
        requests: list of InlinedRequest (for metadata)
        responses: list of InlinedResponse (unordered)
        preparations: dict of {crawl_result_id: PreparedExtraction}

    Returns:
        tuple of (single_results, chunked_events, failed_crids):
        - single_results: {crawl_result_id: json_string} for single/vision
        - chunked_events: {crawl_result_id: [simple_event_dicts]} for chunks
        - failed_crids: {crawl_result_id: error_message} for chunked results
          whose chunk responses ALL failed — to be stored as status='failed'
          rather than as an empty extraction (see ChunkedExtractionFailure)
    """
    # Build lookup from request_id to request metadata
    id_to_metadata = _build_request_id_index(requests)

    single_results = {}  # crid -> json string
    chunk_events_by_crid = {}  # crid -> list of simple event dicts
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
            metadata = _resolve_metadata(request_id, id_to_metadata)

            if metadata is None:
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

    # Chunked crids that produced no chunk output AT ALL. A chunk that answered
    # "no events" still registers its (empty) list above, so reaching this point
    # means every chunk response for the crawl result errored, went unmatched or
    # was unparseable — nothing was ever read of the page. That is a failed
    # extraction, not an empty calendar: storing '{"events": []}' here made the
    # dead crawl the website's newest successful result and fed archival with it.
    failed_crids = {}
    for crid, prep in preparations.items():
        if prep.extraction_type == 'chunked' and crid not in chunk_events_by_crid and crid not in single_results:
            failed_crids[crid] = (
                f"Extraction failed: no chunk response could be processed for "
                f"{prep.website_name} (batch extraction)")
            print(f"    - ⚠️  {prep.website_name}: every chunk response failed; "
                  f"marking crawl result {crid} failed (content preserved for re-extraction)")

    return single_results, chunk_events_by_crid, failed_crids


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
    id_to_metadata = _build_request_id_index(requests)

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
            metadata = _resolve_metadata(request_id, id_to_metadata)

            if metadata is None:
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


async def _run_enrichment_phase(enrichment_requests, chunked_events, preparations,
                                display_name, poll_interval, timeout):
    """Submit/poll/process the Phase-2 enrichment batch for chunked results.

    When there are no enrichment requests, falls back to combining each crawl
    result's chunked events with empty enrichments. The caller is responsible
    for emitting its own (distinct) lead-in log line before calling this.

    Returns:
        dict of {crawl_result_id: json_string} with fully enriched events
    """
    enriched_results = {}
    if enrichment_requests:
        phase2_responses = await submit_and_poll_batch(
            enrichment_requests,
            display_name=display_name,
            poll_interval=poll_interval,
            timeout=timeout,
        )
        enriched_results = process_enrichment_responses(
            enrichment_requests, phase2_responses, chunked_events, preparations
        )
    else:
        for crid, events in chunked_events.items():
            enriched_results[crid] = _combine_chunked_results(events, {})
    return enriched_results


def _store_batch_results(results_dict, crid_list, failed_crids=None):
    """Store extracted batch results and clear their batch_job_name tags.

    Opens and closes its own DB connection (matching the inline blocks it
    replaces). Returns a list of (crawl_result_id, ok) tuples — True for stored
    extractions, False for crawl results marked failed — in dict-iteration order.

    `failed_crids` ({crid: error_message}) are written as status='failed' rather
    than stored: their extraction never produced an answer, and 'failed' keeps
    crawled_content around for `main.py --ids` re-extraction.
    """
    stored = []
    conn = db.create_connection()
    cursor = conn.cursor(buffered=True)
    try:
        for crid, result_text in results_dict.items():
            db.update_crawl_result_extracted(cursor, conn, crid, result_text)
            stored.append((crid, True))
        for crid, error_msg in (failed_crids or {}).items():
            db.update_crawl_result_failed(cursor, conn, crid, error_msg)
            stored.append((crid, False))
        db.clear_batch_job_name(cursor, conn, crid_list)
    finally:
        cursor.close()
        conn.close()
    return stored


async def _process_completed_batch(responses, crid_list, extraction_queue,
                                    poll_interval=None, timeout=None):
    """Process results from a completed batch job (resumed or new).

    Builds preparations from queue items, processes responses, runs enrichment,
    and stores results in the database.

    Returns:
        list of (crawl_result_id, success) tuples
    """
    results = []
    queue_by_crid = {item['crawl_result_id']: item for item in extraction_queue}

    # Build preparations for response processing
    preparations = {}
    conn = db.create_connection()
    cursor = conn.cursor(buffered=True)
    try:
        for crid in crid_list:
            item = queue_by_crid.get(crid)
            if item:
                prep = await prepare_extraction(
                    cursor, crid, item['name'], item.get('notes', ''),
                    item.get('use_vision', False), item.get('base_url', ''),
                    item.get('max_batches')
                )
                if not prep.error:
                    preparations[crid] = prep
    finally:
        cursor.close()
        conn.close()

    if not preparations:
        return results

    # Re-build requests just for metadata matching (not re-submitted)
    batch_requests, _ = build_batch_requests(preparations)
    single_results, chunked_events, failed_crids = process_batch_responses(
        batch_requests, responses, preparations
    )

    # Handle enrichment for chunked results
    enriched_results = {}
    if chunked_events:
        enrichment_requests = build_enrichment_requests(chunked_events, preparations)
        display_name = None
        if enrichment_requests:
            print(f"\n  Enriching {sum(len(e) for e in chunked_events.values())} events...")
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            display_name = f"fomo-enrich-{timestamp}"
        enriched_results = await _run_enrichment_phase(
            enrichment_requests, chunked_events, preparations,
            display_name, poll_interval, timeout,
        )

    # Store results and clear batch tracking
    all_batch_results = {**single_results, **enriched_results}
    results.extend(_store_batch_results(all_batch_results, crid_list, failed_crids))

    return results


def _clear_batch_names(crid_list):
    """Clear the batch_job_name tag for a set of crawl results.

    Owns its own DB connection lifecycle (matching the inline blocks it
    replaces — no None-check on create_connection()).
    """
    conn = db.create_connection()
    cursor = conn.cursor(buffered=True)
    try:
        db.clear_batch_job_name(cursor, conn, crid_list)
    finally:
        cursor.close()
        conn.close()


async def _poll_and_process_resumed_batch(job_name, crid_list, extraction_queue,
                                           poll_interval, timeout):
    """Poll a resumed batch job until done, then process results.

    Returns:
        list of (crawl_result_id, success) tuples, or empty list on failure
    """
    print(f"\n  Resuming in-flight batch: {job_name} ({len(crid_list)} item(s))")

    try:
        batch_job = await asyncio.wait_for(
            genai_client.aio.batches.get(name=job_name), timeout=120
        )
    except Exception as e:
        print(f"  Warning: Could not retrieve batch job {job_name}: {e}")
        _clear_batch_names(crid_list)
        return []

    state_name = batch_job.state.name if batch_job.state else "UNKNOWN"
    print(f"  Resumed batch status: {state_name}")

    if state_name in ("JOB_STATE_FAILED", "JOB_STATE_CANCELLED"):
        print(f"  Batch {job_name} is {state_name} — will re-prepare these items")
        _clear_batch_names(crid_list)
        return []

    try:
        responses = await _poll_batch_until_done(batch_job, poll_interval, timeout)
    except RuntimeError as e:
        print(f"  Resumed batch failed: {e}")
        _clear_batch_names(crid_list)
        return []

    return await _process_completed_batch(
        responses, crid_list, extraction_queue, poll_interval, timeout
    )


async def _submit_poll_and_process_new_batch(extraction_queue, poll_interval, timeout):
    """Prepare, submit, poll, and process a new extraction batch.

    Handles the full lifecycle: prepare → submit → poll → process → store.

    Returns:
        list of (crawl_result_id, success) tuples
    """
    results = []
    preparations = {}

    print(f"\n  Preparing {len(extraction_queue)} new extraction request(s)...")

    conn = db.create_connection()
    if not conn:
        print("  Failed to connect to database for batch preparation")
        return [(item['crawl_result_id'], False) for item in extraction_queue]
    cursor = conn.cursor(buffered=True)

    resolved_results = {}

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
            elif prep.copy_from_crawl_result_id is not None:
                # Fingerprint match — copy events synchronously, no batch entry needed
                copied = db.copy_crawl_events(
                    cursor, conn, prep.copy_from_crawl_result_id, crid
                )
                _apply_fingerprint_marker_and_status(cursor, conn, prep, copied)
                results.append((crid, True))
                print(f"    - {item['name']}: identical content to crawl {prep.copy_from_crawl_result_id} — copied {copied} events")
            elif prep.resolved_result is not None:
                resolved_results[crid] = prep.resolved_result
                preparations[crid] = prep
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
        for crid in resolved_results:
            del preparations[crid]

    if not preparations:
        return results

    # Build and submit extraction batch
    batch_requests, dropped_crids = build_batch_requests(preparations)

    if dropped_crids:
        conn = db.create_connection()
        cursor = conn.cursor(buffered=True)
        try:
            for crid, error_msg in dropped_crids.items():
                prep = preparations[crid]
                print(f"    ⚠️  {prep.website_name}: extraction dropped — {error_msg}")
                db.update_crawl_result_failed(cursor, conn, crid, error_msg)
                results.append((crid, False))
                del preparations[crid]
        finally:
            cursor.close()
            conn.close()

    if not batch_requests:
        return results

    batch_crids = list(preparations.keys())

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    phase1_responses = await submit_and_poll_batch(
        batch_requests,
        display_name=f"fomo-extract-{timestamp}",
        poll_interval=poll_interval,
        timeout=timeout,
        crawl_result_ids=batch_crids,
    )

    single_results, chunked_events, failed_crids = process_batch_responses(
        batch_requests, phase1_responses, preparations
    )

    # Phase 2: Enrichment for chunked results
    enriched_results = {}
    if chunked_events:
        enrichment_requests = build_enrichment_requests(chunked_events, preparations)
        if enrichment_requests:
            print(f"\n  Phase 2: Enriching {sum(len(e) for e in chunked_events.values())} "
                  f"events in {len(enrichment_requests)} batch(es)...")
        enriched_results = await _run_enrichment_phase(
            enrichment_requests, chunked_events, preparations,
            f"fomo-enrich-{timestamp}", poll_interval, timeout,
        )

    # Store results and clear batch tracking
    all_results = {**single_results, **enriched_results}
    results.extend(_store_batch_results(all_results, batch_crids, failed_crids))

    return results


async def run_batch_extraction(extraction_queue, poll_interval=None, timeout=None):
    """Run extraction for all queued items using the Gemini Batch API.

    Resumed in-flight batches and new batches are polled concurrently so
    a slow resumed batch doesn't block new submissions.

    Args:
        extraction_queue: list of dicts with crawl_result_id, name, notes, etc.
        poll_interval: Seconds between batch status checks
        timeout: Maximum seconds to wait per batch

    Returns:
        list of (crawl_result_id, success) tuples
    """
    if poll_interval is None:
        poll_interval = BATCH_POLL_INTERVAL
    if timeout is None:
        timeout = BATCH_TIMEOUT

    # Check for in-flight batches from a previous interrupted run
    conn = db.create_connection()
    if not conn:
        return [(item['crawl_result_id'], False) for item in extraction_queue]
    cursor = conn.cursor(buffered=True)
    try:
        pending_batches = db.get_pending_batch_jobs(cursor)
    finally:
        cursor.close()
        conn.close()

    # Identify which CRIDs are covered by in-flight batches
    resumed_crids = set()
    for crid_list in pending_batches.values():
        resumed_crids.update(crid_list)

    # Split queue: items with in-flight batches vs new items
    new_queue = [item for item in extraction_queue
                 if item['crawl_result_id'] not in resumed_crids]

    # Build concurrent tasks
    tasks = []

    # Task for each resumed batch
    for job_name, crid_list in pending_batches.items():
        tasks.append(_poll_and_process_resumed_batch(
            job_name, crid_list, extraction_queue, poll_interval, timeout
        ))

    # Task for new extractions (if any)
    if new_queue:
        tasks.append(_submit_poll_and_process_new_batch(
            new_queue, poll_interval, timeout
        ))

    if not tasks:
        return []

    if len(tasks) > 1:
        print(f"\n  Running {len(tasks)} batch tasks concurrently "
              f"({len(pending_batches)} resumed, {'1 new' if new_queue else '0 new'})...")

    # Run all tasks concurrently
    task_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect results, handling any exceptions
    results = []
    for i, result in enumerate(task_results):
        if isinstance(result, Exception):
            print(f"  Batch task {i} failed: {result}")
        else:
            results.extend(result)

    return results
