/**
 * UIManager Module
 *
 * Manages UI components and event listeners for the application.
 * Coordinates date picker, filter panel interactions, and popup content creation.
 *
 * Note: Modal and toast functionality has been extracted to ModalManager and ToastNotifier modules.
 * Note: Popup content creation is delegated to PopupContentBuilder module.
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

    // ========================================
    // DATE PRESETS
    // ========================================

    function getDatePresets() {
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        const tomorrow = new Date(today);
        tomorrow.setDate(tomorrow.getDate() + 1);

        const dayOfWeek = today.getDay();
        let daysUntilSunday = (7 - dayOfWeek) % 7;
        // On Saturday/Sunday, show the upcoming week instead
        if (daysUntilSunday <= 1) daysUntilSunday += 7;
        const nextSunday = new Date(today);
        nextSunday.setDate(nextSunday.getDate() + daysUntilSunday);

        const presets = [
            { label: 'Today', range: [new Date(today), new Date(today)] },
            { label: 'Tomorrow', range: [new Date(tomorrow), new Date(tomorrow)] },
            { label: 'This Week', range: [new Date(today), new Date(nextSunday)] },
        ];

        return presets;
    }

    function getPresetLabel(selectedDates) {
        if (selectedDates.length !== 2) return null;
        const presets = getDatePresets();
        const start = new Date(selectedDates[0]);
        start.setHours(0, 0, 0, 0);
        const end = new Date(selectedDates[1]);
        end.setHours(0, 0, 0, 0);

        for (const preset of presets) {
            if (start.getTime() === preset.range[0].getTime() &&
                end.getTime() === preset.range[1].getTime()) {
                return preset.label;
            }
        }
        return null;
    }

    function updateDatePickerDisplay(instance, elements) {
        const label = getPresetLabel(instance.selectedDates);
        if (label) {
            instance.input.value = label;
        }
        resizeDatePickerInput(instance, elements);

        // Update preset button active states
        const calendar = instance.calendarContainer;
        if (calendar) {
            const buttons = calendar.querySelectorAll('.flatpickr-preset-btn');
            buttons.forEach(btn => {
                btn.classList.toggle('active', btn.textContent === label);
            });
        }
    }

    function injectDatePresets(instance, elements) {
        const presets = getDatePresets();
        const container = document.createElement('div');
        container.className = 'flatpickr-presets';

        const minDate = instance.config.minDate;
        const maxDate = instance.config.maxDate;

        presets.forEach(preset => {
            if ((minDate && preset.range[0] < minDate) || (maxDate && preset.range[1] > maxDate)) return;

            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'flatpickr-preset-btn';
            btn.textContent = preset.label;
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                instance.setDate(preset.range, true);
                instance.close();
            });
            container.appendChild(btn);
        });

        const calendar = instance.calendarContainer;
        calendar.insertBefore(container, calendar.firstChild);
    }

    // ========================================
    // DATE PICKER INIT
    // ========================================

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

        // Check if URL date range is stale (entirely in the past)
        const urlDatesStale = urlParams.end instanceof Date && urlParams.end < today;

        if (!urlDatesStale && urlParams.start instanceof Date) {
            // Clamp start to today if it's in the past
            initialStartDate = urlParams.start < today ? today : urlParams.start;
        } else if (today.getTime() > config.START_DATE.getTime() && today.getTime() <= config.END_DATE.getTime()) {
            initialStartDate = today;
        }

        if (!urlDatesStale && urlParams.end instanceof Date) {
            finalDefaultEndDate = urlParams.end;
        } else {
            // Default to same day as start (matches "Today" preset)
            finalDefaultEndDate = new Date(initialStartDate.getTime());
        }

        state.datePickerInstance = flatpickr(elements.datePicker, {
            mode: "range",
            dateFormat: "M j",
            defaultDate: [initialStartDate, finalDefaultEndDate],
            minDate: config.START_DATE,
            maxDate: config.END_DATE,
            monthSelectorType: "static",
            onReady: (selectedDates, dateStr, instance) => {
                injectDatePresets(instance, elements);
                updateDatePickerDisplay(instance, elements);
            },
            onChange: (selectedDates, dateStr, instance) => {
                if (selectedDates.length === 2) {
                    updateDatePickerDisplay(instance, elements);
                }
            },
            onClose: (selectedDates, dateStr, instance) => {
                if (selectedDates.length === 2) {
                    callbacks.onDatePickerClose(selectedDates);
                }
                updateDatePickerDisplay(instance, elements);
            }
        });

        const initialSelectedDates = state.datePickerInstance.selectedDates;
        if (initialSelectedDates.length === 2) {
            callbacks.onDatePickerClose(initialSelectedDates);
        }

        // Re-measure after fonts load (initial sizing may use fallback font metrics)
        document.fonts.ready.then(() => {
            if (state.datePickerInstance) {
                resizeDatePickerInput(state.datePickerInstance, elements);
            }
        });
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
        input.style.width = `${sizer.offsetWidth + 2}px`;
    }

    // ========================================
    // EVENT LISTENERS
    // ========================================

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
    // POPUP CONTENT CREATION (delegated to PopupContentBuilder)
    // ========================================

    /**
     * Creates popup content for a location marker
     * Delegates to PopupContentBuilder for actual content creation
     * @param {Object} locationInfo - Location information
     * @param {Array} eventsAtLocation - Events at this location
     * @param {Object} activeFilters - Active filter states
     * @param {Set} geotagsSet - Set of geotags
     * @param {Object} filterFunctions - Filter function callbacks
     * @param {string|null} forceDisplayEventId - Event ID to force display
     * @param {Date|null} selectedStartDate - Currently selected start date
     * @returns {HTMLElement} Popup content container
     */
    function createLocationPopupContent(locationInfo, eventsAtLocation, activeFilters, geotagsSet, filterFunctions, forceDisplayEventId = null, selectedStartDate = null, previousActiveTab = null) {
        return PopupContentBuilder.createLocationPopupContent(
            locationInfo,
            eventsAtLocation,
            activeFilters,
            geotagsSet,
            filterFunctions,
            forceDisplayEventId,
            selectedStartDate,
            previousActiveTab
        );
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Date picker
        destroyDatePicker,
        initDatePicker,
        resizeDatePickerInput,
        updateDatePickerDisplay,
        getPresetLabel,

        // Event listeners
        initLogoMenu,

        // Popup content (delegated to PopupContentBuilder)
        createLocationPopupContent,
        createPopupHeader: PopupContentBuilder.createPopupHeader,
        createEventsList: PopupContentBuilder.createEventsList,
        createEventDetail: PopupContentBuilder.createEventDetail
    };
})();
