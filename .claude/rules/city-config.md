---
paths:
  - "config/*.yaml"
  - "pipeline/city_config.py"
  - "pipeline/site_profiles.py"
  - "pipeline/sources/**"
  - "build.js"
  - "src/index.html"
---

# City configuration

All city/region/branding specifics live in **one committed file**, `config/nyc.yaml` (the active file is `config/${FOMO_CITY}.yaml`, default `nyc`). To adapt to another city, copy it to `config/<city>.yaml`, replace the values, set `FOMO_CITY=<city>`, and add gitignored source plugins.

- **Backend** reads it via `pipeline/city_config.py` (`import city_config`): extraction-prompt geography/intro lines, generic location names, processor token lists (including the `processor.address` street-name overrides), the scoring calibration examples, and the User-Agent (`USER_AGENT` env / `constants.get_user_agent()`).
- **Frontend** `frontend:` block (map center/zoom/bounds, timezone, site_name/domain/emoji, the full welcome-modal HTML) is injected by `build.js` at build time: a `window.__CITY__` global for the JS bundle + `{{TOKEN}}` branding replacement in `src/index.html`.
- **Source plugins**: per-platform crawl behavior (meetup, instagram, ra.co, …) lives in gitignored `pipeline/sources/*.py`, auto-discovered by `pipeline/site_profiles.py` (committed examples + README there). Empty plugin dir ⇒ everything crawls generically. `ra_graphql.py` was removed — its logic is now the `resident_advisor` plugin.

- **Neighborhood selector**: `frontend.neighborhood_selector.groups` adds parent groups with explicitly ordered children, `order` sorts the top level, and `expanded` sets initially open groups. All unspecified siblings remain alphabetical. The build injects this configuration into `window.__CITY__.neighborhoodSelector`; no city-specific names or ordering belong in selector JavaScript.

- **Reviewed geographic hierarchy**: `geographic_hierarchy.groups` specifies DB parent assignments for listed children; `promote` explicitly permits new heading names. `scripts/audit_geographic_hierarchy.py --apply` validates and applies this configuration under the DB write lock. Unlisted relationships and non-geographic parents are retained.
- **Selector grouping**: `frontend.neighborhood_selector.groups` relocates listed children into their configured menu parent (including synthetic headings); it no longer duplicates a child under its former borough. Synthetic headings are navigation conventions only. The selectors hide zero-match options by default and show counts computed from the current date range, topic/organizer filters, and the other selector across the whole map. A non-empty area search reveals matching empty options and their ancestor paths with `(0)` counts; blank/whitespace-only search hides them. Counts use distinct events and update when additional date chunks load; no export-wide snapshot metadata is used for selector counts.
