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
    // HELPER FUNCTIONS
    // ========================================

    /**
     * Calculate distance between two lat/lng points using Haversine formula
     * @param {Object} point1 - First point {lat, lng}
     * @param {Object} point2 - Second point {lat, lng}
     * @returns {number} Distance in meters
     */
    function calculateDistance(point1, point2) {
        const R = 6371000; // Earth's radius in meters
        const lat1 = point1.lat * Math.PI / 180;
        const lat2 = point2.lat * Math.PI / 180;
        const deltaLat = (point2.lat - point1.lat) * Math.PI / 180;
        const deltaLng = (point2.lng - point1.lng) * Math.PI / 180;

        const a = Math.sin(deltaLat / 2) * Math.sin(deltaLat / 2) +
            Math.cos(lat1) * Math.cos(lat2) *
            Math.sin(deltaLng / 2) * Math.sin(deltaLng / 2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

        return R * c;
    }

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
     * @param {maplibregl.Map} map - MapLibre map instance
     * @param {boolean} [isInitialLoad=false] - Whether this is during initial load
     * @returns {Object|null} Visible center coordinates {lat, lng} or null if map not ready
     */
    function calculateVisibleCenter(map, isInitialLoad = false) {
        if (!map) return null;

        const center = map.getCenter();
        const container = map.getContainer();
        const centerPoint = map.project(center);

        // Get filter panel dimensions
        const { filterPanelWidth, filterPanelHeight } = getFilterPanelDimensions(isInitialLoad);

        // Calculate the visible center (80% of the way between map center and edge of visible area)
        const visibleCenterPoint = {
            x: centerPoint.x + filterPanelWidth * 0.4,
            y: centerPoint.y + filterPanelHeight * 0.4
        };

        const visibleCenter = map.unproject([visibleCenterPoint.x, visibleCenterPoint.y]);
        state.visibleCenter = { lat: visibleCenter.lat, lng: visibleCenter.lng };

        return state.visibleCenter;
    }

    /**
     * Gets the currently cached visible center
     * @returns {Object|null} Cached visible center {lat, lng} or null
     */
    function getVisibleCenter() {
        return state.visibleCenter;
    }

    // ========================================
    // VIEWPORT BOUNDS CALCULATION
    // ========================================

    /**
     * Check if a point is inside a quadrilateral using ray casting algorithm
     * @param {Object} point - Point to check {lat, lng}
     * @param {Array} quad - Array of 4 corner points [{lat, lng}, ...]
     * @returns {boolean} True if point is inside the quadrilateral
     */
    function isPointInQuadrilateral(point, quad) {
        const x = point.lng;
        const y = point.lat;
        let inside = false;

        for (let i = 0, j = quad.length - 1; i < quad.length; j = i++) {
            const xi = quad[i].lng, yi = quad[i].lat;
            const xj = quad[j].lng, yj = quad[j].lat;

            if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) {
                inside = !inside;
            }
        }

        return inside;
    }

    /**
     * Calculates viewport bounds and debug rectangle for popup positioning
     * For rotated/pitched maps, uses a quadrilateral for accurate visibility checks
     *
     * @param {maplibregl.Map} map - MapLibre map instance
     * @param {boolean} [isInitialLoad=false] - Whether this is during initial load
     * @returns {Object} Object with bounds, debugRectBounds, visibleCenter
     */
    function calculateViewportBounds(map, isInitialLoad = false) {
        if (!map) return null;

        const container = map.getContainer();
        const viewportWidth = container.offsetWidth;
        const viewportHeight = container.offsetHeight;

        // Get filter panel dimensions
        const { filterPanelWidth, filterPanelHeight } = getFilterPanelDimensions(isInitialLoad);

        // Calculate the corners of the actual visible viewport in pixels
        const topLeftPx = { x: filterPanelWidth, y: filterPanelHeight };
        const topRightPx = { x: viewportWidth, y: filterPanelHeight };
        const bottomRightPx = { x: viewportWidth, y: viewportHeight };
        const bottomLeftPx = { x: filterPanelWidth, y: viewportHeight };

        // Calculate visible center
        const visibleCenter = calculateVisibleCenter(map, isInitialLoad);

        // Get lat/lng for all four corners (handles rotation and pitch)
        const topLeft = map.unproject([topLeftPx.x, topLeftPx.y]);
        const topRight = map.unproject([topRightPx.x, topRightPx.y]);
        const bottomRight = map.unproject([bottomRightPx.x, bottomRightPx.y]);
        const bottomLeft = map.unproject([bottomLeftPx.x, bottomLeftPx.y]);

        // Create quadrilateral array for point-in-polygon check
        const quadrilateral = [
            { lat: topLeft.lat, lng: topLeft.lng },
            { lat: topRight.lat, lng: topRight.lng },
            { lat: bottomRight.lat, lng: bottomRight.lng },
            { lat: bottomLeft.lat, lng: bottomLeft.lng }
        ];

        // Create bounds object with quadrilateral-based contains check
        const bounds = {
            // These are approximate for compatibility - use the actual corners for precision
            getSouthWest: () => ({
                lat: Math.min(topLeft.lat, topRight.lat, bottomRight.lat, bottomLeft.lat),
                lng: Math.min(topLeft.lng, topRight.lng, bottomRight.lng, bottomLeft.lng)
            }),
            getNorthEast: () => ({
                lat: Math.max(topLeft.lat, topRight.lat, bottomRight.lat, bottomLeft.lat),
                lng: Math.max(topLeft.lng, topRight.lng, bottomRight.lng, bottomLeft.lng)
            }),
            // Use quadrilateral check for accurate visibility with rotation/pitch
            contains: (point) => {
                const lat = Array.isArray(point) ? point[0] : point.lat;
                const lng = Array.isArray(point) ? point[1] : point.lng;
                return isPointInQuadrilateral({ lat, lng }, quadrilateral);
            },
            // Expose the quadrilateral for debugging
            getQuadrilateral: () => quadrilateral
        };

        // Calculate 90% inset bounds for popup positioning (in screen pixels - still a rectangle)
        const inset = 0.05; // 5% inset on each side = 90% of bounds
        const effectiveWidth = viewportWidth - filterPanelWidth;
        const effectiveHeight = viewportHeight - filterPanelHeight;

        const insetTopLeft = {
            x: topLeftPx.x + effectiveWidth * inset,
            y: topLeftPx.y + effectiveHeight * inset
        };
        const insetBottomRight = {
            x: bottomRightPx.x - effectiveWidth * inset,
            y: bottomRightPx.y - effectiveHeight * inset
        };

        // Store debug rectangle bounds (in pixel coordinates)
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
     * @param {Object} visibleCenter - The visible center point {lat, lng}
     * @param {Object} locationsByLatLng - Map of locationKey to location info
     * @returns {Object} Map of locationKey to distance in meters
     */
    function calculateLocationDistances(visibleCenter, locationsByLatLng) {
        if (!visibleCenter || !locationsByLatLng) return {};

        const distances = {};

        for (const locationKey in locationsByLatLng) {
            const [lat, lng] = locationKey.split(',').map(Number);
            distances[locationKey] = calculateDistance(visibleCenter, { lat, lng });
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
     * @param {maplibregl.Map} map - MapLibre map instance
     * @param {Object} desiredVisibleCenter - Desired visible center {lat, lng}
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
        const adjustedMapCenter = {
            lat: currentCenter.lat + offsetLat,
            lng: currentCenter.lng + offsetLng
        };

        if (animate) {
            map.panTo([adjustedMapCenter.lng, adjustedMapCenter.lat]);
        } else {
            map.jumpTo({ center: [adjustedMapCenter.lng, adjustedMapCenter.lat] });
        }
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
     * @param {maplibregl.Map} map - MapLibre map instance
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
     * @param {maplibregl.Map} map - MapLibre map instance
     * @param {Object} popupLngLat - The lng/lat position of the popup anchor (marker position)
     * @param {number} popupHeight - Height of the popup element in pixels
     * @param {number} popupWidth - Width of the popup element in pixels
     * @returns {Object|null} Object with panX and panY offsets, or null if no pan needed
     */
    function calculatePopupPanOffset(map, popupLngLat, popupHeight, popupWidth) {
        const debugRectBounds = state.debugRectBounds;
        if (!debugRectBounds) return null;

        // Get marker position in pixel coordinates
        const markerPoint = map.project(popupLngLat);

        // The popup has an offset of [0, -55] from the marker (see mapManager.js)
        // and anchor is 'bottom', so the popup bottom is at markerPoint.y - 55
        const popupOffset = 55;
        const popupBottom = markerPoint.y - popupOffset;
        const popupTop = popupBottom - popupHeight;
        const popupLeft = markerPoint.x - popupWidth / 2;
        const popupRight = markerPoint.x + popupWidth / 2;

        // Add some padding for visual comfort
        const padding = 10;

        // Calculate if we need to pan (vertical and horizontal)
        let panX = 0;
        let panY = 0;

        // Check vertical bounds
        // Use the more restrictive bound: either debugRectBounds.top or absolute screen top (0)
        // This handles pitched maps where markers near horizon could cause popup to go off-screen
        const effectiveTop = Math.max(debugRectBounds.top, 0);
        if (popupTop < effectiveTop + padding) {
            panY = (effectiveTop + padding) - popupTop;
        } else if (popupBottom > debugRectBounds.bottom - padding) {
            panY = (debugRectBounds.bottom - padding) - popupBottom;
        }

        // Check horizontal bounds
        if (popupLeft < debugRectBounds.left + padding) {
            panX = (debugRectBounds.left + padding) - popupLeft;
        } else if (popupRight > debugRectBounds.right - padding) {
            panX = (debugRectBounds.right - padding) - popupRight;
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
     * Note: For MapLibre, we use DOM elements for debug visualization
     *
     * @param {maplibregl.Map} map - MapLibre map instance
     * @param {HTMLElement} debugContainer - Container element for debug visualization
     * @param {boolean} debugMode - Whether debug mode is enabled
     */
    function updateDebugOverlay(map, debugContainer, debugMode) {
        // Clear existing debug overlays
        if (debugContainer) {
            debugContainer.innerHTML = '';
        }

        if (!debugMode || !state.debugRectBounds || !state.visibleCenter || !debugContainer) {
            return;
        }

        const bounds = state.debugRectBounds;

        // Create debug rectangle using CSS
        const rect = document.createElement('div');
        rect.style.position = 'absolute';
        rect.style.left = `${bounds.left}px`;
        rect.style.top = `${bounds.top}px`;
        rect.style.width = `${bounds.right - bounds.left}px`;
        rect.style.height = `${bounds.bottom - bounds.top}px`;
        rect.style.border = '2px dashed #ff0000';
        rect.style.pointerEvents = 'none';
        rect.style.zIndex = '1000';
        debugContainer.appendChild(rect);

        // Create visible center marker
        const centerPoint = map.project([state.visibleCenter.lng, state.visibleCenter.lat]);
        const centerMarker = document.createElement('div');
        centerMarker.style.position = 'absolute';
        centerMarker.style.left = `${centerPoint.x - 8}px`;
        centerMarker.style.top = `${centerPoint.y - 8}px`;
        centerMarker.style.width = '16px';
        centerMarker.style.height = '16px';
        centerMarker.style.backgroundColor = '#00ff00';
        centerMarker.style.borderRadius = '50%';
        centerMarker.style.pointerEvents = 'none';
        centerMarker.style.zIndex = '1000';
        debugContainer.appendChild(centerMarker);

        // Create crosshair
        const crosshairH = document.createElement('div');
        crosshairH.style.position = 'absolute';
        crosshairH.style.left = `${centerPoint.x - 20}px`;
        crosshairH.style.top = `${centerPoint.y - 1}px`;
        crosshairH.style.width = '40px';
        crosshairH.style.height = '2px';
        crosshairH.style.backgroundColor = '#00ff00';
        crosshairH.style.pointerEvents = 'none';
        crosshairH.style.zIndex = '1000';
        debugContainer.appendChild(crosshairH);

        const crosshairV = document.createElement('div');
        crosshairV.style.position = 'absolute';
        crosshairV.style.left = `${centerPoint.x - 1}px`;
        crosshairV.style.top = `${centerPoint.y - 20}px`;
        crosshairV.style.width = '2px';
        crosshairV.style.height = '40px';
        crosshairV.style.backgroundColor = '#00ff00';
        crosshairV.style.pointerEvents = 'none';
        crosshairV.style.zIndex = '1000';
        debugContainer.appendChild(crosshairV);
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
