/**
 * DataManager Module
 *
 * Manages data fetching, processing, and indexing for events and locations.
 * Handles initial and full dataset loading, event filtering, and tag management.
 *
 * Features:
 * - Network data fetching with timeout and error handling
 * - Event and location data processing
 * - Tag indexing and frequency calculation
 * - Date range filtering
 * - Occurrence parsing and validation
 *
 * @module DataManager
 */
const DataManager = (() => {
    // ========================================
    // DATA FETCHING
    // ========================================

    /**
     * Fetches data from the specified URL with comprehensive error handling
     * @param {string} url - The URL to fetch data from
     * @param {number} timeout - Timeout in milliseconds (default: 10000ms)
     * @returns {Promise<Object>} The parsed JSON data
     * @throws {Error} Network, timeout, or parsing errors with user-friendly messages
     */
    async function fetchData(url, timeout = 10000) {
        try {
            // Create an AbortController for timeout handling
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), timeout);

            let response;
            try {
                response = await fetch(url, { signal: controller.signal });
                clearTimeout(timeoutId);
            } catch (fetchError) {
                clearTimeout(timeoutId);

                // Handle different types of fetch errors
                if (fetchError.name === 'AbortError') {
                    throw new Error(`Request timed out after ${timeout/1000} seconds. Please check your internet connection and try again.`);
                } else if (fetchError.message.includes('Failed to fetch') || fetchError.message.includes('NetworkError')) {
                    throw new Error('Unable to connect to the server. Please check your internet connection and try again.');
                } else {
                    throw new Error(`Network error: ${fetchError.message}`);
                }
            }

            // Handle HTTP errors
            if (!response.ok) {
                if (response.status === 404) {
                    throw new Error(`Data file not found (404). The requested resource may have been moved or deleted.`);
                } else if (response.status === 500) {
                    throw new Error(`Server error (500). Please try again later.`);
                } else if (response.status >= 400 && response.status < 500) {
                    throw new Error(`Client error (${response.status}). Please refresh the page and try again.`);
                } else if (response.status >= 500) {
                    throw new Error(`Server error (${response.status}). Please try again later.`);
                } else {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
            }

            // Parse JSON with error handling
            let data;
            try {
                data = await response.json();
            } catch (parseError) {
                throw new Error(`Invalid data format received from server. The data may be corrupted.`);
            }

            return data;

        } catch (error) {
            // Log the error for debugging
            console.error(`Failed to fetch data from ${url}:`, error);

            // Re-throw the error for the caller to handle
            throw error;
        }
    }

    // ========================================
    // DATA PROCESSING
    // ========================================

    /**
     * Processes location data into a lookup map
     * @param {Array} locationData - Array of location objects
     * @param {Object} state - Application state
     */
    function processLocationData(locationData, state) {
        state.locationsByLatLng = {};
        locationData.forEach(location => {
            if (location.lat != null && location.lng != null) {
                const locationKey = `${location.lat},${location.lng}`;
                if (!state.locationsByLatLng[locationKey]) {
                    state.locationsByLatLng[locationKey] = location;
                }
            }
        });
    }

    /**
     * Processes initial dataset (events and locations)
     * @param {Array} eventData - Array of event objects
     * @param {Array} locationData - Array of location objects
     * @param {Object} state - Application state
     * @param {Object} config - Application configuration
     */
    function processInitialData(eventData, locationData, state, config) {
        processLocationData(locationData, state);
        processEventData(eventData, state, config);
    }

    /**
     * Processes event data into structured format
     * @param {Array} eventData - Array of raw event objects
     * @param {Object} state - Application state
     * @param {Object} config - Application configuration
     */
    function processEventData(eventData, state, config) {
        let windows = Utils.isWindows();
        state.allEvents = eventData.flatMap((rawEvent, index) => {
            const { lat, lng, tags, occurrences: occurrencesJson, ...restOfEvent } = rawEvent;

            ['name', 'location', 'sublocation'].forEach(field => {
                if (restOfEvent[field]) {
                    restOfEvent[field] = Utils.decodeHtml(restOfEvent[field]);
                }
            });

            if (!restOfEvent.name || lat == null || lng == null || lat === '' || lng === '') {
                return [];
            }

            ['location', 'sublocation'].forEach(field => {
                if (restOfEvent[field] && (restOfEvent[field].startsWith('None') || restOfEvent[field].startsWith('N/A'))) {
                    restOfEvent[field] = '';
                }
            });

            let parsedOccurrences;
            try {
                parsedOccurrences = parseOccurrences(occurrencesJson);
            } catch (e) {
                console.warn(`Could not parse occurrences for event "${rawEvent.name}":`, occurrencesJson, e);
                return [];
            }

            if (!isEventInAppDateRange(parsedOccurrences, config)) {
                return [];
            }

            const locationKey = `${lat},${lng}`;

            // On Windows, replace country flag emojis with location emoji
            let emoji = restOfEvent.emoji;
            if (windows && Utils.isCountryFlagEmoji(emoji)) {
                const location = state.locationsByLatLng[locationKey];
                if (location?.emoji) {
                    emoji = location.emoji;
                }
            }

            return [{
                id: index,
                ...restOfEvent,
                emoji: emoji,
                latitude: lat,
                longitude: lng,
                locationKey: locationKey,
                tags: tags,
                occurrences: parsedOccurrences
            }];
        });

        rebuildEventLookups(state);
    }

    /**
     * Processes full dataset (events and locations)
     * @param {Array} fullEventData - Array of all event objects
     * @param {Array} fullLocationData - Array of all location objects
     * @param {Object} state - Application state
     * @param {Object} config - Application configuration
     */
    function processFullData(fullEventData, fullLocationData, state, config) {
        // Add new locations from the full set
        fullLocationData.forEach(location => {
            if (location.lat != null && location.lng != null) {
                const locationKey = `${location.lat},${location.lng}`;
                if (!state.locationsByLatLng[locationKey]) {
                    state.locationsByLatLng[locationKey] = location;
                }
            }
        });

        // Append new events from the full set
        appendEventData(fullEventData, state, config);
    }

    /**
     * Parses occurrence data into structured format
     * @param {Array} occurrencesJson - Raw occurrence data
     * @returns {Array} Parsed occurrences with start/end dates
     */
    function parseOccurrences(occurrencesJson) {
        const occurrencesArray = occurrencesJson || [];
        if (!Array.isArray(occurrencesArray)) return []; // Keep this check for safety

        const parsedOccurrences = occurrencesArray.map(occ => {
            const [startDateStr, startTimeStr, endDateStr, endTimeStr] = occ;
            const start = Utils.parseDateInNewYork(startDateStr, startTimeStr);
            const effectiveEndDateStr = (endDateStr && endDateStr.trim() !== '') ? endDateStr : startDateStr;
            const effectiveEndTimeStr = (endTimeStr && endTimeStr.trim() !== '') ? endTimeStr : startTimeStr;
            const end = Utils.parseDateInNewYork(effectiveEndDateStr, effectiveEndTimeStr);

            if (start && !end) {
                return { start, end: new Date(start), originalStartTime: startTimeStr, originalEndTime: endTimeStr };
            }
            if (start && end) {
                return { start, end, originalStartTime: startTimeStr, originalEndTime: endTimeStr };
            }
            return null;
        }).filter(Boolean);

        parsedOccurrences.sort((a, b) => a.start - b.start);
        return parsedOccurrences;
    }

    /**
     * Checks if event falls within application date range
     * @param {Array} occurrences - Event occurrences
     * @param {Object} config - Application configuration
     * @returns {boolean} True if event is in date range
     */
    function isEventInAppDateRange(occurrences, config) {
        return occurrences.some(occ =>
            occ.start <= config.END_DATE && occ.end >= config.START_DATE
        );
    }

    /**
     * Appends new event data to existing events
     * @param {Array} newEventData - Array of new event objects
     * @param {Object} state - Application state
     * @param {Object} config - Application configuration
     */
    function appendEventData(newEventData, state, config) {
        const initialEventCount = state.allEvents.length;

        const newEvents = newEventData.flatMap((rawEvent, index) => {
            const { lat, lng, tags, occurrences: occurrencesJson, ...restOfEvent } = rawEvent;

            ['name', 'location', 'sublocation'].forEach(field => {
                if (restOfEvent[field]) {
                    restOfEvent[field] = Utils.decodeHtml(restOfEvent[field]);
                }
            });

            if (!restOfEvent.name || lat == null || lng == null || lat === '' || lng === '') {
                return [];
            }

            ['location', 'sublocation'].forEach(field => {
                if (restOfEvent[field] && (restOfEvent[field].startsWith('None') || restOfEvent[field].startsWith('N/A'))) {
                    restOfEvent[field] = '';
                }
            });

            const parsedOccurrences = parseOccurrences(occurrencesJson);
            if (!isEventInAppDateRange(parsedOccurrences, config)) {
                return [];
            }

            const locationKey = `${lat},${lng}`;

            // On Windows, replace country flag emojis with location emoji
            let emoji = restOfEvent.emoji;
            if (Utils.isWindows() && Utils.isCountryFlagEmoji(emoji)) {
                const location = state.locationsByLatLng[locationKey];
                if (location?.emoji) {
                    emoji = location.emoji;
                }
            }

            return [{
                id: initialEventCount + index, // Ensure unique IDs
                ...restOfEvent,
                emoji: emoji,
                latitude: lat,
                longitude: lng,
                locationKey: locationKey,
                tags: tags,
                occurrences: parsedOccurrences
            }];
        });

        state.allEvents.push(...newEvents);
        rebuildEventLookups(state);
    }

    // ========================================
    // INDEXING & LOOKUPS
    // ========================================

    /**
     * Rebuilds event lookup indexes
     * @param {Object} state - Application state
     */
    function rebuildEventLookups(state) {
        state.eventsById = {};
        state.eventsByLatLng = {};
        state.allEvents.forEach(event => {
            state.eventsById[event.id] = event;
            if (event.locationKey) {
                if (!state.eventsByLatLng[event.locationKey]) {
                    state.eventsByLatLng[event.locationKey] = [];
                }
                state.eventsByLatLng[event.locationKey].push(event);
            }
        });
    }

    /**
     * Builds search index with normalized text for accent/case-insensitive search
     * @param {Object} state - Application state
     */
    function buildSearchIndex(state) {
        state.searchIndex = {
            events: new Map(),      // eventId -> normalized searchable text
            locations: new Map(),   // locationKey -> normalized searchable text
            tags: new Map()         // tag -> normalized tag
        };

        // Index events
        state.allEvents.forEach(event => {
            const searchableFields = [
                event.name,
                event.short_name,
                event.description,
                event.location,
                event.sublocation
            ].filter(Boolean);

            const normalizedText = searchableFields
                .map(field => Utils.normalizeForSearch(field))
                .join(' ');

            state.searchIndex.events.set(event.id, normalizedText);
        });

        // Index locations
        Object.entries(state.locationsByLatLng).forEach(([key, location]) => {
            const searchableFields = [
                location.name,
                location.short_name,
                ...(location.tags || [])
            ].filter(Boolean);

            const normalizedText = searchableFields
                .map(field => Utils.normalizeForSearch(field))
                .join(' ');

            state.searchIndex.locations.set(key, normalizedText);
        });

        // Index tags
        state.allAvailableTags.forEach(tag => {
            state.searchIndex.tags.set(tag, Utils.normalizeForSearch(tag));
        });
    }

    /**
     * Builds tag index for efficient tag-based lookups
     * @param {Object} state - Application state
     * @param {Array} events - Events to index (optional, defaults to all events)
     */
    function buildTagIndex(state, events) {
        const eventsToIndex = events || state.allEvents;
        state.eventTagIndex = {};
        eventsToIndex.forEach(event => {
            const combinedTags = new Set(event.tags || []);
            const location = state.locationsByLatLng[event.locationKey];
            if (location && location.tags) {
                location.tags.forEach(tag => combinedTags.add(tag));
            }

            combinedTags.forEach(tag => {
                if (!state.eventTagIndex[tag]) {
                    state.eventTagIndex[tag] = [];
                }
                state.eventTagIndex[tag].push(event.id);
            });
        });
    }

    /**
     * Calculates tag frequencies across all locations
     * @param {Object} state - Application state
     */
    function calculateTagFrequencies(state) {
        const tagLocationSets = {};
        state.allEvents.forEach(event => {
            if (event.tags && Array.isArray(event.tags) && event.locationKey) {
                event.tags.forEach(tag => {
                    if (!tagLocationSets[tag]) {
                        tagLocationSets[tag] = new Set();
                    }
                    tagLocationSets[tag].add(event.locationKey);
                });
            }
        });

        Object.entries(state.locationsByLatLng).forEach(([locationKey, location]) => {
            if (location.tags && Array.isArray(location.tags)) {
                location.tags.forEach(tag => {
                    if (!tagLocationSets[tag]) {
                        tagLocationSets[tag] = new Set();
                    }
                    // Add the locationKey to the set for this tag
                    tagLocationSets[tag].add(locationKey);
                });
            }
        });

        state.tagFrequencies = {};
        for (const tag in tagLocationSets) {
            state.tagFrequencies[tag] = tagLocationSets[tag].size;
        }
    }

    /**
     * Processes tag hierarchy and available tags
     * @param {Object} state - Application state
     * @param {Object} config - Application configuration
     */
    function processTagHierarchy(state, config) {
        state.tagColors = state.tagConfig.colors || {};
        const allUniqueTagsSet = new Set();
        state.allEvents.forEach(event => {
            if (event.tags && Array.isArray(event.tags)) {
                event.tags.forEach(tag => allUniqueTagsSet.add(tag));
            }
        });

        Object.values(state.locationsByLatLng).forEach(location => {
            if (location.tags && Array.isArray(location.tags)) {
                location.tags.forEach(tag => allUniqueTagsSet.add(tag));
            }
        });

        state.allAvailableTags = Array.from(allUniqueTagsSet).sort();
    }

    /**
     * Groups events by location key for events in the current date range
     * Rebuilds the eventsByLatLngInDateRange lookup from filtered events
     * @param {Object} state - Application state (will be modified)
     */
    function groupEventsByLatLngInDateRange(state) {
        state.eventsByLatLngInDateRange = {};
        state.allEventsFilteredByDateAndLocation.forEach(event => {
            if (event.locationKey) {
                if (!state.eventsByLatLngInDateRange[event.locationKey]) {
                    state.eventsByLatLngInDateRange[event.locationKey] = [];
                }
                state.eventsByLatLngInDateRange[event.locationKey].push(event);
            }
        });
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        fetchData,
        processLocationData,
        processInitialData,
        processEventData,
        processFullData,
        parseOccurrences,
        isEventInAppDateRange,
        appendEventData,
        rebuildEventLookups,
        buildSearchIndex,
        buildTagIndex,
        calculateTagFrequencies,
        processTagHierarchy,
        groupEventsByLatLngInDateRange
    };
})();
