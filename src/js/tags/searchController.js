/**
 * SearchController Module
 *
 * Handles the search input UI functionality including:
 * - Debounced search input handling
 * - Special search term detection (debug, noto)
 * - Mobile auto-expand behavior
 * - Search input event management
 *
 * Note: This is distinct from SearchManager which handles the search algorithm/scoring.
 * SearchController = UI/input handling, SearchManager = data querying/scoring logic.
 *
 * @module SearchController
 */
const SearchController = (() => {
    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // DOM elements
        searchInputDOM: null,
        filterPanelDOM: null,
        expandFilterPanelButtonDOM: null,

        // Callbacks
        onSpecialSearchTerm: null,
        performSearchCallback: null
    };

    // ========================================
    // SEARCH HANDLING
    // ========================================

    /**
     * Handles keydown events in the search input
     * @param {KeyboardEvent} e - Keyboard event
     */
    function handleSearchKeydown(e) {
        if (e.key === 'Escape') {
            clearSearch();
        }
    }

    /**
     * Clears the search input and results
     */
    function clearSearch() {
        if (state.searchInputDOM) {
            state.searchInputDOM.value = '';
        }
        if (state.performSearchCallback) {
            state.performSearchCallback('');
        }
        if (state.searchInputDOM) {
            state.searchInputDOM.blur();
        }
    }

    /**
     * Gets the current search term
     * @returns {string} Current search term (lowercase)
     */
    function getSearchTerm() {
        return state.searchInputDOM ? state.searchInputDOM.value.toLowerCase() : '';
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the SearchController module
     * @param {Object} config - Configuration object
     * @param {HTMLElement} [config.filterPanelDOM] - Filter panel element (for mobile auto-expand)
     * @param {HTMLElement} [config.expandFilterPanelButtonDOM] - Expand button element (for mobile)
     * @param {Function} [config.onSpecialSearchTerm] - Callback for special search terms (debug, noto)
     * @param {Function} config.performSearchCallback - Callback to perform search
     */
    function init(config) {
        state.filterPanelDOM = config.filterPanelDOM || null;
        state.expandFilterPanelButtonDOM = config.expandFilterPanelButtonDOM || null;
        state.onSpecialSearchTerm = config.onSpecialSearchTerm || null;
        state.performSearchCallback = config.performSearchCallback;

        state.searchInputDOM = document.getElementById('omni-search-input');

        if (!state.searchInputDOM) {
            console.warn("SearchController: searchInputDOM not found.");
            return;
        }

        // Add keydown handler for Escape
        state.searchInputDOM.addEventListener('keydown', handleSearchKeydown);

        // Debounce search to improve performance (executes after user stops typing)
        const debouncedSearch = Utils.debounce((searchTerm) => {
            if (state.performSearchCallback) {
                state.performSearchCallback(searchTerm);
            }
        }, Constants.TIME.SEARCH_DEBOUNCE_MS);

        state.searchInputDOM.addEventListener('input', (e) => {
            const searchTerm = e.target.value.toLowerCase();

            // Handle special terms immediately (no debounce)
            if (state.onSpecialSearchTerm) {
                state.onSpecialSearchTerm(searchTerm);
            }

            // Debounce regular search
            debouncedSearch(searchTerm);

            // Auto-expand panel on mobile when user enters search term
            if (searchTerm && window.innerWidth <= Constants.UI.MOBILE_BREAKPOINT) {
                if (state.filterPanelDOM) {
                    state.filterPanelDOM.classList.remove('tags-collapsed');
                }
                if (state.expandFilterPanelButtonDOM) {
                    state.expandFilterPanelButtonDOM.classList.remove('collapsed');
                }
            }
        });

        state.searchInputDOM.addEventListener('focus', (e) => {
            const searchTerm = e.target.value.toLowerCase();
            if (searchTerm && state.performSearchCallback) {
                state.performSearchCallback(searchTerm);
            }
        });
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        init,
        clearSearch,
        getSearchTerm
    };
})();
