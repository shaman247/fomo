/**
 * SectionRenderer Module
 *
 * Handles rendering of search result sections.
 * Manages section display, section ordering, and scroll position preservation.
 *
 * Features:
 * - Render search result sections (locations, events, tags)
 * - Section toggle and reordering support
 *
 * @module SectionRenderer
 */
const SectionRenderer = (() => {
    // ========================================
    // CONSTANTS
    // ========================================

    /**
     * Metadata for each result section type
     */
    const SECTION_METADATA = {
        locations: {
            title: 'Places',
        },
        events: {
            title: 'Events',
        },
        tags: {
            title: 'Tags',
        },
        organizers: {
            title: 'Organizers',
        }
    };

    /**
     * Maximum items rendered per section (visible + hidden combined)
     */
    const SECTION_ITEM_LIMIT = 10;

    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     * Note: sectionOrder is set via init() from FilterPanelUI
     */
    const state = {
        // DOM elements
        resultsContainerDOM: null,

        // Section state - set via init() based on device type
        sectionOrder: [],

        // Search state
        debugMode: false,
        lastSearchResults: [],
        lastSearchTerm: '',

        // Callbacks
        createSearchResultButton: null,
        onSectionReorder: null,
        onAfterRender: null,

    };

    // ========================================
    // UTILITY FUNCTIONS
    // ========================================

    /**
     * Determines if the current window is small (mobile-like)
     * @returns {boolean} True if window width is at or below the mobile breakpoint
     */
    function isSmallWindow() {
        return Utils.isMobileLayout();
    }

    // ========================================
    // SECTION RENDERING
    // ========================================

    /**
     * Creates the section header label
     * @param {string} sectionTitle - Section title
     * @param {string} sectionKey - Section identifier
     * @returns {HTMLElement} Section header element
     */
    function createSectionHeader(sectionTitle, sectionKey) {
        const header = document.createElement('button');
        header.className = 'tag-button state-unselected toggle-hidden-button section-icon-button';
        header.innerHTML = `<span class="section-label">${sectionTitle.toUpperCase()}</span>`;
        header.setAttribute('aria-label', sectionTitle);
        header.setAttribute('title', sectionTitle);

        // Right-click to dismiss section (move to bottom)
        header.addEventListener('contextmenu', (e) => {
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

            renderFilters(state.lastSearchResults.groupedResults, state.lastSearchResults.hiddenResults, state.lastSearchTerm, state.debugMode);
        });

        return header;
    }

    /**
     * Renders a single result section
     * @param {Array} results - Visible results
     * @param {Array} hiddenItems - Hidden results
     * @param {string} sectionTitle - Section title
     * @param {string} sectionKey - Section identifier
     */
    function renderSection(results, hiddenItems, sectionTitle, sectionKey) {
        const hasHiddenItems = hiddenItems && hiddenItems.length > 0;

        // Skip section if there are no results
        if (results.length === 0 && !hasHiddenItems) return;

        // Create section wrapper
        const sectionWrapper = document.createElement('div');
        sectionWrapper.className = 'search-results-section';
        sectionWrapper.dataset.sectionKey = sectionKey;

        // Create section header
        const header = createSectionHeader(sectionTitle, sectionKey);
        sectionWrapper.appendChild(header);

        // Create and add result elements (visible + hidden, capped)
        const allItems = [...results, ...(hiddenItems || [])].slice(0, SECTION_ITEM_LIMIT);
        allItems.forEach(result => {
            sectionWrapper.appendChild(state.createSearchResultButton(result));
        });

        state.resultsContainerDOM.appendChild(sectionWrapper);
    }

    /**
     * Main render function for the filter UI
     * @param {Object} groupedResults - Grouped search results by type
     * @param {Object} hiddenResults - Hidden results by type
     * @param {string} searchTerm - Current search term
     */
    function renderFilters(groupedResults = {}, hiddenResults = {}, searchTerm = '', debugMode = false) {
        const FP = (typeof window !== 'undefined' && window.FilterProfiler) || null;
        if (FP) FP.mark('fp:sections:start');

        state.debugMode = debugMode;
        state.lastSearchResults = { groupedResults, hiddenResults };
        state.lastSearchTerm = searchTerm;

        if (!state.resultsContainerDOM) return;

        // Clear and reset scroll
        state.resultsContainerDOM.innerHTML = '';
        state.resultsContainerDOM.scrollTop = 0;

        // On desktop, hide sections when there's no search term (unless debug mode)
        if (!isSmallWindow() && !searchTerm && !debugMode) {
            if (FP) {
                FP.mark('fp:sections:skipped');
                FP.measure('fp:sections:skip-build', 'fp:sections:start', 'fp:sections:skipped');
            }
            if (state.onAfterRender) {
                state.onAfterRender();
            }
            if (FP) {
                FP.mark('fp:sections:end');
                FP.measure('fp:sections:onAfterRender', 'fp:sections:skipped', 'fp:sections:end');
            }
            return;
        }

        // Check if we have any results
        const hasResults = Object.values(groupedResults).some(arr => arr && arr.length > 0) ||
                          Object.values(hiddenResults).some(arr => arr && arr.length > 0);

        if (!hasResults) {
            // Container was already cleared above; still notify the parent so
            // the chip bar resyncs to the current term.
            if (state.onAfterRender) {
                state.onAfterRender();
            }
            return;
        }

        // Render sections in the specified order
        state.sectionOrder.forEach(sectionKey => {
            const metadata = SECTION_METADATA[sectionKey];
            if (!metadata) return;

            const results = groupedResults[sectionKey] || [];
            const hidden = hiddenResults[sectionKey] || [];

            renderSection(results, hidden, metadata.title, sectionKey);
        });

        if (FP) {
            FP.mark('fp:sections:built');
            FP.measure('fp:sections:build', 'fp:sections:start', 'fp:sections:built');
        }

        // Notify parent (e.g., FilterPanelUI) that rendering is complete
        if (state.onAfterRender) {
            state.onAfterRender();
        }

        if (FP) {
            FP.mark('fp:sections:end');
            FP.measure('fp:sections:onAfterRender', 'fp:sections:built', 'fp:sections:end');
        }
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the SectionRenderer module
     * @param {Object} config - Configuration object
     * @param {HTMLElement} config.resultsContainerDOM - Container for search results
     * @param {Array<string>} config.sectionOrder - Section order array
     * @param {Function} config.createSearchResultButton - Callback to create result buttons
     * @param {Function} config.onSectionReorder - Callback when sections are reordered
     */
    function init(config) {
        state.resultsContainerDOM = config.resultsContainerDOM;
        state.sectionOrder = config.sectionOrder;
        state.createSearchResultButton = config.createSearchResultButton;
        state.onSectionReorder = config.onSectionReorder;
        state.onAfterRender = config.onAfterRender || null;
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Initialization
        init,

        // Rendering
        renderFilters,
    };
})();
