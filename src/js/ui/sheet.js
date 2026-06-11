/**
 * Sheet Module
 *
 * The unified list / search-results sheet, shared by desktop and mobile. Both
 * host the same content — `#tags-wrapper` / `#results-container`, the render
 * target FilterPanelUI and ListView write into (event list when the search box
 * is empty, search sections when a term is active) — but dock differently:
 *
 *   Desktop (>768px): a panel that slides in from the LEFT edge. A separate
 *   floating "Show list" handle (#sheet-handle), vertically centered at the
 *   screen's left edge, opens it; it is hidden while the sheet is open — the
 *   open sheet is dismissed by clicking empty map space (MapManager's click
 *   handler calls dismissToMini()). The open/collapsed state persists across
 *   reloads via localStorage (default collapsed). Marker popups stay as
 *   floating MapLibre popups.
 *
 *   Mobile (≤768px): a bottom sheet with a drag grip and snap points
 *   CLOSED ↔ PEEK (48vh) ↔ FULL (85vh). CLOSED is a mini strip, not fully
 *   hidden: a CSS min-height keeps the sheet's top edge (the grip) peeking
 *   at the bottom of the screen, so reopening is a tap or drag-up on the
 *   strip itself. The sheet also has a DETAIL mode: tapping a marker shows
 *   the location popup content inside the sheet (in `.sheet-detail`, swapped
 *   with the browse content); a horizontal swipe dismisses it back to browse.
 *
 * This module owns only the open/snap/detail state — it does not render the
 * browse content. Whenever the browse content newly becomes visible (desktop
 * open, mobile snap up from closed, detail dismissed) it fires `onToggle(true)`
 * so FilterPanelUI re-renders; the list is skipped while hidden to avoid
 * rendering 200 cards off-screen on every map pan.
 *
 * @module Sheet
 */
const Sheet = (() => {
    // ========================================
    // CONSTANTS
    // ========================================

    const STORAGE_KEY_OPEN = 'leftSheetOpen';   // kept from the old left sheet for continuity

    const SNAP_PEEK = 0.48;          // Content visible
    const SNAP_FULL = 0.85;          // Full content view
    const VELOCITY_THRESHOLD = 0.5;  // px/ms — threshold for velocity-based snap
    const DISMISS_VELOCITY = 0.3;    // px/ms — threshold for swipe-to-close
    const MAX_VELOCITY_SAMPLES = 5;
    const DETAIL_SWIPE_THRESHOLD = 35; // px — minimum horizontal distance to dismiss detail

    // ========================================
    // STATE
    // ========================================

    const state = {
        mapInstance: null,

        // DOM (static markup in index.html)
        sheet: null,        // #sheet
        dragArea: null,     // .sheet-drag-area (mobile grip)
        browseEl: null,     // #tags-wrapper
        detailEl: null,     // .sheet-detail
        edgeHandle: null,   // #sheet-handle (desktop "Show list" button)

        // Desktop open/collapsed state (persisted)
        desktopOpen: false,

        // Mobile snap state
        currentSnap: 0,

        // Detail mode (mobile)
        activeLocationKey: null,
        activeLngLat: null,
        detailHasPopupTabs: false,

        // Vertical drag gesture (grip)
        isDragging: false,
        dragStartY: 0,
        dragStartHeight: 0,
        dragMoved: false,
        velocitySamples: [],

        // Detail horizontal swipe gesture
        detailSwipeStartX: 0,
        detailSwipeStartY: 0,

        onToggle: null,     // callback(true) — re-render content when browse becomes visible
        initialized: false,
        wasDesktop: null,   // breakpoint tracking for resize transitions
    };

    // ========================================
    // HELPERS
    // ========================================

    function isDesktop() {
        return !Utils.isMobileLayout();
    }

    /** Notify the content layer that the browse content newly became visible. */
    function _emitBrowseShown() {
        if (typeof state.onToggle === 'function') state.onToggle(true);
    }

    // ========================================
    // DESKTOP — open / collapse (click toggle, persisted)
    // ========================================

    /** Toggle a class on both the sheet and the (separate) floating handle. */
    function _toggleBoth(cls, on) {
        if (state.sheet) state.sheet.classList.toggle(cls, on);
        if (state.edgeHandle) state.edgeHandle.classList.toggle(cls, on);
    }

    function _applyOpenState() {
        _toggleBoth('sheet-collapsed', !state.desktopOpen);
        // The handle is hidden while the sheet is open (CSS); its label is the
        // static "Show list" from the markup. Empty-map clicks dismiss the open
        // sheet (MapManager's click handler).
        if (state.edgeHandle) {
            state.edgeHandle.setAttribute('aria-expanded', state.desktopOpen ? 'true' : 'false');
        }
    }

    /**
     * Measure the floating top filter bar and push the sheet's scroll content
     * below it, so the logo / search / chips never overlap the list (desktop).
     */
    function _measureTopOffset() {
        if (!isDesktop()) return;
        const panel = document.getElementById('filter-panel');
        if (!panel) return;
        const rect = panel.getBoundingClientRect();
        const top = Math.max(48, Math.round(rect.bottom) + 8);
        document.documentElement.style.setProperty('--sheet-content-top', top + 'px');
    }

    function _persist() {
        Utils.SafeStorage.setItem(STORAGE_KEY_OPEN, state.desktopOpen ? '1' : '0');
    }

    function _restore() {
        state.desktopOpen = Utils.SafeStorage.getItem(STORAGE_KEY_OPEN) === '1';
    }

    function _setDesktopOpen(v) {
        const next = !!v;
        const changed = next !== state.desktopOpen;
        state.desktopOpen = next;
        if (state.desktopOpen) _measureTopOffset();
        _applyOpenState();
        _persist();
        if (changed && state.desktopOpen) _emitBrowseShown();
    }

    // ========================================
    // MOBILE — snap / drag
    // ========================================

    function _showBrowse() {
        if (state.browseEl) state.browseEl.style.display = '';
        if (state.detailEl) state.detailEl.style.display = 'none';
    }

    function _showDetail() {
        if (state.browseEl) state.browseEl.style.display = 'none';
        if (state.detailEl) state.detailEl.style.display = 'block';
    }

    function _snapTo(snapRatio) {
        const prev = state.currentSnap;
        state.currentSnap = snapRatio;
        const h = window.innerHeight * snapRatio;
        // Snap 0 leaves the CSS min-height floor in charge — the mini strip.
        state.sheet.style.height = `${h}px`;
        state.sheet.classList.toggle('open', snapRatio > 0);
        state.sheet.classList.toggle('full', snapRatio >= SNAP_FULL);
        // Browse content newly visible → ask the content layer to render it.
        if (prev <= 0 && snapRatio > 0 && !state.activeLocationKey) {
            _emitBrowseShown();
        }
    }

    function _clearDetail() {
        const closedKey = state.activeLocationKey;
        const closedLngLat = state.activeLngLat;

        state.activeLocationKey = null;
        state.activeLngLat = null;
        state.detailHasPopupTabs = false;

        if (state.detailEl) state.detailEl.innerHTML = '';
        _showBrowse();

        // Browse content is stale/empty behind the detail layer — repopulate
        // if the sheet is still open.
        if (state.currentSnap > 0) _emitBrowseShown();

        // Clear marker highlight
        if (typeof MapManager !== 'undefined') {
            MapManager.clearActiveState();
        }

        // Fire popupclose for state coordination
        if (state.mapInstance && closedKey) {
            state.mapInstance.fire('popupclose', {
                popup: null,
                locationKey: closedKey,
                lngLat: closedLngLat
            });
        }
    }

    /**
     * Closes the sheet, then clears detail if active. Close-first so
     * _clearDetail doesn't trigger a browse re-render that immediately
     * disappears off-screen.
     * animate=false snaps shut instantly (desktop resize, history restore).
     */
    function _clearAndClose(animate) {
        if (animate) {
            _snapTo(0);
        } else {
            state.sheet.classList.add('no-transition');
            _snapTo(0);
            state.sheet.offsetHeight; // force reflow so the transition skip applies
            state.sheet.classList.remove('no-transition');
        }
        if (state.activeLocationKey) _clearDetail();
    }

    // --- Vertical sheet drag (grip) ---

    function _onDragStart(e) {
        const touch = e.touches[0];
        state.isDragging = true;
        state.dragMoved = false;
        state.dragStartY = touch.clientY;
        state.dragStartHeight = _getCurrentHeight();
        state.velocitySamples = [{ time: Date.now(), y: touch.clientY }];
        state.sheet.classList.add('no-transition');
    }

    function _onDragMove(e) {
        if (!state.isDragging) return;

        const touch = e.touches[0];
        const deltaY = touch.clientY - state.dragStartY;
        if (Math.abs(deltaY) > 2) state.dragMoved = true;

        // Pulling down → prevent browser scroll, drag sheet
        if (deltaY > 0) {
            e.preventDefault();
        }

        const viewportHeight = window.innerHeight;
        let newHeight = state.dragStartHeight - deltaY;

        // Rubber-band above full snap
        const maxH = viewportHeight * SNAP_FULL;
        if (newHeight > maxH) {
            const overshoot = newHeight - maxH;
            newHeight = maxH + overshoot * 0.3;
        }

        newHeight = Math.max(0, newHeight);
        state.sheet.style.height = `${newHeight}px`;
        state.sheet.classList.toggle('open', newHeight > 0);

        // Record velocity sample
        state.velocitySamples.push({ time: Date.now(), y: touch.clientY });
        if (state.velocitySamples.length > MAX_VELOCITY_SAMPLES) {
            state.velocitySamples.shift();
        }
    }

    function _onDragEnd() {
        if (!state.isDragging) return;
        _cancelDrag();

        // A tap (no movement) is handled by the click handlers, not the drag.
        if (!state.dragMoved) {
            _snapTo(state.currentSnap);
            return;
        }

        const velocity = _calculateVelocity(); // positive = downward
        const currentHeight = _getCurrentHeight();
        const viewportHeight = window.innerHeight;
        const currentRatio = currentHeight / viewportHeight;

        // Fast upward swipe → full
        if (velocity < -VELOCITY_THRESHOLD) {
            _snapTo(SNAP_FULL);
            HistoryManager.push();
            return;
        }

        // Fast downward swipe → close
        if (velocity > DISMISS_VELOCITY) {
            _clearAndClose(true);
            HistoryManager.push();
            return;
        }

        // Snap to nearest of CLOSED, PEEK, FULL
        const snaps = [0, SNAP_PEEK, SNAP_FULL];
        const nearest = snaps.reduce((best, snap) =>
            Math.abs(currentRatio - snap) < Math.abs(currentRatio - best) ? snap : best
        );

        if (nearest <= 0) {
            _clearAndClose(true);
        } else {
            _snapTo(nearest);
        }
        HistoryManager.push();
    }

    // --- Detail horizontal swipe (dismiss back to browse) ---

    function _onDetailSwipeStart(e) {
        if (!state.activeLocationKey) return;
        const touch = e.touches[0];
        state.detailSwipeStartX = touch.clientX;
        state.detailSwipeStartY = touch.clientY;
    }

    function _onDetailSwipeEnd(e) {
        if (!state.activeLocationKey) return;
        if (state.detailHasPopupTabs) return; // Don't dismiss via swipe when popup has its own tabs
        const touch = e.changedTouches?.[0];
        if (!touch) return;

        const dx = Math.abs(touch.clientX - state.detailSwipeStartX);
        const dy = Math.abs(touch.clientY - state.detailSwipeStartY);

        // Must be primarily horizontal and past threshold
        if (dx >= DETAIL_SWIPE_THRESHOLD && dx > dy * 1.5) {
            _clearDetail();
            HistoryManager.push();
        }
    }

    // --- Taps ---

    /** Grip tap: opens the closed (mini-strip) sheet to PEEK, otherwise steps
     *  it down FULL → PEEK → closed. (After a real drag the browser doesn't
     *  fire click — touchmove preventDefaults.) */
    function _onGripTap() {
        if (state.currentSnap <= 0) {
            _snapTo(SNAP_PEEK);
        } else if (state.currentSnap >= SNAP_FULL) {
            _snapTo(SNAP_PEEK);
        } else {
            _clearAndClose(true);
        }
        HistoryManager.push();
    }

    // --- Shared drag helpers ---

    function _cancelDrag() {
        state.isDragging = false;
        state.sheet.classList.remove('no-transition');
    }

    function _calculateVelocity() {
        const s = state.velocitySamples;
        if (s.length < 2) return 0;
        const dt = s[s.length - 1].time - s[0].time;
        if (dt === 0) return 0;
        return (s[s.length - 1].y - s[0].y) / dt; // px/ms, positive = down
    }

    function _getCurrentHeight() {
        const h = parseFloat(state.sheet.style.height);
        if (!isNaN(h) && h > 0) return h;
        // Closed: the CSS min-height keeps the mini grip strip rendered —
        // measure it so a drag starting from the strip tracks the finger
        // without an initial jump.
        return state.sheet.offsetHeight || window.innerHeight * state.currentSnap;
    }

    // ========================================
    // RESIZE
    // ========================================

    function _onResize() {
        const desktop = isDesktop();
        if (desktop !== state.wasDesktop) {
            state.wasDesktop = desktop;
            if (desktop) {
                // Crossed to desktop: drop all mobile state (inline height would
                // squash the left-docked panel), re-apply the persisted state.
                if (state.activeLocationKey) _clearDetail();
                state.currentSnap = 0;
                state.sheet.style.height = '';
                state.sheet.classList.remove('open', 'full');
                _applyOpenState();
                _measureTopOffset();
            } else {
                // Crossed to mobile: start closed (mini strip).
                _toggleBoth('sheet-collapsed', false);
                state.sheet.classList.add('no-transition');
                _snapTo(0);
                state.sheet.offsetHeight;
                state.sheet.classList.remove('no-transition');
            }
            return;
        }
        if (desktop) {
            _measureTopOffset();
        } else if (state.currentSnap > 0) {
            _snapTo(state.currentSnap); // recompute px height for the new viewport
        }
    }

    // ========================================
    // PUBLIC API
    // ========================================

    function open() {
        if (isDesktop()) {
            _setDesktopOpen(true);
        } else if (state.currentSnap < SNAP_PEEK) {
            _snapTo(SNAP_PEEK);
        }
    }

    function close() {
        if (isDesktop()) {
            _setDesktopOpen(false);
        } else {
            _clearAndClose(false);
        }
    }

    function dismissToMini() {
        if (isDesktop()) {
            _setDesktopOpen(false);
        } else {
            _clearAndClose(true);
        }
    }

    function isOpen() {
        return isDesktop() ? state.desktopOpen : state.currentSnap > 0;
    }

    /** Whether the browse content (#results-container) is actually on screen —
     *  the gate for rendering the list view. */
    function isBrowseVisible() {
        if (isDesktop()) return state.desktopOpen;
        return state.currentSnap > 0 && !state.activeLocationKey;
    }

    function isDetailMode() {
        return state.activeLocationKey !== null;
    }

    function snapTo(snap) {
        if (isDesktop()) {
            _setDesktopOpen(snap > 0);
        } else {
            _snapTo(snap);
        }
    }

    /**
     * Shows a location's popup content inside the sheet (mobile detail mode).
     */
    function openDetail(locationKey, lngLat, contentElement) {
        // Already showing this location
        if (state.activeLocationKey === locationKey && state.currentSnap > 0) return;

        state.activeLocationKey = locationKey;
        state.activeLngLat = lngLat;

        // Set detail content
        state.detailEl.innerHTML = '';
        state.detailEl.appendChild(contentElement);
        state.detailEl.scrollTop = 0;
        _showDetail();

        // Track whether popup has its own tab bar (prevents swipe-to-dismiss)
        state.detailHasPopupTabs = !!contentElement.querySelector('.popup-tab-bar');

        // Open sheet if closed
        if (state.currentSnap < SNAP_PEEK) {
            _snapTo(SNAP_PEEK);
        }

        // Fire popupopen for state coordination
        if (state.mapInstance) {
            state.mapInstance.fire('popupopen', {
                popup: null,
                locationKey,
                lngLat
            });
        }
    }

    function updateContent(contentElement) {
        if (!state.activeLocationKey) return;
        state.detailEl.innerHTML = '';
        state.detailEl.appendChild(contentElement);
        state.detailEl.scrollTop = 0;
        state.detailHasPopupTabs = !!contentElement.querySelector('.popup-tab-bar');
    }

    function setMap(mapInstance) {
        state.mapInstance = mapInstance;
    }

    /**
     * @param {Object} config
     * @param {Function} [config.onToggle] - called with `true` whenever the
     *   browse content newly becomes visible (open / snap up / detail dismissed)
     */
    function init(config = {}) {
        if (state.initialized) return;
        state.sheet = document.getElementById('sheet');
        if (!state.sheet) return;
        state.dragArea = state.sheet.querySelector('.sheet-drag-area');
        state.browseEl = document.getElementById('tags-wrapper');
        state.detailEl = state.sheet.querySelector('.sheet-detail');
        state.edgeHandle = document.getElementById('sheet-handle');
        state.onToggle = config.onToggle || null;
        state.wasDesktop = isDesktop();

        // Desktop state (persisted)
        _restore();
        _measureTopOffset();
        _applyOpenState();

        // Desktop edge handle — only visible (and clickable) while collapsed
        if (state.edgeHandle) {
            state.edgeHandle.addEventListener('click', () => _setDesktopOpen(true));
        }

        // Mobile grip — drag + tap. Touch events follow the touchstart target,
        // so move/end fire even when the finger leaves the grip.
        if (state.dragArea) {
            state.dragArea.addEventListener('touchstart', _onDragStart, { passive: true });
            state.dragArea.addEventListener('touchmove', _onDragMove, { passive: false });
            state.dragArea.addEventListener('touchend', _onDragEnd, { passive: true });
            state.dragArea.addEventListener('touchcancel', _onDragEnd, { passive: true });
            state.dragArea.addEventListener('click', _onGripTap);
        }

        // Detail content — horizontal swipe to dismiss
        if (state.detailEl) {
            state.detailEl.addEventListener('touchstart', _onDetailSwipeStart, { passive: true });
            state.detailEl.addEventListener('touchend', _onDetailSwipeEnd, { passive: true });
        }

        window.addEventListener('resize', _onResize);

        state.initialized = true;
    }

    return {
        init,
        setMap,
        open,
        close,
        dismissToMini,
        isOpen,
        isBrowseVisible,
        isDetailMode,
        openDetail,
        updateContent,
        snapTo,
        getCurrentSnap: () => (isDesktop() ? 0 : state.currentSnap),
        getCurrentLocationKey: () => state.activeLocationKey,
        measureTopOffset: _measureTopOffset,
        SNAP_PEEK,
    };
})();
