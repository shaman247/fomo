/**
 * TagColorManager Module
 *
 * Manages tag color assignments and maintains the mapping between
 * selected tags and their assigned colors from the palette.
 *
 * Features:
 * - Assigns colors from theme-appropriate palette
 * - Tracks selected tags with their colors and weights
 * - Handles color reuse when palette is exhausted
 * - Reassigns colors when theme changes
 * - Provides display order for selected tags
 * - Manages both explicit selections (weight=1.0) and implicit/related tags (weight<1.0)
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

        // Selected tags with their assigned colors and weights
        // Array of [tag, color, weight] tuples, maintains selection order
        // weight=1.0 for explicitly selected tags, weight<1.0 for related/implicit tags
        selectedTagsWithColors: [],

        // Set of implicit tags that have been manually excluded by the user
        excludedImplicitTags: new Set(),

        // Callbacks
        getRelatedTags: null,  // Callback to get related tags for a given tag
        onImplicitTagsChanged: null  // Callback when implicit tags are added/removed
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
     * Gets all currently used colors (by explicitly selected tags only)
     * @returns {Set<string>} Set of color hex codes
     */
    function getUsedColors() {
        return new Set(
            state.selectedTagsWithColors
                .filter(([, , weight]) => weight === 1.0)
                .map(([, color]) => color)
        );
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
     * Gets the count of explicitly selected tags (weight=1.0)
     * @returns {number} Count of explicitly selected tags
     */
    function getExplicitTagCount() {
        return state.selectedTagsWithColors.filter(([, , weight]) => weight === 1.0).length;
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

        // All colors used, wrap around based on explicit selection count
        const colorIndex = getExplicitTagCount() % palette.length;
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
        const entry = state.selectedTagsWithColors.find(([t]) => t === tag);
        return entry ? entry[1] : null;
    }

    /**
     * Gets the weight for a tag
     * @param {string} tag - Tag name
     * @returns {number} Weight (1.0 for explicit, <1.0 for implicit, 0 if not selected)
     */
    function getTagWeight(tag) {
        const entry = state.selectedTagsWithColors.find(([t]) => t === tag);
        return entry ? entry[2] : 0;
    }

    /**
     * Checks if a tag is implicitly selected (weight < 1.0)
     * @param {string} tag - Tag name
     * @returns {boolean} True if tag is implicitly selected
     */
    function isImplicitlySelected(tag) {
        const weight = getTagWeight(tag);
        return weight > 0 && weight < 1.0;
    }

    /**
     * Assigns a color to a tag (explicit selection with weight=1.0)
     * Also adds related tags with their respective weights
     * If tag already has a color, does nothing
     * @param {string} tag - Tag name
     * @returns {string} The assigned color
     */
    function assignColorToTag(tag) {
        // Check if already assigned as explicit
        const existingEntry = state.selectedTagsWithColors.find(([t]) => t === tag);
        if (existingEntry && existingEntry[2] === 1.0) {
            return existingEntry[1];
        }

        // Get next available color
        const color = getNextColor();

        // If tag was implicitly selected, upgrade to explicit
        if (existingEntry) {
            existingEntry[1] = color;
            existingEntry[2] = 1.0;
        } else {
            // Add to the list as explicitly selected
            state.selectedTagsWithColors.push([tag, color, 1.0]);
        }

        // Add related tags if callback is available
        if (state.getRelatedTags) {
            const relatedTags = state.getRelatedTags(tag);
            for (const [relatedTag, weight] of relatedTags) {
                // Check if related tag already exists
                const existingRelated = state.selectedTagsWithColors.find(([t]) => t === relatedTag);
                if (!existingRelated) {
                    // Add related tag with the parent's color and its weight
                    state.selectedTagsWithColors.push([relatedTag, color, weight]);
                } else if (existingRelated[2] < 1.0 && weight > existingRelated[2]) {
                    // Update weight if higher (keep existing color)
                    existingRelated[2] = weight;
                }
                // If already explicit (weight=1.0), don't change anything
            }
        }

        return color;
    }

    /**
     * Removes color assignment from a tag
     * Also removes related tags that are no longer needed
     * @param {string} tag - Tag name
     * @returns {boolean} True if tag was found and removed, false otherwise
     */
    function unassignColorFromTag(tag) {
        const index = state.selectedTagsWithColors.findIndex(([t]) => t === tag);

        if (index > -1) {
            state.selectedTagsWithColors.splice(index, 1);

            // Remove orphaned implicit tags (those not related to any remaining explicit tags)
            rebuildImplicitTags();

            return true;
        }

        return false;
    }

    /**
     * Rebuilds implicit tags based on currently explicit tags
     * Removes orphaned implicit tags and updates weights
     * Respects manually excluded implicit tags
     */
    function rebuildImplicitTags() {
        if (!state.getRelatedTags) return;

        // Track which implicit tags existed before
        const oldImplicitTags = new Set(
            state.selectedTagsWithColors
                .filter(([, , weight]) => weight < 1.0)
                .map(([tag]) => tag)
        );

        // Get all explicitly selected tags
        const explicitTags = state.selectedTagsWithColors
            .filter(([, , weight]) => weight === 1.0)
            .map(([tag, color]) => ({ tag, color }));

        // Build a map of which implicit tags should exist and with what weight/color
        const implicitTagsMap = new Map();

        for (const { tag, color } of explicitTags) {
            const relatedTags = state.getRelatedTags(tag);
            for (const [relatedTag, weight] of relatedTags) {
                // Skip if this related tag is explicitly selected
                if (explicitTags.some(e => e.tag === relatedTag)) continue;

                // Skip if this related tag has been manually excluded
                if (state.excludedImplicitTags.has(relatedTag)) continue;

                const existing = implicitTagsMap.get(relatedTag);
                if (!existing || weight > existing.weight) {
                    implicitTagsMap.set(relatedTag, { color, weight });
                }
            }
        }

        // Track new implicit tags
        const newImplicitTags = new Set(implicitTagsMap.keys());

        // Find removed and added implicit tags
        const removedImplicitTags = [...oldImplicitTags].filter(tag => !newImplicitTags.has(tag));
        const addedImplicitTags = [...newImplicitTags].filter(tag => !oldImplicitTags.has(tag));

        // Remove all implicit tags from current list
        state.selectedTagsWithColors = state.selectedTagsWithColors.filter(([, , weight]) => weight === 1.0);

        // Add back the implicit tags with correct weights
        for (const [tag, { color, weight }] of implicitTagsMap) {
            state.selectedTagsWithColors.push([tag, color, weight]);
        }

        // Notify about changes if there were any
        if ((removedImplicitTags.length > 0 || addedImplicitTags.length > 0) && state.onImplicitTagsChanged) {
            state.onImplicitTagsChanged(addedImplicitTags, removedImplicitTags);
        }
    }

    /**
     * Excludes an implicit tag from the related tags list
     * The tag will not appear as an implicit selection until explicit tags change
     * @param {string} tag - Tag to exclude
     * @returns {boolean} True if the tag was excluded
     */
    function excludeImplicitTag(tag) {
        // Only exclude if it's currently an implicit tag
        const entry = state.selectedTagsWithColors.find(([t]) => t === tag);
        if (!entry || entry[2] === 1.0) {
            return false; // Not an implicit tag
        }

        state.excludedImplicitTags.add(tag);

        // Remove from current selections
        const index = state.selectedTagsWithColors.findIndex(([t]) => t === tag);
        if (index !== -1) {
            state.selectedTagsWithColors.splice(index, 1);
        }

        return true;
    }

    /**
     * Clears the excluded implicit tags list
     * Called when explicit tag selection changes significantly
     */
    function clearExcludedImplicitTags() {
        state.excludedImplicitTags.clear();
    }

    /**
     * Reassigns colors to all selected tags using the current theme's palette
     * Maintains the selection order but updates colors
     * Used when theme changes
     */
    function reassignTagColors() {
        const palette = getCurrentPalette();

        // First, reassign colors for explicit tags
        let colorIndex = 0;
        const explicitColorMap = new Map();

        state.selectedTagsWithColors.forEach((entry) => {
            const [tag, , weight] = entry;
            if (weight === 1.0) {
                const newColor = palette[colorIndex % palette.length];
                entry[1] = newColor;
                explicitColorMap.set(tag, newColor);
                colorIndex++;
            }
        });

        // Then update implicit tags to use their parent's new color
        if (state.getRelatedTags) {
            state.selectedTagsWithColors.forEach((entry) => {
                const [tag, , weight] = entry;
                if (weight < 1.0) {
                    // Find which explicit tag this is related to
                    for (const [explicitTag, color] of explicitColorMap) {
                        const relatedTags = state.getRelatedTags(explicitTag);
                        if (relatedTags.some(([rt]) => rt === tag)) {
                            entry[1] = color;
                            break;
                        }
                    }
                }
            });
        }
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
     * Gets all explicitly selected tags in selection order (weight=1.0)
     * @returns {Array<string>} Array of tag names
     */
    function getSelectedTags() {
        return state.selectedTagsWithColors
            .filter(([, , weight]) => weight === 1.0)
            .map(([tag]) => tag);
    }

    /**
     * Gets all tags (explicit and implicit) with their colors and weights
     * @returns {Array<[string, string, number]>} Array of [tag, color, weight] tuples
     */
    function getSelectedTagsWithColors() {
        return [...state.selectedTagsWithColors];
    }

    /**
     * Gets all tag names (explicit and implicit)
     * @returns {Array<string>} Array of all tag names
     */
    function getAllSelectedTagNames() {
        return state.selectedTagsWithColors.map(([tag]) => tag);
    }

    /**
     * Gets the number of explicitly selected tags
     * @returns {number} Count of explicitly selected tags
     */
    function getSelectedTagCount() {
        return state.selectedTagsWithColors.filter(([, , weight]) => weight === 1.0).length;
    }

    /**
     * Checks if a tag is selected (explicit or implicit)
     * @param {string} tag - Tag name
     * @returns {boolean} True if tag is selected
     */
    function isTagSelected(tag) {
        return state.selectedTagsWithColors.some(([t]) => t === tag);
    }

    /**
     * Checks if a tag is explicitly selected (weight=1.0)
     * @param {string} tag - Tag name
     * @returns {boolean} True if tag is explicitly selected
     */
    function isExplicitlySelected(tag) {
        const entry = state.selectedTagsWithColors.find(([t]) => t === tag);
        return entry ? entry[2] === 1.0 : false;
    }

    /**
     * Gets color statistics for debugging/monitoring
     * @returns {Object} Object with color usage stats
     */
    function getColorStats() {
        const palette = getCurrentPalette();
        const usedColors = getUsedColors();
        const explicitCount = getExplicitTagCount();
        const implicitCount = state.selectedTagsWithColors.length - explicitCount;

        return {
            theme: getCurrentTheme(),
            paletteSize: palette.length,
            explicitTagCount: explicitCount,
            implicitTagCount: implicitCount,
            totalTagCount: state.selectedTagsWithColors.length,
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
     * @param {Function} [config.getRelatedTags] - Callback to get related tags for a tag
     * @param {Function} [config.onImplicitTagsChanged] - Callback when implicit tags change (addedTags, removedTags)
     */
    function init(config) {
        state.darkPalette = config.darkPalette || [];
        state.lightPalette = config.lightPalette || [];
        state.selectedTagsWithColors = [];
        state.getRelatedTags = config.getRelatedTags || null;
        state.onImplicitTagsChanged = config.onImplicitTagsChanged || null;
    }

    /**
     * Sets the callback for getting related tags
     * Can be called after init if RelatedTagsManager is initialized later
     * @param {Function} callback - Function that takes a tag and returns [[relatedTag, weight], ...]
     */
    function setRelatedTagsCallback(callback) {
        state.getRelatedTags = callback;
    }

    /**
     * Resets the manager to initial state
     */
    function reset() {
        state.selectedTagsWithColors = [];
        state.excludedImplicitTags.clear();
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Initialization
        init,
        reset,
        setRelatedTagsCallback,

        // Color management
        getTagColor,
        getTagWeight,
        assignColorToTag,
        unassignColorFromTag,
        reassignTagColors,
        clearAll,

        // Implicit tag management
        excludeImplicitTag,
        clearExcludedImplicitTags,

        // Query functions
        getSelectedTags,
        getSelectedTagsWithColors,
        getAllSelectedTagNames,
        getSelectedTagCount,
        isTagSelected,
        isExplicitlySelected,
        isImplicitlySelected,
        getColorStats,

        // Utility (exposed for testing/debugging)
        getCurrentTheme,
        getCurrentPalette
    };
})();
