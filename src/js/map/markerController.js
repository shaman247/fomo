/**
 * MarkerController Module
 *
 * Manages marker data lifecycle and popup content generation.
 * Coordinates with MapManager's WebGL symbol layers for rendering.
 *
 * @module MarkerController
 */
const MarkerController = (() => {
    // ========================================
    // STATE
    // ========================================

    const state = {
        appState: null,
        config: null,
        filterProvider: null,
        eventProvider: null,
        // Cached label events from the most recent two filter signatures.
        // Lets a select→deselect roundtrip reuse work, and lets viewport
        // refreshes hit the cache for already-computed locations.
        _labelCache: new Map(), // signature -> Map<locationKey, Event[]>
        _labelCacheOrder: [],   // signatures in MRU order (max 2)
        _lastDisplay: null      // { locationsToDisplay } for moveend label refresh
    };

    const LABEL_CACHE_MAX = 2;

    function _signatureFromCtx(sortCtx) {
        const tagStates = sortCtx.activeFilters.tagStates || {};
        const parts = [];
        for (const tag in tagStates) {
            const s = tagStates[tag];
            if (s && s !== 'unselected') parts.push(`${tag}:${s[0]}`);
        }
        parts.sort();
        // Both dates affect eventsByLatLngInDateRange, so both must be in the
        // signature — otherwise narrowing/widening the end date would return
        // stale label events from the prior range.
        const startMs = sortCtx.selectedStartDate ? sortCtx.selectedStartDate.getTime() : 0;
        const endMs = sortCtx.selectedEndDate ? sortCtx.selectedEndDate.getTime() : 0;
        const forceId = sortCtx.forceDisplayEventId || '';
        return `${startMs}-${endMs}|${forceId}|${parts.join(',')}`;
    }

    function _getOrCreateCacheBucket(signature) {
        let bucket = state._labelCache.get(signature);
        if (bucket) {
            // Move to MRU position
            const idx = state._labelCacheOrder.indexOf(signature);
            if (idx > -1) state._labelCacheOrder.splice(idx, 1);
            state._labelCacheOrder.push(signature);
            return bucket;
        }
        bucket = new Map();
        state._labelCache.set(signature, bucket);
        state._labelCacheOrder.push(signature);
        while (state._labelCacheOrder.length > LABEL_CACHE_MAX) {
            const evicted = state._labelCacheOrder.shift();
            state._labelCache.delete(evicted);
        }
        return bucket;
    }

    // ========================================
    // POPUP CONTENT
    // ========================================

    /**
     * Creates a popup content callback for a location
     * @param {string} locationKey - Location key in "lat,lng" format
     * @returns {Function} Callback that generates popup HTML
     */
    function createPopupContentCallback(locationKey) {
        return () => {
            const selectedDates = state.filterProvider.getSelectedDates();
            const currentPopupFilters = {
                sliderStartDate: selectedDates[0],
                sliderEndDate: selectedDates[1],
                tagStates: state.filterProvider.getTagStates()
            };

            const eventsAtLocationInDateRange = state.appState.eventsByLatLngInDateRange[locationKey] || [];
            const filterFunctions = {
                isEventMatchingTagFilters: (event, tagStates) => FilterManager.isEventMatchingTagFilters(event, tagStates),
                getLocationInfo: (key) => state.appState.locationsByLatLng[key]
            };

            // Handle forced display event (e.g., from search)
            let eventsToDisplay = eventsAtLocationInDateRange;
            const forceDisplayEventId = state.eventProvider.getForceDisplayEventId();
            if (forceDisplayEventId) {
                const isForcedEventPresent = eventsToDisplay.some(e => e.id === forceDisplayEventId);
                if (!isForcedEventPresent) {
                    const forcedEvent = state.appState.eventsById[forceDisplayEventId];
                    if (forcedEvent && forcedEvent.locationKey === locationKey) {
                        eventsToDisplay = [...eventsToDisplay, forcedEvent];
                    }
                }
            }

            const locationInfo = state.appState.locationsByLatLng[locationKey];
            return UIManager.createLocationPopupContent(
                locationInfo,
                eventsToDisplay,
                currentPopupFilters,
                state.appState.geotagsSet,
                filterFunctions,
                forceDisplayEventId,
                selectedDates[0]
            );
        };
    }

    // ========================================
    // MARKER DISPLAY
    // ========================================

    /**
     * Displays markers for locations with matching events
     * Builds popup callbacks and updates MapManager's GeoJSON data
     *
     * @param {Object} locationsToDisplay - Object mapping locationKey to array of events
     */
    function _buildSortCtx() {
        const selectedDates = state.filterProvider.getSelectedDates();
        const tagStates = state.filterProvider.getTagStates();
        // Derive tag-state Sets ONCE per render, not per location. Hands them
        // to sortEventsForLocation via ctx.tagSets so the inner loop skips the
        // O(|tagStates|) Object.entries+filter work per call.
        const selectedTagsSet = new Set();
        const requiredTagsSet = new Set();
        const forbiddenTagsSet = new Set();
        for (const tag in tagStates) {
            const s = tagStates[tag];
            if (s === 'selected' || s === 'required') selectedTagsSet.add(tag);
            if (s === 'required') requiredTagsSet.add(tag);
            else if (s === 'forbidden') forbiddenTagsSet.add(tag);
        }
        return {
            activeFilters: { tagStates, sliderStartDate: selectedDates[0] },
            filterFunctions: { getLocationInfo: (key) => state.appState.locationsByLatLng[key] },
            selectedStartDate: selectedDates[0],
            selectedEndDate: selectedDates[1],
            forceDisplayEventId: state.eventProvider.getForceDisplayEventId(),
            tagSets: { selectedTagsSet, requiredTagsSet, forbiddenTagsSet }
        };
    }

    function displayEventsOnMap(locationsToDisplay) {
        const FP = (typeof window !== 'undefined' && window.FilterProfiler) || null;
        if (FP) FP.mark('fp:dom:start');

        state._lastDisplay = { locationsToDisplay };

        // Build popup content callbacks for all locations
        const callbacks = new Map();
        for (const locationKey in locationsToDisplay) {
            if (locationsToDisplay[locationKey].length === 0) continue;
            callbacks.set(locationKey, createPopupContentCallback(locationKey));
        }

        if (FP) {
            FP.mark('fp:dom:callbacks');
            FP.measure('fp:dom:buildCallbacks', 'fp:dom:start', 'fp:dom:callbacks');
        }

        const sortCtx = _buildSortCtx();

        // Only compute popup-ordered labels for in-viewport locations. Off-screen
        // markers fall back to the raw event order — when the user pans to them,
        // moveend triggers refreshLabelsForViewport() to upgrade them.
        const visibleSet = state.appState.currentlyVisibleMatchingLocationKeys;
        const useViewport = visibleSet && typeof visibleSet.has === 'function' && visibleSet.size > 0;

        const signature = _signatureFromCtx(sortCtx);
        const cacheBucket = _getOrCreateCacheBucket(signature);

        const labelEventsByKey = {};
        let _computed = 0, _cached = 0, _skipped = 0;
        for (const locationKey of callbacks.keys()) {
            const eventsAtLocation = state.appState.eventsByLatLngInDateRange[locationKey] || [];
            if (eventsAtLocation.length === 0) {
                labelEventsByKey[locationKey] = locationsToDisplay[locationKey];
                continue;
            }
            if (useViewport && !visibleSet.has(locationKey)) {
                labelEventsByKey[locationKey] = locationsToDisplay[locationKey];
                _skipped++;
                continue;
            }
            const cached = cacheBucket.get(locationKey);
            if (cached) {
                labelEventsByKey[locationKey] = cached;
                _cached++;
                continue;
            }
            const { sectionEvents } = PopupContentBuilder.getDefaultSectionAndEvents(eventsAtLocation, sortCtx);
            cacheBucket.set(locationKey, sectionEvents);
            labelEventsByKey[locationKey] = sectionEvents;
            _computed++;
        }

        if (FP && FP._active) {
            FP.mark('fp:dom:labelLoop');
            FP.measure('fp:dom:labelLoop', 'fp:dom:callbacks', 'fp:dom:labelLoop');
            console.log(`  [dom labelLoop] computed ${_computed} · cached ${_cached} · skipped(off-viewport) ${_skipped}`);
        }

        // Update the WebGL marker data — pass the popup-sorted events so the
        // secondary label and "+N" count agree with the popup.
        MapManager.updateMarkerData(
            labelEventsByKey,
            state.appState.locationsByLatLng,
            callbacks
        );

        if (FP) {
            FP.mark('fp:dom:end');
            FP.measure('fp:dom:updateMarkerData', 'fp:dom:labelLoop', 'fp:dom:end');
        }

        // Idle-warm the cache for off-viewport locations so subsequent pans
        // are instant. Runs in chunks during browser idle time so it never
        // blocks user interaction.
        _scheduleIdleWarm(sortCtx, locationsToDisplay);
    }

    let _idleWarmHandle = null;
    function _scheduleIdleWarm(sortCtx, locationsToDisplay) {
        if (_idleWarmHandle != null) {
            (window.cancelIdleCallback || clearTimeout)(_idleWarmHandle);
            _idleWarmHandle = null;
        }
        const ric = window.requestIdleCallback || ((cb) => setTimeout(() => cb({ timeRemaining: () => 16, didTimeout: false }), 50));
        const signature = _signatureFromCtx(sortCtx);
        const cacheBucket = _getOrCreateCacheBucket(signature);
        const keysToWarm = [];
        for (const locationKey in locationsToDisplay) {
            if (locationsToDisplay[locationKey].length === 0) continue;
            if (cacheBucket.has(locationKey)) continue;
            keysToWarm.push(locationKey);
        }
        if (keysToWarm.length === 0) return;

        let i = 0;
        const step = (deadline) => {
            // If the user has triggered a new render in the meantime, the cache
            // bucket signature will differ — bail out so we don't waste work.
            const currentSig = _signatureFromCtx(_buildSortCtx());
            if (currentSig !== signature) { _idleWarmHandle = null; return; }

            while (i < keysToWarm.length && deadline.timeRemaining() > 1) {
                const key = keysToWarm[i++];
                if (cacheBucket.has(key)) continue;
                const eventsAtLocation = state.appState.eventsByLatLngInDateRange[key] || [];
                if (eventsAtLocation.length === 0) continue;
                const { sectionEvents } = PopupContentBuilder.getDefaultSectionAndEvents(eventsAtLocation, sortCtx);
                cacheBucket.set(key, sectionEvents);
            }
            if (i < keysToWarm.length) {
                _idleWarmHandle = ric(step);
            } else {
                _idleWarmHandle = null;
            }
        };
        _idleWarmHandle = ric(step);
    }

    /**
     * Refreshes marker labels for newly-visible locations after a viewport change.
     * Cheaper than displayEventsOnMap — reuses cached locations and only computes
     * for locations that just entered the viewport.
     */
    function refreshLabelsForViewport() {
        if (!state._lastDisplay) return;
        const { locationsToDisplay } = state._lastDisplay;
        const visibleSet = state.appState.currentlyVisibleMatchingLocationKeys;
        if (!visibleSet || typeof visibleSet.has !== 'function') return;

        const sortCtx = _buildSortCtx();
        const signature = _signatureFromCtx(sortCtx);
        const cacheBucket = _getOrCreateCacheBucket(signature);

        let dirty = false;
        const labelEventsByKey = {};
        for (const locationKey in locationsToDisplay) {
            const events = locationsToDisplay[locationKey];
            if (!events || events.length === 0) continue;
            const eventsAtLocation = state.appState.eventsByLatLngInDateRange[locationKey] || [];
            if (eventsAtLocation.length === 0) {
                labelEventsByKey[locationKey] = events;
                continue;
            }
            if (!visibleSet.has(locationKey)) {
                labelEventsByKey[locationKey] = events;
                continue;
            }
            const cached = cacheBucket.get(locationKey);
            if (cached) {
                labelEventsByKey[locationKey] = cached;
                continue;
            }
            const { sectionEvents } = PopupContentBuilder.getDefaultSectionAndEvents(eventsAtLocation, sortCtx);
            cacheBucket.set(locationKey, sectionEvents);
            labelEventsByKey[locationKey] = sectionEvents;
            dirty = true;
        }
        if (!dirty) return;

        // Build callbacks again so MapManager has the same shape it expects.
        const callbacks = new Map();
        for (const locationKey in labelEventsByKey) {
            if (labelEventsByKey[locationKey] && labelEventsByKey[locationKey].length > 0) {
                callbacks.set(locationKey, createPopupContentCallback(locationKey));
            }
        }
        MapManager.updateMarkerData(
            labelEventsByKey,
            state.appState.locationsByLatLng,
            callbacks
        );
    }

    /**
     * Updates the content of an open popup with current filters
     *
     * @param {maplibregl.Popup} openPopup - The open popup to update
     * @returns {boolean} True if popup was updated, false otherwise
     */
    /**
     * Force a rebuild of the currently open popup/bottom sheet, bypassing the
     * unchanged-content early-out in updateOpenPopupContent (whose signature
     * keys on event ids/tags/dates, not description text). Used when deferred
     * descriptions arrive for events whose popup is already open.
     */
    function refreshOpenPopupContent() {
        state._popupContentSig = null;
        return updateOpenPopupContent(MapManager.getCurrentPopup());
    }

    function updateOpenPopupContent(openPopup) {
        // Handle sheet detail case (mobile) — openPopup is null but sheet is open
        const isSheetDetail = !openPopup && typeof Sheet !== 'undefined' && Sheet.isDetailMode();
        if (!openPopup && !isSheetDetail) return false;

        const locationKey = isSheetDetail
            ? Sheet.getCurrentLocationKey()
            : MapManager.getCurrentPopupLocationKey();
        if (!locationKey) return false;

        const locationInfo = state.appState.locationsByLatLng[locationKey];
        const eventsAtLocationInDateRange = state.appState.eventsByLatLngInDateRange[locationKey] || [];

        const selectedDates = state.filterProvider.getSelectedDates();
        const currentPopupFilters = {
            sliderStartDate: selectedDates[0],
            sliderEndDate: selectedDates[1],
            tagStates: state.filterProvider.getTagStates()
        };

        const filterFunctions = {
            isEventMatchingTagFilters: (event, tagStates) => FilterManager.isEventMatchingTagFilters(event, tagStates),
            getLocationInfo: (key) => state.appState.locationsByLatLng[key]
        };

        // Handle forced display event
        let eventsToDisplay = eventsAtLocationInDateRange;
        const forceDisplayEventId = state.eventProvider.getForceDisplayEventId();
        if (forceDisplayEventId) {
            const isForcedEventPresent = eventsToDisplay.some(e => e.id === forceDisplayEventId);
            if (!isForcedEventPresent) {
                const forcedEvent = state.appState.eventsById[forceDisplayEventId];
                if (forcedEvent && forcedEvent.locationKey === locationKey) {
                    eventsToDisplay = [...eventsToDisplay, forcedEvent];
                }
            }
        }

        // Early-out: rebuilding the popup DOM is the costliest part of a tag
        // toggle when a popup is open (~3-10ms). The event list at a location is
        // date-filtered, not tag-filtered, so it's stable across tag toggles;
        // the only filter changes that alter this popup's rendering (event sort
        // order, dimming of non-matching events, tag-chip styling) are:
        //   - a change to any required/forbidden tag (can dim/reorder anything), or
        //   - a change to a *selected* tag that actually appears on these events.
        // Toggling a selected tag absent from this location's events — the common
        // case while filtering the whole map with a popup open — can't change
        // anything here, so we skip the rebuild. Signature captures exactly those
        // inputs plus the date range, the event set, and any forced event.
        const tagStates = currentPopupFilters.tagStates || {};
        const localTags = new Set();
        for (const ev of eventsToDisplay) {
            if (ev.tags) for (const t of ev.tags) localTags.add(t);
        }
        const relevantTagParts = [];
        for (const tag in tagStates) {
            const st = tagStates[tag];
            if (st === 'required' || st === 'forbidden') relevantTagParts.push(tag + ':' + st);
            else if (st === 'selected' && localTags.has(tag)) relevantTagParts.push(tag + ':s');
        }
        relevantTagParts.sort();
        const contentSig = [
            locationKey,
            currentPopupFilters.sliderStartDate, currentPopupFilters.sliderEndDate,
            forceDisplayEventId || '',
            eventsToDisplay.map(e => e.id).join(','),
            relevantTagParts.join('|')
        ].join('§');

        if (!forceDisplayEventId && state._popupContentSig === contentSig) {
            return true; // popup already shows the current content — nothing to do
        }

        // Preserve the currently active tab across rebuilds
        const currentPopupEl = isSheetDetail
            ? document.querySelector('#sheet .sheet-detail .maplibre-popup-content')
            : openPopup.getElement()?.querySelector('.maplibre-popup-content');
        const activeTabBtn = currentPopupEl?.querySelector('.popup-tab-bar .popup-tab.active');
        const previousActiveTab = activeTabBtn ? activeTabBtn.textContent : null;

        const newContent = UIManager.createLocationPopupContent(
            locationInfo,
            eventsToDisplay,
            currentPopupFilters,
            state.appState.geotagsSet,
            filterFunctions,
            forceDisplayEventId,
            selectedDates[0],
            previousActiveTab
        );

        // Update popup content
        const wrapper = document.createElement('div');
        wrapper.className = 'maplibre-popup-content';
        if (newContent instanceof HTMLElement) {
            wrapper.appendChild(newContent);
        } else {
            wrapper.innerHTML = newContent;
        }
        if (isSheetDetail) {
            Sheet.updateContent(wrapper);
        } else {
            openPopup.setDOMContent(wrapper);
        }

        // Clear forced display after updating
        state.eventProvider.setForceDisplayEventId(null);

        // Remember what we just rendered so an unrelated next toggle can skip
        // the rebuild. Forced-display renders inject a transient event, so don't
        // cache them as the steady-state signature.
        state._popupContentSig = forceDisplayEventId ? null : contentSig;

        return true;
    }

    /**
     * Finds the currently open popup or sheet detail if any
     * @returns {Object|null} Object with {popup, locationKey} or null
     */
    function findOpenPopup() {
        const popup = MapManager.getCurrentPopup();
        const locationKey = MapManager.getCurrentPopupLocationKey();
        if (popup) return { popup, locationKey };

        // Check sheet detail mode (mobile)
        if (typeof Sheet !== 'undefined' && Sheet.isDetailMode()) {
            return { popup: null, locationKey: Sheet.getCurrentLocationKey() };
        }
        return null;
    }

    /**
     * Checks if a location has matching events based on current tag filters
     * @param {string} locationKey - Location key in "lat,lng" format
     * @returns {boolean} True if location has at least one matching event
     */
    function hasMatchingEvents(locationKey) {
        const eventsAtLocation = state.appState.eventsByLatLngInDateRange[locationKey] || [];
        const currentTagStates = state.filterProvider.getTagStates();
        return eventsAtLocation.some(event =>
            FilterManager.isEventMatchingTagFilters(event, currentTagStates)
        );
    }

    // ========================================
    // PUBLIC API
    // ========================================

    function init(config) {
        state.appState = config.appState;
        state.config = config.config;
        state.filterProvider = config.filterProvider;
        state.eventProvider = config.eventProvider;
    }

    /**
     * Fly to a location on the map and open its popup
     * @param {number} lat - Latitude
     * @param {number} lng - Longitude
     * @param {string|null} [eventIdToForce=null] - Event ID to force display
     */
    function flyToLocationAndOpenPopup(lat, lng, eventIdToForce = null) {
        if (state.eventProvider && state.eventProvider.setForceDisplayEventId) {
            state.eventProvider.setForceDisplayEventId(eventIdToForce);
        }

        const locationKey = `${lat},${lng}`;

        // Register a popup callback for this location (in case it's filtered out)
        MapManager.registerPopupCallback(locationKey, createPopupContentCallback(locationKey));

        // Open the popup at the coordinates
        MapManager.openPopupAtCoordinates(locationKey, [lng, lat]);
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        init,
        displayEventsOnMap,
        refreshLabelsForViewport,
        updateOpenPopupContent,
        refreshOpenPopupContent,
        findOpenPopup,
        hasMatchingEvents,
        createPopupContentCallback,
        flyToLocationAndOpenPopup
    };
})();
