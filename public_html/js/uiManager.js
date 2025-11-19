const UIManager = {
    initDatePicker: function(elements, config, state, callbacks) {
        const today = new Date();
        today.setHours(0, 0, 0, 0);

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
            onReady: (selectedDates, dateStr, instance) => this.resizeDatePickerInput(instance, elements),
            onClose: (selectedDates, dateStr, instance) => {
                if (selectedDates.length === 2) {
                    callbacks.onDatePickerClose(selectedDates);
                }
                this.resizeDatePickerInput(instance, elements);
            }
        });

        const initialSelectedDates = state.datePickerInstance.selectedDates;
        if (initialSelectedDates.length === 2) {
            callbacks.onDatePickerClose(initialSelectedDates);
        }
    },

    initEventListeners: function(elements, callbacks = {}) {
        const tagsWrapper = document.getElementById('tags-wrapper');
        if (elements.toggleTagsBtn && tagsWrapper) {
            if (window.innerWidth <= 768) {
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
    },

    initLogoMenu: function(callbacks = {}) {
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
                this.openSettingsModal();
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
    },

    resizeDatePickerInput: function(instance, elements) {
        const input = instance.input;
        const sizer = elements.datePickerSizer;
        if (!sizer || !input) return;
        sizer.textContent = input.value || input.placeholder;
        input.style.width = `${sizer.offsetWidth + 5}px`;
    },

    createLocationPopupContent: function(locationInfo, eventsAtLocation, activeFilters, geotagsSet, filterFunctions, forceDisplayEventId = null, selectedStartDate = null) {
        const popupContainer = document.createElement('div');
        popupContainer.className = 'leaflet-popup-content';

        if (locationInfo) {
            popupContainer.appendChild(this.createPopupHeader(locationInfo, geotagsSet));
        }

        popupContainer.appendChild(this.createEventsList(eventsAtLocation, activeFilters, locationInfo, filterFunctions, forceDisplayEventId, selectedStartDate));

        return popupContainer;
    },

    createPopupHeader: function (locationInfo, geotagsSet = new Set()) {
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
    },

    createEventsList: function(eventsAtLocation, activeFilters, locationInfo, filterFunctions, forceDisplayEventId = null, selectedStartDate = null) {
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

            details.appendChild(this.createEventDetail(event));
            eventsListWrapper.appendChild(details);
            isFirstEvent = false;
        });

        return eventsListWrapper;
    },

    createEventDetail: function(event) {
        const eventDetailContainer = document.createElement('div');
        eventDetailContainer.className = 'popup-event-detail';

        const dateTimeP = document.createElement('p');
        dateTimeP.className = 'popup-event-datetime';
        dateTimeP.textContent = Utils.formatEventDateTimeCompactly(event);
        eventDetailContainer.appendChild(dateTimeP);

        const descriptionP = document.createElement('p');
        descriptionP.innerHTML = Utils.formatAndSanitize(event.description);
        if (event.url && Utils.isValidUrl(event.url)) {
            const linkIconSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>`;
            const urlLink = document.createElement('a');
            urlLink.href = event.url;
            urlLink.target = '_blank';
            urlLink.rel = 'noopener noreferrer';
            urlLink.className = 'popup-external-link';
            urlLink.title = 'More Info (opens in new tab)';
            urlLink.innerHTML = ` ${linkIconSvg}`;
            descriptionP.appendChild(urlLink);
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
    },

    initSettingsModal: function(callbacks = {}) {
        const modal = document.getElementById('settings-modal');
        const closeBtn = document.getElementById('settings-close-btn');
        const emojiFontRadios = document.querySelectorAll('input[name="emoji-font"]');
        const themeRadios = document.querySelectorAll('input[name="theme"]');

        if (!modal || !closeBtn || emojiFontRadios.length === 0 || themeRadios.length === 0) return;

        // Load current settings
        const savedEmojiFont = localStorage.getItem('emojiFont') || 'system';
        const savedTheme = localStorage.getItem('theme') || 'dark';

        // Set the correct radio buttons based on saved settings
        emojiFontRadios.forEach(radio => {
            radio.checked = radio.value === savedEmojiFont;
        });
        themeRadios.forEach(radio => {
            radio.checked = radio.value === savedTheme;
        });

        // Close modal when clicking close button
        closeBtn.addEventListener('click', () => {
            this.closeSettingsModal();
        });

        // Close modal when clicking outside
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                this.closeSettingsModal();
            }
        });

        // Handle emoji font change
        emojiFontRadios.forEach(radio => {
            radio.addEventListener('change', (e) => {
                const emojiFont = e.target.value;
                localStorage.setItem('emojiFont', emojiFont);
                if (callbacks.onEmojiFontChange) {
                    callbacks.onEmojiFontChange(emojiFont);
                }
            });
        });

        // Handle theme change
        themeRadios.forEach(radio => {
            radio.addEventListener('change', (e) => {
                const theme = e.target.value;
                localStorage.setItem('theme', theme);
                if (callbacks.onThemeChange) {
                    callbacks.onThemeChange(theme);
                }
            });
        });

        // Close modal on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modal.classList.contains('show')) {
                this.closeSettingsModal();
            }
        });
    },

    openSettingsModal: function() {
        const modal = document.getElementById('settings-modal');
        if (modal) {
            modal.classList.add('show');
            // Focus the first input for accessibility
            const firstInput = modal.querySelector('select');
            if (firstInput) {
                setTimeout(() => firstInput.focus(), 100);
            }
        }
    },

    closeSettingsModal: function() {
        const modal = document.getElementById('settings-modal');
        if (modal) {
            modal.classList.remove('show');
        }
    },

    initWelcomeModal: function() {
        const modal = document.getElementById('welcome-modal');
        const closeBtn = document.getElementById('welcome-close-btn');

        if (!modal || !closeBtn) return;

        // Close modal when clicking close button
        closeBtn.addEventListener('click', () => {
            this.closeWelcomeModal();
        });

        // Close modal when clicking outside
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                this.closeWelcomeModal();
            }
        });

        // Close modal on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modal.classList.contains('show')) {
                this.closeWelcomeModal();
            }
        });
    },

    showWelcomeModalIfFirstVisit: function() {
        // Check if user has visited before
        const hasVisitedBefore = localStorage.getItem('hasVisitedBefore');

        if (!hasVisitedBefore) {
            // Mark that user has now visited
            localStorage.setItem('hasVisitedBefore', 'true');

            // Show the welcome modal after a short delay to let the page load
            setTimeout(() => {
                this.openWelcomeModal();
            }, 50);
        }
    },

    openWelcomeModal: function() {
        const modal = document.getElementById('welcome-modal');
        if (modal) {
            modal.classList.add('show');
        }
    },

    closeWelcomeModal: function() {
        const modal = document.getElementById('welcome-modal');
        if (modal) {
            modal.classList.remove('show');
        }
    },

    /**
     * Show a toast notification message
     * @param {string} message - The message to display
     * @param {string} type - Type of toast: 'success', 'error', or 'info' (default)
     * @param {number} duration - Duration in ms (default 3000)
     */
    showToast: function(message, type = 'info', duration = 3000) {
        const toast = document.getElementById('toast-notification');
        if (!toast) return;

        // Clear any existing timeout
        if (this._toastTimeout) {
            clearTimeout(this._toastTimeout);
        }

        // Set message and type
        toast.textContent = message;
        toast.className = 'toast-notification';
        if (type === 'success' || type === 'error') {
            toast.classList.add(type);
        }

        // Show toast
        setTimeout(() => {
            toast.classList.add('show');
        }, 10);

        // Auto-hide after duration
        this._toastTimeout = setTimeout(() => {
            toast.classList.remove('show');
        }, duration);
    }
};
