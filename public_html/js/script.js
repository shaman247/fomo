document.addEventListener('DOMContentLoaded', () => {
    const App = {
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
            selectedTagsWithColors: [], // Array of [tag, color] pairs
            isInitialLoad: true, // Track if we're in initial load phase
        },

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

        elements: {
            resultsContainer: document.getElementById('results-container'),
            datePicker: document.getElementById('date-picker'),
            datePickerSizer: document.getElementById('date-picker-sizer'),
            dateFilterContainer: document.getElementById('date-filter-container'),
            filterContainer: document.getElementById('filter-container'),
            omniSearchFilter: document.getElementById('omni-search-filter'),
            toggleTagsBtn: document.getElementById('toggle-tags-btn'),
            filterPanel: document.getElementById('filter-panel'),
            omniSearchInput: document.getElementById('omni-search-input'),
            selectedTagsDisplay: document.getElementById('selected-tags-display'),
        },

        async init() {
            const loadingContainer = document.getElementById('loading-container');
            const tagsWrapper = document.getElementById('tags-wrapper');

            // Parse URL parameters
            const urlParams = URLParams.parse();
            this.state.urlParams = urlParams;

            // Clean up URL parameters from address bar after parsing
            // This prevents confusion when users interact with the map and change the view
            if (Object.keys(urlParams).length > 0) {
                const cleanUrl = window.location.origin + window.location.pathname;
                window.history.replaceState({}, '', cleanUrl);
            }

            // Show welcome modal for first-time visitors
            UIManager.showWelcomeModalIfFirstVisit();

            // --- Phase 1: Load Initial Data ---
            try { 
                const [initEventData, initLocationData, tagConfig] = await Promise.all([
                    DataManager.fetchData(this.config.EVENT_INIT_URL),
                    DataManager.fetchData(this.config.LOCATIONS_INIT_URL),
                    DataManager.fetchData(this.config.TAG_CONFIG_URL)
                ]);

                this.state.tagConfig = tagConfig;
                this.state.geotagsSet = new Set((tagConfig.geotags || []).map(tag => tag.toLowerCase()));
                DataManager.processInitialData(initEventData, initLocationData, this.state, this.config);
                DataManager.calculateTagFrequencies(this.state);
                DataManager.processTagHierarchy(this.state, this.config);
                DataManager.buildTagIndex(this.state);

                // Initialize theme before map to ensure correct tiles are loaded
                this.initEmojiFont();

                this.initMap();
                this.initTagFilterUI();

                // Apply URL parameter tag selections before date picker init
                // This ensures tags are selected when the date picker triggers initial filtering
                if (urlParams.tags && urlParams.tags.length > 0) {
                    TagFilterUI.selectTags(urlParams.tags, (tag) => this.assignColorToTag(tag));
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
                UIManager.initEventListeners(this.elements, {
                    onToggleCollapse: () => {
                        const currentTerm = this.elements.omniSearchInput.value.toLowerCase();
                        this.performSearch(currentTerm);
                    }
                });
                UIManager.initLogoMenu({
                    onShareView: () => this.shareCurrentView()
                });
                UIManager.initSettingsModal({
                    onEmojiFontChange: (emojiFont) => {
                        const statusElement = document.getElementById('emoji-font-status');
                        this.applyEmojiFont(emojiFont, statusElement);
                    },
                    onThemeChange: (theme) => {
                        this.setTheme(theme, null, null);

                        // Update map tiles based on theme
                        if (this.state.tileLayer) {
                            const tileUrl = theme === 'dark'
                                ? this.config.MAP_TILE_URL_DARK
                                : this.config.MAP_TILE_URL_LIGHT;
                            this.state.tileLayer.setUrl(tileUrl);
                        }

                        // Reassign colors for selected tags with new theme palette
                        this.reassignTagColors();
                        this.updateSelectedTagsDisplay();
                    }
                });
                UIManager.initWelcomeModal();

                this.filterAndDisplayEvents();

                // Hide loading message and show main content
                const logoContainer = document.getElementById('logo-container');
                if (loadingContainer) loadingContainer.style.display = 'none';
                if (logoContainer) logoContainer.classList.remove('initially-hidden');
                this.elements.filterContainer.classList.remove('initially-hidden');
                tagsWrapper.classList.remove('initially-hidden');
                this.elements.toggleTagsBtn.classList.remove('initially-hidden');

                // Set up toggle tags button for mobile
                this.elements.toggleTagsBtn.addEventListener('click', () => {
                    this.elements.filterPanel.classList.toggle('tags-collapsed');
                    this.elements.toggleTagsBtn.classList.toggle('collapsed');
                });

                // Mark initial load as complete
                this.state.isInitialLoad = false;
            } catch (error) {
                console.error("Failed to initialize app with initial data:", error);
                if (loadingContainer) {
                    const p = loadingContainer.querySelector('p');
                    if (p) p.textContent = 'Failed to load events. Please try again later.';
                }
                return; // Stop if initial load fails
            }

            // --- Phase 2: Asynchronously Load Full Data ---
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
                    TagFilterUI.selectTags(urlParams.tags, (tag) => this.assignColorToTag(tag));
                    this.updateSelectedTagsDisplay();
                }

                // Re-render with the full dataset, applying current filters.
                this.filterAndDisplayEvents();

            } catch (error) {
                console.error("Failed to load full dataset:", error);
                if (loadingContainer) {
                    const p = loadingContainer.querySelector('p');
                    if (p) p.textContent = 'Failed to load events. Please try again later.';
                }
            }
        },

        setTheme(theme, moonIcon, sunIcon) {
            const root = document.documentElement;
            root.setAttribute('data-theme', theme);

            if (moonIcon && sunIcon) {
                if (theme === 'light') {
                    moonIcon.style.display = 'none';
                    sunIcon.style.display = 'block';
                } else {
                    moonIcon.style.display = 'block';
                    sunIcon.style.display = 'none';
                }
            }
        },

        initEmojiFont() {
            // Initialize emoji font from localStorage or default to system
            const savedEmojiFont = localStorage.getItem('emojiFont') || 'system';
            this.applyEmojiFont(savedEmojiFont);
        },

        applyEmojiFont(emojiFont, statusElement = null) {
            if (emojiFont === 'noto') {
                // Apply the class immediately (non-blocking)
                document.body.classList.add('use-noto-emoji');

                // Show loading status
                if (statusElement) {
                    statusElement.textContent = 'Loading...';
                    statusElement.className = 'setting-status loading';
                }

                // Load the font asynchronously in the background
                const loadFont = () => {
                    document.fonts.load('1em "Noto Color Emoji"').then(() => {
                        this.forceEmojiRerender();
                        console.log('Noto Color Emoji font loaded and applied');

                        // Show success status briefly, then hide
                        if (statusElement) {
                            statusElement.textContent = 'Loaded';
                            statusElement.className = 'setting-status loaded';
                            setTimeout(() => {
                                statusElement.textContent = '';
                                statusElement.className = 'setting-status';
                            }, 2000);
                        }
                    }).catch(() => {
                        setTimeout(() => this.forceEmojiRerender(), 500);
                        console.log('Noto Color Emoji font applied (with fallback)');

                        // Clear status on error
                        if (statusElement) {
                            statusElement.textContent = '';
                            statusElement.className = 'setting-status';
                        }
                    });
                };

                if (document.fonts) {
                    // Use requestIdleCallback to defer font loading
                    if (window.requestIdleCallback) {
                        window.requestIdleCallback(loadFont);
                    } else {
                        // Fallback if requestIdleCallback is not supported
                        setTimeout(loadFont, 0);
                    }
                } else {
                    // Browser doesn't support Font Loading API
                    setTimeout(() => {
                        this.forceEmojiRerender();
                        if (statusElement) {
                            statusElement.textContent = '';
                            statusElement.className = 'setting-status';
                        }
                    }, 500);
                }
            } else {
                // Remove Noto emoji class to use system default
                document.body.classList.remove('use-noto-emoji');
                // Force re-render to apply system emoji
                this.forceEmojiRerender();

                // Clear status
                if (statusElement) {
                    statusElement.textContent = '';
                    statusElement.className = 'setting-status';
                }
            }
        },

        initOmniSearch() {
            this.elements.omniSearchInput.addEventListener('input', (e) => {
                const searchTerm = e.target.value.toLowerCase();
                this.handleSpecialSearchTerms(searchTerm);
                this.performSearch(searchTerm);

                // Auto-expand panel on mobile when user enters search term
                if (searchTerm && window.innerWidth <= 768) {
                    this.elements.filterPanel.classList.remove('tags-collapsed');
                    this.elements.toggleTagsBtn.classList.remove('collapsed');
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

        handleSpecialSearchTerms(term) {
            // Toggle debug mode if search term is exactly "debug"
            if (term === 'debug') {
                this.state.debugMode = !this.state.debugMode;
                console.log('Debug Mode:', this.state.debugMode ? 'ENABLED' : 'DISABLED');
                this.updateDebugOverlay();
            }
            // Toggle Noto emoji font if search term is exactly "noto"
            else if (term === 'noto') {
                if (!document.body.classList.contains('use-noto-emoji')) {
                    this.updateEmojiFont();
                }
            }
        },

        getDisplayName(item) {
            // Use short_name if available, otherwise use the full name
            let nameToDisplay = item.short_name || item.name;
            if (nameToDisplay.length > 40) {
                nameToDisplay = nameToDisplay.substring(0, 35) + '…';
            }
            return nameToDisplay;
        },

        performSearch(term) {
            // --- Scoring Setup ---
            const dynamicFrequencies = TagFilterUI.getDynamicFrequencies();
            const matchingEventIds = new Set(this.state.currentlyMatchingEvents.map(e => e.id));
            const matchingLocationKeys = this.state.currentlyMatchingLocationKeys;
            const visibleEventIds = new Set(this.state.currentlyVisibleMatchingEvents.map(e => e.id));

            // Get selected tags for multi-tag match scoring
            const selectedTagsSet = new Set(this.state.selectedTagsWithColors.map(([tag]) => tag));

            const results = new Map();

            // Search locations
            for (const key in this.state.locationsByLatLng) {
                const location = this.state.locationsByLatLng[key];
                const hasSearchTerm = term.length > 0;
                const isVisible = this.state.currentlyVisibleMatchingLocationKeys.has(key);
                const isMatching = matchingLocationKeys.has(key);

                const nameMatch = hasSearchTerm && location.name.toLowerCase().includes(term);
                const tagsMatch = location.tags && location.tags.some(tag => tag.toLowerCase().includes(term));
                const matchesSearchTerm = nameMatch || tagsMatch;

                // Include location if:
                // 1. No search term: visible OR has matching events
                // 2. Has search term: ONLY if it matches the search term
                let shouldInclude;
                if (hasSearchTerm) {
                    shouldInclude = matchesSearchTerm;
                } else {
                    shouldInclude = isVisible || isMatching;
                }

                if (shouldInclude) {
                    let score = 1;
                    if (isMatching) {
                        score += 10; // Boost score if location has currently filtered events
                    }

                    // Boost score for locations that match multiple selected tags
                    if (selectedTagsSet.size >= 2 && location.tags) {
                        const matchedTagCount = location.tags.filter(tag => selectedTagsSet.has(tag)).length;
                        if (matchedTagCount > 0) {
                            score += matchedTagCount * 3; // +3 per matched tag
                        }
                    }

                    // Use precomputed distance for proximity bonus
                    const distance = this.state.locationDistances[key] || 0;
                    // Max bonus of 5 for being at the center, decreasing to 0 at 2km.
                    const proximityBonus = Math.max(0, 5 * (1 - distance / 20000));
                    score += proximityBonus;

                    // Add extra boost for visible locations
                    if (isVisible) {
                        score += 5;
                    }

                    const resultKey = `location-${key}`;
                    if (!results.has(resultKey)) {
                        results.set(resultKey, {
                            type: 'location',
                            ref: key,
                            displayName: this.getDisplayName(location),
                            emoji: location.emoji,
                            score: score,
                            isVisible: isVisible
                        });
                    }
                }
            }

            // Get reference date for temporal scoring
            const selectedDates = this.state.datePickerInstance?.selectedDates || [];
            const referenceDate = selectedDates.length > 0 ? selectedDates[0].getTime() : 0;
            const FIVE_DAYS_IN_MS = 5 * 24 * 60 * 60 * 1000;

            // Search events
            this.state.allEvents.forEach(event => {
                const resultKey = `event-${event.id}`;
                if (results.has(resultKey)) return;

                const hasSearchTerm = term.length > 0;
                const isVisible = visibleEventIds.has(event.id);
                const isMatching = matchingEventIds.has(event.id);

                const textMatch = hasSearchTerm && (
                    (event.name && event.name.toLowerCase().includes(term)) ||
                    (event.description && event.description.toLowerCase().includes(term)) ||
                    (event.location && event.location.toLowerCase().includes(term)) ||
                    (event.sublocation && event.sublocation.toLowerCase().includes(term))
                );

                // Include event if:
                // 1. No search term: visible OR matches tag filters
                // 2. Has search term: ONLY if it matches the search term
                let shouldInclude;
                if (hasSearchTerm) {
                    shouldInclude = textMatch;
                } else {
                    shouldInclude = isVisible || isMatching;
                }

                if (shouldInclude) {
                    let score = 1;
                    if (isMatching) {
                        score += 10; // Boost score if event matches current filters
                    }

                    // Boost score for events that match multiple selected tags
                    if (selectedTagsSet.size >= 2) {
                        // Combine event tags and location tags (just like isEventMatchingTagFilters does)
                        const locationInfo = event.locationKey ? this.state.locationsByLatLng[event.locationKey] : null;
                        const combinedTags = new Set([...(event.tags || []), ...(locationInfo?.tags || [])]);
                        const matchedTagCount = [...combinedTags].filter(tag => selectedTagsSet.has(tag)).length;
                        if (matchedTagCount > 0) {
                            score += matchedTagCount * 3; // +3 per matched tag
                        }
                    }

                    // Use precomputed distance for proximity bonus
                    if (event.locationKey) {
                        const distance = this.state.locationDistances[event.locationKey] || 0;
                        // Max bonus of 5 for being at the center, decreasing to 0 at 20km.
                        const proximityBonus = Math.max(0, 5 * (1 - distance / 20000));
                        score += proximityBonus;
                    }

                    // Add date-based scoring: prioritize events closer to the reference date
                    if (referenceDate > 0 && event.occurrences && event.occurrences.length > 0) {
                        const startTime = event.occurrences[0].start?.getTime() || 0;
                        const endTime = event.occurrences[0].end?.getTime() || startTime;

                        // Check if event is happening on the reference date
                        const isOngoingOnReferenceDate = startTime <= referenceDate && endTime >= referenceDate;

                        // Calculate distance from reference date with 5-day boost for ongoing events
                        let distanceFromReference = Math.abs(startTime - referenceDate);
                        if (isOngoingOnReferenceDate) {
                            distanceFromReference = Math.max(0, distanceFromReference - FIVE_DAYS_IN_MS);
                        }

                        // Convert distance to a score bonus (max +5 for events on the reference date, decreasing over time)
                        // Events within 30 days get a boost, beyond that the bonus is 0
                        const THIRTY_DAYS_IN_MS = 30 * 24 * 60 * 60 * 1000;
                        const temporalBonus = Math.max(0, 5 * (1 - distanceFromReference / THIRTY_DAYS_IN_MS));
                        score += temporalBonus;
                    }

                    // Add extra boost for visible events
                    if (isVisible) {
                        score += 5;
                    }

                    const nameToDisplay = this.getDisplayName(event);

                    results.set(resultKey, {
                        type: 'event',
                        ref: event.id,
                        displayName: Utils.formatAndSanitize(nameToDisplay).replace(/<\/?em>/g, ''),
                        emoji: event.emoji,
                        score: score,
                        isVisible: isVisible
                    });
                }
            });

            // Search tags
            this.state.allAvailableTags.forEach(tag => {
                if (tag.toLowerCase().includes(term)) {
                    // Skip geotags when search term is empty
                    if (!term && this.state.geotagsSet.has(tag.toLowerCase())) {
                        return;
                    }

                    const isVisible = this.state.visibleTagFrequencies[tag] > 0;

                    let score = dynamicFrequencies[tag] || 0;

                    // Boost score significantly for exact matches
                    if (tag.toLowerCase() === term) {
                        score += 1000;
                    }

                    // Add proximity-weighted score for tags that are visible on the map
                    // (visibleTagFrequencies already includes proximity weighting)
                    if (isVisible) {
                        score += this.state.visibleTagFrequencies[tag] * 5;
                        // Extra boost for visible tags (consistent with locations/events)
                        score += 5;
                    }

                    // Add a very small global frequency tiebreaker (0.01 per occurrence)
                    // This breaks ties for tags with the same dynamic frequency
                    const globalFreq = this.state.tagFrequencies[tag] || 0;
                    score += globalFreq * 0.01;

                    const resultKey = `tag-${tag}`;
                    if (!results.has(resultKey)) {
                        results.set(resultKey, {
                            type: 'tag',
                            ref: tag,
                            score: score,
                            isVisible: isVisible
                        });
                    }
                }
            });

            TagFilterUI.render(Array.from(results.values()), term);
        },

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
                const popupContentCallback = () => {
                    const selectedDates = this.state.datePickerInstance.selectedDates;
                    const currentPopupFilters = {
                        sliderStartDate: selectedDates[0],
                        sliderEndDate: selectedDates[1],
                        tagStates: TagFilterUI.getTagStates()
                    };
                    let eventsToDisplay = [...(this.state.eventsByLatLngInDateRange[locationKey] || [])];
                    if (this.state.forceDisplayEventId) {
                        const isForcedEventPresent = eventsToDisplay.some(e => e.id === this.state.forceDisplayEventId);
                        if (!isForcedEventPresent) {
                            const forcedEvent = this.state.eventsById[this.state.forceDisplayEventId];
                            if (forcedEvent && forcedEvent.locationKey === locationKey) {
                                eventsToDisplay.push(forcedEvent);
                            }
                        }
                    }

                    const filterFunctions = {
                       isEventMatchingTagFilters: this.isEventMatchingTagFilters.bind(this)
                    };
                    return UIManager.createLocationPopupContent(
                       locationInfo,
                       eventsToDisplay,
                       currentPopupFilters,
                       this.state.geotagsSet,
                       filterFunctions,
                       this.state.forceDisplayEventId,
                       selectedDates[0]
                    );
                };
                const newMarker = MapManager.addMarkerToMap([lat, lng], customIcon, locationInfo.name, popupContentCallback);
                if (newMarker) {
                    newMarker.openPopup();
                }
            }
        },

        updateFilteredEventList() {
            const selectedDates = this.state.datePickerInstance.selectedDates;
            if (selectedDates.length < 2) {
                this.state.allEventsFilteredByDateAndLocation = [];
            } else {
                const [startDate, endDate] = selectedDates;
                let events = this.filterEventsByDateRange(startDate, endDate);
    
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

        getFilterPanelDimensions() {
            let filterPanelWidth = 0;
            let filterPanelHeight = 0;
            const filterPanel = document.getElementById('filter-panel');
            if (filterPanel) {
                if (window.innerWidth <= 768) {
                    // On mobile, panel covers top of screen
                    // Use hardcoded height during initial load to avoid incorrect measurements
                    if (this.state.isInitialLoad) {
                        filterPanelHeight = 145;
                    } else {
                        filterPanelHeight = filterPanel.offsetHeight;
                    }
                } else {
                    // On desktop, panel covers left side of screen
                    filterPanelWidth = filterPanel.offsetWidth;
                }
            }
            return { filterPanelWidth, filterPanelHeight };
        },

        calculateVisibleCenter() {
            if (!this.state.map) return null;

            const center = this.state.map.getCenter();
            const centerPoint = this.state.map.latLngToContainerPoint(center);

            // Get filter panel dimensions
            const { filterPanelWidth, filterPanelHeight } = this.getFilterPanelDimensions();

            // Calculate the visible center (80% of the way between map center and edge of visible area)
            const visibleCenterPoint = L.point(
                centerPoint.x + filterPanelWidth * 0.4,
                centerPoint.y + filterPanelHeight * 0.4
            );

            return this.state.map.containerPointToLatLng(visibleCenterPoint);
        },

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

            // Check current theme to load appropriate tiles
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
            const tileUrl = currentTheme === 'dark'
                ? this.config.MAP_TILE_URL_DARK
                : this.config.MAP_TILE_URL_LIGHT;

            this.state.tileLayer = L.tileLayer(tileUrl, {
                attribution: this.config.MAP_ATTRIBUTION,
                maxZoom: this.config.MAP_MAX_ZOOM,
                updateWhenIdle: true,
                keepBuffer: 12
            }).addTo(this.state.map);

            const { markersLayer } = MapManager.init(this.state.map, this.state.tagColors, this.state.tagConfig.bgcolors);
            this.state.markersLayer = markersLayer;

            // Initialize debug layer
            this.state.debugLayer = L.layerGroup().addTo(this.state.map);

            // Adjust the initial view so the visible center (accounting for filter panel)
            // ends up at the desired initial view coordinates (from URL params or default)
            const desiredVisibleCenter = L.latLng(initialView);
            const currentVisibleCenter = this.calculateVisibleCenter();

            if (currentVisibleCenter) {
                // Calculate the offset needed to move visible center to desired position
                const currentCenter = this.state.map.getCenter();
                const offsetLat = desiredVisibleCenter.lat - currentVisibleCenter.lat;
                const offsetLng = desiredVisibleCenter.lng - currentVisibleCenter.lng;

                // Apply the offset to the map center
                const adjustedMapCenter = L.latLng(
                    currentCenter.lat + offsetLat,
                    currentCenter.lng + offsetLng
                );
                this.state.map.panTo(adjustedMapCenter, { animate: false });
            }

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
                        if (!popupElement || !this.state.debugRectBounds) return;

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
                        if (popupTop < this.state.debugRectBounds.top) {
                            panY = this.state.debugRectBounds.top - popupTop;
                        } else if (popupBottom > this.state.debugRectBounds.bottom) {
                            panY = this.state.debugRectBounds.bottom - popupBottom;
                        }

                        // Check horizontal bounds
                        if (popupLeft < this.state.debugRectBounds.left) {
                            panX = this.state.debugRectBounds.left - popupLeft;
                        } else if (popupRight > this.state.debugRectBounds.right) {
                            panX = this.state.debugRectBounds.right - popupRight;
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

                const eventsAtLocation = this.state.eventsByLatLngInDateRange[locationKey] || [];
                const currentTagStates = TagFilterUI.getTagStates();

                const hasMatchingEvents = eventsAtLocation.some(event =>
                    this.isEventMatchingTagFilters(event, currentTagStates)
                );

                if (!hasMatchingEvents) {
                    MapManager.removeMarker(marker);
                }
            });
        },

        initTagFilterUI() {
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
                getTagColor: (tag) => this.getTagColor(tag),
                assignColorToTag: (tag) => this.assignColorToTag(tag),
                unassignColorFromTag: (tag) => this.unassignColorFromTag(tag),
            });
            TagFilterUI.setAppProviders({ getSelectedLocationKey: () => this.state.selectedLocationKey });
            TagFilterUI.render([]); // Render with empty results initially
        },

        filterAndDisplayEvents(options = {}) {
            if (!this.state.datePickerInstance) {
                console.warn("filterAndDisplayEvents called before datePicker is initialized.");
                return;
            }

            let openPopup = null;
            let openMarker = null;
            if (this.state.map) {
                this.state.map.eachLayer(layer => {
                    if (layer instanceof L.Popup && this.state.map.hasLayer(layer)) {
                        openPopup = layer;
                        if (layer._source) { openMarker = layer._source; }
                    }
                });
            }

            const selectedDates = this.state.datePickerInstance.selectedDates;
            if (selectedDates.length < 2) {
                return;
            }

            const currentTagStates = TagFilterUI.getTagStates();

            const selectedTags = Object.entries(currentTagStates).filter(([, s]) => s === 'selected').map(([t]) => t);
            const requiredTags = Object.entries(currentTagStates).filter(([, s]) => s === 'required').map(([t]) => t); // eslint-disable-line
            const forbiddenTags = Object.entries(currentTagStates).filter(([, s]) => s === 'forbidden').map(([t]) => t); // eslint-disable-line

            let allMatchingEventsFlatList;
            
            if (selectedTags.length === 0 && requiredTags.length === 0) {
                allMatchingEventsFlatList = this.state.allEventsFilteredByDateAndLocation;
                if (forbiddenTags.length > 0) {
                    const forbiddenTagsSet = new Set(forbiddenTags);
                    allMatchingEventsFlatList = allMatchingEventsFlatList.filter(event =>
                        !event.tags?.some(tag => forbiddenTagsSet.has(tag))
                    );
                }
            } else {
                let eventsToFilter;

                if (requiredTags.length > 0) {
                    let matchingEventIds = new Set(this.state.eventTagIndex[requiredTags[0]] || []);
                    for (let i = 1; i < requiredTags.length; i++) {
                        const tag = requiredTags[i];
                        const eventIdsForTag = new Set(this.state.eventTagIndex[tag] || []);
                        matchingEventIds = new Set([...matchingEventIds].filter(id => eventIdsForTag.has(id)));
                    }
                    eventsToFilter = Array.from(matchingEventIds).map(id => this.state.eventsById[id]).filter(Boolean);
                } else if (selectedTags.length > 0) {
                    const matchingEventIds = new Set();
                    selectedTags.forEach(tag => {
                        if (this.state.eventTagIndex[tag]) {
                            this.state.eventTagIndex[tag].forEach(eventId => matchingEventIds.add(eventId));
                        }
                    });
                    eventsToFilter = Array.from(matchingEventIds).map(id => this.state.eventsById[id]).filter(Boolean);
                } else {
                    eventsToFilter = this.state.allEventsFilteredByDateAndLocation;
                }

                if (forbiddenTags.length > 0) {
                    const forbiddenTagsSet = new Set(forbiddenTags);
                    eventsToFilter = eventsToFilter.filter(event =>
                        !event.tags?.some(tag => forbiddenTagsSet.has(tag))
                    );
                }

                allMatchingEventsFlatList = eventsToFilter;
            }

            // Store the computed lists in the state for use by other functions like search.
            this.state.currentlyMatchingEvents = allMatchingEventsFlatList;

            const filteredLocations = {};
            allMatchingEventsFlatList.forEach(event => {
                if (event.locationKey) {
                    if (!filteredLocations[event.locationKey]) {
                        filteredLocations[event.locationKey] = [];
                    }
                    filteredLocations[event.locationKey].push(event);
                }
            });

            this.state.currentlyMatchingLocationKeys = new Set(Object.keys(filteredLocations));
            // After updating all matching items, update the visible subset as well.
            this.updateVisibleItems();

            if (openPopup) {
                const popupLatLng = openPopup.getLatLng();
                const locationKey = `${popupLatLng.lat},${popupLatLng.lng}`;
                const locationInfo = this.state.locationsByLatLng[locationKey];
                const eventsAtLocationInDateRange = this.state.eventsByLatLngInDateRange[locationKey] || [];

                const currentPopupFilters = {
                    sliderStartDate: selectedDates[0],
                    sliderEndDate: selectedDates[1],
                    tagStates: currentTagStates
                };
                const filterFunctions = {
                    isEventMatchingTagFilters: this.isEventMatchingTagFilters.bind(this)
                };

                let eventsToDisplay = eventsAtLocationInDateRange;
                if (this.state.forceDisplayEventId) {
                    const isForcedEventPresent = eventsToDisplay.some(e => e.id === this.state.forceDisplayEventId);
                    if (!isForcedEventPresent) {
                        const forcedEvent = this.state.eventsById[this.state.forceDisplayEventId];
                        if (forcedEvent && forcedEvent.locationKey === locationKey) {
                            // Create a new array to avoid mutating the original list
                            eventsToDisplay = [...eventsToDisplay, forcedEvent];
                        }
                    }
                }

                const newContent = UIManager.createLocationPopupContent(
                    locationInfo,
                    eventsToDisplay,
                    currentPopupFilters,
                    this.state.geotagsSet,
                    filterFunctions,
                    this.state.forceDisplayEventId,
                    selectedDates[0]
                );
                openPopup.setContent(newContent);
                this.state.forceDisplayEventId = null;
            }
            this.displayEventsOnMap(filteredLocations, openMarker);
            TagFilterUI.updateView(allMatchingEventsFlatList);
        },

        updateVisibleItems() {
            if (!this.state.map) return;

            // Calculate bounds based on the actual visible viewport
            // The map container is 150% size, so getSize() returns the enlarged size
            // We need 2/3 of that to get the actual visible area (100% / 150% = 2/3)
            const containerSize = this.state.map.getSize();
            const viewportWidth = containerSize.x * (2/3);
            let viewportHeight = containerSize.y * (2/3);

            // The filter panel overlays on top of the map
            // Calculate the visible portion excluding the filter panel
            const { filterPanelWidth, filterPanelHeight } = this.getFilterPanelDimensions();

            const center = this.state.map.getCenter();
            const centerPoint = this.state.map.latLngToContainerPoint(center);

            // Calculate the corners of the actual visible viewport
            const topLeft = L.point(
                centerPoint.x - viewportWidth / 2 + filterPanelWidth,
                centerPoint.y - viewportHeight / 2 + filterPanelHeight
            );
            const bottomRight = L.point(
                centerPoint.x + viewportWidth / 2,
                centerPoint.y + viewportHeight / 2
            );

            // Calculate and store the visible center (halfway between map center and edge of visible area)
            const visibleCenter = this.calculateVisibleCenter();
            this.state.visibleCenter = visibleCenter;

            // Precompute distances from visible center to all locations for efficient search
            this.state.locationDistances = {};
            for (const locationKey in this.state.locationsByLatLng) {
                const [lat, lng] = locationKey.split(',').map(Number);
                this.state.locationDistances[locationKey] = visibleCenter.distanceTo([lat, lng]);
            }

            const southWest = this.state.map.containerPointToLatLng(L.point(topLeft.x, bottomRight.y));
            const northEast = this.state.map.containerPointToLatLng(L.point(bottomRight.x, topLeft.y));
            const bounds = L.latLngBounds(southWest, northEast);

            // Calculate 90% inset bounds for popup positioning
            const inset = 0.05; // 5% inset on each side = 90% of bounds
            const insetTopLeft = L.point(
                topLeft.x + (viewportWidth - filterPanelWidth) * inset,
                topLeft.y + (viewportHeight - filterPanelHeight) * inset
            );
            const insetBottomRight = L.point(
                bottomRight.x - viewportWidth * inset,
                bottomRight.y - (viewportHeight - filterPanelHeight) * inset
            );

            // Store debug rectangle bounds in state (in container point coordinates)
            this.state.debugRectBounds = {
                top: insetTopLeft.y,
                bottom: insetBottomRight.y,
                left: insetTopLeft.x,
                right: insetBottomRight.x
            };

            const visibleEvents = [];
            const visibleLocationKeys = new Set();
            const visibleTagFrequencies = {};

            this.state.currentlyMatchingEvents.forEach(event => {
                if (event.locationKey) {
                    const [lat, lng] = event.locationKey.split(',').map(Number);
                    if (bounds.contains([lat, lng])) {
                        visibleEvents.push(event);
                        visibleLocationKeys.add(event.locationKey);

                        // Count tag frequencies for visible events
                        if (event.tags) {
                            const distance = visibleCenter.distanceTo([lat, lng]);
                            // Max bonus of 1 for being at the center, decreasing to 0 at 2km.
                            const proximityWeight = Math.max(0, 1 - distance / 20000);
                            event.tags.forEach(tag => {
                                if (!visibleTagFrequencies[tag]) {
                                    visibleTagFrequencies[tag] = 0;
                                }
                                visibleTagFrequencies[tag] += 1 + proximityWeight;
                            });
                        }
                    }
                }
            });

            this.state.currentlyVisibleMatchingEvents = visibleEvents;
            this.state.currentlyVisibleMatchingLocationKeys = visibleLocationKeys;
            this.state.visibleTagFrequencies = visibleTagFrequencies;
        },

        isEventMatchingTagFilters(event, tagStates) {
            const selectedTags = Object.entries(tagStates).filter(([, state]) => state === 'selected').map(([tag]) => tag);
            const requiredTags = Object.entries(tagStates).filter(([, state]) => state === 'required').map(([tag]) => tag);
            const forbiddenTags = Object.entries(tagStates).filter(([, state]) => state === 'forbidden').map(([tag]) => tag);
        
            const locationInfo = this.state.locationsByLatLng[event.locationKey];
            const combinedTags = new Set([...(event.tags || []), ...(locationInfo?.tags || [])]);
        
            if (forbiddenTags.length > 0 && forbiddenTags.some(tag => combinedTags.has(tag))) {
                return false;
            }
            if (requiredTags.length > 0 && !requiredTags.every(tag => combinedTags.has(tag))) {
                return false;
            }
            if (requiredTags.length === 0 && selectedTags.length > 0 && !selectedTags.some(tag => combinedTags.has(tag))) {
                return false;
            }
            return true;
        },
        
        isEventInDateRange(event, startDate, endDate) {
            if (!event.occurrences || event.occurrences.length === 0) {
                return false;
            }
            const startFilter = (startDate instanceof Date && !isNaN(startDate)) ? startDate : this.config.START_DATE;
            let endFilter = (endDate instanceof Date && !isNaN(endDate)) ? endDate : this.config.END_DATE;
            endFilter = new Date(endFilter);
            endFilter.setHours(23, 59, 59, 999);

            for (const occurrence of event.occurrences) {
                if (occurrence.start <= endFilter && occurrence.end >= startFilter) {
                    return true;
                }
            }
            return false;
        },

        filterEventsByDateRange(startDate, endDate) {
            const startFilter = (startDate instanceof Date && !isNaN(startDate)) ? startDate : this.config.START_DATE;
            let endFilter = (endDate instanceof Date && !isNaN(endDate)) ? endDate : this.config.END_DATE;
            endFilter = new Date(endFilter);
            endFilter.setHours(23, 59, 59, 999);

            const filteredEvents = [];
            for (const event of this.state.allEvents) {
                if (!event.occurrences || event.occurrences.length === 0) {
                    continue;
                }

                const matchingOccurrences = event.occurrences.filter(occurrence => {
                    return occurrence.start <= endFilter && occurrence.end >= startFilter;
                });

                if (matchingOccurrences.length > 0) {
                    const eventWithMatchingOccurrences = { ...event, matching_occurrences: matchingOccurrences };
                    filteredEvents.push(eventWithMatchingOccurrences);
                }
            }
            return filteredEvents;
        },

        displayEventsOnMap(locationsToDisplay, markerToKeep = null) {
             let openMarkerLocationKey = null;
             if (markerToKeep) {
                 const latLng = markerToKeep.getLatLng();
                 openMarkerLocationKey = `${latLng.lat},${latLng.lng}`;
             }
 
             MapManager.clearMarkers(markerToKeep);
             let visibleLocationCount = markerToKeep ? 1 : 0;
 
             for (const locationKey in locationsToDisplay) {
                 if (locationKey === openMarkerLocationKey) {
                     continue;
                 }
 
                 if (visibleLocationCount >= this.config.MARKER_DISPLAY_LIMIT) {
                     console.warn(`Marker display limit (${this.config.MARKER_DISPLAY_LIMIT}) reached.`);
                     break;
                 }
 
                 const eventsAtLocation = locationsToDisplay[locationKey];
                 if (eventsAtLocation.length === 0) continue;
 
                 visibleLocationCount++;
 
                 const [lat, lng] = locationKey.split(',').map(Number);
                 if (lat === 0 && lng === 0) continue;
 
                 const locationInfo = this.state.locationsByLatLng[locationKey];
                 if (!locationInfo) continue;

                 const locationName = locationInfo.name
                 const customIcon = MapManager.createMarkerIcon(locationInfo);
 
                 const popupContentCallback = () => {
                     const selectedDates = this.state.datePickerInstance.selectedDates;
                     const currentPopupFilters = {
                         sliderStartDate: selectedDates[0],
                         sliderEndDate: selectedDates[1],
                         tagStates: TagFilterUI.getTagStates()
                     };
                     const eventsAtLocationInDateRange = this.state.eventsByLatLngInDateRange[locationKey] || [];
                     const filterFunctions = {
                        isEventMatchingTagFilters: this.isEventMatchingTagFilters.bind(this)
                     };

                     let eventsToDisplay = eventsAtLocationInDateRange;
                     if (this.state.forceDisplayEventId) {
                         const isForcedEventPresent = eventsToDisplay.some(e => e.id === this.state.forceDisplayEventId);
                         if (!isForcedEventPresent) {
                             const forcedEvent = this.state.eventsById[this.state.forceDisplayEventId];
                             if (forcedEvent && forcedEvent.locationKey === locationKey) {
                                 eventsToDisplay = [...eventsToDisplay, forcedEvent];
                             }
                         }
                     }

                     return UIManager.createLocationPopupContent(
                        locationInfo,
                        eventsToDisplay,
                        currentPopupFilters,
                        this.state.geotagsSet,
                        filterFunctions,
                        this.state.forceDisplayEventId,
                        selectedDates[0]
                     );
                 };
 
                 const newMarker = MapManager.addMarkerToMap([lat, lng], customIcon, locationName, popupContentCallback);
                 if (this.state.forceDisplayEventId && newMarker) {
                    if (eventsAtLocation.some(e => e.id === this.state.forceDisplayEventId)) {
                        newMarker.openPopup();
                    }
                 }
             }
        },

        updateSelectedTagsDisplay() {
            if (!this.elements.selectedTagsDisplay) return;

            // Use the order from selectedTagsWithColors to maintain selection order
            const selectedTags = this.state.selectedTagsWithColors.map(([tag, color]) => tag);

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

        getTagColor(tag) {
            // Linear search through selected tags
            const entry = this.state.selectedTagsWithColors.find(([t, color]) => t === tag);
            return entry ? entry[1] : null;
        },

        assignColorToTag(tag) {
            // Check if already assigned
            if (this.state.selectedTagsWithColors.some(([t, color]) => t === tag)) {
                return;
            }

            const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
            const palette = currentTheme === 'dark'
                ? this.config.TAG_COLOR_PALETTE_DARK
                : this.config.TAG_COLOR_PALETTE_LIGHT;

            // Find the first unused color in the palette
            const usedColors = new Set(this.state.selectedTagsWithColors.map(([t, c]) => c));
            let color = palette.find(c => !usedColors.has(c));

            // If all colors are used, wrap around
            if (!color) {
                const colorIndex = this.state.selectedTagsWithColors.length % palette.length;
                color = palette[colorIndex];
            }

            // Add to the list
            this.state.selectedTagsWithColors.push([tag, color]);
        },

        unassignColorFromTag(tag) {
            // Remove from the list
            const index = this.state.selectedTagsWithColors.findIndex(([t, color]) => t === tag);
            if (index > -1) {
                this.state.selectedTagsWithColors.splice(index, 1);
            }
        },

        reassignTagColors() {
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
            const palette = currentTheme === 'dark'
                ? this.config.TAG_COLOR_PALETTE_DARK
                : this.config.TAG_COLOR_PALETTE_LIGHT;

            // Reassign colors based on current selection order
            this.state.selectedTagsWithColors.forEach(([tag, oldColor], index) => {
                const newColor = palette[index % palette.length];
                this.state.selectedTagsWithColors[index] = [tag, newColor];
            });
        },

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

        updateEmojiFont() {
            document.body.classList.add('use-noto-emoji');
            console.log('Noto Color Emoji font enabled - loading...');

            // Force re-render of all emoji elements after font loads
            if (document.fonts) {
                document.fonts.load('1em "Noto Color Emoji"').then(() => {
                    this.forceEmojiRerender();
                    console.log('Noto Color Emoji font loaded and applied');
                }).catch(() => {
                    setTimeout(() => this.forceEmojiRerender(), 500);
                    console.log('Noto Color Emoji font applied (with fallback)');
                });
            } else {
                setTimeout(() => this.forceEmojiRerender(), 500);
            }
        },

        forceEmojiRerender() {
            // Force browser to re-render emoji elements by triggering a reflow
            const emojiElements = document.querySelectorAll('.marker-emoji, .popup-header-emoji, .popup-event-emoji');
            emojiElements.forEach(elem => {
                // Force reflow by reading offsetHeight and toggling visibility
                const originalDisplay = elem.style.display;
                elem.style.display = 'none';
                // Trigger reflow
                void elem.offsetHeight;
                elem.style.display = originalDisplay || '';
            });

            // Also refresh all markers on the map by re-rendering them
            if (this.state.markersLayer) {
                // Get all visible markers and their data
                const markersToRefresh = [];
                this.state.markersLayer.eachLayer(marker => {
                    const latLng = marker.getLatLng();
                    const locationKey = `${latLng.lat},${latLng.lng}`;
                    markersToRefresh.push({
                        marker: marker,
                        locationKey: locationKey
                    });
                });

                // Refresh each marker icon to force emoji re-render
                markersToRefresh.forEach(({marker, locationKey}) => {
                    const locationInfo = this.state.locationsByLatLng[locationKey];
                    if (locationInfo) {
                        const newIcon = MapManager.createMarkerIcon(locationInfo);
                        marker.setIcon(newIcon);
                    }
                });
            }
        },

        /**
         * Generate a shareable URL with current map state and copy to clipboard
         */
        shareCurrentView() {
            try {
                // Get current visible center (accounting for filter panel) and zoom
                const center = this.calculateVisibleCenter() || this.state.map.getCenter();
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
                    UIManager.showToast('Link copied to clipboard!', 'success', 3000);
                }).catch(err => {
                    console.error('Failed to copy to clipboard:', err);
                    // Fallback: show the URL in a toast for manual copying
                    UIManager.showToast('Could not copy automatically. URL: ' + shareUrl, 'info', 5000);
                });

            } catch (error) {
                console.error('Error generating share URL:', error);
                UIManager.showToast('Failed to generate share link', 'error', 3000);
            }
        }
    };

    App.init();
});