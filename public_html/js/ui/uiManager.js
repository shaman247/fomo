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
            const defaultEndDate = new Date(today.getTime() + (6 * Constants.TIME.ONE_DAY_MS));
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
    function createLocationPopupContent(locationInfo, eventsAtLocation, activeFilters, geotagsSet, filterFunctions, forceDisplayEventId = null, selectedStartDate = null) {
        return PopupContentBuilder.createLocationPopupContent(
            locationInfo,
            eventsAtLocation,
            activeFilters,
            geotagsSet,
            filterFunctions,
            forceDisplayEventId,
            selectedStartDate
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

        // Event listeners
        initLogoMenu,

        // Popup content (delegated to PopupContentBuilder)
        createLocationPopupContent,
        createPopupHeader: (locationInfo, geotagsSet) => PopupContentBuilder.createPopupHeader(locationInfo, geotagsSet),
        createEventsList: (eventsAtLocation, activeFilters, locationInfo, filterFunctions, forceDisplayEventId, selectedStartDate) =>
            PopupContentBuilder.createEventsList(eventsAtLocation, activeFilters, locationInfo, filterFunctions, forceDisplayEventId, selectedStartDate),
        createEventDetail: (event) => PopupContentBuilder.createEventDetail(event)
    };
})();
