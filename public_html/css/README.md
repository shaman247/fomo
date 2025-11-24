# CSS files

## 📁 File Organization

```
css/
├── index.css           # Main entry point - imports all modules
├── variables.css       # CSS custom properties and theming
├── fonts.css          # Font declarations and typography
├── layout.css         # Base layout and structure
├── filter-panel.css   # Filter panel and search controls
├── tags.css           # Tag button styles
├── map.css            # Map, markers, and Leaflet controls
├── popups.css         # Leaflet popup styling
└── modals.css         # Modals and toast notifications
```

## 📦 Module Overview

### [index.css](./index.css)
The main CSS entry point that imports all other modules in the correct order. This is the only file referenced by the HTML.

**Import Order:**
1. Variables (theme colors and tokens)
2. Fonts (typography setup)
3. Layout (base structure)
4. Components (individual UI components)

### [variables.css](./variables.css)
Centralized theme configuration using CSS custom properties.

- Color palette (backgrounds, text, accents, borders)
- Shadow definitions
- Tag and popup color schemes
- Light theme overrides via `[data-theme="light"]`

### [fonts.css](./fonts.css)
Font loading and typography configuration.

- `@font-face` declarations (Noto Color Emoji)
- Font family setup (Inter/InterVariable)
- Variable font support detection
- Emoji font handling for debug mode

### [layout.css](./layout.css)
Core application structure and positioning.

- Body and base element styles
- Focus indicators for accessibility
- App container and map container layout
- Results container and tab navigation
- Loading states and animations
- (Mobile) app and map container positioning
- (Mobile) Toggle button for tags

### [filter-panel.css](./filter-panel.css)
Left sidebar filter panel and all its controls.

- Filter panel layout and positioning
- Logo and menu dropdown
- Search inputs (date picker, omni-search)
- Filter groups and tags wrapper
- Flatpickr calendar styling
- Search results sections

**Mobile Overrides:**
- Full-width panel with max-height
- Collapsible tags behavior
- Inline heading icons
- Touch-friendly controls

### [tags.css](./tags.css)
Tag button component in all its states.

- Base tag button styles
- State classes (unselected, selected, required, forbidden)
- Non-visible result styling
- Section control buttons
- Result type labels

### [map.css](./map.css)
Leaflet map, markers, and map controls.

- Map container with pre-loading optimization
- Custom marker icons and emoji positioning
- Leaflet attribution and tooltips
- Zoom controls
- Hardware acceleration hints
- (mobile) Hide zoom controls (use pinch gestures)

### [popups.css](./popups.css)
Leaflet popup styling for location markers.

- Popup wrapper and content layout
- Header with emoji and location info
- Details/summary elements for events
- Event list with scrolling
- External links and close button
- Event metadata styling

**Mobile Overrides:**
- Responsive popup sizing
- Viewport-aware max-width
- Adjusted padding

### [modals.css](./modals.css)
Modal dialogs, settings, and notifications.

- Modal overlay and container
- Modal header and close button
- Settings groups and options
- Welcome modal content
- Toast notification system

**Mobile Overrides:**
- Toast notification sizing
