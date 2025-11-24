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

        // Callbacks (injected during init)
        getTagStates: null,
        getSelectedDates: null,
        getForceDisplayEventId: null,
        setForceDisplayEventId: null
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
            const selectedDates = state.getSelectedDates();
            const currentPopupFilters = {
                sliderStartDate: selectedDates[0],
                sliderEndDate: selectedDates[1],
                tagStates: state.getTagStates()
            };

            const eventsAtLocationInDateRange = state.appState.eventsByLatLngInDateRange[locationKey] || [];
            const filterFunctions = {
                isEventMatchingTagFilters: (event, tagStates) => FilterManager.isEventMatchingTagFilters(event, tagStates)
            };

            // Handle forced display event (e.g., from search)
            let eventsToDisplay = eventsAtLocationInDateRange;
            const forceDisplayEventId = state.getForceDisplayEventId();
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
     * Displays markers for locations with matching events
     * Clears existing markers (except markerToKeep) and creates new ones
     * Enforces marker display limit
     *
     * @param {Object} locationsToDisplay - Object mapping locationKey to array of events
     * @param {L.Marker} [markerToKeep=null] - Marker to preserve (e.g., one with open popup)
     */
    function displayEventsOnMap(locationsToDisplay, markerToKeep = null) {
        let openMarkerLocationKey = null;
        if (markerToKeep) {
            const latLng = markerToKeep.getLatLng();
            openMarkerLocationKey = `${latLng.lat},${latLng.lng}`;
        }

        MapManager.clearMarkers(markerToKeep);
        let visibleLocationCount = markerToKeep ? 1 : 0;

        for (const locationKey in locationsToDisplay) {
            // Skip the marker that's being kept open
            if (locationKey === openMarkerLocationKey) {
                continue;
            }

            // Enforce marker display limit
            if (visibleLocationCount >= state.config.MARKER_DISPLAY_LIMIT) {
                console.warn(`Marker display limit (${state.config.MARKER_DISPLAY_LIMIT}) reached.`);
                break;
            }

            const eventsAtLocation = locationsToDisplay[locationKey];
            if (eventsAtLocation.length === 0) continue;

            visibleLocationCount++;

            // Parse location coordinates
            const [lat, lng] = locationKey.split(',').map(Number);
            if (lat === 0 && lng === 0) continue;

            // Get location info
            const locationInfo = state.appState.locationsByLatLng[locationKey];
            if (!locationInfo) continue;

            // Create marker icon
            const locationName = locationInfo.name;
            const customIcon = MapManager.createMarkerIcon(locationInfo);

            // Create popup content callback
            const popupContentCallback = createPopupContentCallback(locationKey);

            // Add marker to map
            const newMarker = MapManager.addMarkerToMap([lat, lng], customIcon, locationName, popupContentCallback);

            // Auto-open popup if this location contains the forced display event
            const forceDisplayEventId = state.getForceDisplayEventId();
            if (forceDisplayEventId && newMarker) {
                if (eventsAtLocation.some(e => e.id === forceDisplayEventId)) {
                    newMarker.openPopup();
                }
            }
        }
    }

    /**
     * Updates the content of an open popup with current filters
     * Used when filters change while a popup is open
     *
     * @param {L.Popup} openPopup - The open popup to update
     * @returns {boolean} True if popup was updated, false otherwise
     */
    function updateOpenPopupContent(openPopup) {
        if (!openPopup) return false;

        const popupLatLng = openPopup.getLatLng();
        const locationKey = `${popupLatLng.lat},${popupLatLng.lng}`;
        const locationInfo = state.appState.locationsByLatLng[locationKey];
        const eventsAtLocationInDateRange = state.appState.eventsByLatLngInDateRange[locationKey] || [];

        const selectedDates = state.getSelectedDates();
        const currentPopupFilters = {
            sliderStartDate: selectedDates[0],
            sliderEndDate: selectedDates[1],
            tagStates: state.getTagStates()
        };

        const filterFunctions = {
            isEventMatchingTagFilters: (event, tagStates) => FilterManager.isEventMatchingTagFilters(event, tagStates)
        };

        // Handle forced display event
        let eventsToDisplay = eventsAtLocationInDateRange;
        const forceDisplayEventId = state.getForceDisplayEventId();
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

        openPopup.setContent(newContent);

        // Clear forced display after updating
        state.setForceDisplayEventId(null);

        return true;
    }

    /**
     * Finds the currently open popup marker if any
     *
     * @param {L.Map} map - Leaflet map instance
     * @returns {Object|null} Object with {popup, marker} or null if no popup is open
     */
    function findOpenPopup(map) {
        if (!map) return null;

        let openPopup = null;
        let openMarker = null;

        map.eachLayer(layer => {
            if (layer instanceof L.Popup && map.hasLayer(layer)) {
                openPopup = layer;
                if (layer._source) {
                    openMarker = layer._source;
                }
            }
        });

        return openPopup ? { popup: openPopup, marker: openMarker } : null;
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
        const currentTagStates = state.getTagStates();

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
     * @param {Function} config.getTagStates - Function to get current tag states
     * @param {Function} config.getSelectedDates - Function to get selected date range
     * @param {Function} config.getForceDisplayEventId - Function to get forced display event ID
     * @param {Function} config.setForceDisplayEventId - Function to set forced display event ID
     */
    function init(config) {
        state.appState = config.appState;
        state.config = config.config;
        state.getTagStates = config.getTagStates;
        state.getSelectedDates = config.getSelectedDates;
        state.getForceDisplayEventId = config.getForceDisplayEventId;
        state.setForceDisplayEventId = config.setForceDisplayEventId;
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Initialization
        init,

        // Marker management
        displayEventsOnMap,
        updateOpenPopupContent,
        findOpenPopup,
        hasMatchingEvents,
        createPopupContentCallback
    };
})();
