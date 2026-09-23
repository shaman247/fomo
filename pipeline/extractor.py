"""
Event extraction by the supervising agent using durable structured packets.

Extracts structured event data from crawled website content using JSON schema.
Uses a two-pass approach for large pages (>50 expected events):
1. First pass: Extract core data (name, location, dates, url) with simplified schema
2. Second pass: Enrich events with descriptions, hashtags, and emoji in batches
"""

import asyncio
import base64
import html
import json
import os
import re
import statistics
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Optional
from urllib.parse import urlparse, urljoin

import httpx
from dotenv import load_dotenv
from PIL import Image
from pydantic import BaseModel, Field, field_validator

import city_config
import constants
import db
import llm_providers
import agent_extraction
from agent_extraction import AgentExtractionPending, AgentExtractionInvalid
import site_profiles
from occurrence_times import standardize_time as _standardize_time
from processor import extract_url_from_content


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

# Compatibility constants for existing call sites; no SDKs or clients are loaded.
genai_client = None
GEMINI_API_KEY = None
GEMINI_MODEL = "supervising agent"
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

# Smallest batch an enrichment failure will subdivide to before giving up.
#
# A batch of 30 wordy events can overrun the model's output budget; the response
# comes back `incomplete` and `enrich_events_batch` used to drop the WHOLE batch,
# leaving all 30 events with "No description available." and no tags. Measured on
# the 2026-08-10 run: 14 of 185 batches failed that way, blanking 95 of 749 new
# events (12.7%) — a silent quality tax, since the events still merge fine.
#
# Halving on failure is the right shape because the cause is cumulative output
# length: most batches are fine and only the wordy tail needs subdividing (the
# same reasoning as `websites.max_records_per_chunk`). The floor exists
# because below it the problem is one pathological event, which splitting cannot
# fix — so we stop paying for calls and let that small group degrade.
ENRICHMENT_MIN_BATCH = 4

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

# Absolute ceiling on raw extracted records in one chunked run. The max_batches
# budget counts DISTINCT NAMES (what enrichment charges for), which leaves the
# raw record count unbounded in principle — a daily-recurring event can emit one
# record per date. This is the runaway guard, set far above anything observed
# (worst real case ~3.5 records per distinct name), so it should never bind.
CHUNK_RECORD_CEILING = int(os.environ.get("CHUNK_RECORD_CEILING", "5000"))

# Timeout for a single-event detail-page extraction (seconds). Deliberately
# short: Step 5 fans these out across every candidate event, so a slow call is
# better abandoned than allowed to stall the batch. Reasoning models spend more
# wall time per call than Gemini does, hence the env override.
DETAIL_TIMEOUT = int(os.environ.get("DETAIL_TIMEOUT", "60"))

# Maximum characters per chunk when falling back to character-based chunking
MAX_CHUNK_CHARS = 30000

# Ceiling on the number of DATE TOKENS one chunk may ask the model to turn into
# occurrences. Enforced by `cap_occurrences_per_chunk`.
#
# WHY this exists, and why it is a global cap where `max-records-per-chunk` is
# deliberately per-site: every existing chunk budget measures the INPUT (chars,
# record headings) and is blind to the OUTPUT the chunk demands. Those track
# each other on an ordinary listing — one card, one or two dates — but come
# apart completely on a card carrying an ENUMERATED DATE LIST, where a single
# 3 KB record demands 60 occurrence objects.
#
# Measured on w944 The Tiny Cupboard (2026-08-30), whose js_code emitted every
# upcoming date per club. Same content, same prompt, only the number of dates
# the response had to carry changing:
#
#     demanded   returned   result
#        130        130     ok
#        480        480     ok
#        600        233     silent truncation (5/9/10/14 of 60 on 8 cards)
#        660        660     ok
#        780        493     silent truncation
#        780         60     occurrences=null on 12 of 13 records
#
# So it is not a hard cliff — it is stochastic degradation that sets in
# somewhere past ~500 and is severe by ~800. And the way the model degrades is
# the worst possible one: `occurrences` is nullable, and the prompt tells it a
# null is better than a fabricated date, so it takes the exit and returns a
# well-formed record with no dates. The event count stays healthy, nothing
# raises, and the events silently drop off the map as undated.
#
# 250 sits at ~2x margin below the lowest observed failure. Unlike a global
# record cap — measured at +83% chunks for +0.1% events, which is why
# `max_records_per_chunk` stayed opt-in — this one is inert on the corpus:
# over the last 10 days' crawls (1,428 chunks on the chunked path) only 18
# chunks (1.26%) exceed it, and every one of them is a page in exactly this
# at-risk shape (BAM 684 date tokens in one chunk, GrowNYC 648, Arts Society of
# Kingston 526, Alamo Drafthouse 503, Alvin Ailey 431).
OCCURRENCE_BUDGET_PER_CHUNK = int(os.environ.get("OCCURRENCE_BUDGET_PER_CHUNK", "250"))

# Longest page preamble `cap_occurrences_per_chunk` will repeat onto the pieces
# it cuts. Big enough for the venue/address header a js_code-built listing puts
# above its cards; small enough that repeating it is free.
PREAMBLE_CARRY_MAX_CHARS = 800

# Largest trailing partial record chunk_content_by_size will carry into the next
# chunk, as a fraction of MAX_CHUNK_CHARS. The carry leads the next chunk, so it
# has to leave that chunk room to hold real content.
CARRY_CAP_FRACTION = 0.25

# Hard limit on total content size before extraction (characters).
# Pages exceeding this will be truncated. 300K chars ≈ 10 chunks of 30K,
# accommodating multi-week event aggregators like NYC Parks date-windowed
# crawls. Prevents runaway extraction on pages with huge archives.
MAX_CONTENT_CHARS = 300000

# Maximum number of images to process for vision extraction.
# Sized to cover a full picnob Instagram bundle (12 posts = 12 flyers) plus a
# little headroom (LTV Studios w1969 carries 14). At 10 this silently dropped
# the last 2 posts of EVERY 12-post bundle. Genuinely image-dense pages exist
# (Lucky 13 Saloon crawls 69-83 images) and are deliberately still capped —
# sending 80 images costs ~20K input tokens for a page whose captions already
# carry the dates — but the drop is now logged instead of silent.
MAX_VISION_IMAGES = 14

# Maximum page text included in the vision prompt (characters).
# The vision prompt is NOT image-only: it carries the page text alongside the
# flyers, and on Instagram the dates live in the captions, not on the image.
# This was 2000, which discarded ~87% of a ~15K-char picnob bundle and made
# vision mode structurally blind to the field it needed — measured at -38%
# events vs text mode over 43 bundles (p=0.0005). Sized against real
# vision-mode crawls (max observed 22,896 chars) and aligned with
# MAX_CHUNK_CHARS, the established single-call text budget.
MAX_VISION_TEXT_CHARS = 30000

# Maximum image dimension (images will be resized if larger)
MAX_IMAGE_DIMENSION = 1024

# Safety limit for an individual unchunked work packet. Oversized packets fail
# explicitly; ordinary large sources are split before reaching this path.
CHARS_PER_TOKEN = 3
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
    chunks: list = field(default_factory=list)  # raw chunk text, parallel to chunk_prompts
    chunk_instructions: str = ""  # static rules + site notes shared by every chunk packet
    pruned_chunks: list = field(default_factory=list)  # (index, reason, chars) dropped before queuing
    max_batches: Optional[int] = None
    max_records_per_chunk: Optional[int] = None
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
    # Match markdown image syntax. The URL may contain markdown-escaped
    # parentheses (`file%20\(1\).jpg`): crawl4ai escapes literal parens in
    # link targets, and the old `[^)]+` stopped at the first `\)` and yielded a
    # truncated URL that 404'd and failed vision coverage closed (Basement NY,
    # 2026-09-18). Accept escaped parens as part of the URL, then unescape.
    pattern = r'!\[[^\]]*\]\(((?:\\.|[^)\\])+)\)'
    urls = [re.sub(r'\\(.)', r'\1', u) for u in re.findall(pattern, content)]

    # Filter and normalize URLs
    result = []
    for url in urls:
        # Skip data URLs
        if url.startswith('data:'):
            continue
        # Skip bare site roots (`<img src="https://host/">`): a page, never a
        # flyer. It downloads as text/html and would fail coverage closed.
        parsed = urlparse(url)
        if parsed.scheme in ('http', 'https') and parsed.path in ('', '/') and not parsed.query:
            continue
        # Skip tiny images (likely icons/buttons)
        if 'icon' in url.lower() or 'button' in url.lower() or 'logo' in url.lower():
            continue
        # Skip ad-tech cookie-sync / tracking beacons. Third-party ad scripts
        # (Songkick, Prebid publishers) render them as <img> tags, so they land
        # in the markdown as images; they never carry event content and most
        # 302 to an HTML endpoint, so they made prepare_vision_content fail
        # closed ("27 source images failed to download") on The Cobra Club,
        # 2026-09-17.
        if is_tracking_beacon_url(url):
            continue
        # Make absolute if relative
        if base_url and not url.startswith(('http://', 'https://')):
            url = urljoin(base_url, url)
        if url.startswith(('http://', 'https://')):
            result.append(url)

    return result


# Cookie-sync / ad-pixel URL shapes. A flyer is never served from a path like
# /getuid or /user-sync, and never carries a gdpr= / redirect= query parameter;
# the sync beacons in the wild always do (measured on the 27 failing Cobra Club
# URLs: every one matched at least one of these, all 12 real flyers matched none).
_BEACON_PATH_RE = re.compile(
    r'/(?:user-?sync\w*|sync|getuid|cm-notify|merge|tum|cookie|match|prebid|[bp]bsync|bsync|pbsync)'
    r'(?:/|$)|\.pixel$',
    re.IGNORECASE)
# A .php "image" is a beacon unless its filename says it serves media
# (image.php, thumb.php, getfile.php are real on older gallery sites).
_BEACON_PHP_RE = re.compile(r'/(?!\w*(?:image|img|photo|thumb|pic|media|file|download)\w*\.php$)\w+\.php$',
                            re.IGNORECASE)
_BEACON_QUERY_RE = re.compile(
    r'[?&](?:gdpr|gdpr_consent|redir|redirect|redirect_url|redirectUri|rur|ru|cr)=',
    re.IGNORECASE)
_BEACON_HOST_TOKENS = {'sync', 'usersync', 'csync', 'ssbsync', 'match', 'cm', 'pixel', 'beacon'}


def is_tracking_beacon_url(url):
    """True for ad-tech cookie-sync / tracking-pixel URLs masquerading as images."""
    if not url:
        return False
    path, _, query = url.partition('?')
    if query and _BEACON_QUERY_RE.search('?' + query):
        return True
    host = urlparse(url).hostname or ''
    if _BEACON_HOST_TOKENS & set(re.split(r'[.-]', host.lower())):
        return True
    return bool(_BEACON_PATH_RE.search(path) or _BEACON_PHP_RE.search(path))


# Sentinel mime value: the URL resolved (HTTP 200) to non-image content, so it
# is not a source image at all rather than a failed download.
NOT_AN_IMAGE = 'not-an-image'


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
                # A 200 that is not an image (an HTML page behind an <img>) is
                # definitively not a flyer -- distinguish it from a transient
                # miss so prepare_vision_content can drop it from coverage.
                return None, NOT_AN_IMAGE

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
    """Persist all source images once; failed downloads never become empty events."""
    import hashlib
    image_urls = extract_image_urls(content, base_url)
    if not image_urls:
        return None, 0
    key = hashlib.sha256(json.dumps(image_urls, sort_keys=True).encode()).hexdigest()
    cache = agent_extraction.work_dir() / 'vision_sources' / f'{key}.json'
    if cache.exists():
        saved = agent_extraction._read_json(cache)
        expected = len(image_urls) - len(saved.get('not_images', []))
        if saved.get('urls') != image_urls or len(saved.get('images', [])) != expected:
            raise AgentExtractionInvalid(f'Incomplete image snapshot: {cache}')
        return saved['images'], len(saved['images'])
    semaphore = asyncio.Semaphore(5)
    async def download(url):
        async with semaphore:
            return await download_and_encode_image(url)
    results = list(await asyncio.gather(*(download(url) for url in image_urls)))
    # The coverage gate below fails the whole extraction closed, so a single
    # transient miss (a 2.7 MB flyer timing out at 10s under 5-way concurrency
    # -- The Cobra Club, 2026-09-17) must not be terminal. Retry the misses
    # one at a time, twice, before giving up.
    def _missing():
        return [i for i, (data, mime) in enumerate(results)
                if not (data and mime) and mime != NOT_AN_IMAGE]
    for _attempt in range(2):
        missing = _missing()
        if not missing:
            break
        for i in missing:
            results[i] = await download_and_encode_image(image_urls[i])
    # URLs that resolved to non-image content are not source images; they
    # neither count toward coverage nor fail it (Basement NY's <img> pointing
    # at its own homepage, 2026-09-18).
    not_images = [image_urls[i] for i, (data, mime) in enumerate(results) if mime == NOT_AN_IMAGE]
    if not_images:
        print(f"    - Skipping {len(not_images)} non-image <img> source(s): {', '.join(not_images[:3])}")
    image_parts = [{'inline_data': {'mime_type': mime, 'data': data}}
                   for data, mime in results if data and mime and mime != NOT_AN_IMAGE]
    if len(image_parts) != len(image_urls) - len(not_images):
        failed = [image_urls[i] for i in _missing()]
        raise ExtractionCallFailure(
            f'{len(failed)} source images failed to download '
            f'after retries ({", ".join(failed[:3])}); complete vision coverage is required')
    if not image_parts:
        return None, 0
    agent_extraction.atomic_json(cache, {'urls': image_urls, 'images': image_parts, 'not_images': not_images})
    return image_parts, len(image_parts)


SCHEDULE_EXCEPTIONS_RULE = (
    'SCHEDULE EXCEPTIONS: Preserve the source\'s break/skip notices verbatim in '
    'the description when one is returned, including the dates and phrases such '
    'as "NO CLASS on November 11th", "Skip Thanksgiving", "NO SESSION NOV 9", '
    'or "except December 27". Do not paraphrase these notices away. Exclude '
    'the explicitly skipped sessions from occurrences; never refill them from '
    'the surrounding recurrence rule.'
)


EVENT_STATUS_RULE = (
    'EVENT STATUS: Calendar reservations marked "HOLD:" (for example, '
    '"HOLD: mri project"), private bookings, and availability blocks are not '
    'confirmed public events; omit them from event lists. Never remove a '
    'HOLD, cancellation, or postponement status marker to turn a listing into '
    'an apparently confirmed event. Preserve explicit status notices verbatim '
    'in any description returned for an existing event. A donation appeal '
    '(for example, a Giving Tuesday campaign asking for support without an '
    'attendable program) is not an event; actual benefit concerts, galas, '
    'volunteer sessions and other announced gatherings remain eligible. '
    'A lowercase title or missing description alone is not evidence of junk.'
)


def prompt_templates():
    """All extraction wording captured before a new run starts crawling."""
    names = ('VISION_PROMPT_TEMPLATE', 'ENRICHMENT_PROMPT_TEMPLATE',
             'CHUNK_PROMPT_TEMPLATE', 'SINGLE_PROMPT_TEMPLATE',
             'DETAIL_PROMPT_TEMPLATE', 'REFERENCE_PROMPT_TEMPLATE',
             'SCHEDULE_EXCEPTIONS_RULE', 'EVENT_STATUS_RULE', 'DETAIL_RULES',
             'CHUNK_RULES', 'FULL_PASS_RULE', 'COVERAGE_REVIEW_RULE')
    return {**{name: globals()[name] for name in names},
            'intro': city_config.extraction_intro(),
            'chunk_intro': city_config.extraction_chunk_intro(),
            'region_rule': city_config.extraction_region_rule(),
            'tag_avoidance': city_config.extraction_tag_avoidance()}


def _prompt_rule(name):
    if name in globals():
        current = globals()[name]
    else:
        current = getattr(city_config, 'extraction_' + name)()
    return agent_extraction.prompt_text(name, current)


VISION_PROMPT_TEMPLATE = '''Today's date is {current_date_string}. We are extracting events from {name} ({url}).

You have TWO sources for this venue's events: the page text below, and the
attached images (event flyers/posters). Use BOTH. Many events appear only in the
text, many only on a flyer, and some in both — extract the union, once each.

For EACH event you find in EITHER source, extract:
- name: The event name
- location: The venue name (default to "{name}" if not specified)
- occurrences: Array of dates/times, read from the text or the image (e.g., "January 16, 2026" or "Jan 16 - Feb 14"). Each occurrence has:
  - start_date: Date in YYYY-MM-DD format
  - start_time: Time if shown in canonical 12-hour format (e.g., "6pm", "6:30pm")
  - end_date: End date if this is a multi-day event/exhibition
  - end_time: End time if shown
- description: Brief description based on the text and image. If neither gives detail beyond the event name, use "No description available." Do NOT fabricate.
- url: The event's own link if the text gives one, else null
- hashtags: 4-7 CamelCase tags. Always include at least one category (Music, Nightlife, Comedy, Art, Theater, Dance, Film, Literature, Community, Family, Wellness, Education, Outdoor, Sports, Games). Add Free if free, Virtual if online. Then granular tags.
- emoji: A single emoji representing the event
{note_section}
Rules:
- {SCHEDULE_EXCEPTIONS_RULE}
- {EVENT_STATUS_RULE}
- Cover BOTH sources: every flyer image provided AND the full page text below
- Do not list the same event twice because it appears in both — merge it
- Only include events that appear to be upcoming (after {current_date_string})
- For art exhibitions, the start_date is opening day and end_date is closing day
- If you can't read a date clearly, skip that event
- Gallery hours (like "Wed-Sat 1-6pm") are NOT start/end times - those are for visitors
{rid_section}
Page text (authoritative for dates — the flyer images are often undated, and on
social feeds the date/time is stated in the caption rather than on the image.
Where the text and an image disagree, prefer the text):
{text_content}'''


def get_vision_prompt(url, text_content, current_date_string, name, notes, request_id=""):
    """Generate a prompt for vision-based event extraction."""
    note_section = f"\n\nIMPORTANT: {notes}" if notes else ""
    rid_section = f"\n\nIMPORTANT: Set request_id to \"{request_id}\" in your response." if request_id else ""

    return _prompt_rule("VISION_PROMPT_TEMPLATE").format(
        current_date_string=current_date_string,
        name=name,
        url=url,
        note_section=note_section,
        SCHEDULE_EXCEPTIONS_RULE=_prompt_rule("SCHEDULE_EXCEPTIONS_RULE"),
        EVENT_STATUS_RULE=_prompt_rule("EVENT_STATUS_RULE"),
        rid_section=rid_section,
        text_content=text_content or "No additional text")


async def extract_with_vision(url, content, current_date_string, name, notes, base_url=None):
    """
    Extract events from images using local agent responses.

    Downloads and snapshots images for the supervising agent to inspect.
    Returns JSON string with extracted events.
    """
    # Prepare image content
    image_parts, image_count = await prepare_vision_content(content, base_url)

    if not image_parts:
        print("    - No valid images found for vision extraction")
        raise ExtractionCallFailure("No usable images for vision extraction")

    print(f"    - Processing {image_count} images with vision...")

    # Build prompt
    prompt_text = get_vision_prompt(url, content, current_date_string, name, notes)

    try:
        response_text = await llm_providers.generate_structured(
            prompt_text, EventList, GEMINI_TIMEOUT * 2,  # Double timeout for vision
            provider=llm_providers.provider_for('vision'),
            images=image_parts,
        )

        # Validate JSON
        try:
            parsed = json.loads(response_text)
            event_count = len(parsed.get('events', []))
            print(f"    - Vision extracted {event_count} events from images")
        except json.JSONDecodeError as exc:
            raise ExtractionCallFailure("Invalid vision extraction JSON") from exc

        return response_text

    except llm_providers.ProviderCallFailure as e:
        raise ExtractionCallFailure(f"Vision extraction failed: {e}") from e


# =============================================================================
# Content Chunking Functions
# =============================================================================

def _is_event_chunk_marker(line):
    # Crawl markdown can wrap the same linked h3 card in a list item. Keep
    # other heading levels on the size path: e.g. Drom puts the date BEFORE
    # its h5 title, so cutting at that title separates the event from its date.
    return bool(re.match(r'^\s*\d+\.\s*###\s*\[', line)
                or line.strip().startswith('### [')
                or re.match(r'^[ \t]*[*-][ \t]+###[ \t]+\[', line))


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
        if _is_event_chunk_marker(line):
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


# A markdown heading line, in every shape a crawled listing actually uses:
# `# [Title](url)`, `### [Title](url)`, `#### Title`, and bulleted/numbered
# variants like `  * ### [Title](url)` or `1. ### [Title](url)`.
# Deliberately broader than _EVENT_HEADING_RE (which requires a link and `##`+)
# because this is used only to decide where NOT to cut, where a false positive
# costs nothing.
_HEADING_LINE_RE = re.compile(r'^[ \t]*(?:[\*\-]\s+|\d+\.\s+)?#{1,6}\s+\S')
_DETAIL_RECORD_LINE_RE = re.compile(r'^\s*EVENT DETAIL URL:\s*https?://\S+\s*$')


def _is_heading_line(line):
    return bool(_HEADING_LINE_RE.match(line))


def _extend_back_over_headings(lines, idx):
    """Index of the first line in the run of consecutive headings ending at `idx`.

    Blank lines between headings are tolerated; the walk stops at the first
    non-blank, non-heading line. `lines[idx]` is assumed to be a heading.
    """
    start = idx
    j = idx - 1
    while j >= 0:
        if _is_heading_line(lines[j]):
            start = j
        elif lines[j].strip():
            break
        j -= 1
    return start


def _split_trailing_heading(text):
    """Peel a trailing run of heading lines off `text`.

    Returns `(kept, carried)`. `carried` is the trailing heading run (plus any
    blank lines around it) that must NOT be left at the end of a chunk, because
    a chunk ending on an event's heading puts that event's date/body in the
    NEXT chunk and Gemini then emits a name with `occurrences: null`.

    Returns `(text, '')` when the last non-blank line isn't a heading, or when
    the whole chunk is headings (nothing left to keep).
    """
    lines = text.split('\n')
    i = len(lines) - 1
    while i >= 0 and not lines[i].strip():
        i -= 1
    if i < 0 or not _is_heading_line(lines[i]):
        return text, ''

    start = _extend_back_over_headings(lines, i)
    if start == 0:
        return text, ''
    return '\n'.join(lines[:start]), '\n'.join(lines[start:])


def _split_trailing_record(text, cap):
    """Peel the trailing PARTIAL RECORD off `text`.

    A chunk that ends a few lines after an event's heading strands the rest of
    that event (typically its date line) in the next chunk — the same failure as
    a chunk ending on the heading itself, just one line later (Alamo Brooklyn
    w3253 "Where is the Friend's House?": heading + synopsis closed the chunk and
    `Showtimes: August 21, 2026 at 12:30pm` opened the next one).

    Carries everything from the last heading or explicit EVENT DETAIL URL line
    (including heading-less feeds such as Viewcy). Headings extend back over a run of
    consecutive headings above it — into the next chunk, so every chunk after
    the first STARTS on a record boundary. Falls back to `_split_trailing_heading`
    when that tail is bigger than `cap` (a very long record would otherwise
    ping-pong whole chunks forward).
    """
    lines = text.split('\n')
    last = None
    for idx, line in enumerate(lines):
        if _is_heading_line(line) or _DETAIL_RECORD_LINE_RE.match(line):
            last = idx
    if last is None:
        return text, ''

    # Extend back over consecutive headings so a section banner travels with the
    # record it introduces (`## Wednesday` + `### [Show](url)`).
    start = _extend_back_over_headings(lines, last)
    if start == 0:
        return text, ''
    carried = '\n'.join(lines[start:])
    kept = '\n'.join(lines[:start])
    if len(carried) > cap or not kept.strip():
        return _split_trailing_heading(text)
    return kept, carried


def _json_record_spans(line):
    """Exact spans of records in a JSON feed, excluding nested child objects.

    Only accept an entire valid JSON line and explicit collection keys. A
    literal `},{` can also occur inside descriptions or nested ticket/venue
    arrays, so it is not evidence of an event boundary.
    """
    decoder = json.JSONDecoder()
    try:
        root = json.loads(line)
        if not isinstance(root, (dict, list)):
            return []
        spans = []

        def skip(pos):
            while pos < len(line) and line[pos].isspace():
                pos += 1
            return pos

        def array_spans(pos):
            pos = skip(pos + 1)
            while line[pos] != ']':
                value, end = decoder.raw_decode(line, pos)
                if isinstance(value, dict):
                    spans.append((pos, end))
                pos = skip(end)
                if line[pos] == ',':
                    pos = skip(pos + 1)

        pos = skip(0)
        if isinstance(root, list):
            array_spans(pos)
        else:
            pos = skip(pos + 1)
            while line[pos] != '}':
                key, end = decoder.raw_decode(line, pos)
                pos = skip(skip(end) + 1)  # colon
                value, end = decoder.raw_decode(line, pos)
                if key in {'events', 'items', 'products', 'upcoming', 'past'} and isinstance(value, list):
                    array_spans(pos)
                pos = skip(end)
                if line[pos] == ',':
                    pos = skip(pos + 1)
        return spans
    except (ValueError, IndexError):
        return []


def _split_long_line(line, max_chars):
    """Split a single line that is itself longer than `max_chars`.

    Without this, one gigantic line is appended whole and yields one gigantic
    chunk (measured: a 303,877-char single-line JSON dump from Skinny Dennis
    w4832 that Gemini answered with 3 events). Valid JSON feeds protect whole
    top-level records that fit the cap. Other text and oversized records fall
    back to `},{`, whitespace, then a hard cut.
    """
    if len(line) + 1 <= max_chars:
        return [line]

    pieces = []
    record_spans = _json_record_spans(line)
    offset = 0
    remaining = line
    floor = int(max_chars * 0.5)
    while len(remaining) + 1 > max_chars:
        window = remaining[:max_chars - 1]
        cut = window.rfind('},{')
        if cut >= floor:
            cut += 2  # keep `},` with the piece we're closing
        else:
            cut = window.rfind(' ')
            if cut < floor:
                cut = max_chars - 1
        # Move a cut inside a known record back to its start. If the record
        # itself exceeds the cap, retain the bounded fallback instead of
        # producing an oversized chunk or looping forever.
        for start, end in record_spans:
            if start < offset + cut < end:
                if start > offset:
                    cut = start - offset
                break
        pieces.append(remaining[:cut])
        tail = remaining[cut:]
        remaining = tail.lstrip()
        offset += cut + len(tail) - len(remaining)
    if remaining:
        pieces.append(remaining)
    return pieces


def chunk_content_by_size(content, max_chars=MAX_CHUNK_CHARS):
    """
    Split content into chunks by character count, breaking at paragraph boundaries.

    Used as fallback when event markers aren't found. Tries to split at double
    newlines (paragraphs) to keep related content together.

    Two invariants this path is responsible for, both learned the hard way:

    1. *Prefer complete records when their boundaries are known.* A paragraph
       or line boundary can land right after an event's
       heading and strand its date in the next chunk (Elsewhere w75 "Klingande":
       chunk 1 ended `  * ### [Klingande](…)`, chunk 2 began
       `**Fri, September 4, 2026 …**`, extraction returned the name with
       `occurrences: null`). Whatever sits after the last heading of a closing
       chunk is carried into the next one, so every chunk after the first STARTS
       at a record boundary — the same guarantee `chunk_content_by_events` gives,
       without changing which pages take which path.
    2. *No chunk exceeds `max_chars`.* A single line longer than the cap used to
       be appended whole; `_split_long_line` breaks it up instead.

    Returns a list of content strings, one per chunk.
    """
    if len(content) <= max_chars:
        return [content]

    # A carried tail leads the next chunk, so cap it well below max_chars.
    carry_cap = max(1, int(max_chars * CARRY_CAP_FRACTION))

    chunks = []
    carry = ['']  # trailing partial record deferred from the previous chunk

    def emit(text):
        """Close a chunk, holding back its trailing partial record."""
        kept, carried = _split_trailing_record(text, carry_cap)
        if carried and kept.strip():
            chunks.append(kept)
            carry[0] = carried
        else:
            chunks.append(text)
            carry[0] = ''

    def put_carry_back():
        """Undo the last carry when the next unit cannot share a chunk with it.

        Re-attaching is better than emitting a record fragment on its own; this
        only fires for a paragraph so large that carry + paragraph exceed the cap.
        """
        if carry[0] and chunks:
            chunks[-1] = chunks[-1] + '\n' + carry[0]
            carry[0] = ''

    # Split by paragraphs (double newlines)
    paragraphs = re.split(r'\n\n+', content)

    current_chunk = []
    current_size = 0

    def seed_paragraph_chunk():
        nonlocal current_chunk, current_size
        current_chunk = [carry[0]] if carry[0] else []
        current_size = (len(carry[0]) + 2) if carry[0] else 0
        carry[0] = ''

    for para in paragraphs:
        para_size = len(para) + 2  # +2 for the newlines we'll add back

        # If single paragraph exceeds max, split it by lines
        if para_size > max_chars:
            # First, save current chunk if any
            if current_chunk:
                emit('\n\n'.join(current_chunk))
                current_chunk = []
                current_size = 0
                if carry[0] and len(carry[0]) + 1 + len(para) > max_chars:
                    # The line splitter below re-packs anyway, so only put the
                    # carry back when it cannot lead even one line of this
                    # paragraph.
                    first_line = para.split('\n', 1)[0]
                    if len(carry[0]) + 1 + len(first_line) + 1 > max_chars:
                        put_carry_back()

            # Split large paragraph by lines
            line_chunk = [carry[0]] if carry[0] else []
            line_size = (len(carry[0]) + 1) if carry[0] else 0
            carry[0] = ''
            for line in para.split('\n'):
                for piece in _split_long_line(line, max_chars):
                    if line_size + len(piece) + 1 > max_chars and line_chunk:
                        emit('\n'.join(line_chunk))
                        if carry[0] and len(carry[0]) + len(piece) + 2 > max_chars:
                            put_carry_back()
                        line_chunk = [carry[0]] if carry[0] else []
                        line_size = (len(carry[0]) + 1) if carry[0] else 0
                        carry[0] = ''
                    line_chunk.append(piece)
                    line_size += len(piece) + 1
            if line_chunk:
                emit('\n'.join(line_chunk))
            seed_paragraph_chunk()
        elif current_size + para_size > max_chars and current_chunk:
            # Save current chunk and start new one
            emit('\n\n'.join(current_chunk))
            if carry[0] and len(carry[0]) + 2 + para_size > max_chars:
                put_carry_back()
            seed_paragraph_chunk()
            current_chunk.append(para)
            current_size += para_size
        else:
            current_chunk.append(para)
            current_size += para_size

    # Add remaining content
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
    elif carry[0]:
        chunks.append(carry[0])

    return chunks


def cap_records_per_chunk(chunks, max_records):
    """Subdivide any chunk holding more than `max_records` record headings.

    A post-pass, deliberately: it runs after whichever chunker produced the list,
    splits ONLY at heading lines, and never grows a chunk — so it cannot sever a
    record, cannot fight `chunk_content_by_size`'s trailing-record carry, and
    cannot push a chunk past `max_chars`. Pieces are balanced (13/13/13 rather
    than 25/25/1) so no piece is left with a token-budget cliff of its own.

    `max_records` falsy -> the chunk list is returned unchanged (the default;
    see `max_records_per_chunk` above for why this is opt-in).
    """
    if not max_records:
        return chunks

    out = []
    for chunk in chunks:
        lines = chunk.split('\n')
        starts = [i for i, line in enumerate(lines) if _is_heading_line(line)]
        if len(starts) <= max_records:
            out.append(chunk)
            continue
        n_pieces = -(-len(starts) // max_records)          # ceil
        per_piece = -(-len(starts) // n_pieces)            # balanced
        cuts = [starts[k] for k in range(per_piece, len(starts), per_piece)]
        prev = 0
        for cut in cuts:
            out.append('\n'.join(lines[prev:cut]))
            prev = cut
        out.append('\n'.join(lines[prev:]))
    return out


# A calendar date written out in a form a listing actually enumerates:
# "September 6, 2026", "Sep 6", "Sept. 6", "2026-09-06", "08/30", "8/30/26".
# Deliberately does NOT match a naked day number, so "Jan 11, 18, 25" counts as
# one: the estimate errs LOW, and undercounting only means we decline to split
# (the status quo), whereas overcounting would split ordinary pages needlessly.
# The slash form is month-first, range-checked, and fenced off from adjacent
# digits, slashes and decimal points, so it matches `### Sunday - 08/30` but
# not a version (`v1.2/3.4`), a price, or a date inside a URL path (which the
# prompt forbids extracting anyway). Measured over 10 days of crawls it adds
# 0.35pp of chunks.
_DATE_TOKEN_RE = re.compile(
    r'\b(?:January|February|March|April|May|June|July|August|September|October|'
    r'November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?\s+\d{1,2}\b'
    r'|\b\d{4}-\d{2}-\d{2}\b'
    r'|(?<![\d/.])(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])(?:/\d{2,4})?(?![\d/]|\.\d)',
    re.IGNORECASE)


def count_date_tokens(text):
    """How many occurrence objects `text` is likely to demand from the model."""
    return len(_DATE_TOKEN_RE.findall(text or ''))


def cap_occurrences_per_chunk(chunks, budget=OCCURRENCE_BUDGET_PER_CHUNK):
    """Subdivide any chunk whose text enumerates more than `budget` dates.

    The same post-pass shape as `cap_records_per_chunk` — splits ONLY at heading
    lines, so it cannot sever a record, and no piece ever exceeds max_chars. The
    difference is what it budgets: OUTPUT (occurrence objects the response must
    carry) rather than input size or record count. See
    OCCURRENCE_BUDGET_PER_CHUNK for the measurements.

    Records are packed greedily, and a piece always takes at least one record —
    a SINGLE record listing more than `budget` dates cannot be split at a
    heading and is passed through unchanged (the shortfall warning in
    `_execute_chunked_sync` is what covers that residual case).

    A short page PREAMBLE (whatever precedes the first heading) is repeated at
    the head of each piece. That is the one place this differs from
    `cap_records_per_chunk`, and it is not cosmetic: on w944 the preamble is the
    line carrying the venue name and street address, and pieces that lost it
    came back with `location: "game bar or backyard"` — the card's *Space:*
    line — instead of "The Tiny Cupboard". `max_chars` is still respected.
    """
    if not budget:
        return chunks

    out = []
    for chunk in chunks:
        if count_date_tokens(chunk) <= budget:
            out.append(chunk)
            continue

        lines = chunk.split('\n')
        starts = [i for i, line in enumerate(lines) if _is_heading_line(line)]
        if len(starts) < 2:
            out.append(chunk)          # nothing to split at
            continue

        preamble = '\n'.join(lines[:starts[0]]).strip()
        if len(preamble) > PREAMBLE_CARRY_MAX_CHARS:
            preamble = ''

        # Record i spans [starts[i], starts[i+1]); the preamble rides along with
        # the first piece naturally and is repeated onto the rest.
        bounds = starts + [len(lines)]
        pieces, cur_start, cur_dates = [], 0, 0
        for i in range(len(starts)):
            body = '\n'.join(lines[bounds[i]:bounds[i + 1]])
            n = count_date_tokens(body)
            # Cut BEFORE this record when it would blow the budget — but never
            # emit an empty piece, so the first record of a piece always lands.
            if cur_start < starts[i] and cur_dates + n > budget:
                pieces.append('\n'.join(lines[cur_start:starts[i]]))
                cur_start, cur_dates = starts[i], 0
            cur_dates += n
        pieces.append('\n'.join(lines[cur_start:]))

        for j, piece in enumerate(p for p in pieces if p.strip()):
            if j and preamble and len(piece) + len(preamble) + 1 <= MAX_CHUNK_CHARS:
                piece = preamble + '\n' + piece
            out.append(piece)
    return out


def _bound_event_chunk(chunk, max_chars):
    """Bound an oversized event chunk, keeping every record that fits intact.

    The marker-only splitter deliberately permits an oversized record and its
    size guard checks only after a record has been appended. Repack complete
    records before falling back to the size splitter for an individually huge
    record or preamble. Chunks already within the limit remain byte-identical.
    """
    if len(chunk) <= max_chars:
        return [chunk]
    records = []
    current = []
    for line in chunk.splitlines(keepends=True):
        if current and _is_event_chunk_marker(line):
            records.append(''.join(current))
            current = []
        current.append(line)
    if current:
        records.append(''.join(current))

    chunks, pending = [], ''
    for record in records:
        if len(record) > max_chars:
            if pending:
                chunks.append(pending)
                pending = ''
            chunks.extend(piece for piece in chunk_content_by_size(record, max_chars)
                          if piece.strip())
        elif pending and len(pending) + len(record) > max_chars:
            chunks.append(pending)
            pending = record
        else:
            pending += record
    if pending:
        chunks.append(pending)
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

    # Bound only oversized chunks, preserving complete records that fit. Merely
    # checking size at the next marker can still overshoot by an entire record.
    # The common case (no oversized chunk) stays byte-for-byte unchanged.
    if len(event_chunks) > 1:
        if any(len(chunk) > max_chars for chunk in event_chunks):
            event_chunks = [bounded for chunk in event_chunks
                            for bounded in _bound_event_chunk(chunk, max_chars)]
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

# ---------------------------------------------------------------------------
# Listing content hygiene (agent-extraction cost controls)
# ---------------------------------------------------------------------------
# Measured on the 2026-09-18 run (524 listing packets, 14.6M chars): identical
# long paragraphs repeated within one page (a carousel plus the list it
# duplicates on bardavon.org, National Sawdust's grid + list, two IFC pages
# concatenated) were 2.5% of all listing text and up to 33% of a single site;
# 34 of the 76 empty packets had no date token at all. Both are removed
# mechanically here, BEFORE chunking, so no packet is ever built for them.
# Far-future pruning drops a chunk only when every dated mention carries a
# year and all of them sit past the publish window plus a buffer; pages that
# print dates without years (most calendars) never qualify.

DEDUPE_PARAGRAPH_MIN_CHARS = 120
FAR_FUTURE_BUFFER_DAYS = 30
FAR_FUTURE_MIN_DATES = 3
_HTTP_LINK_RE = re.compile(r'\]\(https?://')
_TIME_TOKEN_RE = re.compile(r'\b(?:[01]?\d|2[0-3])(?::[0-5]\d)?\s*(?:am|pm|a\.m\.|p\.m\.)\b', re.IGNORECASE)


def dedupe_repeated_paragraphs(content, min_chars=DEDUPE_PARAGRAPH_MIN_CHARS):
    """Drop later byte-identical copies of long paragraphs. Returns (text, removed_chars).

    Only paragraphs of at least `min_chars` are candidates, so a repeated short
    line ("Buy Tickets", a shared date header) is never touched; a repeated long
    block is the same card rendered twice, and the merger would collapse the
    duplicate anyway.
    """
    if not content:
        return content, 0
    paragraphs = re.split(r'(\n\n+)', content)
    seen = set()
    out = []
    removed = 0
    skip_next_sep = False
    for piece in paragraphs:
        if piece.startswith('\n'):
            if skip_next_sep:
                skip_next_sep = False
                continue
            out.append(piece)
            continue
        key = piece.strip()
        if len(key) >= min_chars and key in seen:
            removed += len(piece)
            skip_next_sep = True
            continue
        seen.add(key)
        out.append(piece)
    text = ''.join(out)
    return (text, removed) if removed else (content, 0)


def chunk_is_chrome_only(chunk):
    """True when a chunk carries no date, time, link or detail-URL marker at all."""
    if not chunk or not chunk.strip():
        return True
    if _DETAIL_URL_MARKER_RE.search(chunk) or _HTTP_LINK_RE.search(chunk):
        return False
    if count_date_tokens(chunk) or _TIME_TOKEN_RE.search(chunk):
        return False
    return True


def _full_dates(text):
    dates = []
    for m in _MONTH_DAY_YEAR_RE.finditer(text):
        try:
            dates.append(date(int(m.group(3)), _MONTH_ABBREVS[m.group(1).lower()[:3]], int(m.group(2))))
        except (ValueError, KeyError):
            continue
    for rx, order in ((_ISO_DATE_RE, (1, 2, 3)), (_NUMERIC_DATE_RE, (3, 1, 2))):
        for m in rx.finditer(text):
            try:
                dates.append(date(int(m.group(order[0])), int(m.group(order[1])), int(m.group(order[2]))))
            except ValueError:
                continue
    return dates


def chunk_is_beyond_window(chunk, today=None, window_days=None, buffer_days=FAR_FUTURE_BUFFER_DAYS):
    """True when every dated mention in `chunk` carries a year and all sit past the
    publish window (+buffer). Requires FAR_FUTURE_MIN_DATES fully-qualified dates
    and no year-less date tokens, so a calendar that prints "Sat, Sep 26" next to
    a stray "2027" is never pruned."""
    if not chunk:
        return False
    today = today or datetime.now().date()
    window_days = constants.FUTURE_WINDOW_DAYS if window_days is None else window_days
    full = _full_dates(chunk)
    if len(full) < FAR_FUTURE_MIN_DATES:
        return False
    # Every date token must be one of the fully-qualified mentions; month-day
    # tokens without a year (or slash dates without a year) disqualify.
    if count_date_tokens(chunk) > len(full):
        return False
    horizon = today + timedelta(days=window_days + buffer_days)
    return min(full) > horizon


def prune_chunks(chunks, today=None):
    """Return (kept_chunks, pruned) where pruned is [(index, reason, chars)]."""
    kept, pruned = [], []
    for i, chunk in enumerate(chunks):
        if chunk_is_chrome_only(chunk):
            pruned.append((i, 'chrome-only', len(chunk)))
        elif chunk_is_beyond_window(chunk, today):
            pruned.append((i, 'beyond-window', len(chunk)))
        else:
            kept.append(chunk)
    return kept, pruned


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


_SNIPPET_HEADING_RE = re.compile(
    r'^[ \t]*(?:[\*\-]\s+|\d+\.\s+)?#{1,6}\s+(.+?)[ \t]*$',
    re.MULTILINE,
)


def _snippet_title_key(title):
    """Ignore presentation punctuation, never words, in event identities."""
    title = unicodedata.normalize('NFKC', html.unescape(title)).casefold()
    return ''.join(char for char in title if char.isalnum())


def _snippet_text(text):
    # Images often precede the NEXT card's heading. Neither their captions nor
    # enormous CDN URLs are descriptive evidence for the current card.
    # Stop rather than merely remove: dates between a following image and its
    # heading also belong to the next card (e.g. Emelin's show list).
    image = re.search(r'^.*!\[', text, flags=re.MULTILINE)
    if image:
        text = text[:image.start()]
    text = re.sub(r'\[([^\]\n]*)\]\([^\n]*?\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    return '\n'.join(line.strip() for line in text.splitlines() if line.strip())


def extract_content_snippets(event_names, content, snippet_chars=500):
    """Return context only for unambiguously identified event heading blocks.

    A title mentioned in another card, image alt text, or navigation is not an
    identity match. Missing/ambiguous headings deliberately omit context so the
    enrichment can fall back to detail crawling rather than inventing evidence.
    """
    if not content or snippet_chars <= 0:
        return {}

    headings = list(_SNIPPET_HEADING_RE.finditer(content))
    cards = {}
    for index, heading in enumerate(headings):
        title = heading.group(1).rstrip('#').strip()
        # Greedy label permits titles such as ADVENTURE[s]. The URL is used
        # only to distinguish repeated renderings from different same-name
        # events; no fuzzy title or first-significant-word fallback is safe.
        link = re.fullmatch(r'\[(.*)\]\((\S+?)(?:\s+[\"\'].*)?\)', title)
        url = link.group(2) if link else None
        title = link.group(1) if link else title
        if '![' in title:
            continue
        key = _snippet_title_key(title)
        end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
        body = _snippet_text(content[heading.end():end])
        text = _snippet_text(title) + ('\n' + body if body else '')
        cards.setdefault(key, []).append((url, text))

    snippets = {}
    for name in event_names:
        matches = cards.get(_snippet_title_key(name), [])
        if not matches:
            continue
        identities = {url if url else text for url, text in matches}
        if len(identities) != 1:
            continue
        # Repeated copies with the same explicit URL describe the same card.
        snippets[name] = matches[0][1][:snippet_chars].strip()
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


ENRICHMENT_PROMPT_TEMPLATE = '''For each event at {venue_name}, provide:
- description: 1-3 sentence description built from words and sentences that actually appear in the event's own Context block. If there is no Context block, or it only has the name, date/time, venue, and links — with no descriptive prose — return EXACTLY "No description available." Do NOT paraphrase the event name. Do NOT write generic filler like "is a local community event" or "visit the official website for more details". Do NOT use background knowledge about the artist, venue, or topic. Each event's description must come from THAT event's Context block, not a neighbor's.
- hashtags: 4-7 CamelCase tags. Always include at least one category (Music, Nightlife, Comedy, Art, Theater, Dance, Film, Literature, Community, Family, Wellness, Education, Outdoor, Sports, Games). Add Free if free, Virtual if online. Then granular tags.
- emoji: Single emoji representing the event

{SCHEDULE_EXCEPTIONS_RULE}
{EVENT_STATUS_RULE}

Examples:
  Context only has name + date + venue → description="No description available."
  Context has a sentence describing the event → use that sentence (lightly compressed if needed)

Events to enrich:
{events_section}
{rid_section}
Return a JSON object with an "enrichments" array, containing exactly one object per requested event name.'''


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

    return _prompt_rule("ENRICHMENT_PROMPT_TEMPLATE").format(
        venue_name=venue_name,
        SCHEDULE_EXCEPTIONS_RULE=_prompt_rule("SCHEDULE_EXCEPTIONS_RULE"),
        EVENT_STATUS_RULE=_prompt_rule("EVENT_STATUS_RULE"),
        events_section=events_section,
        rid_section=rid_section)


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
        # Soft failure on purpose: a failed enrichment leaves the events with
        # "No description available." rather than failing the whole extraction,
        # which is the pre-existing contract for this call.
        response_text = await llm_providers.generate_structured(
            prompt, EnrichmentBatch, GEMINI_TIMEOUT,
            provider=llm_providers.provider_for('enrichment'),
            expected_names=event_names,
        )
        result = json.loads(response_text)
    except (AgentExtractionPending, AgentExtractionInvalid):
        raise
    except Exception as e:
        # The dominant failure here is an over-long batch overrunning the output
        # budget, which takes every event in the batch down with it. Split and
        # retry so only the genuinely oversized group degrades — see
        # ENRICHMENT_MIN_BATCH. Bounded: halving terminates at the floor.
        if len(event_names) > ENRICHMENT_MIN_BATCH:
            mid = len(event_names) // 2
            print(f"    - Enrichment batch of {len(event_names)} failed ({e}); "
                  f"retrying as {mid} + {len(event_names) - mid}")
            first = await enrich_events_batch(event_names[:mid], venue_name, content)
            second = await enrich_events_batch(event_names[mid:], venue_name, content)
            return {**first, **second}
        print(f"    - Enrichment batch error ({len(event_names)} events): {e}")
        return {}

    items = result.get('enrichments', [])
    if {item.get('name') for item in items} != set(event_names) or len(items) != len(set(event_names)):
        raise AgentExtractionInvalid("Enrichment must cover each requested event name exactly once")
    out = {}
    for item in items:
        out[item.get('name', '')] = _grounded_enrichment(item, content_snippets)
    return out


def _grounded_enrichment(item, content_snippets):
    """An unverified title match cannot authorize a generated description."""
    desc = (item.get('description') or '').strip()
    if (not desc or item.get('name') not in (content_snippets or {})
            or _looks_like_boilerplate_fabrication(desc)):
        desc = 'No description available.'
    return {
        'description': desc,
        'hashtags': item.get('hashtags', []),
        'emoji': item.get('emoji', '📅'),
    }


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


DETAIL_RULES = """CRITICAL — DESCRIPTION: The description MUST be derived from words and sentences actually present on the page. If the page only contains the event name, date/time, venue, and links (no descriptive prose), set description to exactly "No description available." Do NOT paraphrase the event name. Do NOT write generic filler like "is a local community event" or "visit the official website for more details". Do NOT use background knowledge about the artist, venue, or topic. If you would only be guessing, return "No description available." instead.

NOT A DESCRIPTION — admission boilerplate and venue marketing. Ticketing sites and venue pages pad every event with the same house copy. It is about the TICKET or the VENUE, not about this event, so it must never become the description. Ignore: door/show times and "front bar opens" notes; age limits and ID/passport policy; RSVP, capacity or door-discretion policy; ticket-tier, seating or lounge perks (e.g. "Preferred Mezzanine includes access to..."); bottle service, table sales and VIP contact addresses; refund, exchange and resale terms; minimum-purchase, tax and gratuity rules; dress code; and the venue's code of conduct or safer-space / anti-discrimination statement. Also ignore boilerplate that describes the PLACE or the promoter rather than this event — a venue's own blurb about its history, capacity, view, atmosphere, menu or lineup of "legends who played here", and an organizer's "we are the world's largest community of..." pitch. If everything on the page is that kind of text, return exactly "No description available." — no description is better than a description of the wrong thing.

CRITICAL: Only return occurrences for SPECIFIC calendar dates that are EXPLICITLY stated on the page. If the page describes a permanent exhibit, ongoing installation, recurring schedule (e.g. "Fridays 7pm"), or has no specific date listed, return occurrences=null. Do NOT fabricate dates, do NOT default to today, do NOT approximate from descriptive text like "spring 2026" or "ongoing". An approximate or invented date is worse than no date.

OCCURRENCES = WHEN THE EVENT ITSELF HAPPENS. If the page lists a multi-day schedule that mixes the actual event with preparatory or ancillary days (e.g. expo, packet/bib pickup, registration, vendor setup, rehearsal, soundcheck, load-in, after-party, awards ceremony), return ONLY the day(s) the event itself takes place. Pickup/expo/setup days are logistics, not occurrences of the event. Example: a race page showing "Wed-Fri Expo / Sat Race" should return only Saturday.

RECEPTION vs EXHIBITION RUN: If the named event is an opening/closing reception, opening night, preview, or launch tied to an exhibition, occurrences = ONLY that reception's own date and time (a single-day event). Do NOT add the exhibition's broader on-view run (e.g. "on view June 4 – July 10") as an additional occurrence — that run belongs to the exhibition itself, which is a separate event."""


def detail_instructions(notes=""):
    """Static detail-page rules plus the site's notes, shared by every detail packet.

    Identical text for every event of a website, so it is hashed into the packet's
    `instructions` and read once per website by the reviewer instead of once per
    page (`agent_extraction.read --omit-instructions`).
    """
    notes = (notes or "").strip()
    note_section = f"\n\nIMPORTANT (site notes): {notes}" if notes else ""
    return (_prompt_rule('DETAIL_RULES') + '\n\n'
            + _prompt_rule('SCHEDULE_EXCEPTIONS_RULE') + '\n\n'
            + _prompt_rule('EVENT_STATUS_RULE') + note_section)


DETAIL_PROMPT_TEMPLATE = (
    'Today\'s date is {current_date}. '
    'Extract information about the event "{event_name}" from this web page. '
    'Include the venue name if it appears on the page.\n'
    '{url_section}\n'
    'Page content:\n\n{content}'
)


async def extract_single_event(event_name, content, notes="", url=""):
    """
    Extract event details from a single event page.

    Used by the detail crawl step for events that got "No description
    available." or missing location/times from the listing page. Uses validated
    local agent responses for reliable parsing.

    Args:
        event_name: name the listing gave this event
        content: the detail page's crawled text
        notes: the site's `websites.notes`, injected the same way the listing
            extraction injects it (`get_prompt`/`get_chunk_prompt`). Without
            this a per-site directive — "this series prints its whole season
            on every dated page, date each record only with the date beside
            its own title" — held for the listing pass and was then thrown
            away by the detail pass, which re-derived the union.
        url: the page's own URL. Site notes routinely key off it (Bryant
            Park's dated series pages carry the installment date in the path),
            and it is the only signal distinguishing one dated page of a
            series from another when the body lists them all.

    Returns dict with 'description', 'hashtags', 'emoji', and optionally
    'location', 'sublocation', 'occurrences', or None on failure.
    """
    if not llm_providers.is_configured(llm_providers.provider_for('detail'), genai_client):
        return None

    notes = _strip_legacy_directives(notes, 'detail page')
    url_section = f'This page\'s URL is {url}\n' if url else ""

    current_date = agent_extraction.reference_date()
    # The static rules ride in the packet's shared `instructions` (read once per
    # instructions hash by the reviewing agent); the prompt keeps only what is
    # specific to this page. Site notes are per-website, so they share too.
    instructions = detail_instructions(notes)
    prompt = _prompt_rule('DETAIL_PROMPT_TEMPLATE').format(
        current_date=current_date, event_name=event_name,
        url_section=url_section, content=content)

    estimated_tokens = (len(prompt) + len(instructions)) // CHARS_PER_TOKEN
    if estimated_tokens > MAX_REQUEST_TOKENS:
        # The caller has saved the full source for review. Failing the phase
        # retains it and does not consume a detail attempt; clipping the input
        # would instead produce a seemingly complete answer from partial dates.
        raise ExtractionCallFailure(
            f'Detail page too large for one extraction packet '
            f'(~{estimated_tokens:,} est. tokens, limit {MAX_REQUEST_TOKENS:,}): {url}')

    try:
        # Soft failure on purpose: returning None just skips enriching this one
        # event from its detail page, which is the pre-existing contract.
        response_text = await llm_providers.generate_structured(
            prompt, SingleEventExtraction, DETAIL_TIMEOUT,
            provider=llm_providers.provider_for('detail'),
            instructions=instructions,
        )
        data = json.loads(response_text)
        desc = (data.get('description') or '').strip().strip('"')
        # A placeholder or boilerplate description is not a description - but
        # it is NOT a reason to throw the rest of the record away. The model
        # routinely returns "No description available." together with a clean
        # location and dated occurrences (a sparse detail page, an at-capacity
        # stub with a venue line, a page whose prose is all chrome), and
        # returning None here discarded the venue and the dates with it: 4,702
        # of 22,765 attempted detail crawls in the 14 days to 2026-09-09 ended
        # this way, 72 of them still undated, and w591 NYC-DSA events kept
        # their listing's "New York City" pin although the detail page said
        # "NYC-DSA Office, 14 Jefferson St". Keep every field that is real and
        # omit the description, so the caller leaves the stored one alone.
        if not desc or 'No description available' in desc or _looks_like_boilerplate_fabrication(desc):
            desc = None
        result = {
            'hashtags': data.get('hashtags', []),
            'emoji': data.get('emoji', ''),
        }
        if desc:
            result['description'] = desc
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
        if not any(k in result for k in ('description', 'location', 'sublocation', 'occurrences')):
            return None  # nothing usable on the page - the pre-existing "skip enrichment" contract
        return result
    except (AgentExtractionPending, AgentExtractionInvalid):
        raise
    except Exception as e:
        print(f"    - AI error for {event_name}: {e}")
        return None


FULL_PASS_RULE = (
    'Extract complete events in a single pass using the full result schema. '
    'In addition to the fields listed below, include sublocation when stated, '
    'a source-grounded description, hashtags, and emoji for every event. '
    'Use "No description available." when the source has no descriptive details. '
    'Do not infer prose from the title. Keep metadata tied to its own listing/URL, '
    'even when two listings share a name. Preserve all dates and occurrences.')


COVERAGE_REVIEW_RULE = (
    "\n\nCOVERAGE REVIEW: The initial extraction triggered a count "
    "variance guard. Independently inspect every source section and "
    "explicit occurrence again. Return a complete extraction; do not "
    "invent events to match historical counts.\n")


CHUNK_RULES = """For each event provide: name, location (venue name), occurrences (array of start_date in YYYY-MM-DD, start_time, end_date, end_time), and url if available.

CRITICAL DATE RULES:
- Only return occurrences for SPECIFIC calendar dates EXPLICITLY shown on the page near the event (e.g. "May 7, 2026", "Sat Jun 14", "9/22").
- EXHIBITIONS: for an art exhibition / gallery show / installation with a stated date range ("March 1 – July 5", "On view through June 30"), return ONE occurrence with start_date = opening date and end_date = closing date. Never collapse the run to a single day, and never stamp today's date as the exhibition date. An exhibition whose OPENING date has already passed is STILL on view as long as its closing date is today or later — keep it, using the original (past) opening date as start_date; do NOT null it or skip it because it already opened.
- CLOSING DATE ONLY: if the page gives a closing date but NO opening date ("Through August 31, 2026", "Until Sept 4", "On view through June 30"), still return ONE occurrence — set end_date to that closing date and leave start_date null. An end-only occurrence is valid and expected here. Do NOT set occurrences=null just because the opening date is missing: the run is still on view, and nulling it drops the event entirely.
- RECEPTION vs RUN: a timed opening/closing reception, opening night, or preview is a SEPARATE single-day event, NOT an occurrence of the exhibition. If a page lists both a dated+timed reception and a broader exhibition run, emit TWO events — the reception (one single-day occurrence: its date + time) and the exhibition (one start→end run occurrence) — never the full run as a second occurrence of the reception, and never the reception's time on the run.
- A STATED DATE ALWAYS WINS OVER A RECURRENCE RULE. If the listing shows a specific calendar date for the event (e.g. "**When**: Sun, Aug 9 at 8:00pm"), emit that date as an occurrence — even when the event's name or description ALSO states a cadence ("Monthly", "Second Mondays", "second Sunday of every month", "every Tuesday", "weekly"). The date printed on the page is ground truth; the cadence is only extra context, and dropping the date deletes the event entirely. Emit ONLY the date(s) actually shown — never extrapolate the cadence into further dates the page does not list.
- If an event is described as "monthly", "weekly", "ongoing", "permanent", or "recurring" AND no specific calendar date appears anywhere in its listing, set occurrences=null. Same for a listing with no date at all. Do NOT invent a next-occurrence date.
- A LIST of specific calendar dates is NOT "recurring" — when the page enumerates actual dates (e.g. "June 18, June 19, June 20, ...", a film's showtimes across many days, or "Jan 11, 18, 25"), emit EACH listed date as its own occurrence. The null-occurrences rule above applies ONLY when a cadence is described in words ("weekly", "every Thursday") WITHOUT the dates being listed, or when no dates appear at all. A missing start_time NEVER justifies dropping a date that IS shown — set start_time to null and keep the date.
- NEVER collapse an enumerated list of dates into one start_date/end_date range. end_date is ONLY for something that genuinely runs every day in between (an exhibition run, a multi-day festival). A film playing on 12 listed dates is TWELVE occurrences with end_date null — NOT one occurrence spanning first-to-last. Collapsing is wrong even when the dates look contiguous, and it silently invents dates whenever the list has gaps (a film showing Aug 10-13 and Aug 17-20 must never become Aug 10 -> Aug 20).
- ONE LISTING PER URL: two listings with DIFFERENT event URLs are DIFFERENT events — never fuse them into one, no matter how similar their titles are. Titles that differ only by a qualifier or suffix ("Early Access", "Fan Event", "Special Preview", "(Sensory)", "(Open Cap/Eng Sub)", "3D", "25th Anniversary", a screening-format or accessibility tag) are separate ticketed listings: emit EACH as its own event, using that listing's OWN url and ONLY the dates shown under that listing. Never move a date from one listing onto another, and never pair one listing's title with another listing's url. Only listings that share the SAME url may be combined into a single event.
- Do NOT default to today's date when no date is listed.
- Do NOT extract dates from URLs or Google Calendar/iCal links — those often reference past instances. Only use dates visible in the page text adjacent to the event.
- Past dates (before today) should also be set to null — those events have already happened. EXCEPTION — ANY event that is STILL IN PROGRESS: if a multi-day event has a stated END date of today or later, keep it even though it started in the past — use its original (past) start_date and its stated end_date, and do NOT null it. This is NOT limited to exhibitions: a conference, symposium, workshop series, festival, residency, class run or camp that opened before today but ends today or later is still happening and must be kept. Only null a multi-day event once its END date is also in the past.
- An empty/null occurrences field is much better than a fabricated date."""


def get_chunk_instructions(notes=""):
    """Static chunk rules + region rule + site notes: identical for every chunk of a site.

    Shared through the packet's `instructions` (read once per site), not repeated
    in every chunk prompt. Keep the wording here and the single-call rules in
    get_prompt in step when either changes.
    """
    # The metro-geography rule was only in get_prompt (single-call mode), so a
    # large listing that fell into chunked mode had no geographic restriction at
    # all and touring/national feeds leaked out-of-region dates (2026-09-17).
    region_rule = _prompt_rule('region_rule')
    region_section = f"\n- {region_rule}" if region_rule else ""
    notes = (notes or "").strip()
    note_section = f"\n\nIMPORTANT: {notes}" if notes else ""
    return (_prompt_rule('CHUNK_RULES') + '\n\n'
            + _prompt_rule('SCHEDULE_EXCEPTIONS_RULE') + '\n\n'
            + _prompt_rule('EVENT_STATUS_RULE') + region_section + note_section)


CHUNK_PROMPT_TEMPLATE = '''{intro}{rid_section}

Website content:

{chunk_text}'''


def get_chunk_prompt(chunk_text, current_date_string, notes=None, request_id=""):
    """Per-chunk prompt: date line, request id and the source. Rules live in
    get_chunk_instructions (shared packet instructions). `notes` is accepted for
    call-site compatibility and intentionally unused here."""
    rid_section = f"\n\nIMPORTANT: Set request_id to \"{request_id}\" in your response." if request_id else ""
    return _prompt_rule("CHUNK_PROMPT_TEMPLATE").format(
        intro=_prompt_rule("chunk_intro").format(date=current_date_string),
        rid_section=rid_section,
        chunk_text=chunk_text)


SINGLE_PROMPT_TEMPLATE = '''{intro}
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
  EXHIBITIONS: For an art exhibition, gallery show, or installation that runs over a date range (e.g. "March 1 – July 5", "On view through June 30"), create ONE occurrence spanning the run: start_date = opening date, end_date = closing date. Do NOT collapse the run to a single day, and do NOT stamp today's date as the exhibition date. An exhibition whose OPENING date has already passed is STILL on view as long as its closing date is today or later — keep it, using the original (past) opening date as start_date; do NOT null it or skip it because it already opened. If the page gives a CLOSING date but no opening date ("Through August 31, 2026", "Until Sept 4"), still return ONE occurrence: end_date = that closing date, start_date = null. An end-only occurrence is valid and expected — do NOT set occurrences=null just because the opening date is missing. Only if the page gives no opening AND no closing date at all (a permanent / date-less display), set occurrences=null instead of inventing a single date.
  RECEPTION vs RUN: A timed opening/closing reception, opening night, or preview is a DISTINCT single-day event — NOT an occurrence of the exhibition it celebrates. When a page describes both a dated, timed reception AND a broader exhibition run (e.g. "Opening reception June 4, 6–8pm" for a show "on view June 4 – July 10"), emit TWO separate events: (1) the reception, with ONE single-day occurrence (its date + time), and (2) the exhibition, with ONE run occurrence (start_date = opening, end_date = closing). Never attach the exhibition's full run as a second occurrence of the reception event, and never put the reception's time on the exhibition run.
- description: 1-3 sentence description based ONLY on what is stated in the source content. If the listing only has a name/date/time with no further details, use "No description available." Do NOT make up or infer descriptions.
- url: Specific event URL if available
- hashtags: 4-7 CamelCase tags (e.g., ["Comedy", "StandUp", "Free"]). Always include at least one category from: Music, Nightlife, Comedy, Art, Theater, Dance, Film, Literature, Community, Family, Wellness, Education, Outdoor, Sports, Games. Also include Free if the event is free, or Virtual if online. Then add granular descriptive tags. {tag_avoidance}
- emoji: A single emoji representing the event

{note_section}{rid_section}
Rules:
- {SCHEDULE_EXCEPTIONS_RULE}
- {EVENT_STATUS_RULE}
- Extract ALL events from the page - do not skip or summarize
- Do NOT extract things that are not attendable public events. Skip: venue/program closures and holiday-closure notices ("Museum Closed", "Park Closes at 5pm", "Office Closed for Juneteenth"); calls for submissions, applications, or grants ("Open Call for Artists", "Submission Deadline", "Micro Grants Round 3"); casting calls and talent-recruitment notices ("Casting Call", "Models Wanted", "Dancers Needed"); civic date markers ("Election Day", "Primary Day", "Election Day 2026") — an attendable election-night watch party IS an event; venue marketing (space/room rentals, "Private Events", "Available for Booking", dining service like "Signature Breakfast"); season passes and ticketing placeholders ("Summer Pass 2026", "Showtimes"); fundraising campaigns and donation-match drives ("Match Campaign", "Giving Day") — an attendable benefit concert or gala IS an event; submit-your-work contests with an entry deadline ("Library Card Art Contest") — a contest held live in front of an audience (trivia, dance, pie-eating) IS an event; info-booth or vendor-table marketing listings inside a festival program ("Our Info Booths"); childcare offered as an amenity during another activity ("Nursery Care" during worship services, babysitting while parents attend) — a children's program or childcare-related class that is itself the event ("Toddler Storytime", "Babysitting 101 Training", "Preschool Open House") IS an event; members-only programming restricted to a venue's or club's own members ("Members-Only Tour", "Lunch | MEMBERS ONLY", "Fabrik Member Exclusive") — an event anyone can attend by buying a ticket IS an event; a school's orientations for its own enrolled students and their families ("New Student Orientation", "Parent/Family Orientation") — a volunteer orientation open to anyone who wants to volunteer IS an event; and content placeholders or unrelated spam. These are not events — leave them out entirely.
- {region_rule}
- Ignore unrelated event sections ("Hot Events", "Similar events", etc.)
- ONE LISTING PER URL: two listings with DIFFERENT event URLs are DIFFERENT events — never fuse them into one, no matter how similar their titles are. Titles that differ only by a qualifier or suffix ("Early Access", "Fan Event", "Special Preview", "(Sensory)", "(Open Cap/Eng Sub)", "3D", "25th Anniversary", a screening-format or accessibility tag) are separate ticketed listings: emit EACH as its own event, using that listing's OWN url and ONLY the dates shown under that listing. Never move a date from one listing onto another, and never pair one listing's title with another listing's url. Only listings that share the SAME url may be combined into a single event.
- For recurring events, expand ALL individual dates into the occurrences array
- If no events are found, return an empty events list
- IMPORTANT: Do NOT fabricate or guess dates. If a listing has no date information on the page, set occurrences to null.

Website content:

{page_content}'''


REFERENCE_PROMPT_TEMPLATE = """
REFERENCE - Previously extracted events (for naming consistency only):
{existing_events_json}

NOTE: The above is ONLY for reference to maintain consistent naming. You MUST still extract ALL events from the page content below - do not limit your output to these events. Our deduplication system will handle any overlaps.

"""


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
        #
        # `description` is dropped for the same reason it is dropped from the
        # detail-crawl prompt: showing Gemini a previous description invites it
        # to COPY that description onto a new event instead of deriving one from
        # the page. That turns any bad description into a self-perpetuating loop
        # — observed on w1066 Refuge, where the venue's marketing blurb kept
        # reappearing verbatim on every new party even though the Eventbrite
        # collection page contains no prose at all. The block exists for naming
        # consistency; descriptions must always come from the page content.
        trimmed = []
        for ev in existing_events:
            trimmed_ev = {k: v for k, v in ev.items()
                          if k not in ('occurrences', 'description')}
            occs = ev.get('occurrences', [])
            trimmed_ev['occurrences'] = occs[:3]
            trimmed.append(trimmed_ev)
        existing_events_json = json.dumps(trimmed, indent=2)

        # Hard cap: if existing events JSON still exceeds 50K chars, drop it entirely
        if len(existing_events_json) > 50000:
            print(f"    - WARNING: Existing events JSON too large ({len(existing_events_json)} chars), omitting from prompt")
            existing_events_section = ""
        else:
            existing_events_section = _prompt_rule('REFERENCE_PROMPT_TEMPLATE').format(
                existing_events_json=existing_events_json)

    return _prompt_rule("SINGLE_PROMPT_TEMPLATE").format(
        intro=_prompt_rule("intro").format(date=current_date_string, name=name, url=url),
        existing_events_section=existing_events_section,
        tag_avoidance=_prompt_rule("tag_avoidance"),
        note_section=note_section,
        rid_section=rid_section,
        SCHEDULE_EXCEPTIONS_RULE=_prompt_rule("SCHEDULE_EXCEPTIONS_RULE"),
        EVENT_STATUS_RULE=_prompt_rule("EVENT_STATUS_RULE"),
        region_rule=_prompt_rule("region_rule"),
        page_content=page_content)


# =============================================================================
# Per-site extraction settings
# =============================================================================
#
# Four knobs shape how a site is extracted, and each has ONE home: a column on
# `websites`, with a source plugin's SiteProfile supplying a per-platform
# default underneath it and the module constant underneath that. They are
# resolved together, once per crawl result, by `resolve_extraction_settings` —
# there is no directive syntax hidden in `websites.notes` (there was, until
# 2026-09-04; a stale `[[extraction: …]]` line is now stripped with a warning so
# it can never reach a prompt).
#
# WHY `force_chunked` exists: mode selection is a heuristic (estimate_event_count
# > LARGE_PAGE_THRESHOLD, or content > MAX_CHUNK_CHARS * 2). A site whose real
# event count sits just under the threshold on content just under 2x the chunk
# size — w950 Nook: ~30 Eventbrite-API cards, estimate 32-34, 43 KB — is routed
# to a single call whose ~8K output-token budget cannot hold 30 full events, so
# the extraction collapses to a random fraction (28,254 -> 7,290 -> 8,383 chars
# over three crawls, 14 of ~30 events surviving). Nudging the heuristic's inputs
# (padding the estimate, lowering the threshold) would move that cliff for every
# site; naming the site that needs chunking does not.
#
# WHY `max_records_per_chunk` is opt-in rather than a global cap: a chunk's
# OUTPUT size scales with its record COUNT, not its char count, so a compact 8K
# chunk holding 50 dense showtime cards can overrun the response budget while a
# 30K chunk holding 10 records is fine. But measured A/B over the 10 densest
# real crawls (47-51 records in the biggest chunk) — same content, same prompt,
# only the cap changing — a global cap of 30 moved distinct extracted events
# 1465 -> 1466 (+0.1%) while chunk count went 48 -> 88 (+83%). Nine of the ten
# were bit-identical. Corpus-wide a cap of 30 would cost +47% Gemini calls per
# run. Only Film Forum w50 measurably benefits (63 -> 66 distinct, reproducible
# over 4 reps: AMERICAN PACHUCO, THE THIRD MAN, WHITE NIGHTS come back only when
# its 50-record/8.4K chunk is split), which is exactly the shape a per-site
# setting exists for. Name the site; don't move the cliff for everyone.
#
# Per-site rationales for the rows that carry a setting live in
# database/extraction_settings_rationale.md.

@dataclass
class ExtractionSettings:
    max_batches: int = DEFAULT_MAX_BATCHES
    max_content_chars: int = MAX_CONTENT_CHARS
    force_chunked: bool = False
    max_records_per_chunk: Optional[int] = None


def resolve_extraction_settings(website_row, profile_urls, max_batches_override=None):
    """Resolve the per-site knobs: `websites` column > plugin default > global.

    `website_row` is (website_id, max_batches, max_content_chars, force_chunked,
    max_records_per_chunk) as selected in prepare_extraction (shorter rows are
    padded, for older callers). `max_batches_override` is an explicit caller
    value that beats the column (kept for tests and ad-hoc runs).
    """
    row = tuple(website_row or ()) + (None,) * 5
    _wid, db_max_batches, db_max_chars, db_force, db_cap = row[:5]
    defaults = site_profiles.extraction_defaults(profile_urls)

    def _positive(value):
        try:
            value = int(value) if value is not None else None
        except (TypeError, ValueError):
            return None
        return value if value and value > 0 else None

    max_batches = _positive(max_batches_override) or _positive(db_max_batches) or DEFAULT_MAX_BATCHES
    max_chars = _positive(db_max_chars) or _positive(defaults['max_content_chars']) or MAX_CONTENT_CHARS
    force_chunked = bool(db_force) or bool(defaults['force_chunked'])
    cap = _positive(db_cap) or _positive(defaults['max_records_per_chunk'])
    return ExtractionSettings(max_batches, max_chars, force_chunked, cap)


# Tripwire for the retired notes directive: strip and warn, never prompt.
_LEGACY_DIRECTIVE_RE = re.compile(
    r'^[ \t]*\[\[[ \t]*extraction[ \t]*:[^\]\n]*\]\].*$', re.MULTILINE | re.IGNORECASE)


def _strip_legacy_directives(notes, website_name):
    if not notes or not _LEGACY_DIRECTIVE_RE.search(notes):
        return notes or ""
    print(f"    - WARNING: {website_name}: websites.notes carries a legacy "
          f"[[extraction: …]] directive line. Directives moved to the "
          f"websites.force_chunked / max_records_per_chunk columns on 2026-09-04; "
          f"the line is ignored (and kept out of the prompt) — move the setting.")
    cleaned = _LEGACY_DIRECTIVE_RE.sub('', notes)
    return re.sub(r'\n{3,}', '\n\n', cleaned).strip()


def _profile_candidate_urls(cursor, crawl_result_id, base_url):
    """URLs to test against the source-plugin registry, most specific first.

    The plugin that shaped this content was chosen from `website_urls.url` at
    crawl time, so those rows — not `websites.base_url` — are the authoritative
    signal for which profile's extraction_notes apply. base_url stays as a
    fallback for sites with no website_urls rows (e.g. Instagram sources).
    """
    urls = []
    try:
        cursor.execute(
            """SELECT wu.url FROM website_urls wu
               JOIN crawl_results cr ON cr.website_id = wu.website_id
               WHERE cr.id = %s""",
            (crawl_result_id,),
        )
        urls = [r[0] for r in cursor.fetchall() if r and r[0]]
    except Exception:
        # Never let prompt decoration break an extraction.
        urls = []
    if base_url:
        urls.append(base_url)
    return urls


async def prepare_extraction(cursor, crawl_result_id, website_name, notes="",
                              use_vision=False, base_url="", max_batches=None):
    """
    Prepare extraction request data without making API calls.

    Performs all validation, classification, and prompt building, returning
    a PreparedExtraction that queues local work and replays completed responses.

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
    profile_urls = _profile_candidate_urls(cursor, crawl_result_id, base_url)
    notes = _strip_legacy_directives(
        site_profiles.resolve_notes(profile_urls, notes), website_name)

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

    # Get website_id and the per-site extraction settings for this crawl result
    cursor.execute(
        """SELECT cr.website_id, w.max_batches, w.max_content_chars,
                  w.force_chunked, w.max_records_per_chunk
             FROM crawl_results cr
             LEFT JOIN websites w ON w.id = cr.website_id
            WHERE cr.id = %s""",
        (crawl_result_id,)
    )
    result = cursor.fetchone()
    website_id = result[0] if result else None
    prep.website_id = website_id
    settings = resolve_extraction_settings(result, profile_urls or [base_url], max_batches)
    prep.max_batches = settings.max_batches
    prep.max_records_per_chunk = settings.max_records_per_chunk

    current_date_string = agent_extraction.reference_date()

    # Extract URL from first line if present
    url, content_to_process = extract_url_from_content(page_content)
    url = url or ""
    prep.url = url

    # Identical long paragraphs are the same card rendered twice; drop the copies
    # before anything is sized or chunked (see dedupe_repeated_paragraphs).
    content_to_process, dup_removed = dedupe_repeated_paragraphs(content_to_process)
    prep.content = content_to_process
    if dup_removed:
        print(f"    - Removed {dup_removed} chars of repeated paragraphs before chunking")

    # Hard limit on content size to prevent runaway extraction. Structured API
    # sources raise it via their SiteProfile — truncating a payload we built
    # ourselves silently drops real events rather than trimming an archive.
    # Plain websites raise (or lower) it via websites.max_content_chars, which
    # wins over the plugin default; both are per-site decisions made after
    # checking what actually sits past the cut.
    max_chars = settings.max_content_chars
    if len(content_to_process) > max_chars:
        print(f"    - Content exceeds legacy cap ({len(content_to_process)} chars); "
              "retaining complete source for agent extraction")

    # Decide extraction approach and build prompts
    if use_vision:
        prep.extraction_type = 'vision'
        print(f"    - Preparing vision extraction for {website_name} ({len(content_to_process)} chars)...")

        # Download and encode images
        image_parts, image_count = await prepare_vision_content(content_to_process, base_url or url)
        if not image_parts:
            print("    - No valid images found for vision extraction")
            prep.error = "No usable images for vision extraction"
            return prep

        print(f"    - Prepared {image_count} images for vision extraction")
        prompt_text = get_vision_prompt(url, content_to_process, current_date_string, website_name, notes,
                                        request_id=f"cr-{crawl_result_id}")
        prep.vision_contents = [prompt_text] + image_parts

    else:
        estimated_events = estimate_event_count(content_to_process)
        forced_chunked = settings.force_chunked
        use_two_pass = (forced_chunked
                        or estimated_events > LARGE_PAGE_THRESHOLD
                        or len(content_to_process) > MAX_CHUNK_CHARS * 2)

        if use_two_pass:
            prep.extraction_type = 'chunked'
            prep.max_batches = settings.max_batches
            if forced_chunked:
                print(f"    - force_chunked set for {website_name} "
                      f"(~{estimated_events} events, {len(content_to_process)} chars), "
                      f"preparing chunked extraction...")
            else:
                print(f"    - Large page detected (~{estimated_events} events, {len(content_to_process)} chars), preparing chunked extraction...")

            # Split content into chunks and build prompts
            chunks, chunk_method = chunk_content(content_to_process, EVENTS_PER_CHUNK, MAX_CHUNK_CHARS)
            records_cap = settings.max_records_per_chunk
            if records_cap:
                capped = cap_records_per_chunk(chunks, records_cap)
                if len(capped) != len(chunks):
                    print(f"    - max_records_per_chunk={records_cap} "
                          f"subdivided {len(chunks)} chunks into {len(capped)}")
                chunks = capped

            # Output budget, applied last so it sees the final piece boundaries.
            # Inert on ordinary listings; only date-list pages are subdivided.
            dense = cap_occurrences_per_chunk(chunks)
            if len(dense) != len(chunks):
                worst = max(count_date_tokens(c) for c in chunks)
                print(f"    - Date-dense page ({worst} dates in one chunk, budget "
                      f"{OCCURRENCE_BUDGET_PER_CHUNK}); subdivided {len(chunks)} "
                      f"chunks into {len(dense)}")
            chunks = dense
            print(f"    - Split into {len(chunks)} chunks using {chunk_method}-based chunking")

            # Never queue a packet for a chunk that cannot hold an event.
            chunks, pruned = prune_chunks(chunks)
            prep.pruned_chunks = pruned
            if pruned:
                summary = ', '.join(f"#{i} {reason} {chars}ch" for i, reason, chars in pruned)
                print(f"    - Pruned {len(pruned)} chunk(s) before queuing: {summary}")
            if not chunks:
                prep.resolved_result = '{"events": []}'
                print("    - Every chunk was chrome-only or beyond the publish window; no packets queued")
                return prep

            prep.chunks = chunks           # raw text, for the shortfall guard
            prep.content = content_to_process  # Store for enrichment context
            prep.chunk_instructions = get_chunk_instructions(notes)
            # Chunk indexes stay positional in the request id; they no longer
            # match the pre-prune split when something was pruned.
            prep.chunk_prompts = [
                get_chunk_prompt(chunk, current_date_string, notes,
                                 request_id=f"cr-{crawl_result_id}-chunk-{i}")
                for i, chunk in enumerate(chunks)
            ]
        else:
            prep.extraction_type = 'single'
            single_model = llm_providers.model_label(llm_providers.single_call_provider())
            print(f"    - Preparing extraction using {single_model} ({len(content_to_process)} chars)...")

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


# Cache for the locations map used by `_location_resolver_for`. Building it is a
# handful of full-table reads, and a run can copy many fingerprint-matched
# crawl_results; the table does not change mid-run.
_LOCATIONS_MAP_CACHE = {}


def _location_resolver_for(cursor, website_id):
    """Build the `resolve_location` callback `db.copy_crawl_events` expects.

    A fingerprint copy reuses an extraction from up to `FINGERPRINT_MAX_REUSE_DAYS`
    ago, so its pins predate any venue/alias work done since. See the rationale
    and the measurement in `db.copy_crawl_events`.

    Imported lazily: `processor` imports `db` and `crawler`, and pulling it in at
    module scope would put `extractor` in the middle of that cycle.
    """
    import processor

    if 'map' not in _LOCATIONS_MAP_CACHE:
        _LOCATIONS_MAP_CACHE['map'] = processor.build_locations_map(cursor)
    locations_map = _LOCATIONS_MAP_CACHE['map']

    def resolve(location_name, sublocation, event_name):
        info = processor.get_location_id(
            (location_name or '').strip(),
            (sublocation or '').strip(),
            '',
            (event_name or '').strip(),
            locations_map,
            website_id=website_id,
        )
        return info.get('id') if info else None

    return resolve


def _apply_fingerprint_marker_and_status(cursor, connection, prep, copied):
    """Store the fingerprint-match skip marker and advance the crawl result to
    'processed' after its crawl_events were copied from a prior identical crawl.

    The caller runs db.copy_crawl_events first (so it can emit its own log line
    using the returned count) and passes that count here.
    """
    # The marker substring is shared with db.find_prior_crawl_with_same_content,
    # which uses it to refuse to chain a reuse onto another reuse.
    marker = (f'{{"events": [], {constants.FINGERPRINT_COPY_MARKER}'
              f'{prep.copy_from_crawl_result_id}"}}')
    db.update_crawl_result_extracted(cursor, connection, prep.crawl_result_id, marker)
    db.update_crawl_result_processed(cursor, connection, prep.crawl_result_id, copied)


async def execute_extraction_sync(cursor, connection, prep):
    """
    Execute extraction using durable local agent work packets.

    Takes a PreparedExtraction and consumes the appropriate local responses.

    Returns:
        True if successful, False otherwise
    """
    crawl_result_id = prep.crawl_result_id

    # Content fingerprint match: copy events from prior identical crawl, no API call.
    # Skip directly to 'processed' state — bypasses both Gemini extraction and the
    # processor's parse/insert step.
    if prep.copy_from_crawl_result_id is not None:
        copied = db.copy_crawl_events(
            cursor, connection, prep.copy_from_crawl_result_id, crawl_result_id,
            resolve_location=_location_resolver_for(cursor, prep.website_id),
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
                review = _prompt_rule('COVERAGE_REVIEW_RULE') + retry_reason
                review_prep = _prepare_coverage_review(prep, review)
                retry_text = await _generate_extraction_response(review_prep, cursor, connection)
            except ExtractionCallFailure as e:
                # The retry hit the API wall; the first attempt is still a real
                # answer, so keep it rather than failing the whole crawl result.
                print(f"    - Coverage review failed ({e}); keeping first completed extraction")
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


def _prepare_coverage_review(prep, review):
    """Retry a collapsed single-page extraction through the chunked path.

    Keep the original preparation immutable so a resumed agent run reconstructs
    identical first-pass and review packets. Small sources without separable
    chunks still get an independent review, with the original source intact.
    """
    if prep.extraction_type == 'single' and prep.content:
        chunks, _ = chunk_content(prep.content, EVENTS_PER_CHUNK, MAX_CHUNK_CHARS)
        chunks = cap_records_per_chunk(chunks, prep.max_records_per_chunk)
        chunks = cap_occurrences_per_chunk(chunks)
        date_string = agent_extraction.reference_date()
        prompts = [get_chunk_prompt(chunk, date_string,
                   request_id=f'cr-{prep.crawl_result_id}-review-chunk-{i}') + review
                   for i, chunk in enumerate(chunks)]
        return replace(prep, extraction_type='chunked', chunks=chunks,
                       chunk_prompts=prompts, chunk_instructions=get_chunk_instructions(prep.notes))
    return replace(prep, prompt=(prep.prompt or '') + review,
                   chunk_prompts=[prompt + review for prompt in prep.chunk_prompts])


async def _generate_extraction_response(prep, cursor, connection):
    """Request agent work for one extraction attempt and return validated JSON.

    Shared by the first attempt and the variance-guard retry in
    execute_extraction_sync. cursor/connection are only used by the chunked
    path's max_batches auto-bump.
    """
    if prep.extraction_type == 'vision':
        # Store prompt and images separately in the durable local packet.
        prompt_text, image_parts = prep.vision_contents[0], prep.vision_contents[1:]
        try:
            return await llm_providers.generate_structured(
                prompt_text, EventList, GEMINI_TIMEOUT * 2,
                provider=llm_providers.provider_for('vision'),
                images=image_parts,
                )
        # A failed vision call is the same lie as a failed chunk: the images were
        # never read, so an empty result says nothing about the post. Fail the
        # crawl result instead of storing a zero (see ExtractionCallFailure).
        except llm_providers.ProviderCallFailure as e:
            print(f"    - Vision extraction error: {e}")
            raise ExtractionCallFailure(f"vision extraction failed: {e}")

    if prep.extraction_type == 'chunked':
        return await _execute_chunked_sync(prep, cursor, connection)

    # single
    estimated_tokens = len(prep.prompt) // CHARS_PER_TOKEN
    if estimated_tokens > MAX_REQUEST_TOKENS:
        error_msg = f"Prompt too large (~{estimated_tokens:,} est. tokens, limit {MAX_REQUEST_TOKENS:,})"
        print(f"    ⚠️  ERROR: {error_msg}, skipping extraction")
        raise RuntimeError(error_msg)
    # All extraction paths consume durable local agent responses.
    try:
        return await llm_providers.generate_structured(
            prep.prompt, EventList, GEMINI_TIMEOUT,
            provider=llm_providers.single_call_provider(),
        )
    except llm_providers.ProviderCallFailure as e:
        print(f"    - Single-call extraction error: {e}")
        raise ExtractionCallFailure(str(e))


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


# Floor rule thresholds for _fingerprint_copy_is_suspect (see its docstring).
# A copy of <= FLOOR events is suspect when the site reached >= HEALTHY_LEVEL
# events in >= HEALTHY_STATES of its recent distinct page states OF COMPARABLE
# SIZE (within SIZE_TOLERANCE, same ±20% notion _variance_retry_reason uses).
FINGERPRINT_FLOOR_COUNT = 1
FINGERPRINT_HEALTHY_LEVEL = 4
FINGERPRINT_HEALTHY_STATES = 2
FINGERPRINT_SIZE_TOLERANCE = 0.2


def _floor_count_confirmed_by_reextraction(cursor, prior_id):
    """Has this exact page state already been really extracted more than once?

    Bounds the floor rule in _fingerprint_copy_is_suspect. Counts the crawl
    results for the same website + content_hash that carry a genuine extraction
    (the fingerprint copies, which just clone a prior result, are excluded via
    FINGERPRINT_COPY_MARKER — the same marker db.find_prior_crawl_with_same_content
    uses to refuse chaining a reuse onto a reuse).

    Returns True (accept the copy, stop re-extracting) only when >= 2 independent
    extractions of these bytes agree the count is at the floor. If any of them
    reached FINGERPRINT_HEALTHY_LEVEL, the low prior is provably a fluke on
    identical content, so the floor is NOT confirmed no matter how many runs agree.
    """
    cursor.execute("""
        SELECT COUNT(*), MAX(cr.event_count)
        FROM crawl_results cr
        JOIN crawl_results p ON p.id = %s
        WHERE cr.website_id = p.website_id
          AND cr.content_hash = p.content_hash
          AND cr.status = 'processed'
          AND cr.event_count IS NOT NULL
          AND COALESCE(cr.extracted_content, '') NOT LIKE %s
    """, (prior_id, f'%{constants.FINGERPRINT_COPY_MARKER}%'))
    row = cursor.fetchone()
    if not row or row[0] is None:
        return False
    real_extractions, best_count = row[0], (row[1] or 0)
    if best_count >= FINGERPRINT_HEALTHY_LEVEL:
        return False
    return real_extractions >= 2


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

    Two rules fire (either one refuses the cache hit), on a site with enough
    distinct-page history to judge (>= 3 distinct hashes):

    1. MEDIAN rule: the prior count is < half a median of >= 4. Tiny/noisy sites
       (median < 4) are exempt — their normal swing is indistinguishable from a
       freeze and re-extracting them every crawl is pure Gemini spend.

    2. FLOOR rule: the prior count is <= FINGERPRINT_FLOOR_COUNT (a 0/1-event
       copy) while the site reached FINGERPRINT_HEALTHY_LEVEL in at least
       FINGERPRINT_HEALTHY_STATES of those recent page states *of comparable
       size*. Rule 1 alone has a blind spot the median can't see past: when a
       site under-extracts repeatedly across *different* page states (w1776
       Bloomingdale School of Music: per-state counts 1,0,7,5,7,0,1,1 on a
       page that stayed 125-127 KB throughout), the dud states are themselves
       the majority, the median collapses to 1.0, and the median >= 4 exemption
       then permanently excuses the very site it should catch — a feedback loop.

    The size scoping is what keeps rule 2 honest, and it is not optional: a page
    that really went quiet usually SHRANK, and its old high-count states were
    much bigger pages. Comparing only same-size states asks the right question —
    "has this site ever produced 4+ events from a page this size?" — instead of
    "was it ever busy?". Measured over the 39 fingerprint skips of the 2026-08-20
    run, that single condition is the difference between 6 forced re-extractions
    and 1 (the real freeze); the other 5 sites' pages had collapsed from 40 KB to
    4 KB, or 122 KB to 1 KB, and their low counts were honest.

    Rule 2 is additionally bounded so it can't re-extract a genuinely-emptied
    page on every crawl: it asks how many times this exact content state was
    REALLY extracted (copies excluded). Two independent extractions that both
    came back at the floor are a confirmation, not a fluke, and the copy is
    accepted from then on — so a page that truly went quiet costs one extra
    extraction, once. Conversely, if some earlier real extraction of these same
    bytes did reach FINGERPRINT_HEALTHY_LEVEL, the low one is provably a fluke.

    Fails open (returns False) on any error so extraction is never broken.
    """
    try:
        cursor.execute(
            "SELECT website_id, event_count, LENGTH(crawled_content) "
            "FROM crawl_results WHERE id = %s",
            (prior_id,)
        )
        row = cursor.fetchone()
        if not row or row[0] is None or row[1] is None:
            return False
        website_id, prior_count, prior_size = row[0], row[1], row[2]

        # One representative (best) count per distinct content_hash, most-recent
        # pages first, with that state's page size (identical within a hash).
        # GROUP BY content_hash collapses the freeze's copies so a long-running
        # freeze still only contributes one low data point.
        cursor.execute("""
            SELECT MAX(event_count) AS cnt, MAX(LENGTH(crawled_content)) AS size
            FROM crawl_results
            WHERE website_id = %s AND status = 'processed'
              AND event_count IS NOT NULL AND content_hash IS NOT NULL
            GROUP BY content_hash
            ORDER BY MAX(id) DESC
            LIMIT 8
        """, (website_id,))
        states = cursor.fetchall()
        counts = [r[0] for r in states]
        if len(counts) < 3:
            return False

        median_count = statistics.median(counts)
        if median_count >= 4 and prior_count < median_count * 0.5:
            return True

        # Floor rule — the polluted-median case.
        if prior_count > FINGERPRINT_FLOOR_COUNT or not prior_size:
            return False
        healthy_states = sum(
            1 for cnt, size in states
            if cnt >= FINGERPRINT_HEALTHY_LEVEL and size
            and abs(size - prior_size) <= prior_size * FINGERPRINT_SIZE_TOLERANCE
        )
        if healthy_states < FINGERPRINT_HEALTHY_STATES:
            return False
        return not _floor_count_confirmed_by_reextraction(cursor, prior_id)
    except (AgentExtractionPending, AgentExtractionInvalid):
        raise
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
    except (AgentExtractionPending, AgentExtractionInvalid):
        raise
    except Exception as e:
        # The guard must never break extraction — fail open (no retry).
        print(f"    - Variance guard check failed ({e}); skipping retry")
        return None


def _distinct_names_in_order(events):
    """Event names, de-duplicated, first-seen order preserved.

    Matched EXACTLY, because that is the key `_combine_chunked_results` uses to
    look enrichment back up — normalising here would strand records whose name
    differs only in case from the one we enriched.
    """
    seen, out = set(), []
    for event in events:
        name = event.get('name')
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _heading_key(text):
    """Loose key for matching a returned event name back to its source heading."""
    text = re.sub(r'^[ \t]*(?:[\*\-]\s+|\d+\.\s+)?#{1,6}\s*', '', text or '')
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)   # markdown link -> label
    return re.sub(r'[^a-z0-9]+', '', text.lower())


def _record_date_counts(chunk):
    """[(heading_key, heading_text, date_token_count)] for each record in a chunk."""
    lines = (chunk or '').split('\n')
    starts = [i for i, line in enumerate(lines) if _is_heading_line(line)]
    bounds = starts + [len(lines)]
    out = []
    for i, s in enumerate(starts):
        heading = lines[s].strip()
        body = '\n'.join(lines[bounds[i]:bounds[i + 1]])
        out.append((_heading_key(heading), heading, count_date_tokens(body)))
    return out


def _report_dropped_dates(chunk, events, label):
    """Warn LOUDLY when a chunk's records list dates but came back date-less.

    This is the detector for the failure `cap_occurrences_per_chunk` prevents,
    kept because that cap cannot split a SINGLE record that enumerates too many
    dates, and because the degradation is stochastic rather than a hard cliff.
    Without it the failure is invisible: `occurrences: null` is a legal answer,
    the record still counts toward the site's event count, nothing raises, and
    the event simply never reaches the map. Warning rather than failing is
    deliberate — the rest of the chunk is good data, and failing the crawl would
    trade a date loss for an archival cascade.
    """
    counts = _record_date_counts(chunk)
    if not counts:
        return 0
    by_key = {k: (h, n) for k, h, n in counts if k}
    dropped = []
    for event in events:
        if event.get('occurrences'):
            continue
        key = _heading_key(event.get('name') or '')
        if not key:
            continue
        hit = by_key.get(key)
        if hit is None:
            hit = next((v for k, v in by_key.items()
                        if k and (k in key or key in k)), None)
        # 2+ dates: one stray date token in a record's prose is not evidence.
        if hit and hit[1] >= 2:
            dropped.append((event.get('name'), hit[1]))
    if not dropped:
        return 0
    lost = sum(n for _, n in dropped)
    examples = '; '.join(f"{name!r} ({n} dates)" for name, n in dropped[:3])
    print(f"      ⚠️  DATE DROP in {label}: {len(dropped)} record(s) returned "
          f"occurrences=null although their source text lists dates "
          f"(~{lost} dates lost) — {examples}"
          + (f"; +{len(dropped) - 3} more" if len(dropped) > 3 else ""))
    return len(dropped)


async def _execute_chunked_sync(prep, cursor=None, connection=None):
    """Extract full events in one pass; resume legacy two-pass packets unchanged.

    Each pass publishes every independent pending packet before pausing. Replay
    reads completed responses. Only legacy simple records need enrichment.
    """
    # Extract events from each chunk
    all_simple_events = []
    seen_names = set()
    attempted_chunks = 0
    failed_chunks = 0
    last_chunk_error = None
    date_dropping_records = 0
    pending = []
    for i, chunk_prompt in enumerate(prep.chunk_prompts):
        # Records per name are unbounded in principle (a daily-recurring event
        # can emit one per date), so keep an absolute ceiling as a runaway
        # guard. Sized far above anything observed (worst real case ~3.5
        # records per name) so it never binds in normal operation.
        if len(all_simple_events) >= CHUNK_RECORD_CEILING:
            raise ChunkedExtractionFailure(
                f"Record ceiling {CHUNK_RECORD_CEILING} reached; complete extraction required")
        print(f"    - Processing chunk {i + 1}/{len(prep.chunk_prompts)}...")
        attempted_chunks += 1
        try:
            # Match the exact old packet before changing prompt/schema. Pending
            # and accepted work from an interrupted run remains usable.
            legacy = agent_extraction.has_request(chunk_prompt, SimpleEventList)
            schema = SimpleEventList if legacy else EventList
            instructions = None if legacy else (
                _prompt_rule('FULL_PASS_RULE') + '\n\n' + (prep.chunk_instructions or get_chunk_instructions(prep.notes)))
            response_text = await llm_providers.generate_structured(
                chunk_prompt, schema, CHUNK_TIMEOUT,
                provider=llm_providers.provider_for('chunked'),
                instructions=instructions,
                )
            result = json.loads(response_text)
            events = result.get('events', [])
            if events:
                print(f"      Got {len(events)} events")
                all_simple_events.extend(events)
                seen_names.update(e['name'] for e in events if e.get('name'))
                if i < len(prep.chunks):
                    date_dropping_records += _report_dropped_dates(
                        prep.chunks[i], events, f"chunk {i + 1}/{len(prep.chunk_prompts)}")
            else:
                print(f"      No events extracted")
        except AgentExtractionPending as exc:
            pending.append(exc)
        except AgentExtractionInvalid:
            raise
        except Exception as e:
            failed_chunks += 1
            last_chunk_error = str(e) or type(e).__name__
            print(f"      Chunk error: {e}")

    if pending:
        raise pending[0]

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

    if failed_chunks:
        # A PARTIAL failure is the same evidence problem as a total one, and it
        # used to slip through here because `all_simple_events` was non-empty:
        # the crawl stored `status='processed'` with a healthy-looking
        # event_count carrying only the chunks that happened to answer, and
        # archival then treated everything in the failed chunks as delisted.
        #
        # On 2026-08-04 a rate-limit storm made this common and it silently
        # under-extracted 23 sites — NYC SAPO Block Parties 12 events against a
        # 150 median, NYC Trivia League 22 vs 152, New York Cares 78 vs 136 —
        # none of which appeared in any failure list, because a partial failure
        # logs nothing at all. They had to be found by comparing each site's
        # count against its own trailing median, weeks of coverage later.
        #
        # Failing closed costs one crawl cycle of freshness and nothing else:
        # the result is stored `failed` with `crawled_content` preserved, so it
        # stays out of `_ws_latest` (no wrongful archival) and
        # `main.py --ids <id>` re-extracts it without re-crawling.
        raise ChunkedExtractionFailure(
            f"{failed_chunks}/{attempted_chunks} chunk request(s) failed; discarding the "
            f"{len(all_simple_events)} event(s) from the surviving chunks rather than "
            f"storing a truncated extraction (last error: {last_chunk_error})")

    if date_dropping_records:
        print(f"    - ⚠️  {date_dropping_records} record(s) across this page came back "
              f"date-less despite listing dates; those events will be undated. If this "
              f"repeats, lower OCCURRENCE_BUDGET_PER_CHUNK or cap the date list this "
              f"site's js_code emits.")

    print(f"    - Total from chunks: {len(all_simple_events)} events")

    # One enrichment slot per distinct name — duplicates would resolve to the
    # same enrichment entry anyway, so sending them again is pure waste.
    legacy_events = [event for event in all_simple_events
                     if not all(key in event for key in ('description', 'hashtags', 'emoji'))]
    if not legacy_events:
        return json.dumps({'events': all_simple_events}, ensure_ascii=False)
    event_names = _distinct_names_in_order(legacy_events)
    if len(event_names) != len(all_simple_events):
        print(f"    - {len(all_simple_events)} records -> {len(event_names)} distinct events")

    # Agent work has no API-cost cap: preserve all distinct names and chunks.
    # Enrich events with descriptions/hashtags/emoji in batches
    num_batches = -(-len(event_names) // ENRICHMENT_BATCH_SIZE)
    all_enrichments = {}

    for i in range(0, len(event_names), ENRICHMENT_BATCH_SIZE):
        batch = event_names[i:i + ENRICHMENT_BATCH_SIZE]
        print(f"    - Enriching batch {i // ENRICHMENT_BATCH_SIZE + 1}/{num_batches} ({len(batch)} events)...")
        try:
            enrichments = await enrich_events_batch(batch, prep.website_name, content=prep.content)
            all_enrichments.update(enrichments)
        except AgentExtractionPending as exc:
            pending.append(exc)

    if pending:
        raise pending[0]
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

    `batches_needed` is derived from DISTINCT event names, so a bump now means
    the site genuinely grew rather than that a model changed how it groups dates
    into records (see _execute_chunked_sync).
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
    except (AgentExtractionPending, AgentExtractionInvalid):
        raise
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
        if all(key in event for key in ('description', 'hashtags', 'emoji')):
            full_events.append(event)
            continue
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
    Extract events from crawled content using validated local agent responses.

    This is the sync (non-batch) extraction path. Prepares the request data,
    then consumes local packets or pauses for the supervising agent.

    Returns:
        True if successful, False otherwise
    """
    prep = await prepare_extraction(cursor, crawl_result_id, website_name, notes,
                                     use_vision, base_url, max_batches)

    if prep.error:
        print(f"    - {prep.error}")
        db.update_crawl_result_failed(cursor, connection, crawl_result_id, prep.error)
        return False

    try:
        return await execute_extraction_sync(cursor, connection, prep)
    except (AgentExtractionPending, AgentExtractionInvalid):
        raise
    except Exception as e:
        error_msg = str(e) or type(e).__name__
        print(f"    - Extraction error: {error_msg}")
        db.update_crawl_result_failed(
            cursor, connection, crawl_result_id, f"Extraction failed: {error_msg}"
        )
        return False


def is_available():
    """Local agent extraction is available without API credentials."""
    return True


# Legacy entry points fail explicitly instead of creating remote batch jobs.
async def run_batch_extraction(*args, **kwargs):
    raise RuntimeError("Remote batch extraction has been removed. Run pipeline/main.py "
                       "with --work-dir, complete local agent packets, and --resume.")


async def submit_and_poll_batch(*args, **kwargs):
    return await run_batch_extraction(*args, **kwargs)
