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

        // Early morning cutoff for event end times (hour in 24h format)
        // Events ending before this hour are treated as ending the previous day
        EARLY_MORNING_CUTOFF_HOUR: 5,

        // Debounce delay (in milliseconds)
        SEARCH_DEBOUNCE_MS: 100
    };

    // ========================================
    // DISTANCE CONSTANTS
    // ========================================

    const DISTANCE = {
        // Distance threshold in meters for proximity calculations
        MAX_PROXIMITY_METERS: 20000
    };

    // ========================================
    // UI CONSTANTS
    // ========================================

    const UI = {
        // Responsive breakpoints (in pixels)
        MOBILE_BREAKPOINT: 768,

        // Toast notification durations (in milliseconds)
        TOAST_DURATION_MEDIUM: 5000,
        TOAST_DURATION_LONG: 7000,

        // Filter panel dimensions (in pixels)
        FILTER_PANEL_MOBILE_HEIGHT: 90,
        FILTER_PANEL_DESKTOP_HEIGHT: 60,

        // Gesture thresholds (in pixels)
        SWIPE_THRESHOLD_PX: 50,
        SWIPE_MAX_DISPLACEMENT_PX: 100,

        // Animation delays (in milliseconds)
        EMOJI_RERENDER_DELAY_MS: 500
    };

    // ========================================
    // EXPORTS
    // ========================================

    return {
        TIME,
        DISTANCE,
        UI
    };
})();
