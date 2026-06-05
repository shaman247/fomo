---
paths:
  - "src/js/**"
  - "src/css/**"
  - "src/index.html"
  - "src/about.html"
---

# Frontend Architecture

## Stack

- MapLibre GL JS v4.7.1 with Protomaps vector tiles
- Vanilla JS with IIFE module pattern (no framework, no bundler)
- CSS with `@import` chain (no preprocessor)

## Module Load Order

Defined by `<script>` tags in `src/index.html`:
core (constants, utils, historyManager, urlParams) → data → tags → UI → map → script.js (App)

## JS Modules (`src/js/`)

- `core/` — utils.js, constants.js, historyManager.js, urlParams.js
- `data/` — dataManager.js, filterManager.js, searchManager.js
- `tags/` — tagColorManager.js, tagStateManager.js, selectedTagsDisplay.js, searchController.js, sectionRenderer.js, filterPanelUI.js
- `ui/` — bottomSheet.js, popupContentBuilder.js, uiManager.js, themeManager.js, gestureHandler.js, modalManager.js, emojiManager.js, feedbackManager.js, toastNotifier.js
- `map/` — mapManager.js, markerController.js, viewportManager.js
- `script.js` — App initialization and event wiring

## Data Files (`src/data/`)

- `events.day0.json` … `events.day3.json` — events occurring on each of the next 4 calendar days (an event with multi-day occurrences appears in every chunk it touches; frontend dedupes by backend `id`)
- `events.remainder.json` — events with at least one occurrence past day 3 (within the 90-day future window)
- `locations.day0.json` … `locations.day3.json` / `locations.remainder.json` — venues referenced by events in each chunk
- `manifest.json` — `{ days: ["YYYY-MM-DD", …] }`; the frontend picks the chunk matching today's NYC date for Phase 1, falls back to `remainder` if today isn't in the manifest
- `tag_hierarchy.json` — exported tag DAG for filter panel
- `tags.json` — tag metadata including geotags list
- `map-style-light.json` / `map-style-dark.json` — MapLibre styles

## CSS Structure (`src/css/`)

- `variables.css` — CSS custom properties (colors, sizes, breakpoints)
- `index.css` — entry point, imports all other files
- Component files: layout, map, filter-panel, tags, popups, bottom-sheet, modals, fonts
