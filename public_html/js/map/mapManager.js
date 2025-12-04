/**
 * MapManager - Manages MapLibre GL map markers and their styling
 * Handles marker creation, icon generation, tooltips, and popups
 * @module MapManager
 */
const MapManager = (() => {
    /**
     * Internal state for MapManager
     * @private
     */
    const state = {
        mapInstance: null,
        markers: [],           // Array of {marker, popup, tooltip, locationKey}
        tagColorsRef: null,
        markerColorsRef: null,
        openTooltipMarker: null,
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
            if (markerObj.tooltip) {
                markerObj.tooltip.remove();
            }
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
     * Generates an SVG pin with an emoji overlay
     * @param {Object} locationInfo - Location information object
     * @param {string} locationInfo.emoji - Emoji to display on the marker
     * @returns {HTMLElement} DOM element for the marker
     */
    function createMarkerIcon(locationInfo) {
        const markerColor = getMarkerColor(locationInfo);
        const emoji = locationInfo.emoji;

        const el = document.createElement('div');
        el.className = 'custom-marker-icon';
        el.innerHTML = `
            <svg width=45 height=60 viewBox="0 0 28 35" xmlns="http://www.w3.org/2000/svg" class="marker-svg">
                <g transform="translate(0, 1)">
                    <path d="M14 0C7.37258 0 2 5.37258 2 12C2 21.056 14 32 14 32C14 32 26 21.056 26 12C26 5.37258 20.6274 0 14 0Z" fill="${markerColor}" stroke="var(--marker-stroke)" stroke-width="0.5"/>
                </g>
            </svg>
            <div class="marker-emoji">${emoji}</div>`;

        return el;
    }

    /**
     * Create a tooltip element for showing on hover
     * @param {string} text - Tooltip text
     * @returns {HTMLElement} Tooltip DOM element
     */
    function createTooltipElement(text) {
        const tooltip = document.createElement('div');
        tooltip.className = 'maplibre-tooltip';
        tooltip.textContent = text;
        return tooltip;
    }

    /**
     * Add a marker to the map with tooltip and popup
     * @param {Array<number>} lngLat - Marker coordinates [lng, lat] (MapLibre uses lng,lat order)
     * @param {HTMLElement} iconElement - Marker icon DOM element
     * @param {string} tooltipText - Text to display in tooltip
     * @param {Function} popupContentCallback - Function that returns popup content
     * @param {string} locationKey - Location key for reference
     * @returns {maplibregl.Marker|undefined} The created marker, or undefined if map not initialized
     */
    function addMarkerToMap(lngLat, iconElement, tooltipText, popupContentCallback, locationKey) {
        if (!state.mapInstance) return;

        // Create the marker with anchor at bottom center of the pin
        const marker = new maplibregl.Marker({
            element: iconElement,
            anchor: 'bottom'
        })
            .setLngLat(lngLat)
            .addTo(state.mapInstance);

        // Create tooltip (shown on hover)
        const tooltipEl = createTooltipElement(tooltipText);

        // Create popup (shown on click)
        const popup = new maplibregl.Popup({
            closeButton: true,
            closeOnClick: false,
            maxWidth: '340px',
            anchor: 'bottom',
            offset: [0, -55] // Offset up from marker
        });

        // Store marker info
        const markerObj = {
            marker,
            popup,
            tooltipEl,
            locationKey,
            popupContentCallback,
            lngLat
        };
        state.markers.push(markerObj);

        // Handle hover for tooltip
        iconElement.addEventListener('mouseenter', () => {
            // Don't show tooltip if popup is open for this marker
            if (state.currentPopupMarker === marker) return;

            // Close any other open tooltip
            if (state.openTooltipMarker && state.openTooltipMarker !== marker) {
                const prevMarkerObj = state.markers.find(m => m.marker === state.openTooltipMarker);
                if (prevMarkerObj && prevMarkerObj.tooltipEl.parentNode) {
                    prevMarkerObj.tooltipEl.remove();
                }
            }

            // Position and show tooltip
            const markerEl = marker.getElement();
            const rect = markerEl.getBoundingClientRect();
            const mapContainer = state.mapInstance.getContainer();
            const mapRect = mapContainer.getBoundingClientRect();

            tooltipEl.style.position = 'absolute';
            tooltipEl.style.left = `${rect.left - mapRect.left + rect.width / 2}px`;
            tooltipEl.style.top = `${rect.top - mapRect.top - 10}px`;
            tooltipEl.style.transform = 'translate(-50%, -100%)';

            mapContainer.appendChild(tooltipEl);
            state.openTooltipMarker = marker;
        });

        iconElement.addEventListener('mouseleave', () => {
            if (tooltipEl.parentNode) {
                tooltipEl.remove();
            }
            if (state.openTooltipMarker === marker) {
                state.openTooltipMarker = null;
            }
        });

        // Handle click for popup
        iconElement.addEventListener('click', (e) => {
            e.stopPropagation();

            // Remove tooltip if showing
            if (tooltipEl.parentNode) {
                tooltipEl.remove();
            }

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

            popup.setLngLat(lngLat)
                .setDOMContent(wrapper)
                .addTo(state.mapInstance);

            state.currentPopup = popup;
            state.currentPopupMarker = marker;

            // Dispatch custom event for popup open
            state.mapInstance.fire('popupopen', { popup, marker, locationKey });
        });

        // Handle popup close
        popup.on('close', () => {
            if (state.currentPopup === popup) {
                const closedMarker = state.currentPopupMarker;
                const closedLocationKey = markerObj.locationKey;
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
            if (markerObj.tooltipEl && markerObj.tooltipEl.parentNode) {
                markerObj.tooltipEl.remove();
            }
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
        eachMarker
    };
})();
