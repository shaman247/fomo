/**
 * HistoryManager — browser history (pushState/popstate) for back/forward navigation
 *
 * Pushes a full state snapshot on every discrete user action (marker click,
 * tag toggle, date change, sheet snap). Continuous changes (map pan, search
 * typing) don't push — their values are captured in the next discrete push.
 *
 * @module HistoryManager
 */
const HistoryManager = (() => {
    const state = {
        map: null,
        callbacks: null,
        isRestoringState: false,
        lastPushedState: null,
        initialized: false
    };

    // ========================================
    // CAPTURE
    // ========================================

    function _captureState() {
        const map = state.map;
        if (!map) return null;

        const center = map.getCenter();
        const cb = state.callbacks;

        // Tags: only store non-unselected
        const tags = Object.fromEntries(
            Object.entries(cb.getTagStates()).filter(([, s]) => s !== 'unselected')
        );

        // Dates: convert to local YYYY-MM-DD strings (toISOString would shift
        // to the next day in any timezone west of UTC for evening captures)
        const rawDates = cb.getSelectedDates();
        const dates = rawDates.map(d => d instanceof Date ? URLParams.formatDate(d) : '');

        // Sheet (mobile only — desktop open state persists via localStorage,
        // and back/forward shouldn't toggle a docked panel)
        let sheet = { mode: 'closed', snap: 0 };
        if (Sheet.isDetailMode()) {
            sheet = { mode: 'detail', snap: Sheet.getCurrentSnap() };
        } else if (Utils.isMobileLayout() && Sheet.isOpen()) {
            sheet = { mode: 'browse', snap: Sheet.getCurrentSnap() };
        }

        return {
            lat: center.lat,
            lng: center.lng,
            zoom: map.getZoom(),
            selectedLocationKey: cb.getSelectedLocationKey(),
            tags,
            dates,
            searchTerm: cb.getSearchTerm(),
            sheet
        };
    }

    // ========================================
    // COMPARISON
    // ========================================

    function _statesAreEqual(a, b) {
        if (!a || !b) return false;

        // Map position (with tolerance)
        if (Math.abs(a.lat - b.lat) > 0.00001) return false;
        if (Math.abs(a.lng - b.lng) > 0.00001) return false;
        if (Math.abs(a.zoom - b.zoom) > 0.1) return false;

        // Marker
        if (a.selectedLocationKey !== b.selectedLocationKey) return false;

        // Tags
        const aKeys = Object.keys(a.tags);
        const bKeys = Object.keys(b.tags);
        if (aKeys.length !== bKeys.length) return false;
        for (const key of aKeys) {
            if (a.tags[key] !== b.tags[key]) return false;
        }

        // Dates
        if (a.dates.length !== b.dates.length) return false;
        for (let i = 0; i < a.dates.length; i++) {
            if (a.dates[i] !== b.dates[i]) return false;
        }

        // Search
        if (a.searchTerm !== b.searchTerm) return false;

        // Sheet (read the legacy `bottomSheet` key from pre-rename entries;
        // its extra `tab` field is ignored)
        const as = a.sheet || a.bottomSheet || {};
        const bs = b.sheet || b.bottomSheet || {};
        if (as.mode !== bs.mode) return false;
        if (as.snap !== bs.snap) return false;

        return true;
    }

    // ========================================
    // PUSH
    // ========================================

    function push() {
        if (state.isRestoringState || !state.initialized) return;

        const newState = _captureState();
        if (!newState) return;
        if (_statesAreEqual(state.lastPushedState, newState)) return;

        state.lastPushedState = newState;
        window.history.pushState(newState, '');
    }

    // ========================================
    // RESTORE
    // ========================================

    function _closeCurrentPopup() {
        const popup = MapManager.getCurrentPopup();
        if (popup) {
            popup.remove();
        } else if (Sheet.isDetailMode()) {
            // Desktop panel-detail (popups=panel prototype): back should land
            // on the open list, not collapse the whole panel. Mobile keeps
            // the sheet-close behavior.
            if (!Utils.isMobileLayout() && ProtoFlags.isOn('popups', 'panel')) {
                Sheet.closeDetail();
            } else {
                Sheet.close();
            }
        }
    }

    function _restoreState(historyState) {
        if (!historyState || !state.map) return;

        state.isRestoringState = true;
        const cb = state.callbacks;

        // 1. Map position
        state.map.jumpTo({
            center: [historyState.lng, historyState.lat],
            zoom: historyState.zoom
        });

        // 2. Tags — diff and apply changes (silent; UI rebuild deferred)
        const currentTags = cb.getTagStates();
        const savedTags = historyState.tags || {};
        let tagsChanged = false;

        for (const [tag, tagState] of Object.entries(currentTags)) {
            if (tagState !== 'unselected' && !savedTags[tag]) {
                FilterPanelUI.setTagState(tag, 'unselected');
                tagsChanged = true;
            }
        }
        for (const [tag, tagState] of Object.entries(savedTags)) {
            if (currentTags[tag] !== tagState) {
                FilterPanelUI.setTagState(tag, tagState);
                tagsChanged = true;
            }
        }

        // 3. Dates — set picker, then rebuild the date-filtered event list.
        //    flatpickr.setDate() does NOT trigger onClose, so we call
        //    updateFilteredEventList explicitly.
        let datesChanged = false;
        const savedDates = historyState.dates || [];
        if (savedDates.length >= 2) {
            const datePicker = cb.getDatePicker();
            if (datePicker) {
                const currentDates = datePicker.selectedDates;
                const savedStart = savedDates[0];
                const savedEnd = savedDates[1];
                const currentStart = currentDates[0] ? URLParams.formatDate(currentDates[0]) : '';
                const currentEnd = currentDates[1] ? URLParams.formatDate(currentDates[1]) : '';

                if (savedStart !== currentStart || savedEnd !== currentEnd) {
                    // setDate needs Date objects: flatpickr parses string args
                    // with its display format ("M j"), so YYYY-MM-DD strings
                    // would fail to parse and clear the selection
                    const parsed = savedDates.slice(0, 2).map(s => URLParams.parseDate(s).date);
                    if (parsed.every(Boolean)) {
                        datePicker.setDate(parsed);
                        datesChanged = true;
                    }
                }
            }
        }

        // 4. Rebuild UI if tags or dates changed
        if (datesChanged) cb.updateFilteredEventList();
        if (tagsChanged) FilterPanelUI.updateAllTagVisuals();
        if (tagsChanged || datesChanged) cb.onFilterChange();

        // 5. Search
        const savedSearch = historyState.searchTerm || '';
        if (cb.getSearchTerm() !== savedSearch) {
            cb.performSearch(savedSearch);
        }

        // 6. Marker — open or close
        const currentKey = cb.getSelectedLocationKey();
        if (historyState.selectedLocationKey) {
            if (currentKey !== historyState.selectedLocationKey) {
                if (currentKey) _closeCurrentPopup();
                const ll = Utils.parseLocationKey(historyState.selectedLocationKey);
                if (ll) MarkerController.flyToLocationAndOpenPopup(ll.lat, ll.lng, null);
            }
        } else if (currentKey) {
            _closeCurrentPopup();
        }

        // 7. Sheet (mobile; legacy entries stored it under `bottomSheet`)
        const isMobile = Utils.isMobileLayout();
        if (isMobile) {
            const s = historyState.sheet || historyState.bottomSheet || { mode: 'closed', snap: 0 };

            if (!historyState.selectedLocationKey) {
                if (s.mode === 'browse' && s.snap > 0) {
                    if (Sheet.isDetailMode()) Sheet.close();
                    Sheet.snapTo(s.snap);
                } else {
                    Sheet.close();
                }
            }
        }

        // 8. Update tracking and clear flag after all sync handlers have fired
        state.lastPushedState = historyState;
        requestAnimationFrame(() => {
            state.isRestoringState = false;
        });
    }

    // ========================================
    // INIT
    // ========================================

    function init(map, callbacks) {
        if (state.initialized) return;

        state.map = map;
        state.callbacks = callbacks;
        state.initialized = true;

        // Listen for back/forward
        window.addEventListener('popstate', (e) => {
            _restoreState(e.state);
        });

        // Set initial history entry
        const initialState = _captureState();
        if (initialState) {
            state.lastPushedState = initialState;
            window.history.replaceState(initialState, '');
        }
    }

    // ========================================
    // PUBLIC API
    // ========================================

    function isRestoring() {
        return state.isRestoringState;
    }

    return {
        init,
        push,
        isRestoring
    };
})();
