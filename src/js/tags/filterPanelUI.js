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
        colorProvider: null,  // { getTagColor, assignColorToTag, unassignColorFromTag }

        // Section management - determined at init time based on device type
        sectionOrder: null,
        sectionViewStates: null,

        // Hierarchy data
        tagDescendantsOf: {},
        tagEmojiMap: {},

        // Chip bar
        getSelectedTagsWithColors: null
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
            ? ['tags', 'events', 'locations', 'organizers']
            : ['locations', 'events', 'tags', 'organizers'];
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
                tags: EXPANDED,
                organizers: EXPANDED
            };
        }
        return {
            locations: COLLAPSED,
            events: COLLAPSED,
            tags: DEFAULT,
            organizers: COLLAPSED
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
    // CHIP BAR
    // ========================================

    const CHIP_BAR_MAX_LINES = 3;
    const CHIP_BAR_RENDER_LIMIT = 100; // render up to this many, then trim to fit lines

    /**
     * Toggles a chip bar tag on/off.
     */
    function _handleChipClick(tagName) {
        const TAG_STATE = TagStateManager.getTagStateConstants();
        const currentState = TagStateManager.getTagState(tagName);

        if (currentState !== TAG_STATE.UNSELECTED) {
            state.tagStates[tagName] = TAG_STATE.UNSELECTED;
            if (state.colorProvider) {
                state.colorProvider.unassignColorFromTag(tagName);
            }
        } else {
            state.tagStates[tagName] = TAG_STATE.SELECTED;
            if (state.colorProvider) {
                state.colorProvider.assignColorToTag(tagName);
            }
        }

        if (state.onFilterChangeCallback) {
            state.onFilterChangeCallback();
        }
    }

    /**
     * Renders the unified chip bar showing selected tags + top unselected curated tags.
     * Called after every filter/search change via onAfterRender.
     */
    function _renderChipBar() {
        const container = document.getElementById('chip-bar');
        if (!container) return;

        const TAG_STATE = TagStateManager.getTagStateConstants();

        // 1. Collect selected tags (always shown first)
        const selectedTagsWithColors = state.getSelectedTagsWithColors
            ? state.getSelectedTagsWithColors()
            : [];
        const selectedTagNames = new Set(selectedTagsWithColors.map(([tag]) => tag));

        // 2. Score unselected curated tags using the same formula as SearchManager,
        //    plus descendant aggregation for parent categories.
        const hasSearch = state.searchTerm && state.searchTerm.trim().length > 0;
        const normalizedSearchTerm = hasSearch ? Utils.normalizeForSearch(state.searchTerm) : '';
        const visibleFreqs = state.getVisibleTagFrequencies ? state.getVisibleTagFrequencies() : {};

        const unselectedTags = [];
        for (const tag of state.allAvailableTags) {
            if (selectedTagNames.has(tag)) continue;
            const tagState = TagStateManager.getTagState(tag);
            if (tagState !== TAG_STATE.UNSELECTED) continue;

            const normalizedTag = Utils.normalizeForSearch(tag);

            // When searching, only include tags whose name matches the term
            if (hasSearch && !normalizedTag.includes(normalizedSearchTerm)) continue;

            const freq = state.currentDynamicFrequencies[tag] || 0;
            if (!hasSearch && freq <= 0) continue;

            // Base score: dynamic frequency (same as SearchManager)
            let score = freq;

            if (hasSearch) {
                // Exact match boost
                if (normalizedTag === normalizedSearchTerm) {
                    score += 1000;
                }
            }

            // Viewport visibility boost
            const visFreq = visibleFreqs[tag] || 0;
            if (visFreq > 0) {
                score += visFreq * 5;
                score += 5;
            }

            // Global frequency tiebreaker
            const globalFreq = state.initialGlobalFrequencies[tag] || 0;
            score += globalFreq * 0.01;

            // Descendant aggregation: parent tags get credit for children's scores
            const descendants = state.tagDescendantsOf[tag];
            if (descendants) {
                descendants.forEach(d => {
                    const dFreq = state.currentDynamicFrequencies[d] || 0;
                    const dVisFreq = visibleFreqs[d] || 0;
                    score += dFreq;
                    if (dVisFreq > 0) {
                        score += dVisFreq * 5 + 5;
                    }
                    score += (state.initialGlobalFrequencies[d] || 0) * 0.01;
                });
            }

            if (score <= 0) continue;

            unselectedTags.push({ tag, score });
        }

        // Sort unselected by descending score
        unselectedTags.sort((a, b) => b.score - a.score);

        // 4. Build DOM with generous limit, then trim to fit max lines
        const unselectedToRender = unselectedTags.slice(0, CHIP_BAR_RENDER_LIMIT);

        container.innerHTML = '';
        container.scrollLeft = 0;

        // Selected chips first
        for (const [tagName] of selectedTagsWithColors) {
            const btn = _createChipButton(tagName, true);
            container.appendChild(btn);
        }

        // Unselected chips
        for (const { tag } of unselectedToRender) {
            const btn = _createChipButton(tag, false);
            container.appendChild(btn);
        }

        const hasChips = selectedTagNames.size > 0 || unselectedToRender.length > 0;
        container.style.display = hasChips ? 'flex' : 'none';

        // Trim to max lines on desktop (mobile is single-row horizontal scroll)
        if (hasChips && !isMobileLayout()) {
            _trimChipBarToMaxLines(container);
            _updateChipBarLayout(container);
        }
    }

    /**
     * If fewer than 6 chips are visible inline, move chip bar to its own row.
     */
    function _updateChipBarLayout(container) {
        const filterContainer = document.getElementById('filter-container');
        if (!filterContainer) return;

        // Count chips visible within the container bounds
        const containerRect = container.getBoundingClientRect();
        let visibleCount = 0;
        for (const chip of container.children) {
            const chipRect = chip.getBoundingClientRect();
            if (chipRect.top < containerRect.bottom && chipRect.right <= containerRect.right + 1) {
                visibleCount++;
            }
        }

        const needsOwnRow = visibleCount < 6 && container.children.length >= 6;
        filterContainer.classList.toggle('chips-below', needsOwnRow);

        if (needsOwnRow) {
            // Align chip bar left edge with search bar (skip past logo)
            const logo = document.getElementById('logo-menu-wrapper');
            if (logo) {
                const gap = 10; // matches #filter-container > div:first-child gap
                container.style.marginLeft = (logo.offsetWidth + gap) + 'px';
            }
            // Re-trim after layout change since more chips may now fit
            _trimChipBarToMaxLines(container);
        } else {
            container.style.marginLeft = '';
        }
    }

    /**
     * Removes unselected chips that overflow past CHIP_BAR_MAX_LINES rows.
     * Measures actual rendered positions to account for variable chip widths.
     */
    function _trimChipBarToMaxLines(container) {
        const chips = container.children;
        if (chips.length === 0) return;

        // Find the top of the first chip to establish the baseline
        const firstTop = chips[0].offsetTop;
        let lineCount = 1;
        let prevTop = firstTop;

        for (let i = 1; i < chips.length; i++) {
            const chipTop = chips[i].offsetTop;
            if (chipTop > prevTop) {
                lineCount++;
                prevTop = chipTop;
            }
            if (lineCount > CHIP_BAR_MAX_LINES && !chips[i].classList.contains('active')) {
                // Remove this and all subsequent unselected chips
                while (container.children.length > i) {
                    container.removeChild(container.lastChild);
                }
                return;
            }
        }
    }

    /**
     * Creates a chip bar button element
     */
    function _createChipButton(tagName, isActive) {
        const btn = document.createElement('button');
        btn.className = 'chip-bar-chip';
        btn.dataset.primaryTag = tagName;
        btn.setAttribute('aria-label', `Filter by ${tagName}`);

        if (isActive) {
            btn.classList.add('active');
            if (state.colorProvider) {
                const color = state.colorProvider.getTagColor(tagName);
                if (color) {
                    btn.style.setProperty('--chip-color', color);
                }
            }
        }

        const emoji = state.tagEmojiMap[tagName] || '';
        if (emoji) {
            const emojiSpan = document.createElement('span');
            emojiSpan.className = 'chip-emoji';
            emojiSpan.setAttribute('aria-hidden', 'true');
            emojiSpan.textContent = emoji;
            btn.appendChild(emojiSpan);
        }
        btn.appendChild(document.createTextNode(tagName));

        btn.addEventListener('click', () => _handleChipClick(tagName));
        return btn;
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

        // Toggle panel height based on whether sections will be shown (desktop only)
        if (!isMobileLayout()) {
            const filterPanel = state.resultsContainerDOM.closest('#filter-panel');
            if (filterPanel) {
                const showSections = !!searchTerm || debugMode;
                filterPanel.classList.toggle('sections-hidden', !showSections);
            }
        }

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
            state.sectionViewStates.organizers = 'expanded';
        }

        // Group and sort results using SearchManager
        const { groupedResults, hiddenResults } = SearchManager.groupAndSortResults(
            searchResults,
            searchTerm,
            providers.getSelectedLocationKey,
            (tag) => TagStateManager.getTagState(tag)
        );

        // Render using SectionRenderer (onAfterRender distributes to bottom sheet on mobile)
        SectionRenderer.renderFilters(groupedResults, hiddenResults, searchTerm, debugMode);
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
        const organizerSection = container.querySelector('[data-section-key="organizers"]');

        if (locationSection) sections.locations = locationSection;
        if (eventSection) sections.events = eventSection;
        if (tagSection) sections.tags = tagSection;
        if (organizerSection) sections.organizers = organizerSection;

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
     */
    function init(config) {
        // Extract provider and assign rest to state
        state.colorProvider = config.colorProvider || null;
        state.allAvailableTags = config.allAvailableTags || [];
        state.tagConfigBgColors = config.tagConfigBgColors || [];
        state.tagDescendantsOf = config.tagDescendantsOf || {};
        state.tagEmojiMap = config.tagEmojiMap || {};
        state.getSelectedTagsWithColors = config.getSelectedTagsWithColors || null;
        state.resultsContainerDOM = config.resultsContainerDOM;
        state.onFilterChangeCallback = config.onFilterChangeCallback;
        state.onSearchResultClick = config.onSearchResultClick;
        state.defaultMarkerColor = config.defaultMarkerColor;
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
            onFilterChangeCallback: state.onFilterChangeCallback,
            defaultMarkerColor: state.defaultMarkerColor,
            tagEmojiMap: state.tagEmojiMap
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
                _renderChipBar();
            }
        });

        _renderChipBar();

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
        _renderChipBar();
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
        renderChipBar: _renderChipBar,
        clearSearch,
    };
})();
