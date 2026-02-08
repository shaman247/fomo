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

        // Current theme ('dark' or 'light')
        currentTheme: 'dark',

        // Callbacks (injected during init)
        onThemeChange: null
    };

    // ========================================
    // THEME APPLICATION
    // ========================================

    /**
     * Sets the theme for the application
     * Updates DOM attribute, localStorage, and optionally updates icon visibility
     *
     * @param {string} theme - Theme to apply ('dark' or 'light')
     * @param {HTMLElement} [moonIcon=null] - Optional moon icon element to toggle
     * @param {HTMLElement} [sunIcon=null] - Optional sun icon element to toggle
     */
    function setTheme(theme, moonIcon = null, sunIcon = null) {
        const root = document.documentElement;
        root.setAttribute('data-theme', theme);
        state.currentTheme = theme;

        // Update icon visibility if icons provided
        if (moonIcon && sunIcon) {
            if (theme === 'light') {
                moonIcon.style.display = 'none';
                sunIcon.style.display = 'block';
            } else {
                moonIcon.style.display = 'block';
                sunIcon.style.display = 'none';
            }
        }

        // Save theme preference to localStorage
        localStorage.setItem('theme', theme);
    }

    /**
     * Applies theme change including map style updates and callbacks
     * This is the main method called when user changes theme in settings
     *
     * @param {string} theme - Theme to apply ('dark' or 'light')
     */
    function applyThemeChange(theme) {
        // Update theme in DOM and localStorage
        setTheme(theme, null, null);

        // Update MapLibre style based on theme
        if (state.appState && state.appState.map) {
            const styleUrl = theme === 'dark'
                ? state.config.MAP_STYLE_DARK
                : state.config.MAP_STYLE_LIGHT;
            // Set the new style directly on the MapLibre map
            state.appState.map.setStyle(styleUrl);
        }

        // Call optional callback for additional theme change handling
        if (state.onThemeChange) {
            state.onThemeChange(theme);
        }
    }

    /**
     * Initializes theme from localStorage or defaults to dark
     * Should be called during app startup before map initialization
     */
    function initTheme() {
        const savedTheme = localStorage.getItem('theme') || 'dark';
        setTheme(savedTheme, null, null);
    }

    /**
     * Gets the MapLibre style URL for the current theme
     * Used during map initialization to load correct style
     *
     * @returns {string} Style URL for current theme
     */
    function getStyleUrlForCurrentTheme() {
        const currentTheme = getCurrentTheme();
        return currentTheme === 'dark'
            ? state.config.MAP_STYLE_DARK
            : state.config.MAP_STYLE_LIGHT;
    }

    // ========================================
    // QUERY FUNCTIONS
    // ========================================

    /**
     * Gets the current theme
     * @returns {string} Current theme ('dark' or 'light')
     */
    function getCurrentTheme() {
        // Always read from DOM as source of truth
        return document.documentElement.getAttribute('data-theme') || 'dark';
    }

    /**
     * Checks if dark theme is currently active
     * @returns {boolean} True if dark theme is active
     */
    function isDarkTheme() {
        return getCurrentTheme() === 'dark';
    }

    /**
     * Checks if light theme is currently active
     * @returns {boolean} True if light theme is active
     */
    function isLightTheme() {
        return getCurrentTheme() === 'light';
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the ThemeManager module
     * @param {Object} config - Configuration object
     * @param {Object} config.appState - Reference to app state
     * @param {Object} config.config - App configuration with MAP_TILE_URL_DARK and MAP_TILE_URL_LIGHT
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
        setTheme,
        applyThemeChange,
        getStyleUrlForCurrentTheme,

        // Query functions
        getCurrentTheme,
        isDarkTheme,
        isLightTheme
    };
})();
