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
        onThemeChange: null,

        // DOM references
        settingsModal: null,
        welcomeModal: null
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

    /** Reflects the active theme onto the theme radios (modal open, changes). */
    function _syncThemeRadios() {
        const current = Utils.getCurrentTheme();
        document.querySelectorAll('input[name="theme"]').forEach(radio => {
            radio.checked = radio.value === current;
        });
    }

    /**
     * Initializes the settings modal
     * @param {Object} callbacks - Callback functions
     * @param {Function} callbacks.onThemeChange - Called when theme changes
     */
    function initSettingsModal(callbacks = {}) {
        state.onThemeChange = callbacks.onThemeChange;

        const modal = document.getElementById('settings-modal');
        const closeBtn = document.getElementById('settings-close-btn');
        const themeOptions = document.getElementById('theme-options');

        _syncThemeRadios();

        if (!modal || !closeBtn || !themeOptions) return;
        state.settingsModal = modal;

        // Close modal when clicking close button
        closeBtn.addEventListener('click', () => {
            closeSettingsModal();
        });

        // Close modal when clicking outside or on Escape
        wireDismiss(modal, closeSettingsModal);

        // Handle changes to the Dark and Light options.
        themeOptions.addEventListener('change', (e) => {
            if (e.target.name === 'theme' && state.onThemeChange) {
                state.onThemeChange(e.target.value);
            }
        });
    }

    /**
     * Opens the settings modal
     */
    function openSettingsModal() {
        const modal = state.settingsModal || document.getElementById('settings-modal');
        if (modal) {
            _syncThemeRadios();
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

        // Welcome modal
        initWelcomeModal,
        showWelcomeModalIfFirstVisit
    };
})();
