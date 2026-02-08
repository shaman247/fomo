# JavaScript Modules

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
| **utils.js** | Utilities: HTML escaping, date formatting, debounce/throttle, SafeStorage |
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
| **mapManager.js** | Create and manage Leaflet markers with custom icons |
| **markerController.js** | Marker lifecycle, popup content, display limits (uses `filterProvider`, `eventProvider`) |
| **viewportManager.js** | Calculate visible center accounting for filter panel overlay |

### Tags (`tags/`)
| Module | Description |
|--------|-------------|
| **filterPanelUI.js** | Orchestrates filter panel UI, delegates to specialized modules |
| **searchController.js** | Handles search input UI, debouncing, special terms, mobile auto-expand |
| **tagStateManager.js** | Manage tag filter states (uses `colorProvider`, `relatedTagsProvider`) |
| **tagColorManager.js** | Assign colors to selected tags from theme palette |
| **selectedTagsDisplay.js** | Selected tags display with related tags toggle |
| **sectionRenderer.js** | Render collapsible search result sections |
| **relatedTagsManager.js** | Related tag relationships and weights |

### UI (`ui/`)
| Module | Description |
|--------|-------------|
| **uiManager.js** | Date picker, event listeners, delegates to PopupContentBuilder |
| **popupContentBuilder.js** | Creates popup content for location markers |
| **gestureHandler.js** | Swipe gestures for section reordering |
| **modalManager.js** | Welcome and settings modals |
| **toastNotifier.js** | Toast notifications |
| **themeManager.js** | Dark/light theme switching |
| **emojiManager.js** | Emoji font loading (Noto Color Emoji) |

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
