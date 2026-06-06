"""Example source plugin: data-only behaviors on the standard crawl path.

Copy to `<platform>.py` (gitignored) and edit. Demonstrates the SiteProfile
fields that don't need any custom code — extra in-page JS, a skip, and image
headers. For a custom (non-browser) fetch path, see resident_advisor.example.py.
"""
import re

from site_profiles import SiteProfile, CrawlMode

# In-page JS appended before scraping — e.g. to rewrite a listing page's DOM so
# each event card is paired with its own detail URL. Leave as None if not needed.
_EXAMPLE_JS = """
(function(){
  // document.querySelectorAll(...) ... rewrite the DOM here ...
})();
""".strip()

# A single SiteProfile (use `PROFILES = [...]` to register several from one module).
PROFILE = SiteProfile(
    name="example",
    label="Example Site",
    # Matched against the URL hostname (lowercased).
    host_re=re.compile(r"^(www\.)?example\.com$", re.IGNORECASE),
    # Optional: only apply when the URL also contains this substring.
    path_substr="/events/",
    # STANDARD (browser crawl, the default), SKIP (ingested out-of-band), or CUSTOM (fetcher).
    crawl_mode=CrawlMode.STANDARD,
    # Appended to the website/per-URL js_code before scraping.
    inject_js=_EXAMPLE_JS,
    # Prepended to the website's extraction notes (guidance for the AI extractor).
    extraction_notes=None,
    # Extra HTTP headers when downloading images whose URL contains one of image_host_substrs.
    image_fetch_headers={},
    image_host_substrs=(),
)

# Example of a SKIP profile (a source you ingest through a separate path):
# PROFILE = SiteProfile(
#     name="example_skip",
#     host_re=re.compile(r"^(www\.)?example-skip\.com$", re.IGNORECASE),
#     crawl_mode=CrawlMode.SKIP,
#     skip_reason="ingested via a separate importer",
# )
