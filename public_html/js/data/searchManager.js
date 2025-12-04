/**
 * SearchManager Module
 *
 * Handles all search and filtering operations for locations, events, and tags.
 * Includes scoring algorithms, result grouping, and sorting logic.
 *
 * @module SearchManager
 */
const SearchManager = (() => {
    // ========================================
    // CONSTANTS
    // ========================================

    /**
     * Time constants for temporal scoring
     */
    const TIME_CONSTANTS = {
        FIVE_DAYS_MS: 5 * 24 * 60 * 60 * 1000,
        THIRTY_DAYS_MS: 30 * 24 * 60 * 60 * 1000
    };

    /**
     * Scoring weights for different match types
     */
    const SCORE_WEIGHTS = {
        MATCHING_BOOST: 10,        // Boost for items matching current filters
        MULTI_TAG_MATCH: 3,        // Points per matched tag (when 2+ tags selected)
        VISIBILITY_BOOST: 5,       // Boost for currently visible items
        MAX_PROXIMITY_BONUS: 5,    // Max points for proximity to map center
        MAX_TEMPORAL_BONUS: 5,     // Max points for temporal proximity to selected date
        EXACT_TAG_MATCH: 1000,     // Large boost for exact tag matches
        VISIBLE_TAG_MULTIPLIER: 5  // Multiplier for visible tag frequency
    };

    /**
     * Distance thresholds for proximity scoring
     */
    const DISTANCE_THRESHOLDS = {
        LOCATION_MAX_DISTANCE: 20000  // 20km in meters
    };

    // ========================================
    // STATE
    // ========================================

    /**
     * Search state and configuration
     */
    const state = {
        // App state references (injected during init)
        appState: null
    };

    // ========================================
    // UTILITY FUNCTIONS
    // ========================================

    /**
     * Calculates proximity bonus based on distance from map center
     * @param {number} distance - Distance in meters
     * @param {number} maxBonus - Maximum bonus points
     * @param {number} maxDistance - Distance at which bonus becomes 0
     * @returns {number} Proximity bonus score
     */
    function calculateProximityBonus(distance, maxBonus, maxDistance) {
        return Math.max(0, maxBonus * (1 - distance / maxDistance));
    }

    /**
     * Calculates temporal bonus based on event timing relative to reference date
     * @param {Object} event - Event object with occurrences
     * @param {number} referenceDate - Reference timestamp (usually selected date)
     * @returns {number} Temporal bonus score
     */
    function calculateTemporalBonus(event, referenceDate) {
        if (referenceDate <= 0 || !event.occurrences || event.occurrences.length === 0) {
            return 0;
        }

        const startTime = event.occurrences[0].start?.getTime() || 0;
        const endTime = event.occurrences[0].end?.getTime() || startTime;

        // Check if event is happening on the reference date
        const isOngoingOnReferenceDate = startTime <= referenceDate && endTime >= referenceDate;

        // Calculate distance from reference date with boost for ongoing events
        let distanceFromReference = Math.abs(startTime - referenceDate);
        if (isOngoingOnReferenceDate) {
            distanceFromReference = Math.max(0, distanceFromReference - TIME_CONSTANTS.FIVE_DAYS_MS);
        }

        // Convert distance to a score bonus
        return Math.max(0, SCORE_WEIGHTS.MAX_TEMPORAL_BONUS * (1 - distanceFromReference / TIME_CONSTANTS.THIRTY_DAYS_MS));
    }

    /**
     * Counts how many selected tags match an item's tags
     * @param {Set} itemTags - Set of tags for the item
     * @param {Set} selectedTags - Set of currently selected tags
     * @returns {number} Number of matching tags
     */
    function countMatchingTags(itemTags, selectedTags) {
        if (selectedTags.size < 2) return 0;
        return [...itemTags].filter(tag => selectedTags.has(tag)).length;
    }

    /**
     * Calculates weighted tag match score for an item
     * @param {Set} itemTags - Set of tags for the item
     * @param {Map} selectedTagsWithWeights - Map of tag -> weight
     * @returns {number} Weighted score based on matching tags
     */
    function calculateWeightedTagScore(itemTags, selectedTagsWithWeights) {
        if (selectedTagsWithWeights.size < 2) return 0;

        let weightedScore = 0;
        const matchedTags = [];
        for (const tag of itemTags) {
            const weight = selectedTagsWithWeights.get(tag);
            if (weight !== undefined) {
                // Weight ranges from 0 to 1, multiply by score weight
                const tagScore = weight * SCORE_WEIGHTS.MULTI_TAG_MATCH;
                weightedScore += tagScore;
                matchedTags.push({ tag, weight, tagScore });
            }
        }

        return weightedScore;
    }

    // ========================================
    // SEARCH FUNCTIONS
    // ========================================

    /**
     * Searches locations based on the search term and current filters
     * @param {string} term - Search term (already normalized)
     * @param {Map} selectedTagsWithWeights - Map of tag -> weight
     * @param {Set} matchingLocationKeys - Set of location keys with matching events
     * @param {Set} visibleLocationKeys - Set of currently visible location keys
     * @returns {Map} Map of location results
     */
    function searchLocations(term, selectedTagsWithWeights, matchingLocationKeys, visibleLocationKeys) {
        const results = new Map();
        const hasSearchTerm = term.length > 0;
        const searchIndex = state.appState.searchIndex;

        for (const key in state.appState.locationsByLatLng) {
            const location = state.appState.locationsByLatLng[key];
            const isVisible = visibleLocationKeys.has(key);
            const isMatching = matchingLocationKeys.has(key);

            // Check if location matches search term using normalized index
            let matchesSearchTerm = false;
            if (hasSearchTerm && searchIndex?.locations) {
                const normalizedText = searchIndex.locations.get(key) || '';
                matchesSearchTerm = normalizedText.includes(term);
            }

            // Determine if location should be included
            const shouldInclude = hasSearchTerm ? matchesSearchTerm : (isVisible || isMatching);

            if (shouldInclude) {
                let score = 1;

                // Boost score if location has currently filtered events
                if (isMatching) {
                    score += SCORE_WEIGHTS.MATCHING_BOOST;
                }

                // Boost score for locations that match multiple selected tags (with weights)
                if (selectedTagsWithWeights.size >= 2 && location.tags) {
                    const weightedScore = calculateWeightedTagScore(new Set(location.tags), selectedTagsWithWeights);
                    score += weightedScore;
                }

                // Add proximity bonus
                const distance = state.appState.locationDistances[key] || 0;
                const proximityBonus = calculateProximityBonus(
                    distance,
                    SCORE_WEIGHTS.MAX_PROXIMITY_BONUS,
                    DISTANCE_THRESHOLDS.LOCATION_MAX_DISTANCE
                );
                score += proximityBonus;

                // Add extra boost for visible locations
                if (isVisible) {
                    score += SCORE_WEIGHTS.VISIBILITY_BOOST;
                }

                const resultKey = `location-${key}`;
                results.set(resultKey, {
                    type: 'location',
                    ref: key,
                    displayName: Utils.getDisplayName(location),
                    emoji: location.emoji,
                    score: score,
                    isVisible: isVisible
                });
            }
        }

        return results;
    }

    /**
     * Searches events based on the search term and current filters
     * @param {string} term - Search term (already normalized)
     * @param {Map} selectedTagsWithWeights - Map of tag -> weight
     * @param {Set} matchingEventIds - Set of event IDs matching current filters
     * @param {Set} visibleEventIds - Set of currently visible event IDs
     * @param {number} referenceDate - Reference date for temporal scoring
     * @returns {Map} Map of event results
     */
    function searchEvents(term, selectedTagsWithWeights, matchingEventIds, visibleEventIds, referenceDate) {
        const results = new Map();
        const hasSearchTerm = term.length > 0;
        const searchIndex = state.appState.searchIndex;

        state.appState.allEvents.forEach(event => {
            const resultKey = `event-${event.id}`;
            const isVisible = visibleEventIds.has(event.id);
            const isMatching = matchingEventIds.has(event.id);

            // Check if event matches search term using normalized index
            let textMatch = false;
            if (hasSearchTerm && searchIndex?.events) {
                const normalizedText = searchIndex.events.get(event.id) || '';
                textMatch = normalizedText.includes(term);
            }

            // Determine if event should be included
            const shouldInclude = hasSearchTerm ? textMatch : (isVisible || isMatching);

            if (shouldInclude) {
                let score = 1;

                // Boost score if event matches current filters
                if (isMatching) {
                    score += SCORE_WEIGHTS.MATCHING_BOOST;
                }

                // Boost score for events that match multiple selected tags (with weights)
                if (selectedTagsWithWeights.size >= 2) {
                    const locationInfo = event.locationKey ? state.appState.locationsByLatLng[event.locationKey] : null;
                    const combinedTags = new Set([...(event.tags || []), ...(locationInfo?.tags || [])]);
                    const weightedScore = calculateWeightedTagScore(combinedTags, selectedTagsWithWeights);
                    score += weightedScore;
                }

                // Add proximity bonus
                if (event.locationKey) {
                    const distance = state.appState.locationDistances[event.locationKey] || 0;
                    const proximityBonus = calculateProximityBonus(
                        distance,
                        SCORE_WEIGHTS.MAX_PROXIMITY_BONUS,
                        DISTANCE_THRESHOLDS.LOCATION_MAX_DISTANCE
                    );
                    score += proximityBonus;
                }

                // Add temporal bonus
                score += calculateTemporalBonus(event, referenceDate);

                // Add extra boost for visible events
                if (isVisible) {
                    score += SCORE_WEIGHTS.VISIBILITY_BOOST;
                }

                const nameToDisplay = Utils.getDisplayName(event);

                results.set(resultKey, {
                    type: 'event',
                    ref: event.id,
                    displayName: Utils.formatAndSanitize(nameToDisplay).replace(/<\/?em>/g, ''),
                    emoji: event.emoji,
                    score: score,
                    isVisible: isVisible
                });
            }
        });

        return results;
    }

    /**
     * Searches tags based on the search term and current filters
     * @param {string} term - Search term (already normalized)
     * @param {Object} dynamicFrequencies - Current dynamic tag frequencies
     * @returns {Map} Map of tag results
     */
    function searchTags(term, dynamicFrequencies) {
        const results = new Map();
        const searchIndex = state.appState.searchIndex;

        state.appState.allAvailableTags.forEach(tag => {
            // Use normalized index for matching
            const normalizedTag = searchIndex?.tags?.get(tag) || tag.toLowerCase();
            if (normalizedTag.includes(term)) {
                // Skip geotags when search term is empty
                if (!term && state.appState.geotagsSet.has(tag.toLowerCase())) {
                    return;
                }

                const isVisible = state.appState.visibleTagFrequencies[tag] > 0;

                let score = dynamicFrequencies[tag] || 0;

                // Boost score significantly for exact matches
                if (normalizedTag === term) {
                    score += SCORE_WEIGHTS.EXACT_TAG_MATCH;
                }

                // Add proximity-weighted score for visible tags
                if (isVisible) {
                    score += state.appState.visibleTagFrequencies[tag] * SCORE_WEIGHTS.VISIBLE_TAG_MULTIPLIER;
                    score += SCORE_WEIGHTS.VISIBILITY_BOOST;
                }

                // Add global frequency tiebreaker
                const globalFreq = state.appState.tagFrequencies[tag] || 0;
                score += globalFreq * 0.01;

                const resultKey = `tag-${tag}`;
                results.set(resultKey, {
                    type: 'tag',
                    ref: tag,
                    score: score,
                    isVisible: isVisible
                });
            }
        });

        return results;
    }

    /**
     * Main search function that searches across locations, events, and tags
     * @param {string} term - Search term (lowercase)
     * @param {Object} dynamicFrequencies - Current dynamic tag frequencies
     * @param {Array<[string, string, number]>} selectedTagsWithColors - Array of [tag, color, weight] tuples
     *        where weight=1.0 for explicitly selected tags and weight<1.0 for implicit/related tags
     * @returns {Array} Array of search results
     */
    function performSearch(term, dynamicFrequencies, selectedTagsWithColors) {
        // Prepare search context
        const matchingEventIds = new Set(state.appState.currentlyMatchingEvents.map(e => e.id));
        const matchingLocationKeys = state.appState.currentlyMatchingLocationKeys;
        const visibleEventIds = new Set(state.appState.currentlyVisibleMatchingEvents.map(e => e.id));
        const visibleLocationKeys = state.appState.currentlyVisibleMatchingLocationKeys;

        // Create a map of tag -> weight for scoring
        const selectedTagsWithWeights = new Map();
        for (const [tag, , weight] of selectedTagsWithColors) {
            selectedTagsWithWeights.set(tag, weight);
        }

        // Get reference date for temporal scoring
        const selectedDates = state.appState.datePickerInstance?.selectedDates || [];
        const referenceDate = selectedDates.length > 0 ? selectedDates[0].getTime() : 0;

        // Perform searches
        const locationResults = searchLocations(term, selectedTagsWithWeights, matchingLocationKeys, visibleLocationKeys);
        const eventResults = searchEvents(term, selectedTagsWithWeights, matchingEventIds, visibleEventIds, referenceDate);
        const tagResults = searchTags(term, dynamicFrequencies);

        // Combine all results
        const allResults = new Map([...locationResults, ...eventResults, ...tagResults]);

        return Array.from(allResults.values());
    }

    // ========================================
    // RESULT GROUPING AND SORTING
    // ========================================

    /**
     * Groups search results by type and separates visible from hidden items
     * @param {Array} searchResults - Array of search result objects
     * @param {string} searchTerm - Current search term
     * @param {Function} getSelectedLocationKey - Function to get selected location key
     * @param {Function} getTagState - Function to get tag state
     * @returns {Object} Object with groupedResults and hiddenResults
     */
    function groupAndSortResults(searchResults, searchTerm, getSelectedLocationKey, getTagState) {
        const groupedResults = {
            locations: [],
            events: [],
            tags: []
        };

        const hiddenResults = {
            locations: [],
            events: [],
            tags: []
        };

        const hasSearchTerm = searchTerm && searchTerm.trim().length > 0;

        // Separate visible and hidden items
        searchResults.forEach(result => {
            const type = result.type;
            const targetGroup = (result.isVisible === false && !hasSearchTerm) ? hiddenResults : groupedResults;

            if (type === 'location') targetGroup.locations.push(result);
            else if (type === 'event') targetGroup.events.push(result);
            else if (type === 'tag') targetGroup.tags.push(result);
        });

        // Sort locations (selected location first, then by score)
        const selectedLocationKey = getSelectedLocationKey();
        const sortLocations = (a, b) => {
            const isASelected = a.ref === selectedLocationKey;
            const isBSelected = b.ref === selectedLocationKey;
            if (isASelected !== isBSelected) return isASelected ? -1 : 1;
            return (b.score || 0) - (a.score || 0);
        };

        groupedResults.locations.sort(sortLocations);
        hiddenResults.locations.sort((a, b) => (b.score || 0) - (a.score || 0));

        // Sort events by score
        groupedResults.events.sort((a, b) => (b.score || 0) - (a.score || 0));
        hiddenResults.events.sort((a, b) => (b.score || 0) - (a.score || 0));

        // Filter and sort tags (exclude selected/required/forbidden tags)
        const filterTags = (result) => {
            const tagState = getTagState(result.ref);
            return tagState === 'unselected' || tagState === 'implicit';
        };

        groupedResults.tags = groupedResults.tags.filter(filterTags);
        hiddenResults.tags = hiddenResults.tags.filter(filterTags);

        groupedResults.tags.sort((a, b) => (b.score || 0) - (a.score || 0));
        hiddenResults.tags.sort((a, b) => (b.score || 0) - (a.score || 0));

        return { groupedResults, hiddenResults };
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the SearchManager module
     * @param {Object} config - Configuration object
     * @param {Object} config.appState - Reference to app state
     */
    function init(config) {
        state.appState = config.appState;
    }

    /**
     * Performs a search and returns results
     * @param {string} term - Search term (will be normalized for accent/case-insensitive search)
     * @param {Object} dynamicFrequencies - Current dynamic tag frequencies
     * @param {Array<[string, string, number]>} selectedTagsWithColors - Array of [tag, color, weight] tuples
     * @returns {Array} Array of search results
     */
    function search(term, dynamicFrequencies, selectedTagsWithColors) {
        const normalizedTerm = Utils.normalizeForSearch(term);
        return performSearch(normalizedTerm, dynamicFrequencies, selectedTagsWithColors);
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        init,
        search,
        groupAndSortResults,

        // Export constants for testing/configuration
        SCORE_WEIGHTS,
        TIME_CONSTANTS,
        DISTANCE_THRESHOLDS
    };
})();
