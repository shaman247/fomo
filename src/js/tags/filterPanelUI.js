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

        // Section management - determined at init time based on device type
        sectionOrder: null,
        sectionViewStates: null,

        // Tag groups for quick filters and grouped tag display
        tagGroups: []
    };

    /**
     * Determines if the current window is mobile-sized
     * @returns {boolean} True if window width is at or below mobile breakpoint
     */
    function isMobileLayout() {
        const breakpoint = (typeof Constants !== 'undefined' && Constants.UI && Constants.UI.MOBILE_BREAKPOINT)
            ? Constants.UI.MOBILE_BREAKPOINT
            : 768;
        return window.innerWidth <= breakpoint;
    }

    /**
     * Gets the default section order based on device type
     * Desktop: locations, events, tags
     * Mobile: tags, events, locations
     * @returns {Array<string>} Section order array
     */
    function getDefaultSectionOrder() {
        return isMobileLayout()
            ? ['tags', 'events', 'locations']
            : ['locations', 'events', 'tags'];
    }

    /**
     * Gets the default section view states based on device type
     * Desktop: tags expanded, others collapsed
     * Mobile: all sections collapsed
     * @returns {Object} Section view states
     */
    function getDefaultSectionViewStates() {
        const COLLAPSED = 'collapsed';
        const DEFAULT = 'default';
        const EXPANDED = 'expanded';

        if (isMobileLayout()) {
            // On mobile, tabs show all content — no collapse buttons
            return {
                locations: EXPANDED,
                events: EXPANDED,
                tags: EXPANDED
            };
        }
        return {
            locations: COLLAPSED,
            events: COLLAPSED,
            tags: DEFAULT
        };
    }

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
    // QUICK FILTERS
    // ========================================

    /**
     * Renders quick filter chips from tag groups config.
     * Called once on init; active states are refreshed after each filter change.
     */
    function _renderQuickFilters() {
        const container = document.getElementById('quick-filters-row');
        if (!container || !state.tagGroups || state.tagGroups.length === 0) return;

        const quickFilters = state.tagGroups.filter(g => g.quickFilter);
        if (quickFilters.length === 0) return;

        container.innerHTML = '';
        quickFilters.forEach(group => {
            const btn = document.createElement('button');
            btn.className = 'quick-filter-chip';
            btn.dataset.primaryTag = group.primaryTag;
            btn.dataset.groupId = group.id;
            btn.setAttribute('aria-label', `Filter by ${group.label}`);
            btn.innerHTML = `<span class="chip-emoji" aria-hidden="true">${group.emoji}</span>${group.label}`;
            btn.addEventListener('click', () => _handleQuickFilterClick(group));
            container.appendChild(btn);
        });

        container.style.display = 'flex';
    }

    /**
     * Toggles the primary tag for a quick filter group on/off.
     */
    function _handleQuickFilterClick(group) {
        const TAG_STATE = TagStateManager.getTagStateConstants();
        const currentState = TagStateManager.getTagState(group.primaryTag);

        if (currentState !== TAG_STATE.UNSELECTED) {
            // Deselect: return to unselected
            state.tagStates[group.primaryTag] = TAG_STATE.UNSELECTED;
            if (state.colorProvider) {
                state.colorProvider.unassignColorFromTag(group.primaryTag);
            }
        } else {
            // Select: set to selected state and assign color
            state.tagStates[group.primaryTag] = TAG_STATE.SELECTED;
            if (state.colorProvider) {
                state.colorProvider.assignColorToTag(group.primaryTag);
            }
        }

        if (state.onFilterChangeCallback) {
            state.onFilterChangeCallback();
        }
    }

    /**
     * Updates active/inactive visual state on all quick filter chips
     * and re-sorts them: selected first, then by descending frequency.
     */
    function _updateQuickFilterActiveStates() {
        const container = document.getElementById('quick-filters-row');
        if (!container) return;

        const TAG_STATE = TagStateManager.getTagStateConstants();
        const chips = Array.from(container.querySelectorAll('.quick-filter-chip'));

        chips.forEach(btn => {
            const primaryTag = btn.dataset.primaryTag;
            const tagState = TagStateManager.getTagState(primaryTag);
            const isActive = tagState !== TAG_STATE.UNSELECTED;
            btn.classList.toggle('active', isActive);
            if (isActive && state.colorProvider) {
                const color = state.colorProvider.getTagColor(primaryTag);
                if (color) {
                    btn.style.setProperty('--chip-color', color);
                }
            } else {
                btn.style.removeProperty('--chip-color');
            }
        });

        // Sort: selected first, then search matches, then by descending frequency
        const searchTerm = state.searchTerm ? state.searchTerm.trim().toLowerCase() : '';
        chips.sort((a, b) => {
            const aActive = a.classList.contains('active') ? 1 : 0;
            const bActive = b.classList.contains('active') ? 1 : 0;
            if (aActive !== bActive) return bActive - aActive;

            if (searchTerm) {
                const aMatch = a.textContent.toLowerCase().includes(searchTerm) ? 1 : 0;
                const bMatch = b.textContent.toLowerCase().includes(searchTerm) ? 1 : 0;
                if (aMatch !== bMatch) return bMatch - aMatch;
            }

            const aFreq = state.currentDynamicFrequencies[a.dataset.primaryTag] || 0;
            const bFreq = state.currentDynamicFrequencies[b.dataset.primaryTag] || 0;
            return bFreq - aFreq;
        });

        chips.forEach(btn => container.appendChild(btn));
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

        // On mobile, force all sections expanded (tabs replace collapse/expand UI)
        if (isMobileLayout()) {
            state.sectionViewStates.locations = 'expanded';
            state.sectionViewStates.events = 'expanded';
            state.sectionViewStates.tags = 'expanded';
        }

        // Group and sort results using SearchManager
        const { groupedResults, hiddenResults } = SearchManager.groupAndSortResults(
            searchResults,
            searchTerm,
            providers.getSelectedLocationKey,
            (tag) => TagStateManager.getTagState(tag)
        );

        // Render using SectionRenderer (onAfterRender distributes to bottom sheet on mobile)
        SectionRenderer.renderFilters(groupedResults, hiddenResults, searchTerm);
    }

    /**
     * On mobile, distributes each section into its own tab in the bottom sheet.
     * The top bar keeps only search + date.
     */
    function _distributeContentMobile() {
        if (!isMobileLayout() || typeof BottomSheet === 'undefined') return;
        const container = state.resultsContainerDOM;
        if (!container) return;

        // Extract each section and pass to the bottom sheet's tab panels
        const sections = {};
        const locationSection = container.querySelector('[data-section-key="locations"]');
        const eventSection = container.querySelector('[data-section-key="events"]');
        const tagSection = container.querySelector('[data-section-key="tags"]');

        if (locationSection) sections.locations = locationSection;
        if (eventSection) sections.events = eventSection;
        if (tagSection) sections.tags = tagSection;

        BottomSheet.updateBrowseTabs(sections);
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
        state.tagGroups = config.tagGroups || [];
        state.resultsContainerDOM = config.resultsContainerDOM;
        state.onFilterChangeCallback = config.onFilterChangeCallback;
        state.onSearchResultClick = config.onSearchResultClick;
        state.defaultMarkerColor = config.defaultMarkerColor;
        state.initialGlobalFrequencies = { ...config.initialGlobalFrequencies };
        state.currentDynamicFrequencies = { ...config.initialGlobalFrequencies };

        if (config.getSearchTerm) {
            state.getSearchTerm = config.getSearchTerm;
        }

        // Initialize section order and view states based on device type (only on first init)
        if (!state.sectionOrder) {
            state.sectionOrder = getDefaultSectionOrder();
            state.sectionViewStates = getDefaultSectionViewStates();
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
            sectionViewStates: state.sectionViewStates,
            createSearchResultButton: (result) => TagStateManager.createSearchResultButton(result, state.onSearchResultClick, state.debugMode),
            onSectionReorder: (newOrder) => {
                state.sectionOrder = newOrder;
            },
            onAfterRender: () => {
                _distributeContentMobile();
                _updateQuickFilterActiveStates();
            }
        });

        _renderQuickFilters();

        // Initialize GestureHandler (desktop only — conflicts with horizontal tag scroll on mobile)
        if (!isMobileLayout()) {
            GestureHandler.init({
                containerDOM: state.resultsContainerDOM,
                sectionOrder: state.sectionOrder,
                onSectionReorder: (newOrder) => {
                    state.sectionOrder = newOrder;
                },
                performSearchCallback: () => performSearchCallback(state.searchTerm)
            });
        }
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
            const availableTagsSet = new Set(state.allAvailableTags);

            filteredEvents.forEach(event => {
                if (event.tags && Array.isArray(event.tags) && event.locationKey) {
                    event.tags.forEach(tag => {
                        if (availableTagsSet.has(tag)) {
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
        _updateQuickFilterActiveStates();
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
