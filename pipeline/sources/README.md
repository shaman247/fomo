# Source plugins

Per-platform crawl/extract behavior lives here, one module per platform. The
registry in `../site_profiles.py` auto-discovers every `*.py` in this directory
(except `__init__.py`, `*.example.py`, and leading-underscore modules) and
collects each module's `PROFILE` / `PROFILES`.

A plugin is **only** needed when a source needs special handling — extra in-page
JS, a skip (out-of-band ingest), custom HTTP headers, or a non-browser fetch
path. Ordinary sites need no plugin; they crawl through the generic crawl4ai
path. With no plugins present, the registry is empty and everything crawls
generically.

## Writing a plugin

Create `<platform>.py` exporting a module-level `PROFILE` (or `PROFILES`):

```python
import re
from site_profiles import SiteProfile, CrawlMode

PROFILE = SiteProfile(
    name="my_platform",
    host_re=re.compile(r"^(www\.)?example\.com$", re.IGNORECASE),
    # ... behavior fields ...
)
```

`SiteProfile` fields (see `../site_profiles.py` for the full dataclass):

- `host_re` (required) — matched against the URL **hostname**.
- `path_substr` — the URL must also contain this substring (e.g. `/events/`).
- `crawl_mode` — `STANDARD` (default), `SKIP` (don't crawl), or `CUSTOM` (call `fetcher`).
- `skip_reason` — message logged when `SKIP`.
- `fetcher` — a `() -> (markdown, n_events)` callable, required when `CUSTOM`. Define it in this module.
- `inject_js` — extra in-page JS appended before scraping.
- `extraction_notes` — text prepended to the website's extraction notes.
- `image_fetch_headers` + `image_host_substrs` — extra HTTP headers when downloading images whose URL contains one of the substrings.
- `label` — log label (defaults to `name`).

## Examples

- `standard_site.example.py` — data-only behaviors (inject_js / notes / headers / skip).
- `custom_api.example.py` — a `CUSTOM`-mode plugin with its own Python fetch path (JSON API).

Copy an example to `<platform>.py` and edit. Real plugins are gitignored
(deployment-specific); only `__init__.py`, the README, and `*.example.py`
templates are committed.
