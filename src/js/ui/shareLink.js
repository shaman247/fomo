/**
 * ShareLink — hands a link to the native share sheet (Messages, WhatsApp, …)
 * where the browser has one, and copies it to the clipboard otherwise.
 *
 * Call share() straight from a click handler: navigator.share needs the
 * click's user activation, so nothing may be awaited before it.
 *
 * @module ShareLink
 */
const ShareLink = (() => {
    /**
     * @param {Object} data
     * @param {string} data.url - Link to share
     * @param {string} [data.title] - Title the share sheet shows
     * @returns {Promise<string>} 'shared', 'cancelled', 'copied' or 'failed'
     */
    async function share({ url, title }) {
        const data = title ? { url, title } : { url };
        if (typeof navigator.share === 'function' && (typeof navigator.canShare !== 'function' || navigator.canShare(data))) {
            try {
                await navigator.share(data);
                return 'shared';
            } catch (err) {
                // Dismissing the sheet is a choice, not a failure to fall back from.
                if (err && err.name === 'AbortError') return 'cancelled';
                console.warn('Native share failed, copying instead:', err);
            }
        }
        return copy(url);
    }

    async function copy(url) {
        try {
            await navigator.clipboard.writeText(url);
            ToastNotifier.showToast('Link copied to clipboard!', 'success', 3000);
            return 'copied';
        } catch (err) {
            console.error('Failed to copy to clipboard:', err);
            // Fallback: show the URL in a toast for manual copying
            ToastNotifier.showToast('Could not copy automatically. URL: ' + url, 'info', 5000);
            return 'failed';
        }
    }

    return { share };
})();
