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
         * @property {L.Map|null} map - Leaflet map instance
         * @property {L.TileLayer|null} tileLayer - Map tile layer
         * @property {L.LayerGroup|null} markersLayer - Layer containing all markers
         * @property {L.LayerGroup|null} debugLayer - Layer for debug visualization
         * @property {boolean} debugMode - Debug mode toggle state
         * @property {L.LatLng|null} visibleCenter - Visible center accounting for filter panel
         * @property {Object|null} debugRectBounds - Debug rectangle bounds for popup positioning
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
            tileLayer: null,
            markersLayer: null,
            debugLayer: null,
            debugMode: false,
            visibleCenter: null,
            debugRectBounds: null,
            locationDistances: {}, // Map of locationKey -> distance from center
            allEvents: [],
            eventsById: {},
            tagConfig: {},
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
            isInitialLoad: true, // Track if we're in initial load phase
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
         * @property {number} ONE_DAY_IN_MS - Milliseconds in one day
         * @property {Array<string>} TAG_COLOR_PALETTE_DARK - Color palette for dark theme
         * @property {Array<string>} TAG_COLOR_PALETTE_LIGHT - Color palette for light theme
         * @property {Array<number>} MAP_INITIAL_VIEW - Initial map center [lat, lng]
         * @property {number} MAP_INITIAL_ZOOM - Initial map zoom level
         * @property {string} MAP_TILE_URL_DARK - Tile URL for dark theme map
         * @property {string} MAP_TILE_URL_LIGHT - Tile URL for light theme map
         * @property {string} MAP_ATTRIBUTION - Map attribution text
         * @property {number} MAP_MAX_ZOOM - Maximum zoom level
         * @property {number} MARKER_DISPLAY_LIMIT - Maximum markers to display
         */
        config: {
            EVENT_INIT_URL: 'data/events.init.json',
            LOCATIONS_INIT_URL: 'data/locations.init.json',
            EVENT_FULL_URL: 'data/events.full.json',
            LOCATIONS_FULL_URL: 'data/locations.full.json',
            TAG_CONFIG_URL: 'data/tags.json',

            START_DATE: new Date(2025, 7, 1),
            END_DATE: new Date(2026, 0, 31),
            ONE_DAY_IN_MS: 24 * 60 * 60 * 1000,
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
            MAP_INITIAL_VIEW: [40.71799, -73.98712],
            MAP_INITIAL_ZOOM: 14,
            MAP_TILE_URL_DARK: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
            MAP_TILE_URL_LIGHT: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager_labels_under/{z}/{x}/{y}{r}.png',
            MAP_ATTRIBUTION: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>',
            MAP_MAX_ZOOM: 20,
            MARKER_DISPLAY_LIMIT: 1000
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
         * @property {HTMLElement} selectedTagsDisplay - Display for selected tags
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
            selectedTagsDisplay: document.getElementById('selected-tags-display'),
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
            const [initEventData, initLocationData, tagConfig] = await Promise.all([
                DataManager.fetchData(this.config.EVENT_INIT_URL),
                DataManager.fetchData(this.config.LOCATIONS_INIT_URL),
                DataManager.fetchData(this.config.TAG_CONFIG_URL)
            ]);

            this.state.tagConfig = tagConfig;
            this.state.geotagsSet = new Set((tagConfig.geotags || []).map(tag => tag.toLowerCase()));

            // Initialize TagColorManager with color palettes
            TagColorManager.init({
                darkPalette: this.config.TAG_COLOR_PALETTE_DARK,
                lightPalette: this.config.TAG_COLOR_PALETTE_LIGHT
            });

            DataManager.processInitialData(initEventData, initLocationData, this.state, this.config);
            DataManager.calculateTagFrequencies(this.state);
            DataManager.processTagHierarchy(this.state, this.config);
            DataManager.buildTagIndex(this.state);
        },

        /**
         * Initialize all core modules (emoji, theme, map, viewport, etc.)
         * @memberof App
         * @private
         */
        _initializeModules() {
            // Initialize emoji font and theme before map
            this.initEmojiManager();
            EmojiManager.initEmojiFont();
            this.initThemeManager();
            ThemeManager.initTheme();

            this.initMap();
            this.initViewportManager();
            this.initMarkerController();
            this.initTagFilterUI();
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
                TagFilterUI.selectTags(urlParams.tags, (tag) => TagColorManager.assignColorToTag(tag));
                this.updateSelectedTagsDisplay();
            }

            UIManager.initDatePicker(this.elements, this.config, this.state, {
                onDatePickerClose: (selectedDates) => {
                    const [newStart, newEnd] = selectedDates;
                    const [oldStart, oldEnd] = this.state.lastSelectedDates;

                    if (oldStart && oldEnd && newStart.getTime() === oldStart.getTime() && newEnd.getTime() === oldEnd.getTime()) {
                        return;
                    }

                    this.state.lastSelectedDates = selectedDates;
                    this.updateFilteredEventList();
                }
            });
            this.initOmniSearch();
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
                }
            });
            ModalManager.initWelcomeModal();
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
            this.elements.expandFilterPanelButton.classList.remove('initially-hidden');

            // Set up toggle tags button for mobile
            this.elements.expandFilterPanelButton.addEventListener('click', () => {
                this.elements.filterPanel.classList.toggle('tags-collapsed');
                this.elements.expandFilterPanelButton.classList.toggle('collapsed');
            });
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
            try {
                const [fullEventData, fullLocationData] = await Promise.all([
                    DataManager.fetchData(this.config.EVENT_FULL_URL),
                    DataManager.fetchData(this.config.LOCATIONS_FULL_URL)
                ]);

                // Merge and process the full dataset
                DataManager.processFullData(fullEventData, fullLocationData, this.state, this.config);
                DataManager.calculateTagFrequencies(this.state);
                DataManager.processTagHierarchy(this.state, this.config);

                this.updateFilteredEventList(); // This will re-filter by date/location and rebuild tag index
                this.initTagFilterUI();

                // Re-apply URL parameter tag selections after re-initializing tag filter UI
                // This preserves the tags selected from URL parameters during Phase 2 full data load
                if (urlParams.tags && urlParams.tags.length > 0) {
                    TagFilterUI.selectTags(urlParams.tags, (tag) => TagColorManager.assignColorToTag(tag));
                    this.updateSelectedTagsDisplay();
                }

                // Re-render with the full dataset, applying current filters.
                this.filterAndDisplayEvents();

            } catch (error) {
                console.error("Failed to load full dataset:", error);

                // Show toast notification for full dataset loading errors
                // (Less critical than initial load failure, so we don't update the loading container)
                ToastNotifier.showToast(
                    `Could not load complete dataset: ${error.message || 'Unknown error'}`,
                    'error',
                    Constants.UI.TOAST_DURATION_MEDIUM
                );
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

            // Show welcome modal for first-time visitors
            ModalManager.showWelcomeModalIfFirstVisit();

            // --- Phase 1: Load Initial Data ---
            try {
                await this._loadInitialData();
                this._initializeModules();
                this._setupUIComponents(urlParams);
                this.filterAndDisplayEvents();
                this._showMainUI();

                // Mark initial load as complete
                this.state.isInitialLoad = false;
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
                    this.updateSelectedTagsDisplay();
                }
            });
        },

        /**
         * Initialize the omni search functionality
         * Sets up debounced search, special term handling, and auto-expand on mobile
         * @memberof App
         */
        initOmniSearch() {
            // Debounce search to improve performance (executes after user stops typing)
            const debouncedSearch = Utils.debounce((searchTerm) => {
                this.performSearch(searchTerm);
            }, Constants.TIME.SEARCH_DEBOUNCE_MS);

            this.elements.omniSearchInput.addEventListener('input', (e) => {
                const searchTerm = e.target.value.toLowerCase();

                // Handle special terms immediately (no debounce)
                this.handleSpecialSearchTerms(searchTerm);

                // Debounce regular search
                debouncedSearch(searchTerm);

                // Auto-expand panel on mobile when user enters search term
                if (searchTerm && window.innerWidth <= Constants.UI.MOBILE_BREAKPOINT) {
                    this.elements.filterPanel.classList.remove('tags-collapsed');
                    this.elements.expandFilterPanelButton.classList.remove('collapsed');
                }
            });

            this.elements.omniSearchInput.addEventListener('focus', (e) => {
                const searchTerm = e.target.value.toLowerCase();
                if (searchTerm) {
                    this.performSearch(searchTerm);
                }
            });

            document.addEventListener('click', (e) => {
                // This could be used to hide results, but with integrated display it's not needed.
            });
        },

        /**
         * Handle special search terms (Easter eggs)
         * - "debug": Toggle debug mode visualization
         * - "noto": Enable Noto Color Emoji font
         * @memberof App
         * @param {string} term - The search term to check
         */
        handleSpecialSearchTerms(term) {
            // Toggle debug mode if search term is exactly "debug"
            if (term === 'debug') {
                this.state.debugMode = !this.state.debugMode;
                console.log('Debug Mode:', this.state.debugMode ? 'ENABLED' : 'DISABLED');
                this.updateDebugOverlay();
            }
            // Toggle Noto emoji font if search term is exactly "noto"
            else if (term === 'noto') {
                if (!EmojiManager.isNotoFontActive()) {
                    EmojiManager.updateToNotoFont();
                }
            }
        },

        /**
         * Get display name for an item (location, event, or tag)
         * Delegates to Utils.getDisplayName for consistent naming
         * @memberof App
         * @param {Object} item - The item to get a display name for
         * @returns {string} The display name
         */
        getDisplayName(item) {
            // Delegate to Utils.getDisplayName
            return Utils.getDisplayName(item);
        },

        /**
         * Perform search across locations, events, and tags
         * Uses SearchManager for scoring and TagFilterUI for rendering
         * @memberof App
         * @param {string} term - The search term
         */
        performSearch(term) {
            // Use SearchManager to perform the search
            const dynamicFrequencies = TagFilterUI.getDynamicFrequencies();
            const selectedTagsWithColors = TagColorManager.getSelectedTagsWithColors();
            const results = SearchManager.search(term, dynamicFrequencies, selectedTagsWithColors);

            // Render results using TagFilterUI
            TagFilterUI.render(results, term);
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
                this.flyToLocationAndOpenPopup(lat, lng, result.type === 'event' ? result.ref : null);
            }

        },

        /**
         * Fly to a location on the map and open its popup
         * Creates a temporary marker if one doesn't exist
         * @memberof App
         * @param {number} lat - Latitude
         * @param {number} lng - Longitude
         * @param {string|null} [eventIdToForce=null] - Event ID to force display in popup
         */
        flyToLocationAndOpenPopup(lat, lng, eventIdToForce = null) {
            this.state.forceDisplayEventId = eventIdToForce;

            // Find or create the marker first, then open its popup
            // The popup opening will trigger the automatic pan to make it visible
            let markerFound = false;
            this.state.markersLayer.eachLayer(marker => {
                const markerLatLng = marker.getLatLng();
                if (markerLatLng.lat === lat && markerLatLng.lng === lng) {
                    marker.openPopup();
                    markerFound = true;
                }
            });

            if (!markerFound) {
                // If no marker was found (e.g., it was filtered out), create it temporarily.
                const locationKey = `${lat},${lng}`;
                const locationInfo = this.state.locationsByLatLng[locationKey];
                if (!locationInfo) {
                    console.error("No location info found for", locationKey);
                    return;
                }

                const customIcon = MapManager.createMarkerIcon(locationInfo);
                const popupContentCallback = MarkerController.createPopupContentCallback(locationKey);
                const newMarker = MapManager.addMarkerToMap([lat, lng], customIcon, locationInfo.name, popupContentCallback);
                if (newMarker) {
                    newMarker.openPopup();
                }
            }
        },

        /**
         * Update the list of events filtered by date range and location tags
         * Rebuilds event lookups and tag index, then triggers display update
         * @memberof App
         */
        updateFilteredEventList() {
            const selectedDates = this.state.datePickerInstance.selectedDates;
            if (selectedDates.length < 2) {
                this.state.allEventsFilteredByDateAndLocation = [];
            } else {
                const [startDate, endDate] = selectedDates;
                let events = FilterManager.filterEventsByDateRange(startDate, endDate);

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
            this.updateEventsByLatLngInDateRange();
            DataManager.buildTagIndex(this.state, this.state.allEventsFilteredByDateAndLocation);
            this.filterAndDisplayEvents();
        },

        /**
         * Update the events grouped by location for the current date range
         * Rebuilds the eventsByLatLngInDateRange lookup from filtered events
         * @memberof App
         */
        updateEventsByLatLngInDateRange() {
            this.state.eventsByLatLngInDateRange = {}; // Reset first
            this.state.allEventsFilteredByDateAndLocation.forEach(event => {
                if (event.locationKey) {
                    if (!this.state.eventsByLatLngInDateRange[event.locationKey]) {
                        this.state.eventsByLatLngInDateRange[event.locationKey] = [];
                    }
                    this.state.eventsByLatLngInDateRange[event.locationKey].push(event);
                }
            });
        },

        /**
         * Initialize the Leaflet map with tiles, controls, and event handlers
         * Sets up map layers, markers, and interactive behaviors
         * @memberof App
         */
        initMap() {
            // Use URL parameters for initial map view if provided
            const urlParams = this.state.urlParams || {};
            const initialView = (urlParams.lat !== undefined && urlParams.lng !== undefined)
                ? [urlParams.lat, urlParams.lng]
                : this.config.MAP_INITIAL_VIEW;
            const initialZoom = urlParams.zoom !== undefined
                ? urlParams.zoom
                : this.config.MAP_INITIAL_ZOOM;

            this.state.map = L.map('map', {
                zoomControl: false,
                inertia: true,
                inertiaDeceleration: 30000,
            })
                .setView(initialView, initialZoom);

            L.control.zoom({ position: 'topright' }).addTo(this.state.map);

            // Get tile URL for current theme
            const tileUrl = ThemeManager.getTileUrlForCurrentTheme();

            this.state.tileLayer = L.tileLayer(tileUrl, {
                attribution: this.config.MAP_ATTRIBUTION,
                maxZoom: this.config.MAP_MAX_ZOOM,
                updateWhenIdle: true,
                keepBuffer: 12
            }).addTo(this.state.map);

            const { markersLayer } = MapManager.init(this.state.map, {}, this.state.tagConfig.bgcolors);
            this.state.markersLayer = markersLayer;

            // Initialize debug layer
            this.state.debugLayer = L.layerGroup().addTo(this.state.map);

            // Adjust the initial view so the visible center (accounting for filter panel)
            // ends up at the desired initial view coordinates (from URL params or default)
            const desiredVisibleCenter = L.latLng(initialView);
            ViewportManager.adjustMapToVisibleCenter(this.state.map, desiredVisibleCenter, false);

            this.state.map.on('popupopen', (e) => {
                const marker = e.popup._source;
                if (marker) {
                    const latLng = marker.getLatLng();
                    const locationKey = `${latLng.lat},${latLng.lng}`;

                    this.state.selectedLocationKey = locationKey;

                    // Pan to ensure popup fits within the visible area (90% debug rectangle)
                    // Wait for popup to render so we can measure its actual height
                    setTimeout(() => {
                        const popup = e.popup;
                        const popupElement = popup.getElement();
                        const debugRectBounds = ViewportManager.getDebugRectBounds();
                        if (!popupElement || !debugRectBounds) return;

                        const popupHeight = popupElement.offsetHeight;
                        const popupWidth = popupElement.offsetWidth;

                        // Get current popup position in container point coordinates
                        const popupPoint = this.state.map.latLngToContainerPoint(latLng);
                        const popupTop = popupPoint.y - popupHeight;
                        const popupBottom = popupPoint.y;
                        const popupLeft = popupPoint.x - popupWidth / 2;
                        const popupRight = popupPoint.x + popupWidth / 2;

                        // Calculate if we need to pan (vertical and horizontal)
                        let panX = 0;
                        let panY = 0;

                        // Check vertical bounds
                        if (popupTop < debugRectBounds.top) {
                            panY = debugRectBounds.top - popupTop;
                        } else if (popupBottom > debugRectBounds.bottom) {
                            panY = debugRectBounds.bottom - popupBottom;
                        }

                        // Check horizontal bounds
                        if (popupLeft < debugRectBounds.left) {
                            panX = debugRectBounds.left - popupLeft;
                        } else if (popupRight > debugRectBounds.right) {
                            panX = debugRectBounds.right - popupRight;
                        }

                        if (panX !== 0 || panY !== 0) {
                            // Use panBy for relative adjustment instead of panTo
                            this.state.map.panBy([-panX, -panY], { animate: true, duration: 0.2 });
                        }
                    }, 50);

                    // Re-run search to update the UI with the selected location
                    const currentTerm = this.elements.omniSearchInput.value.toLowerCase();
                    this.performSearch(currentTerm);
                }
            });

            this.state.map.on('moveend', () => {
                this.updateVisibleItems();
                // Re-run the search to update scores based on map visibility, even if the search term is empty.
                const currentTerm = this.elements.omniSearchInput.value.toLowerCase();
                this.performSearch(currentTerm);
                // Update debug overlay if debug mode is enabled
                this.updateDebugOverlay();
            });

            this.state.map.on('popupclose', (e) => {
                const closedPopup = e.popup;
                const marker = closedPopup._source;
                if (!marker) return;

                const locationKey = `${marker.getLatLng().lat},${marker.getLatLng().lng}`;

                if (this.state.selectedLocationKey === locationKey) {
                    this.state.selectedLocationKey = null;
                    // Re-run search to update the UI and remove the selected location
                    const currentTerm = this.elements.omniSearchInput.value.toLowerCase();
                    this.performSearch(currentTerm);
                }

                // Remove marker if no matching events at this location
                if (!MarkerController.hasMatchingEvents(locationKey)) {
                    MapManager.removeMarker(marker);
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
            // Initialize MarkerController
            MarkerController.init({
                appState: this.state,
                config: this.config,
                getTagStates: () => TagFilterUI.getTagStates(),
                getSelectedDates: () => this.state.datePickerInstance.selectedDates,
                getForceDisplayEventId: () => this.state.forceDisplayEventId,
                setForceDisplayEventId: (id) => { this.state.forceDisplayEventId = id; }
            });
        },

        /**
         * Initialize tag filtering and search UI
         * Sets up SearchManager, FilterManager, and TagFilterUI with callbacks
         * @memberof App
         */
        initTagFilterUI() {
            // Initialize SearchManager
            SearchManager.init({
                appState: this.state
            });

            // Initialize FilterManager
            FilterManager.init({
                appState: this.state,
                config: this.config
            });

            TagFilterUI.init({
                allAvailableTags: this.state.allAvailableTags,
                tagConfigBgColors: this.state.tagConfig.bgcolors,
                initialGlobalFrequencies: this.state.tagFrequencies,
                resultsContainerDOM: this.elements.resultsContainer,
                onFilterChangeCallback: () => {
                    this.updateSelectedTagsDisplay();
                    this.filterAndDisplayEvents();
                },
                onSearchResultClick: (result) => this.handleSearchResultClick(result),
                defaultMarkerColor: this.config.DEFAULT_MARKER_COLOR_DARK,
                performSearch: (term) => this.performSearch(term),
                getSearchTerm: () => this.elements.omniSearchInput.value.toLowerCase(),
                getTagColor: (tag) => TagColorManager.getTagColor(tag),
                assignColorToTag: (tag) => TagColorManager.assignColorToTag(tag),
                unassignColorFromTag: (tag) => TagColorManager.unassignColorFromTag(tag),
            });
            TagFilterUI.setAppProviders({ getSelectedLocationKey: () => this.state.selectedLocationKey });
            TagFilterUI.render([]); // Render with empty results initially
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

            // Find any open popup
            const openPopupInfo = MarkerController.findOpenPopup(this.state.map);
            const openPopup = openPopupInfo?.popup;
            const openMarker = openPopupInfo?.marker;

            const selectedDates = this.state.datePickerInstance.selectedDates;
            if (selectedDates.length < 2) {
                return;
            }

            const currentTagStates = TagFilterUI.getTagStates();

            // Use FilterManager to filter events by tags
            const allMatchingEventsFlatList = FilterManager.filterEventsByTags(
                currentTagStates,
                this.state.allEventsFilteredByDateAndLocation
            );

            // Store the computed lists in the state for use by other functions like search
            this.state.currentlyMatchingEvents = allMatchingEventsFlatList;

            // Group events by location
            const filteredLocations = FilterManager.groupEventsByLocation(allMatchingEventsFlatList);
            this.state.currentlyMatchingLocationKeys = new Set(Object.keys(filteredLocations));

            // After updating all matching items, update the visible subset as well.
            this.updateVisibleItems();

            // Update open popup content if there is one
            if (openPopup) {
                MarkerController.updateOpenPopupContent(openPopup);
            }

            // Display markers on map
            MarkerController.displayEventsOnMap(filteredLocations, openMarker);
            TagFilterUI.updateView(allMatchingEventsFlatList);
        },

        /**
         * Update the visible items based on current map viewport
         * Calculates viewport bounds, distances, and filters events by visibility
         * @memberof App
         */
        updateVisibleItems() {
            if (!this.state.map) return;

            // Use ViewportManager to calculate viewport bounds and distances
            const viewportData = ViewportManager.updateViewportCalculations(
                this.state.map,
                this.state.locationsByLatLng,
                this.state.isInitialLoad
            );

            if (!viewportData) return;

            // Update state with calculated values
            this.state.visibleCenter = viewportData.visibleCenter;
            this.state.debugRectBounds = viewportData.debugRectBounds;
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
         * Update the display of selected tags with interactive buttons
         * Shows/hides the selected tags display area based on selection state
         * @memberof App
         */
        updateSelectedTagsDisplay() {
            if (!this.elements.selectedTagsDisplay) return;

            // Get selected tags from TagColorManager
            const selectedTags = TagColorManager.getSelectedTags();

            if (selectedTags.length === 0) {
                this.elements.selectedTagsDisplay.innerHTML = '';
                this.elements.selectedTagsDisplay.style.display = 'none';
                return;
            }

            this.elements.selectedTagsDisplay.style.display = 'flex';
            this.elements.selectedTagsDisplay.innerHTML = '';

            selectedTags.forEach(tag => {
                const tagButton = TagFilterUI.createInteractiveTagButton(tag);
                this.elements.selectedTagsDisplay.appendChild(tagButton);
            });
        },

        /**
         * Update debug visualization overlay
         * Shows viewport bounds rectangle and visible center marker
         * @memberof App
         */
        updateDebugOverlay() {
            // Clear existing debug overlays
            if (this.state.debugLayer) {
                this.state.debugLayer.clearLayers();
            }

            if (!this.state.debugMode || !this.state.debugRectBounds || !this.state.visibleCenter) {
                return;
            }

            // Convert container point coordinates to lat/lng for the rectangle
            const topLeft = this.state.map.containerPointToLatLng(
                L.point(this.state.debugRectBounds.left, this.state.debugRectBounds.top)
            );
            const bottomRight = this.state.map.containerPointToLatLng(
                L.point(this.state.debugRectBounds.right, this.state.debugRectBounds.bottom)
            );

            // Draw the 90% inset bounds rectangle
            L.rectangle(
                [topLeft, bottomRight],
                {
                    color: '#ff0000',
                    weight: 2,
                    fill: false,
                    dashArray: '5, 5'
                }
            ).addTo(this.state.debugLayer);

            // Draw a marker at the visible center
            L.circleMarker(this.state.visibleCenter, {
                color: '#00ff00',
                fillColor: '#00ff00',
                fillOpacity: 0.8,
                radius: 8
            }).addTo(this.state.debugLayer);

            // Add a crosshair at the center
            const crosshairSize = 20; // pixels
            const centerPoint = this.state.map.latLngToContainerPoint(this.state.visibleCenter);

            const crosshairH1 = this.state.map.containerPointToLatLng(
                L.point(centerPoint.x - crosshairSize, centerPoint.y)
            );
            const crosshairH2 = this.state.map.containerPointToLatLng(
                L.point(centerPoint.x + crosshairSize, centerPoint.y)
            );
            const crosshairV1 = this.state.map.containerPointToLatLng(
                L.point(centerPoint.x, centerPoint.y - crosshairSize)
            );
            const crosshairV2 = this.state.map.containerPointToLatLng(
                L.point(centerPoint.x, centerPoint.y + crosshairSize)
            );

            L.polyline([crosshairH1, crosshairH2], {
                color: '#00ff00',
                weight: 2
            }).addTo(this.state.debugLayer);

            L.polyline([crosshairV1, crosshairV2], {
                color: '#00ff00',
                weight: 2
            }).addTo(this.state.debugLayer);
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
                const tagStates = TagFilterUI.getTagStates();
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

                // Generate the shareable URL
                const baseUrl = window.location.origin + window.location.pathname;
                const urlParams = new URLSearchParams();

                urlParams.set('lat', params.lat.toFixed(5));
                urlParams.set('lng', params.lng.toFixed(5));
                urlParams.set('zoom', params.zoom.toString());

                if (params.start && params.end) {
                    urlParams.set('start', URLParams.formatDate(params.start));
                    urlParams.set('end', URLParams.formatDate(params.end));
                }

                if (params.tags && params.tags.length > 0) {
                    urlParams.set('tags', params.tags.join(','));
                }

                const shareUrl = `${baseUrl}?${urlParams.toString()}`;

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