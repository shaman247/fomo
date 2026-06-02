/**
 * Detect Android app and add body class for app-specific styling
 * Must run before DOMContentLoaded to apply styles early
 */
(function() {
    if (navigator.userAgent.includes('FomoApp')) {
        document.documentElement.classList.add('fomo-android-app');
    }
})();

/**
 * Main application entry point - initializes the events mapping application
 * Coordinates all modules and manages application state
 */
document.addEventListener('DOMContentLoaded', () => {
    /**
     * Main application object - orchestrates all modules and manages global state
     * @namespace App
     */
    const App = {
        /**
         * Application state object
         * @type {Object}
         * @property {maplibregl.Map|null} map - MapLibre map instance
         * @property {HTMLElement|null} debugContainer - Container for debug visualization
         * @property {boolean} debugMode - Debug mode toggle state
         * @property {Object|null} visibleCenter - Visible center accounting for filter panel
         * @property {Object} locationDistances - Map of locationKey -> distance from center
         * @property {Array} allEvents - All loaded events
         * @property {Object} eventsById - Event lookup by ID
         * @property {Object} tagConfig - Tag configuration (geotags, bgcolors)
         * @property {Object} eventsByLatLng - Events grouped by location
         * @property {Object} locationsByLatLng - Location info by coordinates
         * @property {Object} tagFrequencies - Global tag frequency counts
         * @property {Object|null} datePickerInstance - Flatpickr instance
         * @property {Array} allAvailableTags - All tags available in dataset
         * @property {Object} eventTagIndex - Tag to event IDs index
         * @property {Array} allEventsFilteredByDateAndLocation - Events filtered by date/location
         * @property {Set} geotagsSet - Set of geotags from config
         * @property {Object} eventsByLatLngInDateRange - Events by location in date range
         * @property {Array} currentlyMatchingEvents - Events matching current filters
         * @property {Set} currentlyMatchingLocationKeys - Location keys with matching events
         * @property {Array} currentlyVisibleMatchingEvents - Visible matching events
         * @property {Set} currentlyVisibleMatchingLocationKeys - Visible location keys
         * @property {Object} visibleTagFrequencies - Tag frequencies for visible events
         * @property {string|null} forceDisplayEventId - Event ID to force display in popup
         * @property {Array} lastSelectedDates - Last selected date range
         * @property {string|null} selectedLocationKey - Currently selected location key
         * @property {boolean} isInitialLoad - Whether in initial load phase
         */
        state: {
            map: null,
            debugContainer: null,
            debugMode: false,
            visibleCenter: null,
            locationDistances: {}, // Map of locationKey -> distance from center
            allEvents: [],
            eventsById: {},
            tagConfig: {},
            quickFilters: [],
            hierarchyTagsSet: new Set(),
            tagDescendantsOf: {},
            tagParentsOf: {},
            tagChildrenOf: {},
            tagEmojiMap: {},
            eventsByLatLng: {},
            locationsByLatLng: {},
            tagFrequencies: {},
            datePickerInstance: null,
            allAvailableTags: [],
            eventTagIndex: {},
            allEventsFilteredByDateAndLocation: [],
            geotagsSet: new Set(),
            eventsByLatLngInDateRange: {},
            currentlyMatchingEvents: [],
            currentlyMatchingLocationKeys: new Set(),
            currentlyVisibleMatchingEvents: [],
            currentlyVisibleMatchingLocationKeys: new Set(),
            visibleTagFrequencies: {},
            forceDisplayEventId: null,
            lastSelectedDates: [],
            selectedLocationKey: null,
            searchTerm: '', // Current search term for marker filtering
            currentFilteredLocations: null, // Locations after tag/date filtering (before search)
            organizersById: {}, // Organizer data keyed by website ID
            isInitialLoad: true, // Track if we're in initial load phase
            _moveendSearchTimeout: null, // Debounce timer for search on moveend
        },

        /**
         * Application configuration object
         * @type {Object}
         * @property {string} EVENT_INIT_URL - URL for initial events data
         * @property {string} LOCATIONS_INIT_URL - URL for initial locations data
         * @property {string} EVENT_FULL_URL - URL for full events dataset
         * @property {string} LOCATIONS_FULL_URL - URL for full locations dataset
         * @property {string} TAG_CONFIG_URL - URL for tag configuration
         * @property {Date} START_DATE - Default start date for date range
         * @property {Date} END_DATE - Default end date for date range
         * @property {Array<string>} TAG_COLOR_PALETTE_DARK - Color palette for dark theme
         * @property {Array<string>} TAG_COLOR_PALETTE_LIGHT - Color palette for light theme
         * @property {Array<number>} MAP_INITIAL_VIEW - Initial map center [lat, lng]
         * @property {number} MAP_INITIAL_ZOOM - Initial map zoom level
         * @property {string} MAP_TILE_URL_DARK - Tile URL for dark theme map
         * @property {string} MAP_TILE_URL_LIGHT - Tile URL for light theme map
         * @property {string} MAP_ATTRIBUTION - Map attribution text
         * @property {number} MAP_MAX_ZOOM - Maximum zoom level
         */
        config: {
            // Event data is split into per-day chunks. Phase 1 fetches the
            // chunk matching the user's current NYC date; Phase 2 fetches the
            // others. manifest.json maps "day0".."dayN" → calendar dates.
            DATA_DIR: 'data/',
            MANIFEST_URL: 'data/manifest.json',
            REMAINDER_CHUNK: 'remainder',
            TAG_CONFIG_URL: 'data/tags.json',
            TAG_HIERARCHY_URL: 'data/tag_hierarchy.json',
            ORGANIZERS_URL: 'data/organizers.json',

            START_DATE: new Date(new Date().setHours(0, 0, 0, 0)),
            END_DATE: new Date(new Date().setHours(0, 0, 0, 0) + 90 * 24 * 60 * 60 * 1000),
            TAG_COLOR_PALETTE_DARK: [
                '#b03540', '#3d8578', '#c07030', '#3d70a0', '#5da035',
                '#a04570', '#7da030', '#3d5ca8', '#b58030', '#3d7580', '#a03d78',
                '#6aa035', '#903d68', '#b55530', '#3d68a0', '#308578', '#a85035',
                '#5d3ca8', '#a88035', '#4d8538', '#903d5d', '#3d4d50', '#708038'
            ],
            TAG_COLOR_PALETTE_LIGHT: [
                '#e08085', '#85c0b0', '#e8a875', '#85aad8', '#9dd085',
                '#e085a8', '#b8d075', '#8595e0', '#e0b875', '#85adb8', '#e085b0',
                '#a8d085', '#c88598', '#e09075', '#85a0d8', '#75c0b0', '#e89075',
                '#9585e0', '#e0b085', '#8dc090', '#c88590', '#859098', '#a8b075'
            ],
            MAP_INITIAL_VIEW: [40.70424, -73.97086],
            MAP_INITIAL_ZOOM: 12,
            MAP_USER_LOCATION_ZOOM: 14,
            // NYC area bounds for geolocation validation
            NYC_BOUNDS: {
                latMin: 40.49,
                latMax: 40.92,
                lngMin: -74.26,
                lngMax: -73.70
            },
            MAP_STYLE_DARK: 'data/map-style-dark.json?v=7',
            MAP_STYLE_LIGHT: 'data/map-style-light.json?v=7',
            MAP_ATTRIBUTION: '© <a href="https://protomaps.com">Protomaps</a> © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            MAP_MAX_ZOOM: 20
        },

        /**
         * Cached DOM elements for efficient access
         * @type {Object}
         * @property {HTMLElement} resultsContainer - Container for search results
         * @property {HTMLElement} datePicker - Date picker input element
         * @property {HTMLElement} datePickerSizer - Hidden element for measuring date picker width
         * @property {HTMLElement} dateFilterContainer - Container for date filter
         * @property {HTMLElement} filterContainer - Main filter container
         * @property {HTMLElement} omniSearchFilter - Omni search filter container
         * @property {HTMLElement} expandFilterPanelButton - Button to expand/collapse filter panel on mobile
         * @property {HTMLElement} filterPanel - Filter panel element
         * @property {HTMLElement} omniSearchInput - Search input element
         */
        elements: {
            resultsContainer: document.getElementById('results-container'),
            datePicker: document.getElementById('date-picker'),
            datePickerSizer: document.getElementById('date-picker-sizer'),
            dateFilterContainer: document.getElementById('date-filter-container'),
            filterContainer: document.getElementById('filter-container'),
            omniSearchFilter: document.getElementById('omni-search-filter'),
            expandFilterPanelButton: document.getElementById('expand-filter-panel-button'),
            filterPanel: document.getElementById('filter-panel'),
            omniSearchInput: document.getElementById('omni-search-input'),
        },

        /**
         * Parse URL parameters and clean up the address bar
         * @memberof App
         * @returns {Object} Parsed URL parameters
         * @private
         */
        _parseAndCleanUrlParams() {
            const urlParams = URLParams.parse();
            this.state.urlParams = urlParams;

            // Clean up URL parameters from address bar after parsing
            // This prevents confusion when users interact with the map and change the view
            if (Object.keys(urlParams).length > 0) {
                const cleanUrl = window.location.origin + window.location.pathname;
                window.history.replaceState({}, '', cleanUrl);
            }

            return urlParams;
        },

        /**
         * Load and process initial data
         * @memberof App
         * @async
         * @returns {Promise<void>}
         * @private
         */
        async _loadInitialData() {
            // Step 1: Fetch the manifest first — it's tiny (~60 bytes) and tells
            // us which day-chunk maps to today's NYC date.
            const manifest = await DataManager.fetchData(this.config.MANIFEST_URL);

            this.state.manifest = manifest || { days: [] };
            this.state.loadedChunks = new Set();

            // Step 2: Pick the chunk matching today's date. If today isn't in
            // the manifest (export is older than NUM_DAY_CHUNKS days), fall
            // back to remainder so the user still sees recent + future events.
            const todayStr = Utils.getTodayInNewYork();
            const dayIndex = (this.state.manifest.days || []).indexOf(todayStr);
            const initChunk = dayIndex >= 0 ? `day${dayIndex}` : this.config.REMAINDER_CHUNK;
            this.state.initChunk = initChunk;
            this.state.loadedChunks.add(initChunk);

            // Step 3: Fetch everything else in a SINGLE parallel batch. The heavy
            // events chunk (~330 KB gz) now downloads concurrently with the
            // metadata instead of waiting for it — previously organizers.json
            // (~120 KB gz) sat on the critical path *before* the chunk fetch even
            // started, adding a full round-trip + its transfer to time-to-markers.
            const [tagConfig, tagHierarchy, organizersData, initEventData, initLocationData] = await Promise.all([
                DataManager.fetchData(this.config.TAG_CONFIG_URL),
                DataManager.fetchData(this.config.TAG_HIERARCHY_URL),
                DataManager.fetchData(this.config.ORGANIZERS_URL),
                DataManager.fetchData(`${this.config.DATA_DIR}events.${initChunk}.json`),
                DataManager.fetchData(`${this.config.DATA_DIR}locations.${initChunk}.json`)
            ]);
            this.state.organizersById = organizersData || {};

            this.state.tagConfig = tagConfig;
            this.state.geotagsSet = new Set((tagConfig.geotags || []).map(tag => tag.toLowerCase()));

            // Build hierarchy maps from exported data
            const hierarchyMaps = DataManager.buildTagHierarchyMaps(tagHierarchy || { tags: [], keywords: [] });
            this.state.quickFilters = hierarchyMaps.quickFilters;
            this.state.hierarchyTagsSet = hierarchyMaps.hierarchyTagsSet;
            this.state.tagDescendantsOf = hierarchyMaps.descendantsOf;
            this.state.tagParentsOf = hierarchyMaps.parentsOf;
            this.state.tagChildrenOf = hierarchyMaps.childrenOf;
            this.state.tagEmojiMap = hierarchyMaps.tagEmojiMap;

            // Organizers participate in the tag filter system as namespaced
            // pseudo-tags (e.g. "organizer:123"). Register their names and fold
            // their emojis into tagEmojiMap so they render like any other tag
            // wherever a tag chip is drawn (popups, chip bar, search results).
            Utils.registerOrganizers(this.state.organizersById);
            for (const [id, org] of Object.entries(this.state.organizersById)) {
                const orgTag = Utils.makeOrganizerTag(id);
                if (orgTag && org && org.emoji) this.state.tagEmojiMap[orgTag] = org.emoji;
            }

            // Initialize TagColorManager with color palettes and emoji bgcolors
            TagColorManager.init({
                darkPalette: this.config.TAG_COLOR_PALETTE_DARK,
                lightPalette: this.config.TAG_COLOR_PALETTE_LIGHT,
                tagEmojiMap: this.state.tagEmojiMap,
                bgcolors: this.state.tagConfig.bgcolors || {}
            });

            DataManager.processInitialData(initEventData, initLocationData, this.state, this.config);
            DataManager.calculateTagFrequencies(this.state);
            DataManager.processTagHierarchy(this.state, this.config);
            DataManager.buildTagIndex(this.state);
            DataManager.buildSearchIndex(this.state);
        },

        /**
         * Initialize all core modules (emoji, theme, map, viewport, etc.)
         * @memberof App
         * @private
         * @async
         */
        async _startMap() {
            // Everything here is independent of the event/tag data, so it can run
            // (and kick off the base map's style/tile/glyph downloads) in PARALLEL
            // with _loadInitialData() instead of waiting for it. The base map needs
            // only the theme (for its style URL) and the initial center/zoom.
            this.initEmojiManager();
            EmojiManager.initEmojiFont();
            this.initThemeManager();
            ThemeManager.initTheme();

            // Only request location if user has enabled the setting
            if (ModalManager.isLocationEnabled()) {
                this.state.userLocation = await this.getUserLocation();
            }

            this.initMap();
            // ViewportManager must exist before mapLoadPromise resolves — the
            // map's ready handler calls ViewportManager.adjustMapToVisibleCenter().
            this.initViewportManager();
            // Search/filter managers must be ready before the map can fire a
            // moveend→performSearch (which happens during the parallel load).
            this.initSearchAndFilterManagers();
        },

        /**
         * Initialize the modules that depend on the loaded event/tag data.
         * Runs after both _startMap() and _loadInitialData() have completed.
         * @memberof App
         * @private
         */
        _initDataDependentModules() {
            // Feed the now-loaded emoji→color map to the already-created map.
            MapManager.setMarkerColors((this.state.tagConfig && this.state.tagConfig.bgcolors) || {});
            this.initMarkerController();
            this.initFilterPanelUI();
        },

        /**
         * Setup UI components and event listeners
         * @memberof App
         * @param {Object} urlParams - Parsed URL parameters
         * @private
         */
        _setupUIComponents(urlParams) {
            // Apply URL parameter tag selections before date picker init
            // This ensures tags are selected when the date picker triggers initial filtering
            if (urlParams.tags && urlParams.tags.length > 0) {
                FilterPanelUI.selectTags(urlParams.tags, (tag) => TagColorManager.assignColorToTag(tag));
            }

            UIManager.initDatePicker(this.elements, this.config, this.state, {
                onDatePickerClose: (selectedDates) => {
                    const [newStart, newEnd] = selectedDates;
                    const [oldStart, oldEnd] = this.state.lastSelectedDates;

                    if (oldStart && oldEnd && newStart.getTime() === oldStart.getTime() && newEnd.getTime() === oldEnd.getTime()) {
                        return;
                    }

                    this.state.lastSelectedDates = selectedDates;
                    // During init, skip display — filterAndDisplayEvents is called explicitly after map loads
                    this.updateFilteredEventList({ skipDisplay: this.state.isInitialLoad });

                    HistoryManager.push();
                }
            });
            FilterPanelUI.initOmniSearch({
                filterPanelDOM: this.elements.filterPanel,
                expandFilterPanelButtonDOM: this.elements.expandFilterPanelButton,
                onSpecialSearchTerm: (term) => this.handleSpecialSearchTerms(term)
            });
            UIManager.initLogoMenu({
                onShareView: () => this.shareCurrentView()
            });
            ModalManager.initSettingsModal({
                onEmojiFontChange: (emojiFont) => {
                    const statusElement = document.getElementById('emoji-font-status');
                    EmojiManager.applyEmojiFont(emojiFont, statusElement);
                },
                onThemeChange: (theme) => {
                    ThemeManager.applyThemeChange(theme);
                },
                onLocationToggle: (enabled) => {
                    this.handleLocationToggle(enabled);
                }
            });
            // Note: Welcome modal is initialized earlier in init() so it can be closed during loading
            FeedbackManager.init();
        },

        /**
         * Update the Phase 1 loading progress bar.
         * @memberof App
         * @private
         * @param {number} pct - Percentage (0-100)
         */
        _setLoadingProgress(pct) {
            const container = document.getElementById('loading-container');
            if (!container) return;
            const bar = container.querySelector('.loading-progress-bar');
            const wrapper = container.querySelector('.loading-progress');
            if (bar) bar.style.width = `${pct}%`;
            if (wrapper) wrapper.setAttribute('aria-valuenow', String(pct));
        },

        /**
         * Show main UI and hide loading screen
         * @memberof App
         * @private
         */
        _showMainUI() {
            const loadingContainer = document.getElementById('loading-container');
            const logoContainer = document.getElementById('logo-container');
            const tagsWrapper = document.getElementById('tags-wrapper');

            if (loadingContainer) loadingContainer.style.display = 'none';
            if (logoContainer) logoContainer.classList.remove('initially-hidden');
            this.elements.filterContainer.classList.remove('initially-hidden');
            tagsWrapper.classList.remove('initially-hidden');

            // Remove tags-collapsed so panel is visible
            this.elements.filterPanel.classList.remove('tags-collapsed');
        },

        /**
         * Load and process full dataset asynchronously
         * @memberof App
         * @param {Object} urlParams - Parsed URL parameters
         * @async
         * @returns {Promise<void>}
         * @private
         */
        async _loadFullData(urlParams) {
            const FP = (typeof window !== 'undefined' && window.FilterProfiler) || null;
            const profile = FP && FP.enabled;
            if (profile) FP.start('Phase 2: full data load');

            const indicator = document.getElementById('phase2-loading-indicator');
            if (indicator) indicator.classList.add('visible');

            try {
                if (profile) FP.mark('fp:p2:fetch-start');

                // Build list of chunks not yet loaded: every day chunk in the
                // manifest plus the remainder, minus whichever one Phase 1
                // already grabbed. Fetched in parallel; HTTP/2 multiplexes.
                const allChunks = (this.state.manifest.days || []).map((_, i) => `day${i}`);
                allChunks.push(this.config.REMAINDER_CHUNK);
                const remainingChunks = allChunks.filter(c => !this.state.loadedChunks.has(c));

                const fetches = [];
                for (const chunk of remainingChunks) {
                    fetches.push(DataManager.fetchData(`${this.config.DATA_DIR}events.${chunk}.json`));
                    fetches.push(DataManager.fetchData(`${this.config.DATA_DIR}locations.${chunk}.json`));
                }
                const fetched = await Promise.all(fetches);

                const fullEventData = [];
                const fullLocationData = [];
                for (let i = 0; i < remainingChunks.length; i++) {
                    fullEventData.push(...(fetched[i * 2] || []));
                    fullLocationData.push(...(fetched[i * 2 + 1] || []));
                    this.state.loadedChunks.add(remainingChunks[i]);
                }
                if (profile) {
                    FP.mark('fp:p2:fetch-end');
                    FP.measure('fp:p2:fetch+parse', 'fp:p2:fetch-start', 'fp:p2:fetch-end');
                }

                // Chunked merge — yields to main thread between batches so map clicks
                // and typing stay responsive during the heavy ~30k-event processing.
                await DataManager.processFullDataAsync(
                    fullEventData,
                    fullLocationData,
                    this.state,
                    this.config,
                    (done, total) => {
                        if (indicator) {
                            const pct = Math.round((done / total) * 100);
                            indicator.querySelector('.phase2-progress').textContent = `${pct}%`;
                        }
                    }
                );
                if (profile) {
                    FP.mark('fp:p2:processFullData');
                    FP.measure('fp:p2:processFullData', 'fp:p2:fetch-end', 'fp:p2:processFullData');
                }

                DataManager.calculateTagFrequencies(this.state);
                DataManager.processTagHierarchy(this.state, this.config);
                if (profile) {
                    FP.mark('fp:p2:tagHier');
                    FP.measure('fp:p2:tagFreq+hierarchy', 'fp:p2:processFullData', 'fp:p2:tagHier');
                }

                // Yield once before the next big block so any pending input fires.
                await new Promise(r => setTimeout(r, 0));

                await DataManager.buildSearchIndexAsync(this.state);
                if (profile) {
                    FP.mark('fp:p2:searchIndex');
                    FP.measure('fp:p2:buildSearchIndex', 'fp:p2:tagHier', 'fp:p2:searchIndex');
                }

                await MapManager.loadEmojiImagesChunked(this.state.locationsByLatLng);
                if (profile) {
                    FP.mark('fp:p2:emoji');
                    FP.measure('fp:p2:loadEmojiImages', 'fp:p2:searchIndex', 'fp:p2:emoji');
                }

                this.updateFilteredEventList({ skipDisplay: true });
                // Lightweight refresh — preserves user selections made during Phase 1
                // and avoids re-instantiating SectionRenderer / GestureHandler / etc.
                FilterPanelUI.refreshAvailableTags({
                    allAvailableTags: this.state.allAvailableTags,
                    initialGlobalFrequencies: this.state.tagFrequencies
                });
                if (profile) {
                    FP.mark('fp:p2:initPanel');
                    FP.measure('fp:p2:filterList+refreshPanel', 'fp:p2:emoji', 'fp:p2:initPanel');
                }

                // Re-apply URL-param tag selections — these might reference tags
                // that didn't exist in Phase 1 and were skipped earlier. Idempotent
                // for tags that were already selected.
                if (urlParams.tags && urlParams.tags.length > 0) {
                    FilterPanelUI.selectTags(urlParams.tags, (tag) => TagColorManager.assignColorToTag(tag));
                }

                this.filterAndDisplayEvents();
                if (profile) {
                    FP.mark('fp:p2:render');
                    FP.measure('fp:p2:filterAndDisplayEvents', 'fp:p2:initPanel', 'fp:p2:render');
                }

                if (indicator) {
                    indicator.classList.remove('visible');
                    indicator.classList.add('done');
                }

            } catch (error) {
                if (indicator) indicator.classList.remove('visible');
                console.error("Failed to load full dataset:", error);

                // Show toast notification for full dataset loading errors
                // (Less critical than initial load failure, so we don't update the loading container)
                ToastNotifier.showToast(
                    `Could not load complete dataset: ${error.message || 'Unknown error'}`,
                    'error',
                    Constants.UI.TOAST_DURATION_MEDIUM
                );
            } finally {
                const FP = (typeof window !== 'undefined' && window.FilterProfiler) || null;
                if (FP && FP.enabled) FP.flush();
            }
        },

        /**
         * Initialize the application
         * Loads data in two phases: initial data for quick startup, then full dataset
         * Sets up all modules, UI components, and event listeners
         * @async
         * @returns {Promise<void>}
         */
        async init() {
            const loadingContainer = document.getElementById('loading-container');

            // Parse URL parameters
            const urlParams = this._parseAndCleanUrlParams();

            // Initialize welcome modal early so it can be closed during loading
            ModalManager.initWelcomeModal();

            // Show welcome modal for first-time visitors
            ModalManager.showWelcomeModalIfFirstVisit();

            // Yield to allow modal event handlers to be registered before heavy work
            await new Promise(resolve => setTimeout(resolve, 0));

            // --- Phase 1: Load Initial Data ---
            try {
                this._setLoadingProgress(5);

                // Start the base map and load the data CONCURRENTLY. The map's
                // style/tiles/glyphs and the event/location JSON are independent,
                // so overlapping them shaves the (previously serial) map-init tail
                // off the time-to-interactive — the largest remaining win on slow
                // connections.
                await Promise.all([
                    this._startMap(),
                    this._loadInitialData()
                ]);
                this._setLoadingProgress(45);

                // Modules that need the loaded data, then UI wiring.
                this._initDataDependentModules();
                this._setupUIComponents(urlParams);
                this._setLoadingProgress(65);

                // Wait for the base map tiles to be ready before showing markers
                // (prevents markers over a blank/ocean background). Glyphs/labels
                // are intentionally NOT awaited here — see initMap's mapLoadPromise.
                await this.state.mapLoadPromise;
                this._setLoadingProgress(85);

                this.filterAndDisplayEvents();
                this._setLoadingProgress(100);
                this._showMainUI();

                // Mark initial load as complete
                this.state.isInitialLoad = false;

                // Initialize browser history for back/forward navigation
                HistoryManager.init(this.state.map, {
                    getSelectedLocationKey: () => this.state.selectedLocationKey,
                    getTagStates: () => FilterPanelUI.getTagStates(),
                    getSelectedDates: () => this.state.datePickerInstance?.selectedDates || [],
                    getSearchTerm: () => this.state.searchTerm,
                    getDatePicker: () => this.state.datePickerInstance,
                    performSearch: (term) => {
                        this.elements.omniSearchInput.value = term;
                        this.performSearch(term);
                    },
                    updateFilteredEventList: () => this.updateFilteredEventList(),
                    onFilterChange: () => {
                        this.filterAndDisplayEvents();
                    },
                });
            } catch (error) {
                console.error("Failed to initialize app with initial data:", error);

                // Display user-friendly error message
                if (loadingContainer) {
                    const p = loadingContainer.querySelector('p');
                    if (p) {
                        p.textContent = error.message || 'Failed to load events. Please try again later.';
                    }
                }

                // Also show a toast notification with the error
                ToastNotifier.showToast(
                    error.message || 'Failed to load events. Please try again later.',
                    'error',
                    Constants.UI.TOAST_DURATION_LONG
                );

                return; // Stop if initial load fails
            }

            // --- Phase 2: Asynchronously Load Full Data ---
            await this._loadFullData(urlParams);
        },

        /**
         * Initialize the ThemeManager module
         * Sets up theme switching functionality and callbacks for theme-dependent updates
         * @memberof App
         */
        initThemeManager() {
            // Initialize ThemeManager
            ThemeManager.init({
                appState: this.state,
                config: this.config,
                onThemeChange: (theme) => {
                    // Reassign colors for selected tags with new theme palette
                    TagColorManager.reassignTagColors();
                    FilterPanelUI.renderChipBar();
                }
            });
        },

        /**
         * Handle special search terms (Easter eggs)
         * - "debug": Toggle debug mode visualization
         * @memberof App
         * @param {string} term - The search term to check
         */
        handleSpecialSearchTerms(term) {
            if (term === 'debug') {
                this.state.debugMode = !this.state.debugMode;
                this.updateDebugOverlay();
            }
        },

        /**
         * Perform search across locations, events, and tags
         * Uses SearchManager for scoring and TagFilterUI for rendering
         * @memberof App
         * @param {string} term - The search term
         */
        performSearch(term) {
            const FP = (typeof window !== 'undefined' && window.FilterProfiler) || null;
            const run = () => {
                const previousTerm = this.state.searchTerm;
                this.state.searchTerm = term;

                if (FP) FP.mark('fp:search:start');
                const dynamicFrequencies = FilterPanelUI.getDynamicFrequencies();
                const selectedTagsWithColors = TagColorManager.getSelectedTagsWithColors();
                const results = SearchManager.search(term, dynamicFrequencies, selectedTagsWithColors);
                if (FP) {
                    FP.mark('fp:search:scored');
                    FP.measure('fp:search:scoring', 'fp:search:start', 'fp:search:scored');
                }

                FilterPanelUI.render(results, term, this.state.debugMode);

                if (term !== previousTerm && this.state.currentFilteredLocations) {
                    const locationsToDisplay = this._applySearchTermFilter(this.state.currentFilteredLocations);
                    MarkerController.displayEventsOnMap(locationsToDisplay);
                }
            };
            return FP ? FP.wrap(`performSearch "${term}"`, run) : run();
        },

        /**
         * Handle click on a search result
         * Flies to the location and opens the marker popup
         * @memberof App
         * @param {Object} result - The search result object
         * @param {string} result.type - Result type ('location' or 'event')
         * @param {string} result.ref - Reference to location key or event ID
         */
        handleSearchResultClick(result) {
            if (result.type === 'location' || result.type === 'event') {
                let lat, lng;
                if (result.type === 'location') {
                    [lat, lng] = result.ref.split(',').map(Number);
                } else { // event
                    const event = this.state.eventsById[result.ref];
                    if (!event || !event.locationKey) return;
                    [lat, lng] = event.locationKey.split(',').map(Number);
                }
                MarkerController.flyToLocationAndOpenPopup(lat, lng, result.type === 'event' ? result.ref : null);
            }
            // Organizer results are rendered as interactive tag chips (see
            // TagStateManager.createSearchResultButton) and toggle the organizer
            // filter directly, so they never reach this fly-to handler.
        },

        /**
         * Update the list of events filtered by date range and location tags
         * Rebuilds event lookups and tag index, then triggers display update
         * @memberof App
         */
        updateFilteredEventList({ skipDisplay = false } = {}) {
            const FP = (typeof window !== 'undefined' && window.FilterProfiler) || null;
            const run = () => {
                if (FP) FP.mark('fp:dates:start');

                const selectedDates = this.state.datePickerInstance.selectedDates;
                if (selectedDates.length < 1) {
                    this.state.allEventsFilteredByDateAndLocation = [];
                } else {
                    // A lone start date (mid range-pick) acts as a single-day
                    // range (start, start) so filtering applies on the first click.
                    const startDate = selectedDates[0];
                    const endDate = selectedDates.length >= 2 ? selectedDates[1] : selectedDates[0];
                    let events = FilterManager.filterEventsByDateRange(startDate, endDate);

                    if (FP) {
                        FP.mark('fp:dates:byRange');
                        FP.measure('fp:dates:filterByDateRange', 'fp:dates:start', 'fp:dates:byRange');
                    }

                    if (this.state.selectedGeotags && this.state.selectedGeotags.size > 0) {
                        events = events.filter(event => {
                            if (!event.locationKey) return false;
                            const locationInfo = this.state.locationsByLatLng[event.locationKey];
                            if (!locationInfo || !locationInfo.tags) return false;
                            return locationInfo.tags.some(locationTag => this.state.selectedGeotags.has(locationTag));
                        });
                    }
                    this.state.allEventsFilteredByDateAndLocation = events;
                }

                if (FP) FP.mark('fp:dates:filtered');

                DataManager.groupEventsByLatLngInDateRange(this.state);

                if (FP) {
                    FP.mark('fp:dates:grouped');
                    FP.measure('fp:dates:groupByLatLng', 'fp:dates:filtered', 'fp:dates:grouped');
                }

                DataManager.buildTagIndex(this.state, this.state.allEventsFilteredByDateAndLocation);

                if (FP) {
                    FP.mark('fp:dates:tagIndex');
                    FP.measure('fp:dates:buildTagIndex', 'fp:dates:grouped', 'fp:dates:tagIndex');
                }

                if (!skipDisplay) {
                    this.filterAndDisplayEvents();
                }
            };
            return FP ? FP.wrap('updateFilteredEventList', run) : run();
        },

        /**
         * Check if coordinates are within NYC bounds
         * @param {number} lat - Latitude
         * @param {number} lng - Longitude
         * @returns {boolean} True if within NYC bounds
         * @memberof App
         */
        isWithinNYC(lat, lng) {
            const bounds = this.config.NYC_BOUNDS;
            return lat >= bounds.latMin && lat <= bounds.latMax &&
                   lng >= bounds.lngMin && lng <= bounds.lngMax;
        },

        /**
         * Get user's current location via Geolocation API
         * Returns null if geolocation is unavailable, denied, or location is outside NYC
         * @returns {Promise<{lat: number, lng: number}|null>}
         * @memberof App
         */
        async getUserLocation() {
            if (!navigator.geolocation) {
                return null;
            }

            try {
                const position = await new Promise((resolve, reject) => {
                    navigator.geolocation.getCurrentPosition(resolve, reject, {
                        enableHighAccuracy: false,
                        timeout: 5000,
                        maximumAge: 300000 // Cache for 5 minutes
                    });
                });

                const lat = position.coords.latitude;
                const lng = position.coords.longitude;

                // Only use location if within NYC area
                if (this.isWithinNYC(lat, lng)) {
                    return { lat, lng };
                }
                return null;
            } catch (error) {
                // Geolocation denied or failed - silently fall back to default
                return null;
            }
        },

        /**
         * Handle location toggle change from settings
         * Requests geolocation when enabled and recenters the map
         * @param {boolean} enabled - Whether location is enabled
         * @memberof App
         */
        async handleLocationToggle(enabled) {
            if (enabled) {
                ModalManager.setLocationStatus('Locating...', 'loading');
                const location = await this.getUserLocation();

                if (location) {
                    this.state.userLocation = location;
                    // Recenter map to user's location
                    this.state.map.flyTo({
                        center: [location.lng, location.lat],
                        zoom: this.config.MAP_USER_LOCATION_ZOOM,
                        duration: 1000
                    });
                    ModalManager.setLocationStatus('', '');
                } else {
                    // Location denied or outside NYC
                    ModalManager.setLocationStatus('Not available', '');
                }
            } else {
                this.state.userLocation = null;
                ModalManager.setLocationStatus('', '');
            }
        },

        /**
         * Initialize the MapLibre GL map with tiles, controls, and event handlers
         * Sets up map layers, markers, and interactive behaviors
         * @memberof App
         */
        initMap() {
            // Determine initial view: URL params > user location > default
            const urlParams = this.state.urlParams || {};
            let initialView, initialZoom;

            if (urlParams.lat !== undefined && urlParams.lng !== undefined) {
                // URL parameters take highest priority
                initialView = [urlParams.lat, urlParams.lng];
                initialZoom = urlParams.zoom !== undefined ? urlParams.zoom : this.config.MAP_INITIAL_ZOOM;
            } else if (this.state.userLocation) {
                // User location (if within NYC) takes second priority
                initialView = [this.state.userLocation.lat, this.state.userLocation.lng];
                initialZoom = this.config.MAP_USER_LOCATION_ZOOM;
            } else {
                // Fall back to default
                initialView = this.config.MAP_INITIAL_VIEW;
                initialZoom = this.config.MAP_INITIAL_ZOOM;
            }

            // Get MapLibre style URL for current theme
            const styleUrl = ThemeManager.getStyleUrlForCurrentTheme();

            // Create native MapLibre GL map
            this.state.map = new maplibregl.Map({
                container: 'map',
                style: styleUrl,
                center: [initialView[1], initialView[0]], // MapLibre uses [lng, lat]
                zoom: initialZoom,
                maxZoom: this.config.MAP_MAX_ZOOM,
                attributionControl: false,
                dragPan: false, // Disable initially, re-enable without inertia below
                fadeDuration: 0 // No crossfade on label collision changes
            });

            // Re-enable drag pan without inertia (momentum after releasing)
            this.state.map.dragPan.enable({
                maxSpeed: 0
            });

            // Attribution is displayed in about.html instead of on the map

            // Add zoom control (navigation control)
            const navControl = new maplibregl.NavigationControl({
                showCompass: true,
                showZoom: true,
                visualizePitch: true
            });
            this.state.map.addControl(navControl, 'bottom-right');

            // Override the compass click to use a faster reset animation
            // The compass button resets bearing and pitch to 0
            const compassButton = document.querySelector('.maplibregl-ctrl-compass');
            if (compassButton) {
                compassButton.addEventListener('click', (e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    this.state.map.easeTo({
                        bearing: 0,
                        pitch: 0,
                        duration: 150
                    });
                }, true); // Use capture to intercept before MapLibre's handler
            }

            // Initialize MapManager with the MapLibre map. bgcolors may not be
            // loaded yet (the map is started in parallel with the data fetch) —
            // App.init calls MapManager.setMarkerColors() once tagConfig arrives,
            // before any marker is drawn.
            MapManager.init(this.state.map, {}, (this.state.tagConfig && this.state.tagConfig.bgcolors) || {});

            // Create debug container for DOM-based debug overlay
            const mapContainer = this.state.map.getContainer();
            this.state.debugContainer = document.createElement('div');
            this.state.debugContainer.id = 'debug-overlay';
            this.state.debugContainer.style.position = 'absolute';
            this.state.debugContainer.style.top = '0';
            this.state.debugContainer.style.left = '0';
            this.state.debugContainer.style.width = '100%';
            this.state.debugContainer.style.height = '100%';
            this.state.debugContainer.style.pointerEvents = 'none';
            this.state.debugContainer.style.zIndex = '1000';
            mapContainer.appendChild(this.state.debugContainer);

            // Create a promise that resolves once the map is ready to show
            // markers. We resolve as soon as the base vector tiles for the
            // initial viewport have loaded (geography is painted → no markers
            // over a blank/ocean background) WITHOUT waiting for the map's full
            // `load` event, which also blocks on the ~0.5 MB of label glyph PBFs.
            // Labels (street names + marker text) fill in a beat later when the
            // glyphs arrive; until then the user already has the map + emoji
            // markers + popups and can pan/zoom freely.
            this.state.mapLoadPromise = new Promise((resolve) => {
                const map = this.state.map;
                let resolved = false;

                const onReady = () => {
                    if (resolved) return;
                    resolved = true;
                    map.off('sourcedata', onSourceData);
                    map.off('load', onReady);

                    // Adjust the initial view so the visible center (accounting for filter panel)
                    // ends up at the desired initial view coordinates (from URL params or default)
                    const desiredVisibleCenter = { lat: initialView[0], lng: initialView[1] };
                    ViewportManager.adjustMapToVisibleCenter(map, desiredVisibleCenter, false);

                    // Load emoji images and set up WebGL marker interactions.
                    // The map can become ready before Phase-1 data has loaded
                    // (they run in parallel), so locationsByLatLng may be absent;
                    // updateMarkerData() lazily adds any missing emoji images later.
                    MapManager.loadEmojiImages(this.state.locationsByLatLng || {});
                    MapManager.setupMarkerInteractions();

                    // Initialize mobile bottom sheet for popups
                    BottomSheet.init(map);

                    // Fade in the map container
                    const mapContainerEl = document.getElementById('map-container');
                    if (mapContainerEl) {
                        mapContainerEl.classList.add('map-loaded');
                    }

                    resolve();
                };

                // Fire as soon as the base source's viewport tiles are all in.
                const onSourceData = (e) => {
                    if (e.sourceId === 'protomaps' && e.isSourceLoaded && map.isStyleLoaded()) {
                        onReady();
                    }
                };
                map.on('sourcedata', onSourceData);

                // Fallback: the full `load` event always resolves us, covering
                // edge cases (e.g. no tiles for the viewport, or sourcedata
                // already fired before this handler attached).
                map.on('load', onReady);
            });

            // Handle popup open events (custom event fired by MapManager or BottomSheet)
            this.state.map.on('popupopen', (e) => {
                const { locationKey, popup, lngLat } = e;
                if (locationKey) {
                    this.state.selectedLocationKey = locationKey;

                    // Skip auto-pan during history restore (map is already positioned)
                    if (!HistoryManager.isRestoring()) {
                        if (!popup) {
                            // Bottom sheet (mobile) — pan marker to visible area above the sheet
                            requestAnimationFrame(() => {
                                const { filterPanelHeight } = ViewportManager.getFilterPanelDimensions();
                                const viewportHeight = window.innerHeight;
                                const sheetHeight = viewportHeight * 0.40; // peek snap
                                const visibleCenter = filterPanelHeight + (viewportHeight - filterPanelHeight - sheetHeight) / 2;
                                const offsetY = visibleCenter - viewportHeight / 2;

                                this.state.map.easeTo({
                                    center: [lngLat.lng, lngLat.lat],
                                    offset: [0, offsetY],
                                    duration: 300
                                });
                            });
                        } else {
                            // Desktop popup — measure and pan to fit
                            requestAnimationFrame(() => {
                                const popupElement = popup.getElement();
                                if (!popupElement) return;

                                const contentElement = popupElement.querySelector('.maplibre-popup-content');
                                const actualWidth = contentElement ? contentElement.offsetWidth : popupElement.offsetWidth;
                                const actualHeight = contentElement ? contentElement.offsetHeight : popupElement.offsetHeight;

                                const panOffset = ViewportManager.calculatePopupPanOffset(
                                    this.state.map,
                                    lngLat,
                                    actualHeight,
                                    actualWidth
                                );

                                if (panOffset) {
                                    this.state.map.panBy([-panOffset.panX, -panOffset.panY], { animate: true, duration: 100 });
                                }
                            });
                        }
                    }

                    // Re-run search to update the UI with the selected location
                    const currentTerm = this.elements.omniSearchInput.value.toLowerCase();
                    this.performSearch(currentTerm);

                    HistoryManager.push();
                }
            });

            this.state.map.on('moveend', () => {
                // The map is created in parallel with the data load and fires
                // moveend (e.g. from the initial adjustMapToVisibleCenter) before
                // the data-dependent modules (MarkerController/FilterPanelUI) are
                // ready. Skip during init — the explicit filterAndDisplayEvents()
                // at the end of init() performs the first render.
                if (this.state.isInitialLoad) return;
                const FP = (typeof window !== 'undefined' && window.FilterProfiler) || null;
                const run = () => {
                    if (FP) FP.mark('fp:moveend:start');
                    this.updateVisibleItems();
                    if (FP) {
                        FP.mark('fp:moveend:visibleItems');
                        FP.measure('fp:moveend:updateVisibleItems', 'fp:moveend:start', 'fp:moveend:visibleItems');
                    }
                    MarkerController.refreshLabelsForViewport();
                    if (FP) {
                        FP.mark('fp:moveend:labels');
                        FP.measure('fp:moveend:refreshLabels', 'fp:moveend:visibleItems', 'fp:moveend:labels');
                    }
                    clearTimeout(this._moveendSearchTimeout);
                    this._moveendSearchTimeout = setTimeout(() => {
                        const currentTerm = this.elements.omniSearchInput.value.toLowerCase();
                        this.performSearch(currentTerm);
                    }, 150);
                    this.updateDebugOverlay();
                };
                if (FP) FP.wrap('moveend', run); else run();
            });

            // Handle popup close events (custom event fired by MapManager)
            this.state.map.on('popupclose', (e) => {
                const { locationKey } = e;
                if (!locationKey) return;

                if (this.state.selectedLocationKey === locationKey) {
                    this.state.selectedLocationKey = null;
                    // Re-run search to update the UI and remove the selected location
                    const currentTerm = this.elements.omniSearchInput.value.toLowerCase();
                    this.performSearch(currentTerm);

                    HistoryManager.push();
                }
            });
        },

        /**
         * Initialize the EmojiManager module
         * Sets up emoji font loading and switching functionality
         * @memberof App
         */
        initEmojiManager() {
            // Initialize EmojiManager
            EmojiManager.init({
                appState: this.state
            });
        },

        /**
         * Initialize the ViewportManager module
         * Sets up viewport calculations accounting for filter panel overlay
         * @memberof App
         */
        initViewportManager() {
            // Initialize ViewportManager
            ViewportManager.init({
                appState: this.state
            });
        },

        /**
         * Initialize the MarkerController module
         * Sets up marker creation, updating, and lifecycle management
         * @memberof App
         */
        initMarkerController() {
            // Initialize MarkerController with provider objects
            MarkerController.init({
                appState: this.state,
                config: this.config,
                filterProvider: {
                    getTagStates: () => FilterPanelUI.getTagStates(),
                    getSelectedDates: () => this.state.datePickerInstance.selectedDates
                },
                eventProvider: {
                    getForceDisplayEventId: () => this.state.forceDisplayEventId,
                    setForceDisplayEventId: (id) => { this.state.forceDisplayEventId = id; }
                }
            });
        },

        /**
         * Initialize the filter panel UI and search functionality
         * Sets up SearchManager, FilterManager, and FilterPanelUI with callbacks
         * @memberof App
         */
        /**
         * Initialize SearchManager + FilterManager. These only need appState/
         * config (no loaded data), so they run in _startMap — BEFORE the map can
         * fire a moveend→performSearch. Initializing them late (after the data
         * load) left a window on slow connections where a search ran against a
         * not-yet-initialized SearchManager (null appState).
         * @memberof App
         */
        initSearchAndFilterManagers() {
            SearchManager.init({
                appState: this.state
            });
            FilterManager.init({
                appState: this.state,
                config: this.config
            });
        },

        initFilterPanelUI() {
            FilterPanelUI.init({
                allAvailableTags: this.state.allAvailableTags,
                tagConfigBgColors: this.state.tagConfig.bgcolors,
                tagDescendantsOf: this.state.tagDescendantsOf,
                tagParentsOf: this.state.tagParentsOf,
                tagChildrenOf: this.state.tagChildrenOf,
                structuralFormatTags: this.state.structuralFormatTags,
                tagEmojiMap: this.state.tagEmojiMap,
                getSelectedTagsWithColors: () => TagColorManager.getSelectedTagsWithColors(),
                initialGlobalFrequencies: this.state.tagFrequencies,
                resultsContainerDOM: this.elements.resultsContainer,
                onFilterChangeCallback: () => {
                    this.filterAndDisplayEvents();
                    HistoryManager.push();
                },
                onSearchResultClick: (result) => this.handleSearchResultClick(result),
                defaultMarkerColor: this.config.DEFAULT_MARKER_COLOR_DARK,
                performSearch: (term) => this.performSearch(term),
                getSearchTerm: () => this.elements.omniSearchInput.value.toLowerCase(),
                getVisibleTagFrequencies: () => this.state.visibleTagFrequencies,
                colorProvider: {
                    getTagColor: (tag) => TagColorManager.getTagColor(tag),
                    assignColorToTag: (tag) => TagColorManager.assignColorToTag(tag),
                    unassignColorFromTag: (tag) => TagColorManager.unassignColorFromTag(tag)
                }
            });
            FilterPanelUI.setAppProviders({ getSelectedLocationKey: () => this.state.selectedLocationKey });
            FilterPanelUI.render([]); // Render with empty results initially

            // Initialize PopupContentBuilder for creating marker popups
            PopupContentBuilder.init({
                createInteractiveTagButton: (tag) => FilterPanelUI.createInteractiveTagButton(tag),
                hierarchyTagsSet: this.state.hierarchyTagsSet,
                tagEmojiMap: this.state.tagEmojiMap,
                getDebugMode: () => this.state.debugMode
            });
        },

        /**
         * Filter locations by the current search term
         * Returns only locations where the location name or any event matches
         * @memberof App
         * @param {Object} filteredLocations - Locations grouped by key with event arrays
         * @returns {Object} Filtered locations matching the search term
         * @private
         */
        _applySearchTermFilter(filteredLocations) {
            const searchTerm = this.state.searchTerm;
            if (!searchTerm || searchTerm.trim().length === 0) {
                return filteredLocations;
            }

            const normalizedTerm = Utils.normalizeForSearch(searchTerm);
            if (!normalizedTerm) return filteredLocations;

            const searchIndex = this.state.searchIndex;
            const filtered = {};

            for (const locationKey in filteredLocations) {
                // Check if location name matches
                const locationText = searchIndex?.locations?.get(locationKey) || '';
                if (locationText.includes(normalizedTerm)) {
                    filtered[locationKey] = filteredLocations[locationKey];
                    continue;
                }

                // Check if any event at this location matches
                const events = filteredLocations[locationKey];
                const hasMatchingEvent = events.some(event => {
                    const eventText = searchIndex?.events?.get(event.id) || '';
                    return eventText.includes(normalizedTerm);
                });

                if (hasMatchingEvent) {
                    filtered[locationKey] = filteredLocations[locationKey];
                }
            }

            return filtered;
        },

        /**
         * Filter events by tags and display them on the map
         * Updates matching events, groups by location, and updates markers
         * @memberof App
         * @param {Object} [options={}] - Optional configuration
         */
        filterAndDisplayEvents(options = {}) {
            if (!this.state.datePickerInstance) {
                console.warn("filterAndDisplayEvents called before datePicker is initialized.");
                return;
            }

            const FP = (typeof window !== 'undefined' && window.FilterProfiler) || null;
            if (FP) FP.mark('fp:fade:start');

            // Find any open popup
            const openPopupInfo = MarkerController.findOpenPopup();
            const openPopup = openPopupInfo?.popup;

            const selectedDates = this.state.datePickerInstance.selectedDates;
            // A lone start date (mid range-pick) is treated as a single-day
            // range, so only bail when nothing is selected at all.
            if (selectedDates.length < 1) {
                return;
            }

            const currentTagStates = FilterPanelUI.getTagStates();

            // Use FilterManager to filter events by tags
            const allMatchingEventsFlatList = FilterManager.filterEventsByTags(
                currentTagStates,
                this.state.allEventsFilteredByDateAndLocation
            );

            if (FP) {
                FP.mark('fp:fade:byTags');
                FP.measure('fp:fade:filterByTags', 'fp:fade:start', 'fp:fade:byTags');
            }

            // Store the computed lists in the state for use by other functions like search
            this.state.currentlyMatchingEvents = allMatchingEventsFlatList;

            // Group events by location
            const filteredLocations = FilterManager.groupEventsByLocation(allMatchingEventsFlatList);
            this.state.currentlyMatchingLocationKeys = new Set(Object.keys(filteredLocations));
            this.state.currentFilteredLocations = filteredLocations;

            if (FP) {
                FP.mark('fp:fade:grouped');
                FP.measure('fp:fade:groupByLoc', 'fp:fade:byTags', 'fp:fade:grouped');
            }

            // After updating all matching items, update the visible subset as well.
            this.updateVisibleItems();

            if (FP) {
                FP.mark('fp:fade:viewport');
                FP.measure('fp:fade:updateVisibleItems', 'fp:fade:grouped', 'fp:fade:viewport');
            }

            // Update open popup/bottom sheet content if there is one
            if (openPopupInfo) {
                MarkerController.updateOpenPopupContent(openPopup);
            }

            // Apply search term filter for marker display
            const locationsToDisplay = this._applySearchTermFilter(filteredLocations);

            // Display markers on map
            MarkerController.displayEventsOnMap(locationsToDisplay);

            if (FP) {
                FP.mark('fp:fade:markers');
                FP.measure('fp:fade:displayOnMap', 'fp:fade:viewport', 'fp:fade:markers');
            }

            FilterPanelUI.updateView(allMatchingEventsFlatList);

            if (FP) {
                FP.mark('fp:fade:end');
                FP.measure('fp:fade:updateView-wall', 'fp:fade:markers', 'fp:fade:end');
            }
        },

        /**
         * Update the visible items based on current map viewport
         * Calculates viewport bounds, distances, and filters events by visibility
         * @memberof App
         */
        updateVisibleItems() {
            if (!this.state.map) return;

            // Viewport bounds + per-location haversine distances depend only on
            // the camera (center/zoom/bearing/pitch), the window/panel size, and
            // the set of locations — NOT on tag filters. Recomputing them on
            // every tag toggle re-runs a haversine over all ~2400 locations for
            // nothing (~2.3ms). Cache by a view signature and reuse when the map
            // hasn't moved; moveend/resize/Phase-2-load change the signature and
            // force a fresh compute.
            const m = this.state.map;
            const c = m.getCenter();
            const viewSig = [
                c.lng.toFixed(6), c.lat.toFixed(6),
                m.getZoom().toFixed(4), m.getBearing().toFixed(2), m.getPitch().toFixed(2),
                window.innerWidth, window.innerHeight,
                Object.keys(this.state.locationsByLatLng).length,
                this.state.isInitialLoad ? 1 : 0
            ].join('|');

            let viewportData;
            if (this._viewportCache && this._viewportCache.sig === viewSig) {
                viewportData = this._viewportCache.data;
            } else {
                viewportData = ViewportManager.updateViewportCalculations(
                    m,
                    this.state.locationsByLatLng,
                    this.state.isInitialLoad
                );
                if (!viewportData) return;
                this._viewportCache = { sig: viewSig, data: viewportData };
            }

            if (!viewportData) return;

            // Update state with calculated values
            this.state.visibleCenter = viewportData.visibleCenter;
            this.state.locationDistances = viewportData.locationDistances;

            // Use FilterManager to filter by viewport
            const viewportResults = FilterManager.filterEventsByViewport(
                this.state.currentlyMatchingEvents,
                viewportData.bounds,
                viewportData.visibleCenter,
                viewportData.locationDistances
            );

            this.state.currentlyVisibleMatchingEvents = viewportResults.visibleEvents;
            this.state.currentlyVisibleMatchingLocationKeys = viewportResults.visibleLocationKeys;
            this.state.visibleTagFrequencies = viewportResults.visibleTagFrequencies;
        },

        /**
         * Update debug visualization overlay
         * Delegates to ViewportManager for rendering
         * @memberof App
         */
        updateDebugOverlay() {
            ViewportManager.updateDebugOverlay(
                this.state.map,
                this.state.debugContainer,
                this.state.debugMode
            );
        },

        /**
         * Generate a shareable URL with current map state and copy to clipboard
         */
        shareCurrentView() {
            try {
                // Get current visible center (accounting for filter panel) and zoom
                const center = ViewportManager.calculateVisibleCenter(this.state.map) || this.state.map.getCenter();
                const zoom = this.state.map.getZoom();

                // Get current date range
                const selectedDates = this.state.datePickerInstance?.selectedDates || [];

                // Get selected tags
                const tagStates = FilterPanelUI.getTagStates();
                const selectedTags = Object.entries(tagStates)
                    .filter(([, state]) => state === 'selected')
                    .map(([tag]) => tag);

                // Build URL parameters
                const params = {
                    lat: center.lat,
                    lng: center.lng,
                    zoom: zoom
                };

                if (selectedDates.length >= 2) {
                    params.start = selectedDates[0];
                    params.end = selectedDates[1];
                }

                if (selectedTags.length > 0) {
                    params.tags = selectedTags;
                }

                // Generate the shareable URL using URLParams module
                const shareUrl = URLParams.generateShareUrl(params);

                // Copy to clipboard
                navigator.clipboard.writeText(shareUrl).then(() => {
                    ToastNotifier.showToast('Link copied to clipboard!', 'success', 3000);
                }).catch(err => {
                    console.error('Failed to copy to clipboard:', err);
                    // Fallback: show the URL in a toast for manual copying
                    ToastNotifier.showToast('Could not copy automatically. URL: ' + shareUrl, 'info', 5000);
                });

            } catch (error) {
                console.error('Error generating share URL:', error);
                ToastNotifier.showToast('Failed to generate share link', 'error', 3000);
            }
        }
    };

    App.init();
});