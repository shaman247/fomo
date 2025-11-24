/**
 * EmojiManager Module
 *
 * Manages emoji font loading, switching, and re-rendering for the application.
 * Handles the Noto Color Emoji font as an alternative to system emoji.
 *
 * Features:
 * - Load and apply Noto Color Emoji font asynchronously
 * - Switch between system and Noto emoji fonts
 * - Force re-render of emoji elements when font changes
 * - Refresh map markers to display new emoji font
 * - Show loading status for font loading
 * - Persist emoji font preference in localStorage
 *
 * @module EmojiManager
 */
const EmojiManager = (() => {
    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // App state reference (injected during init)
        appState: null,

        // Current emoji font ('system' or 'noto')
        currentFont: 'system'
    };

    // ========================================
    // FONT APPLICATION
    // ========================================

    /**
     * Applies the specified emoji font
     * Handles async loading for Noto font with status updates
     *
     * @param {string} emojiFont - Font to apply ('system' or 'noto')
     * @param {HTMLElement} [statusElement=null] - Optional element to show loading status
     */
    function applyEmojiFont(emojiFont, statusElement = null) {
        if (emojiFont === 'noto') {
            // Apply the class immediately (non-blocking)
            document.body.classList.add('use-noto-emoji');
            state.currentFont = 'noto';

            // Show loading status
            if (statusElement) {
                statusElement.textContent = 'Loading...';
                statusElement.className = 'setting-status loading';
            }

            // Load the font asynchronously in the background
            const loadFont = () => {
                document.fonts.load('1em "Noto Color Emoji"').then(() => {
                    forceEmojiRerender();
                    console.log('Noto Color Emoji font loaded and applied');

                    // Show success status briefly, then hide
                    if (statusElement) {
                        statusElement.textContent = 'Loaded';
                        statusElement.className = 'setting-status loaded';
                        setTimeout(() => {
                            statusElement.textContent = '';
                            statusElement.className = 'setting-status';
                        }, 2000);
                    }
                }).catch(() => {
                    setTimeout(() => forceEmojiRerender(), Constants.UI.EMOJI_RERENDER_DELAY_MS);
                    console.log('Noto Color Emoji font applied (with fallback)');

                    // Clear status on error
                    if (statusElement) {
                        statusElement.textContent = '';
                        statusElement.className = 'setting-status';
                    }
                });
            };

            if (document.fonts) {
                // Use requestIdleCallback to defer font loading
                if (window.requestIdleCallback) {
                    window.requestIdleCallback(loadFont);
                } else {
                    // Fallback if requestIdleCallback is not supported
                    setTimeout(loadFont, 0);
                }
            } else {
                // Browser doesn't support Font Loading API
                setTimeout(() => {
                    forceEmojiRerender();
                    if (statusElement) {
                        statusElement.textContent = '';
                        statusElement.className = 'setting-status';
                    }
                }, Constants.UI.EMOJI_RERENDER_DELAY_MS);
            }
        } else {
            // Remove Noto emoji class to use system default
            document.body.classList.remove('use-noto-emoji');
            state.currentFont = 'system';

            // Force re-render to apply system emoji
            forceEmojiRerender();

            // Clear status
            if (statusElement) {
                statusElement.textContent = '';
                statusElement.className = 'setting-status';
            }
        }

        // Save preference to localStorage
        localStorage.setItem('emojiFont', emojiFont);
    }

    /**
     * Initializes emoji font from localStorage
     * Called during app startup
     */
    function initEmojiFont() {
        // Initialize emoji font from localStorage or default to system
        const savedEmojiFont = localStorage.getItem('emojiFont') || 'system';
        applyEmojiFont(savedEmojiFont);
    }

    /**
     * Updates emoji font to Noto (convenience method)
     * Used for the "noto" search term Easter egg
     */
    function updateToNotoFont() {
        if (state.currentFont !== 'noto') {
            document.body.classList.add('use-noto-emoji');
            state.currentFont = 'noto';
            console.log('Noto Color Emoji font enabled - loading...');

            // Force re-render of all emoji elements after font loads
            if (document.fonts) {
                document.fonts.load('1em "Noto Color Emoji"').then(() => {
                    forceEmojiRerender();
                    console.log('Noto Color Emoji font loaded and applied');
                }).catch(() => {
                    setTimeout(() => forceEmojiRerender(), Constants.UI.EMOJI_RERENDER_DELAY_MS);
                    console.log('Noto Color Emoji font applied (with fallback)');
                });
            } else {
                setTimeout(() => forceEmojiRerender(), Constants.UI.EMOJI_RERENDER_DELAY_MS);
            }

            // Save preference
            localStorage.setItem('emojiFont', 'noto');
        }
    }

    // ========================================
    // EMOJI RE-RENDERING
    // ========================================

    /**
     * Forces a re-render of all emoji elements
     * Triggers browser reflow to apply new font
     * Also refreshes map marker icons
     *
     * Optimized to batch DOM operations and minimize forced reflows
     */
    function forceEmojiRerender() {
        const emojiElements = document.querySelectorAll('.marker-emoji, .popup-header-emoji, .popup-event-emoji');

        if (emojiElements.length === 0) return;

        // Batch DOM operations to prevent forced reflows
        // Phase 1: Collect original display values (batch read)
        const originalDisplays = Array.from(emojiElements).map(elem => elem.style.display);

        // Phase 2: Hide all elements (batch write)
        emojiElements.forEach(elem => {
            elem.style.display = 'none';
        });

        // Force a single reflow by reading layout property once
        void emojiElements[0].offsetHeight;

        // Phase 3: Restore all display values (batch write)
        emojiElements.forEach((elem, index) => {
            elem.style.display = originalDisplays[index] || '';
        });

        // Also refresh all markers on the map by re-rendering them
        if (state.appState && state.appState.markersLayer) {
            refreshMapMarkers();
        }
    }

    /**
     * Refreshes all map marker icons
     * Used to update emoji display in markers after font change
     */
    function refreshMapMarkers() {
        if (!state.appState || !state.appState.markersLayer) return;

        // Get all visible markers and their data
        const markersToRefresh = [];
        state.appState.markersLayer.eachLayer(marker => {
            const latLng = marker.getLatLng();
            const locationKey = `${latLng.lat},${latLng.lng}`;
            markersToRefresh.push({
                marker: marker,
                locationKey: locationKey
            });
        });

        // Refresh each marker icon to force emoji re-render
        markersToRefresh.forEach(({marker, locationKey}) => {
            const locationInfo = state.appState.locationsByLatLng[locationKey];
            if (locationInfo) {
                const newIcon = MapManager.createMarkerIcon(locationInfo);
                marker.setIcon(newIcon);
            }
        });
    }

    // ========================================
    // QUERY FUNCTIONS
    // ========================================

    /**
     * Gets the current emoji font
     * @returns {string} Current font ('system' or 'noto')
     */
    function getCurrentFont() {
        return state.currentFont;
    }

    /**
     * Checks if Noto emoji font is currently active
     * @returns {boolean} True if Noto font is active
     */
    function isNotoFontActive() {
        return state.currentFont === 'noto';
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the EmojiManager module
     * @param {Object} config - Configuration object
     * @param {Object} config.appState - Reference to app state
     */
    function init(config) {
        state.appState = config.appState;
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Initialization
        init,
        initEmojiFont,

        // Font management
        applyEmojiFont,
        updateToNotoFont,

        // Re-rendering
        forceEmojiRerender,
        refreshMapMarkers,

        // Query functions
        getCurrentFont,
        isNotoFontActive
    };
})();
