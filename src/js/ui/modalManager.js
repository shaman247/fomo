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
        getDebugMode: null,

        // DOM references
        settingsModal: null,
        welcomeModal: null
    };

    /** Whether debug mode (the "debug" search easter egg) is active. */
    function _debugEnabled() {
        return typeof state.getDebugMode === 'function' && !!state.getDebugMode();
    }

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
     * Rebuilds the theme options from the Themes registry. Prototype themes
     * are debug-gated (type "debug" in search to toggle): normally only the
     * built-in dark/light options show — plus the active theme when it IS a
     * prototype one, so the checked state never points at a hidden option.
     * Rebuilt on every modal open; change handling is delegated (init), so
     * rebuilt radios need no re-wiring.
     */
    function _populateThemeOptions() {
        const container = document.getElementById('theme-options');
        if (!container || typeof Themes === 'undefined') return;
        const debug = _debugEnabled();
        const current = Utils.getCurrentTheme();
        container.textContent = '';
        Themes.list().forEach(def => {
            if (!debug && def.proto && def.name !== current) return;
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
     * Debug-gated like the prototype themes; rebuilt on every modal open.
     */
    function _buildProtoFlagGroups() {
        const host = document.getElementById('proto-setting-groups');
        if (!host || typeof ProtoFlags === 'undefined') return;

        const FLAG_LABELS = { layout: 'Layout', popups: 'Popups', chips: 'Chips' };
        host.textContent = '';
        if (!_debugEnabled()) return;

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

    /**
     * Initializes the settings modal
     * @param {Object} callbacks - Callback functions
     * @param {Function} callbacks.onEmojiFontChange - Called when emoji font changes
     * @param {Function} callbacks.onThemeChange - Called when theme changes
     * @param {Function} [callbacks.getDebugMode] - Returns whether debug mode
     *   is active (gates the prototype theme/layout options)
     */
    function initSettingsModal(callbacks = {}) {
        state.onEmojiFontChange = callbacks.onEmojiFontChange;
        state.onThemeChange = callbacks.onThemeChange;
        state.getDebugMode = callbacks.getDebugMode;

        const modal = document.getElementById('settings-modal');
        const closeBtn = document.getElementById('settings-close-btn');
        const themeOptions = document.getElementById('theme-options');

        // Dynamic sections: themes + (debug-gated) prototype layout flags.
        // Rebuilt on every open; handled via delegation below.
        _populateThemeOptions();
        _buildProtoFlagGroups();
        _syncThemeRadios();

        const emojiFontRadios = document.querySelectorAll('input[name="emoji-font"]');

        if (!modal || !closeBtn || !themeOptions || emojiFontRadios.length === 0) return;

        state.settingsModal = modal;

        // Load current settings with safe storage
        const savedEmojiFont = Utils.SafeStorage.getItem('emojiFont') || 'system';

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

        // Handle theme change — delegated, so per-open rebuilds of the
        // option list need no re-wiring
        themeOptions.addEventListener('change', (e) => {
            if (e.target.name === 'theme' && state.onThemeChange) {
                state.onThemeChange(e.target.value);
            }
        });

        // Keep flag radios honest when flags change elsewhere (?proto picker)
        document.addEventListener('protoflagschange', _syncProtoFlagGroups);
    }

    /**
     * Opens the settings modal
     */
    function openSettingsModal() {
        const modal = state.settingsModal || document.getElementById('settings-modal');
        if (modal) {
            // Rebuild the dynamic sections: debug mode may have been toggled
            // since the last open (which gates the prototype options), and
            // the theme/flags may have changed via the ?proto picker.
            _populateThemeOptions();
            _buildProtoFlagGroups();
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
