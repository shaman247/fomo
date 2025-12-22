/**
 * MarkerController Module
 *
 * Manages the lifecycle of map markers including creation, updating, and removal.
 * Handles marker display logic, popup callbacks, and marker limit enforcement.
 *
 * Features:
 * - Creates markers for locations with events
 * - Generates popup content callbacks dynamically
 * - Enforces marker display limits
 * - Manages marker preservation during updates
 * - Coordinates with MapManager for marker operations
 *
 * @module MarkerController
 */
const MarkerController = (() => {
    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // App state reference (injected during init)
        appState: null,
        config: null,

        // Provider objects (injected during init)
        filterProvider: null,   // { getTagStates, getSelectedDates }
        eventProvider: null,    // { getForceDisplayEventId, setForceDisplayEventId }

        // Viewport culling state
        allFilteredLocations: {},  // All locations that pass filters (may not all have markers)
        viewportUpdatePending: false,  // Debounce flag for viewport updates
        lastViewportBounds: null  // Last bounds used for marker rendering
    };

    // ========================================
    // MARKER DISPLAY
    // ========================================

    /**
     * Creates a popup content callback for a marker at a given location
     * The callback is executed when the popup is opened
     *
     * @param {string} locationKey - Location key in "lat,lng" format
     * @returns {Function} Callback that generates popup HTML
     */
    function createPopupContentCallback(locationKey) {
        return () => {
            const selectedDates = state.filterProvider.getSelectedDates();
            const currentPopupFilters = {
                sliderStartDate: selectedDates[0],
                sliderEndDate: selectedDates[1],
                tagStates: state.filterProvider.getTagStates()
            };

            const eventsAtLocationInDateRange = state.appState.eventsByLatLngInDateRange[locationKey] || [];
            const filterFunctions = {
                isEventMatchingTagFilters: (event, tagStates) => FilterManager.isEventMatchingTagFilters(event, tagStates)
            };

            // Handle forced display event (e.g., from search)
            let eventsToDisplay = eventsAtLocationInDateRange;
            const forceDisplayEventId = state.eventProvider.getForceDisplayEventId();
            if (forceDisplayEventId) {
                const isForcedEventPresent = eventsToDisplay.some(e => e.id === forceDisplayEventId);
                if (!isForcedEventPresent) {
                    const forcedEvent = state.appState.eventsById[forceDisplayEventId];
                    if (forcedEvent && forcedEvent.locationKey === locationKey) {
                        eventsToDisplay = [...eventsToDisplay, forcedEvent];
                    }
                }
            }

            const locationInfo = state.appState.locationsByLatLng[locationKey];
            return UIManager.createLocationPopupContent(
                locationInfo,
                eventsToDisplay,
                currentPopupFilters,
                state.appState.geotagsSet,
                filterFunctions,
                forceDisplayEventId,
                selectedDates[0]
            );
        };
    }

    /**
     * Creates a marker for a location and adds it to the map
     * @param {string} locationKey - Location key in "lat,lng" format
     * @param {Array} eventsAtLocation - Events at this location
     * @returns {maplibregl.Marker|null} The created marker or null
     * @private
     */
    function createMarkerForLocation(locationKey, eventsAtLocation) {
        // Parse location coordinates
        const [lat, lng] = locationKey.split(',').map(Number);
        if (lat === 0 && lng === 0) return null;

        // Get location info
        const locationInfo = state.appState.locationsByLatLng[locationKey];
        if (!locationInfo) return null;

        // Create marker icon element
        const locationName = locationInfo.name;
        const customIconElement = MapManager.createMarkerIcon(locationInfo);

        // Create popup content callback
        const popupContentCallback = createPopupContentCallback(locationKey);

        // Add marker to map (MapLibre uses [lng, lat] order)
        const newMarker = MapManager.addMarkerToMap(
            [lng, lat],
            customIconElement,
            locationName,
            popupContentCallback,
            locationKey
        );

        // Auto-open popup if this location contains the forced display event
        const forceDisplayEventId = state.eventProvider.getForceDisplayEventId();
        if (forceDisplayEventId && newMarker) {
            if (eventsAtLocation.some(e => e.id === forceDisplayEventId)) {
                MapManager.openMarkerPopup(newMarker);
            }
        }

        return newMarker;
    }

    /**
     * Displays markers for locations with matching events
     * Uses viewport-based culling to only render markers within the visible area
     * This significantly improves panning performance with many markers
     *
     * @param {Object} locationsToDisplay - Object mapping locationKey to array of events
     * @param {maplibregl.Marker} [markerToKeep=null] - Marker to preserve (e.g., one with open popup)
     */
    function displayEventsOnMap(locationsToDisplay, markerToKeep = null) {
        // Store all filtered locations for viewport-based updates
        state.allFilteredLocations = locationsToDisplay;

        let openMarkerLocationKey = null;
        if (markerToKeep) {
            const markerObj = MapManager.getMarkerObject(markerToKeep);
            if (markerObj) {
                openMarkerLocationKey = markerObj.locationKey;
            }
        }

        MapManager.clearMarkers(markerToKeep);

        // Get buffered viewport bounds for smoother panning
        const bounds = MapManager.getBufferedBounds(0.5);
        state.lastViewportBounds = bounds;

        let visibleLocationCount = markerToKeep ? 1 : 0;

        for (const locationKey in locationsToDisplay) {
            // Skip the marker that's being kept open
            if (locationKey === openMarkerLocationKey) {
                continue;
            }

            // Enforce marker display limit
            if (visibleLocationCount >= Constants.UI.MAX_MARKERS) {
                console.warn(`Marker display limit (${Constants.UI.MAX_MARKERS}) reached.`);
                break;
            }

            const eventsAtLocation = locationsToDisplay[locationKey];
            if (eventsAtLocation.length === 0) continue;

            // Parse location coordinates for viewport check
            const [lat, lng] = locationKey.split(',').map(Number);
            if (lat === 0 && lng === 0) continue;

            // Skip locations outside the buffered viewport
            if (bounds && !MapManager.isInBounds(lat, lng, bounds)) {
                continue;
            }

            visibleLocationCount++;

            createMarkerForLocation(locationKey, eventsAtLocation);
        }

        // Update label visibility based on marker density
        MapManager.updateLabelVisibility();
    }

    /**
     * Updates markers based on current viewport
     * Called on map move/zoom to add markers entering viewport and remove those leaving
     * Uses debouncing to prevent excessive updates during rapid panning
     */
    function updateMarkersForViewport() {
        // Skip if no filtered locations or update already pending
        if (!state.allFilteredLocations || Object.keys(state.allFilteredLocations).length === 0) {
            return;
        }

        // Get current buffered bounds
        const bounds = MapManager.getBufferedBounds(0.5);
        if (!bounds) return;

        // Track which location keys currently have markers
        const existingMarkerKeys = new Set();
        MapManager.eachMarker(markerObj => {
            existingMarkerKeys.add(markerObj.locationKey);
        });

        // Find the open popup marker's location key (if any)
        let openMarkerLocationKey = null;
        const openMarker = MapManager.getCurrentPopupMarker();
        if (openMarker) {
            const markerObj = MapManager.getMarkerObject(openMarker);
            if (markerObj) {
                openMarkerLocationKey = markerObj.locationKey;
            }
        }

        // Collect markers to remove (outside viewport, except open popup)
        const markersToRemove = [];
        MapManager.eachMarker(markerObj => {
            // Never remove the marker with open popup
            if (markerObj.locationKey === openMarkerLocationKey) return;

            const [lat, lng] = markerObj.locationKey.split(',').map(Number);
            // Use a larger buffer for removal to prevent flickering
            const removeBounds = MapManager.getBufferedBounds(1.0);
            if (removeBounds && !MapManager.isInBounds(lat, lng, removeBounds)) {
                markersToRemove.push(markerObj.marker);
            }
        });

        // Remove markers outside viewport
        markersToRemove.forEach(marker => {
            MapManager.removeMarker(marker);
        });

        // Update existing marker keys after removal
        existingMarkerKeys.clear();
        MapManager.eachMarker(markerObj => {
            existingMarkerKeys.add(markerObj.locationKey);
        });

        // Add markers for locations now in viewport
        let addedCount = 0;
        const currentMarkerCount = MapManager.getMarkerCount();
        const maxToAdd = Constants.UI.MAX_MARKERS - currentMarkerCount;

        for (const locationKey in state.allFilteredLocations) {
            // Skip if already has a marker
            if (existingMarkerKeys.has(locationKey)) continue;

            // Enforce marker limit
            if (addedCount >= maxToAdd) break;

            const eventsAtLocation = state.allFilteredLocations[locationKey];
            if (eventsAtLocation.length === 0) continue;

            const [lat, lng] = locationKey.split(',').map(Number);
            if (lat === 0 && lng === 0) continue;

            // Only add if within viewport bounds
            if (MapManager.isInBounds(lat, lng, bounds)) {
                createMarkerForLocation(locationKey, eventsAtLocation);
                addedCount++;
            }
        }

        state.lastViewportBounds = bounds;

        // Update label visibility if markers were added or removed
        if (addedCount > 0 || markersToRemove.length > 0) {
            MapManager.updateLabelVisibility();
        }
    }

    /**
     * Updates the content of an open popup with current filters
     * Used when filters change while a popup is open
     *
     * @param {maplibregl.Popup} openPopup - The open popup to update
     * @returns {boolean} True if popup was updated, false otherwise
     */
    function updateOpenPopupContent(openPopup) {
        if (!openPopup) return false;

        const marker = MapManager.getCurrentPopupMarker();
        if (!marker) return false;

        const markerObj = MapManager.getMarkerObject(marker);
        if (!markerObj) return false;

        const locationKey = markerObj.locationKey;
        const locationInfo = state.appState.locationsByLatLng[locationKey];
        const eventsAtLocationInDateRange = state.appState.eventsByLatLngInDateRange[locationKey] || [];

        const selectedDates = state.filterProvider.getSelectedDates();
        const currentPopupFilters = {
            sliderStartDate: selectedDates[0],
            sliderEndDate: selectedDates[1],
            tagStates: state.filterProvider.getTagStates()
        };

        const filterFunctions = {
            isEventMatchingTagFilters: (event, tagStates) => FilterManager.isEventMatchingTagFilters(event, tagStates)
        };

        // Handle forced display event
        let eventsToDisplay = eventsAtLocationInDateRange;
        const forceDisplayEventId = state.eventProvider.getForceDisplayEventId();
        if (forceDisplayEventId) {
            const isForcedEventPresent = eventsToDisplay.some(e => e.id === forceDisplayEventId);
            if (!isForcedEventPresent) {
                const forcedEvent = state.appState.eventsById[forceDisplayEventId];
                if (forcedEvent && forcedEvent.locationKey === locationKey) {
                    eventsToDisplay = [...eventsToDisplay, forcedEvent];
                }
            }
        }

        const newContent = UIManager.createLocationPopupContent(
            locationInfo,
            eventsToDisplay,
            currentPopupFilters,
            state.appState.geotagsSet,
            filterFunctions,
            forceDisplayEventId,
            selectedDates[0]
        );

        // Update popup content
        const wrapper = document.createElement('div');
        wrapper.className = 'maplibre-popup-content';
        if (newContent instanceof HTMLElement) {
            wrapper.appendChild(newContent);
        } else {
            wrapper.innerHTML = newContent;
        }
        openPopup.setDOMContent(wrapper);

        // Clear forced display after updating
        state.eventProvider.setForceDisplayEventId(null);

        return true;
    }

    /**
     * Finds the currently open popup and marker if any
     *
     * @returns {Object|null} Object with {popup, marker} or null if no popup is open
     */
    function findOpenPopup() {
        const popup = MapManager.getCurrentPopup();
        const marker = MapManager.getCurrentPopupMarker();

        return popup ? { popup, marker } : null;
    }

    /**
     * Checks if a location has matching events based on current tag filters
     * Used to determine if a marker should remain visible after popup close
     *
     * @param {string} locationKey - Location key in "lat,lng" format
     * @returns {boolean} True if location has at least one matching event
     */
    function hasMatchingEvents(locationKey) {
        const eventsAtLocation = state.appState.eventsByLatLngInDateRange[locationKey] || [];
        const currentTagStates = state.filterProvider.getTagStates();

        return eventsAtLocation.some(event =>
            FilterManager.isEventMatchingTagFilters(event, currentTagStates)
        );
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the MarkerController module
     *
     * @param {Object} config - Configuration object
     * @param {Object} config.appState - Reference to app state
     * @param {Object} config.config - App configuration
     * @param {Object} config.filterProvider - Provider for filter-related state
     * @param {Function} config.filterProvider.getTagStates - Function to get current tag states
     * @param {Function} config.filterProvider.getSelectedDates - Function to get selected date range
     * @param {Object} config.eventProvider - Provider for event-related state
     * @param {Function} config.eventProvider.getForceDisplayEventId - Function to get forced display event ID
     * @param {Function} config.eventProvider.setForceDisplayEventId - Function to set forced display event ID
     */
    function init(config) {
        state.appState = config.appState;
        state.config = config.config;
        state.filterProvider = config.filterProvider;
        state.eventProvider = config.eventProvider;
    }

    /**
     * Fly to a location on the map and open its popup
     * Creates a temporary marker if one doesn't exist at that location
     *
     * @param {number} lat - Latitude
     * @param {number} lng - Longitude
     * @param {string|null} [eventIdToForce=null] - Event ID to force display in popup
     */
    function flyToLocationAndOpenPopup(lat, lng, eventIdToForce = null) {
        if (state.eventProvider && state.eventProvider.setForceDisplayEventId) {
            state.eventProvider.setForceDisplayEventId(eventIdToForce);
        }

        const locationsByLatLng = state.appState.locationsByLatLng;

        // Find and open marker popup directly
        // Our popup positioning logic in script.js will handle any necessary panning
        let markerFound = false;
        MapManager.eachMarker(markerObj => {
            const markerLngLat = markerObj.marker.getLngLat();
            if (markerLngLat.lat === lat && markerLngLat.lng === lng) {
                MapManager.openMarkerPopup(markerObj.marker);
                markerFound = true;
            }
        });

        if (!markerFound) {
            // If no marker was found (e.g., it was filtered out), create it temporarily
            const locationKey = `${lat},${lng}`;
            const locationInfo = locationsByLatLng[locationKey];
            if (!locationInfo) {
                console.error("No location info found for", locationKey);
                return;
            }

            const customIconElement = MapManager.createMarkerIcon(locationInfo);
            const popupContentCallback = createPopupContentCallback(locationKey);
            const newMarker = MapManager.addMarkerToMap(
                [lng, lat],
                customIconElement,
                locationInfo.name,
                popupContentCallback,
                locationKey
            );
            if (newMarker) {
                MapManager.openMarkerPopup(newMarker);
            }
        }
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Initialization
        init,

        // Marker management
        displayEventsOnMap,
        updateMarkersForViewport,
        updateOpenPopupContent,
        findOpenPopup,
        hasMatchingEvents,
        createPopupContentCallback,

        // Navigation
        flyToLocationAndOpenPopup
    };
})();
