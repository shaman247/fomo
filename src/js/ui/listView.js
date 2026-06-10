/**
 * ListView Module
 *
 * Renders a scrollable list of filter-matching events into the sheet's
 * results container when there is no active search term (desktop and mobile).
 * It takes the place of the (otherwise empty) search-results panel.
 *
 * Only events within the current map window are shown (the caller supplies
 * `currentlyVisibleMatchingEvents`, re-filtered on every pan), minus — on
 * desktop — events whose markers sit under the open left-docked sheet itself
 * (in the viewport but not visible). They are ranked so that one-off events come before
 * long-running/recurring ones and every location's first event appears before
 * any location's second (round-robin across locations); remaining ties favor
 * events earlier in the active date range, then distance to the map center.
 * Duplicate titles collapse to their highest-ranked instance. Capped to keep
 * panning responsive.
 *
 * Each row reuses the popup event card (`PopupContentBuilder.createEventCard`,
 * non-interactive) so formatting matches the location popup, styled like an
 * expanded popup event (vivid title, full-opacity preview — see filter-panel.css).
 * Rows are permanently collapsed: hovering a row highlights the location's marker
 * (ring + label) and clicking it opens that location's popup (desktop: floating
 * popup; mobile: detail mode inside the sheet).
 *
 * @module ListView
 */
const ListView = (() => {
    // ========================================
    // CONSTANTS
    // ========================================

    // Max cards rendered. The list re-renders on every map pan (moveend), so an
    // uncapped list of thousands of events would jank panning. We show the
    // top-ranked N and note the truncation in a footer.
    const RENDER_CAP = 200;

    const MS_PER_DAY = 24 * 60 * 60 * 1000;

    // Spread value assigned to exporter-classified 'Ongoing' events so they
    // always sort with the long-running tail, even when their listed
    // occurrences cover few days.
    const ONGOING_SPREAD = 1000;

    // ========================================
    // STATE
    // ========================================

    const state = {
        getMatchingEvents: () => [],
        getLocationInfo: () => null,
        getLocationDistances: () => ({}),
        getVisibleCenter: () => null,
        getContainer: () => null,
    };

    // ========================================
    // HELPERS
    // ========================================

    /**
     * Resolves the distance (meters) from the map center to an event's location.
     * Prefers the precomputed App.state.locationDistances map; falls back to a
     * haversine calculation from the visible center when the key is missing.
     * Returns Infinity when no distance can be resolved (sorts such events last).
     */
    function distanceForEvent(event, distances, visibleCenter) {
        const key = event.locationKey;
        if (key && distances && Object.prototype.hasOwnProperty.call(distances, key)) {
            return distances[key];
        }
        if (visibleCenter && key) {
            const [lat, lng] = key.split(',').map(Number);
            if (Number.isFinite(lat) && Number.isFinite(lng)) {
                return Utils.calculateHaversineDistance(visibleCenter, { lat, lng });
            }
        }
        return Infinity;
    }

    /**
     * Total number of days an event is active across all its occurrences —
     * 1 for a true one-off, growing with recurrence (weekly series) and run
     * length (multi-week exhibitions). Lower spreads rank higher in the list.
     */
    function spreadDaysForEvent(event) {
        const occurrences = Array.isArray(event.occurrences) ? event.occurrences : [];
        let days = 0;
        for (const occ of occurrences) {
            days += 1 + Math.max(0, Math.round((occ.end - occ.start) / MS_PER_DAY));
        }
        if (event.section && event.section !== 'Events') {
            return Math.max(days, ONGOING_SPREAD);
        }
        return Math.max(days, 1);
    }

    /**
     * Epoch ms of the event's soonest occurrence within the active date filter
     * (falling back to its first occurrence overall). Events earlier in the
     * date range rank above later ones, both within a location's own ordering
     * and across locations within a round.
     */
    function nextStartForEvent(event) {
        const matching = event.matching_occurrences;
        const occurrences = (Array.isArray(matching) && matching.length > 0)
            ? matching
            : event.occurrences;
        const start = occurrences && occurrences[0] && occurrences[0].start;
        return (start instanceof Date && !isNaN(start)) ? start.getTime() : Number.MAX_SAFE_INTEGER;
    }

    /**
     * Map-container-relative x px below which the map is covered by the open
     * left-docked sheet. 0 when the sheet is closed/absent (nothing covered).
     * Desktop-only: the mobile bottom sheet overlays the map rather than
     * docking beside it, so nothing is filtered out there (filtering by the
     * covered bottom half would reshuffle the list on every snap change).
     */
    function coveredLeftPx(map) {
        const bp = (typeof Constants !== 'undefined' && Constants.UI && Constants.UI.MOBILE_BREAKPOINT) || 768;
        if (window.innerWidth <= bp) return 0;
        if (typeof Sheet === 'undefined' || !Sheet.isOpen()) return 0;
        const sheet = document.getElementById('sheet');
        if (!sheet) return 0;
        // offsetWidth, not getBoundingClientRect: the sheet slides in via a CSS
        // transform, and the open-time render runs while that transition is
        // still going. Layout geometry gives the settled footprint (the open
        // sheet is fixed at the window's left edge).
        const mapRect = map.getContainer().getBoundingClientRect();
        return Math.max(0, sheet.offsetWidth - mapRect.left);
    }

    /**
     * Drops events whose markers sit under the open left sheet — they pass the
     * caller's viewport filter but aren't actually visible to the user.
     * Projections are cached per location since events share locations.
     */
    function filterToUncoveredMap(events) {
        const map = (typeof MapManager !== 'undefined' && MapManager.getMap) ? MapManager.getMap() : null;
        if (!map) return events;
        const cutoff = coveredLeftPx(map);
        if (cutoff <= 0) return events;

        const projectedX = new Map();
        return events.filter(event => {
            const key = event.locationKey;
            if (!key) return true;
            let x = projectedX.get(key);
            if (x === undefined) {
                const [lat, lng] = key.split(',').map(Number);
                x = (Number.isFinite(lat) && Number.isFinite(lng)) ? map.project([lng, lat]).x : Infinity;
                projectedX.set(key, x);
            }
            return x >= cutoff;
        });
    }

    // ========================================
    // PUBLIC API
    // ========================================

    function init(config) {
        if (config.getMatchingEvents) state.getMatchingEvents = config.getMatchingEvents;
        if (config.getLocationInfo) state.getLocationInfo = config.getLocationInfo;
        if (config.getLocationDistances) state.getLocationDistances = config.getLocationDistances;
        if (config.getVisibleCenter) state.getVisibleCenter = config.getVisibleCenter;
        if (config.getContainer) state.getContainer = config.getContainer;
    }

    /**
     * Whether the list has any events to show (drives the panel's collapse logic).
     */
    function hasContent() {
        const events = state.getMatchingEvents();
        return Array.isArray(events) && events.length > 0;
    }

    /**
     * Builds and renders the event list into the results container.
     */
    function render() {
        const container = state.getContainer();
        if (!container) return;

        const events = filterToUncoveredMap(state.getMatchingEvents() || []);
        const distances = state.getLocationDistances() || {};
        const visibleCenter = state.getVisibleCenter();

        const entries = events.map(event => ({
            event,
            dist: distanceForEvent(event, distances, visibleCenter),
            spread: spreadDaysForEvent(event),
            next: nextStartForEvent(event),
            rank: 0,
        }));

        // Round-robin across locations: order each location's own events
        // (one-offs first, then soonest), so its i-th event competes in
        // round i against every other location's i-th event.
        const byLocation = new Map();
        for (const entry of entries) {
            const key = entry.event.locationKey || `event:${entry.event.id}`;
            const group = byLocation.get(key);
            if (group) group.push(entry); else byLocation.set(key, [entry]);
        }
        for (const group of byLocation.values()) {
            group.sort((a, b) => (a.spread - b.spread) || (a.next - b.next));
            group.forEach((entry, i) => { entry.rank = i; });
        }

        // Within each round, one-off events outrank long-running/recurring
        // ones, then events earlier in the date range outrank later ones;
        // remaining ties go nearest-first relative to the map center.
        const sorted = entries.sort((a, b) =>
            (a.rank - b.rank) ||
            (a.spread - b.spread) ||
            (a.next - b.next) ||
            (a.dist < b.dist ? -1 : a.dist > b.dist ? 1 : 0));

        // Collapse duplicate titles — different venues often list the same
        // touring show/series; keep only the highest-ranked instance.
        const seenTitles = new Set();
        const deduped = sorted.filter(({ event }) => {
            const title = (event.name || '').trim().toLowerCase();
            if (!title) return true;
            if (seenTitles.has(title)) return false;
            seenTitles.add(title);
            return true;
        });

        const total = deduped.length;
        const shown = deduped.slice(0, RENDER_CAP);

        const wrapper = document.createElement('div');
        wrapper.className = 'list-view-scroll';

        shown.forEach(({ event }) => {
            // Permanently collapsed, non-expanding cards — the list wires its own
            // hover (highlight the marker, solo its label) and click (open the
            // location popup). createEventCard tints the title from the event's
            // own emoji color.
            const card = PopupContentBuilder.createEventCard(event, { interactive: false });

            const locationKey = event.locationKey;
            if (locationKey) {
                card.addEventListener('mouseenter', () => {
                    MapManager.highlightLocationByKey(locationKey, { soloLabel: true, labelEvent: event });
                });
                card.addEventListener('mouseleave', () => {
                    MapManager.clearHoverHighlight();
                });
                card.addEventListener('click', () => {
                    const [lat, lng] = locationKey.split(',').map(Number);
                    if (Number.isFinite(lat) && Number.isFinite(lng)) {
                        MarkerController.flyToLocationAndOpenPopup(lat, lng, event.id);
                    }
                });
            }

            wrapper.appendChild(card);
        });

        if (total > RENDER_CAP) {
            const footer = document.createElement('div');
            footer.className = 'list-view-footer';
            footer.textContent = `Showing ${RENDER_CAP} of ${total} events`;
            wrapper.appendChild(footer);
        }

        container.innerHTML = '';
        container.appendChild(wrapper);
        container.scrollTop = 0;
    }

    /**
     * Clears the list (used when a search term takes over the results container).
     */
    function teardown() {
        const container = state.getContainer();
        if (container) {
            container.innerHTML = '';
            container.scrollTop = 0;
        }
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        init,
        render,
        teardown,
        hasContent,
    };
})();
