/**
 * Detect Android app and add body class for app-specific styling
 * Must run before DOMContentLoaded to apply styles early
 */
(function() {
    // Android only: the iOS app's UA also contains "FomoApp", but iOS must NOT
    // get this class — its .fomo-android-app 36px safe-area fallback undercuts
    // the real env(safe-area-inset-top) (62px on Dynamic Island iPhones).
    if (navigator.userAgent.includes('FomoApp') && /Android/i.test(navigator.userAgent)) {
        document.documentElement.classList.add('fomo-android-app');
    }
})();

/**
 * Main application entry point - initializes the events mapping application
 * Coordinates all modules and manages application state
 */
document.addEventListener('DOMContentLoaded', () => {
    // City/region config injected by build.js (window.__CITY__). Defensive default
    // keeps the app from hard-crashing if served unbuilt; the build always injects it.
    const CITY = (typeof window !== 'undefined' && window.__CITY__) || { map: {} };

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
         * @property {Object} tagConfig - Tag configuration (geotags)
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
            hierarchyTagsSet: new Set(),
            tagDescendantsOf: {},
            tagParentsOf: {},
            tagChildrenOf: {},
            tagEmojiMap: {},
            tagIconMap: {},
            tagSearchTerms: {},
            locationsByLatLng: {},
            tagFrequencies: {},
            datePickerInstance: null,
            allAvailableTags: [],
            eventTagIndex: {},
            allEventsFilteredByDate: [],
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
            dataFromCache: false, // Whether this session rendered from the DataCache snapshot
            todayStr: null, // Today's date (in the city timezone) captured at load
        },

        /**
         * Application configuration object
         * @type {Object}
         * @property {string} DATA_DIR - Base directory for per-day event/location data chunks
         * @property {string} MANIFEST_URL - URL for the chunk manifest (maps day0..dayN to dates)
         * @property {string} REMAINDER_CHUNK - Name of the chunk holding events beyond the dated days
         * @property {string} TAG_CONFIG_URL - URL for tag configuration
         * @property {string} TAG_HIERARCHY_URL - URL for the tag hierarchy
         * @property {string} ORGANIZERS_URL - URL for organizer data
         * @property {Date} START_DATE - Default start date for date range
         * @property {Date} END_DATE - Default end date for date range
         * @property {Array<string>} TAG_COLOR_PALETTE_DARK - Color palette for dark theme
         * @property {Array<string>} TAG_COLOR_PALETTE_LIGHT - Color palette for light theme
         * @property {Array<number>} MAP_INITIAL_VIEW - Initial map center [lat, lng]
         * @property {number} MAP_INITIAL_ZOOM - Initial map zoom level
         * @property {string} MAP_STYLE_DARK - Map style URL for dark theme
         * @property {string} MAP_STYLE_LIGHT - Map style URL for light theme
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
            MAP_INITIAL_VIEW: CITY.map.center,
            MAP_INITIAL_ZOOM: CITY.map.zoom,
            MAP_STYLE_DARK: 'data/map-style-dark.json?v=8',
            MAP_STYLE_LIGHT: 'data/map-style-light.json?v=8',
            MAP_MAX_ZOOM: 20
        },

        /**
         * Cached DOM elements for efficient access
         * @type {Object}
         * @property {HTMLElement} resultsContainer - Container for search results
         * @property {HTMLElement} datePicker - Date picker input element
         * @property {HTMLElement} datePickerSizer - Hidden element for measuring date picker width
         * @property {HTMLElement} filterContainer - Main filter container
         * @property {HTMLElement} filterPanel - Filter panel element
         * @property {HTMLElement} omniSearchInput - Search input element
         */
        elements: {
            resultsContainer: document.getElementById('results-container'),
            datePicker: document.getElementById('date-picker'),
            datePickerSizer: document.getElementById('date-picker-sizer'),
            filterContainer: document.getElementById('filter-container'),
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
            // us which day-chunk maps to today's NYC date. In cache mode this
            // (like every _loadDataFile below) reads the IndexedDB snapshot
            // instead of the network.
            const manifest = await this._loadDataFile(this.config.MANIFEST_URL);

            this.state.manifest = manifest || { days: [] };
            // An older cached app may have saved a new manifest but downloaded
            // only the legacy remainder. Keep that complete snapshot usable offline.
            if (this.state.dataFromCache && manifest?.remainderChunks?.length) {
                const required = manifest.remainderChunks.flatMap(c => [
                    `${this.config.DATA_DIR}events.${c}.json`,
                    `${this.config.DATA_DIR}events.${c}.desc.json`
                ]);
                const legacy = `${this.config.DATA_DIR}events.remainder.json`;
                const present = await DataCache.hasKeys([...required, legacy]);
                if (present.has(legacy) && required.some(url => !present.has(url))) {
                    this.state.manifest = { ...manifest, remainderChunks: undefined };
                }
            }
            this.state.loadedChunks = new Set();

            // Step 2: Load complete coverage of the URL's date range (or today).
            // Dates outside the manifest's day files require the tail partitions.
            const todayStr = Utils.getTodayInZone();
            this.state.todayStr = todayStr;
            const urlStart = this.state.urlParams?.start;
            const urlEnd = this.state.urlParams?.end;
            const end = urlEnd ? URLParams.formatDate(urlEnd) : null;
            const start = urlStart && (!end || end >= todayStr)
                ? URLParams.formatDate(urlStart) : todayStr;
            // Publish the complete requested date range on the first render.
            // Other dates can load without replacing this view afterwards.
            const requestedStart = start < todayStr ? todayStr : start;
            const initChunks = this._chunksForDates(requestedStart, end && end >= requestedStart ? end : requestedStart);
            this.state.initChunks = initChunks;
            initChunks.forEach(c => this.state.loadedChunks.add(c));

            // Step 3: Fetch everything else in a SINGLE parallel batch. The heavy
            // events chunk (~330 KB gz) now downloads concurrently with the
            // metadata instead of waiting for it — previously organizers.json
            // (~120 KB gz) sat on the critical path *before* the chunk fetch even
            // started, adding a full round-trip + its transfer to time-to-markers.
            const [tagConfig, tagHierarchy, organizersData, initEventData, initLocationData] = await Promise.all([
                this._loadDataFile(this.config.TAG_CONFIG_URL),
                this._loadDataFile(this.config.TAG_HIERARCHY_URL),
                this._loadDataFile(this.config.ORGANIZERS_URL),
                Promise.all(initChunks.map(c => this._loadDataFile(`${this.config.DATA_DIR}events.${c}.json`))).then(parts => parts.flat()),
                Promise.all([...new Set(initChunks.map(c => this._locationChunk(c)))].map(c =>
                    this._loadDataFile(`${this.config.DATA_DIR}locations.${c}.json`))).then(parts => parts.flat())
            ]);
            this.state.organizersById = organizersData || {};

            this.state.tagConfig = tagConfig;
            this.state.geotagsSet = new Set((tagConfig.geotags || []).map(tag => tag.toLowerCase()));

            // Build hierarchy maps from exported data
            const hierarchyMaps = DataManager.buildTagHierarchyMaps(tagHierarchy || { tags: [], keywords: [] });
            this.state.hierarchyTagsSet = hierarchyMaps.hierarchyTagsSet;
            this.state.tagDescendantsOf = hierarchyMaps.descendantsOf;
            this.state.tagParentsOf = hierarchyMaps.parentsOf;
            this.state.tagChildrenOf = hierarchyMaps.childrenOf;
            this.state.tagEmojiMap = hierarchyMaps.tagEmojiMap;
            this.state.tagIconMap = hierarchyMaps.tagIconMap;
            this.state.tagSearchTerms = hierarchyMaps.tagSearchTerms;
            this.state.formats = hierarchyMaps.formats;
            this.state.formatOnlyTags = hierarchyMaps.formatOnlyTags;
            this.state.neighborhoodTags = new Set([...hierarchyMaps.neighborhoodTags, ...(tagConfig.geotags || []).filter(tag => hierarchyMaps.hierarchyTagsSet.has(tag))]);
            this.state.tagRedirects = hierarchyMaps.tagRedirects;
            DiscoveryRanking.migrateTagAliases(this.state.tagRedirects);
            IconManager.setTagIcons(this.state.tagIconMap, this.state.tagEmojiMap);

            // Organizers participate in the tag filter system as namespaced
            // pseudo-tags (e.g. "organizer:123"). Register their names and fold
            // their emojis into tagEmojiMap so they render like any other tag
            // wherever a tag chip is drawn (popups, chip bar, search results).
            Utils.registerOrganizers(this.state.organizersById);
            for (const [id, org] of Object.entries(this.state.organizersById)) {
                const orgTag = Utils.makeOrganizerTag(id);
                if (orgTag && org && org.emoji) this.state.tagEmojiMap[orgTag] = org.emoji;
                if (orgTag && org?.icon_id) this.state.tagIconMap[orgTag] = org.icon_id;
            }

            // Initialize TagColorManager with color palettes. Emoji colors are
            // extracted live per emoji (no precomputed table needed).
            TagColorManager.init({
                darkPalette: this.config.TAG_COLOR_PALETTE_DARK,
                lightPalette: this.config.TAG_COLOR_PALETTE_LIGHT,
                tagEmojiMap: this.state.tagEmojiMap
            });

            DataManager.processInitialData([], initLocationData, this.state, this.config);
            await DataManager.processFullDataAsync(initEventData, [], this.state, this.config);
            DataManager.calculateTagFrequencies(this.state);
            DataManager.processTagHierarchy(this.state, this.config);
            DataManager.buildTagIndex(this.state);
            await DataManager.buildSearchIndexAsync(this.state);
        },

        /**
         * Initialize all core modules (emoji, theme, map, etc.)
         * @memberof App
         * @private
         * @async
         */
        async _startMap() {
            // Everything here is independent of the event/tag data, so it can run
            // (and kick off the base map's style/tile/glyph downloads) in PARALLEL
            // with _loadInitialData() instead of waiting for it. The base map needs
            // only the theme (for its style URL) and the initial center/zoom.
            IconManager.init();
            this.initThemeManager();
            ThemeManager.initTheme();

            // The map-label webfont must be loaded before the map bakes its TinySDF glyph
            // atlas, or labels render in the fallback font until reload.
            await ThemeManager.loadMapFont();

            this.initMap();
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
            FormatSelector.configure(this.state.formats);
            NeighborhoodSelector.configure(this.state.tagChildrenOf, this.state.neighborhoodTags);
            urlParams.tags = (urlParams.tags || []).map(t => this.state.tagRedirects[t] || t);
            const legacyNeighborhoods = (urlParams.tags || []).filter(t => this.state.neighborhoodTags.has(t));
            const legacyFormats = (urlParams.tags || []).filter(t => this.state.formatOnlyTags.has(t));
            urlParams.tags = [...new Set((urlParams.tags || [])
                .filter(t => !this.state.formatOnlyTags.has(t) && !this.state.neighborhoodTags.has(t))
                .map(t => this.state.tagRedirects[t] || t))];
            FormatSelector.init(this.state.formats, urlParams.formats ?? (legacyFormats.length ? FormatSelector.fromLegacyTags(legacyFormats) : null), () => {
                this._requestFilterUpdate(true);
                HistoryManager.push();
            });
            NeighborhoodSelector.init(this.state.tagChildrenOf, this.state.neighborhoodTags,
                urlParams.neighborhoods ?? (legacyNeighborhoods.length ? NeighborhoodSelector.fromLegacyTags(legacyNeighborhoods) : null), () => {
                    this._requestFilterUpdate(true);
                    HistoryManager.push();
                });
            // Apply URL parameter tag selections before date picker init
            // This ensures tags are selected when the date picker triggers initial filtering
            if (urlParams.tags && urlParams.tags.length > 0) {
                FilterPanelUI.selectTags(urlParams.tags, (tag) => TagColorManager.assignColorToTag(tag));
            }

            UIManager.initDatePicker(this.elements, this.config, this.state, {
                onDatePickerClose: (selectedDates) => {
                    const [newStart, newEnd] = selectedDates;
                    const [oldStart, oldEnd] = this.state.lastSelectedDates;

                    if (oldStart && oldEnd && newStart && newEnd && newStart.getTime() === oldStart.getTime() && newEnd.getTime() === oldEnd.getTime()) {
                        return;
                    }

                    this.state.lastSelectedDates = selectedDates;
                    // During init, skip display — filterAndDisplayEvents is called explicitly after map loads
                    if (this.state.isInitialLoad) this.updateFilteredEventList({ skipDisplay: true });
                    else this._requestFilterUpdate(true);

                    HistoryManager.push();
                }
            });
            FilterPanelUI.initOmniSearch({
                onSpecialSearchTerm: (term) => this.handleSpecialSearchTerms(term)
            });
            UIManager.initLogoMenu({
                onShareView: () => this.shareCurrentView()
            });
            ModalManager.initSettingsModal({
                onThemeChange: (theme) => {
                    ThemeManager.applyThemeChange(theme);
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
            const sheet = document.getElementById('sheet');
            const sheetHandle = document.getElementById('sheet-handle');

            if (loadingContainer) loadingContainer.style.display = 'none';
            if (logoContainer) logoContainer.classList.remove('initially-hidden');
            this.elements.filterContainer.classList.remove('initially-hidden');
            if (sheet) sheet.classList.remove('initially-hidden');
            if (sheetHandle) sheetHandle.classList.remove('initially-hidden');
            // Re-measure the top-bar clearance now the loading screen is gone and
            // the real top bar has settled (the init-time measurement was stale).
            if (typeof Sheet !== 'undefined') Sheet.measureTopOffset();

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
            const pendingUrlTags = new Set((urlParams.tags || []).filter(
                tag => !this.state.allAvailableTags.includes(tag)));

            const indicator = document.getElementById('phase2-loading-indicator');
            if (indicator) {
                indicator.classList.remove('done');
                indicator.classList.add('visible');
            }

            try {
                if (profile) FP.mark('fp:p2:fetch-start');

                // Build list of chunks not yet loaded: every day chunk in the
                // manifest plus the remainder, minus whichever one Phase 1
                // already grabbed. Fetch nearby dates first with bounded concurrency.
                const allChunks = this._dataChunks(this.state.manifest);
                const remaining = allChunks.filter(c => !this.state.loadedChunks.has(c) &&
                    !(c.startsWith('remainder') && this.state.loadedChunks.has('remainder')));
                // Publish nearby day chunks before downloading the distant tail.
                const groups = [remaining.filter(c => c.startsWith('day')),
                    remaining.filter(c => !c.startsWith('day'))].filter(g => g.length);
                let downloaded = 0;
                const totalFiles = remaining.length * 2 + new Set(remaining.map(c => this._locationChunk(c))).size;
                const load = async (url) => {
                    const data = await this._loadDataFile(url);
                    downloaded++;
                    if (indicator) indicator.querySelector('.phase2-progress').textContent =
                        `${Math.round(downloaded / totalFiles * 100)}%`;
                    return data;
                };
                for (const remainingChunks of groups) {
                    if (profile) FP.mark('fp:p2:fetch-start');
                    if (indicator) indicator.querySelector('.phase2-label').textContent =
                        'Showing available events · loading more dates';
                    const fullEventData = [], fullLocationData = [], descriptions = [];
                    const locationLoads = new Map();
                    const batches = new Map();
                    // Bounded concurrency keeps small requested-day files ahead
                    // of the tail instead of flooding the connection with it.
                    const queue = [...remainingChunks];
                    const fetchNext = async () => {
                        while (queue.length) {
                            const selected = this.state.datePickerInstance?.selectedDates?.[0];
                            const day = selected ? URLParams.formatDate(selected) : '';
                            const preferred = `day${(this.state.manifest.days || []).indexOf(day)}`;
                            const index = Math.max(0, queue.indexOf(preferred));
                            const chunk = queue.splice(index, 1)[0];
                            const locationChunk = this._locationChunk(chunk);
                            if (!locationLoads.has(locationChunk)) {
                                locationLoads.set(locationChunk, load(`${this.config.DATA_DIR}locations.${locationChunk}.json`));
                            }
                            const [events, desc] = await Promise.all([
                                load(`${this.config.DATA_DIR}events.${chunk}.json`),
                                load(`${this.config.DATA_DIR}events.${chunk}.desc.json`),
                                locationLoads.get(locationChunk)
                            ]);
                            batches.set(chunk, { events, desc });
                        }
                    };
                    await Promise.all(Array.from({ length: Math.min(4, queue.length) }, fetchNext));
                    for (const locations of await Promise.all(locationLoads.values())) fullLocationData.push(...(locations || []));
                    for (const chunk of remainingChunks) {
                        const { events, desc } = batches.get(chunk);
                        fullEventData.push(...(events || []));
                        descriptions.push(desc);
                    }
                    if (indicator) indicator.querySelector('.phase2-label').textContent = 'Preparing more events';
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

                    // Merge descriptions before the search index is (re)built below.
                    this._applyChunkDescriptions(descriptions, false);
                    remainingChunks.forEach(c => this.state.loadedChunks.add(c));

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

                    // Artwork is loaded lazily for visible icons by IconManager.
                    if (profile) {
                        FP.mark('fp:p2:emoji');
                        FP.measure('fp:p2:iconScheduling', 'fp:p2:searchIndex', 'fp:p2:emoji');
                    }

                    // Background arrivals become visible on the next interaction.
                    // Keep the current map/list stable while other dates load.
                    this._dataViewPending = true;
                    if (profile) {
                        FP.mark('fp:p2:initPanel');
                        FP.measure('fp:p2:filterList+refreshPanel', 'fp:p2:emoji', 'fp:p2:initPanel');
                    }

                    // Apply URL tags skipped in Phase 1 only when first available;
                    // never restore a selection the user has since cleared.
                    const newlyAvailable = [...pendingUrlTags].filter(tag => this.state.allAvailableTags.includes(tag));
                    if (newlyAvailable.length) {
                        FilterPanelUI.selectTags(newlyAvailable, (tag) => TagColorManager.assignColorToTag(tag));
                        newlyAvailable.forEach(tag => pendingUrlTags.delete(tag));
                    }

                    // A date change made during loading is an outstanding user
                    // request: fulfil it once, with its complete date coverage.
                    if (this._waitingForDateChunks && this._selectedDateChunksReady()) {
                        this.filterAndDisplayEvents();
                    }
                    if (profile) {
                        FP.mark('fp:p2:render');
                        FP.measure('fp:p2:filterAndDisplayEvents', 'fp:p2:initPanel', 'fp:p2:render');
                    }

                } // Each group becomes usable before loading the next one.

                if (indicator) {
                    indicator.classList.remove('visible');
                    indicator.classList.add('done');
                }

                // Everything fetched this session is now in the DataCache;
                // verify coverage and stamp the snapshot complete so the NEXT
                // session can start instantly from cache (fire-and-forget).
                if (!this.state.dataFromCache) this._markSnapshotComplete();

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

            // Open the on-device data cache and decide the session's data
            // source ONCE: a complete cached snapshot → render instantly from
            // IndexedDB (fresh data revalidates in the background afterwards);
            // otherwise → network with write-through into the cache. One atomic
            // decision so a render generation never mixes cached and fresh files.
            this._sessionHashes = new Map();
            this._cachePutPromises = [];
            PreferenceUI.init(() => this.state);
            document.addEventListener('fomo:preferences-changed', () => {
                if (!this.state.isInitialLoad) this._requestFilterUpdate();
            });
            await DataCache.init();
            this.state.dataFromCache = DataCache.isUsable();

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
                // Artwork is loaded lazily for visible icons by IconManager.
                this._setLoadingProgress(85);

                this.filterAndDisplayEvents();
                this._setLoadingProgress(100);
                this._showMainUI();

                // Mark initial load as complete
                this.state.isInitialLoad = false;

                // Initialize browser history for back/forward navigation
                HistoryManager.init(this.state.map, {
                    getQuery: () => FomoQueries.query(),
                    getQueryUrl: () => {
                        try { if (FomoQueries.active()) return FomoQueries.shareUrl(); } catch (_) { /* Large queries still work without a share link. */ }
                        const url = new URL(location.href); url.searchParams.delete('q'); url.searchParams.delete('qv'); return url.href;
                    },
                    restoreQuery: query => FomoQueries.restore(query),
                    getSelectedLocationKey: () => this.state.selectedLocationKey,
                    getTagStates: () => FilterPanelUI.getTagStates(),
                    getFormats: () => FormatSelector.selection(),
                    getNeighborhoods: () => NeighborhoodSelector.selection(),
                    setNeighborhoods: values => NeighborhoodSelector.setSelection(values),
                    canonicalTag: tag => this.state.tagRedirects[tag] || tag,
                    setFormats: values => FormatSelector.setSelection(values),
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

                // Cold cache + offline gets a clearer message than the generic
                // network error (offline WITH a cached snapshot never lands here).
                const message = (typeof navigator !== 'undefined' && navigator.onLine === false)
                    ? "You're offline and no saved events are available yet. Connect to the internet once to enable offline use."
                    : (error.message || 'Failed to load events. Please try again later.');

                // Display user-friendly error message
                if (loadingContainer) {
                    const p = loadingContainer.querySelector('p');
                    if (p) {
                        p.textContent = message;
                    }
                }

                // Also show a toast notification with the error
                ToastNotifier.showToast(
                    message,
                    'error',
                    Constants.UI.TOAST_DURATION_LONG
                );

                return; // Stop if initial load fails
            }

            // Descriptions are split out of the event payload (largest, worst-
            // compressing field) and loaded here, AFTER the markers are on the
            // map, so they never block time-to-interactive. Merge today's chunk
            // now — search + any open popup pick them up — then go to Phase 2.
            try {
                if (await this._loadChunkDescriptions(this.state.initChunks, true)) {
                    MarkerController.refreshOpenPopupContent();
                }
            } catch (e) {
                console.warn('Initial description load failed:', e);
            }

            // --- Phase 2: Asynchronously Load Full Data ---
            await this._loadFullData(urlParams);
            FomoQueries.init(this);

            // --- Offline/refresh wiring (post-critical-path) ---
            // The service worker registers only now so its shell precache
            // never competes with the loads above for bandwidth.
            this._lastRefreshCheck = Date.now();
            this._registerServiceWorker();
            if (this.state.dataFromCache) {
                // Rendered from the snapshot — revalidate against the server
                // shortly and silently merge any changes (no-op offline).
                setTimeout(() => this._backgroundRefresh(), 3000);
            }
            document.addEventListener('visibilitychange', () => this._onVisibilityRecheck());
        },

        /**
         * Start fetching the {eventId: description} companion files for the
         * given chunks. Failed fetches resolve to null (applyDescriptions
         * ignores null maps).
         * @param {string[]} chunks - chunk names, e.g. ['day1'] or ['remainder']
         * @returns {Promise<Array<Object|null>>}
         * @private
         */
        _fetchChunkDescriptions(chunks) {
            return Promise.all(chunks.map(c =>
                this._loadDataFile(`${this.config.DATA_DIR}events.${c}.desc.json`).catch(() => null)
            ));
        },

        /**
         * Merge fetched description maps into loaded events.
         * @param {Array<Object|null>} maps - results of _fetchChunkDescriptions
         * @param {boolean} reindex - re-index touched events for search (Phase 1;
         *   Phase 2 merges before its index build, so it passes false)
         * @returns {boolean} true if any loaded event was updated
         * @private
         */
        _applyChunkDescriptions(maps, reindex) {
            let changed = false;
            for (const m of maps) {
                if (DataManager.applyDescriptions(m, this.state, reindex)) changed = true;
            }
            return changed;
        },

        /**
         * Fetch and merge the {eventId: description} companion files for the
         * given chunks (descriptions are deferred off the marker-render path).
         * @param {string[]} chunks - chunk names, e.g. ['day1'] or ['remainder']
         * @param {boolean} reindex - re-index touched events for search
         * @returns {Promise<boolean>} true if any loaded event was updated
         * @private
         */
        async _loadChunkDescriptions(chunks, reindex) {
            return this._applyChunkDescriptions(await this._fetchChunkDescriptions(chunks), reindex);
        },

        // ========================================
        // OFFLINE CACHE + BACKGROUND REFRESH
        // ========================================

        /**
         * Load one data file for the current render generation: from the
         * DataCache snapshot in cache mode, from the network (with write-
         * through into the cache) otherwise. A cache miss falls back to the
         * network for that file — the background refresh reconciles shortly.
         * @param {string} url - fetch path, e.g. 'data/events.day0.json'
         * @returns {Promise<Object>} parsed JSON
         * @private
         */
        async _loadDataFile(url) {
            if (this.state.dataFromCache) {
                const entry = await DataCache.get(url);
                if (entry) return entry.data;
                console.warn(`DataCache miss for ${url}; fetching from network.`);
                return (await DataManager.fetchDataHashed(url, undefined, { cache: 'no-cache' })).data;
            }
            // A schema reset must not refill IndexedDB with stale HTTP-cached JSON.
            const { data, hash } = await DataManager.fetchDataHashed(url, undefined, { cache: 'no-cache' });
            this._sessionHashes.set(url, hash);
            this._cachePutPromises.push(DataCache.put(url, data, hash));
            return data;
        },

        // Tail partitions share one venue payload to avoid repeated transfers.
        _locationChunk(chunk) {
            return /^remainder\d+$/.test(chunk) ? 'remainder' : chunk;
        },

        _dataChunks(manifest) {
            const tail = Array.isArray(manifest?.remainderChunks)
                ? manifest.remainderChunks : [this.config.REMAINDER_CHUNK];
            return [...(manifest?.days || []).map((_, i) => `day${i}`), ...tail];
        },

        _chunksForDates(start, end = start) {
            const days = this.state.manifest?.days || [];
            const chunks = days.flatMap((day, i) => day >= start && day <= end ? [`day${i}`] : []);
            const dayCount = Math.round((Date.parse(end) - Date.parse(start)) / 86400000) + 1;
            if (chunks.length < dayCount || !days.length) {
                chunks.push(...this._dataChunks(this.state.manifest).filter(c => c.startsWith('remainder')));
            }
            return chunks;
        },

        _selectedDateChunksReady() {
            const dates = this.state.datePickerInstance?.selectedDates || [];
            if (!dates.length) return true;
            return this._chunksForDates(URLParams.formatDate(dates[0]), URLParams.formatDate(dates[1] || dates[0]))
                .every(c => this.state.loadedChunks.has(c) || (c.startsWith('remainder') && this.state.loadedChunks.has('remainder')));
        },

        /** Every file required before the loaded snapshot may be used offline. */
        _expectedSnapshotUrls() {
            const urls = [
                this.config.MANIFEST_URL,
                this.config.TAG_CONFIG_URL,
                this.config.TAG_HIERARCHY_URL,
                this.config.ORGANIZERS_URL
            ];
            const chunks = this.state.loadedChunks.has('remainder')
                ? [...(this.state.manifest.days || []).map((_, i) => `day${i}`), 'remainder']
                : this._dataChunks(this.state.manifest);
            for (const c of chunks) {
                urls.push(`${this.config.DATA_DIR}events.${c}.json`);
                urls.push(`${this.config.DATA_DIR}locations.${this._locationChunk(c)}.json`);
                urls.push(`${this.config.DATA_DIR}events.${c}.desc.json`);
            }
            return [...new Set(urls)];
        },

        /**
         * After a network-mode session has loaded everything (end of Phase 2),
         * verify the cache actually holds every expected file and stamp the
         * snapshot complete + record per-file hashes. If anything is missing
         * (e.g. a desc fetch failed), the stamp is skipped and the next
         * session simply loads from the network again — self-healing.
         * @private
         */
        async _markSnapshotComplete() {
            try {
                await Promise.all(this._cachePutPromises);
                const expected = this._expectedSnapshotUrls();
                const present = await DataCache.hasKeys(expected);
                const hashes = {};
                for (const url of expected) {
                    const hash = this._sessionHashes.get(url);
                    if (!present.has(url) || !hash) return;
                    hashes[url] = hash;
                }
                await DataCache.setMeta({
                    complete: true,
                    manifestDays: [...(this.state.manifest.days || [])],
                    savedAt: Date.now(),
                    hashes
                });
            } catch (error) {
                console.warn('Could not finalize offline snapshot:', error);
            }
        },

        /**
         * Re-fetch the full dataset and, if anything changed, rebuild the app
         * state on a detached staging object and swap it in — silently, with
         * the user's filters/search/open popup preserved. All failures are
         * swallowed (typically: offline). Runs at most once concurrently.
         * @private
         */
        async _backgroundRefresh() {
            if (this._refreshInFlight || this.state.isInitialLoad) return;
            this._refreshInFlight = true;
            this._lastRefreshCheck = Date.now();
            try {
                const fresh = await this._fetchFreshSnapshot();

                // Skip-if-identical: content hashes (not Last-Modified — the
                // pipeline re-uploads identical bytes) decide whether any
                // reprocessing/re-render happens at all.
                const meta = DataCache.getMeta();
                const cachedHashes = (meta && meta.hashes) || {};
                const freshUrls = [...fresh.files.keys()];
                const unchanged = freshUrls.length === Object.keys(cachedHashes).length &&
                    freshUrls.every(u => fresh.files.get(u).hash === cachedHashes[u]);
                if (unchanged) {
                    if (meta) DataCache.setMeta({ ...meta, savedAt: Date.now() });
                    return;
                }

                await this._applyFreshSnapshot(fresh);
                await this._persistFreshSnapshot(fresh);
            } catch (error) {
                console.warn('Background data refresh failed (will retry later):', error);
            } finally {
                this._refreshInFlight = false;
            }
        },

        /**
         * Fetch manifest + every data file of the current server generation.
         * Throws if ANY file fails — a partial snapshot is never applied.
         * @returns {Promise<{manifest: Object, chunks: string[], files: Map}>}
         * @private
         */
        async _fetchFreshSnapshot() {
            const files = new Map();
            // EVERY file bypasses the 1-hour HTTP data cache: a same-day
            // re-export changes the chunk files but NOT the manifest, so a
            // plain fetch would hash stale HTTP-cache bytes and the refresh
            // would wrongly conclude nothing changed. no-cache still sends
            // conditional requests — unchanged files cost a 304, not a body.
            const fetchOne = async (url) => {
                const result = await DataManager.fetchDataHashed(url, 30000, { cache: 'no-cache' });
                files.set(url, result);
                return result.data;
            };
            const manifest = await fetchOne(this.config.MANIFEST_URL);
            const chunks = this._dataChunks(manifest);
            const urls = [this.config.TAG_CONFIG_URL, this.config.TAG_HIERARCHY_URL, this.config.ORGANIZERS_URL];
            for (const c of chunks) {
                urls.push(`${this.config.DATA_DIR}events.${c}.json`);
                urls.push(`${this.config.DATA_DIR}locations.${this._locationChunk(c)}.json`);
                urls.push(`${this.config.DATA_DIR}events.${c}.desc.json`);
            }
            await Promise.all([...new Set(urls)].map(u => fetchOne(u)));
            return { manifest: manifest || { days: [] }, chunks, files };
        },

        /**
         * Rebuild the full app dataset from a fresh snapshot on a detached
         * staging object (reusing the standard processing pipeline — every
         * DataManager processor takes `state` as an explicit parameter), then
         * atomically swap it into the live state and re-render.
         * @param {{manifest: Object, chunks: string[], files: Map}} fresh
         * @private
         */
        async _applyFreshSnapshot(fresh) {
            const cfg = this.config;
            const get = (url) => (fresh.files.get(url) || {}).data;

            const tagConfig = get(cfg.TAG_CONFIG_URL) || {};
            const tagHierarchy = get(cfg.TAG_HIERARCHY_URL);
            const organizersById = get(cfg.ORGANIZERS_URL) || {};
            const hierarchyMaps = DataManager.buildTagHierarchyMaps(tagHierarchy || { tags: [], keywords: [] });

            const allEventData = [];
            const allLocationData = [];
            for (const c of fresh.chunks) {
                allEventData.push(...(get(`${cfg.DATA_DIR}events.${c}.json`) || []));
            }
            for (const c of new Set(fresh.chunks.map(c => this._locationChunk(c)))) {
                allLocationData.push(...(get(`${cfg.DATA_DIR}locations.${c}.json`) || []));
            }

            const staging = {
                tagConfig,
                geotagsSet: new Set((tagConfig.geotags || []).map(tag => tag.toLowerCase())),
                organizersById,
                hierarchyTagsSet: hierarchyMaps.hierarchyTagsSet,
                tagDescendantsOf: hierarchyMaps.descendantsOf,
                tagParentsOf: hierarchyMaps.parentsOf,
                tagChildrenOf: hierarchyMaps.childrenOf,
                tagEmojiMap: hierarchyMaps.tagEmojiMap,
                tagIconMap: hierarchyMaps.tagIconMap,
                tagSearchTerms: hierarchyMaps.tagSearchTerms,
                formats: hierarchyMaps.formats,
                formatOnlyTags: hierarchyMaps.formatOnlyTags,
                neighborhoodTags: new Set([...hierarchyMaps.neighborhoodTags, ...(tagConfig.geotags || []).filter(tag => hierarchyMaps.hierarchyTagsSet.has(tag))]),
                tagRedirects: hierarchyMaps.tagRedirects
            };
            // Organizer emojis render like tag emojis (mirrors _loadInitialData).
            for (const [id, org] of Object.entries(organizersById)) {
                const orgTag = Utils.makeOrganizerTag(id);
                if (orgTag && org && org.emoji) staging.tagEmojiMap[orgTag] = org.emoji;
                if (orgTag && org?.icon_id) staging.tagIconMap[orgTag] = org.icon_id;
            }

            // Empty initial pass initializes the location/event shells through
            // the same code path the live load uses; the full dataset then
            // merges with the standard chunked (main-thread-yielding) pipeline.
            DataManager.processInitialData([], [], staging, cfg);
            await DataManager.processFullDataAsync(allEventData, allLocationData, staging, cfg);
            for (const c of fresh.chunks) {
                DataManager.applyDescriptions(get(`${cfg.DATA_DIR}events.${c}.desc.json`), staging, false);
            }
            DataManager.calculateTagFrequencies(staging);
            DataManager.processTagHierarchy(staging, cfg);
            await DataManager.buildSearchIndexAsync(staging);

            this._swapRefreshedState(staging, fresh);
            this._dataViewPending = true;
        },

        /** Clear+refill an object in place (identity preserved). @private */
        _refillObject(target, source) {
            for (const key of Object.keys(target)) delete target[key];
            Object.assign(target, source);
        },

        /** Clear+refill a Set in place (identity preserved). @private */
        _refillSet(target, source) {
            target.clear();
            for (const value of source) target.add(value);
        },

        /**
         * Atomically point the live state at the staged dataset. Synchronous
         * (<1 ms) so no interaction can observe a half-swapped state.
         *
         * CRITICAL: FilterPanelUI.init / PopupContentBuilder.init /
         * TagColorManager.init captured REFERENCES to the hierarchy maps and
         * Sets — those must be refilled IN PLACE, never reassigned. Everything
         * else is read live through the shared appState reference.
         * @private
         */
        _swapRefreshedState(staging, fresh) {
            const s = this.state;
            s.formats = staging.formats;
            s.formatOnlyTags = staging.formatOnlyTags;
            s.tagRedirects = staging.tagRedirects;
            FormatSelector.configure(s.formats);
            DiscoveryRanking.migrateTagAliases(s.tagRedirects);

            // In-place refills (references captured by UI modules at init)
            this._refillObject(s.tagDescendantsOf, staging.tagDescendantsOf);
            this._refillObject(s.tagParentsOf, staging.tagParentsOf);
            this._refillObject(s.tagChildrenOf, staging.tagChildrenOf);
            this._refillObject(s.tagEmojiMap, staging.tagEmojiMap);
            this._refillObject(s.tagIconMap, staging.tagIconMap);
            this._refillObject(s.tagSearchTerms, staging.tagSearchTerms);
            this._refillSet(s.hierarchyTagsSet, staging.hierarchyTagsSet);
            this._refillSet(s.structuralFormatTags, staging.structuralFormatTags);
            this._refillSet(s.geotagsSet, staging.geotagsSet);
            this._refillSet(s.neighborhoodTags, staging.neighborhoodTags);
            NeighborhoodSelector.configure(s.tagChildrenOf, s.neighborhoodTags);

            // Straight reassignments (read live via appState)
            s.manifest = fresh.manifest;
            s.loadedChunks = new Set(fresh.chunks);
            s.tagConfig = staging.tagConfig;
            s.organizersById = staging.organizersById;
            s.allEvents = staging.allEvents;
            s.eventsById = staging.eventsById;
            s.rawLocations = staging.rawLocations;
            s._rawLocationSeen = staging._rawLocationSeen;
            s.coordOffsetByVenue = staging.coordOffsetByVenue;
            s.locationsByLatLng = staging.locationsByLatLng;
            s.tagColors = staging.tagColors;
            s.tagFrequencies = staging.tagFrequencies;
            s.allAvailableTags = staging.allAvailableTags;
            s.searchableTagsForEmptyTerm = staging.searchableTagsForEmptyTerm;
            s.searchIndex = staging.searchIndex;

            // Organizer pseudo-tag display names live in a Utils-level registry.
            Utils.registerOrganizers(s.organizersById);

            // Viewport aggregates were computed against the old dataset.
            this._viewportCache = null;
        },

        /**
         * Persist an applied fresh snapshot into the DataCache: one file per
         * transaction with yields between (the ~9 MB remainder chunk's
         * structured clone is the expensive part), then the completeness meta.
         * @private
         */
        async _persistFreshSnapshot(fresh) {
            const hashes = {};
            for (const [url, file] of fresh.files) {
                const ok = await DataCache.put(url, file.data, file.hash);
                if (!ok) return; // cache broken/full — snapshot stays incomplete
                hashes[url] = file.hash;
                await new Promise(resolve => setTimeout(resolve, 0));
            }
            await DataCache.setMeta({
                complete: true,
                manifestDays: [...(fresh.manifest.days || [])],
                savedAt: Date.now(),
                hashes
            });
        },

        /**
         * visibilitychange handler for long-lived sessions (the WebView apps
         * stay resident for days). Crossing midnight invalidates the whole
         * fixed-at-load date pipeline (config.START_DATE, chunk selection) —
         * reload outright. Otherwise revalidate data at most hourly.
         * @private
         */
        _onVisibilityRecheck() {
            if (document.visibilityState !== 'visible' || this.state.isInitialLoad) return;
            if (this.state.todayStr && Utils.getTodayInZone() !== this.state.todayStr) {
                window.location.reload();
                return;
            }
            const REFRESH_CHECK_INTERVAL_MS = 60 * 60 * 1000;
            if (Date.now() - (this._lastRefreshCheck || 0) > REFRESH_CHECK_INTERVAL_MS) {
                this._backgroundRefresh();
                if ('serviceWorker' in navigator) {
                    navigator.serviceWorker.getRegistration()
                        .then(reg => reg && reg.update())
                        .catch(() => {});
                }
            }
        },

        /**
         * Register the service worker (app-shell + map-tile offline cache).
         * Deferred to the end of init so the precache never competes with the
         * critical path. Feature-detected: iOS WKWebView exposes
         * navigator.serviceWorker only with App-Bound Domains configured.
         * @private
         */
        _registerServiceWorker() {
            if (!('serviceWorker' in navigator)) return;
            if (CITY.swEnabled === false) return;
            // Relative path → correct scope at the origin root in prod and
            // under a subpath (e.g. localhost/fomo/dist/) in local testing.
            navigator.serviceWorker.register('sw.js').catch(() => {});
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
                    FilterPanelUI.refreshTagSelector();
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
         * Read the current omni-search input value, lowercased
         * @memberof App
         * @returns {string} The current search term
         */
        _getCurrentSearchTerm() {
            return this.elements.omniSearchInput.value.toLowerCase();
        },

        /**
         * Perform search across locations, events, and tags
         * Uses SearchManager for scoring and TagFilterUI for rendering
         * @memberof App
         * @param {string} term - The search term
         */
        performSearch(term) {
            FomoQueries.invalidate();
            const FP = (typeof window !== 'undefined' && window.FilterProfiler) || null;
            const run = () => {
                const previousTerm = this.state.searchTerm;
                this.state.searchTerm = term;

                if (this._dataViewPending) {
                    this.filterAndDisplayEvents();
                    return;
                }

                if (FP) FP.mark('fp:search:start');
                // No term + debug off: renderFilters takes the ListView branch
                // and never reads the results — skip the scoring pass.
                let results = [];
                if (term || this.state.debugMode) {
                    const dynamicFrequencies = FilterPanelUI.getDynamicFrequencies();
                    const selectedTagsWithColors = TagColorManager.getSelectedTagsWithColors();
                    results = SearchManager.search(term, dynamicFrequencies, selectedTagsWithColors);
                }
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
                let key;
                if (result.type === 'location') {
                    key = result.ref;
                } else { // event
                    const event = this.state.eventsById[result.ref];
                    if (!event) return;
                    key = event.locationKey;
                }
                const ll = Utils.parseLocationKey(key);
                if (!ll) return;
                MarkerController.flyToLocationAndOpenPopup(ll.lat, ll.lng, result.type === 'event' ? result.ref : null);
            }
            // Organizer results are rendered as interactive tag chips (see
            // TagStateManager.createSearchResultButton) and toggle the organizer
            // filter directly, so they never reach this fly-to handler.
        },

        /**
         * Update the list of events filtered by date range
         * Rebuilds event lookups and tag index, then triggers display update
         * @memberof App
         */
        updateFilteredEventList({ skipDisplay = false } = {}) {
            const FP = (typeof window !== 'undefined' && window.FilterProfiler) || null;
            const run = () => {
                if (FP) FP.mark('fp:dates:start');

                const structuredEvents = FomoQueries.currentViewEvents();
                if (structuredEvents) {
                    this.state.allEventsFilteredByDate = structuredEvents;
                    this.state.allEventsFilteredByDateAndLocation = structuredEvents;
                    DataManager.groupEventsByLatLngInDateRange(this.state);
                    if (!skipDisplay) this.filterAndDisplayEvents();
                    return;
                }
                const selectedDates = this.state.datePickerInstance.selectedDates;
                if (selectedDates.length < 1) {
                    this.state.allEventsFilteredByDate = [];
                    this.state.allEventsFilteredByDateAndLocation = [];
                } else {
                    // A lone start date (mid range-pick) acts as a single-day
                    // range (start, start) so filtering applies on the first click.
                    const startDate = selectedDates[0];
                    const endDate = selectedDates.length >= 2 ? selectedDates[1] : selectedDates[0];
                    this.state.allEventsFilteredByDate = FilterManager.filterEventsByDateRange(startDate, endDate);
                    const events = this.state.allEventsFilteredByDate.filter(FormatSelector.matches)
                        .filter(event => NeighborhoodSelector.matches(event, this.state.locationsByLatLng[event.locationKey]));

                    if (FP) {
                        FP.mark('fp:dates:byRange');
                        FP.measure('fp:dates:filterByDateRange', 'fp:dates:start', 'fp:dates:byRange');
                    }

                    this.state.allEventsFilteredByDateAndLocation = events;
                }

                if (FP) FP.mark('fp:dates:filtered');

                DataManager.groupEventsByLatLngInDateRange(this.state);

                if (FP) {
                    FP.mark('fp:dates:grouped');
                    FP.measure('fp:dates:groupByLatLng', 'fp:dates:filtered', 'fp:dates:grouped');
                }

                // Index the whole date range so facet counts can include alternatives
                // outside the selected format/area. Filtering still intersects base IDs.
                DataManager.buildTagIndex(this.state, this.state.allEventsFilteredByDate);

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
         * Initialize the MapLibre GL map with tiles, controls, and event handlers
         * Sets up map layers, markers, and interactive behaviors
         * @memberof App
         */
        initMap() {
            // Determine initial view: URL params > default
            const urlParams = this.state.urlParams || {};
            let initialView, initialZoom;

            if (urlParams.lat !== undefined && urlParams.lng !== undefined) {
                // URL parameters take highest priority
                initialView = [urlParams.lat, urlParams.lng];
                initialZoom = urlParams.zoom !== undefined ? urlParams.zoom : this.config.MAP_INITIAL_ZOOM;
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
                // Brief native symbol fades keep filtering and map movement smooth.
                fadeDuration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 150
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

            // Initialize MapManager with the MapLibre map. Marker colors are
            // derived live from each emoji (TagColorManager.getColorForEmoji), so
            // there's no color map to feed in.
            MapManager.init(this.state.map);

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
            // `load` event. (Labels render locally via TinySDF from the Inter
            // webfont — there are no glyph PBF downloads to wait on — but the
            // full `load` still trails tile availability.)
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
                    // Emoji images are warmed asynchronously after both the map
                    // and Phase-1 data are ready, before the first marker render.
                    MapManager.setupMarkerInteractions();

                    // Give the sheet the map instance (popupopen/popupclose firing)
                    Sheet.setMap(map);

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

            // Handle popup open events (custom event fired by MapManager or Sheet)
            this.state.map.on('popupopen', (e) => {
                const { locationKey, popup, lngLat } = e;
                if (locationKey) {
                    this.state.selectedLocationKey = locationKey;

                    // The push below runs before the deferred fit-pan, so the
                    // history entry always stores the PRE-pan camera. On
                    // restore the map jumps back to that camera, so the
                    // fit-pan must re-run (instantly) or the popup reopens
                    // cut off. Capture the flag now — it may clear before rAF.
                    const restoring = HistoryManager.isRestoring();
                    if (!popup && Utils.isMobileLayout()) {
                        // Bottom sheet (mobile) — pan marker to visible area above the sheet
                        requestAnimationFrame(() => {
                            const { filterPanelHeight } = ViewportManager.getFilterPanelDimensions();
                            const viewportHeight = window.innerHeight;
                            const sheetHeight = viewportHeight * Sheet.SNAP_PEEK;
                            const visibleCenter = filterPanelHeight + (viewportHeight - filterPanelHeight - sheetHeight) / 2;
                            const offsetY = visibleCenter - viewportHeight / 2;

                            this.state.map.easeTo({
                                center: [lngLat.lng, lngLat.lat],
                                offset: [0, offsetY],
                                duration: restoring ? 0 : 300
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
                                this.state.map.panBy([-panOffset.panX, -panOffset.panY], { animate: !restoring, duration: 100 });
                            }
                        });
                    }

                    // Re-run search to update the UI with the selected location
                    this.performSearch(this._getCurrentSearchTerm());

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
                if (this._dataViewPending) {
                    this.filterAndDisplayEvents();
                    return;
                }
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
                        this.performSearch(this._getCurrentSearchTerm());
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
                    this.performSearch(this._getCurrentSearchTerm());

                    HistoryManager.push();
                }
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
                tagDescendantsOf: this.state.tagDescendantsOf,
                tagParentsOf: this.state.tagParentsOf,
                tagChildrenOf: this.state.tagChildrenOf,
                structuralFormatTags: this.state.structuralFormatTags,
                neighborhoodTags: this.state.neighborhoodTags,
                tagEmojiMap: this.state.tagEmojiMap,
                initialGlobalFrequencies: this.state.tagFrequencies,
                resultsContainerDOM: this.elements.resultsContainer,
                onFilterChangeCallback: () => {
                    this._requestFilterUpdate();
                    HistoryManager.push();
                },
                onSearchResultClick: (result) => this.handleSearchResultClick(result),
                performSearch: (term) => this.performSearch(term),
                getSearchTerm: () => this._getCurrentSearchTerm(),
                getVisibleTagFrequencies: () => this.state.visibleTagFrequencies,
                getEventFilterTags: event => Utils.eventFilterTags(event, this.state.locationsByLatLng[event.locationKey]),
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

            ListView.init({
                // Only events within the current map window (re-filtered on every
                // pan via updateVisibleItems), sorted by distance + capped in render.
                getMatchingEvents: () => this.state.currentlyVisibleMatchingEvents,
                getLocationInfo: (key) => this.state.locationsByLatLng[key],
                getLocationDistances: () => this.state.locationDistances,
                getVisibleCenter: () => this.state.visibleCenter || ViewportManager.getVisibleCenter(),
                getContainer: () => document.getElementById('results-container')
            });

            // The sheet hosting the list view / search results. Whenever its
            // browse content newly becomes visible (open / snap up / detail
            // dismissed), re-render the panel so the (otherwise skipped) list
            // view populates.
            if (typeof Sheet !== 'undefined') {
                Sheet.init({
                    onToggle: (open) => {
                        if (open) FilterPanelUI.rerender();
                        setTimeout(() => MapManager.refreshPromotedMarkers(), 300);
                    }
                });
            }
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
        _requestFilterUpdate(datesChanged = false) {
            FomoQueries.invalidate();
            this._pendingDateUpdate = this._pendingDateUpdate || datesChanged;
            if (this._filterUpdateQueued) return;
            this._filterUpdateQueued = true;
            const status = document.getElementById('filter-update-status');
            if (status) status.hidden = false;
            // Allow the selected control and status to paint first. Read the
            // latest state when this runs, not a snapshot of the first click.
            requestAnimationFrame(() => setTimeout(() => {
                this._filterUpdateQueued = false;
                const updateDates = this._pendingDateUpdate;
                this._pendingDateUpdate = false;
                try {
                    if (updateDates) this.updateFilteredEventList();
                    else this.filterAndDisplayEvents();
                } finally {
                    if (status) status.hidden = true;
                }
            }, 0));
        },

        filterAndDisplayEvents(options = {}) {
            if (!this._selectedDateChunksReady()) {
                this._waitingForDateChunks = true;
                return;
            }
            this._waitingForDateChunks = false;
            if (this._dataViewPending) {
                this._dataViewPending = false;
                this.updateFilteredEventList({ skipDisplay: true });
                FilterPanelUI.refreshAvailableTags({
                    allAvailableTags: this.state.allAvailableTags,
                    initialGlobalFrequencies: this.state.tagFrequencies
                });
            }
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

            // Facet counts use dates + topics + the other selector, across the
            // whole map. Deduplication and ancestor counts live in each selector.
            const tagMatches = FilterManager.filterEventsByTags(
                currentTagStates, this.state.allEventsFilteredByDate || []);
            const areaMatches = tagMatches.filter(event =>
                NeighborhoodSelector.matches(event, this.state.locationsByLatLng[event.locationKey]));
            const formatMatches = tagMatches.filter(FormatSelector.matches);
            const selectorEvents = (this.state.allEventsFilteredByDate || []).filter(event =>
                FormatSelector.matches(event) && NeighborhoodSelector.matches(event, this.state.locationsByLatLng[event.locationKey]));
            TagSelector.updateCounts(selectorEvents, this.state.locationsByLatLng);
            VenueSelector.updateCounts(selectorEvents, this.state.locationsByLatLng);
            FormatSelector.updateCounts(areaMatches);
            NeighborhoodSelector.updateCounts(formatMatches, this.state.locationsByLatLng);
            const allMatchingEventsFlatList = FomoQueries.currentViewEvents() ?? areaMatches.filter(FormatSelector.matches);

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
                const { selectedTags } = Utils.partitionTagStates(FilterPanelUI.getTagStates());

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

                params.formats = FormatSelector.selection();
                params.neighborhoods = NeighborhoodSelector.selection();

                // Generate the shareable URL using URLParams module
                const shareUrl = FomoQueries.shareUrl() || URLParams.generateShareUrl(params);

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
