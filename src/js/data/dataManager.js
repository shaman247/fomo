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
     * Transforms a raw event into a structured event object.
     * The id comes from the backend export so the same event in two chunks
     * (recurring events live in every day chunk they touch) collapses to one.
     * @param {Object} rawEvent - Raw event from data source
     * @param {Object} state - Application state (for location lookups)
     * @param {Object} config - Application configuration
     * @param {boolean} isWindows - Whether running on Windows
     * @returns {Object|null} Processed event or null if invalid
     */
    function transformRawEvent(rawEvent, state, config, isWindows) {
        const { id, lat, lng, tags, occurrences: occurrencesJson, ...restOfEvent } = rawEvent;

        // Decode HTML entities in text fields
        ['name', 'location', 'sublocation'].forEach(field => {
            if (restOfEvent[field]) {
                restOfEvent[field] = Utils.decodeHtml(restOfEvent[field]);
            }
        });

        // Validate required fields
        if (!restOfEvent.name || lat == null || lng == null || lat === '' || lng === '') {
            return null;
        }

        // Clear invalid location/sublocation values
        ['location', 'sublocation'].forEach(field => {
            if (restOfEvent[field] && (restOfEvent[field].startsWith('None') || restOfEvent[field].startsWith('N/A'))) {
                restOfEvent[field] = '';
            }
        });

        // Parse occurrences
        let parsedOccurrences;
        try {
            parsedOccurrences = parseOccurrences(occurrencesJson);
        } catch (e) {
            console.warn(`Could not parse occurrences for event "${rawEvent.name}":`, occurrencesJson, e);
            return null;
        }

        // Filter by date range
        if (!isEventInAppDateRange(parsedOccurrences, config)) {
            return null;
        }

        const locationKey = `${lat},${lng}`;

        // On Windows, replace country flag emojis with location emoji
        let emoji = restOfEvent.emoji;
        if (isWindows && Utils.isCountryFlagEmoji(emoji)) {
            const location = state.locationsByLatLng[locationKey];
            if (location?.emoji) {
                emoji = location.emoji;
            }
        }

        return {
            id,
            ...restOfEvent,
            section: restOfEvent.section || 'Events',
            emoji,
            latitude: lat,
            longitude: lng,
            locationKey,
            tags,
            occurrences: parsedOccurrences
        };
    }

    /**
     * Processes event data into structured format
     * @param {Array} eventData - Array of raw event objects
     * @param {Object} state - Application state
     * @param {Object} config - Application configuration
     */
    function processEventData(eventData, state, config) {
        const isWindows = Utils.isWindows();
        state.allEvents = eventData
            .map(rawEvent => transformRawEvent(rawEvent, state, config, isWindows))
            .filter(Boolean);

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
     * Async version of processFullData that yields to the main thread between
     * event-processing chunks. Keeps clicks/typing responsive during the heavy
     * Phase 2 merge (~30k events would otherwise block ~150ms uninterrupted).
     */
    async function processFullDataAsync(fullEventData, fullLocationData, state, config, onProgress) {
        fullLocationData.forEach(location => {
            if (location.lat != null && location.lng != null) {
                const locationKey = `${location.lat},${location.lng}`;
                if (!state.locationsByLatLng[locationKey]) {
                    state.locationsByLatLng[locationKey] = location;
                }
            }
        });
        await appendEventDataChunked(fullEventData, state, config, onProgress);
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
        const isWindows = Utils.isWindows();
        const seen = state.eventsById || {};

        const newEvents = [];
        for (const rawEvent of newEventData) {
            // Skip events already loaded — chunks overlap on multi-day events.
            if (rawEvent && rawEvent.id != null && seen[rawEvent.id]) continue;
            const ev = transformRawEvent(rawEvent, state, config, isWindows);
            if (!ev) continue;
            if (seen[ev.id]) continue;
            seen[ev.id] = ev;
            newEvents.push(ev);
        }

        state.allEvents.push(...newEvents);
        appendToEventLookups(state, newEvents);
    }

    /**
     * Async chunked version of appendEventData. Processes events in batches of
     * EVENT_PROCESS_CHUNK_SIZE and yields to the main thread between chunks
     * via setTimeout(0), so user interactions get frame boundaries to fire on.
     */
    // Use scheduler.yield() when available (yields with input priority on modern Chrome),
    // otherwise MessageChannel.postMessage (sub-ms scheduling, vs setTimeout's 4ms min).
    // Lets chunked loops yield ~10× more cheaply than `setTimeout(0)`.
    let _yieldChannel = null;
    function _yieldToMain() {
        if (typeof scheduler !== 'undefined' && typeof scheduler.yield === 'function') {
            return scheduler.yield();
        }
        if (typeof MessageChannel !== 'undefined') {
            if (!_yieldChannel) {
                _yieldChannel = new MessageChannel();
                _yieldChannel.port1.start?.();
            }
            return new Promise(resolve => {
                const handler = () => {
                    _yieldChannel.port1.removeEventListener('message', handler);
                    resolve();
                };
                _yieldChannel.port1.addEventListener('message', handler);
                _yieldChannel.port2.postMessage(0);
            });
        }
        return new Promise(r => setTimeout(r, 0));
    }

    // Larger chunks = less yield overhead but longer pauses between input handling.
    // 4000 events ≈ ~25ms per chunk on a typical machine — under a 30fps frame budget.
    const EVENT_PROCESS_CHUNK_SIZE = 4000;
    async function appendEventDataChunked(newEventData, state, config, onProgress) {
        const isWindows = Utils.isWindows();
        const total = newEventData.length;
        const newEvents = [];
        // Track ids seen across chunks (Phase 1's eventsById + this batch).
        // Multi-day events appear in every chunk they touch — dedup on id.
        const seen = new Set(Object.keys(state.eventsById || {}));

        for (let i = 0; i < total; i += EVENT_PROCESS_CHUNK_SIZE) {
            const end = Math.min(i + EVENT_PROCESS_CHUNK_SIZE, total);
            for (let j = i; j < end; j++) {
                const raw = newEventData[j];
                if (!raw || raw.id == null) continue;
                const idKey = String(raw.id);
                if (seen.has(idKey)) continue;
                seen.add(idKey);
                const ev = transformRawEvent(raw, state, config, isWindows);
                if (ev) newEvents.push(ev);
            }
            if (onProgress) onProgress(end, total);
            if (end < total) {
                await _yieldToMain();
            }
        }

        state.allEvents.push(...newEvents);
        appendToEventLookups(state, newEvents);
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
        appendToEventLookups(state, state.allEvents);
    }

    /**
     * Append-only update of event lookups. Phase 2 uses this instead of
     * rebuilding from scratch — saves O(initEventCount) work each time the
     * full dataset merges.
     */
    function appendToEventLookups(state, eventsToAdd) {
        if (!state.eventsById) state.eventsById = {};
        if (!state.eventsByLatLng) state.eventsByLatLng = {};
        for (const event of eventsToAdd) {
            state.eventsById[event.id] = event;
            if (event.locationKey) {
                if (!state.eventsByLatLng[event.locationKey]) {
                    state.eventsByLatLng[event.locationKey] = [];
                }
                state.eventsByLatLng[event.locationKey].push(event);
            }
        }
    }

    /**
     * Builds search index with normalized text for accent/case-insensitive search
     * @param {Object} state - Application state
     */
    /**
     * Async chunked version of buildSearchIndex. Yields to the main thread
     * every SEARCH_INDEX_CHUNK_SIZE events. The synchronous version is kept
     * for callers that need to block (e.g. a search fired before the async
     * build completes).
     */
    const SEARCH_INDEX_CHUNK_SIZE = 5000;
    async function buildSearchIndexAsync(state) {
        _initSearchIndexShell(state);
        for (let i = 0; i < state.allEvents.length; i += SEARCH_INDEX_CHUNK_SIZE) {
            const end = Math.min(i + SEARCH_INDEX_CHUNK_SIZE, state.allEvents.length);
            for (let j = i; j < end; j++) {
                _indexEvent(state, state.allEvents[j]);
            }
            if (end < state.allEvents.length) {
                await _yieldToMain();
            }
        }
        _indexLocationsTagsOrganizers(state);
    }

    function _initSearchIndexShell(state) {
        state.searchIndex = {
            events: new Map(),
            locations: new Map(),
            tags: new Map(),
            organizers: new Map(),
            eventDisplayNames: new Map()
        };
    }

    function _indexEvent(state, event) {
        const searchableFields = [
            event.name, event.short_name, event.description, event.location, event.sublocation
        ].filter(Boolean);
        const normalizedText = searchableFields.map(field => Utils.normalizeForSearch(field)).join(' ');
        state.searchIndex.events.set(event.id, normalizedText);
        const nameToDisplay = Utils.getDisplayName(event);
        const formatted = Utils.formatAndSanitize(nameToDisplay).replace(/<\/?em>/g, '');
        state.searchIndex.eventDisplayNames.set(event.id, formatted);
    }

    function _indexLocationsTagsOrganizers(state) {
        Object.entries(state.locationsByLatLng).forEach(([key, location]) => {
            const searchableFields = [location.name, location.short_name, ...(location.tags || [])].filter(Boolean);
            const normalizedText = searchableFields.map(field => Utils.normalizeForSearch(field)).join(' ');
            state.searchIndex.locations.set(key, normalizedText);
        });
        state.allAvailableTags.forEach(tag => {
            state.searchIndex.tags.set(tag, Utils.normalizeForSearch(tag));
        });
        if (state.organizersById) {
            Object.entries(state.organizersById).forEach(([id, org]) => {
                state.searchIndex.organizers.set(id, Utils.normalizeForSearch(org.name || ''));
            });
        }
    }

    function buildSearchIndex(state) {
        _initSearchIndexShell(state);
        for (const event of state.allEvents) _indexEvent(state, event);
        _indexLocationsTagsOrganizers(state);
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
     * Builds hierarchy lookup maps from the exported tag_hierarchy.json data.
     * @param {Object} data - { tags: [...], keywords: [...] }
     * @returns {Object} { childrenOf, parentsOf, descendantsOf, quickFilters, hierarchyTagsSet, tagEmojiMap }
     */
    function buildTagHierarchyMaps(data) {
        const tags = data.tags || [];

        const childrenOf = {};   // parent -> [children]
        const parentsOf = {};    // child -> [parents]
        const quickFilters = []; // [{name, emoji, order}]
        const tagEmojiMap = {};  // tagName -> emoji
        // Set of all curated tag names (tags NOT in this set are keywords)
        const hierarchyTagsSet = new Set();

        // Build parent/child maps from flat list
        tags.forEach(tag => {
            hierarchyTagsSet.add(tag.name);
            if (tag.emoji) tagEmojiMap[tag.name] = tag.emoji;
            const parents = tag.parents || [];
            if (parents.length > 0) {
                parentsOf[tag.name] = parents;
                parents.forEach(parent => {
                    if (!childrenOf[parent]) childrenOf[parent] = [];
                    childrenOf[parent].push(tag.name);
                });
            }
            if (tag.quickFilter) {
                quickFilters.push({
                    name: tag.name,
                    emoji: tag.emoji || '',
                    order: tag.order || 999
                });
            }
        });

        // Sort quick filters by order
        quickFilters.sort((a, b) => a.order - b.order);

        // Compute transitive descendants via BFS
        const descendantsOf = {};
        const allParents = Object.keys(childrenOf);
        allParents.forEach(parent => {
            const descendants = new Set();
            const queue = [...(childrenOf[parent] || [])];
            while (queue.length > 0) {
                const child = queue.shift();
                if (descendants.has(child)) continue;
                descendants.add(child);
                (childrenOf[child] || []).forEach(grandchild => {
                    if (!descendants.has(grandchild)) queue.push(grandchild);
                });
            }
            descendantsOf[parent] = descendants;
        });

        return { childrenOf, parentsOf, descendantsOf, quickFilters, hierarchyTagsSet, tagEmojiMap };
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

        // Exclude keywords (tags not in the hierarchy) from the browsable tag list
        const hierarchyTagsSet = state.hierarchyTagsSet || new Set();
        state.allAvailableTags = Array.from(allUniqueTagsSet)
            .filter(tag => hierarchyTagsSet.size === 0 || hierarchyTagsSet.has(tag))
            .sort();

        // Precompute the empty-term tag list (excludes geotags). SearchManager
        // iterates this on every search-clear; doing the geotag filter once
        // saves ~2,100 Set lookups per search.
        const geotagsSet = state.geotagsSet || new Set();
        state.searchableTagsForEmptyTerm = state.allAvailableTags.filter(
            tag => !geotagsSet.has(tag.toLowerCase())
        );
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
        processFullDataAsync,
        parseOccurrences,
        isEventInAppDateRange,
        appendEventData,
        rebuildEventLookups,
        buildSearchIndex,
        buildSearchIndexAsync,
        buildTagIndex,
        calculateTagFrequencies,
        buildTagHierarchyMaps,
        processTagHierarchy,
        groupEventsByLatLngInDateRange
    };
})();
