/**
 * FilterPanelUI Module
 *
 * Orchestrates the filter panel UI by coordinating between specialized modules:
 * - TagStateManager: Manages tag states and button creation
 * - SectionRenderer: Renders collapsible search result sections
 * - GestureHandler: Handles swipe gestures for section reordering
 * - SearchController: Handles search input and special terms
 *
 * This module acts as the main coordinator for the filter panel which displays
 * search results across locations, events, and tags.
 *
 * @module FilterPanelUI
 */
const FilterPanelUI = (() => {
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
        debugMode: false,

        // Frequencies (tag usage counts)
        initialGlobalFrequencies: {},
        currentDynamicFrequencies: {},

        // Tag states (managed by TagStateManager)
        tagStates: {},

        // Search state (SearchController handles input events)
        searchTerm: '',
        lastSearchResults: [],
        lastSearchTerm: '',
        onSearchResultClick: null,
        getSearchTerm: null,

        // Provider objects
        colorProvider: null,  // { getTagColor, assignColorToTag, unassignColorFromTag, isImplicitlySelected }

        // Section management (managed by SectionRenderer)
        sectionOrder: ['locations', 'events', 'tags']
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
    // SEARCH HANDLING (delegated to SearchController)
    // ========================================

    /**
     * Clears the search input and results
     * Delegates to SearchController for input clearing
     */
    function clearSearch() {
        SearchController.clearSearch();
        state.searchTerm = '';
        renderFilters([]);
    }

    // ========================================
    // RENDERING COORDINATION
    // ========================================

    /**
     * Main render function that coordinates SearchManager and SectionRenderer
     * @param {Array} searchResults - Array of search results
     * @param {string} searchTerm - Current search term
     * @param {boolean} [debugMode=false] - Whether debug mode is enabled
     */
    function renderFilters(searchResults = [], searchTerm = '', debugMode = false) {
        state.searchTerm = searchTerm;
        state.lastSearchResults = searchResults;
        state.lastSearchTerm = searchTerm;
        state.debugMode = debugMode;

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
     * Initializes the FilterPanelUI module
     * @param {Object} config - Configuration object
     * @param {Array} config.allAvailableTags - All available tags
     * @param {Array} config.tagConfigBgColors - Background colors for tags
     * @param {Object} config.initialGlobalFrequencies - Initial tag frequencies
     * @param {HTMLElement} config.resultsContainerDOM - Container for search results
     * @param {Function} config.onFilterChangeCallback - Callback when filters change
     * @param {Function} config.onSearchResultClick - Callback when search result clicked
     * @param {string} config.defaultMarkerColor - Default marker color
     * @param {Function} config.performSearch - Function to perform search
     * @param {Function} config.getSearchTerm - Function to get current search term
     * @param {Object} config.colorProvider - Provider for tag color operations
     * @param {Function} config.colorProvider.getTagColor - Get tag color
     * @param {Function} config.colorProvider.assignColorToTag - Assign color to tag
     * @param {Function} config.colorProvider.unassignColorFromTag - Unassign color from tag
     * @param {Function} config.colorProvider.isImplicitlySelected - Check if tag is implicitly selected
     */
    function init(config) {
        // Extract provider and assign rest to state
        state.colorProvider = config.colorProvider || null;
        state.allAvailableTags = config.allAvailableTags || [];
        state.tagConfigBgColors = config.tagConfigBgColors || [];
        state.resultsContainerDOM = config.resultsContainerDOM;
        state.onFilterChangeCallback = config.onFilterChangeCallback;
        state.onSearchResultClick = config.onSearchResultClick;
        state.defaultMarkerColor = config.defaultMarkerColor;
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
            console.error("FilterPanelUI: resultsContainerDOM is not provided.");
            return;
        }

        performSearchCallback = config.performSearch || performSearchCallback;

        // Initialize TagStateManager with provider objects
        TagStateManager.init({
            tagStates: state.tagStates,
            colorProvider: state.colorProvider,
            relatedTagsProvider: {
                isImplicitlySelected: state.colorProvider?.isImplicitlySelected,
                isIncludingRelatedTags: () => SelectedTagsDisplay.isIncludingRelatedTags()
            },
            onFilterChangeCallback: state.onFilterChangeCallback,
            defaultMarkerColor: state.defaultMarkerColor
        });

        // Initialize SectionRenderer
        SectionRenderer.init({
            resultsContainerDOM: state.resultsContainerDOM,
            sectionOrder: state.sectionOrder,
            createSearchResultButton: (result) => TagStateManager.createSearchResultButton(result, state.onSearchResultClick, state.debugMode),
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
    // SEARCH INITIALIZATION
    // ========================================

    /**
     * Initialize the search input functionality
     * Delegates to SearchController for input handling
     * @param {Object} config - Configuration object
     * @param {HTMLElement} config.filterPanelDOM - Filter panel element (for mobile auto-expand)
     * @param {HTMLElement} config.expandFilterPanelButtonDOM - Expand button element (for mobile)
     * @param {Function} config.onSpecialSearchTerm - Callback for special search terms (debug, noto)
     */
    function initOmniSearch(config) {
        // Delegate to SearchController
        SearchController.init({
            filterPanelDOM: config.filterPanelDOM,
            expandFilterPanelButtonDOM: config.expandFilterPanelButtonDOM,
            onSpecialSearchTerm: config.onSpecialSearchTerm,
            performSearchCallback: performSearchCallback
        });
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        init,
        initOmniSearch,
        setAppProviders,
        populateInitialFilters,
        updateView,
        getTagStates,
        getDynamicFrequencies,
        resetSelections,
        selectTags,
        setTagState: (tag, state) => TagStateManager.setTagState(tag, state),
        createInteractiveTagButton: (tag) => TagStateManager.createInteractiveTagButton(tag),
        updateAllTagVisuals: () => TagStateManager.updateAllTagVisuals(),
        render: renderFilters,
        clearSearch,
    };
})();
