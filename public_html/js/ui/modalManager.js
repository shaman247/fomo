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
 * - Accessibility features (focus management)
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

        // DOM references
        settingsModal: null,
        welcomeModal: null
    };

    // ========================================
    // SETTINGS MODAL
    // ========================================

    /**
     * Initializes the settings modal
     * @param {Object} callbacks - Callback functions
     * @param {Function} callbacks.onEmojiFontChange - Called when emoji font changes
     * @param {Function} callbacks.onThemeChange - Called when theme changes
     */
    function initSettingsModal(callbacks = {}) {
        state.onEmojiFontChange = callbacks.onEmojiFontChange;
        state.onThemeChange = callbacks.onThemeChange;

        const modal = document.getElementById('settings-modal');
        const closeBtn = document.getElementById('settings-close-btn');
        const emojiFontRadios = document.querySelectorAll('input[name="emoji-font"]');
        const themeRadios = document.querySelectorAll('input[name="theme"]');

        if (!modal || !closeBtn || emojiFontRadios.length === 0 || themeRadios.length === 0) return;

        state.settingsModal = modal;

        // Load current settings with safe storage
        const savedEmojiFont = Utils.SafeStorage.getItem('emojiFont') || 'system';
        const savedTheme = Utils.SafeStorage.getItem('theme') || 'dark';

        // Set the correct radio buttons based on saved settings
        emojiFontRadios.forEach(radio => {
            radio.checked = radio.value === savedEmojiFont;
        });
        themeRadios.forEach(radio => {
            radio.checked = radio.value === savedTheme;
        });

        // Close modal when clicking close button
        closeBtn.addEventListener('click', () => {
            closeSettingsModal();
        });

        // Close modal when clicking outside
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeSettingsModal();
            }
        });

        // Handle emoji font change
        emojiFontRadios.forEach(radio => {
            radio.addEventListener('change', (e) => {
                const emojiFont = e.target.value;
                Utils.SafeStorage.setItem('emojiFont', emojiFont);
                if (state.onEmojiFontChange) {
                    state.onEmojiFontChange(emojiFont);
                }
            });
        });

        // Handle theme change
        themeRadios.forEach(radio => {
            radio.addEventListener('change', (e) => {
                const theme = e.target.value;
                Utils.SafeStorage.setItem('theme', theme);
                if (state.onThemeChange) {
                    state.onThemeChange(theme);
                }
            });
        });

        // Close modal on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modal.classList.contains('show')) {
                closeSettingsModal();
            }
        });
    }

    /**
     * Opens the settings modal
     */
    function openSettingsModal() {
        const modal = state.settingsModal || document.getElementById('settings-modal');
        if (modal) {
            modal.classList.add('show');
            // Focus the first input for accessibility
            const firstInput = modal.querySelector('select');
            if (firstInput) {
                setTimeout(() => firstInput.focus(), 100);
            }
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
        const closeBtn = document.getElementById('welcome-close-btn');

        if (!modal || !closeBtn) return;

        state.welcomeModal = modal;

        // Close modal when clicking close button
        closeBtn.addEventListener('click', () => {
            closeWelcomeModal();
        });

        // Close modal when clicking outside
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeWelcomeModal();
            }
        });

        // Close modal on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modal.classList.contains('show')) {
                closeWelcomeModal();
            }
        });
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
        // Settings modal
        initSettingsModal,
        openSettingsModal,
        closeSettingsModal,

        // Welcome modal
        initWelcomeModal,
        showWelcomeModalIfFirstVisit,
        openWelcomeModal,
        closeWelcomeModal
    };
})();
