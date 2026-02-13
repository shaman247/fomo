/**
 * HistoryManager — browser history (pushState/popstate) for back/forward navigation
 *
 * Pushes a full state snapshot on every discrete user action (marker click,
 * tag toggle, date change, tab switch, sheet snap). Continuous changes
 * (map pan, search typing) don't push — their values are captured in
 * the next discrete push.
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

        // Dates: convert to ISO strings
        const rawDates = cb.getSelectedDates();
        const dates = rawDates.map(d => d instanceof Date ? d.toISOString().split('T')[0] : '');

        // Bottom sheet
        let bottomSheet = { mode: 'closed', tab: 0, snap: 0 };
        if (BottomSheet.isDetailMode()) {
            bottomSheet = { mode: 'detail', tab: -1, snap: BottomSheet.getCurrentSnap() };
        } else if (BottomSheet.isOpen()) {
            bottomSheet = { mode: 'browse', tab: BottomSheet.getActiveTab(), snap: BottomSheet.getCurrentSnap() };
        }

        return {
            lat: center.lat,
            lng: center.lng,
            zoom: map.getZoom(),
            selectedLocationKey: cb.getSelectedLocationKey(),
            tags,
            dates,
            searchTerm: cb.getSearchTerm(),
            bottomSheet
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

        // Bottom sheet
        if (a.bottomSheet.mode !== b.bottomSheet.mode) return false;
        if (a.bottomSheet.tab !== b.bottomSheet.tab) return false;
        if (a.bottomSheet.snap !== b.bottomSheet.snap) return false;

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

    /**
     * Suppress pushes during fn(). Use when a single user action triggers
     * multiple events that each call push() — e.g. _clearDetail() fires
     * popupclose (→ push) before the tab switch (→ push). Wrapping the
     * first part in batch() ensures only the final push captures state.
     */
    function batch(fn) {
        const was = state.isRestoringState;
        state.isRestoringState = true;
        try { fn(); } finally { state.isRestoringState = was; }
    }

    // ========================================
    // RESTORE
    // ========================================

    function _closeCurrentPopup() {
        const popup = MapManager.getCurrentPopup();
        if (popup) {
            popup.remove();
        } else if (BottomSheet.isDetailMode()) {
            BottomSheet.close();
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
                const currentStart = currentDates[0] ? currentDates[0].toISOString().split('T')[0] : '';
                const currentEnd = currentDates[1] ? currentDates[1].toISOString().split('T')[0] : '';

                if (savedStart !== currentStart || savedEnd !== currentEnd) {
                    datePicker.setDate(savedDates);
                    datesChanged = true;
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
                const [lat, lng] = historyState.selectedLocationKey.split(',').map(Number);
                MarkerController.flyToLocationAndOpenPopup(lat, lng, null);
            }
        } else if (currentKey) {
            _closeCurrentPopup();
        }

        // 7. Bottom sheet (mobile)
        const isMobile = window.innerWidth <= Constants.UI.MOBILE_BREAKPOINT;
        if (isMobile) {
            const bs = historyState.bottomSheet || { mode: 'closed', tab: 0, snap: 0 };

            if (!historyState.selectedLocationKey) {
                if (bs.mode === 'browse') {
                    if (BottomSheet.isDetailMode()) BottomSheet.close();
                    BottomSheet.switchTab(bs.tab);
                    BottomSheet.snapTo(bs.snap);
                } else {
                    BottomSheet.close();
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
        batch,
        isRestoring
    };
})();
