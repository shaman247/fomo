/**
 * PopupContentBuilder Module
 *
 * Handles the creation of popup content for location markers.
 * Extracts popup building logic from UIManager for better separation of concerns.
 *
 * Features:
 * - Creates popup headers with location info and tags
 * - Builds event lists with sorting and filtering
 * - Handles forced event display
 * - Creates event detail sections with links
 *
 * @module PopupContentBuilder
 */
const PopupContentBuilder = (() => {
    // ========================================
    // STATE
    // ========================================

    /**
     * Module state - stores callback for creating interactive tag buttons
     */
    const state = {
        createInteractiveTagButton: null
    };

    // ========================================
    // POPUP HEADER
    // ========================================

    /**
     * Creates the header section of a popup
     * @param {Object} locationInfo - Location information
     * @param {Set} geotagsSet - Set of geotags to exclude from display
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
        if (displayTags.length > 0 && state.createInteractiveTagButton) {
            const tagsContainer = document.createElement('div');
            tagsContainer.className = 'tag-tags-container popup-tags-container';
            displayTags.forEach(tag => {
                const tagButton = state.createInteractiveTagButton(tag);
                if (tagButton) {
                    tagsContainer.appendChild(tagButton);
                }
            });
            textWrapper.appendChild(tagsContainer);
        }

        headerWrapper.appendChild(textWrapper);
        return headerWrapper;
    }

    // ========================================
    // EVENT DETAIL
    // ========================================

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
        // Limit to max 1 URL per distinct domain name
        const urls = event.urls || (event.url ? [event.url] : []);
        if (urls && urls.length > 0) {
            const linkIconSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>`;

            const seenDomains = new Set();
            urls.forEach((url) => {
                if (url && Utils.isValidUrl(url)) {
                    try {
                        const domain = new URL(url).hostname;
                        if (seenDomains.has(domain)) return;
                        seenDomains.add(domain);
                    } catch {
                        // If URL parsing fails, skip domain check and show the link
                    }
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

        if (event.tags && event.tags.length > 0 && state.createInteractiveTagButton) {
            const tagsContainer = document.createElement('div');
            tagsContainer.className = 'tag-tags-container popup-tags-container';
            event.tags.forEach(tag => {
                const tagButton = state.createInteractiveTagButton(tag);
                if (tagButton) {
                    tagsContainer.appendChild(tagButton);
                }
            });
            eventDetailContainer.appendChild(tagsContainer);
        }

        return eventDetailContainer;
    }

    // ========================================
    // EVENTS LIST
    // ========================================

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

        // Get all selected tags (explicit, required, and implicit)
        const selectedTags = Object.entries(activeFilters.tagStates)
            .filter(([, state]) => (state === 'selected' || state === 'required' || state === 'implicit'))
            .map(([tag]) => tag);

        // Get only explicitly selected tags (for determining if filters are active)
        const explicitlySelectedTags = Object.entries(activeFilters.tagStates)
            .filter(([, state]) => (state === 'selected' || state === 'required'))
            .map(([tag]) => tag);

        const hasActiveTagFilters = explicitlySelectedTags.length > 0;
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

    // ========================================
    // MAIN BUILDER
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

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the PopupContentBuilder module
     * @param {Object} config - Configuration object
     * @param {Function} config.createInteractiveTagButton - Callback to create interactive tag buttons
     */
    function init(config) {
        state.createInteractiveTagButton = config.createInteractiveTagButton || null;
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        init,
        createLocationPopupContent,
        createPopupHeader,
        createEventsList,
        createEventDetail
    };
})();
