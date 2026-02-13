/**
 * BottomSheet Module
 *
 * Mobile bottom sheet with tab-based navigation.
 * The tab bar is a permanent fixture at the bottom of the screen.
 * The sheet itself sits above it and is either closed or open (PEEK/FULL).
 *
 * Tab bar: Places | Events | Tags (3 tabs, always present)
 *   - Always visible on mobile (hidden on desktop via CSS)
 *   - No active tab when sheet is closed or in detail mode
 *   - Tapping a tab opens the sheet; tapping the active tab closes it
 *   - Detail mode (marker click) shows popup content with no active tab
 *     Tapping any tab returns to browse mode
 *   - Tabs wrap circularly: swipe right past Tags → Places, left past Places → Tags
 *   - Horizontal swipe on detail popup dismisses it, returns to previous tab
 *
 * Sheet snap points:
 *   CLOSED (0)   — sheet hidden, only tab bar visible
 *   PEEK  (40vh) — content visible
 *   FULL  (85vh) — expanded view
 *
 * Desktop: hidden entirely via CSS. Desktop uses MapLibre floating popups.
 *
 * @module BottomSheet
 */
const BottomSheet = (() => {
    // ========================================
    // CONSTANTS
    // ========================================

    const SNAP_PEEK = 0.40;          // Content visible
    const SNAP_FULL = 0.85;          // Full content view
    const VELOCITY_THRESHOLD = 0.5;  // px/ms — threshold for velocity-based snap
    const DISMISS_VELOCITY = 0.3;    // px/ms — threshold for swipe-to-close
    const MAX_VELOCITY_SAMPLES = 5;
    const TAB_SWIPE_THRESHOLD = 8;   // px — minimum movement to commit to horizontal swipe
    const DETAIL_SWIPE_THRESHOLD = 35; // px — minimum horizontal distance to dismiss detail
    const SWIPE_COMMIT_FRACTION = 0.25; // fraction of viewport width to commit to next tab

    const TAB_KEYS = ['locations', 'events', 'tags'];
    const TAB_LABELS = ['Places', 'Events', 'Tags'];
    const TAB_ICONS = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM7 10h5v5H7v-5z"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M21.41 11.58l-9-9C12.05 2.22 11.55 2 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l9 9c.36.36.86.58 1.41.58s1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41s-.23-1.06-.59-1.42zM5.5 7C4.67 7 4 6.33 4 5.5S4.67 4 5.5 4 7 4.67 7 5.5 6.33 7 5.5 7z"/></svg>'
    ];

    // ========================================
    // STATE
    // ========================================

    const state = {
        mapInstance: null,

        // DOM (created once in init)
        sheetElement: null,
        handleArea: null,
        contentContainer: null,
        browseContentContainer: null,
        detailContentContainer: null,
        // Tab DOM (tab bar lives outside the sheet)
        tabBar: null,
        tabButtons: [],         // 3 browse tab buttons
        tabViewport: null,
        tabTrack: null,
        tabPanels: [],

        // Snap state
        currentSnap: 0,

        // Tab state: -1 = no active tab (closed or detail), 0-2 = browse
        activeTab: -1,

        // Location tracking (detail mode)
        activeLocationKey: null,
        activeLngLat: null,
        preDetailTab: 0,  // tab to restore when exiting detail

        // Vertical drag gesture (handle area)
        isDragging: false,
        dragStartY: 0,
        dragStartHeight: 0,
        velocitySamples: [],

        // Horizontal tab swipe gesture (browse tabs)
        isTabSwiping: false,
        tabSwipeStartX: 0,
        tabTrackStartOffset: 0,

        // Detail horizontal swipe gesture
        detailSwipeStartX: 0,
        detailSwipeStartY: 0,

        // Clone panels for smooth circular swiping
        cloneStart: null,  // clone of last tab (before first real tab)
        cloneEnd: null      // clone of first tab (after last real tab)
    };

    // ========================================
    // DOM CREATION
    // ========================================

    function _createDOM() {
        // Sheet container
        state.sheetElement = document.createElement('div');
        state.sheetElement.id = 'bottom-sheet';

        // Handle area (large touch target for dragging)
        state.handleArea = document.createElement('div');
        state.handleArea.className = 'bottom-sheet-handle-area';
        const handle = document.createElement('div');
        handle.className = 'bottom-sheet-handle';
        state.handleArea.appendChild(handle);

        // Content container
        state.contentContainer = document.createElement('div');
        state.contentContainer.className = 'bottom-sheet-content';

        // Browse content — tab viewport + track + panels
        state.browseContentContainer = document.createElement('div');
        state.browseContentContainer.className = 'bottom-sheet-browse-content';

        state.tabViewport = document.createElement('div');
        state.tabViewport.className = 'bottom-sheet-tab-viewport';

        state.tabTrack = document.createElement('div');
        state.tabTrack.className = 'bottom-sheet-tab-track';

        // Clone of last tab (before first, for smooth circular wrap)
        state.cloneStart = document.createElement('div');
        state.cloneStart.className = 'bottom-sheet-tab-panel';
        state.cloneStart.setAttribute('aria-hidden', 'true');
        state.tabTrack.appendChild(state.cloneStart);

        // Real tab panels
        state.tabPanels = TAB_KEYS.map(key => {
            const panel = document.createElement('div');
            panel.className = 'bottom-sheet-tab-panel';
            panel.dataset.tab = key;
            state.tabTrack.appendChild(panel);
            return panel;
        });

        // Clone of first tab (after last, for smooth circular wrap)
        state.cloneEnd = document.createElement('div');
        state.cloneEnd.className = 'bottom-sheet-tab-panel';
        state.cloneEnd.setAttribute('aria-hidden', 'true');
        state.tabTrack.appendChild(state.cloneEnd);

        state.tabViewport.appendChild(state.tabTrack);
        state.browseContentContainer.appendChild(state.tabViewport);

        // Detail content (location popup)
        state.detailContentContainer = document.createElement('div');
        state.detailContentContainer.className = 'bottom-sheet-detail-content';

        state.contentContainer.appendChild(state.browseContentContainer);
        state.contentContainer.appendChild(state.detailContentContainer);

        // Assemble sheet: handle + content (no tab bar inside)
        state.sheetElement.appendChild(state.handleArea);
        state.sheetElement.appendChild(state.contentContainer);

        // Tab bar — separate element, fixed at bottom of screen
        state.tabBar = document.createElement('div');
        state.tabBar.className = 'bottom-sheet-tab-bar';
        state.tabButtons = TAB_LABELS.map((label, i) => {
            const btn = document.createElement('button');
            btn.className = 'bottom-sheet-tab-button';
            btn.innerHTML = `${TAB_ICONS[i]}<span>${label}</span>`;
            btn.addEventListener('click', () => _onTabClick(i));
            state.tabBar.appendChild(btn);
            return btn;
        });

        // Append both to app container
        const appContainer = document.getElementById('app-container');
        appContainer.appendChild(state.sheetElement);
        appContainer.appendChild(state.tabBar);

        // Measure tab bar height for content padding (sheet extends behind tab bar)
        requestAnimationFrame(() => _measureTabBar());

        _setupGestureListeners();
    }

    /**
     * Measures the tab bar and sets a CSS custom property so content
     * can pad itself above the tab bar's transparent overlay area.
     */
    function _measureTabBar() {
        if (!state.tabBar) return;
        const h = state.tabBar.offsetHeight;
        state.sheetElement.style.setProperty('--tab-bar-height', `${h}px`);
    }

    // ========================================
    // TAB MANAGEMENT
    // ========================================

    /**
     * Tab click handler — toggle/switch behavior
     * If in detail mode, return to browse and show the clicked tab.
     */
    function _onTabClick(index) {
        // Tapping active tab when sheet is open (and not in detail) → close
        if (!state.activeLocationKey && index === state.activeTab && state.currentSnap > 0) {
            _closeSheet();
            HistoryManager.push();
            return;
        }

        // Clear detail if active, then switch to the clicked tab.
        // batch() suppresses the intermediate push from popupclose so
        // only the final push (below) captures the end state.
        if (state.activeLocationKey) {
            HistoryManager.batch(() => _clearDetail());
        }
        _switchTab(index);
        if (state.currentSnap < SNAP_PEEK) {
            _snapTo(SNAP_PEEK);
        }
        HistoryManager.push();
    }

    function _showBrowse() {
        state.browseContentContainer.style.display = '';
        state.detailContentContainer.style.display = 'none';
    }

    function _showDetail() {
        state.browseContentContainer.style.display = 'none';
        state.detailContentContainer.style.display = 'block';
    }

    /**
     * Sets tab state and button highlights without moving the track.
     * Used when track positioning is handled separately (e.g., wrap animation).
     */
    function _activateTab(index) {
        index = Math.max(0, Math.min(TAB_KEYS.length - 1, index));
        state.activeTab = index;
        state.tabButtons.forEach((btn, i) => btn.classList.toggle('active', i === index));
        _showBrowse();
    }

    /**
     * Switches to the given browse tab index (0-2).
     * @param {number} index - Tab index
     * @param {boolean} animate - Use CSS transition (true for swipe completion)
     */
    function _switchTab(index, animate = false) {
        _activateTab(index);
        index = state.activeTab; // use clamped value

        // Position the browse track (real tab 0 is at track position 1 due to leading clone)
        const offset = -(index + 1) * state.tabViewport.offsetWidth;
        state.tabTrack.classList.toggle('no-transition', !animate);
        state.tabTrack.style.transform = `translateX(${offset}px)`;
        if (!animate) {
            state.tabTrack.offsetHeight; // force reflow
            state.tabTrack.classList.remove('no-transition');
        }
    }

    function _deactivateAllTabs() {
        state.activeTab = -1;
        state.tabButtons.forEach(btn => btn.classList.remove('active'));
    }

    function _closeSheet() {
        _snapTo(0);
        _deactivateAllTabs();
    }

    function _getTabTrackOffset() {
        const match = state.tabTrack.style.transform.match(/translateX\(([^)]+)px\)/);
        return match ? parseFloat(match[1]) : 0;
    }

    // ========================================
    // DETAIL MODE
    // ========================================

    /**
     * Clears detail state: clears marker, fires popupclose, returns to browse layout
     */
    function _clearDetail() {
        const closedKey = state.activeLocationKey;
        const closedLngLat = state.activeLngLat;

        state.activeLocationKey = null;
        state.activeLngLat = null;

        state.detailContentContainer.innerHTML = '';
        _showBrowse();

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

    // ========================================
    // GESTURE HANDLING
    // ========================================

    function _setupGestureListeners() {
        // Handle area — draggable + tappable
        state.handleArea.addEventListener('touchstart', _onDragStart, { passive: true });
        state.handleArea.addEventListener('click', _onHandleTap);

        // Tab viewport — horizontal swipe for tab switching (browse tabs)
        state.tabViewport.addEventListener('touchstart', _onTabSwipeStart, { passive: true });
        state.tabViewport.addEventListener('touchmove', _onTabSwipeMove, { passive: false });
        state.tabViewport.addEventListener('touchend', _onTabSwipeEnd, { passive: true });
        state.tabViewport.addEventListener('touchcancel', _onTabSwipeEnd, { passive: true });

        // Detail content — horizontal swipe to dismiss
        state.detailContentContainer.addEventListener('touchstart', _onDetailSwipeStart, { passive: true });
        state.detailContentContainer.addEventListener('touchend', _onDetailSwipeEnd, { passive: true });

        // Move / end on sheet (captures handle drags)
        state.sheetElement.addEventListener('touchmove', _onDragMove, { passive: false });
        state.sheetElement.addEventListener('touchend', _onDragEnd, { passive: true });
        state.sheetElement.addEventListener('touchcancel', _onDragEnd, { passive: true });

        // Resize — clean up at breakpoint
        window.addEventListener('resize', _onResize);
    }

    // --- Vertical sheet drag (handle only) ---

    function _onDragStart(e) {
        const touch = e.touches[0];
        state.isDragging = true;
        state.dragStartY = touch.clientY;
        state.dragStartHeight = _getCurrentHeight();
        state.velocitySamples = [{ time: Date.now(), y: touch.clientY }];
        state.sheetElement.classList.add('no-transition');
    }

    function _onDragMove(e) {
        if (!state.isDragging) return;

        const touch = e.touches[0];
        const deltaY = touch.clientY - state.dragStartY;

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
        state.sheetElement.style.height = `${newHeight}px`;

        // Record velocity sample
        state.velocitySamples.push({ time: Date.now(), y: touch.clientY });
        if (state.velocitySamples.length > MAX_VELOCITY_SAMPLES) {
            state.velocitySamples.shift();
        }
    }

    function _onDragEnd() {
        if (!state.isDragging) return;
        _cancelDrag();

        const velocity = _calculateVelocity(); // positive = downward
        const currentHeight = _getCurrentHeight();
        const viewportHeight = window.innerHeight;
        const currentRatio = currentHeight / viewportHeight;

        // Fast upward swipe → full
        if (velocity < -VELOCITY_THRESHOLD) {
            _snapTo(SNAP_FULL);
            return;
        }

        // Fast downward swipe → close
        if (velocity > DISMISS_VELOCITY) {
            _clearAndClose(true);
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

    // --- Horizontal tab swipe (browse tabs, wraps circularly) ---

    function _onTabSwipeStart(e) {
        if (state.activeTab < 0) return;
        const touch = e.touches[0];
        state.tabSwipeStartX = touch.clientX;
        state.tabTrackStartOffset = _getTabTrackOffset();
        state.isTabSwiping = false;
    }

    function _onTabSwipeMove(e) {
        if (state.activeTab < 0) return;
        const touch = e.touches[0];
        const dx = touch.clientX - state.tabSwipeStartX;

        if (!state.isTabSwiping) {
            if (Math.abs(dx) < TAB_SWIPE_THRESHOLD) return;
            state.isTabSwiping = true;
            state.tabTrack.classList.add('no-transition');
        }

        e.preventDefault();

        const viewportWidth = state.tabViewport.offsetWidth;
        let offset = state.tabTrackStartOffset + dx;

        // 5-panel track: [clone_last | real0 | real1 | real2 | clone_first]
        // Rubber-band only past the clone edges
        const minOffset = -4 * viewportWidth;
        if (offset > 0) {
            offset *= 0.3;
        } else if (offset < minOffset) {
            offset = minOffset + (offset - minOffset) * 0.3;
        }

        state.tabTrack.style.transform = `translateX(${offset}px)`;
    }

    function _onTabSwipeEnd(e) {
        if (!state.isTabSwiping) return;
        state.isTabSwiping = false;

        const viewportWidth = state.tabViewport.offsetWidth;
        if (viewportWidth === 0) {
            state.tabTrack.classList.remove('no-transition');
            return;
        }

        const endX = e.changedTouches?.[0]?.clientX;
        if (endX === undefined) {
            _switchTab(state.activeTab);
            return;
        }

        // Determine target track position (0-4: clone_last, real0, real1, real2, clone_first)
        const rawDx = endX - state.tabSwipeStartX;
        const currentTrackPos = state.activeTab + 1; // 1, 2, or 3
        let targetTrackPos = currentTrackPos;

        // Commit to next/prev tab at 25% of viewport width
        if (rawDx < -viewportWidth * SWIPE_COMMIT_FRACTION) {
            targetTrackPos = currentTrackPos + 1; // swipe left → next
        } else if (rawDx > viewportWidth * SWIPE_COMMIT_FRACTION) {
            targetTrackPos = currentTrackPos - 1; // swipe right → prev
        }
        targetTrackPos = Math.max(0, Math.min(4, targetTrackPos));

        const isWrapping = targetTrackPos === 0 || targetTrackPos === 4;
        const targetOffset = -targetTrackPos * viewportWidth;

        // Determine real tab index from track position
        const realTabIndex = targetTrackPos === 0 ? TAB_KEYS.length - 1
            : targetTrackPos === 4 ? 0
            : targetTrackPos - 1;

        if (!isWrapping) {
            _switchTab(realTabIndex, true);
        } else {
            // Update tab state immediately, animate to clone, then jump to real position
            _activateTab(realTabIndex);
            state.tabTrack.classList.remove('no-transition');
            state.tabTrack.style.transform = `translateX(${targetOffset}px)`;
            const onEnd = () => {
                state.tabTrack.removeEventListener('transitionend', onEnd);
                _switchTab(realTabIndex); // instant jump to real panel position
            };
            state.tabTrack.addEventListener('transitionend', onEnd);
        }
        HistoryManager.push();
    }

    // --- Detail horizontal swipe (dismiss + return to previous tab) ---

    function _onDetailSwipeStart(e) {
        if (!state.activeLocationKey) return;
        const touch = e.touches[0];
        state.detailSwipeStartX = touch.clientX;
        state.detailSwipeStartY = touch.clientY;
    }

    function _onDetailSwipeEnd(e) {
        if (!state.activeLocationKey) return;
        const touch = e.changedTouches?.[0];
        if (!touch) return;

        const dx = Math.abs(touch.clientX - state.detailSwipeStartX);
        const dy = Math.abs(touch.clientY - state.detailSwipeStartY);

        // Must be primarily horizontal and past threshold
        if (dx >= DETAIL_SWIPE_THRESHOLD && dx > dy * 1.5) {
            _clearDetail();
            if (state.preDetailTab >= 0) {
                // Was browsing a tab → restore it
                _switchTab(state.preDetailTab);
            } else {
                // Opened via marker (no prior tab) → close sheet
                _closeSheet();
            }
            HistoryManager.push();
        }
    }

    // --- Handle tap ---

    function _onHandleTap() {
        if (state.currentSnap >= SNAP_FULL) {
            _snapTo(SNAP_PEEK);
        } else if (state.currentSnap >= SNAP_PEEK) {
            _clearAndClose(true);
        }
        HistoryManager.push();
    }

    // --- Shared helpers ---

    function _cancelDrag() {
        state.isDragging = false;
        state.sheetElement.classList.remove('no-transition');
    }

    function _calculateVelocity() {
        const s = state.velocitySamples;
        if (s.length < 2) return 0;
        const dt = s[s.length - 1].time - s[0].time;
        if (dt === 0) return 0;
        return (s[s.length - 1].y - s[0].y) / dt; // px/ms, positive = down
    }

    function _getCurrentHeight() {
        const h = parseFloat(state.sheetElement.style.height);
        if (!isNaN(h)) return h;
        return window.innerHeight * state.currentSnap;
    }

    function _snapTo(snapRatio) {
        state.currentSnap = snapRatio;
        const h = window.innerHeight * snapRatio;
        state.sheetElement.style.height = `${h}px`;
        state.sheetElement.classList.toggle('open', snapRatio > 0);
    }

    function _onResize() {
        if (window.innerWidth > Constants.UI.MOBILE_BREAKPOINT) {
            _clearAndClose(false);
        } else {
            // On mobile → re-measure tab bar for padding
            _measureTabBar();
            if (state.currentSnap > 0) {
                _snapTo(state.currentSnap);
            }
        }
    }

    // ========================================
    // OPEN / CLOSE
    // ========================================

    function open(locationKey, lngLat, contentElement) {
        // Already showing this location
        if (state.activeLocationKey === locationKey && state.currentSnap > 0) return;

        // Save current browse tab (-1 if sheet was closed / opened via marker)
        state.preDetailTab = state.activeTab;

        state.activeLocationKey = locationKey;
        state.activeLngLat = lngLat;

        // Set detail content
        state.detailContentContainer.innerHTML = '';
        state.detailContentContainer.appendChild(contentElement);
        state.detailContentContainer.scrollTop = 0;
        _showDetail();

        // Deactivate all tabs (detail mode has no active tab)
        _deactivateAllTabs();

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

    /**
     * Clears detail if active, then closes the sheet.
     * Used by both close() (instant, desktop resize) and dismissToMini() (animated, map tap).
     */
    function _clearAndClose(animate) {
        if (state.activeLocationKey) _clearDetail();
        if (animate) {
            _closeSheet();
        } else {
            state.sheetElement.style.height = '0';
            state.currentSnap = 0;
            _deactivateAllTabs();
        }
    }

    function close() {
        _clearAndClose(false);
    }

    function dismissToMini() {
        _clearAndClose(true);
    }

    function updateContent(contentElement) {
        if (!state.activeLocationKey) return;
        state.detailContentContainer.innerHTML = '';
        state.detailContentContainer.appendChild(contentElement);
        state.detailContentContainer.scrollTop = 0;
    }

    function updateBrowseTabs(sections) {
        const mapping = { locations: 0, events: 1, tags: 2 };
        Object.entries(sections).forEach(([key, element]) => {
            const idx = mapping[key];
            if (idx !== undefined && state.tabPanels[idx]) {
                state.tabPanels[idx].innerHTML = '';
                if (element) state.tabPanels[idx].appendChild(element);
            }
        });
        _updateClones();
    }

    /**
     * Copies visual content from edge panels into their clones.
     * Clones are non-interactive — only visible during wrap transitions.
     */
    function _updateClones() {
        const last = state.tabPanels[TAB_KEYS.length - 1];
        const first = state.tabPanels[0];
        if (state.cloneStart && last) state.cloneStart.innerHTML = last.innerHTML;
        if (state.cloneEnd && first) state.cloneEnd.innerHTML = first.innerHTML;
    }

    // ========================================
    // PUBLIC API
    // ========================================

    function init(mapInstance) {
        state.mapInstance = mapInstance;
        _createDOM();

        // On mobile, prepare browse content (sheet starts closed, tab bar visible)
        if (window.innerWidth <= Constants.UI.MOBILE_BREAKPOINT) {
            _switchTab(0);
            _deactivateAllTabs();
        }
    }

    return {
        init,
        open,
        close,
        dismissToMini,
        updateContent,
        updateBrowseTabs,
        isOpen: () => state.currentSnap > 0,
        isDetailMode: () => state.activeLocationKey !== null,
        getCurrentLocationKey: () => state.activeLocationKey,
        getCurrentSnap: () => state.currentSnap,
        getActiveTab: () => state.activeTab,
        switchTab: (index) => _switchTab(index),
        snapTo: (snap) => {
            // Auto-activate first browse tab when opening from closed
            if (snap > 0 && state.activeTab < 0 && !state.activeLocationKey) {
                _switchTab(0);
            }
            _snapTo(snap);
        }
    };
})();
