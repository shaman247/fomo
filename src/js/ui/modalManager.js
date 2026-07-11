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

    /**
     * Initializes the settings modal
     * @param {Object} callbacks - Callback functions
     * @param {Function} callbacks.onEmojiFontChange - Called when emoji font changes
     * @param {Function} callbacks.onThemeChange - Called when theme changes
     */
    /**
     * Rebuilds the theme options from the Themes registry so every theme
     * (built-in + prototypes) is selectable from settings. Falls back to the
     * static dark/light markup if the container is missing.
     */
    function _populateThemeOptions() {
        const container = document.getElementById('theme-options');
        if (!container || typeof Themes === 'undefined') return;
        container.textContent = '';
        Themes.list().forEach(def => {
            const label = document.createElement('label');
            label.className = 'setting-option';
            const input = document.createElement('input');
            input.type = 'radio';
            input.name = 'theme';
            input.value = def.name;
            const text = document.createElement('span');
            text.textContent = def.label;
            label.appendChild(input);
            label.appendChild(text);
            container.appendChild(label);
        });
    }

    /**
     * Builds one setting group per prototype layout flag (ProtoFlags) and
     * keeps it in sync with changes made elsewhere (the ?proto=1 picker,
     * docked→popups lock). The `layout` flag is applied at load time, so
     * changing it surfaces a "Reload now" affordance instead of pretending.
     */
    function _buildProtoFlagGroups() {
        const host = document.getElementById('proto-setting-groups');
        if (!host || typeof ProtoFlags === 'undefined') return;

        const FLAG_LABELS = { layout: 'Layout', popups: 'Popups', chips: 'Chips' };
        host.textContent = '';

        ProtoFlags.list().forEach(flag => {
            const group = document.createElement('div');
            group.className = 'setting-group';
            group.dataset.protoFlag = flag.name;

            const groupLabel = document.createElement('label');
            groupLabel.className = 'setting-group-label';
            groupLabel.textContent = FLAG_LABELS[flag.name] || flag.name;
            group.appendChild(groupLabel);

            const options = document.createElement('div');
            options.className = 'setting-options';
            flag.values.forEach(value => {
                const label = document.createElement('label');
                label.className = 'setting-option';
                const input = document.createElement('input');
                input.type = 'radio';
                input.name = `proto-${flag.name}`;
                input.value = value;
                input.addEventListener('change', () => {
                    ProtoFlags.set(flag.name, value);
                    if (flag.requiresReload) {
                        const status = document.getElementById('proto-reload-status');
                        if (status) status.style.display = '';
                    }
                });
                const text = document.createElement('span');
                text.textContent = value.charAt(0).toUpperCase() + value.slice(1);
                label.appendChild(input);
                label.appendChild(text);
                options.appendChild(label);
            });
            group.appendChild(options);
            host.appendChild(group);
        });

        // Reload affordance for load-time flags (hidden until needed)
        const status = document.createElement('button');
        status.type = 'button';
        status.id = 'proto-reload-status';
        status.className = 'proto-reload-status';
        status.textContent = '↻ Layout changes apply after a reload — tap to reload';
        status.style.display = 'none';
        status.addEventListener('click', () => window.location.reload());
        host.appendChild(status);

        _syncProtoFlagGroups();
        document.addEventListener('protoflagschange', _syncProtoFlagGroups);
    }

    /** Reflects current flag values + lock states onto the radios. */
    function _syncProtoFlagGroups() {
        const host = document.getElementById('proto-setting-groups');
        if (!host || typeof ProtoFlags === 'undefined') return;
        ProtoFlags.list().forEach(flag => {
            const group = host.querySelector(`[data-proto-flag="${flag.name}"]`);
            if (!group) return;
            group.querySelectorAll('input').forEach(input => {
                input.checked = input.value === flag.value;
                input.disabled = !!flag.locked;
            });
            group.style.opacity = flag.locked ? '0.5' : '';
            group.title = flag.locked ? 'Forced by the docked layout' : '';
        });
    }

    /** Reflects the active theme onto the theme radios (modal open, changes). */
    function _syncThemeRadios() {
        const current = Utils.getCurrentTheme();
        document.querySelectorAll('input[name="theme"]').forEach(radio => {
            radio.checked = radio.value === current;
        });
    }

    function initSettingsModal(callbacks = {}) {
        state.onEmojiFontChange = callbacks.onEmojiFontChange;
        state.onThemeChange = callbacks.onThemeChange;

        const modal = document.getElementById('settings-modal');
        const closeBtn = document.getElementById('settings-close-btn');

        // Dynamic sections: full theme registry + prototype layout flags
        _populateThemeOptions();
        _buildProtoFlagGroups();

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

    }

    /**
     * Opens the settings modal
     */
    function openSettingsModal() {
        const modal = state.settingsModal || document.getElementById('settings-modal');
        if (modal) {
            // The theme/flags may have changed via the ?proto picker or URL
            // params since init — reflect reality before showing.
            _syncThemeRadios();
            _syncProtoFlagGroups();
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
