/**
 * RelatedTagsManager Module
 *
 * Manages related tag relationships and weights. Provides tag relationship
 * data that TagColorManager uses to automatically select related tags
 * when a user explicitly selects a tag.
 *
 * Features:
 * - Loads related tag data from JSON file
 * - Provides related tags and weights for a given tag
 * - Maintains tag relationship mappings
 *
 * Note: Tag enrichment logic has been moved to TagColorManager, which now
 * automatically adds related tags with their weights when a tag is selected.
 *
 * @module RelatedTagsManager
 */
const RelatedTagsManager = (() => {
    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // Map of tag -> array of [relatedTag, weight] tuples
        relatedTagsMap: new Map(),

        // Whether the module has been initialized
        isInitialized: false
    };

    // ========================================
    // INITIALIZATION
    // ========================================

    /**
     * Loads related tags data from JSON file
     * @param {string} url - URL to the related tags JSON file
     * @returns {Promise<void>}
     */
    async function loadRelatedTags(url) {
        try {
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`Failed to load related tags: ${response.statusText}`);
            }

            const data = await response.json();

            // Convert JSON object to Map
            state.relatedTagsMap.clear();
            for (const [tag, relatedTags] of Object.entries(data)) {
                // relatedTags is an array of [tagName, weight] tuples
                state.relatedTagsMap.set(tag, relatedTags);
            }

            state.isInitialized = true;
        } catch (error) {
            console.error('Error loading related tags:', error);
            state.isInitialized = false;
        }
    }

    // ========================================
    // TAG QUERIES
    // ========================================

    /**
     * Gets related tags for a specific tag
     * Used by TagColorManager to add implicit tags when a tag is selected
     * @param {string} tag - Tag name
     * @returns {Array<[string, number]>} Array of [relatedTag, weight] tuples, or empty array
     */
    function getRelatedTags(tag) {
        if (!state.isInitialized) {
            return [];
        }
        return state.relatedTagsMap.get(tag) || [];
    }

    /**
     * Checks if a tag has related tags
     * @param {string} tag - Tag name
     * @returns {boolean} True if tag has related tags
     */
    function hasRelatedTags(tag) {
        if (!state.isInitialized) {
            return false;
        }
        return state.relatedTagsMap.has(tag);
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the RelatedTagsManager module
     * @param {Object} config - Configuration object
     * @param {string} config.relatedTagsUrl - URL to the related tags JSON file
     * @returns {Promise<void>}
     */
    async function init(config) {
        if (config.relatedTagsUrl) {
            await loadRelatedTags(config.relatedTagsUrl);
        }
    }

    /**
     * Resets the manager to initial state
     */
    function reset() {
        state.relatedTagsMap.clear();
        state.isInitialized = false;
    }

    /**
     * Gets the initialization status
     * @returns {boolean} True if initialized
     */
    function isInitialized() {
        return state.isInitialized;
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Initialization
        init,
        reset,
        isInitialized,

        // Tag operations
        getRelatedTags,
        hasRelatedTags
    };
})();
