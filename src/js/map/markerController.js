/**
 * MarkerController Module
 *
 * Manages marker data lifecycle and popup content generation.
 * Coordinates with MapManager's WebGL symbol layers for rendering.
 *
 * @module MarkerController
 */
const MarkerController = (() => {
    // ========================================
    // STATE
    // ========================================

    const state = {
        appState: null,
        config: null,
        filterProvider: null,
        eventProvider: null
    };

    // ========================================
    // POPUP CONTENT
    // ========================================

    /**
     * Creates a popup content callback for a location
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
                isEventMatchingTagFilters: (event, tagStates) => FilterManager.isEventMatchingTagFilters(event, tagStates),
                getLocationInfo: (key) => state.appState.locationsByLatLng[key]
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

    // ========================================
    // MARKER DISPLAY
    // ========================================

    /**
     * Displays markers for locations with matching events
     * Builds popup callbacks and updates MapManager's GeoJSON data
     *
     * @param {Object} locationsToDisplay - Object mapping locationKey to array of events
     */
    function displayEventsOnMap(locationsToDisplay) {
        // Build popup content callbacks for all locations
        const callbacks = new Map();
        for (const locationKey in locationsToDisplay) {
            if (locationsToDisplay[locationKey].length === 0) continue;
            callbacks.set(locationKey, createPopupContentCallback(locationKey));
        }

        // Update the WebGL marker data
        MapManager.updateMarkerData(
            locationsToDisplay,
            state.appState.locationsByLatLng,
            callbacks
        );
    }

    /**
     * Updates the content of an open popup with current filters
     *
     * @param {maplibregl.Popup} openPopup - The open popup to update
     * @returns {boolean} True if popup was updated, false otherwise
     */
    function updateOpenPopupContent(openPopup) {
        if (!openPopup) return false;

        const locationKey = MapManager.getCurrentPopupLocationKey();
        if (!locationKey) return false;

        const locationInfo = state.appState.locationsByLatLng[locationKey];
        const eventsAtLocationInDateRange = state.appState.eventsByLatLngInDateRange[locationKey] || [];

        const selectedDates = state.filterProvider.getSelectedDates();
        const currentPopupFilters = {
            sliderStartDate: selectedDates[0],
            sliderEndDate: selectedDates[1],
            tagStates: state.filterProvider.getTagStates()
        };

        const filterFunctions = {
            isEventMatchingTagFilters: (event, tagStates) => FilterManager.isEventMatchingTagFilters(event, tagStates),
            getLocationInfo: (key) => state.appState.locationsByLatLng[key]
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
     * Finds the currently open popup if any
     * @returns {Object|null} Object with {popup, locationKey} or null
     */
    function findOpenPopup() {
        const popup = MapManager.getCurrentPopup();
        const locationKey = MapManager.getCurrentPopupLocationKey();
        return popup ? { popup, locationKey } : null;
    }

    /**
     * Checks if a location has matching events based on current tag filters
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

    function init(config) {
        state.appState = config.appState;
        state.config = config.config;
        state.filterProvider = config.filterProvider;
        state.eventProvider = config.eventProvider;
    }

    /**
     * Fly to a location on the map and open its popup
     * @param {number} lat - Latitude
     * @param {number} lng - Longitude
     * @param {string|null} [eventIdToForce=null] - Event ID to force display
     */
    function flyToLocationAndOpenPopup(lat, lng, eventIdToForce = null) {
        if (state.eventProvider && state.eventProvider.setForceDisplayEventId) {
            state.eventProvider.setForceDisplayEventId(eventIdToForce);
        }

        const locationKey = `${lat},${lng}`;

        // Register a popup callback for this location (in case it's filtered out)
        MapManager.registerPopupCallback(locationKey, createPopupContentCallback(locationKey));

        // Open the popup at the coordinates
        MapManager.openPopupAtCoordinates(locationKey, [lng, lat]);
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        init,
        displayEventsOnMap,
        updateOpenPopupContent,
        findOpenPopup,
        hasMatchingEvents,
        createPopupContentCallback,
        flyToLocationAndOpenPopup
    };
})();
