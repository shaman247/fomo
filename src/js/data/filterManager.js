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
     * Gets the effective end date for filtering, applying early morning cutoff.
     * For overnight events ending before 5 AM, treats them as ending on the previous day.
     * @param {Object} occurrence - Occurrence with start and end dates
     * @returns {Date} The effective end date for filtering
     */
    function getEffectiveEndDate(occurrence) {
        const isOvernightEvent = occurrence.end.getDate() !== occurrence.start.getDate();
        const endsBeforeCutoff = occurrence.end.getHours() < Constants.TIME.EARLY_MORNING_CUTOFF_HOUR;

        if (isOvernightEvent && endsBeforeCutoff) {
            const effectiveEnd = new Date(occurrence.end);
            effectiveEnd.setDate(effectiveEnd.getDate() - 1);
            effectiveEnd.setHours(23, 59, 59, 999);
            return effectiveEnd;
        }
        return occurrence.end;
    }

    /**
     * Normalizes date filter parameters, applying defaults and setting end-of-day for endDate
     * @param {Date} startDate - Start date (may be null/invalid)
     * @param {Date} endDate - End date (may be null/invalid)
     * @returns {Object} Object with startFilter and endFilter dates
     */
    function normalizeDateFilters(startDate, endDate) {
        const startFilter = (startDate instanceof Date && !isNaN(startDate)) ? startDate : state.config.START_DATE;
        let endFilter = (endDate instanceof Date && !isNaN(endDate)) ? endDate : state.config.END_DATE;

        endFilter = new Date(endFilter);
        endFilter.setHours(23, 59, 59, 999);

        return { startFilter, endFilter };
    }

    /**
     * Checks if an occurrence overlaps with a date range.
     * Epoch-ms bounds are cached on the occurrence (immutable after parse) so
     * repeated date filtering skips the per-occurrence Date math.
     * @param {Object} occurrence - Occurrence with start and end dates
     * @param {number} startFilterMs - Start of date range (epoch ms)
     * @param {number} endFilterMs - End of date range (epoch ms)
     * @returns {boolean} True if occurrence overlaps with range
     */
    function occurrenceOverlapsRange(occurrence, startFilterMs, endFilterMs) {
        if (occurrence.effectiveEndMs === undefined) {
            occurrence.startMs = occurrence.start.getTime();
            occurrence.effectiveEndMs = getEffectiveEndDate(occurrence).getTime();
        }
        return occurrence.startMs <= endFilterMs && occurrence.effectiveEndMs >= startFilterMs;
    }

    /**
     * Filters events by date range and attaches matching occurrences
     * @param {Date} startDate - Start of date range
     * @param {Date} endDate - End of date range
     * @returns {Array} Filtered events with matching_occurrences property
     */
    function filterEventsByDateRange(startDate, endDate) {
        const { startFilter, endFilter } = normalizeDateFilters(startDate, endDate);
        const startFilterMs = startFilter.getTime();
        const endFilterMs = endFilter.getTime();
        const filteredEvents = [];

        for (const event of state.appState.allEvents) {
            if (!event.occurrences || event.occurrences.length === 0) {
                continue;
            }

            const matchingOccurrences = event.occurrences.filter(occurrence =>
                occurrenceOverlapsRange(occurrence, startFilterMs, endFilterMs)
            );

            if (matchingOccurrences.length > 0) {
                filteredEvents.push({
                    ...event,
                    matching_occurrences: matchingOccurrences
                });
            }
        }

        return filteredEvents;
    }

    // ========================================
    // TAG FILTERING
    // ========================================

    /**
     * Filters events by tag states using tag index for performance
     * @param {Object} tagStates - Tag states object {tagName: state}
     * @param {Array} baseEvents - Events to filter (already filtered by date/location)
     * @returns {Array} Events matching tag filters
     */
    function filterEventsByTags(tagStates, baseEvents) {
        const { selectedTags, requiredTags, forbiddenTags } = Utils.partitionTagStates(tagStates);

        // Tag-index ids must resolve to the date-filtered copies in baseEvents
        // (they carry matching_occurrences); state.appState.eventsById holds
        // the un-annotated originals, which would rank and display recurring
        // events by occurrences outside the active date range downstream.
        let baseById = null;
        if (requiredTags.length > 0 || selectedTags.length > 0) {
            baseById = new Map();
            for (const event of baseEvents) baseById.set(event.id, event);
        }

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
                .map(id => baseById.get(id))
                .filter(Boolean);
        }
        // Selected tags: use union of tag indexes (including related tags!)
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
                .map(id => baseById.get(id))
                .filter(Boolean);
        }

        // Apply forbidden tag filter.
        // NOTE: this index-based path checks event + organizer tags only — NOT
        // location tags, unlike Utils.matchesTagSets (used by the popup sort).
        // Long-standing divergence, kept as-is to preserve which markers display.
        if (forbiddenTags.length > 0) {
            const forbiddenTagsSet = new Set(forbiddenTags);
            filteredEvents = filteredEvents.filter(event => {
                if (event.tags?.some(tag => forbiddenTagsSet.has(tag))) return false;
                if (Utils.organizerTagsForEvent(event).some(t => forbiddenTagsSet.has(t))) return false;
                return true;
            });
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
     * @param {Object} bounds - Bounds object with contains() method
     * @param {Object} visibleCenter - Visible center coordinates {lat, lng}
     * @param {Object} [locationDistances=null] - Pre-calculated distances from ViewportManager
     * @returns {Object} Object with visibleEvents, visibleLocationKeys, and visibleTagFrequencies
     */
    function filterEventsByViewport(events, bounds, visibleCenter, locationDistances = null) {
        const visibleEvents = [];
        const visibleLocationKeys = new Set();
        const visibleTagFrequencies = {};

        // Events cluster on far fewer distinct locations than there are
        // events, so the bounds check and proximity weight are computed once
        // per locationKey rather than once per event. The cache is per-call:
        // nothing survives across viewport or filter changes.
        const locationCache = new Map();

        events.forEach(event => {
            if (event.locationKey) {
                let loc = locationCache.get(event.locationKey);
                if (loc === undefined) {
                    const ll = Utils.parseLocationKey(event.locationKey);
                    const inBounds = !!ll && bounds.contains([ll.lat, ll.lng]);
                    let proximityWeight = 0;
                    if (inBounds) {
                        // Use pre-calculated distance if available, otherwise calculate on the fly
                        let distance;
                        if (locationDistances?.[event.locationKey] !== undefined) {
                            distance = locationDistances[event.locationKey];
                        } else if (visibleCenter) {
                            distance = Utils.calculateHaversineDistance(visibleCenter, ll);
                        } else {
                            distance = 0;
                        }
                        // Max bonus of 1 for being at the center, decreasing to 0 at max proximity distance
                        proximityWeight = Math.max(0, 1 - distance / Constants.DISTANCE.MAX_PROXIMITY_METERS);
                    }
                    loc = { inBounds, proximityWeight };
                    locationCache.set(event.locationKey, loc);
                }

                if (loc.inBounds) {
                    visibleEvents.push(event);
                    visibleLocationKeys.add(event.locationKey);

                    // Calculate tag frequencies with proximity weighting
                    if (event.tags) {
                        event.tags.forEach(tag => {
                            if (!visibleTagFrequencies[tag]) {
                                visibleTagFrequencies[tag] = 0;
                            }
                            visibleTagFrequencies[tag] += 1 + loc.proximityWeight;
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

    // ========================================
    // EXPORTS
    // ========================================

    return {
        init,
        filterEventsByDateRange,
        filterEventsByTags,
        filterEventsByViewport,
        groupEventsByLocation
    };
})();
