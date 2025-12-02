/**
 * MapManager - Manages Leaflet map markers and their styling
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
        markersLayerInstance: null,
        tagColorsRef: null,
        markerColorsRef: null,
        openTooltipMarker: null,
    };

    /**
     * Initialize MapManager with map instance and color references
     * Creates and returns the markers layer group
     * @param {L.Map} mapInstance - Leaflet map instance
     * @param {Object} tagColors - Tag to color mapping (currently unused)
     * @param {Object} markerColors - Emoji to marker color mapping
     * @returns {Object} Object containing markersLayer reference
     */
    function init(mapInstance, tagColors, markerColors) {
        state.mapInstance = mapInstance;
        state.tagColorsRef = tagColors;
        state.markerColorsRef = markerColors || {};

        state.markersLayerInstance = L.layerGroup().addTo(state.mapInstance);
        return { markersLayer: state.markersLayerInstance };
    }

    /**
     * Clear all markers from the map, optionally sparing one marker
     * Useful for updating markers while preserving an open popup
     * @param {L.Marker|null} [markerToSpare=null] - Marker to keep on the map
     */
    function clearMarkers(markerToSpare = null) {
        if (state.markersLayerInstance) {
            if (!markerToSpare) {
                state.markersLayerInstance.clearLayers();
                return;
            }
            const layersToRemove = [];
            state.markersLayerInstance.eachLayer(layer => {
                if (layer !== markerToSpare) {
                    layersToRemove.push(layer);
                }
            });
            layersToRemove.forEach(layer => state.markersLayerInstance.removeLayer(layer));
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
     * Create a custom Leaflet divIcon for a map marker
     * Generates an SVG pin with an emoji overlay
     * @param {Object} locationInfo - Location information object
     * @param {string} locationInfo.emoji - Emoji to display on the marker
     * @returns {L.DivIcon} Leaflet divIcon for the marker
     */
    function createMarkerIcon(locationInfo) {
        const baseWidth = 45;
        const baseHeight = 60;
        const iconSize = [baseWidth, baseHeight];
        const markerColor = getMarkerColor(locationInfo);
        const emoji = locationInfo.emoji;

        const iconHtml = `
            <svg width=45 height=60 viewBox="0 0 28 35" xmlns="http://www.w3.org/2000/svg" class="marker-svg">
                <g transform="translate(0, 1)">
                    <path d="M14 0C7.37258 0 2 5.37258 2 12C2 21.056 14 32 14 32C14 32 26 21.056 26 12C26 5.37258 20.6274 0 14 0Z" fill="${markerColor}" stroke="var(--marker-stroke)" stroke-width="0.5"/>
                </g>
            </svg>
            <div class="marker-emoji">${emoji}</div>`;

        return L.divIcon({
            className: 'custom-marker-icon',
            html: iconHtml,
            iconSize: iconSize,
            iconAnchor: [iconSize[0] / 2, iconSize[1] - 3],
        });
    }

    /**
     * Add a marker to the map with tooltip and popup
     * Manages tooltip state to ensure only one tooltip is open at a time
     * @param {L.LatLng|Array<number>} latLng - Marker coordinates [lat, lng]
     * @param {L.DivIcon} icon - Marker icon
     * @param {string} tooltipText - Text to display in tooltip
     * @param {Function} popupContentCallback - Function that returns popup content
     * @returns {L.Marker|undefined} The created marker, or undefined if markers layer not initialized
     */
    function addMarkerToMap(latLng, icon, tooltipText, popupContentCallback) {
        if (!state.markersLayerInstance) return;

        const markerOptions = { icon };

        const marker = L.marker(latLng, markerOptions);

        marker.bindTooltip(tooltipText);
        marker.bindPopup(popupContentCallback, {
            autoPan: false, // Disable default autopan; we handle it manually
            keepInView: false,
        });

        marker.on('tooltipopen', (e) => {
            if (state.openTooltipMarker && state.openTooltipMarker !== e.target) {
                state.openTooltipMarker.closeTooltip();
            }
            state.openTooltipMarker = e.target;
        });

        marker.on('popupopen', () => {
            if (state.openTooltipMarker) {
                state.openTooltipMarker.closeTooltip();
                // The tooltipclose event will set openTooltipMarker to null
            }
        });

        marker.on('tooltipclose', (e) => {
            // When a tooltip is closed, nullify the reference if it was the one we were tracking.
            if (state.openTooltipMarker === e.target) {
                state.openTooltipMarker = null;
            }
        });

        state.markersLayerInstance.addLayer(marker);
        return marker;
    }

    /**
     * Remove a marker from the map
     * @param {L.Marker} marker - The marker to remove
     */
    function removeMarker(marker) {
        if (state.markersLayerInstance && marker) {
            state.markersLayerInstance.removeLayer(marker);
        }
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
    };
})();