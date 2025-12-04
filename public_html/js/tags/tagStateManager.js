/**
 * TagStateManager Module
 *
 * Manages tag filter states and visual representation for tag buttons.
 * Handles state transitions, color assignments, and tag button creation.
 *
 * Features:
 * - Tag state management (unselected, selected, required, forbidden)
 * - State cycling for left-click and right-click
 * - Visual updates based on tag state
 * - Color assignment coordination
 * - Interactive tag button creation
 *
 * @module TagStateManager
 */
const TagStateManager = (() => {
    // ========================================
    // CONSTANTS
    // ========================================

    /**
     * Available states for tag filters
     * @enum {string}
     */
    const TAG_STATE = {
        UNSELECTED: 'unselected',
        SELECTED: 'selected',
        REQUIRED: 'required',
        FORBIDDEN: 'forbidden',
        IMPLICIT: 'implicit'  // Implicitly selected via related tags
    };

    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // Tag states tracking
        tagStates: {},

        // Provider objects
        colorProvider: null,    // { getTagColor, assignColorToTag, unassignColorFromTag }
        relatedTagsProvider: null, // { isImplicitlySelected, isIncludingRelatedTags }

        // Callbacks
        onFilterChangeCallback: null,

        // Configuration
        defaultMarkerColor: null
    };

    // ========================================
    // STATE TRANSITIONS
    // ========================================

    /**
     * Gets the next tag state for left-click cycling
     * @param {string} currentState - Current tag state
     * @returns {string} Next state in the cycle
     */
    function getNextState(currentState) {
        switch (currentState) {
            case TAG_STATE.SELECTED:
            case TAG_STATE.REQUIRED:
            case TAG_STATE.FORBIDDEN:
                return TAG_STATE.UNSELECTED;
            case TAG_STATE.UNSELECTED:
            case TAG_STATE.IMPLICIT:
                return TAG_STATE.SELECTED;
            default:
                return TAG_STATE.SELECTED;
        }
    }

    /**
     * Gets the next tag state for right-click cycling
     * @param {string} currentState - Current tag state
     * @returns {string} Next state in the cycle
     */
    function getRightClickNextState(currentState) {
        switch (currentState) {
            case TAG_STATE.UNSELECTED:
            case TAG_STATE.IMPLICIT:
                return TAG_STATE.SELECTED;
            case TAG_STATE.SELECTED:
                return TAG_STATE.REQUIRED;
            case TAG_STATE.REQUIRED:
                return TAG_STATE.FORBIDDEN;
            case TAG_STATE.FORBIDDEN:
            default:
                return TAG_STATE.UNSELECTED;
        }
    }

    /**
     * Handles color assignment when tag state changes
     * @param {string} oldState - Previous tag state
     * @param {string} newState - New tag state
     * @param {string} tag - Tag name
     */
    function handleColorAssignment(oldState, newState, tag) {
        const wasUnselected = oldState === TAG_STATE.UNSELECTED || oldState === TAG_STATE.IMPLICIT;
        const isNowActive = newState === TAG_STATE.SELECTED || newState === TAG_STATE.REQUIRED;
        const wasActive = oldState === TAG_STATE.SELECTED || oldState === TAG_STATE.REQUIRED || oldState === TAG_STATE.FORBIDDEN;
        const isNowUnselected = newState === TAG_STATE.UNSELECTED || newState === TAG_STATE.IMPLICIT;

        if (wasUnselected && isNowActive) {
            if (state.colorProvider && state.colorProvider.assignColorToTag) {
                state.colorProvider.assignColorToTag(tag);
            }
        } else if (wasActive && isNowUnselected) {
            if (state.colorProvider && state.colorProvider.unassignColorFromTag) {
                state.colorProvider.unassignColorFromTag(tag);
            }
        }
    }

    // ========================================
    // TAG VISUAL UPDATES
    // ========================================

    /**
     * Updates the visual appearance of a tag button based on its state
     * @param {HTMLElement} buttonElement - The button element to update
     * @param {string} tagValue - The tag value/name
     */
    function updateTagVisuals(buttonElement, tagValue) {
        const tagState = state.tagStates[tagValue] || TAG_STATE.UNSELECTED;
        const tagColor = state.colorProvider && state.colorProvider.getTagColor ? state.colorProvider.getTagColor(tagValue) : null;
        const colorToUse = tagColor || state.defaultMarkerColor;

        buttonElement.className = 'tag-button';

        const applyColor = () => {
            if (Array.isArray(colorToUse)) {
                buttonElement.style.background = `linear-gradient(to bottom, color-mix(in srgb, ${colorToUse[0]} 80%, transparent), color-mix(in srgb, ${colorToUse[1]} 80%, transparent))`;
            } else {
                buttonElement.style.backgroundColor = `color-mix(in srgb, ${colorToUse} 80%, transparent)`;
            }
        };

        switch (tagState) {
            case TAG_STATE.SELECTED:
                buttonElement.classList.add('state-selected');
                buttonElement.setAttribute('aria-pressed', 'true');
                buttonElement.setAttribute('aria-label', `${tagValue}`);
                applyColor();
                break;

            case TAG_STATE.REQUIRED:
                buttonElement.classList.add('state-required');
                buttonElement.setAttribute('aria-pressed', 'true');
                buttonElement.setAttribute('aria-label', `${tagValue}`);
                applyColor();
                break;

            case TAG_STATE.FORBIDDEN:
                buttonElement.classList.add('state-forbidden');
                buttonElement.setAttribute('aria-pressed', 'mixed');
                buttonElement.setAttribute('aria-label', `${tagValue}`);
                break;

            case TAG_STATE.IMPLICIT:
                buttonElement.classList.add('state-implicit');
                buttonElement.setAttribute('aria-pressed', 'mixed');
                buttonElement.setAttribute('aria-label', `${tagValue} (related)`);
                break;

            case TAG_STATE.UNSELECTED:
            default:
                buttonElement.classList.add('state-unselected');
                buttonElement.setAttribute('aria-pressed', 'false');
                buttonElement.setAttribute('aria-label', `${tagValue}`);
                break;
        }

        buttonElement.textContent = tagValue;
    }

    // ========================================
    // TAG BUTTON CREATION
    // ========================================

    /**
     * Creates a tag button with click handlers for state cycling
     * @param {string} tag - Tag name
     * @param {Function} onClick - Click handler
     * @param {Function} onRightClick - Right-click handler
     * @returns {HTMLElement} Button element
     */
    function createTagButtonWithHandlers(tag, onClick, onRightClick) {
        const button = document.createElement('button');
        button.dataset.tag = tag;
        updateTagVisuals(button, tag);

        button.addEventListener('click', (e) => {
            const oldState = state.tagStates[tag] || TAG_STATE.UNSELECTED;
            state.tagStates[tag] = getNextState(oldState);
            const newState = state.tagStates[tag];

            handleColorAssignment(oldState, newState, tag);
            updateTagVisuals(button, tag);

            if (onClick) onClick(e);
        });

        button.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            const oldState = state.tagStates[tag] || TAG_STATE.UNSELECTED;
            state.tagStates[tag] = getRightClickNextState(oldState);
            const newState = state.tagStates[tag];

            handleColorAssignment(oldState, newState, tag);
            updateTagVisuals(button, tag);

            if (onRightClick) onRightClick(e);
        });

        return button;
    }

    /**
     * Creates a tag element for the tag cloud (non-search context)
     * @param {string} tag - Tag name
     * @returns {HTMLElement} Tag button element
     */
    function createTagElement(tag) {
        return createTagButtonWithHandlers(
            tag,
            () => {
                if (state.onFilterChangeCallback) {
                    state.onFilterChangeCallback();
                }
            },
            () => {
                if (state.onFilterChangeCallback) {
                    state.onFilterChangeCallback();
                }
            }
        );
    }

    /**
     * Creates an interactive tag button for search results
     * @param {string} tag - Tag name
     * @returns {HTMLElement} Interactive tag button element
     */
    function createInteractiveTagButton(tag) {
        return createTagButtonWithHandlers(
            tag,
            (e) => {
                if (state.onFilterChangeCallback) {
                    state.onFilterChangeCallback();
                }
            },
            (e) => {
                if (state.onFilterChangeCallback) {
                    state.onFilterChangeCallback();
                }
            }
        );
    }

    /**
     * Creates a button for a search result (location, event, or tag)
     * @param {Object} result - Search result object
     * @param {string} result.type - Type (location, event, or tag)
     * @param {string} result.ref - Reference (tag name or item ID)
     * @param {boolean} [result.isVisible] - Visibility flag
     * @param {string} [result.emoji] - Emoji for display
     * @param {string} [result.displayName] - Display name
     * @param {number} [result.score] - Search score for debug display
     * @param {Function} onSearchResultClick - Callback for non-tag results
     * @param {boolean} [debugMode=false] - Whether to show scores in debug mode
     * @returns {HTMLElement} Button element
     */
    function createSearchResultButton(result, onSearchResultClick, debugMode = false) {
        // For tags, create the interactive button
        if (result.type === 'tag') {
            const button = createInteractiveTagButton(result.ref);
            if (result.isVisible === false) {
                button.classList.add('non-visible-tag');
            }
            // Add score in debug mode
            if (debugMode && result.score !== undefined) {
                const scoreSpan = document.createElement('span');
                scoreSpan.className = 'debug-score';
                scoreSpan.textContent = ` [${result.score.toFixed(1)}]`;
                scoreSpan.style.opacity = '0.6';
                scoreSpan.style.fontSize = '0.85em';
                button.appendChild(scoreSpan);
            }
            return button;
        }

        // For locations and events
        const button = document.createElement('button');
        button.className = 'tag-button state-unselected';

        // Add non-visible class based on result type
        if (result.isVisible === false) {
            if (result.type === 'location') {
                button.classList.add('non-visible-location');
            } else if (result.type === 'event') {
                button.classList.add('non-visible-event');
            }
        }

        button.dataset.resultType = result.type;
        button.dataset.resultRef = result.ref;
        button.setAttribute('role', 'listitem');

        const emoji = result.emoji ? `<span class="popup-event-emoji" aria-hidden="true">${result.emoji}</span>` : '';
        const displayName = result.displayName || result.ref;
        const scoreText = (debugMode && result.score !== undefined) ? ` <span class="debug-score" style="opacity: 0.6; font-size: 0.85em;">[${result.score.toFixed(1)}]</span>` : '';
        button.innerHTML = `${emoji} ${displayName.replace(/<\/?strong>/g, '')}${scoreText}`;
        button.setAttribute('aria-label', `${result.type}: ${displayName.replace(/<\/?[^>]+(>|$)/g, '')}`);

        button.addEventListener('click', () => {
            if (onSearchResultClick && result.type) {
                onSearchResultClick(result);
            }
        });

        return button;
    }

    // ========================================
    // STATE MANAGEMENT
    // ========================================

    /**
     * Sets the state for a tag
     * @param {string} tag - Tag name
     * @param {string} newState - New state value
     */
    function setTagState(tag, newState) {
        const oldState = state.tagStates[tag] || TAG_STATE.UNSELECTED;
        state.tagStates[tag] = newState;
        handleColorAssignment(oldState, newState, tag);
    }

    /**
     * Gets the state for a tag
     * @param {string} tag - Tag name
     * @returns {string} Tag state
     */
    function getTagState(tag) {
        return state.tagStates[tag] || TAG_STATE.UNSELECTED;
    }

    /**
     * Gets all tag states
     * @returns {Object} Map of tag to state
     */
    function getTagStates() {
        return state.tagStates;
    }

    /**
     * Selects multiple tags (sets them to SELECTED state)
     * @param {Array<string>} tags - Tags to select
     */
    function selectTags(tags) {
        tags.forEach(tag => {
            setTagState(tag, TAG_STATE.SELECTED);
        });
    }

    /**
     * Updates all tag button visuals
     * Used when colors are reassigned (e.g., theme change)
     */
    function updateAllTagVisuals() {
        const tagButtons = document.querySelectorAll('[data-tag]');
        tagButtons.forEach(button => {
            const tag = button.dataset.tag;
            if (tag) {
                updateTagVisuals(button, tag);
            }
        });
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the TagStateManager module
     * @param {Object} config - Configuration object
     * @param {Object} config.tagStates - Reference to tag states object
     * @param {Object} config.colorProvider - Provider for tag color operations
     * @param {Function} config.colorProvider.getTagColor - Get tag color
     * @param {Function} config.colorProvider.assignColorToTag - Assign color to tag
     * @param {Function} config.colorProvider.unassignColorFromTag - Unassign color from tag
     * @param {Object} [config.relatedTagsProvider] - Provider for related tags operations
     * @param {Function} [config.relatedTagsProvider.isImplicitlySelected] - Check if tag is implicitly selected
     * @param {Function} [config.relatedTagsProvider.isIncludingRelatedTags] - Check if related tags are included
     * @param {Function} config.onFilterChangeCallback - Callback when filters change
     * @param {string} config.defaultMarkerColor - Default marker color
     */
    function init(config) {
        state.tagStates = config.tagStates;
        state.colorProvider = config.colorProvider || null;
        state.relatedTagsProvider = config.relatedTagsProvider || null;
        state.onFilterChangeCallback = config.onFilterChangeCallback;
        state.defaultMarkerColor = config.defaultMarkerColor;
    }

    /**
     * Gets the TAG_STATE constants
     * @returns {Object} Tag state constants
     */
    function getTagStateConstants() {
        return TAG_STATE;
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Initialization
        init,

        // Button creation
        createTagElement,
        createInteractiveTagButton,
        createSearchResultButton,

        // State management
        setTagState,
        getTagState,
        getTagStates,
        selectTags,
        updateAllTagVisuals,

        // Constants
        getTagStateConstants
    };
})();
