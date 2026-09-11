# JavaScript Modules

## Canvas readback performance

Emoji rasterization and color extraction use small 2D canvases whose pixels are
read immediately. Keep `willReadFrequently: true` on these contexts: default GPU
readback stalled the first date-range expansion in desktop Chrome, while repeat
clicks hid the cost through emoji caches. Profile fresh-page interactions as well
as warm repeats, and measure Event Timing through the next paint, not just the
synchronous `FilterProfiler` spans. See `.claude/decisions.md` (2026-09-07 INP).

## Discovery ranking and explicit preferences

`DiscoveryRanking` owns the versioned on-device preference store and exact-match
scoring. Each matching event ID, place identity, event tag or saved whole phrase
contributes +1 or -1. Personal counts sort before the bounded 0–6 broad-appeal
prior (outing-format groups, free tags, extra listing hostnames). The prior is
an unvalidated popularity proxy, never measured attendance. Tag matches use
only event tags, avoiding venue-audience spillover. `SimilarityModel` adds a bounded
offline-trained affinity term and suggested interest chips; see
[the model documentation](../../pipeline/similarity.md). Exact preferences remain
stronger than inferred similarity. There is no inferred geographic or transit model.

`PreferenceUI` (shown as ⭐ Favorites) supports all four types, reversal/removal, and term editing. Finder
results must clear immediately on new input and prioritize exact names; otherwise
an old suggestion can be selected during the debounce. Stored place identity is
normalized name plus address because exports currently lack stable venue IDs.
Coordinate perturbation must not change it; venue renames/address edits remain
a migration limitation. A profile can hold 200 entries; it stays local to this
browser and city deployment.

`MapManager` promotes the best eligible event at each place, then selects 20
places on desktop or 10 on mobile. Other places use translucent, single-color
dots (frontend.map.dot_color hue) with no hover or click targets; zooming reveals
them as emoji. Only promoted places receive invisible hit targets.
Active/hovered places reserve slots within the same cap.
Dark themes use `DotDensityLayer`: a cached GPU coverage buffer and an OKLCH
palette raise overlap lightness from .74 to .985 at five overlapping cores,
with chroma fading toward white and opacity rising from 70% to 99%. Soft
radial halos expand when zoomed out (4–10 CSS-pixel radius), letting dense
areas merge into a heat map. Light themes keep native 55% dots.
The custom layer sits below symbols, excludes promoted places, and releases
its GPU resources on removal. It rebuilds after context loss or resize.
Run `node --test src/js/tests/dotDensityLayer.test.cjs` for palette checks.
The canvas overscans the viewport: use visible window coordinates and exclude
sheet/filter overlays when choosing candidates, not the backing canvas bounds.
Recompute after map movement; restore both filters and dot styles after a theme
swap. Preference revision belongs in popup/label cache signatures.

Popup location/event titles have inline ☆/★ buttons (inactive section-header gray / yellow) at the title's
inherited font size, toggling Interested on/off.
An existing negative preference becomes positive on star activation; unfavoriting
returns it to neutral. Not interested can only be set in the Favorites pane.
Stars sync with pane changes and expose keyboard-accessible pressed states.

`PreferenceUI` keeps the dialog dimensions fixed within the viewport; search
suggestions overlay the internally scrolling profile. Interested then Not
interested each contain Places, Tags, Events and Searches, using shared
`tag-button` chips with the shared emoji renderer. The pane reuses Settings
modal surface/header/close styles. Click a chip for move/remove (and saved-search editing),
or drag it between stance sections with mouse, pen or touch. Dragging preserves
the entry type; keyboard users have the same actions through the chip editor.

Run `npm run test:discovery` for the scoring, persistence and selection tests.
Browser verification notes: `.scratch/discovery-implementation/report.md`.

## Keeping interactions responsive

Paint control feedback before filtering and map updates. Queued updates must
read the latest selection, so rapid clicks coalesce without restoring stale
state. Event Timing measures that first feedback paint; it does not measure
when the entire map and list finish updating.

Render the first screen of event cards before yielding, cancel stale batches,
and preserve scroll on unchanged results. Use elapsed-time budgets for data,
search indexing and emoji warming: large fixed batches stall slower CPUs.
Keep the event append and coordinate/lookup rebuild atomic; build a replacement
search index separately so input never sees a partially built index.

The manifest optionally lists `remainderChunks`. These contain event and
corresponding description partitions targeting 512 KiB combined raw content;
an individual event is never split. All partitions share
`locations.remainder.json`. Load the complete requested date range first, then
load other days and the tail in the background. Keep legacy remainder files for
cached older bundles, and accept older complete offline caches that only contain
the legacy remainder. Full download time and payload size are separate from
perceived responsiveness.

Background data and artwork must not reshuffle the current view. Defer data-driven
map/list refreshes until the next search, filter change, or map movement. If a user
selects dates still loading, keep the previous view until all requested chunks
arrive, then publish once. Do not publish each partial batch of that request.

Map sprites reserve fixed-size transparent slots. Fill them with `updateImage`
and update accent colors with feature-state; never call GeoJSON `setData` when an
image finishes. Replacing unchanged marker data restarts symbol collision
placement and makes unrelated labels flicker. Clear resolved accent state when
generated feature IDs are reassigned or the theme changes.
Artwork may decode after the native placement fade has finished: animate its
sprite alpha on arrival. Cached icons can also skip native fades after bucket
reloads, so newly promoted cached markers need a feature-state opacity fade.
Keep existing markers and shared sprite pixels unchanged during that fade. Browser checks on
2026-09-11 reduced startup source replacements from seven to one, and a search
from four to one; background downloads produced no subsequent replacements.

## 📁 File Organization

```
js/
├── core/           # Core utilities and configuration
├── data/           # Data management, filtering, and search
├── map/            # Map, markers, and viewport
├── tags/           # Tag filtering and UI coordination
├── ui/             # UI components, theming, and gestures
└── script.js       # Main application entry point
```

## 📦 Module Overview

### Core (`core/`)
| Module | Description |
|--------|-------------|
| **constants.js** | Application-wide constants (eliminates magic numbers) |
| **utils.js** | Utilities: HTML escaping, date formatting, debounce, SafeStorage |
| **historyManager.js** | Browser history/URL state management |
| **urlParams.js** | URL parameter parsing and updates |

### Data (`data/`)
| Module | Description |
|--------|-------------|
| **dataManager.js** | Fetch and process event/location data, build indexes |
| **filterManager.js** | Filter events by date, tags, and viewport with proximity weighting |
| **searchManager.js** | Search locations/events/tags with proximity and temporal scoring |

### Map (`map/`)
| Module | Description |
|--------|-------------|
| **mapManager.js** | Create and manage MapLibre WebGL symbol-layer markers (GPU-accelerated, not DOM markers) |
| **markerController.js** | Marker lifecycle, popup content, display limits (uses `filterProvider`, `eventProvider`) |
| **viewportManager.js** | Calculate visible center accounting for filter panel overlay |

### Tags (`tags/`)
| Module | Description |
|--------|-------------|
| **filterPanelUI.js** | Orchestrates filter panel UI, delegates to specialized modules |
| **searchController.js** | Handles search input UI, debouncing, special terms, mobile auto-expand |
| **tagStateManager.js** | Manage tag filter states (uses `colorProvider`) |
| **tagColorManager.js** | Assign colors to selected tags from theme palette |
| **sectionRenderer.js** | Render collapsible search result sections |

### UI (`ui/`)
| Module | Description |
|--------|-------------|
| **uiManager.js** | Date picker, event listeners, delegates to PopupContentBuilder |
| **popupContentBuilder.js** | Creates popup content for location markers |
| **bottomSheet.js** | Mobile bottom sheet for popup content |
| **listView.js** | List view of events |
| **feedbackManager.js** | User feedback UI |
| **gestureHandler.js** | Swipe gestures for section reordering |
| **modalManager.js** | Welcome and settings modals |
| **toastNotifier.js** | Toast notifications |
| **themeManager.js** | Dark/light theme switching |
| **iconManager.js** | Unified Noto/editorial artwork rendering, lazy decoding, themes and accent colors |

### Main Application
| Module | Description |
|--------|-------------|
| **script.js** | Application initialization, state management, and module orchestration |

## 🔗 Provider Pattern

Modules use provider objects to reduce callback bloat and improve organization:

```javascript
// Example: MarkerController uses filterProvider and eventProvider
MarkerController.init({
  filterProvider: {
    getTagStates: () => ...,
    getSelectedDates: () => ...
  },
  eventProvider: {
    getForceDisplayEventId: () => ...,
    setForceDisplayEventId: (id) => ...
  }
});
```

**Provider objects used:**
- `filterProvider` - Filter state access (MarkerController)
- `eventProvider` - Event display state (MarkerController)
- `colorProvider` - Tag color operations (TagStateManager, FilterPanelUI)
