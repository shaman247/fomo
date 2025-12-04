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
        eventProvider: null     // { getForceDisplayEventId, setForceDisplayEventId }
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
     * Displays markers for locations with matching events
     * Clears existing markers (except markerToKeep) and creates new ones
     * Enforces marker display limit
     *
     * @param {Object} locationsToDisplay - Object mapping locationKey to array of events
     * @param {maplibregl.Marker} [markerToKeep=null] - Marker to preserve (e.g., one with open popup)
     */
    function displayEventsOnMap(locationsToDisplay, markerToKeep = null) {
        let openMarkerLocationKey = null;
        if (markerToKeep) {
            const markerObj = MapManager.getMarkerObject(markerToKeep);
            if (markerObj) {
                openMarkerLocationKey = markerObj.locationKey;
            }
        }

        MapManager.clearMarkers(markerToKeep);
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

            visibleLocationCount++;

            // Parse location coordinates
            const [lat, lng] = locationKey.split(',').map(Number);
            if (lat === 0 && lng === 0) continue;

            // Get location info
            const locationInfo = state.appState.locationsByLatLng[locationKey];
            if (!locationInfo) continue;

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
        const map = MapManager.getMap();

        // Fly to the location first
        if (map) {
            map.flyTo({
                center: [lng, lat],
                zoom: Math.max(map.getZoom(), 15),
                duration: 500
            });
        }

        // Function to find and open marker popup
        const openMarkerAtLocation = () => {
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
        };

        // Open marker popup after fly animation completes
        if (map) {
            map.once('moveend', openMarkerAtLocation);
        } else {
            openMarkerAtLocation();
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
        updateOpenPopupContent,
        findOpenPopup,
        hasMatchingEvents,
        createPopupContentCallback,

        // Navigation
        flyToLocationAndOpenPopup
    };
})();
