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
    // Static enum object; TagStateManager loads earlier in script-tag order, so eager capture is safe.
    const TAG_STATE = TagStateManager.getTagStateConstants();

    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // Configuration
        allAvailableTags: [],
        resultsContainerDOM: null,
        onFilterChangeCallback: null,
        debugMode: false,

        // Frequencies (tag usage counts)
        initialGlobalFrequencies: {},
        currentDynamicFrequencies: {},

        // Tag states (managed by TagStateManager)
        tagStates: {},

        // Search state (SearchController handles input events)
        searchTerm: '',
        lastSearchResults: [],
        onSearchResultClick: null,
        getSearchTerm: null,

        // Provider objects
        colorProvider: null,  // { getTagColor, assignColorToTag, unassignColorFromTag }

        // Section management - determined at init time based on device type
        sectionOrder: null,

        // Hierarchy data
        tagDescendantsOf: {},
        tagParentsOf: {},
        tagChildrenOf: {},
        structuralFormatTags: new Set(),
        neighborhoodTags: new Set(),
        tagEmojiMap: {}
    };

    // Membership cache rebuilt at init and refreshAvailableTags. Normalized
    // canonical/alias terms are shared with SearchManager through app state.
    let _availableTagsSet = new Set();

    function _rebuildTagCaches() {
        _availableTagsSet = new Set(state.allAvailableTags);
    }

    /**
     * Gets the default section order based on device type
     * Desktop: locations, events, tags
     * Mobile: tags, events, locations
     * @returns {Array<string>} Section order array
     */
    function getDefaultSectionOrder() {
        return Utils.isMobileLayout()
            ? ['tags', 'events', 'locations', 'organizers']
            : ['locations', 'events', 'tags', 'organizers'];
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
    // FILTER PROFILING
    // ========================================

    // ----- Performance profiler (off by default; enable via window.FilterProfiler.enabled = true) -----
    // Used by the /profile-frontend skill to time interactions like chip clicks,
    // date changes, search, and pan. mark/measure are no-ops when no session
    // is active, so leaving the FP.mark calls in place has effectively zero cost.
    // For load-time profiling (Phase 2, etc.), set localStorage.fp_enabled='1' before reload.
    let _profilerEnabledFromStorage = false;
    try { _profilerEnabledFromStorage = localStorage.getItem('fp_enabled') === '1'; } catch (_) {}
    const FilterProfiler = {
        enabled: _profilerEnabledFromStorage,
        _active: false,
        _label: '',
        start(label) {
            if (!this.enabled) return;
            try { performance.clearMarks(); performance.clearMeasures(); } catch (_) {}
            this._active = true;
            this._label = label;
            performance.mark('fp:total:start');
        },
        mark(name) {
            if (!this._active) return;
            performance.mark(name);
        },
        measure(name, startMark, endMark) {
            if (!this._active) return;
            try { performance.measure(name, startMark, endMark); } catch (_) {}
        },
        flush() {
            if (!this._active) return;
            performance.mark('fp:total:end');
            try { performance.measure('fp:total', 'fp:total:start', 'fp:total:end'); } catch (_) {}
            const measures = performance.getEntriesByType('measure').filter(m => m.name.startsWith('fp:'));
            const total = measures.find(m => m.name === 'fp:total');
            const totalDur = total ? total.duration : 0;
            console.groupCollapsed(`%c[profile] ${this._label} — total ${totalDur.toFixed(1)}ms`,
                'color:#888;font-weight:normal');
            const others = measures.filter(m => m.name !== 'fp:total')
                .sort((a, b) => a.startTime - b.startTime);
            for (const m of others) {
                console.log(`  ${m.name.padEnd(28)} ${m.duration.toFixed(1).padStart(7)}ms`);
            }
            console.groupEnd();
            performance.clearMarks();
            performance.clearMeasures();
            this._active = false;
        },
        // Re-entrant wrapper. If a profiling session is already active (e.g.,
        // a chip click flow that calls performSearch internally), wrap() is a
        // no-op around fn so inner calls don't clobber the outer session.
        wrap(label, fn) {
            if (!this.enabled || this._active) return fn();
            this.start(label);
            try { return fn(); } finally { this.flush(); }
        }
    };
    if (typeof window !== 'undefined') window.FilterProfiler = FilterProfiler;

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
        state.debugMode = debugMode;

        if (!state.resultsContainerDOM) return;

        const sheet = (typeof Sheet !== 'undefined') ? Sheet : null;

        // A search term (or debug mode) auto-opens the sheet so the results are
        // visible as the user types (mobile: snaps the bottom sheet to peek).
        if (sheet && (searchTerm || debugMode)) {
            sheet.open();
        }

        // No search term: the sheet shows the nearby-events list view instead
        // of search sections. We only render it while the browse content is
        // actually on screen (skip rendering 200 cards off-screen on every map
        // pan); the sheet fires onToggle when it opens, triggering a re-render.
        if (!searchTerm && !debugMode && typeof ListView !== 'undefined') {
            const showList = (!sheet || sheet.isBrowseVisible()) && ListView.hasContent();
            if (showList) {
                ListView.render();
            } else {
                state.resultsContainerDOM.innerHTML = '';
                state.resultsContainerDOM.scrollTop = 0;
            }
            // Mirror SectionRenderer's onAfterRender: keep the tag selector in sync.
            TagSelector.refresh(); VenueSelector.refresh();
            return;
        }

        // A search term (or debug mode) takes over the results container — tear
        // down any list view that was showing.
        if (typeof ListView !== 'undefined') ListView.teardown();

        if (!searchResults || searchResults.length === 0) {
            state.resultsContainerDOM.innerHTML = '';
            state.resultsContainerDOM.scrollTop = 0;
            // Mirror SectionRenderer's onAfterRender so the tag selector resyncs
            // to the current term even when the search has no results.
            TagSelector.refresh(); VenueSelector.refresh();
            return;
        }

        FilterProfiler.mark('fp:panel:group-start');

        // Group and sort results using SearchManager
        const { groupedResults, hiddenResults } = SearchManager.groupAndSortResults(
            searchResults,
            searchTerm,
            providers.getSelectedLocationKey,
            (tag) => TagStateManager.getTagState(tag)
        );

        FilterProfiler.mark('fp:panel:group-end');
        FilterProfiler.measure('fp:panel:groupResults', 'fp:panel:group-start', 'fp:panel:group-end');

        // Render using SectionRenderer
        SectionRenderer.renderFilters(groupedResults, hiddenResults, searchTerm, debugMode);
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the FilterPanelUI module
     * @param {Object} config - Configuration object
     * @param {Array} config.allAvailableTags - All available tags
     * @param {Object} config.initialGlobalFrequencies - Initial tag frequencies
     * @param {HTMLElement} config.resultsContainerDOM - Container for search results
     * @param {Function} config.onFilterChangeCallback - Callback when filters change
     * @param {Function} config.onSearchResultClick - Callback when search result clicked
     * @param {Function} config.performSearch - Function to perform search
     * @param {Function} config.getSearchTerm - Function to get current search term
     * @param {Object} config.colorProvider - Provider for tag color operations
     * @param {Function} config.colorProvider.getTagColor - Get tag color
     * @param {Function} config.colorProvider.assignColorToTag - Assign color to tag
     * @param {Function} config.colorProvider.unassignColorFromTag - Unassign color from tag
     */
    function init(config) {
        // Extract provider and assign rest to state
        state.colorProvider = config.colorProvider || null;
        state.allAvailableTags = config.allAvailableTags || [];
        _rebuildTagCaches();
        state.tagDescendantsOf = config.tagDescendantsOf || {};
        state.tagParentsOf = config.tagParentsOf || {};
        state.tagChildrenOf = config.tagChildrenOf || {};
        // Structural Format nodes (Format root + its category children) are kept in
        // the hierarchy for grouping but never shown as chips. Prefer the value
        // computed in DataManager; fall back to deriving from the hierarchy here so
        // this never depends on init ordering.
        state.structuralFormatTags = config.structuralFormatTags
            || new Set(['Format', ...(((config.tagChildrenOf || {})['Format']) || [])]);
        state.neighborhoodTags = config.neighborhoodTags || new Set();
        state.tagEmojiMap = config.tagEmojiMap || {};
        state.getEventFilterTags = config.getEventFilterTags || (event => Utils.eventFilterTags(event));
        state.resultsContainerDOM = config.resultsContainerDOM;
        state.onFilterChangeCallback = config.onFilterChangeCallback;
        state.onSearchResultClick = config.onSearchResultClick;
        state.initialGlobalFrequencies = { ...config.initialGlobalFrequencies };
        state.currentDynamicFrequencies = { ...config.initialGlobalFrequencies };

        if (config.getSearchTerm) {
            state.getSearchTerm = config.getSearchTerm;
        }
        if (config.getVisibleTagFrequencies) {
            state.getVisibleTagFrequencies = config.getVisibleTagFrequencies;
        }

        // Initialize section order and view states based on device type (only on first init)
        if (!state.sectionOrder) {
            state.sectionOrder = getDefaultSectionOrder();
        }

        // Initialize tag states
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
            onFilterChangeCallback: state.onFilterChangeCallback,
            tagEmojiMap: state.tagEmojiMap
        });

        // Initialize SectionRenderer
        SectionRenderer.init({
            resultsContainerDOM: state.resultsContainerDOM,
            sectionOrder: state.sectionOrder,
            createSearchResultButton: (result) => TagStateManager.createSearchResultButton(result, state.onSearchResultClick, state.debugMode),
            onSectionReorder: (newOrder) => {
                state.sectionOrder = newOrder;
            },
            onAfterRender: () => {
                TagSelector.refresh(); VenueSelector.refresh();
            }
        });

        for (const selector of [TagSelector, VenueSelector]) selector.init({
            childrenOf: state.tagChildrenOf,
            names: state.allAvailableTags,
            onChange: state.onFilterChangeCallback,
        });

        // Initialize GestureHandler (desktop only — conflicts with horizontal tag scroll on mobile)
        if (!Utils.isMobileLayout()) {
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
     * Lightweight refresh used after Phase 2 data merge. Updates the available
     * tag list and global frequencies WITHOUT resetting `tagStates` — so any
     * tags the user clicked during Phase 1 stay selected. New tags introduced
     * by the full dataset are added as UNSELECTED. Tags that disappeared keep
     * their state but won't be rendered.
     *
     * Caller should follow this with `filterAndDisplayEvents()` to trigger
     * a normal render cycle that picks up the refreshed frequencies.
     */
    function refreshAvailableTags(updates = {}) {
        if (updates.allAvailableTags) {
            state.allAvailableTags = updates.allAvailableTags;
            for (const tag of state.allAvailableTags) {
                if (!(tag in state.tagStates)) {
                    state.tagStates[tag] = TAG_STATE.UNSELECTED;
                }
            }
            _rebuildTagCaches();
            TagSelector.configure(state.tagChildrenOf, state.allAvailableTags);
            VenueSelector.configure(state.tagChildrenOf, state.allAvailableTags);
        }
        if (updates.initialGlobalFrequencies) {
            state.initialGlobalFrequencies = { ...updates.initialGlobalFrequencies };
        }
    }

    /**
     * Updates the view with filtered events
     * @param {Array} filteredEvents - Array of filtered events
     */
    function updateView(filteredEvents) {
        FilterProfiler.mark('fp:updateView:start');

        state.currentDynamicFrequencies = {};
        state.allAvailableTags.forEach(tag => state.currentDynamicFrequencies[tag] = 0);

        if (filteredEvents && Array.isArray(filteredEvents)) {
            const tagLocationSets = {};

            filteredEvents.forEach(event => {
                if (event.locationKey) {
                    state.getEventFilterTags(event).forEach(tag => {
                        if (_availableTagsSet.has(tag)) {
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

        FilterProfiler.mark('fp:updateView:freq-done');
        FilterProfiler.measure('fp:updateView:freq', 'fp:updateView:start', 'fp:updateView:freq-done');

        performSearchCallback(state.getSearchTerm());

        FilterProfiler.mark('fp:updateView:end');
        FilterProfiler.measure('fp:updateView:performSearch', 'fp:updateView:freq-done', 'fp:updateView:end');
    }

    /**
     * Gets current tag states
     * @returns {Object} Live reference — treat as read-only. All consumers
     *     iterate immediately (HistoryManager copies what it keeps); none
     *     mutate or retain it across tag-state changes.
     */
    function getTagStates() {
        return state.tagStates;
    }

    /**
     * Gets current dynamic frequencies
     * @returns {Object} Live reference — treat as read-only (see getTagStates)
     */
    function getDynamicFrequencies() {
        return state.currentDynamicFrequencies;
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

        tagsToSelect.forEach(tag => {
            // Organizer pseudo-tags are valid filter keys even though they're not
            // in the browsable tag list — select them directly.
            if (Utils.isOrganizerTag(tag)) {
                const oldState = state.tagStates[tag];
                state.tagStates[tag] = TAG_STATE.SELECTED;
                if (oldState !== TAG_STATE.SELECTED && assignColorCallback) {
                    assignColorCallback(tag);
                }
                return;
            }

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
     * @param {Function} config.onSpecialSearchTerm - Callback for special search terms (debug, noto)
     */
    function initOmniSearch(config) {
        // Delegate to SearchController
        SearchController.init({
            onSpecialSearchTerm: config.onSpecialSearchTerm,
            performSearchCallback: performSearchCallback
        });
    }

    // ========================================
    // EXPORTS
    // ========================================

    /**
     * Re-render the panel with the last search/debug state. Used when the left
     * sheet opens so the (previously skipped) list view populates.
     */
    function rerender() {
        renderFilters(state.lastSearchResults || [], state.searchTerm || '', state.debugMode);
    }

    return {
        init,
        initOmniSearch,
        setAppProviders,
        refreshAvailableTags,
        updateView,
        getTagStates,
        getDynamicFrequencies,
        selectTags,
        setTagState: (tag, state) => TagStateManager.setTagState(tag, state),
        createInteractiveTagButton: (tag) => TagStateManager.createInteractiveTagButton(tag),
        updateAllTagVisuals: () => TagStateManager.updateAllTagVisuals(),
        render: renderFilters,
        refreshTagSelector: () => { TagSelector.refresh(); VenueSelector.refresh(); },
        rerender,
    };
})();
