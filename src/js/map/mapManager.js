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

        // Ensure source/layers exist whenever the map becomes idle.
        // Covers both initial load and style changes (theme switch destroys
        // custom sources/layers; idle fires after the new style is fully ready).
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
        // Each location emits TWO features: an icon-only feature (low sortKey,
        // placed first) and a label-only feature (higher sortKey, placed after
        // all icons). This ensures every icon's collision box is in the grid
        // before any label is evaluated, preventing labels from overlapping icons.
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
                'text-field': ['get', 'shortName'],
                'text-font': ['Inter SemiBold'],
                'text-size': _getLabelSize(),
                'text-anchor': 'left',
                'text-justify': 'left',
                'text-offset': [1.4, -0.15],
                'text-max-width': 50,
                'text-allow-overlap': false,
                'text-optional': true,
                'text-ignore-placement': false,
                'text-padding': 3,
                'text-letter-spacing': -0.03,
                'symbol-sort-key': ['get', 'sortKey']
            },
            paint: {
                'text-color': _getLabelColor(),
                'text-halo-color': _getHaloColor(),
                'text-halo-width': 2,
                'text-halo-blur': 1
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
                'text-field': ['get', 'shortName'],
                'text-font': ['Inter SemiBold'],
                'text-size': _getLabelSize(),
                'text-anchor': 'left',
                'text-justify': 'left',
                'text-offset': [1.4, -0.15],
                'text-max-width': 50,
                'text-allow-overlap': true,
                'text-ignore-placement': true,
                'text-letter-spacing': -0.03,
                'symbol-sort-key': ['get', 'sortKey']
            },
            paint: {
                'text-color': _getHoverLabelColor(),
                'text-halo-color': _getHaloColor(),
                'text-halo-width': 2.5,
                'text-halo-blur': 0.5
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
        return theme === 'dark' ? '#ccc' : '#333';
    }

    function _getHoverLabelColor() {
        const theme = document.documentElement.getAttribute('data-theme') || 'dark';
        return theme === 'dark' ? '#fff' : '#000';
    }

    function _getHaloColor() {
        const theme = document.documentElement.getAttribute('data-theme') || 'dark';
        return theme === 'dark' ? '#171717' : '#f0f0f0';
    }

    // ========================================
    // EMOJI IMAGE RENDERING
    // ========================================

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
        ctx.font = `${canvasSize * 0.72}px ${fontFamily}`;
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

    function reloadEmojiImages(locationsByLatLng) {
        if (!state.mapInstance) return;
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

        // Build GeoJSON features — up to three per location:
        //   1. Icon features (low sortKey → placed first, populate collision grid)
        //   2. Full label features (mid sortKey → placed after icons)
        //   3. Short label features (high sortKey → fallback if full label collides)
        const iconFeatures = [];
        const labelFeatures = [];
        const shortLabelFeatures = [];
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
            const veryShortName = locationInfo.very_short_name || '';

            // Icon feature — no text, placed first via low sortKey
            iconFeatures.push({
                type: 'Feature',
                geometry: { type: 'Point', coordinates: [lng, lat] },
                properties: {
                    locationKey,
                    shortName: '',
                    emojiImageId: `emoji-${locationInfo.emoji || '📍'}`,
                    color,
                    sortKey: -10000 - lat
                }
            });

            // Full label feature — placed after all icons
            labelFeatures.push({
                type: 'Feature',
                geometry: { type: 'Point', coordinates: [lng, lat] },
                properties: {
                    locationKey,
                    shortName,
                    color,
                    sortKey: -lat
                }
            });

            // Short label feature — fallback when full label collides
            shortLabelFeatures.push({
                type: 'Feature',
                geometry: { type: 'Point', coordinates: [lng, lat] },
                properties: {
                    locationKey,
                    shortName: veryShortName,
                    isShortLabel: true,
                    color,
                    sortKey: 10000 - lat
                }
            });

            locationKeys.push(locationKey);
        }

        // Icons (0..N-1), full labels (N..2N-1), short labels (2N..3N-1)
        const features = [...iconFeatures, ...labelFeatures, ...shortLabelFeatures];
        const N = iconFeatures.length;
        locationKeys.forEach((locationKey, i) => {
            state.locationKeyToFeatureId.set(locationKey, i); // icon feature ID
            state.featureIdToLocationKey.set(i, locationKey);       // icon
            state.featureIdToLocationKey.set(N + i, locationKey);   // full label
            state.featureIdToLocationKey.set(2 * N + i, locationKey); // short label
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

        // Rebuild lookup maps — icons are first third, labels second, short labels third
        state.locationKeyToFeatureId.clear();
        state.featureIdToLocationKey.clear();
        const allFeatures = state.sourceDataCache.features;
        const third = allFeatures.length / 3;
        allFeatures.forEach((f, i) => {
            const locKey = f.properties.locationKey;
            state.featureIdToLocationKey.set(i, locKey);
            if (i < third) {
                state.locationKeyToFeatureId.set(locKey, i); // icon feature ID
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
     * Updates the marker-symbols-hover filter to show the hovered and/or active feature.
     * Called whenever hover or active state changes.
     */
    function _updateHoverFilter() {
        const map = state.mapInstance;
        if (!map || !map.getLayer('marker-symbols-hover')) return;

        // Resolve feature IDs to locationKeys so both the icon and full-label
        // features for a location are shown in the hover layer.
        // Short labels are excluded so hover always shows the full name.
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
            keyFilter = ['==', ['get', 'locationKey'], ''];
        } else if (keys.size === 1) {
            keyFilter = ['==', ['get', 'locationKey'], [...keys][0]];
        } else {
            keyFilter = ['in', ['get', 'locationKey'], ['literal', [...keys]]];
        }
        map.setFilter('marker-symbols-hover', ['all', keyFilter, ['!=', ['get', 'isShortLabel'], true]]);
    }

    /**
     * When icon-padding causes overlapping hit areas, MapLibre returns
     * features sorted by symbol-sort-key — not by proximity to the cursor.
     * This picks the feature whose geometry is closest to the event point.
     */
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
    }

    // ========================================
    // UTILITY
    // ========================================

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
        getMap,
        getCurrentPopup,
        getCurrentPopupLocationKey,
        clearActiveState,
        loadEmojiImages,
        reloadEmojiImages,
        updateMarkerData,
        setupMarkerInteractions,
        openPopupAtCoordinates,
        registerPopupCallback,
        updateThemeColors
    };
})();
