const Analytics = (() => {
    // First-party, aggregate usage counts. One beacon when the page loads, then
    // one each time the page is hidden, carrying visible seconds and feature-use
    // counts since the previous beacon. api/analytics.php only adds them to daily
    // totals: no cookies, no device storage, no identifiers, and no visitor
    // counting. Off under Do Not Track / Global Privacy Control, and off on any
    // host but the production domain, so dev builds and smoke tests never count.
    // Read the totals with scripts/analytics_report.py.

    const ENDPOINT = 'api/analytics.php';
    const CITY = window.__CITY__ || {};
    const host = location.hostname.replace(/^www\./, '');
    const optedOut = navigator.doNotTrack === '1' || window.doNotTrack === '1' || navigator.globalPrivacyControl === true;
    const enabled = Boolean(CITY.domain) && host === CITY.domain && !optedOut;
    // Engagement milestones, reported once per page load like first feature uses.
    const MILESTONES = [[10, 'engaged_10s'], [60, 'engaged_60s'], [300, 'engaged_5m']];
    const MAX_SECONDS_PER_BEACON = 1800;
    // URL parameters that only a shared view link carries (see URLParams).
    const SHARED_VIEW_PARAMS = ['lat', 'lng', 'zoom', 'start', 'end', 'tags', 'formats', 'neighborhoods'];

    let counts = {};
    let firsts = new Set();
    const used = new Set();
    let visibleMs = 0;
    let totalSeconds = 0;
    let visibleSince = document.visibilityState === 'visible' ? performance.now() : null;

    function count(action) {
        if (!enabled) return;
        counts[action] = (counts[action] || 0) + 1;
        if (!used.has(action)) {
            used.add(action);
            firsts.add(action);
        }
    }

    function referrerHost() {
        try {
            const referrer = new URL(document.referrer).hostname.replace(/^www\./, '');
            return referrer === host ? '' : referrer;
        } catch (e) {
            return '';
        }
    }

    function sendView() {
        const params = new URLSearchParams(location.search);
        const utm = params.get('utm_source') || '';
        Beacon.send(ENDPOINT, {
            type: 'view',
            ...Beacon.context(),
            ctz: CITY.timezone,
            ref: referrerHost(),
            utm: /^[\w.-]{1,40}$/.test(utm) ? utm : '',
            shared: SHARED_VIEW_PARAMS.some(name => params.has(name)),
            lang: (navigator.language || '').slice(0, 2).toLowerCase()
        });
    }

    function flush() {
        if (visibleSince !== null) {
            visibleMs += performance.now() - visibleSince;
            visibleSince = document.visibilityState === 'visible' ? performance.now() : null;
        }
        const seconds = Math.min(Math.round(visibleMs / 1000), MAX_SECONDS_PER_BEACON);
        visibleMs = 0;
        totalSeconds += seconds;
        for (const [threshold, name] of MILESTONES) {
            if (totalSeconds >= threshold && !used.has(name)) {
                used.add(name);
                firsts.add(name);
            }
        }
        if (!seconds && !firsts.size && !Object.keys(counts).length) return;
        const { platform, viewport, screen, wd } = Beacon.context();
        Beacon.send(ENDPOINT, { type: 'engage', ctz: CITY.timezone, platform, viewport, screen, wd, seconds, counts, firsts: [...firsts] });
        counts = {};
        firsts = new Set();
    }

    // Feature use, observed through delegated listeners so no module has to call in.
    const CLICKS = [
        ['a.popup-external-link', 'event_link'],
        ['#share-view-btn', 'share'],
        ['#feedback-btn', 'feedback_open'],
        ['#sheet-handle, .sheet-drag-area', 'list_toggle'],
        ['#results-container .popup-event-card', 'list_event_open'],
        ['.tag-button, .tag-keyword', 'tag_click']
    ];
    const CHANGES = [
        ['#tag-selector-panel', 'filter_topic'],
        ['#venue-selector-panel', 'filter_venue'],
        ['#format-selector-panel', 'filter_format'],
        ['#neighborhood-selector-panel', 'filter_area'],
        ['#date-filter-container', 'date_change'],
        ['#theme-options', 'theme_change']
    ];

    function start() {
        sendView();

        document.addEventListener('click', event => {
            const target = event.target instanceof Element ? event.target : null;
            if (!target) return;
            const match = CLICKS.find(([selector]) => target.closest(selector));
            if (match) count(match[1]);
            else {
                const link = target.closest('a[href]');
                if (link && link.hostname && link.hostname.replace(/^www\./, '') !== host) count('outbound');
            }
        }, true);

        document.addEventListener('change', event => {
            const target = event.target instanceof Element ? event.target : null;
            const match = target && CHANGES.find(([selector]) => target.closest(selector));
            if (match) count(match[1]);
        }, true);

        let searchTimer = null;
        document.addEventListener('input', event => {
            if (!(event.target instanceof Element) || event.target.id !== 'omni-search-input') return;
            clearTimeout(searchTimer);
            const input = event.target;
            searchTimer = setTimeout(() => { if (input.value.trim().length >= 2) count('search'); }, 1500);
        }, true);

        // A popup opens as a MapLibre popup on the map (desktop) or as content in
        // the sheet's empty detail pane (mobile); one open can do both, and the
        // detail pane re-renders in place when filters change, so count a popup
        // being added, or the pane going from empty to filled, at most once a second.
        let lastPopupAt = -Infinity;
        const countPopup = () => {
            if (performance.now() - lastPopupAt < 1000) return;
            lastPopupAt = performance.now();
            count('popup_open');
        };
        const map = document.getElementById('map');
        if (map) {
            new MutationObserver(mutations => {
                if (mutations.some(m => [...m.addedNodes].some(n => n instanceof Element && n.matches('.maplibregl-popup')))) countPopup();
            }).observe(map, { childList: true });
        }
        const detail = document.querySelector('.sheet-detail');
        if (detail) {
            let filled = detail.childElementCount > 0;
            new MutationObserver(() => {
                const now = detail.childElementCount > 0;
                if (now && !filled) countPopup();
                filled = now;
            }).observe(detail, { childList: true });
        }

        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'hidden') flush();
            else visibleSince = performance.now();
        });
        window.addEventListener('pagehide', flush);
    }

    if (enabled) {
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
        else start();
    }

    return { count, enabled };
})();
