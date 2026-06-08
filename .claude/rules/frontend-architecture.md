---
paths:
  - "src/js/**"
  - "src/css/**"
  - "src/index.html"
  - "src/about.html"
---

# Frontend Architecture

## Stack

- MapLibre GL JS v5.24.0 (self-hosted in `vendor/`) with Protomaps vector tiles
- Vanilla JS with IIFE module pattern (no framework, no bundler)
- CSS with `@import` chain (no preprocessor)

## City config (`window.__CITY__`)

City-specific frontend values are NOT hardcoded — `build.js` injects them from `config/<FOMO_CITY>.yaml` as a `window.__CITY__` global (prepended to the bundle) + `{{TOKEN}}` branding replacement in `index.html` (see `.claude/rules/build-system.md`). Readers:
- `script.js` `App.config`: `MAP_INITIAL_VIEW`/`MAP_INITIAL_ZOOM`/`MAP_USER_LOCATION_ZOOM` and `REGION_BOUNDS` come from `window.__CITY__.map`. `App.isWithinRegion()` gates geolocation (accepts any location when `REGION_BOUNDS` is null).
- `utils.js`: `getTodayInZone()` / `parseDateInZone()` / `getZoneOffset()` use `window.__CITY__.timezone` (generic `Intl` offset — any IANA zone, not just US DST).

## Module Load Order

Defined by `<script>` tags in `src/index.html`:
core (constants, utils, historyManager, urlParams) → data → tags → UI → map → script.js (App)

## JS Modules (`src/js/`)

- `core/` — utils.js, colorUtils.js (shared OKLCH/OKLab color math), constants.js, historyManager.js, urlParams.js
- `data/` — dataManager.js, filterManager.js, searchManager.js
- `tags/` — tagColorManager.js, tagStateManager.js, selectedTagsDisplay.js, searchController.js, sectionRenderer.js, filterPanelUI.js
- `ui/` — bottomSheet.js, listView.js, popupContentBuilder.js, uiManager.js, themeManager.js, gestureHandler.js, modalManager.js, emojiManager.js, feedbackManager.js, toastNotifier.js
- `map/` — mapManager.js, markerController.js, viewportManager.js
- `script.js` — App initialization and event wiring

## Data Files (`src/data/`)

- `events.day0.json` … `events.day3.json` — events occurring on each of the next 4 calendar days (an event with multi-day occurrences appears in every chunk it touches; frontend dedupes by backend `id`)
- `events.remainder.json` — events with at least one occurrence past day 3 (within the 90-day future window)
- `events.day0.desc.json` … `events.day3.desc.json` / `events.remainder.desc.json` — per-chunk `{id: description}` companion files (descriptions are split out so the main event chunks stay small; loaded lazily/separately by `script.js`)
- `locations.day0.json` … `locations.day3.json` / `locations.remainder.json` — venues referenced by events in each chunk
- `organizers.json` — `{id: {name, url, emoji, description}}` map of event organizers (aggregators/unknown sources dropped)
- `manifest.json` — `{ days: ["YYYY-MM-DD", …] }`; the frontend picks the chunk matching today's date in the configured timezone (`window.__CITY__.timezone`, via `Utils.getTodayInZone()`) for Phase 1, falls back to `remainder` if today isn't in the manifest
- `tag_hierarchy.json` — exported tag DAG for filter panel
- `tags.json` — tag metadata including geotags list
- `map-style-light.json` / `map-style-dark.json` — MapLibre styles

## CSS Structure (`src/css/`)

- `variables.css` — CSS custom properties (colors, sizes, breakpoints)
- `index.css` — entry point, imports all other files
- Component files: layout, map, filter-panel, tags, popups, bottom-sheet, modals, fonts
