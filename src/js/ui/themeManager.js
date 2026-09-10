/**
 * ThemeManager Module
 *
 * Manages theme switching between dark and light modes for the application.
 * Handles theme persistence, DOM updates, and map tile layer updates.
 *
 * Features:
 * - Switch between dark and light themes
 * - Persist theme preference in localStorage
 * - Update map tile layers based on theme
 * - Apply theme to DOM via data attribute
 * - Initialize theme from localStorage or default to dark
 *
 * @module ThemeManager
 */
const ThemeManager = (() => {
    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // App state reference (injected during init)
        appState: null,
        config: null,

        // Callbacks (injected during init)
        onThemeChange: null
    };

    // ========================================
    // THEME APPLICATION
    // ========================================

    /**
     * Sets the theme for the application
     * Updates DOM attribute and localStorage
     *
     * @param {string} theme - Theme to apply ('dark' or 'light')
     */
    function setTheme(theme) {
        // Removed or invalid saved themes fall back to Dark.
        theme = theme === 'light' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', theme);

        // Save theme preference to localStorage
        Utils.SafeStorage.setItem('theme', theme);
    }

    /** Returns the map style URL for a Dark or Light theme. */
    function _styleUrlFor(theme) {
        return theme === 'light'
            ? state.config.MAP_STYLE_LIGHT
            : state.config.MAP_STYLE_DARK;
    }

    /** Applies the selected theme to the UI and map. */
    function applyThemeChange(theme) {
        const oldTheme = getCurrentTheme();
        setTheme(theme);
        const currentTheme = getCurrentTheme();
        if (currentTheme === oldTheme) return;

        const map = state.appState && state.appState.map;
        if (map) map.setStyle(_styleUrlFor(currentTheme));
        if (state.onThemeChange) state.onThemeChange(currentTheme);
    }

    /** Loads the map-label font before MapLibre rasterizes its glyph atlas. */
    async function loadMapFont() {
        if (!(document.fonts && document.fonts.load)) return;
        try {
            await document.fonts.load('400 14px "Inter Regular"');
        } catch (e) { /* fall back to the stack's next font */ }
    }

    /**
     * Initializes theme from localStorage or defaults to dark
     * Should be called during app startup before map initialization
     */
    function initTheme() {
        const savedTheme = Utils.SafeStorage.getItem('theme') || 'dark';
        setTheme(savedTheme);
        Utils.SafeStorage.removeItem('protoFlags');
    }

    /**
     * Gets the MapLibre style URL for the current theme
     * Used during map initialization to load correct style
     *
     * @returns {string} Style URL for current theme
     */
    function getStyleUrlForCurrentTheme() {
        return _styleUrlFor(getCurrentTheme());
    }

    // ========================================
    // QUERY FUNCTIONS
    // ========================================

    /**
     * Gets the current theme
     * @returns {string} Current theme ('dark' or 'light')
     */
    function getCurrentTheme() {
        return Utils.getCurrentTheme();
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the ThemeManager module
     * @param {Object} config - Configuration object
     * @param {Object} config.appState - Reference to app state
     * @param {Object} config.config - App configuration with MAP_STYLE_DARK and MAP_STYLE_LIGHT
     * @param {Function} [config.onThemeChange] - Optional callback when theme changes
     */
    function init(config) {
        state.appState = config.appState;
        state.config = config.config;
        state.onThemeChange = config.onThemeChange;
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Initialization
        init,
        initTheme,

        // Theme management
        applyThemeChange,
        loadMapFont,
        getStyleUrlForCurrentTheme,

        // Query functions
        getCurrentTheme
    };
})();
