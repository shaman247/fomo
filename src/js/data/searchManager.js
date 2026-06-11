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
     * Scoring weights for different match types
     */
    const SCORE_WEIGHTS = {
        MATCHING_BOOST: 10,        // Boost for items matching current filters
        MULTI_TAG_MATCH: 3,        // Points per matched tag (when 2+ tags selected)
        VISIBILITY_BOOST: 5,       // Boost for currently visible items
        MAX_PROXIMITY_BONUS: 5,    // Max points for proximity to map center
        EXACT_TAG_MATCH: 1000,     // Large boost for exact tag matches
        VISIBLE_TAG_MULTIPLIER: 5, // Multiplier for visible tag frequency
        GLOBAL_FREQ_TIEBREAKER: 0.01 // Global tag frequency tiebreaker
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
     * Counts how many selected tags match an item's tags
     * @param {Set} itemTags - Set of tags for the item
     * @param {Set} selectedTags - Set of currently selected tags
     * @returns {number} Number of matching tags
     */
    function countMatchingTags(itemTags, selectedTags) {
        if (selectedTags.size < 2) return 0;
        return [...itemTags].filter(tag => selectedTags.has(tag)).length;
    }

    // ========================================
    // SEARCH FUNCTIONS
    // ========================================

    /**
     * Scores a location and creates a result object
     */
    function scoreLocation(key, location, isVisible, isMatching, selectedTags) {
        let score = 1;

        if (isMatching) {
            score += SCORE_WEIGHTS.MATCHING_BOOST;
        }

        if (selectedTags.size >= 2 && location.tags) {
            score += countMatchingTags(new Set(location.tags), selectedTags) * SCORE_WEIGHTS.MULTI_TAG_MATCH;
        }

        const distance = state.appState.locationDistances[key] || 0;
        score += calculateProximityBonus(distance, SCORE_WEIGHTS.MAX_PROXIMITY_BONUS, Constants.DISTANCE.MAX_PROXIMITY_METERS);

        if (isVisible) {
            score += SCORE_WEIGHTS.VISIBILITY_BOOST;
        }

        return {
            type: 'location',
            ref: key,
            displayName: Utils.getDisplayName(location),
            emoji: location.emoji,
            score: score,
            isVisible: isVisible
        };
    }

    function searchLocations(term, selectedTags, matchingLocationKeys, visibleLocationKeys) {
        const results = [];
        const hasSearchTerm = term.length > 0;

        if (hasSearchTerm) {
            // With a search term, scan all locations for text matches
            const searchIndex = state.appState.searchIndex;
            for (const key in state.appState.locationsByLatLng) {
                const normalizedText = searchIndex?.locations?.get(key) || '';
                if (normalizedText.includes(term)) {
                    const location = state.appState.locationsByLatLng[key];
                    const isVisible = visibleLocationKeys.has(key);
                    const isMatching = matchingLocationKeys.has(key);
                    results.push(scoreLocation(key, location, isVisible, isMatching, selectedTags));
                }
            }
        } else {
            // Without a search term, only iterate visible + limited matching locations
            const HIDDEN_LIMIT = 100;

            // All visible matching locations
            for (const key of visibleLocationKeys) {
                const location = state.appState.locationsByLatLng[key];
                if (location) {
                    results.push(scoreLocation(key, location, true, matchingLocationKeys.has(key), selectedTags));
                }
            }

            // Limited hidden (matching but not visible) locations
            let hiddenCount = 0;
            for (const key of matchingLocationKeys) {
                if (hiddenCount >= HIDDEN_LIMIT) break;
                if (visibleLocationKeys.has(key)) continue;
                const location = state.appState.locationsByLatLng[key];
                if (location) {
                    results.push(scoreLocation(key, location, false, true, selectedTags));
                    hiddenCount++;
                }
            }
        }

        return results;
    }

    /**
     * Searches events based on the search term and current filters
     * @param {string} term - Search term (already normalized)
     * @param {Map} selectedTags - Map of tag -> weight
     * @param {Set} matchingEventIds - Set of event IDs matching current filters
     * @param {Set} visibleEventIds - Set of currently visible event IDs
     * @returns {Array} Array of event results
     */
    /**
     * Scores an event and creates a result object
     * @param {Object} event - Event object
     * @param {boolean} isVisible - Whether event is in viewport
     * @param {boolean} isMatching - Whether event matches current filters
     * @param {Map} selectedTags - Map of tag -> weight
     * @returns {Object} Result object
     */
    function scoreEvent(event, isVisible, isMatching, selectedTags) {
        let score = 1;

        if (isMatching) {
            score += SCORE_WEIGHTS.MATCHING_BOOST;
        }

        if (selectedTags.size >= 2) {
            const locationInfo = event.locationKey ? state.appState.locationsByLatLng[event.locationKey] : null;
            const combinedTags = new Set([...(event.tags || []), ...(locationInfo?.tags || [])]);
            score += countMatchingTags(combinedTags, selectedTags) * SCORE_WEIGHTS.MULTI_TAG_MATCH;
        }

        if (event.locationKey) {
            const distance = state.appState.locationDistances[event.locationKey] || 0;
            score += calculateProximityBonus(distance, SCORE_WEIGHTS.MAX_PROXIMITY_BONUS, Constants.DISTANCE.MAX_PROXIMITY_METERS);
        }

        if (isVisible) {
            score += SCORE_WEIGHTS.VISIBILITY_BOOST;
        }

        // Display name is precomputed at data load (avoids per-search textarea creation
        // via Utils.formatAndSanitize). Falls back to live computation if cache missing.
        const cachedName = state.appState.searchIndex?.eventDisplayNames?.get(event.id);
        const displayName = cachedName !== undefined
            ? cachedName
            : Utils.formatAndSanitize(Utils.getDisplayName(event)).replace(/<\/?em>/g, '');

        return {
            type: 'event',
            ref: event.id,
            displayName,
            emoji: event.emoji,
            score: score,
            isVisible: isVisible
        };
    }

    function searchEvents(term, selectedTags, matchingEventIds, visibleEventIds) {
        const results = [];
        const hasSearchTerm = term.length > 0;

        if (hasSearchTerm) {
            // With a search term, scan all events for text matches
            const searchIndex = state.appState.searchIndex;
            state.appState.allEvents.forEach(event => {
                const normalizedText = searchIndex?.events?.get(event.id) || '';
                if (normalizedText.includes(term)) {
                    const isVisible = visibleEventIds.has(event.id);
                    const isMatching = matchingEventIds.has(event.id);
                    results.push(scoreEvent(event, isVisible, isMatching, selectedTags));
                }
            });
        } else {
            // Without a search term, use pre-computed visible/matching sets
            // instead of scanning all events
            const HIDDEN_LIMIT = 100;
            const visibleEvents = state.appState.currentlyVisibleMatchingEvents;
            const matchingEvents = state.appState.currentlyMatchingEvents;
            const visibleIds = new Set(visibleEvents.map(e => e.id));

            // All visible matching events
            for (const event of visibleEvents) {
                results.push(scoreEvent(event, true, true, selectedTags));
            }

            // Limited hidden (matching but not visible) events
            let hiddenCount = 0;
            for (const event of matchingEvents) {
                if (hiddenCount >= HIDDEN_LIMIT) break;
                if (visibleIds.has(event.id)) continue;
                results.push(scoreEvent(event, false, true, selectedTags));
                hiddenCount++;
            }
        }

        return results;
    }

    /**
     * Scores a single tag's relevance signal. Shared by searchTags, the chip
     * bar, and the descendant dropdown (FilterPanelUI) so tuning SCORE_WEIGHTS
     * keeps all three rankings in sync.
     * @param {Object} signal
     * @param {number} signal.dynamicFreq - Dynamic (filter-scoped) tag frequency
     * @param {number} signal.visibleFreq - Proximity-weighted visible tag frequency
     * @param {number} signal.globalFreq - Global tag frequency (tiebreaker)
     * @param {boolean} signal.isExactMatch - Search term exactly matches the tag
     * @returns {number} Relevance score
     */
    function scoreTagSignal({ dynamicFreq, visibleFreq, globalFreq, isExactMatch }) {
        let score = dynamicFreq;

        // Boost score significantly for exact matches
        if (isExactMatch) {
            score += SCORE_WEIGHTS.EXACT_TAG_MATCH;
        }

        // Add proximity-weighted score for visible tags
        if (visibleFreq > 0) {
            score += visibleFreq * SCORE_WEIGHTS.VISIBLE_TAG_MULTIPLIER;
            score += SCORE_WEIGHTS.VISIBILITY_BOOST;
        }

        // Add global frequency tiebreaker
        score += globalFreq * SCORE_WEIGHTS.GLOBAL_FREQ_TIEBREAKER;

        return score;
    }

    /**
     * Searches tags based on the search term and current filters
     * @param {string} term - Search term (already normalized)
     * @param {Object} dynamicFrequencies - Current dynamic tag frequencies
     * @returns {Array} Array of tag results
     */
    function searchTags(term, dynamicFrequencies) {
        const results = [];
        const searchIndex = state.appState.searchIndex;

        // Empty term: skip geotags via precomputed list. Term: keep all hierarchy tags.
        // (allAvailableTags is already hierarchy-filtered at load — no per-iteration check needed.)
        const tagList = !term && state.appState.searchableTagsForEmptyTerm
            ? state.appState.searchableTagsForEmptyTerm
            : state.appState.allAvailableTags;

        tagList.forEach(tag => {
            // Use normalized index for matching
            const normalizedTag = searchIndex?.tags?.get(tag) || tag.toLowerCase();
            if (normalizedTag.includes(term)) {
                const visibleFreq = state.appState.visibleTagFrequencies[tag] || 0;

                const score = scoreTagSignal({
                    dynamicFreq: dynamicFrequencies[tag] || 0,
                    visibleFreq,
                    globalFreq: state.appState.tagFrequencies[tag] || 0,
                    isExactMatch: normalizedTag === term
                });

                results.push({
                    type: 'tag',
                    ref: tag,
                    score: score,
                    isVisible: visibleFreq > 0
                });
            }
        });

        return results;
    }

    /**
     * Searches organizers based on the search term
     * @param {string} term - Search term (already normalized)
     * @returns {Array} Array of organizer results
     */
    function searchOrganizers(term) {
        const results = [];
        if (!term || !state.appState.organizersById) return results;

        const searchIndex = state.appState.searchIndex;
        const matchingEvents = state.appState.currentlyMatchingEvents;

        // Build organizer -> matching event count lookup. A merged event can have
        // several organizers (organizer_ids), each counted toward its own total.
        const orgEventCounts = {};
        for (const event of matchingEvents) {
            for (const orgId of (event.organizer_ids || [])) {
                const key = String(orgId);
                orgEventCounts[key] = (orgEventCounts[key] || 0) + 1;
            }
        }

        for (const [id, org] of Object.entries(state.appState.organizersById)) {
            const normalizedText = searchIndex?.organizers?.get(id) || Utils.normalizeForSearch(org.name || '');
            if (!normalizedText.includes(term)) continue;

            const matchCount = orgEventCounts[id] || 0;
            let score = matchCount;

            // Exact match boost
            if (normalizedText === term) {
                score += SCORE_WEIGHTS.EXACT_TAG_MATCH;
            }

            results.push({
                type: 'organizer',
                ref: id,
                displayName: org.name,
                emoji: org.emoji || null,
                score: score,
                isVisible: matchCount > 0,
                eventCount: matchCount
            });
        }

        return results;
    }

    /**
     * Main search function that searches across locations, events, and tags
     * @param {string} term - Search term (lowercase)
     * @param {Object} dynamicFrequencies - Current dynamic tag frequencies
     * @param {Array<[string, string]>} selectedTagsWithColors - Array of [tag, color] tuples
     * @returns {Array} Array of search results
     */
    function performSearch(term, dynamicFrequencies, selectedTagsWithColors) {
        const hasSearchTerm = term.length > 0;

        // Create a set of selected tags for scoring
        const selectedTags = new Set(selectedTagsWithColors.map(([tag]) => tag));

        const matchingLocationKeys = state.appState.currentlyMatchingLocationKeys;
        const visibleLocationKeys = state.appState.currentlyVisibleMatchingLocationKeys;

        // Only build expensive event ID Sets when needed (text search requires membership checks)
        const matchingEventIds = hasSearchTerm ? new Set(state.appState.currentlyMatchingEvents.map(e => e.id)) : null;
        const visibleEventIds = hasSearchTerm ? new Set(state.appState.currentlyVisibleMatchingEvents.map(e => e.id)) : null;

        // Perform searches
        const locationResults = searchLocations(term, selectedTags, matchingLocationKeys, visibleLocationKeys);
        const eventResults = searchEvents(term, selectedTags, matchingEventIds, visibleEventIds);
        const tagResults = searchTags(term, dynamicFrequencies);
        const organizerResults = searchOrganizers(term);

        // Combine all results (each search yields unique items, so no dedup is needed)
        return [...locationResults, ...eventResults, ...tagResults, ...organizerResults];
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
            tags: [],
            organizers: []
        };

        const hiddenResults = {
            locations: [],
            events: [],
            tags: [],
            organizers: []
        };

        const hasSearchTerm = searchTerm && searchTerm.trim().length > 0;

        // Separate visible and hidden items
        searchResults.forEach(result => {
            const type = result.type;
            const targetGroup = (result.isVisible === false && !hasSearchTerm) ? hiddenResults : groupedResults;

            if (type === 'location') targetGroup.locations.push(result);
            else if (type === 'event') targetGroup.events.push(result);
            else if (type === 'tag') targetGroup.tags.push(result);
            else if (type === 'organizer') targetGroup.organizers.push(result);
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
            return tagState === 'unselected';
        };

        groupedResults.tags = groupedResults.tags.filter(filterTags);
        hiddenResults.tags = hiddenResults.tags.filter(filterTags);

        groupedResults.tags.sort((a, b) => (b.score || 0) - (a.score || 0));
        hiddenResults.tags.sort((a, b) => (b.score || 0) - (a.score || 0));

        // Sort organizers by score
        groupedResults.organizers.sort((a, b) => (b.score || 0) - (a.score || 0));
        hiddenResults.organizers.sort((a, b) => (b.score || 0) - (a.score || 0));

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
     * @param {Array<[string, string]>} selectedTagsWithColors - Array of [tag, color] tuples
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
        scoreTagSignal
    };
})();
