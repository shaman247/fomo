# JavaScript files

## 📁 File Organization

```
js/
├── core/           # Core utilities and configuration
├── data/           # Data management and filtering
├── map/            # Map, markers, and viewport
├── tags/           # Tag filtering and search
├── ui/             # UI components and theming
└── script.js       # Main application entry point
```

## 📦 Module Overview

### Core (`core/`)
- **constants.js** - Application-wide constants (eliminates magic numbers)
- **utils.js** - Utilities: HTML escaping, date formatting, debounce/throttle, SafeStorage
- **urlParams.js** - URL parameter parsing and updates

### Data (`data/`)
- **dataManager.js** - Fetch and process event/location data, build indexes
- **filterManager.js** - Filter events by date, tags, and viewport with proximity weighting

### Map (`map/`)
- **mapManager.js** - Create and manage Leaflet markers with custom icons
- **markerController.js** - Marker lifecycle, popup content, display limits
- **viewportManager.js** - Calculate visible center accounting for filter panel overlay

### Tags/Search (`tags/`)
- **filterPanelUI.js** - Orchestrates filter panel UI (locations, events, tags)
- **tagStateManager.js** - Manage tag filter states (selected/required/forbidden)
- **tagColorManager.js** - Assign colors to selected tags from theme palette
- **selectedTagsDisplay.js** - Selected tags display with related tags toggle
- **searchManager.js** - Search locations/events/tags with proximity scoring
- **sectionRenderer.js** - Render collapsible search result sections
- **relatedTagsManager.js** - Related tag relationships and weights
- **gestureHandler.js** - Swipe gestures for section reordering

### UI (`ui/`)
- **uiManager.js** - Date picker, event listeners, popup content generation
- **modalManager.js** - Welcome and settings modals
- **toastNotifier.js** - Toast notifications
- **themeManager.js** - Dark/light theme switching
- **emojiManager.js** - Emoji font loading (Noto Color Emoji)

### Main Application
- **script.js** - Application initialization and orchestration
