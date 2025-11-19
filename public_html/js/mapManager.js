const MapManager = (() => {
    const state = {
        mapInstance: null,
        markersLayerInstance: null,
        tagColorsRef: null,
        markerColorsRef: null,
        openTooltipMarker: null,
    };

    function init(mapInstance, tagColors, markerColors) {
        state.mapInstance = mapInstance;
        state.tagColorsRef = tagColors;
        state.markerColorsRef = markerColors || {};

        state.markersLayerInstance = L.layerGroup().addTo(state.mapInstance);
        return { markersLayer: state.markersLayerInstance };
    }

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

    function removeMarker(marker) {
        if (state.markersLayerInstance && marker) {
            state.markersLayerInstance.removeLayer(marker);
        }
    }

    return {
        init,
        clearMarkers,
        getMarkerColor,
        createMarkerIcon,
        addMarkerToMap,
        removeMarker,
    };
})();