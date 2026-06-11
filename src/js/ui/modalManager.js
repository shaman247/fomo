/**
 * ModalManager Module
 *
 * Manages modal dialogs for the application.
 * Handles welcome modal and settings modal functionality.
 *
 * Features:
 * - Welcome modal for first-time visitors
 * - Settings modal for user preferences (theme, emoji font)
 * - Keyboard navigation (Escape key support)
 * - Click-outside-to-close behavior
 *
 * @module ModalManager
 */
const ModalManager = (() => {
    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // Callbacks
        onEmojiFontChange: null,
        onThemeChange: null,
        onLocationToggle: null,

        // DOM references
        settingsModal: null,
        welcomeModal: null,
        locationToggle: null,
        locationStatus: null
    };

    // ========================================
    // SHARED DISMISS WIRING
    // ========================================

    /**
     * Wires standard dismiss behavior onto a modal: click-to-close and
     * Escape-to-close while the modal is shown.
     * @param {HTMLElement} modal - The modal overlay element
     * @param {Function} close - Closes the modal
     * @param {Object} [options]
     * @param {boolean} [options.closeOnAnyClick=false] - Close on any click on
     *   the modal (including its content), not just the backdrop
     */
    function wireDismiss(modal, close, { closeOnAnyClick = false } = {}) {
        modal.addEventListener('click', (e) => {
            if (closeOnAnyClick || e.target === modal) {
                close();
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modal.classList.contains('show')) {
                close();
            }
        });
    }

    // ========================================
    // SETTINGS MODAL
    // ========================================

    /**
     * Initializes the settings modal
     * @param {Object} callbacks - Callback functions
     * @param {Function} callbacks.onEmojiFontChange - Called when emoji font changes
     * @param {Function} callbacks.onThemeChange - Called when theme changes
     * @param {Function} callbacks.onLocationToggle - Called when location toggle changes
     */
    function initSettingsModal(callbacks = {}) {
        state.onEmojiFontChange = callbacks.onEmojiFontChange;
        state.onThemeChange = callbacks.onThemeChange;
        state.onLocationToggle = callbacks.onLocationToggle;

        const modal = document.getElementById('settings-modal');
        const closeBtn = document.getElementById('settings-close-btn');
        const emojiFontRadios = document.querySelectorAll('input[name="emoji-font"]');
        const themeRadios = document.querySelectorAll('input[name="theme"]');
        const locationToggle = document.getElementById('use-location-toggle');
        const locationStatus = document.getElementById('location-status');

        if (!modal || !closeBtn || emojiFontRadios.length === 0 || themeRadios.length === 0) return;

        state.settingsModal = modal;
        state.locationToggle = locationToggle;
        state.locationStatus = locationStatus;

        // Load current settings with safe storage
        const savedEmojiFont = Utils.SafeStorage.getItem('emojiFont') || 'system';
        const savedTheme = Utils.SafeStorage.getItem('theme') || 'dark';
        const savedUseLocation = Utils.SafeStorage.getItem('useLocation') === 'true';

        // Set the correct radio buttons based on saved settings
        emojiFontRadios.forEach(radio => {
            radio.checked = radio.value === savedEmojiFont;
            // Disable Noto option on unsupported browsers (Safari)
            if (radio.value === 'noto' && !EmojiManager.isNotoSupported()) {
                radio.disabled = true;
                const label = radio.closest('label');
                if (label) label.style.opacity = '0.4';
            }
        });
        themeRadios.forEach(radio => {
            radio.checked = radio.value === savedTheme;
        });
        if (locationToggle) {
            locationToggle.checked = savedUseLocation;
        }

        // Close modal when clicking close button
        closeBtn.addEventListener('click', () => {
            closeSettingsModal();
        });

        // Close modal when clicking outside or on Escape
        wireDismiss(modal, closeSettingsModal);

        // Handle emoji font change
        emojiFontRadios.forEach(radio => {
            radio.addEventListener('change', (e) => {
                const emojiFont = e.target.value;
                if (state.onEmojiFontChange) {
                    state.onEmojiFontChange(emojiFont);
                }
            });
        });

        // Handle theme change
        themeRadios.forEach(radio => {
            radio.addEventListener('change', (e) => {
                const theme = e.target.value;
                if (state.onThemeChange) {
                    state.onThemeChange(theme);
                }
            });
        });

        // Handle location toggle change
        if (locationToggle) {
            locationToggle.addEventListener('change', (e) => {
                const useLocation = e.target.checked;
                Utils.SafeStorage.setItem('useLocation', useLocation ? 'true' : 'false');
                if (state.onLocationToggle) {
                    state.onLocationToggle(useLocation);
                }
            });
        }

    }

    /**
     * Opens the settings modal
     */
    function openSettingsModal() {
        const modal = state.settingsModal || document.getElementById('settings-modal');
        if (modal) {
            modal.classList.add('show');
        }
    }

    /**
     * Closes the settings modal
     */
    function closeSettingsModal() {
        const modal = state.settingsModal || document.getElementById('settings-modal');
        if (modal) {
            modal.classList.remove('show');
        }
    }

    /**
     * Updates the location status message in settings
     * @param {string} message - Status message to display
     * @param {string} [className] - Optional CSS class ('loading', 'loaded', or empty)
     */
    function setLocationStatus(message, className = '') {
        const statusEl = state.locationStatus || document.getElementById('location-status');
        if (statusEl) {
            statusEl.textContent = message;
            statusEl.className = 'setting-status' + (className ? ' ' + className : '');
        }
    }

    /**
     * Checks if location setting is enabled
     * @returns {boolean} True if user has enabled location
     */
    function isLocationEnabled() {
        return Utils.SafeStorage.getItem('useLocation') === 'true';
    }

    // ========================================
    // WELCOME MODAL
    // ========================================

    /**
     * Initializes the welcome modal
     */
    function initWelcomeModal() {
        const modal = document.getElementById('welcome-modal');

        if (!modal) return;

        state.welcomeModal = modal;

        // Close modal when clicking anywhere on it, or on Escape
        wireDismiss(modal, closeWelcomeModal, { closeOnAnyClick: true });
    }

    /**
     * Shows the welcome modal if this is the user's first visit
     */
    function showWelcomeModalIfFirstVisit() {
        // Check if user has visited before with safe storage
        const hasVisitedBefore = Utils.SafeStorage.getItem('hasVisitedBefore');

        if (!hasVisitedBefore) {
            // Mark that user has now visited
            Utils.SafeStorage.setItem('hasVisitedBefore', 'true');

            // Show the welcome modal after a short delay to let the page load
            setTimeout(() => {
                openWelcomeModal();
            }, 50);
        }
    }

    /**
     * Opens the welcome modal
     */
    function openWelcomeModal() {
        const modal = state.welcomeModal || document.getElementById('welcome-modal');
        if (modal) {
            modal.classList.add('show');
        }
    }

    /**
     * Closes the welcome modal
     */
    function closeWelcomeModal() {
        const modal = state.welcomeModal || document.getElementById('welcome-modal');
        if (modal) {
            modal.classList.remove('show');
        }
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Shared
        wireDismiss,

        // Settings modal
        initSettingsModal,
        openSettingsModal,
        setLocationStatus,
        isLocationEnabled,

        // Welcome modal
        initWelcomeModal,
        showWelcomeModalIfFirstVisit
    };
})();
