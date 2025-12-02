/**
 * SelectedTagsDisplay Module
 *
 * Manages the display of selected tags above the search input.
 * Shows explicitly selected tags with an optional toggle to include/exclude
 * related (implicit) tags from search and filtering.
 *
 * Features:
 * - Displays explicitly selected tags as interactive buttons
 * - Provides add/remove toggle for related tags
 * - Controls whether implicit tags affect search and map filtering
 * - Coordinates with TagColorManager for tag data
 * - Triggers filter updates when related tags toggle changes
 *
 * @module SelectedTagsDisplay
 */
const SelectedTagsDisplay = (() => {
    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // DOM element
        containerDOM: null,

        // Whether related/implicit tags are included in search and filtering
        includeRelatedTags: false,

        // Callbacks
        getSelectedTagsWithColors: null,
        createInteractiveTagButton: null,
        onRelatedTagsToggle: null,
        setTagState: null  // Callback to set tag state (for IMPLICIT/UNSELECTED)
    };

    // ========================================
    // RENDERING
    // ========================================

    /**
     * Updates the display of selected tags with interactive buttons
     * Shows explicit tags, with an "add/remove related tags" button to toggle
     * implicit tags in search and filtering
     */
    function render() {
        if (!state.containerDOM) return;

        // Get all tags with colors (explicit and implicit)
        const allTagsWithColors = state.getSelectedTagsWithColors
            ? state.getSelectedTagsWithColors()
            : [];

        // Separate explicit (weight=1.0) and implicit (weight<1.0) tags
        const explicitTags = allTagsWithColors
            .filter(([, , weight]) => weight === 1.0)
            .map(([tag]) => tag);
        const implicitTags = allTagsWithColors
            .filter(([, , weight]) => weight < 1.0)
            .map(([tag]) => tag);

        if (explicitTags.length === 0 && implicitTags.length === 0) {
            state.containerDOM.innerHTML = '';
            state.containerDOM.style.display = 'none';
            state.includeRelatedTags = false;
            return;
        }

        state.containerDOM.style.display = 'flex';
        state.containerDOM.innerHTML = '';

        // Add explicit tags
        explicitTags.forEach(tag => {
            if (state.createInteractiveTagButton) {
                const tagButton = state.createInteractiveTagButton(tag);
                state.containerDOM.appendChild(tagButton);
            }
        });

        // If there are implicit tags, add toggle button
        if (implicitTags.length > 0) {
            if (state.includeRelatedTags) {
                // Add "remove related tags" button (styled with orange background)
                const removeBtn = document.createElement('button');
                removeBtn.className = 'tag-button state-unselected state-cycle-button remove-related-tags-button related-tags-active';
                removeBtn.textContent = '−';
                removeBtn.setAttribute('title', 'Exclude related tags');
                removeBtn.setAttribute('aria-label', 'Exclude related tags');
                removeBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    state.includeRelatedTags = false;
                    // Set all implicit tags to UNSELECTED
                    if (state.setTagState) {
                        implicitTags.forEach(tag => {
                            state.setTagState(tag, 'unselected');
                        });
                    }
                    render();
                    if (state.onRelatedTagsToggle) {
                        state.onRelatedTagsToggle(false);
                    }
                });
                state.containerDOM.appendChild(removeBtn);
            } else {
                // Add "add related tags" button
                const addBtn = document.createElement('button');
                addBtn.className = 'tag-button state-unselected state-cycle-button add-related-tags-button';
                addBtn.textContent = '+';
                addBtn.setAttribute('title', `Include related tags`);
                addBtn.setAttribute('aria-label', `Include related tags`);
                addBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    state.includeRelatedTags = true;
                    // Set all implicit tags to IMPLICIT state
                    if (state.setTagState) {
                        implicitTags.forEach(tag => {
                            state.setTagState(tag, 'implicit');
                        });
                    }
                    render();
                    if (state.onRelatedTagsToggle) {
                        state.onRelatedTagsToggle(true);
                    }
                });
                state.containerDOM.appendChild(addBtn);
            }
        } else {
            // Reset state if no implicit tags
            state.includeRelatedTags = false;
        }
    }

    // ========================================
    // QUERY FUNCTIONS
    // ========================================

    /**
     * Gets whether related tags are currently included in search/filtering
     * @returns {boolean} True if related tags are included
     */
    function isIncludingRelatedTags() {
        return state.includeRelatedTags;
    }

    /**
     * Sets whether related tags should be included in search/filtering
     * @param {boolean} include - Whether to include related tags
     * @param {boolean} [triggerCallback=true] - Whether to trigger the toggle callback
     */
    function setIncludeRelatedTags(include, triggerCallback = true) {
        if (state.includeRelatedTags !== include) {
            state.includeRelatedTags = include;
            render();
            if (triggerCallback && state.onRelatedTagsToggle) {
                state.onRelatedTagsToggle(include);
            }
        }
    }

    /**
     * Gets the selected tags based on current include state
     * Returns only explicit tags when related tags are not included,
     * or all tags when related tags are included
     * @returns {Array<string>} Array of tag names
     */
    function getEffectiveSelectedTags() {
        const allTagsWithColors = state.getSelectedTagsWithColors
            ? state.getSelectedTagsWithColors()
            : [];

        if (state.includeRelatedTags) {
            return allTagsWithColors.map(([tag]) => tag);
        } else {
            return allTagsWithColors
                .filter(([, , weight]) => weight === 1.0)
                .map(([tag]) => tag);
        }
    }

    /**
     * Gets the selected tags with colors based on current include state
     * @returns {Array<[string, string, number]>} Array of [tag, color, weight] tuples
     */
    function getEffectiveSelectedTagsWithColors() {
        const allTagsWithColors = state.getSelectedTagsWithColors
            ? state.getSelectedTagsWithColors()
            : [];

        if (state.includeRelatedTags) {
            return allTagsWithColors;
        } else {
            return allTagsWithColors.filter(([, , weight]) => weight === 1.0);
        }
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the SelectedTagsDisplay module
     * @param {Object} config - Configuration object
     * @param {HTMLElement} config.containerDOM - Container element for the display
     * @param {Function} config.getSelectedTagsWithColors - Callback to get [tag, color, weight] tuples
     * @param {Function} config.createInteractiveTagButton - Callback to create tag buttons
     * @param {Function} config.onRelatedTagsToggle - Callback when related tags toggle changes
     * @param {Function} config.setTagState - Callback to set tag state
     */
    function init(config) {
        state.containerDOM = config.containerDOM;
        state.getSelectedTagsWithColors = config.getSelectedTagsWithColors;
        state.createInteractiveTagButton = config.createInteractiveTagButton;
        state.onRelatedTagsToggle = config.onRelatedTagsToggle;
        state.setTagState = config.setTagState;
        state.includeRelatedTags = false;
    }

    /**
     * Resets the module state
     */
    function reset() {
        state.includeRelatedTags = false;
        if (state.containerDOM) {
            state.containerDOM.innerHTML = '';
            state.containerDOM.style.display = 'none';
        }
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Initialization
        init,
        reset,

        // Rendering
        render,

        // State management
        isIncludingRelatedTags,
        setIncludeRelatedTags,

        // Query functions
        getEffectiveSelectedTags,
        getEffectiveSelectedTagsWithColors
    };
})();
