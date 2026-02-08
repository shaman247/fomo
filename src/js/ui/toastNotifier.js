/**
 * ToastNotifier Module
 *
 * Manages toast notification messages for the application.
 * Provides temporary, non-intrusive feedback to users.
 *
 * Features:
 * - Success, error, and info toast types
 * - Configurable display duration
 * - Automatic dismissal
 * - Single toast instance (new toasts replace old ones)
 *
 * @module ToastNotifier
 */
const ToastNotifier = (() => {
    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // Toast timeout tracking
        toastTimeout: null,

        // DOM reference
        toastElement: null
    };

    // ========================================
    // TOAST NOTIFICATION
    // ========================================

    /**
     * Shows a toast notification message
     * @param {string} message - The message to display
     * @param {string} type - Type of toast: 'success', 'error', or 'info' (default)
     * @param {number} duration - Duration in ms (default 3000)
     */
    function showToast(message, type = 'info', duration = 3000) {
        const toast = state.toastElement || document.getElementById('toast-notification');
        if (!toast) return;

        // Cache the element for future use
        if (!state.toastElement) {
            state.toastElement = toast;
        }

        // Clear any existing timeout
        if (state.toastTimeout) {
            clearTimeout(state.toastTimeout);
        }

        // Set message and type
        toast.textContent = message;
        toast.className = 'toast-notification';
        if (type === 'success' || type === 'error') {
            toast.classList.add(type);
        }

        // Show toast
        setTimeout(() => {
            toast.classList.add('show');
        }, 10);

        // Auto-hide after duration
        state.toastTimeout = setTimeout(() => {
            toast.classList.remove('show');
        }, duration);
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        showToast
    };
})();
