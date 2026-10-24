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
     * Gets the effective end (epoch ms) for filtering, applying early morning cutoff.
     * For overnight events ending before 5 AM, treats them as ending on the previous day.
     * Days and hours are the city's (Utils.*InZone), not the device's.
     * @param {Object} occurrence - Occurrence with start and end dates
     * @returns {number} The effective end for filtering, in epoch ms
     */
    function getEffectiveEndMs(occurrence) {
        const endDay = Utils.dayIndexInZone(occurrence.end);
        const isOvernightEvent = endDay !== Utils.dayIndexInZone(occurrence.start);
        const endsBeforeCutoff = Utils.hourInZone(occurrence.end) < Constants.TIME.EARLY_MORNING_CUTOFF_HOUR;

        if (isOvernightEvent && endsBeforeCutoff) return Utils.dayStartMsInZone(endDay) - 1;
        return occurrence.end.getTime();
    }

    /**
     * Normalizes date filter parameters to the instants bounding those calendar
     * days in the city's timezone, applying defaults.
     * @param {Date} startDate - Start date (may be null/invalid)
     * @param {Date} endDate - End date (may be null/invalid)
     * @returns {Object} Object with startFilterMs and endFilterMs (inclusive, epoch ms)
     */
    function normalizeDateFilters(startDate, endDate) {
        const startFilter = (startDate instanceof Date && !isNaN(startDate)) ? startDate : state.config.START_DATE;
        const endFilter = (endDate instanceof Date && !isNaN(endDate)) ? endDate : state.config.END_DATE;

        return {
            startFilterMs: Utils.dayStartMsInZone(Utils.calendarDayIndex(startFilter)),
            endFilterMs: Utils.dayStartMsInZone(Utils.calendarDayIndex(endFilter) + 1) - 1
        };
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
            occurrence.effectiveEndMs = getEffectiveEndMs(occurrence);
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
        const { startFilterMs, endFilterMs } = normalizeDateFilters(startDate, endDate);
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

        // Use the same event + venue + organizer membership as inclusion.
        if (forbiddenTags.length > 0) {
            const forbiddenIds = new Set();
            for (const tag of forbiddenTags) {
                for (const id of state.appState.eventTagIndex[tag] || []) forbiddenIds.add(id);
            }
            filteredEvents = filteredEvents.filter(event => !forbiddenIds.has(event.id));
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

                    // Each effective tag counts once, even if event and venue share it.
                    const tags = Utils.eventFilterTags(event, state.appState.locationsByLatLng[event.locationKey]);
                    for (const tag of tags) {
                        visibleTagFrequencies[tag] = (visibleTagFrequencies[tag] || 0) + 1 + loc.proximityWeight;
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
