/**
 * ListView Module
 *
 * Renders a scrollable list of filter-matching events into the filter panel's
 * results container on DESKTOP when there is no active search term. It takes the
 * place of the (otherwise empty) search-results panel.
 *
 * Each row reuses the popup event card (`PopupContentBuilder.createEventCard`,
 * non-interactive) so formatting matches the location popup. Rows are
 * permanently collapsed: hovering a row highlights the location's marker (ring +
 * label) and clicking it opens that location's popup. Events are sorted
 * nearest-first relative to the current map center and capped to keep panning
 * responsive.
 *
 * Desktop-only — mobile uses the bottom sheet browse tabs instead.
 *
 * @module ListView
 */
const ListView = (() => {
    // ========================================
    // CONSTANTS
    // ========================================

    // Max cards rendered. The list re-renders on every map pan (moveend), so an
    // uncapped list of thousands of events would jank panning. We show the
    // nearest N and note the truncation in a footer.
    const RENDER_CAP = 200;

    // ========================================
    // STATE
    // ========================================

    const state = {
        getMatchingEvents: () => [],
        getLocationInfo: () => null,
        getLocationDistances: () => ({}),
        getVisibleCenter: () => null,
        getContainer: () => null,
        // Hidden by default — surfaced via the "Show list" toggle below the logo.
        visible: false,
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

    /** Whether the user has toggled the list on. */
    function isVisible() {
        return state.visible;
    }

    /** Set the list's visibility (does not re-render — caller triggers that). */
    function setVisible(v) {
        state.visible = !!v;
    }

    /**
     * Builds and renders the event list into the results container.
     */
    function render() {
        const container = state.getContainer();
        if (!container) return;

        const events = state.getMatchingEvents() || [];
        const distances = state.getLocationDistances() || {};
        const visibleCenter = state.getVisibleCenter();

        // Sort nearest-first by distance to the map center.
        const sorted = events
            .map(event => ({ event, dist: distanceForEvent(event, distances, visibleCenter) }))
            .sort((a, b) => a.dist - b.dist);

        const total = sorted.length;
        const shown = sorted.slice(0, RENDER_CAP);

        const wrapper = document.createElement('div');
        wrapper.className = 'list-view-scroll';

        shown.forEach(({ event }) => {
            // Permanently collapsed, non-expanding cards — the list wires its own
            // hover (highlight the marker) and click (open the location popup).
            // createEventCard tints the title from the event's own emoji color.
            const card = PopupContentBuilder.createEventCard(event, { interactive: false });

            const locationKey = event.locationKey;
            if (locationKey) {
                card.addEventListener('mouseenter', () => {
                    MapManager.highlightLocationByKey(locationKey);
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
            footer.textContent = `Showing nearest ${RENDER_CAP} of ${total} events`;
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
        isVisible,
        setVisible,
    };
})();
