/**
 * FilterManager Module
 *
 * Handles all event filtering logic including:
 * - Date range filtering
 * - Tag-based filtering (selected/required/forbidden tags)
 * - Viewport-based filtering (visible events on map)
 * - Tag frequency calculations
 *
 * @module FilterManager
 */
const FilterManager = (() => {
    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // App state reference (injected during init)
        appState: null,
        config: null
    };

    // ========================================
    // DATE RANGE FILTERING
    // ========================================

    /**
     * Checks if an event occurs within a given date range
     * @param {Object} event - Event object with occurrences
     * @param {Date} startDate - Start of date range
     * @param {Date} endDate - End of date range
     * @returns {boolean} True if event has at least one occurrence in range
     */
    function isEventInDateRange(event, startDate, endDate) {
        if (!event.occurrences || event.occurrences.length === 0) {
            return false;
        }

        const startFilter = (startDate instanceof Date && !isNaN(startDate)) ? startDate : state.config.START_DATE;
        let endFilter = (endDate instanceof Date && !isNaN(endDate)) ? endDate : state.config.END_DATE;

        // Set end filter to end of day
        endFilter = new Date(endFilter);
        endFilter.setHours(23, 59, 59, 999);

        // Check if any occurrence overlaps with the date range
        for (const occurrence of event.occurrences) {
            if (occurrence.start <= endFilter && occurrence.end >= startFilter) {
                return true;
            }
        }

        return false;
    }

    /**
     * Filters events by date range and attaches matching occurrences
     * @param {Date} startDate - Start of date range
     * @param {Date} endDate - End of date range
     * @returns {Array} Filtered events with matching_occurrences property
     */
    function filterEventsByDateRange(startDate, endDate) {
        const startFilter = (startDate instanceof Date && !isNaN(startDate)) ? startDate : state.config.START_DATE;
        let endFilter = (endDate instanceof Date && !isNaN(endDate)) ? endDate : state.config.END_DATE;

        endFilter = new Date(endFilter);
        endFilter.setHours(23, 59, 59, 999);

        const filteredEvents = [];

        for (const event of state.appState.allEvents) {
            if (!event.occurrences || event.occurrences.length === 0) {
                continue;
            }

            // Find occurrences that overlap with the date range
            const matchingOccurrences = event.occurrences.filter(occurrence => {
                return occurrence.start <= endFilter && occurrence.end >= startFilter;
            });

            if (matchingOccurrences.length > 0) {
                // Create new event object with matching occurrences
                const eventWithMatchingOccurrences = {
                    ...event,
                    matching_occurrences: matchingOccurrences
                };
                filteredEvents.push(eventWithMatchingOccurrences);
            }
        }

        return filteredEvents;
    }

    // ========================================
    // TAG FILTERING
    // ========================================

    /**
     * Checks if an event matches the current tag filters
     * Considers both event tags and location tags
     *
     * @param {Object} event - Event object
     * @param {Object} tagStates - Tag states object {tagName: state}
     * @returns {boolean} True if event matches tag filters
     */
    function isEventMatchingTagFilters(event, tagStates) {
        // Extract tag categories
        const selectedTags = Object.entries(tagStates)
            .filter(([, state]) => state === 'selected')
            .map(([tag]) => tag);

        const requiredTags = Object.entries(tagStates)
            .filter(([, state]) => state === 'required')
            .map(([tag]) => tag);

        const forbiddenTags = Object.entries(tagStates)
            .filter(([, state]) => state === 'forbidden')
            .map(([tag]) => tag);

        // Get combined tags from event and location
        const locationInfo = state.appState.locationsByLatLng[event.locationKey];
        const combinedTags = new Set([
            ...(event.tags || []),
            ...(locationInfo?.tags || [])
        ]);

        // Forbidden tags: event must not have any forbidden tags
        if (forbiddenTags.length > 0 && forbiddenTags.some(tag => combinedTags.has(tag))) {
            return false;
        }

        // Required tags: event must have ALL required tags
        if (requiredTags.length > 0 && !requiredTags.every(tag => combinedTags.has(tag))) {
            return false;
        }

        // Selected tags: event must have at least ONE selected tag (if no required tags)
        if (requiredTags.length === 0 && selectedTags.length > 0 && !selectedTags.some(tag => combinedTags.has(tag))) {
            return false;
        }

        return true;
    }

    /**
     * Filters events by tag states using tag index for performance
     * @param {Object} tagStates - Tag states object {tagName: state}
     * @param {Array} baseEvents - Events to filter (already filtered by date/location)
     * @returns {Array} Events matching tag filters
     */
    function filterEventsByTags(tagStates, baseEvents) {
        const selectedTags = Object.entries(tagStates)
            .filter(([, state]) => state === 'selected')
            .map(([tag]) => tag);

        const requiredTags = Object.entries(tagStates)
            .filter(([, state]) => state === 'required')
            .map(([tag]) => tag);

        const forbiddenTags = Object.entries(tagStates)
            .filter(([, state]) => state === 'forbidden')
            .map(([tag]) => tag);

        let filteredEvents;

        // If no tags selected, use all base events
        if (selectedTags.length === 0 && requiredTags.length === 0) {
            filteredEvents = baseEvents;
        }
        // Required tags: use intersection of tag indexes
        else if (requiredTags.length > 0) {
            let matchingEventIds = new Set(state.appState.eventTagIndex[requiredTags[0]] || []);

            // Intersect with other required tags
            for (let i = 1; i < requiredTags.length; i++) {
                const tag = requiredTags[i];
                const eventIdsForTag = new Set(state.appState.eventTagIndex[tag] || []);
                matchingEventIds = new Set(
                    [...matchingEventIds].filter(id => eventIdsForTag.has(id))
                );
            }

            filteredEvents = Array.from(matchingEventIds)
                .map(id => state.appState.eventsById[id])
                .filter(Boolean);
        }
        // Selected tags: use union of tag indexes
        else if (selectedTags.length > 0) {
            const matchingEventIds = new Set();

            selectedTags.forEach(tag => {
                if (state.appState.eventTagIndex[tag]) {
                    state.appState.eventTagIndex[tag].forEach(eventId =>
                        matchingEventIds.add(eventId)
                    );
                }
            });

            filteredEvents = Array.from(matchingEventIds)
                .map(id => state.appState.eventsById[id])
                .filter(Boolean);
        }
        // No tags selected
        else {
            filteredEvents = baseEvents;
        }

        // Apply forbidden tag filter
        if (forbiddenTags.length > 0) {
            const forbiddenTagsSet = new Set(forbiddenTags);
            filteredEvents = filteredEvents.filter(event =>
                !event.tags?.some(tag => forbiddenTagsSet.has(tag))
            );
        }

        return filteredEvents;
    }

    // ========================================
    // VIEWPORT FILTERING
    // ========================================

    /**
     * Filters events to only those visible in the current map viewport
     * Also calculates tag frequencies for visible events with proximity weighting
     *
     * @param {Array} events - Events to filter
     * @param {Object} bounds - Leaflet LatLngBounds object
     * @param {Object} visibleCenter - Leaflet LatLng object for visible center (used as fallback)
     * @param {Object} [locationDistances=null] - Pre-calculated distances from ViewportManager
     * @returns {Object} Object with visibleEvents, visibleLocationKeys, and visibleTagFrequencies
     */
    function filterEventsByViewport(events, bounds, visibleCenter, locationDistances = null) {
        const visibleEvents = [];
        const visibleLocationKeys = new Set();
        const visibleTagFrequencies = {};

        events.forEach(event => {
            if (event.locationKey) {
                const [lat, lng] = event.locationKey.split(',').map(Number);

                if (bounds.contains([lat, lng])) {
                    visibleEvents.push(event);
                    visibleLocationKeys.add(event.locationKey);

                    // Calculate tag frequencies with proximity weighting
                    if (event.tags) {
                        // Use pre-calculated distance if available, otherwise calculate on the fly
                        const distance = locationDistances?.[event.locationKey] ?? visibleCenter.distanceTo([lat, lng]);
                        // Max bonus of 1 for being at the center, decreasing to 0 at max proximity distance
                        const proximityWeight = Math.max(0, 1 - distance / Constants.DISTANCE.MAX_PROXIMITY_METERS);

                        event.tags.forEach(tag => {
                            if (!visibleTagFrequencies[tag]) {
                                visibleTagFrequencies[tag] = 0;
                            }
                            visibleTagFrequencies[tag] += 1 + proximityWeight;
                        });
                    }
                }
            }
        });

        return {
            visibleEvents,
            visibleLocationKeys,
            visibleTagFrequencies
        };
    }

    // ========================================
    // LOCATION FILTERING
    // ========================================

    /**
     * Groups events by location key
     * @param {Array} events - Events to group
     * @returns {Object} Object mapping locationKey to array of events
     */
    function groupEventsByLocation(events) {
        const eventsByLocation = {};

        events.forEach(event => {
            if (event.locationKey) {
                if (!eventsByLocation[event.locationKey]) {
                    eventsByLocation[event.locationKey] = [];
                }
                eventsByLocation[event.locationKey].push(event);
            }
        });

        return eventsByLocation;
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the FilterManager module
     * @param {Object} config - Configuration object
     * @param {Object} config.appState - Reference to app state
     * @param {Object} config.config - App configuration
     */
    function init(config) {
        state.appState = config.appState;
        state.config = config.config;
    }

    /**
     * Main filtering function that applies all filters
     * @param {Object} params - Filter parameters
     * @param {Date} params.startDate - Start date
     * @param {Date} params.endDate - End date
     * @param {Object} params.tagStates - Tag states object
     * @param {Object} [params.bounds] - Leaflet bounds for viewport filtering
     * @param {Object} [params.visibleCenter] - Leaflet LatLng for visible center
     * @returns {Object} Filtered results with various subsets
     */
    function applyFilters(params) {
        const {
            startDate,
            endDate,
            tagStates,
            bounds,
            visibleCenter
        } = params;

        // Step 1: Filter by date range
        const eventsInDateRange = filterEventsByDateRange(startDate, endDate);

        // Step 2: Filter by tags
        const eventsMatchingTags = filterEventsByTags(tagStates, eventsInDateRange);

        // Step 3: Group by location
        const eventsByLocation = groupEventsByLocation(eventsMatchingTags);
        const matchingLocationKeys = new Set(Object.keys(eventsByLocation));

        // Step 4: Filter by viewport (if bounds provided)
        let viewportResults = null;
        if (bounds && visibleCenter) {
            viewportResults = filterEventsByViewport(eventsMatchingTags, bounds, visibleCenter);
        }

        return {
            eventsInDateRange,
            eventsMatchingTags,
            eventsByLocation,
            matchingLocationKeys,
            ...(viewportResults && {
                visibleEvents: viewportResults.visibleEvents,
                visibleLocationKeys: viewportResults.visibleLocationKeys,
                visibleTagFrequencies: viewportResults.visibleTagFrequencies
            })
        };
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        init,
        applyFilters,
        isEventInDateRange,
        isEventMatchingTagFilters,
        filterEventsByDateRange,
        filterEventsByTags,
        filterEventsByViewport,
        groupEventsByLocation
    };
})();
