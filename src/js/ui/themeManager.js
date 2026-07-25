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
        // Unknown names (stale storage after a theme was removed) fall back
        if (!Themes.isKnown(theme)) theme = 'dark';
        const root = document.documentElement;
        root.setAttribute('data-theme', theme);
        // Base axis for unconverted binary styling (icon inversion, hover
        // lighten/darken direction) — prototype themes inherit their base's.
        root.setAttribute('data-theme-base', Themes.baseOf(theme));

        // Save theme preference to localStorage
        Utils.SafeStorage.setItem('theme', theme);
    }

    /**
     * Style JSON URL for a theme: its own registry mapStyle, else the
     * built-in style matching its base.
     * @param {string} theme - Theme name
     * @returns {string} Style URL
     */
    function _styleUrlFor(theme) {
        const def = Themes.resolve(theme);
        if (def.mapStyle) return def.mapStyle;
        return Themes.baseOf(theme) === 'dark'
            ? state.config.MAP_STYLE_DARK
            : state.config.MAP_STYLE_LIGHT;
    }

    /**
     * Applies theme change including map style updates and callbacks.
     * This is the main method called when the user changes theme (settings
     * modal or prototype picker). Async because themes with a custom webfont
     * await it before map glyphs rasterize; callers may fire-and-forget.
     *
     * @param {string} theme - Theme name from the Themes registry
     */
    async function applyThemeChange(theme) {
        const oldTheme = getCurrentTheme();

        // Update theme in DOM and localStorage
        setTheme(theme);

        // The theme's webfonts must be resolvable before TinySDF
        // rasterizes map glyphs, else the atlas bakes fallback glyphs.
        await loadThemeFonts(theme);

        const map = state.appState && state.appState.map;
        if (map) {
            const newUrl = _styleUrlFor(theme);
            if (newUrl !== _styleUrlFor(oldTheme)) {
                // Full style swap — MapManager's style.load/idle restore path
                // re-creates layers, re-rasterizes emoji under the new theme,
                // and re-applies theme layer properties.
                map.setStyle(newUrl);
            } else {
                // Same style JSON (e.g. two themes sharing a base): never
                // call setStyle — just re-render what the theme changes.
                if (Themes.transformKey(theme) !== Themes.transformKey(oldTheme)) {
                    MapManager.reloadEmojiImages(state.appState.locationsByLatLng || {});
                }
                MapManager.applyThemeToLayers();
            }
        }

        // Call optional callback for additional theme change handling
        if (state.onThemeChange) {
            state.onThemeChange(theme);
        }
    }

    /**
     * Loads the webfonts a theme needs on the map BEFORE TinySDF bakes its
     * glyph atlas: the map-label family (an @font-face alias named after the
     * MapLibre fontstack, e.g. "Inter Regular" — see fonts.css) plus any
     * theme-declared uiFontLoad. Baking happens once per style load; if the
     * font isn't loaded yet, labels rasterize in the fallback font until the
     * next style change.
     *
     * @param {string} theme - Theme name from the Themes registry
     */
    async function loadThemeFonts(theme) {
        if (!(document.fonts && document.fonts.load)) return;
        const def = Themes.resolve(theme);
        const mapFont = (def.mapLabelFont && def.mapLabelFont[0]) || 'Inter Regular';
        const loads = [document.fonts.load('400 14px "' + mapFont + '"')];
        if (def.uiFontLoad) loads.push(document.fonts.load(def.uiFontLoad));
        try {
            await Promise.all(loads);
        } catch (e) { /* fall back to the stack's next font */ }
    }

    /**
     * Initializes theme from localStorage or defaults to dark
     * Should be called during app startup before map initialization
     */
    function initTheme() {
        const savedTheme = Utils.SafeStorage.getItem('theme') || 'dark';
        setTheme(savedTheme);
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
        loadThemeFonts,
        getStyleUrlForCurrentTheme,

        // Query functions
        getCurrentTheme
    };
})();
