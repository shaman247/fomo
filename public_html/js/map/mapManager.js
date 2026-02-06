/**
 * MapManager - Manages MapLibre GL map markers and their styling
 * Handles marker creation, icon generation, labels, and popups
 * @module MapManager
 */
const MapManager = (() => {
    /**
     * Internal state for MapManager
     * @private
     */
    const state = {
        mapInstance: null,
        markers: [],           // Array of {marker, popup, locationKey}
        tagColorsRef: null,
        markerColorsRef: null,
        currentPopup: null,
        currentPopupMarker: null
    };

    /**
     * Initialize MapManager with map instance and color references
     * @param {maplibregl.Map} mapInstance - MapLibre map instance
     * @param {Object} tagColors - Tag to color mapping (currently unused)
     * @param {Object} markerColors - Emoji to marker color mapping
     * @returns {Object} Object containing markers array reference
     */
    function init(mapInstance, tagColors, markerColors) {
        state.mapInstance = mapInstance;
        state.tagColorsRef = tagColors;
        state.markerColorsRef = markerColors || {};
        state.markers = [];

        return { markers: state.markers };
    }

    /**
     * Clear all markers from the map, optionally sparing one marker
     * Useful for updating markers while preserving an open popup
     * @param {Object|null} [markerToSpare=null] - Marker object to keep on the map
     */
    function clearMarkers(markerToSpare = null) {
        const markersToRemove = [];

        state.markers.forEach(markerObj => {
            if (markerToSpare && markerObj.marker === markerToSpare) {
                return; // Keep this marker
            }
            markersToRemove.push(markerObj);
        });

        markersToRemove.forEach(markerObj => {
            if (markerObj.popup && markerObj.popup !== state.currentPopup) {
                markerObj.popup.remove();
            }
            markerObj.marker.remove();
        });

        // Update markers array to only keep spared marker
        if (markerToSpare) {
            state.markers = state.markers.filter(m => m.marker === markerToSpare);
        } else {
            state.markers = [];
        }
    }

    /**
     * Get the marker color based on location's emoji
     * Falls back to default gray color if no matching color found
     * @param {Object} locationInfo - Location information object
     * @param {string} locationInfo.emoji - Location's emoji character
     * @returns {string} Hex color code for the marker
     */
    function getMarkerColor(locationInfo) {
        if (locationInfo) {
            const emoji = locationInfo.emoji;
            const colors = state.markerColorsRef;

            if (colors[emoji]) {
                return colors[emoji];
            }
        }
        return '#444';
    }

    /**
     * Create a custom HTML element for a map marker
     * Generates an SVG pin with an emoji overlay and optional label
     * @param {Object} locationInfo - Location information object
     * @param {string} locationInfo.emoji - Emoji to display on the marker
     * @param {string} locationInfo.short_name - Short name for the label
     * @returns {HTMLElement} DOM element for the marker
     */
    function createMarkerIcon(locationInfo) {
        const markerColor = getMarkerColor(locationInfo);
        const emoji = locationInfo.emoji;
        const shortName = locationInfo.short_name || locationInfo.name || '';

        const el = document.createElement('div');
        el.className = 'custom-marker-icon';
        el.style.setProperty('--marker-color', markerColor);
        el.innerHTML = `<div class="marker-emoji">${emoji}</div><div class="marker-label">${shortName}</div>`;

        return el;
    }

    /**
     * Add a marker to the map with label and popup
     * @param {Array<number>} lngLat - Marker coordinates [lng, lat] (MapLibre uses lng,lat order)
     * @param {HTMLElement} iconElement - Marker icon DOM element
     * @param {string} _unused - Unused parameter (kept for API compatibility)
     * @param {Function} popupContentCallback - Function that returns popup content
     * @param {string} locationKey - Location key for reference
     * @returns {maplibregl.Marker|undefined} The created marker, or undefined if map not initialized
     */
    function addMarkerToMap(lngLat, iconElement, _unused, popupContentCallback, locationKey) {
        if (!state.mapInstance) return;

        // Create the marker with anchor at center of the circle
        const marker = new maplibregl.Marker({
            element: iconElement,
            anchor: 'center'
        })
            .setLngLat(lngLat)
            .addTo(state.mapInstance);

        // Store marker info (popup will be created dynamically when opened)
        const markerObj = {
            marker,
            popup: null,
            locationKey,
            popupContentCallback,
            lngLat,
            labelWidth: 0,
            labelHeight: 0
        };
        state.markers.push(markerObj);

        // Cache label dimensions to avoid layout thrashing in updateMarkerVisuals
        const labelEl = iconElement.querySelector('.marker-label');
        if (labelEl) {
            labelEl.classList.add('visible');
            markerObj.labelWidth = labelEl.offsetWidth;
            markerObj.labelHeight = labelEl.offsetHeight;
            labelEl.classList.remove('visible');
        }

        // Handle hover for label
        iconElement.addEventListener('mouseenter', () => {
            // Don't highlight if popup is open for this marker
            if (state.currentPopupMarker === marker) return;

            // Show label on hover with full opacity and high z-index
            iconElement.classList.add('hovered');
        });

        iconElement.addEventListener('mouseleave', () => {
            // Remove hover state from label
            iconElement.classList.remove('hovered');
        });

        // Handle click for popup
        iconElement.addEventListener('click', (e) => {
            e.stopPropagation();

            // Close any existing popup
            if (state.currentPopup) {
                state.currentPopup.remove();
            }

            // Generate popup content
            const content = popupContentCallback();

            // Create wrapper div for popup content
            const wrapper = document.createElement('div');
            wrapper.className = 'maplibre-popup-content';
            if (content instanceof HTMLElement) {
                wrapper.appendChild(content);
            } else {
                wrapper.innerHTML = content;
            }

            // Remove active class from previous marker
            if (state.currentPopupMarker) {
                state.currentPopupMarker.getElement().classList.remove('active');
            }

            // Create popup dynamically based on current screen size
            // On mobile: center popup on marker; on desktop: popup above marker
            const isMobile = window.innerWidth <= Constants.UI.MOBILE_BREAKPOINT;
            const popup = new maplibregl.Popup({
                closeButton: true,
                closeOnClick: true,
                maxWidth: 'none',
                anchor: isMobile ? 'center' : 'bottom',
                offset: isMobile ? [0, 0] : [0, -26]
            });

            // Handle popup close
            popup.on('close', () => {
                if (state.currentPopup === popup) {
                    const closedMarker = state.currentPopupMarker;
                    const closedLocationKey = markerObj.locationKey;

                    // Remove active class from marker
                    if (closedMarker) {
                        closedMarker.getElement().classList.remove('active');
                    }

                    state.currentPopup = null;
                    state.currentPopupMarker = null;

                    // Dispatch custom event for popup close
                    state.mapInstance.fire('popupclose', {
                        popup,
                        marker: closedMarker,
                        locationKey: closedLocationKey
                    });
                }
            });

            popup.setLngLat(lngLat)
                .setDOMContent(wrapper)
                .addTo(state.mapInstance);

            // Update markerObj reference
            markerObj.popup = popup;

            state.currentPopup = popup;
            state.currentPopupMarker = marker;

            // Add active class to current marker
            iconElement.classList.add('active');

            // Dispatch custom event for popup open
            state.mapInstance.fire('popupopen', { popup, marker, locationKey });
        });

        return marker;
    }

    /**
     * Remove a marker from the map
     * @param {maplibregl.Marker} marker - The marker to remove
     */
    function removeMarker(marker) {
        const index = state.markers.findIndex(m => m.marker === marker);
        if (index > -1) {
            const markerObj = state.markers[index];
            if (markerObj.popup) {
                markerObj.popup.remove();
            }
            marker.remove();
            state.markers.splice(index, 1);
        }
    }

    /**
     * Open popup for a specific marker
     * @param {maplibregl.Marker} marker - The marker to open popup for
     */
    function openMarkerPopup(marker) {
        const markerObj = state.markers.find(m => m.marker === marker);
        if (markerObj) {
            // Trigger click on marker element to open popup
            markerObj.marker.getElement().click();
        }
    }

    /**
     * Get the current open popup
     * @returns {maplibregl.Popup|null} The currently open popup or null
     */
    function getCurrentPopup() {
        return state.currentPopup;
    }

    /**
     * Get the marker associated with the current open popup
     * @returns {maplibregl.Marker|null} The marker with open popup or null
     */
    function getCurrentPopupMarker() {
        return state.currentPopupMarker;
    }

    /**
     * Get marker object by marker instance
     * @param {maplibregl.Marker} marker - The marker instance
     * @returns {Object|null} The marker object or null
     */
    function getMarkerObject(marker) {
        return state.markers.find(m => m.marker === marker) || null;
    }

    /**
     * Get the map instance
     * @returns {maplibregl.Map|null} The map instance
     */
    function getMap() {
        return state.mapInstance;
    }

    /**
     * Iterate over all markers
     * @param {Function} callback - Callback function(markerObj)
     */
    function eachMarker(callback) {
        state.markers.forEach(callback);
    }

    /**
     * Check if two rectangles overlap
     * @param {Object} rect1 - First rectangle {left, right, top, bottom}
     * @param {Object} rect2 - Second rectangle {left, right, top, bottom}
     * @returns {boolean} True if rectangles overlap
     */
    function rectsOverlap(rect1, rect2) {
        return !(rect1.right < rect2.left ||
                 rect1.left > rect2.right ||
                 rect1.bottom < rect2.top ||
                 rect1.top > rect2.bottom);
    }

    /**
     * Combined update for marker z-indices and label visibility.
     * Projects all marker positions once and uses the results for both operations,
     * avoiding redundant map.project() calls. Uses cached label dimensions to
     * avoid layout thrashing from DOM measurement.
     */
    function updateMarkerVisuals() {
        if (!state.mapInstance) return;

        const markers = state.markers;
        if (markers.length === 0) return;

        // --- Shared: Project all marker positions once ---
        const projected = markers.map(markerObj => ({
            markerObj,
            screenPos: state.mapInstance.project(markerObj.lngLat)
        }));

        // --- Z-Index Update ---
        const maxZIndex = 399; // Must stay below popup z-index (400)
        const viewportHeight = window.innerHeight;
        const offsetY = viewportHeight * 0.5; // Buffer offset (must match CSS)

        for (const { markerObj, screenPos } of projected) {
            const normalizedY = (screenPos.y - offsetY) / viewportHeight;
            const zIndex = Math.round(Math.max(0, Math.min(1, normalizedY)) * maxZIndex);
            markerObj.marker.getElement().style.zIndex = zIndex;
        }

        // --- Label Visibility ---
        const isMobile = window.innerWidth <= Constants.UI.MOBILE_BREAKPOINT;
        const densityRadius = isMobile ? 150 : 200;
        const maxLocalDensity = isMobile ? 4 : 6;

        const markerSize = 54;
        const markerRadius = markerSize / 2;
        const labelOffset = -6; // margin-left in CSS

        // Build screen positions with cached label dimensions (no DOM reads)
        const markerScreenPositions = projected.map(({ markerObj, screenPos }) => {
            const labelEl = markerObj.marker.getElement().querySelector('.marker-label');
            const labelWidth = markerObj.labelWidth || 0;
            const labelHeight = markerObj.labelHeight || 0;

            const labelRect = {
                left: screenPos.x + markerRadius + labelOffset,
                right: screenPos.x + markerRadius + labelOffset + labelWidth,
                top: screenPos.y - labelHeight / 2,
                bottom: screenPos.y + labelHeight / 2
            };

            return {
                markerObj,
                x: screenPos.x,
                y: screenPos.y,
                labelRect,
                labelEl
            };
        });

        // Build spatial grid for efficient local density calculation
        const cellSize = densityRadius;
        const grid = new Map();

        for (const pos of markerScreenPositions) {
            const cellX = Math.floor(pos.x / cellSize);
            const cellY = Math.floor(pos.y / cellSize);
            const cellKey = `${cellX},${cellY}`;
            if (!grid.has(cellKey)) {
                grid.set(cellKey, []);
            }
            grid.get(cellKey).push(pos);
        }

        // Calculate local density for each marker
        const densityRadiusSq = densityRadius * densityRadius;
        for (const pos of markerScreenPositions) {
            const cellX = Math.floor(pos.x / cellSize);
            const cellY = Math.floor(pos.y / cellSize);
            let neighborCount = 0;

            for (let dx = -1; dx <= 1; dx++) {
                for (let dy = -1; dy <= 1; dy++) {
                    const neighborKey = `${cellX + dx},${cellY + dy}`;
                    const cellMarkers = grid.get(neighborKey);
                    if (!cellMarkers) continue;

                    for (const other of cellMarkers) {
                        if (other === pos) continue;
                        const distSq = (pos.x - other.x) ** 2 + (pos.y - other.y) ** 2;
                        if (distSq <= densityRadiusSq) {
                            neighborCount++;
                        }
                    }
                }
            }
            pos.localDensity = neighborCount;
        }

        // Sort by local density (lowest first - sparse areas get priority)
        markerScreenPositions.sort((a, b) => a.localDensity - b.localDensity);

        const shownLabelRects = [];

        // First pass: hide all labels
        for (const pos of markerScreenPositions) {
            if (pos.labelEl) {
                pos.labelEl.classList.remove('visible');
            }
        }

        // Second pass: show labels in sparse areas that don't overlap
        for (const pos of markerScreenPositions) {
            if (!pos.labelEl) continue;

            if (pos.localDensity > maxLocalDensity) continue;

            let overlapsLabel = false;
            for (const shownRect of shownLabelRects) {
                if (rectsOverlap(pos.labelRect, shownRect)) {
                    overlapsLabel = true;
                    break;
                }
            }
            if (overlapsLabel) continue;

            pos.labelEl.classList.add('visible');
            shownLabelRects.push(pos.labelRect);
        }
    }

    /**
     * Re-measure and cache label dimensions for all markers.
     * Called on window resize to handle CSS breakpoint changes.
     */
    function invalidateLabelDimensionCache() {
        state.markers.forEach(markerObj => {
            const labelEl = markerObj.marker.getElement().querySelector('.marker-label');
            if (labelEl) {
                labelEl.classList.add('visible');
                markerObj.labelWidth = labelEl.offsetWidth;
                markerObj.labelHeight = labelEl.offsetHeight;
                labelEl.classList.remove('visible');
            }
        });
    }

    /**
     * Initialize marker visual updates and resize handling.
     * The moveend listener for ongoing updates is managed by script.js
     * to avoid redundant calls.
     */
    function enableZIndexUpdates() {
        if (!state.mapInstance) return;

        // Invalidate cached label dimensions on resize (handles CSS breakpoint changes)
        window.addEventListener('resize', Utils.throttle(() => {
            invalidateLabelDimensionCache();
        }, 500));

        // Initial update
        updateMarkerVisuals();
    }

    /**
     * Get the current map bounds with an optional buffer
     * Uses the map's native getBounds() and expands it proportionally in lat/lng space
     * @param {number} [bufferRatio=0.5] - Buffer as a ratio of viewport size (0.5 = 50% buffer on each side)
     * @returns {Object|null} Bounds object with north/south/east/west, or null if map not ready
     */
    function getBufferedBounds(bufferRatio = 0.5) {
        if (!state.mapInstance) return null;

        const bounds = state.mapInstance.getBounds();
        const ne = bounds.getNorthEast();
        const sw = bounds.getSouthWest();

        const latRange = ne.lat - sw.lat;
        const lngRange = ne.lng - sw.lng;

        const latBuffer = latRange * bufferRatio;
        const lngBuffer = lngRange * bufferRatio;

        return {
            north: ne.lat + latBuffer,
            south: sw.lat - latBuffer,
            east: ne.lng + lngBuffer,
            west: sw.lng - lngBuffer
        };
    }

    /**
     * Check if a coordinate is within given bounds
     * @param {number} lat - Latitude
     * @param {number} lng - Longitude
     * @param {Object} bounds - Bounds object with north, south, east, west
     * @returns {boolean} True if coordinate is within bounds
     */
    function isInBounds(lat, lng, bounds) {
        return lat <= bounds.north &&
               lat >= bounds.south &&
               lng <= bounds.east &&
               lng >= bounds.west;
    }

    /**
     * Get count of current markers
     * @returns {number} Number of markers currently on the map
     */
    function getMarkerCount() {
        return state.markers.length;
    }

    /**
     * Public API for MapManager
     * @public
     */
    return {
        init,
        clearMarkers,
        getMarkerColor,
        createMarkerIcon,
        addMarkerToMap,
        removeMarker,
        openMarkerPopup,
        getCurrentPopup,
        getCurrentPopupMarker,
        getMarkerObject,
        getMap,
        eachMarker,
        updateMarkerVisuals,
        enableZIndexUpdates,
        getBufferedBounds,
        isInBounds,
        getMarkerCount
    };
})();
