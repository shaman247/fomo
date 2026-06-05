/**
 * MapManager - WebGL Symbol Layer based marker rendering
 * Uses MapLibre native layers instead of DOM markers for GPU-accelerated performance
 * @module MapManager
 */
const MapManager = (() => {
    const state = {
        mapInstance: null,
        markerColorsRef: null,

        // Popup state
        currentPopup: null,
        currentPopupLocationKey: null,

        // Feature state tracking
        hoveredFeatureId: null,
        activeFeatureId: null,

        // Bidirectional lookups between locationKey and feature ID
        locationKeyToFeatureId: new Map(),
        featureIdToLocationKey: new Map(),

        // Emoji image tracking
        emojiImagesLoaded: new Set(),
        emojiScale: null, // computed once at first render

        // Cache for restoring after style.load (theme change)
        sourceDataCache: null,
        layersAdded: false,

        // Popup content callbacks by locationKey
        popupContentCallbacks: new Map()
    };

    // ========================================
    // INITIALIZATION
    // ========================================

    function init(mapInstance, _tagColors, markerColors) {
        state.mapInstance = mapInstance;
        state.markerColorsRef = markerColors || {};

        // Add the marker source/layers as soon as the style is parsed. This
        // fires well before the map's `load`/`idle` events (which also wait on
        // label glyph PBFs to download), so emoji markers can render without
        // blocking on the ~0.5 MB of font glyphs. In MapLibre v5 `style.load`
        // fires on both initial load and setStyle() (theme switch).
        mapInstance.on('style.load', _ensureLayers);

        // Ensure source/layers exist whenever the map becomes idle, too.
        // Safety net covering any path where style.load didn't (re-)create them.
        mapInstance.on('idle', _ensureLayers);

        // Try immediate setup if style is already loaded
        if (mapInstance.isStyleLoaded()) {
            _addSourceAndLayers();
        }
    }

    // ========================================
    // SOURCE AND LAYERS
    // ========================================

    /**
     * Called on map idle — re-creates source/layers if they were destroyed
     * by setStyle() (theme change). No-op if layers already exist.
     */
    function _ensureLayers() {
        const map = state.mapInstance;
        if (!map || !map.isStyleLoaded()) return;
        if (map.getSource('markers')) return; // Already set up

        state.layersAdded = false;
        state.emojiImagesLoaded.clear();
        _addSourceAndLayers();
        if (state.sourceDataCache) {
            _restoreAfterStyleChange();
        }
    }

    function _addSourceAndLayers() {
        const map = state.mapInstance;
        if (!map || state.layersAdded) return;

        // Add GeoJSON source with auto-generated numeric IDs for feature-state
        map.addSource('markers', {
            type: 'geojson',
            data: { type: 'FeatureCollection', features: [] },
            generateId: true
        });

        // Layer 1: Emoji icons + text labels.
        // Each location emits up to TWO features:
        //   1. Icon-only (lowest sortKey, placed first → populates collision grid)
        //   2. Expanded label — 2-line: location name + event label below
        // Labels are always 2-line. text-allow-overlap:false + text-optional:true
        // means a label that collides is simply dropped (the icon still shows);
        // there is no single-line fallback.
        map.addLayer({
            id: 'marker-symbols',
            type: 'symbol',
            source: 'markers',
            layout: {
                'icon-image': ['get', 'emojiImageId'],
                'icon-size': _getIconSize(),
                'icon-allow-overlap': true,
                'icon-ignore-placement': false,
                'icon-padding': 0,
                'icon-offset': [-8, 0],
                'text-field': _getTextFieldExpression(),
                'text-font': ['Inter Regular'],
                'text-size': _getLabelSize(),
                'text-anchor': 'left',
                'text-justify': 'left',
                'text-offset': [1.4, -0.15],
                'text-max-width': 50,
                'text-allow-overlap': false,
                'text-optional': true,
                'text-ignore-placement': false,
                'text-padding': 3,
                'text-letter-spacing': 0,
                'text-line-height': 1.15,
                'symbol-sort-key': ['get', 'sortKey']
            },
            paint: {
                'text-color': _getLabelColor(),
                'text-halo-color': _getHaloColor(),
                'text-halo-width': 2,
                'text-halo-blur': 0
            }
        });

        // Layer 2: Highlight circle (colored ring on hover/active, above all emojis)
        map.addLayer({
            id: 'marker-highlight',
            type: 'circle',
            source: 'markers',
            paint: {
                'circle-radius': _getMarkerRadius(),
                'circle-color': 'transparent',
                'circle-stroke-width': [
                    'case',
                    ['boolean', ['feature-state', 'active'], false], 4,
                    ['boolean', ['feature-state', 'hover'], false], 4,
                    0
                ],
                'circle-stroke-color': ['get', 'color']
            }
        });

        // Layer 3: Hover — emoji + label, always visible, shown only for hovered feature
        map.addLayer({
            id: 'marker-symbols-hover',
            type: 'symbol',
            source: 'markers',
            filter: ['==', ['get', 'locationKey'], ''], // hidden by default
            layout: {
                'icon-image': ['get', 'emojiImageId'],
                'icon-size': _getIconSize(),
                'icon-allow-overlap': true,
                'icon-ignore-placement': true,
                'icon-offset': [-8, 0],
                'text-field': _getTextFieldExpression(),
                'text-font': ['Inter Regular'],
                'text-size': _getLabelSize(),
                'text-anchor': 'left',
                'text-justify': 'left',
                'text-offset': [1.4, -0.15],
                'text-max-width': 50,
                'text-allow-overlap': true,
                'text-ignore-placement': true,
                'text-letter-spacing': 0,
                'text-line-height': 1.15,
                'symbol-sort-key': ['get', 'sortKey']
            },
            paint: {
                'text-color': _getHoverLabelColor(),
                'text-halo-color': _getHaloColor(),
                'text-halo-width': 2.5,
                'text-halo-blur': 0
            }
        });

        state.layersAdded = true;
    }

    function _getMarkerRadius() {
        return window.innerWidth <= 768 ? 20 : 24;
    }

    function _getIconSize() {
        return window.innerWidth <= 768 ? 0.55 : 0.7;
    }

    function _getLabelSize() {
        return window.innerWidth <= 768 ? 13 : 14.5;
    }

    function _getLabelColor() {
        const theme = document.documentElement.getAttribute('data-theme') || 'dark';
        return theme === 'dark' ? '#e5e5e5' : '#1a1a1a';
    }

    function _getHoverLabelColor() {
        const theme = document.documentElement.getAttribute('data-theme') || 'dark';
        return theme === 'dark' ? '#fff' : '#000';
    }

    function _getHaloColor() {
        const theme = document.documentElement.getAttribute('data-theme') || 'dark';
        return theme === 'dark' ? '#171717' : '#f0f0f0';
    }

    /**
     * Builds the text-field expression used by both the main and hover layers.
     * Renders the 2-line label (location + event) for expanded features; icon
     * features carry no text. The event line uses a desaturated version of the
     * marker color (pre-computed in feature properties) so the hue stays tied to
     * the highlight ring while brightness is consistent across labels.
     */
    function _getTextFieldExpression() {
        return ['case',
            ['==', ['get', 'labelType'], 'expanded'],
                ['format',
                    ['get', 'locationName'], {},
                    '\n', {},
                    ['get', 'eventLabel'], {
                        'text-font': ['literal', ['Inter Regular']],
                        'text-color': ['get', 'eventLabelColor'],
                        'font-scale': 0.88
                    },
                    ['get', 'eventLabelExtra'], {
                        'text-font': ['literal', ['Inter Regular']],
                        'font-scale': 0.88
                    }
                ],
            ''
        ];
    }

    /**
     * Converts a hex marker color into a CSS hsl() string with reduced
     * saturation and a theme-dependent fixed lightness, so all event labels
     * share a consistent brightness level regardless of the marker hue.
     */
    function _toEventLabelColor(hexColor, opts = {}) {
        const hex = (hexColor || '#888').replace(/^#/, '');
        const full = hex.length === 3 ? hex.split('').map(c => c + c).join('') : hex;
        const r = parseInt(full.slice(0, 2), 16) / 255;
        const g = parseInt(full.slice(2, 4), 16) / 255;
        const b = parseInt(full.slice(4, 6), 16) / 255;
        const max = Math.max(r, g, b), min = Math.min(r, g, b);
        const l0 = (max + min) / 2;
        let h = 0, s0 = 0;
        if (max !== min) {
            const d = max - min;
            s0 = l0 > 0.5 ? d / (2 - max - min) : d / (max + min);
            if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
            else if (max === g) h = (b - r) / d + 2;
            else h = (r - g) / d + 4;
            h *= 60;
        }
        const theme = document.documentElement.getAttribute('data-theme') || 'dark';
        const targetL = opts.lightness ?? (theme === 'dark' ? 68 : 44);
        const baseS = s0 > 0.05 ? 32 : 0;
        const targetS = opts.saturation ?? baseS;
        return `hsl(${Math.round(h)}, ${targetS}%, ${targetL}%)`;
    }

    /**
     * Builds the second-line event label parts.
     * Returns the first event's name (truncated with ellipsis) and a separate
     * " +N" suffix string when there are additional matching events at the
     * location. Split into two parts so the format expression can color them
     * independently — the name uses the marker's hue, the count is neutral.
     */
    function _buildEventLabel(events) {
        if (!events || events.length === 0) return { name: '', extra: '' };
        const first = events[0];
        const rawName = (first && (first.short_name || first.name)) || '';
        if (!rawName) return { name: '', extra: '' };

        // Only truncate when it actually saves space — slicing 23 chars down
        // to "22 chars + …" leaves the label the same length but less readable.
        const MAX_LEN = 22;
        const MIN_SAVINGS = 3;
        const name = rawName.length > MAX_LEN + MIN_SAVINGS
            ? rawName.slice(0, MAX_LEN).trimEnd() + '…'
            : rawName;

        const extras = events.length - 1;
        const extra = extras > 0 ? ` +${extras}` : '';
        return { name, extra };
    }

    // ========================================
    // EMOJI IMAGE RENDERING
    // ========================================

    /**
     * Measure the actual rendered size of a reference emoji and return a
     * scale factor that normalizes it to a target ratio (Apple-sized).
     * Called once per font configuration; result is cached in state.emojiScale.
     */
    function _measureEmojiScale(fontFamily) {
        const TARGET_RATIO = 1.0; // Apple ⬛ fills 1.0 of em-square; normalize others to match
        const testSize = 128;
        const canvas = document.createElement('canvas');
        const dim = testSize * 2;
        canvas.width = dim;
        canvas.height = dim;
        const ctx = canvas.getContext('2d');
        ctx.font = `${testSize}px ${fontFamily}`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('\u2B1B', dim / 2, dim / 2); // ⬛ — solid square, fills design space

        const imageData = ctx.getImageData(0, 0, dim, dim);
        const data = imageData.data;
        let minX = dim, maxX = 0, minY = dim, maxY = 0;
        let found = false;
        for (let y = 0; y < dim; y++) {
            for (let x = 0; x < dim; x++) {
                if (data[(y * dim + x) * 4 + 3] > 10) {
                    found = true;
                    if (x < minX) minX = x;
                    if (x > maxX) maxX = x;
                    if (y < minY) minY = y;
                    if (y > maxY) maxY = y;
                }
            }
        }
        if (!found) return 1;

        const measuredRatio = Math.max(maxX - minX + 1, maxY - minY + 1) / testSize;
        const scale = TARGET_RATIO / measuredRatio;
        console.log(
            `[MapManager] Emoji scale: font="${fontFamily}" measured=${measuredRatio.toFixed(3)} target=${TARGET_RATIO} scale=${scale.toFixed(3)}`
        );
        return scale;
    }

    function _addEmojiImage(emoji) {
        const map = state.mapInstance;
        const imageId = `emoji-${emoji}`;
        if (state.emojiImagesLoaded.has(imageId) || map.hasImage(imageId)) {
            state.emojiImagesLoaded.add(imageId);
            return;
        }

        const size = 64;
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const canvasSize = size * dpr;

        const canvas = document.createElement('canvas');
        canvas.width = canvasSize;
        canvas.height = canvasSize;
        const ctx = canvas.getContext('2d');

        // Use Noto font if active
        const isNoto = document.body.classList.contains('use-noto-emoji');
        const fontFamily = isNoto ? '"Noto Color Emoji"' : 'serif';

        // Compute scale factor once per font configuration
        if (state.emojiScale === null) {
            state.emojiScale = _measureEmojiScale(fontFamily);
        }

        ctx.font = `${canvasSize * 0.72 * state.emojiScale}px ${fontFamily}`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        // Draw emoji shifted right on canvas so that when icon-offset shifts
        // the image back left, the emoji stays centered but the collision box
        // is biased leftward — preventing labels from colliding with their
        // own location's icon in the dual-feature layout.
        const collisionShift = 8 * dpr;
        ctx.fillText(emoji, canvasSize / 2 + collisionShift, canvasSize / 2);

        const imageData = ctx.getImageData(0, 0, canvasSize, canvasSize);

        map.addImage(imageId, imageData, { pixelRatio: dpr });
        state.emojiImagesLoaded.add(imageId);
    }

    function loadEmojiImages(locationsByLatLng) {
        if (!state.mapInstance) return;
        const uniqueEmojis = new Set();
        for (const key in locationsByLatLng) {
            const loc = locationsByLatLng[key];
            if (loc && loc.emoji) uniqueEmojis.add(loc.emoji);
        }
        uniqueEmojis.forEach(emoji => _addEmojiImage(emoji));
    }

    /**
     * Async chunked version. Each canvas creation+draw is ~0.5-1ms; with 200+
     * unique emojis that adds up to ~100ms of main-thread time on a fresh
     * Phase 2 merge. This yields every CHUNK emojis so the user can interact.
     */
    async function loadEmojiImagesChunked(locationsByLatLng) {
        if (!state.mapInstance) return;
        const uniqueEmojis = new Set();
        for (const key in locationsByLatLng) {
            const loc = locationsByLatLng[key];
            if (loc && loc.emoji) uniqueEmojis.add(loc.emoji);
        }
        const list = [...uniqueEmojis];
        const CHUNK = 50;
        for (let i = 0; i < list.length; i += CHUNK) {
            const end = Math.min(i + CHUNK, list.length);
            for (let j = i; j < end; j++) _addEmojiImage(list[j]);
            if (end < list.length) {
                if (typeof scheduler !== 'undefined' && typeof scheduler.yield === 'function') {
                    await scheduler.yield();
                } else {
                    await new Promise(r => setTimeout(r, 0));
                }
            }
        }
    }

    function reloadEmojiImages(locationsByLatLng) {
        if (!state.mapInstance) return;
        // Reset scale so it's re-measured with the (possibly changed) font
        state.emojiScale = null;
        // Remove all existing emoji images and reload
        state.emojiImagesLoaded.forEach(imageId => {
            if (state.mapInstance.hasImage(imageId)) {
                state.mapInstance.removeImage(imageId);
            }
        });
        state.emojiImagesLoaded.clear();
        loadEmojiImages(locationsByLatLng);

        // Trigger a source data refresh to pick up new images
        if (state.sourceDataCache) {
            const source = state.mapInstance.getSource('markers');
            if (source) {
                source.setData(state.sourceDataCache);
            }
        }
    }

    // ========================================
    // MARKER DATA MANAGEMENT
    // ========================================

    function updateMarkerData(filteredLocations, locationsByLatLng, popupContentCallbacks) {
        const map = state.mapInstance;
        if (!map) return;

        // Store callbacks
        state.popupContentCallbacks = popupContentCallbacks;

        // Build GeoJSON features — up to two per location:
        //   1. Icon (lowest sortKey → placed first, populates collision grid)
        //   2. Expanded label — 2-line: location + event title
        // Labels are always 2-line; a label that collides is simply dropped.
        const iconFeatures = [];
        const expandedLabelFeatures = [];
        state.locationKeyToFeatureId.clear();
        state.featureIdToLocationKey.clear();

        const locationKeys = [];
        for (const locationKey in filteredLocations) {
            const events = filteredLocations[locationKey];
            if (events.length === 0) continue;

            const [lat, lng] = locationKey.split(',').map(Number);
            if (lat === 0 && lng === 0) continue;

            const locationInfo = locationsByLatLng[locationKey];
            if (!locationInfo) continue;

            // Ensure emoji image exists
            if (locationInfo.emoji) {
                _addEmojiImage(locationInfo.emoji);
            }

            const color = getMarkerColor(locationInfo);
            const shortName = locationInfo.short_name || locationInfo.name || '';
            const { name: eventLabel, extra: eventLabelExtra } = _buildEventLabel(events);

            // Icon feature — no text, placed first via low sortKey
            iconFeatures.push({
                type: 'Feature',
                geometry: { type: 'Point', coordinates: [lng, lat] },
                properties: {
                    locationKey,
                    labelType: 'icon',
                    shortName: '',
                    emojiImageId: `emoji-${locationInfo.emoji || '📍'}`,
                    color,
                    sortKey: -10000 - lat
                }
            });

            // Expanded label — 2-line; only emit when an event label exists
            if (eventLabel) {
                expandedLabelFeatures.push({
                    type: 'Feature',
                    geometry: { type: 'Point', coordinates: [lng, lat] },
                    properties: {
                        locationKey,
                        labelType: 'expanded',
                        locationName: shortName,
                        eventLabel,
                        eventLabelExtra,
                        eventLabelColor: _toEventLabelColor(color),
                        shortName,
                        color,
                        sortKey: -5000 - lat
                    }
                });
            }

            locationKeys.push(locationKey);
        }

        // Order: icons, then expanded labels. Icons map 1:1 to locations
        // (0..N-1) and own the feature-state for hover/active rings. Expanded
        // labels are sparse (only when a non-empty event label exists), so we
        // record their feature IDs explicitly while building the array.
        const features = [];
        iconFeatures.forEach((f, i) => {
            features.push(f);
            const lk = f.properties.locationKey;
            state.locationKeyToFeatureId.set(lk, i);
            state.featureIdToLocationKey.set(i, lk);
        });
        expandedLabelFeatures.forEach((f) => {
            const id = features.length;
            features.push(f);
            state.featureIdToLocationKey.set(id, f.properties.locationKey);
        });

        const geojson = { type: 'FeatureCollection', features };
        state.sourceDataCache = geojson;

        // Clear stale feature-state before replacing data — MapLibre preserves
        // feature-state across setData(), so old hover/active states would
        // "stick" to whatever feature inherits the same auto-generated ID.
        if (state.hoveredFeatureId !== null) {
            map.setFeatureState({ source: 'markers', id: state.hoveredFeatureId }, { hover: false });
            state.hoveredFeatureId = null;
        }
        if (state.activeFeatureId !== null) {
            map.setFeatureState({ source: 'markers', id: state.activeFeatureId }, { active: false });
            state.activeFeatureId = null;
        }

        const source = map.getSource('markers');
        if (source) {
            source.setData(geojson);
        }

        // Re-apply active state if popup is open
        if (state.currentPopupLocationKey) {
            const fid = state.locationKeyToFeatureId.get(state.currentPopupLocationKey);
            if (fid !== undefined) {
                state.activeFeatureId = fid;
                map.setFeatureState({ source: 'markers', id: fid }, { active: true });
            }
        }
        _updateHoverFilter();
    }

    function _restoreAfterStyleChange() {
        const map = state.mapInstance;
        if (!map || !state.sourceDataCache) return;

        // Reload emoji images
        const uniqueEmojis = new Set();
        state.sourceDataCache.features.forEach(f => {
            const eid = f.properties.emojiImageId;
            if (eid) {
                const emoji = eid.replace('emoji-', '');
                uniqueEmojis.add(emoji);
            }
        });
        uniqueEmojis.forEach(emoji => _addEmojiImage(emoji));

        // Restore data
        const source = map.getSource('markers');
        if (source) {
            source.setData(state.sourceDataCache);
        }

        // Rebuild lookup maps — icons are emitted first; labelType disambiguates
        state.locationKeyToFeatureId.clear();
        state.featureIdToLocationKey.clear();
        state.sourceDataCache.features.forEach((f, i) => {
            const locKey = f.properties.locationKey;
            state.featureIdToLocationKey.set(i, locKey);
            if (f.properties.labelType === 'icon') {
                state.locationKeyToFeatureId.set(locKey, i);
            }
        });

        // Restore active state
        if (state.currentPopupLocationKey) {
            const fid = state.locationKeyToFeatureId.get(state.currentPopupLocationKey);
            if (fid !== undefined) {
                state.activeFeatureId = fid;
                map.setFeatureState({ source: 'markers', id: fid }, { active: true });
            }
        }
        _updateHoverFilter();

        // Update theme colors
        updateThemeColors();
    }

    // ========================================
    // INTERACTIONS
    // ========================================

    /**
     * Updates the marker-symbols-hover filter to show the hovered and/or active
     * location's label, even when the main layer dropped it on collision.
     * Called whenever hover or active state changes.
     *
     * Labels are always 2-line (the single 'expanded' variant), so there is
     * nothing to match against the main layer's collision result — we simply
     * show every feature (icon + expanded) for the hovered/active keys. This
     * keeps the per-hover work to a single setFilter() with no
     * queryRenderedFeatures() scan.
     */
    function _updateHoverFilter() {
        const map = state.mapInstance;
        if (!map || !map.getLayer('marker-symbols-hover')) return;

        const keys = new Set();
        if (state.hoveredFeatureId !== null) {
            const lk = state.featureIdToLocationKey.get(state.hoveredFeatureId);
            if (lk) keys.add(lk);
        }
        if (state.activeFeatureId !== null) {
            const lk = state.featureIdToLocationKey.get(state.activeFeatureId);
            if (lk) keys.add(lk);
        }

        let keyFilter;
        if (keys.size === 0) {
            keyFilter = ['==', ['get', 'locationKey'], '']; // matches nothing
        } else if (keys.size === 1) {
            keyFilter = ['==', ['get', 'locationKey'], [...keys][0]];
        } else {
            keyFilter = ['in', ['get', 'locationKey'], ['literal', [...keys]]];
        }

        map.setFilter('marker-symbols-hover', keyFilter);
    }

    /**
     * When icon-padding causes overlapping hit areas, MapLibre returns
     * features sorted by symbol-sort-key — not by proximity to the cursor.
     * This picks the feature whose geometry is closest to the event point.
     */
    /**
     * Programmatically highlight a location's marker (ring + label) by its
     * locationKey, mirroring a mouse hover. Used by the desktop list view so
     * hovering a list row highlights the corresponding marker. Shares the same
     * `hoveredFeatureId` state as real mouse hover, so the two interleave
     * cleanly. No-op if the location has no currently-rendered marker.
     */
    function highlightLocationByKey(locationKey) {
        const map = state.mapInstance;
        if (!map) return;
        const iconFid = state.locationKeyToFeatureId.get(locationKey);
        if (iconFid === undefined) return;
        if (iconFid === state.hoveredFeatureId) return;
        if (state.hoveredFeatureId !== null) {
            map.setFeatureState({ source: 'markers', id: state.hoveredFeatureId }, { hover: false });
        }
        state.hoveredFeatureId = iconFid;
        map.setFeatureState({ source: 'markers', id: iconFid }, { hover: true });
        _updateHoverFilter();
    }

    /** Clear any hover highlight set via highlightLocationByKey or mouse hover. */
    function clearHoverHighlight() {
        const map = state.mapInstance;
        if (!map) return;
        if (state.hoveredFeatureId !== null) {
            map.setFeatureState({ source: 'markers', id: state.hoveredFeatureId }, { hover: false });
            state.hoveredFeatureId = null;
            _updateHoverFilter();
        }
    }

    function _closestFeature(e) {
        const features = e.features;
        if (!features || features.length === 0) return null;
        if (features.length === 1) return features[0];

        const pt = e.lngLat;
        let best = features[0];
        let bestDist = Infinity;
        for (const f of features) {
            const coords = f.geometry.coordinates;
            const dx = coords[0] - pt.lng;
            const dy = coords[1] - pt.lat;
            const d = dx * dx + dy * dy;
            if (d < bestDist) { bestDist = d; best = f; }
        }
        return best;
    }

    function setupMarkerInteractions() {
        const map = state.mapInstance;
        if (!map) return;

        // Hover handlers — use mousemove (not mouseenter) so that when
        // markers overlap, moving between them updates the hovered feature
        // immediately rather than staying stuck on the first one entered.
        map.on('mousemove', 'marker-symbols', (e) => {
            map.getCanvas().style.cursor = 'pointer';
            const feature = _closestFeature(e);
            if (feature) {
                // Resolve to the icon feature ID for this location
                const locationKey = feature.properties.locationKey;
                const iconFid = state.locationKeyToFeatureId.get(locationKey);
                if (iconFid === undefined) return;
                if (iconFid === state.hoveredFeatureId) return; // same location, no-op
                if (state.hoveredFeatureId !== null) {
                    map.setFeatureState({ source: 'markers', id: state.hoveredFeatureId }, { hover: false });
                }
                state.hoveredFeatureId = iconFid;
                map.setFeatureState({ source: 'markers', id: iconFid }, { hover: true });
                _updateHoverFilter();
            }
        });

        map.on('mouseleave', 'marker-symbols', () => {
            map.getCanvas().style.cursor = '';
            if (state.hoveredFeatureId !== null) {
                map.setFeatureState({ source: 'markers', id: state.hoveredFeatureId }, { hover: false });
                state.hoveredFeatureId = null;
                _updateHoverFilter();
            }
        });

        // Click: open popup for the closest marker to the click point
        map.on('click', 'marker-symbols', (e) => {
            const feature = _closestFeature(e);
            if (feature) {
                const locationKey = feature.properties.locationKey;
                _openPopupForLocation(locationKey, e.lngLat);
            }
        });

        // Click on empty map: dismiss bottom sheet (mobile)
        map.on('click', (e) => {
            if (typeof BottomSheet === 'undefined' || (!BottomSheet.isOpen() && !BottomSheet.isDetailMode())) return;
            const features = map.queryRenderedFeatures(e.point, { layers: ['marker-symbols'] });
            if (features.length === 0) {
                BottomSheet.dismissToMini();
            }
        });
    }

    function _openPopupForLocation(locationKey, lngLat) {
        const map = state.mapInstance;
        if (!map) return;

        // Close existing popup
        if (state.currentPopup) {
            state.currentPopup.remove();
            // The close handler will clean up state
        }

        // Get popup content
        const callback = state.popupContentCallbacks.get(locationKey);
        if (!callback) return;

        const content = callback();

        // Create wrapper
        const wrapper = document.createElement('div');
        wrapper.className = 'maplibre-popup-content';
        if (content instanceof HTMLElement) {
            wrapper.appendChild(content);
        } else {
            wrapper.innerHTML = content;
        }

        // Clear previous active state
        if (state.activeFeatureId !== null) {
            map.setFeatureState({ source: 'markers', id: state.activeFeatureId }, { active: false });
        }

        // Set new active state
        const fid = state.locationKeyToFeatureId.get(locationKey);
        if (fid !== undefined) {
            state.activeFeatureId = fid;
            map.setFeatureState({ source: 'markers', id: fid }, { active: true });
        }
        _updateHoverFilter();

        // Mobile: use bottom sheet instead of MapLibre popup
        const isMobile = window.innerWidth <= Constants.UI.MOBILE_BREAKPOINT;
        if (isMobile && typeof BottomSheet !== 'undefined') {
            state.currentPopup = null;
            state.currentPopupLocationKey = locationKey;
            BottomSheet.open(locationKey, lngLat, wrapper);
            // popupopen event is fired by BottomSheet.open()
            return;
        }

        // Desktop: standard MapLibre popup
        const popup = new maplibregl.Popup({
            closeButton: true,
            closeOnClick: true,
            maxWidth: 'none',
            anchor: 'bottom',
            offset: [0, -26]
        });

        // Handle popup close
        popup.on('close', () => {
            if (state.currentPopup === popup) {
                const closedLocationKey = state.currentPopupLocationKey;

                // Clear active state
                if (state.activeFeatureId !== null) {
                    map.setFeatureState({ source: 'markers', id: state.activeFeatureId }, { active: false });
                    state.activeFeatureId = null;
                }

                state.currentPopup = null;
                state.currentPopupLocationKey = null;
                _updateHoverFilter();

                map.fire('popupclose', {
                    popup,
                    locationKey: closedLocationKey,
                    lngLat
                });
            }
        });

        popup.setLngLat([lngLat.lng, lngLat.lat])
            .setDOMContent(wrapper)
            .addTo(map);

        state.currentPopup = popup;
        state.currentPopupLocationKey = locationKey;

        map.fire('popupopen', {
            popup,
            locationKey,
            lngLat
        });
    }

    // ========================================
    // PUBLIC POPUP API
    // ========================================

    function openPopupAtCoordinates(locationKey, lngLat) {
        _openPopupForLocation(locationKey, { lng: lngLat[0], lat: lngLat[1] });
    }

    function registerPopupCallback(locationKey, callback) {
        state.popupContentCallbacks.set(locationKey, callback);
    }

    function getCurrentPopup() {
        return state.currentPopup;
    }

    function getCurrentPopupLocationKey() {
        return state.currentPopupLocationKey;
    }

    // ========================================
    // THEME
    // ========================================

    function updateThemeColors() {
        const map = state.mapInstance;
        if (!map || !map.getLayer('marker-symbols')) return;

        map.setPaintProperty('marker-symbols', 'text-color', _getLabelColor());
        map.setPaintProperty('marker-symbols', 'text-halo-color', _getHaloColor());

        if (map.getLayer('marker-symbols-hover')) {
            map.setPaintProperty('marker-symbols-hover', 'text-color', _getHoverLabelColor());
            map.setPaintProperty('marker-symbols-hover', 'text-halo-color', _getHaloColor());
        }

        // Per-section event label color depends on theme (different lightness),
        // so recompute it from the marker color and re-push the source data.
        if (state.sourceDataCache) {
            let changed = false;
            state.sourceDataCache.features.forEach(f => {
                if (f.properties.labelType !== 'expanded') return;
                const next = _toEventLabelColor(f.properties.color);
                if (f.properties.eventLabelColor !== next) {
                    f.properties.eventLabelColor = next;
                    changed = true;
                }
            });
            if (changed) {
                const source = map.getSource('markers');
                if (source) source.setData(state.sourceDataCache);
            }
        }
    }

    // ========================================
    // UTILITY
    // ========================================

    // Set/replace the emoji→marker-color map. Lets the map be created before
    // the tag config (which carries bgcolors) has loaded — colors are only read
    // when markers are actually built (updateMarkerData), which happens after.
    function setMarkerColors(markerColors) {
        state.markerColorsRef = markerColors || {};
    }

    function getMarkerColor(locationInfo) {
        if (locationInfo) {
            const emoji = locationInfo.emoji;
            const colors = state.markerColorsRef;
            if (colors && colors[emoji]) {
                return colors[emoji];
            }
        }
        return '#444';
    }

    function getMap() {
        return state.mapInstance;
    }

    /**
     * Clears active marker highlight state.
     * Called by BottomSheet on close to remove the highlight ring.
     */
    function clearActiveState() {
        const map = state.mapInstance;
        if (state.activeFeatureId !== null && map) {
            map.setFeatureState({ source: 'markers', id: state.activeFeatureId }, { active: false });
            state.activeFeatureId = null;
        }
        state.currentPopupLocationKey = null;
        _updateHoverFilter();
    }

    // ========================================
    // PUBLIC API
    // ========================================

    return {
        init,
        getMarkerColor,
        toEventLabelColor: _toEventLabelColor,
        getMap,
        getCurrentPopup,
        getCurrentPopupLocationKey,
        clearActiveState,
        loadEmojiImages,
        loadEmojiImagesChunked,
        reloadEmojiImages,
        setMarkerColors,
        updateMarkerData,
        setupMarkerInteractions,
        openPopupAtCoordinates,
        registerPopupCallback,
        updateThemeColors,
        highlightLocationByKey,
        clearHoverHighlight
    };
})();
