/**
 * SectionRenderer Module
 *
 * Handles rendering of search result sections with collapsible/expandable functionality.
 * Manages section display states, collapse thresholds, and scroll position preservation.
 *
 * Features:
 * - Render search result sections (locations, events, tags)
 * - Collapse/expand sections with dynamic threshold calculation
 * - Show more/fewer buttons for section visibility control
 * - Scroll position preservation during re-renders
 * - Section toggle and reordering support
 *
 * @module SectionRenderer
 */
const SectionRenderer = (() => {
    // ========================================
    // CONSTANTS
    // ========================================

    /**
     * View states for result sections
     * @enum {string}
     */
    const SECTION_VIEW_STATE = {
        COLLAPSED: 'collapsed',   // Show limited results based on thresholds
        DEFAULT: 'default',       // Hide isVisible=false items
        EXPANDED: 'expanded'      // Show all items including isVisible=false
    };

    /**
     * Target number of lines to show when a section is collapsed
     */
    const TARGET_COLLAPSED_LINES = {
        small: 2,  // Mobile/small windows
        large: 5   // Desktop/large windows
    };

    /**
     * Metadata for each result section type
     */
    const SECTION_METADATA = {
        locations: {
            title: 'Places',
            icon: '<svg xmlns="http://www.w3.org/2000/svg" height="18px" viewBox="0 0 24 24" width="18px" fill="currentColor" aria-hidden="true"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>',
            estimatedItemsPerLine: { small: 1.5, large: 3 }
        },
        events: {
            title: 'Events',
            icon: '<svg xmlns="http://www.w3.org/2000/svg" height="18px" viewBox="0 0 24 24" width="18px" fill="currentColor" aria-hidden="true"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM7 10h5v5H7v-5z"/></svg>',
            estimatedItemsPerLine: { small: 1.2, large: 2.5 }
        },
        tags: {
            title: 'Tags',
            icon: '<svg xmlns="http://www.w3.org/2000/svg" height="18px" viewBox="0 0 24 24" width="18px" fill="currentColor" aria-hidden="true"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M21.41 11.58l-9-9C12.05 2.22 11.55 2 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l9 9c.36.36.86.58 1.41.58s1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41s-.23-1.06-.59-1.42zM5.5 7C4.67 7 4 6.33 4 5.5S4.67 4 5.5 4 7 4.67 7 5.5 6.33 7 5.5 7z"/></svg>',
            estimatedItemsPerLine: { small: 2.5, large: 5 }
        }
    };

    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // DOM elements
        resultsContainerDOM: null,

        // Section state
        sectionOrder: ['locations', 'events', 'tags'],
        sectionViewStates: {
            locations: SECTION_VIEW_STATE.DEFAULT,
            events: SECTION_VIEW_STATE.DEFAULT,
            tags: SECTION_VIEW_STATE.DEFAULT
        },

        // Search state
        searchTerm: '',
        lastSearchResults: [],
        lastSearchTerm: '',

        // Callbacks
        createSearchResultButton: null,
        onSectionReorder: null
    };

    // ========================================
    // UTILITY FUNCTIONS
    // ========================================

    /**
     * Determines if the current window is small (mobile-like)
     * @returns {boolean} True if window width is less than mobile breakpoint
     */
    function isSmallWindow() {
        return window.innerWidth < Constants.UI.MOBILE_BREAKPOINT;
    }

    // ========================================
    // COLLAPSE/EXPAND LOGIC
    // ========================================

    /**
     * Estimates the collapse threshold before rendering
     * Used for initial layout calculations
     * @param {string} sectionKey - Section identifier (locations/events/tags)
     * @returns {number} Estimated number of items to show when collapsed
     */
    function getEstimatedCollapseThreshold(sectionKey) {
        const targetLines = isSmallWindow() ? TARGET_COLLAPSED_LINES.small : TARGET_COLLAPSED_LINES.large;
        const metadata = SECTION_METADATA[sectionKey];

        if (!metadata) return Math.max(1, Math.floor(targetLines * 2));

        const itemsPerLine = isSmallWindow()
            ? metadata.estimatedItemsPerLine.small
            : metadata.estimatedItemsPerLine.large;

        return Math.max(1, Math.floor(targetLines * itemsPerLine));
    }

    /**
     * Calculates precise collapse threshold based on actual DOM measurements
     * This is called during rendering with actual DOM elements to determine
     * how many items fit within the target number of lines
     *
     * @param {HTMLElement} sectionWrapper - Section container element
     * @param {HTMLElement[]} items - Array of item elements to measure
     * @returns {number} Number of items that fit in target lines
     */
    function calculateCollapseThreshold(sectionWrapper, items) {
        if (items.length === 0) return 3;

        const targetLines = isSmallWindow() ? TARGET_COLLAPSED_LINES.small : TARGET_COLLAPSED_LINES.large;
        const lineHeight = 32; // Approximate line height for tag buttons with padding/margin
        const maxHeight = lineHeight * targetLines;

        // Create temporary container for measurement
        const tempContainer = document.createElement('div');
        tempContainer.style.cssText = 'position: absolute; visibility: hidden; width: ' + sectionWrapper.offsetWidth + 'px;';
        tempContainer.className = sectionWrapper.className;
        document.body.appendChild(tempContainer);

        // Clone the icon button (it takes up horizontal space in the flexbox)
        const iconButton = sectionWrapper.querySelector('.section-icon-button');
        if (iconButton) {
            const tempIconButton = iconButton.cloneNode(true);
            tempContainer.appendChild(tempIconButton);
        }

        // Create a temporary show more button to account for its space
        const tempShowMoreButton = document.createElement('button');
        tempShowMoreButton.className = 'tag-button state-cycle-button';
        tempShowMoreButton.textContent = '+';

        let count = 0;

        // Add items one by one until we exceed the target height
        for (let i = 0; i < items.length; i++) {
            const testElement = items[i].cloneNode(true);
            tempContainer.appendChild(testElement);
            tempContainer.appendChild(tempShowMoreButton);

            const heightWithButton = tempContainer.offsetHeight;
            tempContainer.removeChild(tempShowMoreButton);

            // Check if adding this item plus the button would exceed our target
            if (heightWithButton > maxHeight && count > 0) {
                tempContainer.removeChild(testElement);
                break;
            }

            count++;
        }

        document.body.removeChild(tempContainer);
        return Math.max(1, Math.min(count, items.length));
    }

    // ========================================
    // SCROLL POSITION PRESERVATION
    // ========================================

    /**
     * Re-renders the filter UI while keeping a reference element in the same visual position
     * This prevents jarring scroll jumps when expanding/collapsing sections
     *
     * @param {HTMLElement} referenceElement - Element to keep in the same position (button or section wrapper)
     */
    function reRenderWithElementPositionPreserved(referenceElement) {
        if (!state.resultsContainerDOM || !referenceElement) return;

        // Find the section this element belongs to
        const sectionWrapper = referenceElement.closest('[data-section-key]');
        const sectionKey = sectionWrapper?.dataset.sectionKey;
        if (!sectionKey) return;

        // Determine what type of element to track after re-render
        let isSection = referenceElement.classList.contains('search-results-section');
        let buttonClass = null;

        if (!isSection) {
            if (referenceElement.classList.contains('section-icon-button')) {
                buttonClass = 'section-icon-button';
            } else if (referenceElement.classList.contains('show-more-button')) {
                buttonClass = 'show-more-button';
            } else if (referenceElement.classList.contains('show-fewer-button')) {
                buttonClass = 'show-fewer-button';
            }
        }

        // Save scroll position and element position before re-render
        const containerRect = state.resultsContainerDOM.getBoundingClientRect();
        const elemRect = referenceElement.getBoundingClientRect();
        const offsetFromTop = elemRect.top - containerRect.top;

        // Re-render
        renderFilters(state.lastSearchResults.groupedResults, state.lastSearchResults.hiddenResults, state.lastSearchTerm);

        // Find the equivalent element after re-render
        const newSectionWrapper = state.resultsContainerDOM.querySelector(`[data-section-key="${sectionKey}"]`);
        if (!newSectionWrapper) return;

        let newReferenceElement = null;
        if (isSection) {
            newReferenceElement = newSectionWrapper;
        } else if (buttonClass) {
            newReferenceElement = newSectionWrapper.querySelector(`.${buttonClass}`);
        }

        if (!newReferenceElement) return;

        // Calculate how much to scroll to keep the element in the same position
        const newElemRect = newReferenceElement.getBoundingClientRect();
        const newOffsetFromTop = newElemRect.top - containerRect.top;
        const scrollAdjustment = newOffsetFromTop - offsetFromTop;

        state.resultsContainerDOM.scrollTop += scrollAdjustment;
    }

    // ========================================
    // SECTION RENDERING
    // ========================================

    /**
     * Creates the section toggle button (icon with expand/collapse indicator)
     * @param {string} sectionTitle - Section title
     * @param {string} sectionIcon - SVG icon
     * @param {string} sectionKey - Section identifier
     * @param {string} viewState - Current view state
     * @returns {HTMLElement} Toggle button element
     */
    function createSectionToggleButton(sectionTitle, sectionIcon, sectionKey, viewState) {
        const toggleButton = document.createElement('button');
        toggleButton.className = 'tag-button state-unselected toggle-hidden-button section-icon-button';

        const stateSymbol = (viewState === SECTION_VIEW_STATE.COLLAPSED) ? '▶' : '▼';
        toggleButton.innerHTML = `${sectionIcon}<span class="state-indicator">${stateSymbol}</span>`;
        toggleButton.setAttribute('aria-label', sectionTitle);
        toggleButton.setAttribute('title', sectionTitle);
        toggleButton.classList.add(`view-state-${viewState}`);

        // Toggle between COLLAPSED and DEFAULT
        toggleButton.addEventListener('click', (e) => {
            e.stopPropagation();

            const currentState = state.sectionViewStates[sectionKey];
            if (currentState === SECTION_VIEW_STATE.COLLAPSED) {
                state.sectionViewStates[sectionKey] = SECTION_VIEW_STATE.DEFAULT;
            } else {
                state.sectionViewStates[sectionKey] = SECTION_VIEW_STATE.COLLAPSED;
            }

            reRenderWithElementPositionPreserved(toggleButton);
        });

        // Right-click to dismiss section (move to bottom)
        toggleButton.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            e.stopPropagation();

            const currentIndex = state.sectionOrder.indexOf(sectionKey);
            if (currentIndex === -1) return;

            state.sectionOrder.splice(currentIndex, 1);
            state.sectionOrder.push(sectionKey);

            // Notify parent of reorder
            if (state.onSectionReorder) {
                state.onSectionReorder(state.sectionOrder);
            }

            renderFilters(state.lastSearchResults, state.lastSearchTerm);
        });

        return toggleButton;
    }

    /**
     * Adds "show more" button if needed
     * @param {HTMLElement} sectionWrapper - Section container
     * @param {string} viewState - Current view state
     * @param {string} sectionKey - Section identifier
     * @param {string} sectionTitle - Section title
     * @param {number} resultsCount - Number of visible results
     * @param {number} collapseThreshold - Collapse threshold
     * @param {boolean} hasHiddenItems - Whether there are hidden items
     */
    function addShowMoreButton(sectionWrapper, viewState, sectionKey, sectionTitle, resultsCount, collapseThreshold, hasHiddenItems) {
        let shouldShow = false;

        if (viewState === SECTION_VIEW_STATE.COLLAPSED) {
            shouldShow = resultsCount > collapseThreshold || hasHiddenItems;
        } else if (viewState === SECTION_VIEW_STATE.DEFAULT) {
            shouldShow = hasHiddenItems;
        }

        if (!shouldShow) return;

        const btn = document.createElement('button');
        btn.className = 'tag-button state-unselected state-cycle-button show-more-button';
        btn.textContent = '+';

        const label = `Show more ${sectionTitle.toLowerCase()}`;
        btn.setAttribute('title', label);
        btn.setAttribute('aria-label', label);
        btn.classList.add(`view-state-${viewState}`);

        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const currentState = state.sectionViewStates[sectionKey];

            if (currentState === SECTION_VIEW_STATE.COLLAPSED) {
                // Skip DEFAULT and go directly to EXPANDED if all visible items fit
                if (resultsCount <= collapseThreshold && hasHiddenItems) {
                    state.sectionViewStates[sectionKey] = SECTION_VIEW_STATE.EXPANDED;
                } else {
                    state.sectionViewStates[sectionKey] = SECTION_VIEW_STATE.DEFAULT;
                }
            } else if (currentState === SECTION_VIEW_STATE.DEFAULT) {
                state.sectionViewStates[sectionKey] = SECTION_VIEW_STATE.EXPANDED;
            }

            reRenderWithElementPositionPreserved(sectionWrapper);
        });

        sectionWrapper.appendChild(btn);
    }

    /**
     * Adds "show fewer" button if needed
     * @param {HTMLElement} sectionWrapper - Section container
     * @param {string} viewState - Current view state
     * @param {string} sectionKey - Section identifier
     * @param {string} sectionTitle - Section title
     * @param {number} resultsCount - Number of visible results
     * @param {number} collapseThreshold - Collapse threshold
     * @param {boolean} hasHiddenItems - Whether there are hidden items
     */
    function addShowFewerButton(sectionWrapper, viewState, sectionKey, sectionTitle, resultsCount, collapseThreshold, hasHiddenItems) {
        let shouldShow = false;

        if (viewState === SECTION_VIEW_STATE.DEFAULT) {
            shouldShow = resultsCount > collapseThreshold;
        } else if (viewState === SECTION_VIEW_STATE.EXPANDED) {
            shouldShow = hasHiddenItems;
        }

        if (!shouldShow) return;

        const btn = document.createElement('button');
        btn.className = 'tag-button state-unselected state-cycle-button show-fewer-button';
        btn.textContent = '−';

        const label = `Show fewer ${sectionTitle.toLowerCase()}`;
        btn.setAttribute('title', label);
        btn.setAttribute('aria-label', label);
        btn.classList.add(`view-state-${viewState}`);

        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const currentState = state.sectionViewStates[sectionKey];

            if (currentState === SECTION_VIEW_STATE.DEFAULT) {
                state.sectionViewStates[sectionKey] = SECTION_VIEW_STATE.COLLAPSED;
            } else if (currentState === SECTION_VIEW_STATE.EXPANDED) {
                state.sectionViewStates[sectionKey] = SECTION_VIEW_STATE.DEFAULT;
            }

            reRenderWithElementPositionPreserved(btn);
        });

        sectionWrapper.appendChild(btn);
    }

    /**
     * Renders a single result section
     * @param {Array} results - Visible results
     * @param {Array} hiddenItems - Hidden results
     * @param {string} sectionTitle - Section title
     * @param {string} sectionIcon - SVG icon
     * @param {string} sectionKey - Section identifier
     */
    function renderSection(results, hiddenItems, sectionTitle, sectionIcon, sectionKey) {
        const hasHiddenItems = hiddenItems && hiddenItems.length > 0;
        const viewState = state.sectionViewStates[sectionKey];

        // Skip section if there are no results
        if (results.length === 0 && !hasHiddenItems) return;

        // Create section wrapper
        const sectionWrapper = document.createElement('div');
        sectionWrapper.className = 'search-results-section';
        sectionWrapper.dataset.sectionKey = sectionKey;

        // Create toggle button
        const toggleButton = createSectionToggleButton(sectionTitle, sectionIcon, sectionKey, viewState);
        sectionWrapper.appendChild(toggleButton);

        // Create result elements using the provided callback
        const visibleItemElements = results.map(result => state.createSearchResultButton(result));
        const allItems = [...results, ...(hiddenItems || [])];
        const allItemElements = allItems.map(result => state.createSearchResultButton(result));

        // Determine which results to show based on view state
        let resultsToShow = [];
        let collapseThreshold = getEstimatedCollapseThreshold(sectionKey);

        if (viewState === SECTION_VIEW_STATE.COLLAPSED) {
            // Measure actual threshold
            const wasInDOM = sectionWrapper.parentNode !== null;
            if (!wasInDOM) {
                state.resultsContainerDOM.appendChild(sectionWrapper);
            }

            collapseThreshold = calculateCollapseThreshold(sectionWrapper, visibleItemElements);
            resultsToShow = visibleItemElements.slice(0, collapseThreshold);
        } else if (viewState === SECTION_VIEW_STATE.DEFAULT) {
            resultsToShow = visibleItemElements;
        } else { // EXPANDED
            resultsToShow = allItemElements;
        }

        // Add result buttons to section
        resultsToShow.forEach(resultElement => {
            sectionWrapper.appendChild(resultElement);
        });

        // Add show more/fewer buttons
        addShowMoreButton(sectionWrapper, viewState, sectionKey, sectionTitle, results.length, collapseThreshold, hasHiddenItems);
        addShowFewerButton(sectionWrapper, viewState, sectionKey, sectionTitle, results.length, collapseThreshold, hasHiddenItems);

        state.resultsContainerDOM.appendChild(sectionWrapper);
    }

    /**
     * Main render function for the filter UI
     * @param {Object} groupedResults - Grouped search results by type
     * @param {Object} hiddenResults - Hidden results by type
     * @param {string} searchTerm - Current search term
     */
    function renderFilters(groupedResults = {}, hiddenResults = {}, searchTerm = '') {
        state.searchTerm = searchTerm;
        state.lastSearchResults = { groupedResults, hiddenResults };
        state.lastSearchTerm = searchTerm;

        if (!state.resultsContainerDOM) return;

        // Clear and reset scroll
        state.resultsContainerDOM.innerHTML = '';
        state.resultsContainerDOM.scrollTop = 0;

        // Check if we have any results
        const hasResults = Object.values(groupedResults).some(arr => arr && arr.length > 0) ||
                          Object.values(hiddenResults).some(arr => arr && arr.length > 0);

        if (!hasResults) return;

        // Render sections in the specified order
        state.sectionOrder.forEach(sectionKey => {
            const metadata = SECTION_METADATA[sectionKey];
            if (!metadata) return;

            const results = (groupedResults[sectionKey] || []).slice(0, 100);
            const hidden = (hiddenResults[sectionKey] || []).slice(0, 100);

            renderSection(results, hidden, metadata.title, metadata.icon, sectionKey);
        });
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the SectionRenderer module
     * @param {Object} config - Configuration object
     * @param {HTMLElement} config.resultsContainerDOM - Container for search results
     * @param {Array<string>} config.sectionOrder - Reference to section order array
     * @param {Object} config.sectionViewStates - Reference to section view states
     * @param {Function} config.createSearchResultButton - Callback to create result buttons
     * @param {Function} config.onSectionReorder - Callback when sections are reordered
     */
    function init(config) {
        state.resultsContainerDOM = config.resultsContainerDOM;
        state.sectionOrder = config.sectionOrder;
        state.sectionViewStates = config.sectionViewStates;
        state.createSearchResultButton = config.createSearchResultButton;
        state.onSectionReorder = config.onSectionReorder;
    }

    /**
     * Gets the section metadata
     * @returns {Object} Section metadata
     */
    function getSectionMetadata() {
        return SECTION_METADATA;
    }

    /**
     * Gets the section view state constants
     * @returns {Object} View state constants
     */
    function getSectionViewState() {
        return SECTION_VIEW_STATE;
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Initialization
        init,

        // Rendering
        renderFilters,

        // Query functions
        getSectionMetadata,
        getSectionViewState
    };
})();
