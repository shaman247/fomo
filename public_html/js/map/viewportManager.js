/**
 * ViewportManager Module
 *
 * Manages viewport calculations for the map including visible center,
 * filter panel dimensions, and viewport bounds adjustments.
 *
 * Features:
 * - Calculate visible center accounting for filter panel overlay
 * - Compute filter panel dimensions (responsive: desktop/mobile)
 * - Calculate viewport bounds for event visibility
 * - Update location distances from visible center
 * - Manage debug rectangle bounds for popup positioning
 *
 * @module ViewportManager
 */
const ViewportManager = (() => {
    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // App state reference (injected during init)
        appState: null,

        // Cached calculations
        visibleCenter: null,
        debugRectBounds: null,
        locationDistances: {}
    };

    // ========================================
    // FILTER PANEL DIMENSIONS
    // ========================================

    /**
     * Gets the dimensions of the filter panel overlay
     * Returns different values for desktop (left panel) vs mobile (top panel)
     * Uses hardcoded height during initial load to avoid measurement issues
     *
     * @param {boolean} isInitialLoad - Whether this is during initial app load
     * @returns {Object} Object with filterPanelWidth and filterPanelHeight
     */
    function getFilterPanelDimensions(isInitialLoad = false) {
        let filterPanelWidth = 0;
        let filterPanelHeight = 0;

        const filterPanel = document.getElementById('filter-panel');
        if (filterPanel) {
            if (window.innerWidth <= Constants.UI.MOBILE_BREAKPOINT) {
                // On mobile, panel covers top of screen
                // Use constant height during initial load to avoid incorrect measurements
                if (isInitialLoad) {
                    filterPanelHeight = Constants.UI.FILTER_PANEL_MOBILE_HEIGHT;
                } else {
                    filterPanelHeight = filterPanel.offsetHeight;
                }
            } else {
                // On desktop, panel covers left side of screen
                filterPanelWidth = filterPanel.offsetWidth;
            }
        }

        return { filterPanelWidth, filterPanelHeight };
    }

    // ========================================
    // VISIBLE CENTER CALCULATION
    // ========================================

    /**
     * Calculates the visible center of the map accounting for filter panel overlay
     * The visible center is offset from the map center based on panel dimensions
     * Returns a point that is 80% of the way between map center and edge of visible area
     *
     * @param {L.Map} map - Leaflet map instance
     * @param {boolean} [isInitialLoad=false] - Whether this is during initial load
     * @returns {L.LatLng|null} Visible center coordinates or null if map not ready
     */
    function calculateVisibleCenter(map, isInitialLoad = false) {
        if (!map) return null;

        const center = map.getCenter();
        const centerPoint = map.latLngToContainerPoint(center);

        // Get filter panel dimensions
        const { filterPanelWidth, filterPanelHeight } = getFilterPanelDimensions(isInitialLoad);

        // Calculate the visible center (80% of the way between map center and edge of visible area)
        const visibleCenterPoint = L.point(
            centerPoint.x + filterPanelWidth * 0.4,
            centerPoint.y + filterPanelHeight * 0.4
        );

        const visibleCenter = map.containerPointToLatLng(visibleCenterPoint);
        state.visibleCenter = visibleCenter;

        return visibleCenter;
    }

    /**
     * Gets the currently cached visible center
     * @returns {L.LatLng|null} Cached visible center or null
     */
    function getVisibleCenter() {
        return state.visibleCenter;
    }

    // ========================================
    // VIEWPORT BOUNDS CALCULATION
    // ========================================

    /**
     * Calculates viewport bounds and debug rectangle for popup positioning
     * The map container is 150% size, so getSize() returns enlarged size
     * We need 2/3 of that to get the actual visible area (100% / 150% = 2/3)
     *
     * @param {L.Map} map - Leaflet map instance
     * @param {boolean} [isInitialLoad=false] - Whether this is during initial load
     * @returns {Object} Object with bounds, debugRectBounds, visibleCenter
     */
    function calculateViewportBounds(map, isInitialLoad = false) {
        if (!map) return null;

        // Calculate bounds based on the actual visible viewport
        const containerSize = map.getSize();
        const viewportWidth = containerSize.x * (2/3);
        const viewportHeight = containerSize.y * (2/3);

        // Get filter panel dimensions
        const { filterPanelWidth, filterPanelHeight } = getFilterPanelDimensions(isInitialLoad);

        const center = map.getCenter();
        const centerPoint = map.latLngToContainerPoint(center);

        // Calculate the corners of the actual visible viewport
        const topLeft = L.point(
            centerPoint.x - viewportWidth / 2 + filterPanelWidth,
            centerPoint.y - viewportHeight / 2 + filterPanelHeight
        );
        const bottomRight = L.point(
            centerPoint.x + viewportWidth / 2,
            centerPoint.y + viewportHeight / 2
        );

        // Calculate visible center
        const visibleCenter = calculateVisibleCenter(map, isInitialLoad);

        // Calculate lat/lng bounds
        const southWest = map.containerPointToLatLng(L.point(topLeft.x, bottomRight.y));
        const northEast = map.containerPointToLatLng(L.point(bottomRight.x, topLeft.y));
        const bounds = L.latLngBounds(southWest, northEast);

        // Calculate 90% inset bounds for popup positioning
        const inset = 0.05; // 5% inset on each side = 90% of bounds
        const insetTopLeft = L.point(
            topLeft.x + (viewportWidth - filterPanelWidth) * inset,
            topLeft.y + (viewportHeight - filterPanelHeight) * inset
        );
        const insetBottomRight = L.point(
            bottomRight.x - viewportWidth * inset,
            bottomRight.y - (viewportHeight - filterPanelHeight) * inset
        );

        // Store debug rectangle bounds (in container point coordinates)
        const debugRectBounds = {
            top: insetTopLeft.y,
            bottom: insetBottomRight.y,
            left: insetTopLeft.x,
            right: insetBottomRight.x
        };

        state.debugRectBounds = debugRectBounds;

        return {
            bounds,
            debugRectBounds,
            visibleCenter
        };
    }

    /**
     * Gets the currently cached debug rectangle bounds
     * Used for popup positioning
     * @returns {Object|null} Debug rect bounds or null
     */
    function getDebugRectBounds() {
        return state.debugRectBounds;
    }

    // ========================================
    // DISTANCE CALCULATIONS
    // ========================================

    /**
     * Calculates and caches distances from visible center to all locations
     * Precomputed distances are used for efficient proximity-based search scoring
     *
     * @param {L.LatLng} visibleCenter - The visible center point
     * @param {Object} locationsByLatLng - Map of locationKey to location info
     * @returns {Object} Map of locationKey to distance in meters
     */
    function calculateLocationDistances(visibleCenter, locationsByLatLng) {
        if (!visibleCenter || !locationsByLatLng) return {};

        const distances = {};

        for (const locationKey in locationsByLatLng) {
            const [lat, lng] = locationKey.split(',').map(Number);
            distances[locationKey] = visibleCenter.distanceTo([lat, lng]);
        }

        state.locationDistances = distances;
        return distances;
    }

    /**
     * Gets the cached location distances
     * @returns {Object} Map of locationKey to distance
     */
    function getLocationDistances() {
        return state.locationDistances;
    }

    /**
     * Gets the distance for a specific location
     * @param {string} locationKey - Location key in "lat,lng" format
     * @returns {number|null} Distance in meters or null if not found
     */
    function getLocationDistance(locationKey) {
        return state.locationDistances[locationKey] || null;
    }

    // ========================================
    // MAP ADJUSTMENT
    // ========================================

    /**
     * Adjusts the map view so the visible center (accounting for filter panel)
     * ends up at the desired target coordinates
     *
     * @param {L.Map} map - Leaflet map instance
     * @param {L.LatLng} desiredVisibleCenter - Desired visible center coordinates
     * @param {boolean} [animate=false] - Whether to animate the pan
     */
    function adjustMapToVisibleCenter(map, desiredVisibleCenter, animate = false) {
        if (!map || !desiredVisibleCenter) return;

        const currentVisibleCenter = calculateVisibleCenter(map);
        if (!currentVisibleCenter) return;

        // Calculate the offset needed to move visible center to desired position
        const currentCenter = map.getCenter();
        const offsetLat = desiredVisibleCenter.lat - currentVisibleCenter.lat;
        const offsetLng = desiredVisibleCenter.lng - currentVisibleCenter.lng;

        // Apply the offset to the map center
        const adjustedMapCenter = L.latLng(
            currentCenter.lat + offsetLat,
            currentCenter.lng + offsetLng
        );

        map.panTo(adjustedMapCenter, { animate });
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the ViewportManager module
     * @param {Object} config - Configuration object
     * @param {Object} config.appState - Reference to app state
     */
    function init(config) {
        state.appState = config.appState;
    }

    /**
     * Updates all viewport-related calculations
     * Call this after map moves or filter panel size changes
     *
     * @param {L.Map} map - Leaflet map instance
     * @param {Object} locationsByLatLng - Map of locationKey to location info
     * @param {boolean} [isInitialLoad=false] - Whether this is during initial load
     * @returns {Object} Object with bounds, debugRectBounds, visibleCenter, locationDistances
     */
    function updateViewportCalculations(map, locationsByLatLng, isInitialLoad = false) {
        const viewportData = calculateViewportBounds(map, isInitialLoad);
        if (!viewportData) return null;

        const locationDistances = calculateLocationDistances(
            viewportData.visibleCenter,
            locationsByLatLng
        );

        return {
            ...viewportData,
            locationDistances
        };
    }

    // ========================================
    // POPUP POSITIONING
    // ========================================

    /**
     * Calculates the pan offset needed to fit a popup within the visible bounds
     * Returns the X and Y pixel offsets to pan the map by
     *
     * @param {L.Map} map - Leaflet map instance
     * @param {L.LatLng} popupLatLng - The lat/lng position of the popup anchor
     * @param {number} popupHeight - Height of the popup element in pixels
     * @param {number} popupWidth - Width of the popup element in pixels
     * @returns {Object|null} Object with panX and panY offsets, or null if no pan needed
     */
    function calculatePopupPanOffset(map, popupLatLng, popupHeight, popupWidth) {
        const debugRectBounds = state.debugRectBounds;
        if (!debugRectBounds) return null;

        // Get current popup position in container point coordinates
        const popupPoint = map.latLngToContainerPoint(popupLatLng);
        const popupTop = popupPoint.y - popupHeight;
        const popupBottom = popupPoint.y;
        const popupLeft = popupPoint.x - popupWidth / 2;
        const popupRight = popupPoint.x + popupWidth / 2;

        // Calculate if we need to pan (vertical and horizontal)
        let panX = 0;
        let panY = 0;

        // Check vertical bounds
        if (popupTop < debugRectBounds.top) {
            panY = debugRectBounds.top - popupTop;
        } else if (popupBottom > debugRectBounds.bottom) {
            panY = debugRectBounds.bottom - popupBottom;
        }

        // Check horizontal bounds
        if (popupLeft < debugRectBounds.left) {
            panX = debugRectBounds.left - popupLeft;
        } else if (popupRight > debugRectBounds.right) {
            panX = debugRectBounds.right - popupRight;
        }

        if (panX === 0 && panY === 0) {
            return null;
        }

        return { panX, panY };
    }

    // ========================================
    // DEBUG OVERLAY
    // ========================================

    /**
     * Updates the debug visualization overlay on the map
     * Shows viewport bounds rectangle and visible center marker
     *
     * @param {L.Map} map - Leaflet map instance
     * @param {L.LayerGroup} debugLayer - Layer group for debug visualization
     * @param {boolean} debugMode - Whether debug mode is enabled
     */
    function updateDebugOverlay(map, debugLayer, debugMode) {
        // Clear existing debug overlays
        if (debugLayer) {
            debugLayer.clearLayers();
        }

        if (!debugMode || !state.debugRectBounds || !state.visibleCenter) {
            return;
        }

        // Convert container point coordinates to lat/lng for the rectangle
        const topLeft = map.containerPointToLatLng(
            L.point(state.debugRectBounds.left, state.debugRectBounds.top)
        );
        const bottomRight = map.containerPointToLatLng(
            L.point(state.debugRectBounds.right, state.debugRectBounds.bottom)
        );

        // Draw the 90% inset bounds rectangle
        L.rectangle(
            [topLeft, bottomRight],
            {
                color: '#ff0000',
                weight: 2,
                fill: false,
                dashArray: '5, 5'
            }
        ).addTo(debugLayer);

        // Draw a marker at the visible center
        L.circleMarker(state.visibleCenter, {
            color: '#00ff00',
            fillColor: '#00ff00',
            fillOpacity: 0.8,
            radius: 8
        }).addTo(debugLayer);

        // Add a crosshair at the center
        const crosshairSize = 20; // pixels
        const centerPoint = map.latLngToContainerPoint(state.visibleCenter);

        const crosshairH1 = map.containerPointToLatLng(
            L.point(centerPoint.x - crosshairSize, centerPoint.y)
        );
        const crosshairH2 = map.containerPointToLatLng(
            L.point(centerPoint.x + crosshairSize, centerPoint.y)
        );
        const crosshairV1 = map.containerPointToLatLng(
            L.point(centerPoint.x, centerPoint.y - crosshairSize)
        );
        const crosshairV2 = map.containerPointToLatLng(
            L.point(centerPoint.x, centerPoint.y + crosshairSize)
        );

        L.polyline([crosshairH1, crosshairH2], {
            color: '#00ff00',
            weight: 2
        }).addTo(debugLayer);

        L.polyline([crosshairV1, crosshairV2], {
            color: '#00ff00',
            weight: 2
        }).addTo(debugLayer);
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Initialization
        init,

        // Filter panel dimensions
        getFilterPanelDimensions,

        // Visible center
        calculateVisibleCenter,
        getVisibleCenter,

        // Viewport bounds
        calculateViewportBounds,
        getDebugRectBounds,

        // Distance calculations
        calculateLocationDistances,
        getLocationDistances,
        getLocationDistance,

        // Map adjustments
        adjustMapToVisibleCenter,

        // Combined update
        updateViewportCalculations,

        // Popup positioning
        calculatePopupPanOffset,

        // Debug
        updateDebugOverlay
    };
})();
