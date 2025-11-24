/**
 * TagColorManager Module
 *
 * Manages tag color assignments and maintains the mapping between
 * selected tags and their assigned colors from the palette.
 *
 * Features:
 * - Assigns colors from theme-appropriate palette
 * - Tracks selected tags with their colors
 * - Handles color reuse when palette is exhausted
 * - Reassigns colors when theme changes
 * - Provides display order for selected tags
 *
 * @module TagColorManager
 */
const TagColorManager = (() => {
    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // Color palettes (injected during init)
        darkPalette: [],
        lightPalette: [],

        // Selected tags with their assigned colors
        // Array of [tag, color] tuples, maintains selection order
        selectedTagsWithColors: []
    };

    // ========================================
    // UTILITY FUNCTIONS
    // ========================================

    /**
     * Gets the current theme
     * @returns {string} 'dark' or 'light'
     */
    function getCurrentTheme() {
        return document.documentElement.getAttribute('data-theme') || 'dark';
    }

    /**
     * Gets the color palette for the current theme
     * @returns {Array<string>} Array of color hex codes
     */
    function getCurrentPalette() {
        const theme = getCurrentTheme();
        return theme === 'dark' ? state.darkPalette : state.lightPalette;
    }

    /**
     * Gets all currently used colors
     * @returns {Set<string>} Set of color hex codes
     */
    function getUsedColors() {
        return new Set(state.selectedTagsWithColors.map(([tag, color]) => color));
    }

    /**
     * Finds the first unused color in the palette
     * @returns {string|null} Color hex code or null if all colors are used
     */
    function findUnusedColor() {
        const palette = getCurrentPalette();
        const usedColors = getUsedColors();

        return palette.find(color => !usedColors.has(color)) || null;
    }

    /**
     * Gets a color for a new tag assignment
     * Uses first unused color, or wraps around if palette is exhausted
     * @returns {string} Color hex code
     */
    function getNextColor() {
        const palette = getCurrentPalette();

        // Try to find unused color
        const unusedColor = findUnusedColor();
        if (unusedColor) {
            return unusedColor;
        }

        // All colors used, wrap around based on selection count
        const colorIndex = state.selectedTagsWithColors.length % palette.length;
        return palette[colorIndex];
    }

    // ========================================
    // COLOR MANAGEMENT
    // ========================================

    /**
     * Gets the assigned color for a tag
     * @param {string} tag - Tag name
     * @returns {string|null} Color hex code or null if tag is not selected
     */
    function getTagColor(tag) {
        const entry = state.selectedTagsWithColors.find(([t, color]) => t === tag);
        return entry ? entry[1] : null;
    }

    /**
     * Assigns a color to a tag
     * If tag already has a color, does nothing
     * @param {string} tag - Tag name
     * @returns {string} The assigned color
     */
    function assignColorToTag(tag) {
        // Check if already assigned
        const existingColor = getTagColor(tag);
        if (existingColor) {
            return existingColor;
        }

        // Get next available color
        const color = getNextColor();

        // Add to the list
        state.selectedTagsWithColors.push([tag, color]);

        return color;
    }

    /**
     * Removes color assignment from a tag
     * @param {string} tag - Tag name
     * @returns {boolean} True if tag was found and removed, false otherwise
     */
    function unassignColorFromTag(tag) {
        const index = state.selectedTagsWithColors.findIndex(([t, color]) => t === tag);

        if (index > -1) {
            state.selectedTagsWithColors.splice(index, 1);
            return true;
        }

        return false;
    }

    /**
     * Reassigns colors to all selected tags using the current theme's palette
     * Maintains the selection order but updates colors
     * Used when theme changes
     */
    function reassignTagColors() {
        const palette = getCurrentPalette();

        // Reassign colors based on current selection order
        state.selectedTagsWithColors.forEach(([tag, oldColor], index) => {
            const newColor = palette[index % palette.length];
            state.selectedTagsWithColors[index] = [tag, newColor];
        });
    }

    /**
     * Clears all color assignments
     */
    function clearAll() {
        state.selectedTagsWithColors = [];
    }

    // ========================================
    // QUERY FUNCTIONS
    // ========================================

    /**
     * Gets all selected tags in selection order
     * @returns {Array<string>} Array of tag names
     */
    function getSelectedTags() {
        return state.selectedTagsWithColors.map(([tag, color]) => tag);
    }

    /**
     * Gets all selected tags with their colors
     * @returns {Array<[string, string]>} Array of [tag, color] tuples
     */
    function getSelectedTagsWithColors() {
        return [...state.selectedTagsWithColors];
    }

    /**
     * Gets the number of selected tags
     * @returns {number} Count of selected tags
     */
    function getSelectedTagCount() {
        return state.selectedTagsWithColors.length;
    }

    /**
     * Checks if a tag is selected
     * @param {string} tag - Tag name
     * @returns {boolean} True if tag is selected
     */
    function isTagSelected(tag) {
        return state.selectedTagsWithColors.some(([t, color]) => t === tag);
    }

    /**
     * Gets color statistics for debugging/monitoring
     * @returns {Object} Object with color usage stats
     */
    function getColorStats() {
        const palette = getCurrentPalette();
        const usedColors = getUsedColors();

        return {
            theme: getCurrentTheme(),
            paletteSize: palette.length,
            selectedTagCount: state.selectedTagsWithColors.length,
            uniqueColorsUsed: usedColors.size,
            allColorsUsed: usedColors.size >= palette.length
        };
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the TagColorManager module
     * @param {Object} config - Configuration object
     * @param {Array<string>} config.darkPalette - Color palette for dark theme
     * @param {Array<string>} config.lightPalette - Color palette for light theme
     */
    function init(config) {
        state.darkPalette = config.darkPalette || [];
        state.lightPalette = config.lightPalette || [];
        state.selectedTagsWithColors = [];
    }

    /**
     * Resets the manager to initial state
     */
    function reset() {
        state.selectedTagsWithColors = [];
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Initialization
        init,
        reset,

        // Color management
        getTagColor,
        assignColorToTag,
        unassignColorFromTag,
        reassignTagColors,
        clearAll,

        // Query functions
        getSelectedTags,
        getSelectedTagsWithColors,
        getSelectedTagCount,
        isTagSelected,
        getColorStats,

        // Utility (exposed for testing/debugging)
        getCurrentTheme,
        getCurrentPalette
    };
})();
