/**
 * MapManager - WebGL Symbol Layer based marker rendering
 * Uses MapLibre native layers instead of DOM markers for GPU-accelerated performance
 * @module MapManager
 */
const MapManager = (() => {
    const state = {
        mapInstance: null,

        // Popup state
        currentPopup: null,
        currentPopupLocationKey: null,

        // Feature state tracking
        hoveredFeatureId: null,
        activeFeatureId: null,

        // "<locationKey>|<eventName>" while the hover layer's label is
        // overridden to show a specific event (list-row hover), else null
        hoverLabelEventSig: null,
        hoverIconImageId: null,

        // Bidirectional lookups between locationKey and feature ID
        locationKeyToFeatureId: new Map(),
        locationKeyToLabelFeatureId: new Map(),
        featureIdToLocationKey: new Map(),

        // All artwork uses the same lazy, themed sprite cache.
        iconDescriptors: new Map(),
        loadedIcons: new Set(),
        pendingIcons: new Set(),
        iconFades: new Map(),
        iconFadeFrame: null,
        markerFades: new Map(),
        fadedFeatureIds: new Set(),
        promotedIconIds: new Map(),
        accentedFeatureIds: new Set(),
        iconEpoch: 0,
        iconTheme: null,

        // Cache for restoring after style.load (theme change)
        sourceDataCache: null,
        layersAdded: false,
        rankedPlaces: [],
        promotedPlaces: new Set(),
        promotedSignature: null,

        // Popup content callbacks by locationKey
        popupContentCallbacks: new Map()
    };

    // ========================================
    // INITIALIZATION
    // ========================================

    function init(mapInstance) {
        state.mapInstance = mapInstance;

        // Add the marker source/layers as soon as the style is parsed. This
        // fires well before the map's `load`/`idle` events (which wait on tile
        // downloads), so emoji markers can render early. Labels are drawn
        // locally via TinySDF from the Inter webfont — no glyph PBF downloads.
        // In MapLibre v5 `style.load` fires on both initial load and
        // setStyle() (theme switch).
        mapInstance.on('style.load', _ensureLayers);

        // Ensure source/layers exist whenever the map becomes idle, too.
        // Safety net covering any path where style.load didn't (re-)create them.
        mapInstance.on('idle', _ensureLayers);
        mapInstance.on('moveend', refreshPromotedMarkers);
        mapInstance.on('resize', refreshPromotedMarkers);

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
        state.promotedSignature = null;
        _cancelIconFades();
        state.loadedIcons.clear();
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
        //   2. Event name and count of other matching events at this location.
        // Colliding labels are dropped independently of their event icons.
        // Layout/paint shared by the two symbol layers; each passes only the
        // placement/overlap flags and colors that differ.
        const symbolLayout = (overrides) => Object.assign({
            'icon-image': _getIconImageExpression(),
            'icon-size': _getIconSize(),
            'icon-allow-overlap': true,
            'icon-offset': [-8, 0],
            'text-field': _getTextFieldExpression(),
            'text-font': _getMarkerTextFont(),
            'text-size': _getLabelSize(),
            'text-anchor': 'left',
            'text-justify': 'left',
            'text-offset': [1.4, 0],
            'text-max-width': 50,
            'text-letter-spacing': 0,
            'text-line-height': 1.15,
            'symbol-sort-key': ['get', 'sortKey']
        }, overrides);
        const symbolPaint = (textColor, haloWidth) => ({
            'text-color': textColor,
            'text-halo-color': _getHaloColor(),
            'text-halo-width': haloWidth,
            'text-halo-blur': 0
        });

        map.addLayer({
            id: 'marker-dots', type: 'circle', source: 'markers',
            filter: ['==', ['get', 'labelType'], 'icon'],
            paint: {
                'circle-radius': 3,
                'circle-color': window.__CITY__?.map?.dot_color || '#808080',
                'circle-opacity': 0.55,
                'circle-stroke-width': 0
            }
        });

        map.addLayer({
            id: 'marker-symbols',
            type: 'symbol',
            source: 'markers',
            filter: ['==', ['get', 'locationKey'], ''],
            layout: symbolLayout({
                'icon-ignore-placement': false,
                'icon-padding': 0,
                'text-allow-overlap': false,
                'text-optional': true,
                'text-ignore-placement': false,
                'text-padding': 3
            }),
            // Keep highlighted symbols in collision placement, but let the
            // overlay draw them. Removing them frees room for unrelated labels.
            paint: {
                ...symbolPaint(_getLabelColor(), 2),
                'icon-opacity': ['case', ['any',
                    ['boolean', ['feature-state', 'hover'], false],
                    ['boolean', ['feature-state', 'active'], false]], 0,
                    ['coalesce', ['feature-state', 'iconOpacity'], 1]],
                'text-opacity': ['case', ['any',
                    ['boolean', ['feature-state', 'hover'], false],
                    ['boolean', ['feature-state', 'active'], false]], 0, 1]
            }
        });

        // Layer 2: Highlight circle (colored ring on hover/active, above all emojis)
        map.addLayer({
            id: 'marker-highlight',
            type: 'circle',
            source: 'markers',
            filter: ['==', ['get', 'labelType'], 'icon'],
            paint: {
                'circle-radius': _getMarkerRadius(),
                'circle-color': 'transparent',
                'circle-stroke-width': [
                    'case',
                    ['boolean', ['feature-state', 'active'], false], 4,
                    ['boolean', ['feature-state', 'hover'], false], 4,
                    0
                ],
                'circle-stroke-color': ['coalesce', ['feature-state', 'accent'], ['get', 'color']]
            }
        });

        // Layer 3: Hover — emoji + label, always visible, shown only for hovered feature
        map.addLayer({
            id: 'marker-symbols-hover',
            type: 'symbol',
            source: 'markers',
            filter: ['==', ['get', 'locationKey'], ''], // hidden by default
            layout: symbolLayout({
                'icon-ignore-placement': true,
                'text-allow-overlap': true,
                'text-ignore-placement': true
            }),
            paint: symbolPaint(_getHoverLabelColor(), 2.5)
        });

        // Freshly created layers have the default hover text-field (no
        // per-event label override).
        state.hoverLabelEventSig = null;
        state.layersAdded = true;

        // Only promoted emoji have hit targets. Dots are passive density hints;
        // hovering or clicking one must never promote it or open its content.
        map.addLayer({
            id: 'marker-hit-targets', type: 'circle', source: 'markers',
            filter: ['==', ['get', 'locationKey'], ''],
            paint: { 'circle-radius': Utils.isMobileLayout() ? 12 : 9, 'circle-opacity': 0 }
        });
        _syncDotTheme();
    }

    function _syncDotTheme() {
        const map = state.mapInstance;
        if (!map?.getLayer('marker-dots')) return;
        const dark = Utils.getCurrentTheme() === 'dark';
        if (dark && !map.getLayer('marker-dot-density')) {
            map.addLayer(DotDensityLayer.create(() => ({ places: state.rankedPlaces, promoted: state.promotedPlaces }),
                window.__CITY__?.map?.dot_color || '#808080'), 'marker-symbols');
        } else if (!dark && map.getLayer('marker-dot-density')) map.removeLayer('marker-dot-density');
        map.setPaintProperty('marker-dots', 'circle-opacity', dark ? 0 : .55);
    }

    function refreshPromotedMarkers() {
        const map = state.mapInstance;
        if (!map?.getLayer('marker-symbols')) return;
        const canvas = map.getCanvas();
        const rect = canvas.getBoundingClientRect();
        // The canvas extends beyond the window for map tilt/overscan. Budget
        // actual visible pixels, not that larger backing canvas.
        const viewport = document.getElementById('map-container').getBoundingClientRect();
        const left = Math.max(0, viewport.left, rect.left), top = Math.max(0, viewport.top, rect.top);
        const right = Math.min(innerWidth, viewport.right, rect.right), bottom = Math.min(innerHeight, viewport.bottom, rect.bottom);
        const cover = ['filter-panel', 'sheet'].map(id => document.getElementById(id))
            .filter(el => el && !el.classList.contains('initially-hidden'))
            .map(el => el.getBoundingClientRect());
        const bounds = map.getBounds();
        const candidates = state.rankedPlaces.filter(c => {
            if (!bounds.contains(c.coordinates)) return false;
            const p = map.project(c.coordinates);
            const x = p.x + rect.left, y = p.y + rect.top;
            c.distance = Math.hypot(x - (left + right) / 2, y - (top + bottom) / 2);
            if (x < left + 12 || y < top + 12 || x > right - 12 || y > bottom - 12) return false;
            return !cover.some(r => x >= r.left && x <= r.right && y >= r.top && y <= r.bottom);
        });
        const hovered = state.featureIdToLocationKey.get(state.hoveredFeatureId);
        const active = state.featureIdToLocationKey.get(state.activeFeatureId);
        const pinned = [active, hovered].filter(Boolean);
        const limit = Utils.isMobileLayout() ? 10 : 20;
        const chosen = DiscoveryRanking.topPlaces(candidates, limit, pinned);
        state.promotedPlaces = chosen;
        const previousIcons = state.promotedIconIds;
        state.promotedIconIds = new Map();
        for (const key of chosen) {
            const fid = state.locationKeyToFeatureId.get(key);
            const icon = state.sourceDataCache?.features[fid];
            if (icon) {
                const imageId = icon.properties.iconImageId;
                state.promotedIconIds.set(key, imageId);
                // MapLibre can skip placement fades on reloaded icon buckets.
                // Cached artwork therefore needs a per-marker fade as well.
                if (state.loadedIcons.has(imageId) && previousIcons.get(key) !== imageId &&
                    !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
                    state.markerFades.set(key, { imageId, start: performance.now() });
                    state.fadedFeatureIds.add(fid);
                    _setMarkerFeatureState(fid, { iconOpacity: 0 });
                    if (state.iconFadeFrame === null) state.iconFadeFrame = requestAnimationFrame(_animateIconFades);
                }
                _addIconImage(imageId);
            }
        }
        // Pinning can change Set order without changing membership. Keep the
        // filter stable so hovering an existing icon never re-lays out symbols.
        const promotedKeys = [...chosen].sort();
        const signature = JSON.stringify(promotedKeys);
        if (signature !== state.promotedSignature) {
            state.promotedSignature = signature;
            map.setFilter('marker-symbols', ['in', ['get', 'locationKey'], ['literal', promotedKeys]]);
            map.setFilter('marker-hit-targets', ['all', ['==', ['get', 'labelType'], 'icon'],
                ['in', ['get', 'locationKey'], ['literal', [...chosen]]]]);
            map.setFilter('marker-dots', ['all', ['==', ['get', 'labelType'], 'icon'],
                ['!', ['in', ['get', 'locationKey'], ['literal', [...chosen]]]]]);
        }
    }

    function _getMarkerRadius() {
        return Utils.isMobileLayout() ? 20 : 24;
    }

    function _getIconSize() {
        return Utils.isMobileLayout() ? 0.55 : 0.7;
    }

    function _getLabelSize() {
        return Utils.isMobileLayout() ? 13 : 14.5;
    }

    function _getLabelColor() {
        return Utils.getCurrentTheme() === 'dark' ? '#e5e5e5' : '#1a1a1a';
    }

    function _getHoverLabelColor() {
        return Utils.getCurrentTheme() === 'dark' ? '#fff' : '#000';
    }

    function _getHaloColor() {
        return Utils.getCurrentTheme() === 'dark' ? '#171717' : '#f0f0f0';
    }

    /** Marker-label fontstack. */
    function _getMarkerTextFont() {
        return ['Inter Regular'];
    }

    /**
     * Builds the text-field expression used by both the main and hover layers.
     * Renders the event name for expanded features; icon features carry no
     * text. Names inherit the layer's primary label color, font, and size.
     */
    function _getTextFieldExpression() {
        return ['case',
            ['==', ['get', 'labelType'], 'expanded'],
                ['concat', ['get', 'eventLabel'], ['get', 'eventLabelExtra']],
            ''
        ];
    }

    /**
     * Recolors an event label by keeping a base color's hue but pinning its
     * OKLCH lightness and chroma to theme-dependent targets, so every label
     * reads as equally bright and equally saturated regardless of hue.
     * Returns an sRGB hex (parsed equally well by CSS and MapLibre).
     * OKLCH math lives in the shared ColorUtils module (core/colorUtils.js).
     *   opts.lightness — OKLCH L as a 0–100 percentage
     *   opts.chroma    — OKLCH chroma (≈0–0.37); gamut-clamped per hue
     */
    // Memo for _toEventLabelColor: pure math over a bounded input space
    // (emoji-derived palette × theme × the few fixed opts variants).
    const _labelColorCache = new Map();

    function _toEventLabelColor(hexColor, opts = {}) {
        const theme = Utils.getCurrentTheme();
        const cacheKey = `${theme}|${hexColor}|${opts.lightness ?? ''}|${opts.chroma ?? ''}`;
        const cached = _labelColorCache.get(cacheKey);
        if (cached !== undefined) return cached;
        const themeL = Utils.getCurrentTheme() === 'dark' ? 74 : 50;
        const hue = ColorUtils.oklchHueFromHex(hexColor || '#888');
        const targetL = (opts.lightness ?? themeL) / 100;
        const targetC = hue === null ? 0 : (opts.chroma ?? 0.06);
        const result = ColorUtils.oklchToHex(targetL, targetC, hue ?? 0);
        if (_labelColorCache.size >= 4096) _labelColorCache.clear(); // safety valve; never expected to hit
        _labelColorCache.set(cacheKey, result);
        return result;
    }

    /**
     * Builds the event label parts.
     * Returns the first event's name (truncated with ellipsis) and a separate
     * " +N" suffix string when there are additional matching events at the
     * location. Split into two parts so the format expression can color them
     * independently — the name uses the marker's hue, the count is neutral.
     */
    function _buildEventLabel(events) {
        if (!events || events.length === 0) return { name: '', extra: '' };
        const first = events[0];
        // Strip country-flag emoji on every platform: the SDF label font has no
        // glyph for regional-indicator pairs, so they render as tofu in labels.
        // Compose accents before SDF glyph layout and truncation: decomposed
        // names such as "Simo\u0301n" otherwise give the accent its own advance.
        const rawName = Utils.stripCountryFlagEmoji((first && (first.short_name || first.name)) || '').normalize('NFC');
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
    // SHARED ARTWORK SPRITES
    // ========================================

    function _getIconImageExpression() {
        return ['coalesce', ['get', 'iconImageId'], ''];
    }

    function _eventIcon(event) {
        const descriptor = IconManager.resolve(event);
        const iconImageId = `icon-${descriptor.id}-${descriptor.revision}`;
        state.iconDescriptors.set(iconImageId, descriptor);
        return { iconImageId, color: IconManager.getColor(event) };
    }

    function _addIconImage(imageId) {
        const map = state.mapInstance;
        const descriptor = state.iconDescriptors.get(imageId);
        if (!descriptor || state.loadedIcons.has(imageId) || state.pendingIcons.has(imageId)) return;
        const epoch = state.iconEpoch;
        const theme = Utils.getCurrentTheme();
        const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
        const size = 64 * pixelRatio;
        // A fixed transparent slot prevents missing-image warnings during decode.
        if (!map.hasImage(imageId)) map.addImage(imageId,
            { width: size, height: size, data: new Uint8Array(size * size * 4) }, { pixelRatio });
        state.pendingIcons.add(imageId);
        IconManager.prepare(descriptor, theme, true).then(result => {
            if (state.iconEpoch !== epoch || !map.hasImage(imageId)) return;
            _fadeInIconImage(imageId, result.pixels);
            state.pendingIcons.delete(imageId);
            state.loadedIcons.add(imageId);
            if (state.loadedIcons.size > 128) {
                const keep = new Set([state.hoverIconImageId]);
                for (const key of state.promotedPlaces) {
                    const fid = state.locationKeyToFeatureId.get(key);
                    keep.add(state.sourceDataCache?.features[fid]?.properties.iconImageId);
                }
                for (const oldId of state.loadedIcons) {
                    if (state.loadedIcons.size <= 128) break;
                    if (keep.has(oldId)) continue;
                    if (map.hasImage(oldId)) map.removeImage(oldId);
                    state.loadedIcons.delete(oldId);
                }
            }
            if (state.sourceDataCache) {
                const keys = new Set(state.sourceDataCache.features
                    .filter(f => f.properties.iconImageId === imageId).map(f => f.properties.locationKey));
                state.sourceDataCache.features.forEach(f => {
                    if (keys.has(f.properties.locationKey)) f.properties.color = result.accent;
                });
                // Artwork and its accent are paint-only updates. Replacing the
                // GeoJSON here restarts collision placement for every label.
                for (const key of keys) {
                    const id = state.locationKeyToFeatureId.get(key);
                    if (id !== undefined) {
                        _setMarkerFeatureState(id, { accent: result.accent });
                        state.accentedFeatureIds.add(id);
                    }
                }
            }
        }).catch(() => {
            if (state.iconEpoch === epoch) state.pendingIcons.delete(imageId);
        });
    }

    // Symbol placement can finish fading while its sprite is still a transparent
    // loading slot. Fade the decoded pixels separately, without re-placing labels.
    function _fadeInIconImage(imageId, pixels) {
        if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
            state.mapInstance.updateImage(imageId, pixels);
            return;
        }
        state.iconFades.set(imageId, {
            pixels,
            frame: { width: pixels.width, height: pixels.height, data: new Uint8Array(pixels.data) },
            start: performance.now()
        });
        if (state.iconFadeFrame === null) state.iconFadeFrame = requestAnimationFrame(_animateIconFades);
    }

    function _animateIconFades(now) {
        state.iconFadeFrame = null;
        const map = state.mapInstance;
        for (const [imageId, fade] of state.iconFades) {
            if (!map?.hasImage(imageId)) {
                state.iconFades.delete(imageId);
                continue;
            }
            const opacity = Math.min(1, Math.max(0, (now - fade.start) / 150));
            if (opacity === 1) {
                map.updateImage(imageId, fade.pixels);
                state.iconFades.delete(imageId);
            } else {
                for (let i = 3; i < fade.frame.data.length; i += 4) {
                    fade.frame.data[i] = Math.round(fade.pixels.data[i] * opacity);
                }
                map.updateImage(imageId, fade.frame);
            }
        }
        for (const [key, fade] of state.markerFades) {
            const id = state.locationKeyToFeatureId.get(key);
            if (id === undefined || state.promotedIconIds.get(key) !== fade.imageId) {
                if (id !== undefined) _setMarkerFeatureState(id, { iconOpacity: 1 });
                state.markerFades.delete(key);
                continue;
            }
            const opacity = Math.min(1, Math.max(0, (now - fade.start) / 150));
            _setMarkerFeatureState(id, { iconOpacity: opacity });
            if (opacity === 1) state.markerFades.delete(key);
        }
        if (state.iconFades.size || state.markerFades.size) state.iconFadeFrame = requestAnimationFrame(_animateIconFades);
    }

    function _cancelIconFades() {
        if (state.iconFadeFrame !== null) cancelAnimationFrame(state.iconFadeFrame);
        state.iconFadeFrame = null;
        state.iconFades.clear();
        _resetMarkerFades();
    }

    function _resetMarkerFades() {
        state.markerFades.clear();
        for (const id of state.fadedFeatureIds) _setMarkerFeatureState(id, { iconOpacity: null });
        state.fadedFeatureIds.clear();
    }

    function _syncIconEpoch() {
        const key = Utils.getCurrentTheme();
        if (key === state.iconTheme) return;
        state.iconTheme = key;
        reloadIconImages();
    }

    function reloadIconImages() {
        const map = state.mapInstance;
        if (!map) return;
        state.iconEpoch++;
        _cancelIconFades();
        for (const id of state.accentedFeatureIds) _setMarkerFeatureState(id, { accent: null });
        state.accentedFeatureIds.clear();
        state.pendingIcons.clear();
        state.loadedIcons.clear();
        state.iconTheme = Utils.getCurrentTheme();
        _clearHoverLabelEvent();
        map.listImages().filter(id => id.startsWith('icon-')).forEach(id => map.removeImage(id));
        refreshPromotedMarkers();
    }

    // ========================================
    // MARKER DATA MANAGEMENT
    // ========================================

    function updateMarkerData(filteredLocations, locationsByLatLng, popupContentCallbacks, matchingLocations = filteredLocations) {
        const map = state.mapInstance;
        if (!map) return;
        _resetMarkerFades();
        _syncIconEpoch();

        // Clear stale feature-state before replacing data — MapLibre preserves
        // feature-state across setData(), so old hover/active states would
        // "stick" to whatever feature inherits the same auto-generated ID.
        // The hover-label override references the old data too.
        _clearHoverLabelEvent();
        if (state.hoveredFeatureId !== null) {
            _setMarkerFeatureState(state.hoveredFeatureId, { hover: false });
            state.hoveredFeatureId = null;
        }
        if (state.activeFeatureId !== null) {
            _setMarkerFeatureState(state.activeFeatureId, { active: false });
            state.activeFeatureId = null;
        }
        // Generated IDs can now belong to different icons, including their
        // asynchronously resolved paint colors.
        for (const id of state.accentedFeatureIds) _setMarkerFeatureState(id, { accent: null });
        state.accentedFeatureIds.clear();

        // Store callbacks
        state.popupContentCallbacks = popupContentCallbacks;

        // Build GeoJSON features — up to two per location:
        //   1. Icon (lowest sortKey → placed first, populates collision grid)
        //   2. Event label; a label that collides is simply dropped.
        const iconFeatures = [];
        const expandedLabelFeatures = [];
        state.rankedPlaces = [];
        state.locationKeyToFeatureId.clear();
        state.locationKeyToLabelFeatureId.clear();
        state.featureIdToLocationKey.clear();

        for (const locationKey in filteredLocations) {
            const events = filteredLocations[locationKey];
            if (events.length === 0) continue;

            const ll = Utils.parseLocationKey(locationKey);
            if (!ll) continue;
            const { lat, lng } = ll;
            if (lat === 0 && lng === 0) continue;

            const locationInfo = locationsByLatLng[locationKey];
            if (!locationInfo) continue;

            const ranked = [...(matchingLocations[locationKey] || events)].sort((a, b) =>
                DiscoveryRanking.score(b, locationInfo) - DiscoveryRanking.score(a, locationInfo) || Number(a.id) - Number(b.id));
            const { iconImageId, color } = _eventIcon(ranked[0]);
            const { name: eventLabel, extra: eventLabelExtra } = _buildEventLabel(ranked);
            state.rankedPlaces.push({ key: locationKey, coordinates: [lng, lat],
                score: ranked.length ? DiscoveryRanking.score(ranked[0], locationInfo) : 0 });

            // Icon feature — no text (the default text-field expression skips
            // icons), placed first via low sortKey.
            iconFeatures.push({
                type: 'Feature',
                geometry: { type: 'Point', coordinates: [lng, lat] },
                properties: {
                    locationKey,
                    labelType: 'icon',
                    iconImageId,
                    color,
                    sortKey: -10000 - lat
                }
            });

            // Only emit a label when an event name exists.
            if (eventLabel) {
                expandedLabelFeatures.push({
                    type: 'Feature',
                    geometry: { type: 'Point', coordinates: [lng, lat] },
                    properties: {
                        locationKey,
                        labelType: 'expanded',
                        eventLabel,
                        eventLabelExtra,
                        color,
                        sortKey: -5000 - lat
                    }
                });
            }
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
            state.locationKeyToLabelFeatureId.set(f.properties.locationKey, id);
        });

        const geojson = { type: 'FeatureCollection', features };
        state.sourceDataCache = geojson;

        const source = map.getSource('markers');
        if (source) {
            source.setData(geojson);
        }

        // Re-apply active state if popup is open
        if (state.currentPopupLocationKey) {
            const fid = state.locationKeyToFeatureId.get(state.currentPopupLocationKey);
            if (fid !== undefined) {
                state.activeFeatureId = fid;
                _setMarkerFeatureState(fid, { active: true });
            }
        }
        _updateHoverFilter();
    }

    function _restoreAfterStyleChange() {
        const map = state.mapInstance;
        if (!map || !state.sourceDataCache) return;

        // Style reloads can destroy images even when the theme is unchanged.
        reloadIconImages();

        // Restore data
        const source = map.getSource('markers');
        if (source) {
            source.setData(state.sourceDataCache);
        }

        // Rebuild lookup maps — icons are emitted first; labelType disambiguates
        state.locationKeyToFeatureId.clear();
        state.locationKeyToLabelFeatureId.clear();
        state.featureIdToLocationKey.clear();
        state.sourceDataCache.features.forEach((f, i) => {
            const locKey = f.properties.locationKey;
            state.featureIdToLocationKey.set(i, locKey);
            if (f.properties.labelType === 'icon') {
                state.locationKeyToFeatureId.set(locKey, i);
            } else {
                state.locationKeyToLabelFeatureId.set(locKey, i);
            }
        });

        // Restore active state
        if (state.currentPopupLocationKey) {
            const fid = state.locationKeyToFeatureId.get(state.currentPopupLocationKey);
            if (fid !== undefined) {
                state.activeFeatureId = fid;
                _setMarkerFeatureState(fid, { active: true });
            }
        }
        _updateHoverFilter();

        // Update theme-dependent layer properties
        applyThemeToLayers();
    }

    // ========================================
    // INTERACTIONS
    // ========================================

    /**
     * Updates the marker-symbols-hover filter to show the hovered and/or active
     * location's label, even when the main layer dropped it on collision.
     * Called whenever hover or active state changes.
     *
     * Show every feature (icon + event label) for the hovered/active keys,
     * regardless of the main layer's collision result. This
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
        refreshPromotedMarkers();
    }

    /**
     * Overrides the hover layer's icon and label for `locationKey` to show
     * `labelEvent` — the desktop list view hovers individual
     * events, which may not be the event the location's default label picked.
     * The override renders on the location's icon feature (which exists even
     * when the main layer emitted no expanded label) and blanks that
     * location's expanded feature so the label isn't
     * doubled. Any other location in the hover layer (the active popup's)
     * keeps the default label.
     */
    function _setHoverLabelEvent(locationKey, labelEvent) {
        const map = state.mapInstance;
        if (!map || !map.getLayer('marker-symbols-hover')) return;
        const iconFid = state.locationKeyToFeatureId.get(locationKey);
        const icon = (iconFid !== undefined && state.sourceDataCache)
            ? state.sourceDataCache.features[iconFid]
            : null;
        const { name } = _buildEventLabel([labelEvent]);
        if (!icon || !name) {
            _clearHoverLabelEvent();
            return;
        }
        const { iconImageId } = _eventIcon(labelEvent);
        state.hoverIconImageId = iconImageId;
        _addIconImage(iconImageId);
        const sig = `${locationKey}|${name}|${iconImageId}`;
        if (sig === state.hoverLabelEventSig) return;
        state.hoverLabelEventSig = sig;
        map.setLayoutProperty('marker-symbols-hover', 'icon-image', ['case',
            ['all', ['==', ['get', 'locationKey'], locationKey], ['==', ['get', 'labelType'], 'icon']],
            iconImageId,
            _getIconImageExpression()
        ]);
        map.setLayoutProperty('marker-symbols-hover', 'text-field', ['case',
            ['==', ['get', 'locationKey'], locationKey],
                ['case',
                    ['==', ['get', 'labelType'], 'icon'],
                        name,
                    ''
                ],
            _getTextFieldExpression()
        ]);
    }

    /** Restore the hover layer's default event icon and label. */
    function _clearHoverLabelEvent() {
        const map = state.mapInstance;
        if (!map || state.hoverLabelEventSig === null || !map.getLayer('marker-symbols-hover')) return;
        state.hoverLabelEventSig = null;
        state.hoverIconImageId = null;
        map.setLayoutProperty('marker-symbols-hover', 'text-field', _getTextFieldExpression());
        map.setLayoutProperty('marker-symbols-hover', 'icon-image', _getIconImageExpression());
    }

    /**
     * Transitions the hover feature-state to `iconFid` — an icon feature ID,
     * or null to clear. No-op when unchanged (or when iconFid is undefined,
     * i.e. an unresolvable locationKey): clears the previous feature's hover
     * state, sets the new one, then refreshes the hover-label filter.
     */
    // Search/popup interactions can precede the initial source or a style reload.
    // Keep logical active state in the caller; the restore path reapplies it later.
    function _setMarkerFeatureState(id, value) {
        const map = state.mapInstance;
        if (map && map.getSource('markers')) {
            map.setFeatureState({ source: 'markers', id }, value);
            const key = state.featureIdToLocationKey.get(id);
            const labelId = state.locationKeyToLabelFeatureId.get(key);
            if (labelId !== undefined && labelId !== id) {
                map.setFeatureState({ source: 'markers', id: labelId }, value);
            }
        }
    }

    function _setHoveredIcon(iconFid) {
        const map = state.mapInstance;
        if (!map || iconFid === undefined || iconFid === state.hoveredFeatureId) return;
        if (state.hoveredFeatureId !== null) {
            _setMarkerFeatureState(state.hoveredFeatureId, { hover: false });
        }
        state.hoveredFeatureId = iconFid;
        if (iconFid !== null) {
            _setMarkerFeatureState(iconFid, { hover: true });
        }
        _updateHoverFilter();
    }

    /**
     * Programmatically highlight a location's marker (ring + label) by its
     * locationKey, mirroring a mouse hover. Used by the desktop list view so
     * hovering a list row highlights the corresponding marker. Shares the same
     * `hoveredFeatureId` state as real mouse hover, so the two interleave
     * cleanly. No-op if the location has no currently-rendered marker.
     *
     * With `labelEvent`, the icon and label show that specific event.
     */
    function highlightLocationByKey(locationKey, { labelEvent = null } = {}) {
        const map = state.mapInstance;
        if (!map) return;
        const iconFid = state.locationKeyToFeatureId.get(locationKey);
        if (iconFid === undefined) return;
        if (labelEvent) _setHoverLabelEvent(locationKey, labelEvent);
        else _clearHoverLabelEvent();
        _setHoveredIcon(iconFid);
    }

    /** Clear any hover highlight set via highlightLocationByKey or mouse hover. */
    function clearHoverHighlight() {
        _clearHoverLabelEvent();
        _setHoveredIcon(null);
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
        map.on('mousemove', 'marker-hit-targets', (e) => {
            map.getCanvas().style.cursor = 'pointer';
            const feature = _closestFeature(e);
            if (feature) {
                // Resolve to the icon feature ID for this location
                const locationKey = feature.properties.locationKey;
                const iconFid = state.locationKeyToFeatureId.get(locationKey);
                if (iconFid === undefined) return;
                // Direct marker hover always shows the default label
                _clearHoverLabelEvent();
                _setHoveredIcon(iconFid);
            }
        });

        map.on('mouseleave', 'marker-hit-targets', () => {
            map.getCanvas().style.cursor = '';
            _setHoveredIcon(null);
        });

        // Click: open popup for the closest marker to the click point
        map.on('click', (e) => {
            // Labels and promoted emoji remain clickable; dots have no hit targets.
            const features = map.queryRenderedFeatures(e.point,
                { layers: ['marker-hit-targets', 'marker-symbols', 'marker-symbols-hover'] });
            const feature = _closestFeature({ ...e, features });
            if (feature) {
                const locationKey = feature.properties.locationKey;
                _openPopupForLocation(locationKey, e.lngLat);
            }
        });

        // Click on empty map: dismiss the sheet (mobile: snap closed; desktop:
        // collapse the left-docked panel). MapLibre only fires 'click' on a
        // genuine click, not after a drag-pan, so dragging from empty space
        // leaves the sheet open.
        map.on('click', (e) => {
            const sheetActive = typeof Sheet !== 'undefined' && (Sheet.isOpen() || Sheet.isDetailMode());
            if (!sheetActive) return;
            const features = map.queryRenderedFeatures(e.point,
                { layers: ['marker-hit-targets', 'marker-symbols', 'marker-symbols-hover'] });
            if (features.length > 0) return; // clicked a marker, not empty space
            // If a popup is open, this click only closes the popup (handled by the
            // popup's own closeOnClick) — leave the sheet open. The next empty
            // click, with no popup, collapses/dismisses the sheet.
            if (state.currentPopup) return;
            Sheet.dismissToMini();
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
            _setMarkerFeatureState(state.activeFeatureId, { active: false });
        }

        // Set new active state
        const fid = state.locationKeyToFeatureId.get(locationKey);
        if (fid !== undefined) {
            state.activeFeatureId = fid;
            _setMarkerFeatureState(fid, { active: true });
        }
        _updateHoverFilter();

        // Mobile shows popup content inside the sheet (detail mode).
        const useSheetDetail = Utils.isMobileLayout();
        if (useSheetDetail && typeof Sheet !== 'undefined') {
            state.currentPopup = null;
            state.currentPopupLocationKey = locationKey;
            Sheet.openDetail(locationKey, lngLat, wrapper);
            // popupopen event is fired by Sheet.openDetail()
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
                    _setMarkerFeatureState(state.activeFeatureId, { active: false });
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

    /** Refreshes marker colors and labels after the map style changes. */
    function applyThemeToLayers() {
        const map = state.mapInstance;
        if (!map || !map.getLayer('marker-symbols')) return;

        const font = _getMarkerTextFont();
        _syncIconEpoch();
        _syncDotTheme();

        map.setPaintProperty('marker-symbols', 'text-color', _getLabelColor());
        map.setPaintProperty('marker-symbols', 'text-halo-color', _getHaloColor());
        map.setLayoutProperty('marker-symbols', 'text-font', font);
        map.setLayoutProperty('marker-symbols', 'text-field', _getTextFieldExpression());

        if (map.getLayer('marker-symbols-hover')) {
            map.setPaintProperty('marker-symbols-hover', 'text-color', _getHoverLabelColor());
            map.setPaintProperty('marker-symbols-hover', 'text-halo-color', _getHaloColor());
            map.setLayoutProperty('marker-symbols-hover', 'text-font', font);
            // Any per-event hover override embedded the old font/colors — reset
            state.hoverLabelEventSig = null;
            map.setLayoutProperty('marker-symbols-hover', 'text-field', _getTextFieldExpression());
            map.setLayoutProperty('marker-symbols-hover', 'icon-image', _getIconImageExpression());
        }

        if (state.sourceDataCache) {
            state.sourceDataCache.features.forEach(f => {
                const iconId = state.locationKeyToFeatureId.get(f.properties.locationKey);
                const icon = state.sourceDataCache.features[iconId];
                const descriptor = state.iconDescriptors.get(icon?.properties.iconImageId);
                if (descriptor) f.properties.color = IconManager.getColor({ icon_id: descriptor.id });
            });
            for (const key of state.promotedPlaces) {
                const id = state.locationKeyToFeatureId.get(key);
                if (id === undefined) continue;
                _setMarkerFeatureState(id, { accent: state.sourceDataCache.features[id].properties.color });
                state.accentedFeatureIds.add(id);
            }
            refreshPromotedMarkers();
        }
    }

    // ========================================
    // UTILITY
    // ========================================

    function getMarkerColor(record) {
        return IconManager.getColor(record || {});
    }

    function getMap() {
        return state.mapInstance;
    }

    /**
     * Clears active marker highlight state.
     * Called by the Sheet on detail close to remove the highlight ring.
     */
    function clearActiveState() {
        const map = state.mapInstance;
        if (state.activeFeatureId !== null && map) {
            _setMarkerFeatureState(state.activeFeatureId, { active: false });
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
        applyThemeToLayers,
        getMap,
        getCurrentPopup,
        getCurrentPopupLocationKey,
        clearActiveState,
        reloadIconImages,
        updateMarkerData,
        refreshPromotedMarkers,
        setupMarkerInteractions,
        openPopupAtCoordinates,
        registerPopupCallback,
        highlightLocationByKey,
        clearHoverHighlight
    };
})();
