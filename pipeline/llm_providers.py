"""Provider-agnostic structured JSON generation for the extraction path.

Exists so the single-call extraction path can run on a different model from the
rest of the pipeline. Everything else — chunked extraction, vision, enrichment,
single-event detail crawls, and the whole Batch API path — still calls
`genai_client` directly in `extractor.py` and is unaffected by this module.

Measured 2026-08-03 against real crawl results, per path:

  single      TIE      -> safe to switch (8 of 10 sites gave identical
                          (name, date) sets; 59% cheaper)
  enrichment  TIE      -> safe to switch (same enriched counts, same
                          no-description rate, same emoji coverage)
  detail      TIE      -> safe to switch (identical descriptions, tags, emoji,
                          location and occurrence decisions on the sample)
  chunked     TIE      -> safe to switch, but only after the name-based budget
                          fix in extractor._execute_chunked_sync (see below)
  vision      REGRESS  -> pinned to Gemini (see GEMINI_PINNED)

Configure with EXTRACTION_PROVIDER ('gemini' | 'openai') for the switchable
paths, or EXTRACTION_PROVIDER_<PATH> to override one path — including the
pinned ones, which the blanket switch deliberately does not reach. Default is
Gemini everywhere so a checkout without an OpenAI key keeps working.

The Batch API path (`--batch`) is Gemini-only and is NOT covered by this
module: it builds `InlinedRequest`s directly in extractor.py. A batch run and a
sync run can therefore extract the same page with different models. Batch is
not the default path.
"""
import asyncio
import os
import random
import re

from dotenv import load_dotenv

load_dotenv()

GEMINI = 'gemini'
OPENAI = 'openai'

# Reasoning effort for OpenAI reasoning models.
#
# 'low' is the floor, NOT 'none'. Measured across four single-call crawls,
# 'low' and 'medium' agree exactly (Frick 31/31, Open Source Gallery 10/10,
# Pubkey 1/1, Muhlenberg 19 events / 24 occurrences) while 'low' runs at roughly
# half medium's latency. 'none' looks equally good on three of those four and
# then collapses Muhlenberg Library from 19 events to 2 — a dense listing page
# that needs some reasoning to enumerate. That collapse is precisely the shape
# the variance guard exists to catch, so don't trade it for a few seconds.
OPENAI_REASONING_EFFORT = os.environ.get("OPENAI_REASONING_EFFORT", "low")

try:
    from openai import AsyncOpenAI
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    # Strip quotes — .env values are commonly written OPENAI_MODEL="gpt-5.6-luna"
    # and python-dotenv preserves them for some quoting styles.
    OPENAI_MODEL = (os.environ.get("OPENAI_MODEL") or "").strip('"').strip("'")
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except ImportError:
    AsyncOpenAI = None
    openai_client = None
    OPENAI_API_KEY = None
    OPENAI_MODEL = ""


class ProviderCallFailure(RuntimeError):
    """The provider call did not yield a usable answer.

    Callers must translate this into extractor.ExtractionCallFailure so the
    crawl result is stored as 'failed' (content preserved) rather than as a
    `{"events": []}` zero that downstream archival would believe.
    """


# Every AI path that can be pointed at a provider. Each is independently
# overridable because they do not carry the same risk: the single-call path
# measured as a tie between the two models, the chunked path did not.
PATHS = ('single', 'chunked', 'vision', 'enrichment', 'detail')

# Distinguishes "caller didn't ask about Gemini" from "Gemini client is None".
_UNSET = object()


# Paths a measurement says the blanket EXTRACTION_PROVIDER switch must NOT
# reach. Each still has a per-path escape hatch (EXTRACTION_PROVIDER_VISION=...)
# so this is a safe default, not a lock. Re-measure before removing an entry.
GEMINI_PINNED = {
    'vision': (
        "Luna misreads stylized flyer typography. On Lucky 13 Saloon (crawl "
        "109123) it returned 'Fungicide' for a FUNGBLADE flyer, took the "
        "promoter as the event name for a Circus of Power bill, and invented a "
        "band ('Gryslling') on a Crashing Wayward flyer — three of three "
        "flyers checked against the images. Gemini read all three correctly. "
        "Vision carries the Instagram-first venues, where the event name only "
        "exists on the flyer."
    ),
}
# 'chunked' was pinned here until 2026-08-03: Luna's one-record-per-date output
# inflated the record count into the max_batches cap and whole chunks were
# skipped (Prospect Park: 5 of 7 chunks, 34 names vs Gemini's 57). Fixed at the
# source instead — `_execute_chunked_sync` now denominates the budget in
# distinct names, which is what enrichment actually charges for. Re-measured on
# the same page afterwards: 57 names / 185 name-date pairs from BOTH providers.


def provider_for(path):
    """Provider for one AI path: EXTRACTION_PROVIDER_<PATH>, else
    EXTRACTION_PROVIDER (unless the path is pinned), else Gemini.

    An unrecognised value falls back to Gemini rather than disabling
    extraction — a typo in .env must not silently stop the pipeline.
    """
    override = os.environ.get(f"EXTRACTION_PROVIDER_{path.upper()}")
    if override:
        choice = override.strip().lower()
    elif path in GEMINI_PINNED:
        return GEMINI
    else:
        choice = (os.environ.get("EXTRACTION_PROVIDER") or GEMINI).strip().lower()
    return choice if choice in (GEMINI, OPENAI) else GEMINI


def single_call_provider():
    """Back-compat alias for the single-call path."""
    return provider_for('single')


def provider_summary():
    """[(path, provider, model)] for every path, for run banners."""
    return [(p, provider_for(p), model_label(provider_for(p))) for p in PATHS]


def providers_in_use():
    """The distinct set of providers any path is currently pointed at."""
    return {provider_for(p) for p in PATHS}


def unconfigured_paths(gemini_client=_UNSET):
    """[(path, provider)] for paths whose provider can't be called.

    Lets a fully-migrated deployment drop its Gemini key: Gemini is only
    required if some path is still pointed at it.
    """
    return [(p, provider_for(p)) for p in PATHS
            if not is_configured(provider_for(p), gemini_client)]


def is_configured(provider, gemini_client=_UNSET):
    """Whether `provider` can actually be called.

    Pass `gemini_client` to have Gemini readiness checked here; omit it when the
    caller already owns that check (extractor.is_available()).
    """
    if provider == OPENAI:
        return bool(openai_client and OPENAI_MODEL)
    if gemini_client is _UNSET:
        return True
    return gemini_client is not None


def model_label(provider):
    return OPENAI_MODEL if provider == OPENAI else os.environ.get("GEMINI_MODEL", "gemini")


# --- transient-failure retry -------------------------------------------------
# The 2026-08-04 pipeline run took **372 HTTP 429s** against a 200,000
# tokens-per-minute org cap and threw the work away every time, because a rate
# limit was raised as a permanent ProviderCallFailure. The API states exactly how
# long to wait ("Please try again in 1.854s") and we were discarding that hint.
# Retrying transient failures is not optional here: a lost extraction is stored
# as a FAILED crawl, which costs the site a full crawl cycle of freshness.
PROVIDER_MAX_ATTEMPTS = int(os.environ.get("PROVIDER_MAX_ATTEMPTS") or 4)
PROVIDER_BACKOFF_CAP_S = float(os.environ.get("PROVIDER_BACKOFF_CAP_S") or 20)

_RETRY_HINT_RE = re.compile(r"try again in\s*([0-9.]+)\s*(ms|s)\b", re.I)
_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}
_RETRYABLE_MARKERS = ("rate_limit", "rate limit", "429", "500", "502", "503",
                      "504", "overloaded", "temporarily unavailable",
                      "service unavailable", "connection reset",
                      "connection error", "server had an error")

# Indirection so tests can run the retry logic without real sleeping.
_sleep = asyncio.sleep


def _is_retryable(exc):
    """True for rate limits and transient server/connection errors."""
    status = (getattr(exc, "status_code", None)
              or getattr(getattr(exc, "response", None), "status_code", None))
    if status in _RETRYABLE_STATUS:
        return True
    text = str(exc).lower()
    return any(m in text for m in _RETRYABLE_MARKERS)


def _retry_delay(exc, attempt):
    """Seconds to wait: the server's own hint if it gave one, else backoff."""
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        after = headers.get("retry-after") or headers.get("Retry-After")
    except AttributeError:
        after = None
    if after:
        try:
            return min(float(after), PROVIDER_BACKOFF_CAP_S)
        except (TypeError, ValueError):
            pass
    hint = _RETRY_HINT_RE.search(str(exc))
    if hint:
        secs = float(hint.group(1))
        if hint.group(2).lower() == "ms":
            secs /= 1000.0
        # pad the hint slightly: the window is shared with our own concurrency
        return min(secs + 0.25, PROVIDER_BACKOFF_CAP_S)
    # jitter so concurrent workers don't all wake into the same TPM window
    return min((2 ** attempt) + random.uniform(0, 0.5), PROVIDER_BACKOFF_CAP_S)


async def _call_with_retry(make_call, timeout, label):
    """Await `make_call()` with a per-attempt timeout, retrying transients.

    The timeout applies to EACH attempt, not to the whole chain, so a retry
    always gets a full budget rather than inheriting a nearly-spent one.
    A timeout is not retried — it usually means the payload is too big for the
    budget, and retrying would just burn the same wall clock again.
    """
    last = None
    for attempt in range(max(1, PROVIDER_MAX_ATTEMPTS)):
        try:
            return await asyncio.wait_for(make_call(), timeout=timeout)
        except asyncio.TimeoutError:
            raise ProviderCallFailure(f"{label} call timed out after {timeout}s")
        except Exception as e:  # noqa: BLE001 - re-raised as ProviderCallFailure
            last = e
            if attempt + 1 >= max(1, PROVIDER_MAX_ATTEMPTS) or not _is_retryable(e):
                break
            await _sleep(_retry_delay(e, attempt))
    raise ProviderCallFailure(f"{label} call failed: {last or type(last).__name__}")


async def generate_structured(prompt, schema, timeout, provider, images=None,
                              gemini_client=None, gemini_model=None):
    """Return raw JSON text for `prompt` conforming to `schema` (a Pydantic model).

    `images`, when given, is a list of Gemini-shaped inline-data parts —
    `{'inline_data': {'mime_type': ..., 'data': <base64>}}`. That stays the
    canonical internal form because `extractor.prepare_extraction` stores it on
    `PreparedExtraction.vision_contents` and the Batch API path consumes it
    directly; this module translates it per provider.

    Raises ProviderCallFailure on timeout, API error, refusal, or a truncated
    response — never returns a partial or empty answer that would read
    downstream as "this page has no events".
    """
    if provider == OPENAI:
        return await _generate_openai(prompt, schema, timeout, images)
    return await _generate_gemini(prompt, schema, timeout, gemini_client,
                                  gemini_model, images)


def _openai_image_parts(images):
    """Gemini inline-data parts -> OpenAI Responses input_image parts."""
    parts = []
    for part in images or []:
        inline = part.get('inline_data') if isinstance(part, dict) else None
        if not inline or not inline.get('data'):
            continue
        mime = inline.get('mime_type') or 'image/jpeg'
        parts.append({
            "type": "input_image",
            "image_url": f"data:{mime};base64,{inline['data']}",
        })
    return parts


async def _generate_gemini(prompt, schema, timeout, client, model, images=None):
    contents = [prompt] + list(images) if images else prompt
    response = await _call_with_retry(
        lambda: client.aio.models.generate_content(
            model=model,
            contents=contents,
            config={"response_mime_type": "application/json",
                    "response_schema": schema},
        ),
        timeout, "gemini")
    text = (response.text or "").strip()
    if not text:
        raise ProviderCallFailure("gemini returned an empty response body")
    return text


async def _generate_openai(prompt, schema, timeout, images=None):
    if not openai_client or not OPENAI_MODEL:
        raise ProviderCallFailure(
            "OpenAI provider selected but OPENAI_API_KEY/OPENAI_MODEL is not configured")
    image_parts = _openai_image_parts(images)
    if image_parts:
        payload = [{"role": "user",
                    "content": [{"type": "input_text", "text": prompt}] + image_parts}]
    else:
        payload = prompt
    kwargs = {"model": OPENAI_MODEL, "input": payload, "text_format": schema}
    if OPENAI_REASONING_EFFORT:
        kwargs["reasoning"] = {"effort": OPENAI_REASONING_EFFORT}
    response = await _call_with_retry(
        lambda: openai_client.responses.parse(**kwargs), timeout, "openai")

    # A truncated response still carries the events parsed so far. Accepting it
    # would silently under-extract — the exact shape of failure the variance
    # guard exists to catch — so treat it as a failed call instead.
    if getattr(response, "status", None) == "incomplete":
        reason = getattr(getattr(response, "incomplete_details", None), "reason", "unknown")
        raise ProviderCallFailure(f"openai response incomplete ({reason})")
    refusal = next(
        (c.refusal for item in (response.output or [])
         for c in (getattr(item, "content", None) or []) if getattr(c, "refusal", None)),
        None,
    )
    if refusal:
        raise ProviderCallFailure(f"openai refused the request: {refusal}")
    parsed = response.output_parsed
    if parsed is None:
        raise ProviderCallFailure("openai returned no parsable structured output")
    return parsed.model_dump_json()
