/**
 * TagFilterUI Module
 *
 * Orchestrates tag filtering UI by coordinating between specialized modules:
 * - TagStateManager: Manages tag states and button creation
 * - SectionRenderer: Renders collapsible search result sections
 * - GestureHandler: Handles swipe gestures for section reordering
 *
 * This module acts as the main coordinator and maintains the public API.
 *
 * @module TagFilterUI
 */
const TagFilterUI = (() => {
    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // Configuration
        allAvailableTags: [],
        tagConfigBgColors: [],
        resultsContainerDOM: null,
        onFilterChangeCallback: null,
        defaultMarkerColor: null,

        // Frequencies (tag usage counts)
        initialGlobalFrequencies: {},
        currentDynamicFrequencies: {},

        // Tag states (managed by TagStateManager)
        tagStates: {},

        // Search
        searchInputDOM: null,
        searchTerm: '',
        lastSearchResults: [],
        lastSearchTerm: '',
        onSearchResultClick: null,
        getSearchTerm: null,

        // Color management callbacks
        getTagColor: null,
        assignColorToTag: null,
        unassignColorFromTag: null,

        // Section management (managed by SectionRenderer)
        sectionOrder: ['locations', 'events', 'tags'],
        sectionViewStates: {
            locations: null, // Will be set to SECTION_VIEW_STATE.DEFAULT
            events: null,
            tags: null
        }
    };

    /**
     * Provider functions from parent application
     */
    const providers = {
        getSelectedLocationKey: () => null,
    };

    /**
     * Callback to perform search operations
     */
    let performSearchCallback = () => {};

    // ========================================
    // SEARCH HANDLING
    // ========================================

    /**
     * Handles keydown events in the search input
     * @param {KeyboardEvent} e - Keyboard event
     */
    function handleSearchKeydown(e) {
        if (e.key === 'Escape') {
            clearSearch(state.searchInputDOM.value);
        }
    }

    /**
     * Clears the search input and results
     * @param {string} currentTerm - Current search term
     */
    function clearSearch(currentTerm) {
        if (state.searchInputDOM) {
            state.searchInputDOM.value = '';
        }
        state.searchTerm = currentTerm || '';
        render([]);
        state.searchInputDOM.blur();
    }

    // ========================================
    // RENDERING COORDINATION
    // ========================================

    /**
     * Main render function that coordinates SearchManager and SectionRenderer
     * @param {Array} searchResults - Array of search results
     * @param {string} searchTerm - Current search term
     */
    function renderFilters(searchResults = [], searchTerm = '') {
        state.searchTerm = searchTerm;
        state.lastSearchResults = searchResults;
        state.lastSearchTerm = searchTerm;

        if (!state.resultsContainerDOM) return;

        if (!searchResults || searchResults.length === 0) {
            state.resultsContainerDOM.innerHTML = '';
            state.resultsContainerDOM.scrollTop = 0;
            return;
        }

        // Group and sort results using SearchManager
        const { groupedResults, hiddenResults } = SearchManager.groupAndSortResults(
            searchResults,
            searchTerm,
            providers.getSelectedLocationKey,
            (tag) => TagStateManager.getTagState(tag)
        );

        // Render using SectionRenderer
        SectionRenderer.renderFilters(groupedResults, hiddenResults, searchTerm);
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the TagFilterUI module
     * @param {Object} config - Configuration object
     */
    function init(config) {
        Object.assign(state, config);
        state.initialGlobalFrequencies = { ...config.initialGlobalFrequencies };
        state.currentDynamicFrequencies = { ...config.initialGlobalFrequencies };

        if (config.getSearchTerm) {
            state.getSearchTerm = config.getSearchTerm;
        }

        // Initialize tag states
        const TAG_STATE = TagStateManager.getTagStateConstants();
        state.allAvailableTags.forEach(tag => {
            state.tagStates[tag] = TAG_STATE.UNSELECTED;
        });

        if (!state.resultsContainerDOM) {
            console.error("tagFilterUI: resultsContainerDOM is not provided.");
            return;
        }

        performSearchCallback = config.performSearch || performSearchCallback;
        state.searchInputDOM = document.getElementById('omni-search-input');

        if (state.searchInputDOM) {
            state.searchInputDOM.addEventListener('keydown', handleSearchKeydown);
        }

        // Initialize section view states
        const SECTION_VIEW_STATE = SectionRenderer.getSectionViewState();
        state.sectionViewStates = {
            locations: SECTION_VIEW_STATE.DEFAULT,
            events: SECTION_VIEW_STATE.DEFAULT,
            tags: SECTION_VIEW_STATE.DEFAULT
        };

        // Initialize TagStateManager
        TagStateManager.init({
            tagStates: state.tagStates,
            getTagColor: state.getTagColor,
            assignColorToTag: state.assignColorToTag,
            unassignColorFromTag: state.unassignColorFromTag,
            onFilterChangeCallback: state.onFilterChangeCallback,
            defaultMarkerColor: state.defaultMarkerColor
        });

        // Initialize SectionRenderer
        SectionRenderer.init({
            resultsContainerDOM: state.resultsContainerDOM,
            sectionOrder: state.sectionOrder,
            sectionViewStates: state.sectionViewStates,
            createSearchResultButton: (result) => TagStateManager.createSearchResultButton(result, state.onSearchResultClick),
            onSectionReorder: (newOrder) => {
                state.sectionOrder = newOrder;
            }
        });

        // Initialize GestureHandler
        GestureHandler.init({
            containerDOM: state.resultsContainerDOM,
            sectionOrder: state.sectionOrder,
            onSectionReorder: (newOrder) => {
                state.sectionOrder = newOrder;
            },
            performSearchCallback: () => performSearchCallback(state.searchTerm)
        });
    }

    /**
     * Sets application-level providers
     * @param {Object} appProviders - Provider functions
     */
    function setAppProviders(appProviders) {
        Object.assign(providers, appProviders);
    }

    /**
     * Populates initial filters
     */
    function populateInitialFilters() {
        const TAG_STATE = TagStateManager.getTagStateConstants();
        state.currentDynamicFrequencies = { ...state.initialGlobalFrequencies };
        state.allAvailableTags.forEach(tag => {
            state.tagStates[tag] = TAG_STATE.UNSELECTED;
        });
        renderFilters();
    }

    /**
     * Updates the view with filtered events
     * @param {Array} filteredEvents - Array of filtered events
     */
    function updateView(filteredEvents) {
        state.currentDynamicFrequencies = {};
        state.allAvailableTags.forEach(tag => state.currentDynamicFrequencies[tag] = 0);

        if (filteredEvents && Array.isArray(filteredEvents)) {
            const tagLocationSets = {};

            filteredEvents.forEach(event => {
                if (event.tags && Array.isArray(event.tags) && event.locationKey) {
                    event.tags.forEach(tag => {
                        if (state.allAvailableTags.includes(tag)) {
                            if (!tagLocationSets[tag]) {
                                tagLocationSets[tag] = new Set();
                            }
                            tagLocationSets[tag].add(event.locationKey);
                        }
                    });
                }
            });

            for (const tag in tagLocationSets) {
                state.currentDynamicFrequencies[tag] = tagLocationSets[tag].size;
            }
        }

        performSearchCallback(state.getSearchTerm());
    }

    /**
     * Gets current tag states
     * @returns {Object} Copy of tag states
     */
    function getTagStates() {
        return { ...state.tagStates };
    }

    /**
     * Gets current dynamic frequencies
     * @returns {Object} Copy of dynamic frequencies
     */
    function getDynamicFrequencies() {
        return { ...state.currentDynamicFrequencies };
    }

    /**
     * Resets all tag selections
     */
    function resetSelections() {
        const TAG_STATE = TagStateManager.getTagStateConstants();
        state.allAvailableTags.forEach(tag => {
            state.tagStates[tag] = TAG_STATE.UNSELECTED;
        });
        clearSearch('');
    }

    /**
     * Programmatically selects tags (used for URL parameters)
     * @param {Array<string>} tagsToSelect - Array of tag names to select
     * @param {Function} assignColorCallback - Callback to assign colors to selected tags
     */
    function selectTags(tagsToSelect, assignColorCallback) {
        if (!Array.isArray(tagsToSelect)) {
            return;
        }

        const TAG_STATE = TagStateManager.getTagStateConstants();

        tagsToSelect.forEach(tag => {
            // Try exact match first, then case-insensitive match
            let matchedTag = tag;
            if (!state.allAvailableTags.includes(tag)) {
                matchedTag = state.allAvailableTags.find(t => t.toLowerCase() === tag.toLowerCase());
            }

            if (matchedTag && state.allAvailableTags.includes(matchedTag)) {
                const oldState = state.tagStates[matchedTag];
                state.tagStates[matchedTag] = TAG_STATE.SELECTED;

                // Assign color if transitioning from unselected
                if (oldState === TAG_STATE.UNSELECTED && assignColorCallback) {
                    assignColorCallback(matchedTag);
                }
            } else {
                console.warn(`Tag "${tag}" not found in available tags`);
            }
        });
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        init,
        setAppProviders,
        populateInitialFilters,
        updateView,
        getTagStates,
        getDynamicFrequencies,
        resetSelections,
        selectTags,
        createInteractiveTagButton: (tag) => TagStateManager.createInteractiveTagButton(tag),
        render: renderFilters,
        clearSearch,
    };
})();
