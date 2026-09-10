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
- **Selector grouping**: `frontend.neighborhood_selector.groups` relocates listed children into their configured menu parent (including synthetic headings); it no longer duplicates a child under its former borough. Synthetic headings are navigation conventions only. The selectors show plain names and hide zero-match options by default using internal counts computed from the current date range, topic/organizer filters, and the other selector across the whole map. A non-empty area search reveals matching empty options and their ancestor paths; blank/whitespace-only search hides them. Counts use distinct events and update when additional date chunks load; no export-wide snapshot metadata is used for selector counts.

- **Venue selector**: `frontend.venue_selector.tags` lists venue-related tag names for compatibility; scoped curated identities and `frontend.filter_roots.venue` determine the venue tree. Both topic and venue menus retain scoped tag-state/URL semantics, but each menu labels and clears only its own filters. Activities such as Theater, Gardening, and Book Club remain topics unless independently reviewed as venue identities.
- **Venue browsing labels**: `frontend.venue_selector.labels` maps stable tag identities to public labels. Use familiar browsing language: Food & Drink, Arts & Culture, Outdoor. Labels apply to menu sorting/search, checkboxes, accessibility names, selected filters, and standard tag rendering/search. Stored filter keys remain unchanged. Do not remap the existing topic aliases Arts & Culture → Art or Outdoors → Outdoor into venue categories.
- **Venue taxonomy maintenance**: top-level `venue_taxonomy` contains reviewed `aliases`, exact `parents` sets, `remove_aliases`, and `location_tags` corrections. `scripts/audit_venue_taxonomy.py` previews/applies this policy with a reviewed hash, backup, shared database lock, cycle checks, and membership backfill. This is maintenance policy, not a build-time database mutation.

- **Other venue catch-all**: public label Other retains the stable `attraction` key. Use only for reviewed rare venue types without a suitable existing category. Observation Deck belongs under Outdoor (`Outdoor Venue`); Indoor Skydiving and Skatepark belong under Fitness & Recreation. Reparenting includes removing obsolete inherited location memberships.
- **Other membership review**: `venue_taxonomy.membership_review.other_review` records the stable catch-all `tag`, review date, and `retain` entries with location IDs and reasons. The membership audit flags unreviewed Other assignments and redundant Other alongside a specific unrelated venue type. Geography and children beneath Other do not count as redundancy. Check the exact tenant/floor before assigning a building's events to a named venue; organizer-specific aliases must stay scoped.
- **Venue-use review**: `venue_taxonomy.membership_review` holds `promote`, `retire`, exact `parents`, and reviewed `locations` (`location_id`, `expected_name`, `add`, `remove`). Sourced `descriptions` and `names` include expected old values and replacements. `scripts/audit_venue_memberships.py` previews/applies these decisions under the shared lock with backup and drift checks. Event Hall is dedicated rental use; Ballroom and Convention Center are children; Nightclub is independent. Venue, Event Space, Warehouse, and Nightlife Venue remain keywords, never automatic aliases for Event Hall or Other.
