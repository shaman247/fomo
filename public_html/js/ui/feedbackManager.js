/**
 * FeedbackManager Module
 *
 * Manages the feedback submission modal and API communication.
 *
 * Features:
 * - Modal open/close with keyboard support
 * - Character count display
 * - Form validation
 * - API submission with loading states
 * - Success/error feedback via toast notifications
 *
 * @module FeedbackManager
 */
const FeedbackManager = (() => {
    // ========================================
    // CONFIGURATION
    // ========================================

    const CONFIG = {
        API_ENDPOINT: 'api/feedback.php',
        MAX_LENGTH: 10000
    };

    // ========================================
    // STATE
    // ========================================

    const state = {
        modal: null,
        textarea: null,
        submitBtn: null,
        charCount: null,
        statusEl: null,
        isSubmitting: false
    };

    // ========================================
    // INITIALIZATION
    // ========================================

    /**
     * Initializes the feedback modal and event listeners
     */
    function init() {
        state.modal = document.getElementById('feedback-modal');
        state.textarea = document.getElementById('feedback-message');
        state.submitBtn = document.getElementById('feedback-submit-btn');
        state.charCount = document.getElementById('feedback-char-count');
        state.statusEl = document.getElementById('feedback-status');
        const closeBtn = document.getElementById('feedback-close-btn');
        const feedbackBtn = document.getElementById('feedback-btn');

        if (!state.modal || !state.textarea || !state.submitBtn) {
            console.warn('FeedbackManager: Required elements not found');
            return;
        }

        // Open modal from menu button
        if (feedbackBtn) {
            feedbackBtn.addEventListener('click', () => {
                open();
            });
        }

        // Close button
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                close();
            });
        }

        // Click outside to close
        state.modal.addEventListener('click', (e) => {
            if (e.target === state.modal) {
                close();
            }
        });

        // Escape key to close
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && state.modal.classList.contains('show')) {
                close();
            }
        });

        // Character count and validation
        state.textarea.addEventListener('input', () => {
            updateCharCount();
            validateForm();
        });

        // Submit button
        state.submitBtn.addEventListener('click', () => {
            submit();
        });

        // Allow Ctrl+Enter to submit
        state.textarea.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                if (!state.submitBtn.disabled) {
                    submit();
                }
            }
        });

        // Check for #feedback hash in URL
        checkHashAndOpen();
        window.addEventListener('hashchange', checkHashAndOpen);
    }

    /**
     * Opens feedback modal if URL hash is #feedback
     */
    function checkHashAndOpen() {
        if (window.location.hash === '#feedback') {
            // Small delay to ensure page is ready
            setTimeout(() => {
                open();
                // Clear the hash without scrolling
                history.replaceState(null, '', window.location.pathname + window.location.search);
            }, 100);
        }
    }

    // ========================================
    // MODAL CONTROLS
    // ========================================

    /**
     * Opens the feedback modal
     */
    function open() {
        if (state.modal) {
            state.modal.classList.add('show');
            // Focus textarea for accessibility
            setTimeout(() => {
                if (state.textarea) {
                    state.textarea.focus();
                }
            }, 100);
        }
    }

    /**
     * Closes the feedback modal
     */
    function close() {
        if (state.modal) {
            state.modal.classList.remove('show');
        }
    }

    /**
     * Resets the form to initial state
     */
    function reset() {
        if (state.textarea) {
            state.textarea.value = '';
        }
        updateCharCount();
        validateForm();
        setStatus('', '');
    }

    // ========================================
    // FORM HANDLING
    // ========================================

    /**
     * Updates the character count display
     */
    function updateCharCount() {
        if (state.textarea && state.charCount) {
            const count = state.textarea.value.length;
            state.charCount.textContent = `${count} / ${CONFIG.MAX_LENGTH}`;

            // Visual warning when approaching limit
            if (count > CONFIG.MAX_LENGTH * 0.9) {
                state.charCount.classList.add('warning');
            } else {
                state.charCount.classList.remove('warning');
            }
        }
    }

    /**
     * Validates the form and updates submit button state
     */
    function validateForm() {
        if (state.textarea && state.submitBtn) {
            const message = state.textarea.value.trim();
            const isValid = message.length > 0 && message.length <= CONFIG.MAX_LENGTH;
            state.submitBtn.disabled = !isValid || state.isSubmitting;
        }
    }

    /**
     * Sets the status message
     * @param {string} message - Status message
     * @param {string} type - Status type ('', 'loading', 'success', 'error')
     */
    function setStatus(message, type) {
        if (state.statusEl) {
            state.statusEl.textContent = message;
            state.statusEl.className = 'feedback-status' + (type ? ' ' + type : '');
        }
    }

    // ========================================
    // API SUBMISSION
    // ========================================

    /**
     * Submits the feedback to the API
     */
    async function submit() {
        if (state.isSubmitting || !state.textarea) return;

        const message = state.textarea.value.trim();
        if (!message) return;

        state.isSubmitting = true;
        state.submitBtn.disabled = true;
        setStatus('Submitting...', 'loading');

        try {
            const response = await fetch(CONFIG.API_ENDPOINT, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: message,
                    page_url: window.location.href
                })
            });

            const data = await response.json();

            if (response.ok && data.success) {
                setStatus('', '');
                reset();
                close();
                // Show success toast
                if (typeof ToastNotifier !== 'undefined') {
                    ToastNotifier.show('Thank you for your feedback!', 'success');
                }
            } else {
                const errorMsg = data.error || 'Failed to submit feedback';
                setStatus(errorMsg, 'error');
                if (typeof ToastNotifier !== 'undefined') {
                    ToastNotifier.show(errorMsg, 'error');
                }
            }
        } catch (error) {
            console.error('Feedback submission error:', error);
            const errorMsg = 'Network error. Please try again.';
            setStatus(errorMsg, 'error');
            if (typeof ToastNotifier !== 'undefined') {
                ToastNotifier.show(errorMsg, 'error');
            }
        } finally {
            state.isSubmitting = false;
            validateForm();
        }
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        init,
        open,
        close,
        reset
    };
})();
