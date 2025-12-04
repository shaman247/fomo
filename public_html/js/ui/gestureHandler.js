/**
 * GestureHandler Module
 *
 * Manages swipe gesture handling for section reordering in the tag filter UI.
 * Supports both touch and mouse events for horizontal swipe gestures.
 *
 * Features:
 * - Touch and mouse gesture detection
 * - Horizontal swipe recognition with directional threshold
 * - Visual feedback during swipe (translation and opacity)
 * - Section reordering via swipe-to-dismiss
 * - Pointer event management to prevent conflicts
 *
 * @module GestureHandler
 */
const GestureHandler = (() => {
    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // Configuration
        containerDOM: null,
        sectionOrder: [],

        // Callbacks
        onSectionReorder: null,
        performSearchCallback: null,

        // Gesture tracking
        startX: 0,
        startY: 0,
        isDragging: false,
        isHorizontalSwipe: false,
        hasTriggeredReorder: false,
        targetSectionKey: null,
        targetHeader: null,
        targetContainer: null,

        // Event handler references (for cleanup)
        handlers: {
            touchstart: null,
            touchmove: null,
            touchend: null,
            mousedown: null,
            mousemove: null,
            mouseup: null,
            mouseleave: null
        }
    };

    // ========================================
    // GESTURE HANDLERS
    // ========================================

    /**
     * Handles gesture start (touch or mouse down)
     * @param {number} x - X coordinate
     * @param {number} y - Y coordinate
     * @param {HTMLElement} target - Event target element
     */
    function handleStart(x, y, target) {
        const container = target.closest('.search-results-section');
        if (!container) return;

        state.targetContainer = container;
        state.targetSectionKey = container.dataset.sectionKey;
        state.targetHeader = container.querySelector('.result-group-title');

        state.startX = x;
        state.startY = y;
        state.isDragging = true;
        state.isHorizontalSwipe = false;
        state.hasTriggeredReorder = false;
    }

    /**
     * Handles gesture movement (touch move or mouse move)
     * @param {number} x - X coordinate
     * @param {number} y - Y coordinate
     */
    function handleMove(x, y) {
        if (!state.isDragging || !state.targetSectionKey) return;

        const deltaX = x - state.startX;
        const deltaY = y - state.startY;

        // Determine if this is a horizontal swipe
        if (!state.isHorizontalSwipe && (Math.abs(deltaX) > 10 || Math.abs(deltaY) > 10)) {
            state.isHorizontalSwipe = Math.abs(deltaX) > Math.abs(deltaY);

            // Prevent click on buttons when swiping horizontally
            if (state.isHorizontalSwipe && state.targetHeader && state.targetHeader.querySelector('.tag-button')) {
                const buttons = state.targetContainer ? state.targetContainer.querySelectorAll('.tag-button') : [];
                buttons.forEach(btn => {
                    btn.style.pointerEvents = 'none';
                });
            }
        }

        // Apply visual feedback for horizontal swipes
        if (state.isHorizontalSwipe) {
            const maxDisplacement = Constants.UI.SWIPE_MAX_DISPLACEMENT_PX;
            const displacement = Math.max(-maxDisplacement, Math.min(maxDisplacement, deltaX));
            const opacity = 1 - (Math.abs(displacement) / maxDisplacement) * 0.5;

            if (state.targetContainer) {
                state.targetContainer.style.transition = 'none';
                state.targetContainer.style.transform = `translateX(${displacement}px)`;
                state.targetContainer.style.opacity = opacity;
            }

            // Trigger reorder when threshold is reached
            if (!state.hasTriggeredReorder && Math.abs(deltaX) > Constants.UI.SWIPE_THRESHOLD_PX) {
                triggerReorder(deltaX);
            }
        }
    }

    /**
     * Triggers section reorder when swipe threshold is exceeded
     * @param {number} deltaX - Horizontal displacement
     */
    function triggerReorder(deltaX) {
        state.hasTriggeredReorder = true;

        const oldContainer = state.targetContainer;
        const dismissedIndex = state.sectionOrder.indexOf(state.targetSectionKey);

        // Move the swiped section to the bottom
        state.sectionOrder.splice(dismissedIndex, 1);
        state.sectionOrder.push(state.targetSectionKey);

        // Notify parent of reorder
        if (state.onSectionReorder) {
            state.onSectionReorder(state.sectionOrder);
        }

        // Reset drag state
        state.isDragging = false;
        state.isHorizontalSwipe = false;

        // Animate out the swiped section
        const slideDistance = 30;
        const slideOutX = deltaX > 0 ? slideDistance : -slideDistance;

        if (oldContainer) {
            oldContainer.style.transition = 'transform 0.15s ease-out, opacity 0.15s ease-out';
            oldContainer.style.transform = `translateX(${slideOutX}px)`;
            oldContainer.style.opacity = '0';
        }

        // Re-render after animation via callback
        if (state.performSearchCallback) {
            state.performSearchCallback();
        }
    }

    /**
     * Handles gesture end (touch end or mouse up)
     */
    function handleEnd() {
        if (!state.isDragging) return;

        // Reset visual feedback if reorder wasn't triggered
        if (!state.hasTriggeredReorder && state.isHorizontalSwipe) {
            if (state.targetContainer) {
                state.targetContainer.style.transition = 'transform 0.3s ease, opacity 0.3s ease';
                state.targetContainer.style.transform = 'translateX(0)';
                state.targetContainer.style.opacity = '1';
            }
        }

        // Re-enable pointer events on buttons
        if (state.targetContainer) {
            const buttons = state.targetContainer.querySelectorAll('.tag-button');
            buttons.forEach(btn => {
                btn.style.pointerEvents = '';
            });
        }

        resetGestureState();
    }

    /**
     * Handles mouse leave event (cancel gesture)
     */
    function handleMouseLeave() {
        if (state.isDragging && state.isHorizontalSwipe) {
            if (state.targetContainer) {
                state.targetContainer.style.transition = 'transform 0.3s ease, opacity 0.3s ease';
                state.targetContainer.style.transform = 'translateX(0)';
                state.targetContainer.style.opacity = '1';

                const buttons = state.targetContainer.querySelectorAll('.tag-button');
                buttons.forEach(btn => {
                    btn.style.pointerEvents = '';
                });
            }

            resetGestureState();
        }
    }

    /**
     * Resets gesture tracking state
     */
    function resetGestureState() {
        state.isDragging = false;
        state.isHorizontalSwipe = false;
        state.hasTriggeredReorder = false;
        state.targetSectionKey = null;
        state.targetHeader = null;
        state.targetContainer = null;
    }

    // ========================================
    // INITIALIZATION & CLEANUP
    // ========================================

    /**
     * Removes all gesture event listeners to prevent memory leaks
     */
    function cleanup() {
        if (!state.containerDOM) return;

        // Remove all event listeners using stored references
        if (state.handlers.touchstart) {
            state.containerDOM.removeEventListener('touchstart', state.handlers.touchstart);
        }
        if (state.handlers.touchmove) {
            state.containerDOM.removeEventListener('touchmove', state.handlers.touchmove);
        }
        if (state.handlers.touchend) {
            state.containerDOM.removeEventListener('touchend', state.handlers.touchend);
        }
        if (state.handlers.mousedown) {
            state.containerDOM.removeEventListener('mousedown', state.handlers.mousedown);
        }
        if (state.handlers.mousemove) {
            state.containerDOM.removeEventListener('mousemove', state.handlers.mousemove);
        }
        if (state.handlers.mouseup) {
            state.containerDOM.removeEventListener('mouseup', state.handlers.mouseup);
        }
        if (state.handlers.mouseleave) {
            state.containerDOM.removeEventListener('mouseleave', state.handlers.mouseleave);
        }

        // Clear handler references
        state.handlers = {
            touchstart: null,
            touchmove: null,
            touchend: null,
            mousedown: null,
            mousemove: null,
            mouseup: null,
            mouseleave: null
        };
    }

    /**
     * Initializes swipe gesture handlers for section reordering
     * Sets up both touch and mouse event listeners
     */
    function initSwipeGestures() {
        if (!state.containerDOM) {
            console.warn('GestureHandler: containerDOM not set');
            return;
        }

        // Clean up any existing listeners before adding new ones
        cleanup();

        // Create and store event handler references
        state.handlers.touchstart = (e) => {
            const touch = e.touches[0];
            handleStart(touch.clientX, touch.clientY, e.target);
        };

        state.handlers.touchmove = (e) => {
            if (e.touches.length > 0) {
                const touch = e.touches[0];
                handleMove(touch.clientX, touch.clientY);
            }
        };

        state.handlers.touchend = (e) => {
            if (e.changedTouches.length > 0) {
                handleEnd();
            }
        };

        state.handlers.mousedown = (e) => {
            handleStart(e.clientX, e.clientY, e.target);
        };

        state.handlers.mousemove = (e) => {
            handleMove(e.clientX, e.clientY);
        };

        state.handlers.mouseup = () => {
            handleEnd();
        };

        state.handlers.mouseleave = () => {
            handleMouseLeave();
        };

        // Add event listeners with stored references
        state.containerDOM.addEventListener('touchstart', state.handlers.touchstart, { passive: true });
        state.containerDOM.addEventListener('touchmove', state.handlers.touchmove, { passive: true });
        state.containerDOM.addEventListener('touchend', state.handlers.touchend, { passive: true });
        state.containerDOM.addEventListener('mousedown', state.handlers.mousedown);
        state.containerDOM.addEventListener('mousemove', state.handlers.mousemove);
        state.containerDOM.addEventListener('mouseup', state.handlers.mouseup);
        state.containerDOM.addEventListener('mouseleave', state.handlers.mouseleave);
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the GestureHandler module
     * @param {Object} config - Configuration object
     * @param {HTMLElement} config.containerDOM - Container DOM element for gesture events
     * @param {Array<string>} config.sectionOrder - Reference to section order array
     * @param {Function} config.onSectionReorder - Callback when section order changes
     * @param {Function} config.performSearchCallback - Callback to trigger search/re-render
     */
    function init(config) {
        state.containerDOM = config.containerDOM;
        state.sectionOrder = config.sectionOrder;
        state.onSectionReorder = config.onSectionReorder;
        state.performSearchCallback = config.performSearchCallback;

        // Initialize gesture listeners
        initSwipeGestures();
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Initialization
        init,

        // Cleanup
        cleanup
    };
})();
