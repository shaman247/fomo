/**
 * UIManager Module
 *
 * Manages UI components and event listeners for the application.
 * Coordinates date picker, filter panel interactions, and popup content creation.
 *
 * Note: Modal and toast functionality has been extracted to ModalManager and ToastNotifier modules.
 *
 * @module UIManager
 */
const UIManager = (() => {
    // ========================================
    // DATE PICKER
    // ========================================

    /**
     * Destroys the Flatpickr instance to prevent memory leaks
     * @param {Object} state - Application state containing datePickerInstance
     */
    function destroyDatePicker(state) {
        if (state.datePickerInstance) {
            try {
                state.datePickerInstance.destroy();
            } catch (error) {
                console.warn('Failed to destroy Flatpickr instance:', error);
            }
            state.datePickerInstance = null;
        }
    }

    /**
     * Initializes the date picker with Flatpickr
     * @param {Object} elements - DOM element references
     * @param {Object} config - Application configuration
     * @param {Object} state - Application state
     * @param {Object} callbacks - Callback functions
     */
    function initDatePicker(elements, config, state, callbacks) {
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        // Destroy existing instance to prevent memory leaks
        destroyDatePicker(state);

        // Check for URL parameters for start and end dates
        const urlParams = state.urlParams || {};
        let initialStartDate = config.START_DATE;
        let finalDefaultEndDate = null;

        if (urlParams.start && urlParams.start instanceof Date) {
            initialStartDate = urlParams.start;
        } else if (today.getTime() > config.START_DATE.getTime() && today.getTime() <= config.END_DATE.getTime()) {
            initialStartDate = today;
        }

        if (urlParams.end && urlParams.end instanceof Date) {
            finalDefaultEndDate = urlParams.end;
        } else {
            const defaultEndDate = new Date(today.getTime() + (6 * config.ONE_DAY_IN_MS));
            finalDefaultEndDate = defaultEndDate > config.END_DATE ? config.END_DATE : defaultEndDate;
        }

        state.datePickerInstance = flatpickr(elements.datePicker, {
            mode: "range",
            dateFormat: "M j",
            defaultDate: [initialStartDate, finalDefaultEndDate],
            minDate: config.START_DATE,
            maxDate: config.END_DATE,
            monthSelectorType: "static",
            onReady: (selectedDates, dateStr, instance) => resizeDatePickerInput(instance, elements),
            onClose: (selectedDates, dateStr, instance) => {
                if (selectedDates.length === 2) {
                    callbacks.onDatePickerClose(selectedDates);
                }
                resizeDatePickerInput(instance, elements);
            }
        });

        const initialSelectedDates = state.datePickerInstance.selectedDates;
        if (initialSelectedDates.length === 2) {
            callbacks.onDatePickerClose(initialSelectedDates);
        }
    }

    /**
     * Resizes the date picker input to fit its content
     * @param {Object} instance - Flatpickr instance
     * @param {Object} elements - DOM element references
     */
    function resizeDatePickerInput(instance, elements) {
        const input = instance.input;
        const sizer = elements.datePickerSizer;
        if (!sizer || !input) return;
        sizer.textContent = input.value || input.placeholder;
        input.style.width = `${sizer.offsetWidth + 5}px`;
    }

    // ========================================
    // EVENT LISTENERS
    // ========================================

    /**
     * Initializes event listeners for UI components
     * @param {Object} elements - DOM element references
     * @param {Object} callbacks - Callback functions
     */
    function initEventListeners(elements, callbacks = {}) {
        const tagsWrapper = document.getElementById('tags-wrapper');
        if (elements.toggleTagsBtn && tagsWrapper) {
            if (window.innerWidth <= Constants.UI.MOBILE_BREAKPOINT) {
                tagsWrapper.classList.add('collapsed');
                elements.toggleTagsBtn.classList.add('collapsed');
            }
            elements.toggleTagsBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const willBeCollapsed = !tagsWrapper.classList.contains('collapsed');
                tagsWrapper.classList.toggle('collapsed');

                // Toggle class on button for arrow rotation
                elements.toggleTagsBtn.classList.toggle('collapsed', willBeCollapsed);
            });
        }
    }

    /**
     * Initializes the logo menu with dropdown functionality
     * @param {Object} callbacks - Callback functions
     */
    function initLogoMenu(callbacks = {}) {
        const logoContainer = document.getElementById('logo-container');
        const logoMenu = document.getElementById('logo-menu');
        const settingsBtn = document.getElementById('settings-btn');
        const shareViewBtn = document.getElementById('share-view-btn');

        if (!logoContainer || !logoMenu) return;

        // Toggle menu on logo button click
        logoContainer.addEventListener('click', (e) => {
            e.stopPropagation();
            const isHidden = logoMenu.classList.contains('logo-menu-hidden');
            logoMenu.classList.toggle('logo-menu-hidden');
            logoContainer.setAttribute('aria-expanded', isHidden ? 'true' : 'false');
        });

        // Close menu when clicking outside
        document.addEventListener('click', (e) => {
            if (!logoMenu.contains(e.target) && e.target !== logoContainer && !logoContainer.contains(e.target)) {
                logoMenu.classList.add('logo-menu-hidden');
                logoContainer.setAttribute('aria-expanded', 'false');
            }
        });

        // Share view button handler
        if (shareViewBtn && callbacks.onShareView) {
            shareViewBtn.addEventListener('click', () => {
                logoMenu.classList.add('logo-menu-hidden');
                logoContainer.setAttribute('aria-expanded', 'false');
                callbacks.onShareView();
            });
        }

        // Settings button handler
        if (settingsBtn) {
            settingsBtn.addEventListener('click', () => {
                logoMenu.classList.add('logo-menu-hidden');
                logoContainer.setAttribute('aria-expanded', 'false');
                ModalManager.openSettingsModal();
            });
        }

        // Close menu when About link is clicked
        const aboutLink = logoMenu.querySelector('a[href="about.html"]');
        if (aboutLink) {
            aboutLink.addEventListener('click', () => {
                logoMenu.classList.add('logo-menu-hidden');
                logoContainer.setAttribute('aria-expanded', 'false');
            });
        }
    }

    // ========================================
    // POPUP CONTENT CREATION
    // ========================================

    /**
     * Creates popup content for a location marker
     * @param {Object} locationInfo - Location information
     * @param {Array} eventsAtLocation - Events at this location
     * @param {Object} activeFilters - Active filter states
     * @param {Set} geotagsSet - Set of geotags
     * @param {Object} filterFunctions - Filter function callbacks
     * @param {string|null} forceDisplayEventId - Event ID to force display
     * @param {Date|null} selectedStartDate - Currently selected start date
     * @returns {HTMLElement} Popup content container
     */
    function createLocationPopupContent(locationInfo, eventsAtLocation, activeFilters, geotagsSet, filterFunctions, forceDisplayEventId = null, selectedStartDate = null) {
        const popupContainer = document.createElement('div');
        popupContainer.className = 'leaflet-popup-content';

        if (locationInfo) {
            popupContainer.appendChild(createPopupHeader(locationInfo, geotagsSet));
        }

        popupContainer.appendChild(createEventsList(eventsAtLocation, activeFilters, locationInfo, filterFunctions, forceDisplayEventId, selectedStartDate));

        return popupContainer;
    }

    /**
     * Creates the header section of a popup
     * @param {Object} locationInfo - Location information
     * @param {Set} geotagsSet - Set of geotags
     * @returns {HTMLElement} Header wrapper element
     */
    function createPopupHeader(locationInfo, geotagsSet = new Set()) {
        const headerWrapper = document.createElement('div');
        headerWrapper.className = 'popup-header';

        const emojiSpan = document.createElement('span');
        emojiSpan.className = 'popup-header-emoji';
        emojiSpan.textContent = Utils.escapeHtml(locationInfo.emoji);
        headerWrapper.appendChild(emojiSpan);

        const textWrapper = document.createElement('div');
        textWrapper.className = 'popup-header-text';

        const locationP = document.createElement('p');
        locationP.className = 'popup-header-location';
        locationP.innerHTML = Utils.formatAndSanitize(locationInfo.name);
        textWrapper.appendChild(locationP);

        const displayTags = (locationInfo.tags || []).filter(tag => !geotagsSet.has(tag.toLowerCase()));
        if (displayTags.length > 0) {
            const tagsContainer = document.createElement('div');
            tagsContainer.className = 'tag-tags-container popup-tags-container';
            displayTags.forEach(tag => {
                const tagButton = TagFilterUI.createInteractiveTagButton(tag);
                if (tagButton) {
                    tagsContainer.appendChild(tagButton);
                }
            });
            textWrapper.appendChild(tagsContainer);
        }

        headerWrapper.appendChild(textWrapper);
        return headerWrapper;
    }

    /**
     * Creates the events list section of a popup
     * @param {Array} eventsAtLocation - Events at this location
     * @param {Object} activeFilters - Active filter states
     * @param {Object} locationInfo - Location information
     * @param {Object} filterFunctions - Filter function callbacks
     * @param {string|null} forceDisplayEventId - Event ID to force display
     * @param {Date|null} selectedStartDate - Currently selected start date
     * @returns {HTMLElement} Events list wrapper element
     */
    function createEventsList(eventsAtLocation, activeFilters, locationInfo, filterFunctions, forceDisplayEventId = null, selectedStartDate = null) {
        const eventsListWrapper = document.createElement('div');
        eventsListWrapper.className = 'popup-events-list';

        if (eventsAtLocation.length === 0 && !forceDisplayEventId) {
            const noEventsP = document.createElement('p');
            noEventsP.textContent = "No events at this location in the selected date range.";
            eventsListWrapper.appendChild(noEventsP);
            return eventsListWrapper;
        }

        const selectedTags = Object.entries(activeFilters.tagStates)
            .filter(([, state]) => (state === 'selected' || state === 'required'))
            .map(([tag]) => tag);

        const hasActiveTagFilters = selectedTags.length > 0;
        const hasForbiddenTags = Object.entries(activeFilters.tagStates).some(([, state]) => state === 'forbidden');
        const hasAnyTagFilter = hasActiveTagFilters || hasForbiddenTags;

        let forcedEvent = null;
        let otherEvents = [...eventsAtLocation];

        if (forceDisplayEventId) {
            const forcedEventIndex = otherEvents.findIndex(e => e.id === forceDisplayEventId);
            if (forcedEventIndex > -1) {
                [forcedEvent] = otherEvents.splice(forcedEventIndex, 1);
            }
        }

        const eventsToProcess = forcedEvent ? [forcedEvent, ...otherEvents] : eventsAtLocation;

        // Pre-calculate sort-related properties to avoid re-computation inside the sort function.
        const referenceDate = selectedStartDate ? selectedStartDate.getTime() : (activeFilters.sliderStartDate ? activeFilters.sliderStartDate.getTime() : 0);
        const FIVE_DAYS_IN_MS = 5 * 24 * 60 * 60 * 1000;

        const eventsWithSortData = eventsToProcess.map(event => {
            const isMatchingTags = filterFunctions.isEventMatchingTagFilters(event, activeFilters.tagStates);
            let selectedTagMatchCount = 0;
            if (hasActiveTagFilters && isMatchingTags) {
                selectedTagMatchCount = selectedTags.filter(tag => (event.tags || []).includes(tag)).length;
            }
            const startTime = event.occurrences?.[0]?.start?.getTime() || 0;
            const endTime = event.occurrences?.[0]?.end?.getTime() || startTime;

            // Check if event is happening on the reference date
            const isOngoingOnReferenceDate = startTime <= referenceDate && endTime >= referenceDate;

            // Calculate distance with a 5-day boost for ongoing events
            let distanceFromReference = Math.abs(startTime - referenceDate);
            if (isOngoingOnReferenceDate) {
                distanceFromReference = Math.max(0, distanceFromReference - FIVE_DAYS_IN_MS);
            }

            return {
                event,
                isMatchingTags,
                selectedTagMatchCount,
                startTime,
                distanceFromReference
            };
        });

        // Always sort the events based on matching status, tag count, and distance from selected date.
        eventsWithSortData.sort((a, b) => {
            // Primary sort: matching events first
            if (a.isMatchingTags !== b.isMatchingTags) {
                return b.isMatchingTags - a.isMatchingTags;
            }
            // Secondary sort: by number of matching selected tags
            if (a.selectedTagMatchCount !== b.selectedTagMatchCount) {
                return b.selectedTagMatchCount - a.selectedTagMatchCount;
            }
            // Tertiary sort: by distance from selected start date (closest first)
            return a.distanceFromReference - b.distanceFromReference;
        });

        // If an event is forced, find it in the sorted list and move it to the top.
        if (forcedEvent) {
            const forcedEventSortDataIndex = eventsWithSortData.findIndex(data => data.event.id === forcedEvent.id);
            if (forcedEventSortDataIndex > 0) { // No need to move if it's already first
                const [forcedEventSortData] = eventsWithSortData.splice(forcedEventSortDataIndex, 1);
                eventsWithSortData.unshift(forcedEventSortData);
            }
        }

        const expandAll = !hasAnyTagFilter && eventsToProcess.length > 0 && eventsToProcess.length < 4;
        let isFirstEvent = true;

        eventsWithSortData.forEach(({ event, isMatchingTags }) => {
            const details = document.createElement('details');

            if (forcedEvent) {
                // If an event is forced, expand it and collapse all others.
                details.open = (event.id === forcedEvent.id);
            } else if (hasAnyTagFilter) {
                details.open = isMatchingTags;
            } else {
                details.open = expandAll || isFirstEvent;
            }

            const summary = document.createElement('summary');
            const emojiPrefix = event.emoji ? `${event.emoji} ` : '';
            const sanitizedName = Utils.formatAndSanitize(event.name).replace(/<\/?em>/g, '');
            summary.innerHTML = `${emojiPrefix}${sanitizedName}`;

            details.appendChild(summary);

            details.appendChild(createEventDetail(event));
            eventsListWrapper.appendChild(details);
            isFirstEvent = false;
        });

        return eventsListWrapper;
    }

    /**
     * Creates the detail section for a single event
     * @param {Object} event - Event object
     * @returns {HTMLElement} Event detail container element
     */
    function createEventDetail(event) {
        const eventDetailContainer = document.createElement('div');
        eventDetailContainer.className = 'popup-event-detail';

        const dateTimeP = document.createElement('p');
        dateTimeP.className = 'popup-event-datetime';
        dateTimeP.textContent = Utils.formatEventDateTimeCompactly(event);
        eventDetailContainer.appendChild(dateTimeP);

        const descriptionP = document.createElement('p');
        descriptionP.innerHTML = Utils.formatAndSanitize(event.description);

        // Handle both new urls array and legacy url field
        const urls = event.urls || (event.url ? [event.url] : []);
        if (urls && urls.length > 0) {
            const linkIconSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>`;

            urls.forEach((url) => {
                if (url && Utils.isValidUrl(url)) {
                    const urlLink = document.createElement('a');
                    urlLink.href = url;
                    urlLink.target = '_blank';
                    urlLink.rel = 'noopener noreferrer';
                    urlLink.className = 'popup-external-link';
                    urlLink.title = 'More Info (opens in new tab)';
                    urlLink.innerHTML = `  ${linkIconSvg} `;
                    descriptionP.appendChild(urlLink);
                }
            });
        }
        eventDetailContainer.appendChild(descriptionP);

        if (event.tags && event.tags.length > 0) {
            const tagsContainer = document.createElement('div');
            tagsContainer.className = 'tag-tags-container popup-tags-container';
            event.tags.forEach(tag => {
                const tagButton = TagFilterUI.createInteractiveTagButton(tag);
                if (tagButton) {
                    tagsContainer.appendChild(tagButton);
                }
            });
            eventDetailContainer.appendChild(tagsContainer);
        }

        return eventDetailContainer;
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Date picker
        destroyDatePicker,
        initDatePicker,
        resizeDatePickerInput,

        // Event listeners
        initEventListeners,
        initLogoMenu,

        // Popup content
        createLocationPopupContent,
        createPopupHeader,
        createEventsList,
        createEventDetail
    };
})();
