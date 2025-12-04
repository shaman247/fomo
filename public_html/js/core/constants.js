/**
 * Application Constants
 *
 * Centralized constants for the entire application.
 * Eliminates magic numbers and improves maintainability.
 *
 * @module Constants
 */
const Constants = (() => {
    // ========================================
    // TIME CONSTANTS
    // ========================================

    const TIME = {
        ONE_DAY_MS: 24 * 60 * 60 * 1000,
        FIVE_DAYS_MS: 5 * 24 * 60 * 60 * 1000,
        THIRTY_DAYS_MS: 30 * 24 * 60 * 60 * 1000,

        // Debounce/Throttle delays (in milliseconds)
        SEARCH_DEBOUNCE_MS: 100,
        MAP_MOVE_THROTTLE_MS: 250,
        RESIZE_THROTTLE_MS: 150
    };

    // ========================================
    // DISTANCE CONSTANTS
    // ========================================

    const DISTANCE = {
        // Distance threshold in meters for proximity calculations
        MAX_PROXIMITY_METERS: 20000,

        // Distance decay factors for search scoring
        CLOSE_DISTANCE_METERS: 5000,
        FAR_DISTANCE_METERS: 30000
    };

    // ========================================
    // UI CONSTANTS
    // ========================================

    const UI = {
        // Responsive breakpoints (in pixels)
        MOBILE_BREAKPOINT: 768,

        // Marker limits
        MAX_MARKERS: 1000,

        // Line height for text calculations (in pixels)
        LINE_HEIGHT_PX: 32,

        // Toast notification durations (in milliseconds)
        TOAST_DURATION_SHORT: 3000,
        TOAST_DURATION_MEDIUM: 5000,
        TOAST_DURATION_LONG: 7000,

        // Filter panel dimensions (in pixels)
        FILTER_PANEL_MOBILE_HEIGHT: 145,

        // Gesture thresholds (in pixels)
        SWIPE_THRESHOLD_PX: 50,
        SWIPE_MAX_DISPLACEMENT_PX: 100,

        // Animation delays (in milliseconds)
        EMOJI_RERENDER_DELAY_MS: 500
    };

    // ========================================
    // SEARCH CONSTANTS
    // ========================================

    const SEARCH = {
        // Maximum results to show in search
        MAX_RESULTS: 100,

        // Score thresholds
        MIN_SCORE_THRESHOLD: 0.1
    };

    // ========================================
    // EXPORTS
    // ========================================

    return {
        TIME,
        DISTANCE,
        UI,
        SEARCH
    };
})();
