"""
Generic registry of per-platform crawl/extract behaviors.

This module defines the SiteProfile data shape and the helper API the pipeline
consults to apply per-platform behavior generically — but it contains NO
references to any specific site. The actual profiles are auto-discovered from
the `sources/` plugin package (one module per platform, each exporting a
`PROFILE`/`PROFILES`). Real plugins are gitignored and deployment-specific; the
repo ships example templates. A fresh clone with no plugins yields an empty
registry, so every URL crawls via the generic crawl4ai path.

Why a code plugin and not a pure DB table: most behaviors are pure data (JS
snippets, note text, headers) but some sources need a *custom Python fetch path*
(e.g. ra.co's HTTP+GraphQL, no browser) that can't be serialized as data — so a
profile may reference a callable defined in its plugin module. Pipeline BEHAVIOR
is version-controlled in the plugin layer; the DB remains the source of truth
for EVENT/CRAWL data (see CLAUDE.md). Source *classification*
(websites.source_type, used in exporter.py) is a separate, already-DB-driven
concern and intentionally not modeled here.

To add a platform: drop a `<platform>.py` into pipeline/sources/ (copy an
`*.example.py` to start).
"""

import importlib
import os
import pkgutil
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Tuple
from urllib.parse import urlparse


class CrawlMode(Enum):
    STANDARD = "standard"   # normal crawl4ai path
    SKIP = "skip"           # don't crawl (ingested out-of-band, e.g. /picnob-scrape)
    CUSTOM = "custom"       # bypass crawl4ai, call fetcher() -> (markdown, n_events)


@dataclass(frozen=True)
class SiteProfile:
    name: str

    # --- URL matching ---
    host_re: "re.Pattern"               # matched against the URL hostname (lowercased)
    path_substr: Optional[str] = None   # if set, the URL must also contain this substring

    # --- crawl behavior (crawler.py) ---
    crawl_mode: CrawlMode = CrawlMode.STANDARD
    label: Optional[str] = None         # log label (defaults to name)
    skip_reason: Optional[str] = None   # message logged when SKIP
    fetcher: Optional[Callable[[], Tuple[str, int]]] = None  # (markdown, n_events) when CUSTOM
    inject_js: Optional[str] = None     # additive in-page JS appended to the url/website js_code

    # --- extraction behavior (extractor.py) ---
    extraction_notes: Optional[str] = None                   # prepended to the website notes
    image_fetch_headers: dict = field(default_factory=dict)  # extra HTTP headers downloading images
    image_host_substrs: tuple = ()      # full-URL substrings selecting image_fetch_headers

    def matches(self, url) -> bool:
        if not url:
            return False
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        if not self.host_re.match(host):
            return False
        if self.path_substr is not None and self.path_substr not in url:
            return False
        return True

    @property
    def display_label(self) -> str:
        return self.label or self.name


# =============================================================================
# Registry — auto-discovered from the sources/ plugin package
# =============================================================================

_SOURCES_DIRNAME = "sources"


def _discover_profiles(sources_dir=None):
    """Build the registry by importing every plugin in pipeline/sources/.

    Each `sources/<platform>.py` (NOT `*.example.py`, NOT a leading-underscore
    module) may expose a module-level `PROFILE` (a SiteProfile) and/or `PROFILES`
    (an iterable of SiteProfile). A plugin needing a custom fetcher defines that
    callable IN the module and passes it as `SiteProfile(fetcher=...)`.

    Absent/empty dir => [] => every URL crawls via the generic crawl4ai path.
    A plugin that fails to import or exports a non-SiteProfile is logged and
    skipped, never crashing the registry build.
    """
    if sources_dir is None:
        sources_dir = os.path.join(os.path.dirname(__file__), _SOURCES_DIRNAME)
    if not os.path.isdir(sources_dir):
        return []

    # Ensure pipeline/ is importable so `sources` resolves as a package.
    pkg_parent = os.path.dirname(os.path.abspath(sources_dir))
    if pkg_parent not in sys.path:
        sys.path.insert(0, pkg_parent)

    profiles = []
    for mod_info in pkgutil.iter_modules([sources_dir]):
        name = mod_info.name
        if name.startswith("_") or "example" in name:
            continue
        try:
            mod = importlib.import_module(f"{_SOURCES_DIRNAME}.{name}")
        except Exception as e:
            print(f"  ! site_profiles: failed to load source plugin '{name}': {e}")
            continue
        items = getattr(mod, "PROFILES", None)
        if items is None:
            one = getattr(mod, "PROFILE", None)
            items = [one] if one is not None else []
        for p in items:
            if isinstance(p, SiteProfile):
                profiles.append(p)
            else:
                print(f"  ! site_profiles: '{name}' exported a non-SiteProfile, skipped")
    return profiles


PROFILES = _discover_profiles()


def resolve_profile(url) -> Optional[SiteProfile]:
    """Return the first profile matching this URL, or None (=> default crawl)."""
    for p in PROFILES:
        if p.matches(url):
            return p
    return None


# --- crawl-level helpers (crawler.py) ---

def inject_js_for(url) -> str:
    """Extra in-page JS to append for this URL, or '' if none (meetup)."""
    p = resolve_profile(url)
    return p.inject_js if (p and p.inject_js) else ""


def is_skip_url(url) -> bool:
    """True if this URL is handled out-of-band and should not be crawled (instagram)."""
    p = resolve_profile(url)
    return bool(p and p.crawl_mode is CrawlMode.SKIP)


def all_skip(urls) -> Optional[str]:
    """If EVERY url resolves to a SKIP profile, return a skip_reason; else None."""
    if not urls:
        return None
    reason = None
    for u in urls:
        p = resolve_profile(u)
        if not (p and p.crawl_mode is CrawlMode.SKIP):
            return None
        reason = reason or p.skip_reason
    return reason


def custom_fetch_profile(urls) -> Optional[SiteProfile]:
    """If EVERY url resolves to the SAME custom fetcher, return its profile; else None (ra.co)."""
    if not urls:
        return None
    profile = None
    for u in urls:
        p = resolve_profile(u)
        if not (p and p.crawl_mode is CrawlMode.CUSTOM and p.fetcher):
            return None
        if profile is None:
            profile = p
        elif p.fetcher is not profile.fetcher:
            return None  # mixed custom fetchers -> not a clean short-circuit
    return profile


# --- extract-level helpers (extractor.py) ---

def resolve_notes(base_url, notes) -> str:
    """Prepend a profile's extraction_notes to the per-site notes (instagram)."""
    p = resolve_profile(base_url)
    prefix = p.extraction_notes if (p and p.extraction_notes) else None
    if prefix:
        return f"{prefix}\n\n{notes}".rstrip() if notes else prefix
    return notes or ""


def image_headers_for(image_url) -> dict:
    """Extra HTTP headers to merge when downloading this image URL (IG CDN)."""
    if not image_url:
        return {}
    for p in PROFILES:
        if p.image_fetch_headers and any(s in image_url for s in p.image_host_substrs):
            return dict(p.image_fetch_headers)
    return {}
