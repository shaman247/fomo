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

- **Backend** reads it via `pipeline/city_config.py` (`import city_config`): extraction-prompt geography/intro lines, generic location names, processor token lists, the scoring calibration examples, and the User-Agent (`USER_AGENT` env / `constants.get_user_agent()`).
- **Frontend** `frontend:` block (map center/zoom/bounds, timezone, site_name/domain/emoji, the full welcome-modal HTML) is injected by `build.js` at build time: a `window.__CITY__` global for the JS bundle + `{{TOKEN}}` branding replacement in `src/index.html`.
- **Source plugins**: per-platform crawl behavior (meetup, instagram, ra.co, …) lives in gitignored `pipeline/sources/*.py`, auto-discovered by `pipeline/site_profiles.py` (committed examples + README there). Empty plugin dir ⇒ everything crawls generically. `ra_graphql.py` was removed — its logic is now the `resident_advisor` plugin.
