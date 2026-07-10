/**
 * FilterPanelUI Module
 *
 * Orchestrates the filter panel UI by coordinating between specialized modules:
 * - TagStateManager: Manages tag states and button creation
 * - SectionRenderer: Renders collapsible search result sections
 * - GestureHandler: Handles swipe gestures for section reordering
 * - SearchController: Handles search input and special terms
 *
 * This module acts as the main coordinator for the filter panel which displays
 * search results across locations, events, and tags.
 *
 * @module FilterPanelUI
 */
const FilterPanelUI = (() => {
    // Static enum object; TagStateManager loads earlier in script-tag order, so eager capture is safe.
    const TAG_STATE = TagStateManager.getTagStateConstants();

    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // Configuration
        allAvailableTags: [],
        resultsContainerDOM: null,
        onFilterChangeCallback: null,
        debugMode: false,

        // Frequencies (tag usage counts)
        initialGlobalFrequencies: {},
        currentDynamicFrequencies: {},

        // Tag states (managed by TagStateManager)
        tagStates: {},

        // Search state (SearchController handles input events)
        searchTerm: '',
        lastSearchResults: [],
        onSearchResultClick: null,
        getSearchTerm: null,

        // Provider objects
        colorProvider: null,  // { getTagColor, assignColorToTag, unassignColorFromTag }

        // Section management - determined at init time based on device type
        sectionOrder: null,

        // Hierarchy data
        tagDescendantsOf: {},
        tagParentsOf: {},
        tagChildrenOf: {},
        structuralFormatTags: new Set(),
        tagEmojiMap: {},

        // Chip bar
        getSelectedTagsWithColors: null
    };

    // Derived caches over state.allAvailableTags, rebuilt at its only two
    // assignment sites (init, refreshAvailableTags). Tag names are immutable,
    // so re-normalizing / re-building the Set on every render is pure waste.
    let _normalizedTagCache = new Map();   // tag -> Utils.normalizeForSearch(tag)
    let _availableTagsSet = new Set();

    function _rebuildTagCaches() {
        _availableTagsSet = new Set(state.allAvailableTags);
        _normalizedTagCache = new Map();
        for (const tag of state.allAvailableTags) {
            _normalizedTagCache.set(tag, Utils.normalizeForSearch(tag));
        }
    }

    /**
     * Determines if the current window is mobile-sized
     * @returns {boolean} True if window width is at or below mobile breakpoint
     */
    function isMobileLayout() {
        return Utils.isMobileLayout();
    }

    /**
     * Gets the default section order based on device type
     * Desktop: locations, events, tags
     * Mobile: tags, events, locations
     * @returns {Array<string>} Section order array
     */
    function getDefaultSectionOrder() {
        return isMobileLayout()
            ? ['tags', 'events', 'locations', 'organizers']
            : ['locations', 'events', 'tags', 'organizers'];
    }

    /**
     * Provider functions from parent application
     */
    const providers = {
        getSelectedLocationKey: () => null,
    };

    /**
     * Callback to perform search operations
     */
    let performSearchCallback = () => {};

    // ========================================
    // CHIP BAR
    // ========================================

    const CHIP_BAR_RENDER_LIMIT = 100; // max chips rendered; overflow is reachable by scrolling
    const CHIP_BAR_MINIMAL_LIMIT = 12; // proto chips=minimal: calm top-N + a "More" affordance
    const DESCENDANT_DROPDOWN_LIMIT = 12;
    const DESCENDANT_HOVER_OPEN_DELAY = 250;   // ms before hover opens dropdown
    const DESCENDANT_HOVER_CLOSE_DELAY = 180;  // grace period when leaving chip → dropdown
    const DESCENDANT_LONG_PRESS_MS = 450;
    let _chipBarAnimateNext = false; // set true before user-initiated chip changes
    let _activeDropdown = null;      // { tagName, container, anchorChip }
    let _dropdownOpenTimer = null;
    let _dropdownCloseTimer = null;
    let _longPressTimer = null;

    // ----- Performance profiler (off by default; enable via window.FilterProfiler.enabled = true) -----
    // Used by the /profile-frontend skill to time interactions like chip clicks,
    // date changes, search, and pan. mark/measure are no-ops when no session
    // is active, so leaving the FP.mark calls in place has effectively zero cost.
    // For load-time profiling (Phase 2, etc.), set localStorage.fp_enabled='1' before reload.
    let _profilerEnabledFromStorage = false;
    try { _profilerEnabledFromStorage = localStorage.getItem('fp_enabled') === '1'; } catch (_) {}
    const FilterProfiler = {
        enabled: _profilerEnabledFromStorage,
        _active: false,
        _label: '',
        start(label) {
            if (!this.enabled) return;
            try { performance.clearMarks(); performance.clearMeasures(); } catch (_) {}
            this._active = true;
            this._label = label;
            performance.mark('fp:total:start');
        },
        mark(name) {
            if (!this._active) return;
            performance.mark(name);
        },
        measure(name, startMark, endMark) {
            if (!this._active) return;
            try { performance.measure(name, startMark, endMark); } catch (_) {}
        },
        flush() {
            if (!this._active) return;
            performance.mark('fp:total:end');
            try { performance.measure('fp:total', 'fp:total:start', 'fp:total:end'); } catch (_) {}
            const measures = performance.getEntriesByType('measure').filter(m => m.name.startsWith('fp:'));
            const total = measures.find(m => m.name === 'fp:total');
            const totalDur = total ? total.duration : 0;
            console.groupCollapsed(`%c[profile] ${this._label} — total ${totalDur.toFixed(1)}ms`,
                'color:#888;font-weight:normal');
            const others = measures.filter(m => m.name !== 'fp:total')
                .sort((a, b) => a.startTime - b.startTime);
            for (const m of others) {
                console.log(`  ${m.name.padEnd(28)} ${m.duration.toFixed(1).padStart(7)}ms`);
            }
            console.groupEnd();
            performance.clearMarks();
            performance.clearMeasures();
            this._active = false;
        },
        // Re-entrant wrapper. If a profiling session is already active (e.g.,
        // a chip click flow that calls performSearch internally), wrap() is a
        // no-op around fn so inner calls don't clobber the outer session.
        wrap(label, fn) {
            if (!this.enabled || this._active) return fn();
            this.start(label);
            try { return fn(); } finally { this.flush(); }
        }
    };
    if (typeof window !== 'undefined') window.FilterProfiler = FilterProfiler;

    /**
     * Toggles a chip bar tag on/off.
     */
    function _handleChipClick(tagName) {
        const currentState = TagStateManager.getTagState(tagName);
        const willSelect = currentState === TAG_STATE.UNSELECTED;
        FilterProfiler.start(`chip ${willSelect ? 'select' : 'deselect'} → ${tagName}`);

        _chipBarAnimateNext = true;

        if (!willSelect) {
            state.tagStates[tagName] = TAG_STATE.UNSELECTED;
            if (state.colorProvider) {
                state.colorProvider.unassignColorFromTag(tagName);
            }
        } else {
            state.tagStates[tagName] = TAG_STATE.SELECTED;
            if (state.colorProvider) {
                state.colorProvider.assignColorToTag(tagName);
            }
        }

        if (state.onFilterChangeCallback) {
            state.onFilterChangeCallback();
        }

        FilterProfiler.flush();
    }

    /**
     * Wires up wheel-to-horizontal-scroll on the chip bar.
     * Vertical wheel input is redirected to horizontal scroll so trackpad/mouse
     * users can navigate the chip overflow without a horizontal gesture.
     */
    function _initChipBarWheelScroll() {
        const container = document.getElementById('chip-bar');
        if (!container || container.dataset.wheelBound) return;
        container.dataset.wheelBound = '1';

        container.addEventListener('wheel', (e) => {
            if (e.ctrlKey || e.metaKey) return; // preserve pinch-zoom gestures

            const max = container.scrollWidth - container.clientWidth;
            if (max <= 0) return;

            // Use whichever axis dominates; vertical input maps to horizontal scroll.
            const delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
            if (delta === 0) return;

            const atStart = container.scrollLeft <= 0 && delta < 0;
            const atEnd = container.scrollLeft >= max && delta > 0;
            if (atStart || atEnd) return; // let the page handle overscroll

            e.preventDefault();
            container.scrollLeft = Math.max(0, Math.min(max, container.scrollLeft + delta));
        }, { passive: false });
    }

    /**
     * Renders the unified chip bar showing selected tags + top unselected curated tags.
     * Called after every filter/search change via onAfterRender.
     */
    function _renderChipBar(animate = true) {
        const container = document.getElementById('chip-bar');
        if (!container) return;

        _initChipBarChipEvents(container);

        FilterProfiler.mark('fp:chipbar:start');

        // Anchored chip elements are about to be discarded; close any open
        // dropdown and cancel any pending long-press anchored to them.
        _hideDescendantDropdown(true);
        if (_longPressTimer) {
            clearTimeout(_longPressTimer);
            _longPressTimer = null;
        }

        // 1. Collect selected tags (always shown first)
        const selectedTagsWithColors = state.getSelectedTagsWithColors
            ? state.getSelectedTagsWithColors()
            : [];
        const selectedTagNames = new Set(selectedTagsWithColors.map(([tag]) => tag));

        // 2. Score unselected curated tags using the same formula as SearchManager,
        //    plus descendant aggregation for parent categories.
        const hasSearch = state.searchTerm && state.searchTerm.trim().length > 0;
        const normalizedSearchTerm = hasSearch ? Utils.normalizeForSearch(state.searchTerm) : '';
        const visibleFreqs = state.getVisibleTagFrequencies ? state.getVisibleTagFrequencies() : {};

        const unselectedTags = [];
        for (const tag of state.allAvailableTags) {
            if (selectedTagNames.has(tag)) continue;
            const tagState = TagStateManager.getTagState(tag);
            if (tagState !== TAG_STATE.UNSELECTED) continue;

            // When searching, only include tags whose name matches the term
            let exactMatch = false;
            if (hasSearch) {
                const normalizedTag = _normalizedTagCache.get(tag) ?? Utils.normalizeForSearch(tag);
                if (!normalizedTag.includes(normalizedSearchTerm)) continue;
                exactMatch = normalizedTag === normalizedSearchTerm;
            }

            const freq = state.currentDynamicFrequencies[tag] || 0;
            if (!hasSearch && freq <= 0) continue;

            // Same scoring formula as SearchManager.searchTags
            let score = SearchManager.scoreTagSignal({
                dynamicFreq: freq,
                visibleFreq: visibleFreqs[tag] || 0,
                globalFreq: state.initialGlobalFrequencies[tag] || 0,
                isExactMatch: exactMatch
            });

            // Descendant aggregation: parent tags get credit for children's scores
            const descendants = state.tagDescendantsOf[tag];
            if (descendants) {
                descendants.forEach(d => {
                    score += SearchManager.scoreTagSignal({
                        dynamicFreq: state.currentDynamicFrequencies[d] || 0,
                        visibleFreq: visibleFreqs[d] || 0,
                        globalFreq: state.initialGlobalFrequencies[d] || 0,
                        isExactMatch: false
                    });
                });
            }

            if (score <= 0) continue;

            unselectedTags.push({ tag, score });
        }

        // Sort unselected by descending score; on ties prefer parent tags
        // (with descendants) so category chips surface in the minimal bar.
        const hasDesc = (tag) => (state.tagDescendantsOf[tag] && state.tagDescendantsOf[tag].size > 0) ? 1 : 0;
        unselectedTags.sort((a, b) => b.score - a.score || hasDesc(b.tag) - hasDesc(a.tag));

        FilterProfiler.mark('fp:chipbar:scored');
        FilterProfiler.measure('fp:chipbar:score', 'fp:chipbar:start', 'fp:chipbar:scored');

        // 4. Build DOM up to the render limit; overflow scrolls horizontally.
        // The minimal prototype caps hard at a calm top-N — but never while a
        // search term is active (hiding name-matches mid-search reads broken).
        const chipsMinimal = !hasSearch && ProtoFlags.isOn('chips', 'minimal');
        const renderLimit = chipsMinimal ? CHIP_BAR_MINIMAL_LIMIT : CHIP_BAR_RENDER_LIMIT;
        const unselectedToRender = unselectedTags.slice(0, renderLimit);

        // FLIP: capture old chip positions before rebuilding. Only consumed by
        // the animate path below — skip the forced-layout rect reads otherwise.
        const oldPositions = new Map();
        if (animate) {
            for (const chip of container.children) {
                const tag = chip.dataset.primaryTag;
                if (tag) {
                    const rect = chip.getBoundingClientRect();
                    oldPositions.set(tag, { left: rect.left, top: rect.top });
                }
            }
        }

        FilterProfiler.mark('fp:chipbar:flip-capture');
        FilterProfiler.measure('fp:chipbar:flip-capture', 'fp:chipbar:scored', 'fp:chipbar:flip-capture');

        container.innerHTML = '';
        container.scrollLeft = 0;

        // Selected chips first
        for (const [tagName] of selectedTagsWithColors) {
            const btn = _createChipButton(tagName, true);
            container.appendChild(btn);
        }

        // Unselected chips
        for (const { tag } of unselectedToRender) {
            const btn = _createChipButton(tag, false);
            container.appendChild(btn);
        }

        // Minimal mode: trailing "＋ More" pseudo-chip routes into search
        // (which surfaces the full tag catalog). No data-primary-tag, so the
        // delegated chip/dropdown handlers ignore it.
        if (chipsMinimal && unselectedTags.length > unselectedToRender.length) {
            const more = document.createElement('button');
            more.type = 'button';
            more.className = 'tag-button state-unselected chip-more';
            more.textContent = '＋ More';
            more.addEventListener('click', () => {
                const input = document.getElementById('omni-search-input');
                if (input) input.focus();
            });
            container.appendChild(more);
        }

        const hasChips = selectedTagNames.size > 0 || unselectedToRender.length > 0;
        container.style.display = hasChips ? 'flex' : 'none';

        FilterProfiler.mark('fp:chipbar:dom-built');
        FilterProfiler.measure('fp:chipbar:dom-build', 'fp:chipbar:flip-capture', 'fp:chipbar:dom-built');

        // Toggling the chip bar's visibility can change the top bar's height —
        // keep the sheet's content offset below it in sync (desktop only).
        if (!isMobileLayout() && typeof Sheet !== 'undefined') {
            Sheet.measureTopOffset();
        }

        FilterProfiler.mark('fp:chipbar:layout');
        FilterProfiler.measure('fp:chipbar:layout', 'fp:chipbar:dom-built', 'fp:chipbar:layout');

        // FLIP: animate chips from old positions to new positions
        if (animate && oldPositions.size > 0) {
            const chipsToSlide = [];
            for (const chip of container.children) {
                if (chip.classList.contains('chip-more')) continue; // stable, never animated
                const tag = chip.dataset.primaryTag;
                const oldPos = oldPositions.get(tag);
                const newRect = chip.getBoundingClientRect();
                if (oldPos) {
                    const dx = oldPos.left - newRect.left;
                    const dy = oldPos.top - newRect.top;
                    if (Math.abs(dy) > 5) {
                        // Changed rows — fade in instead of sliding diagonally
                        chip.style.animation = 'chip-fade-in 0.25s ease-out';
                    } else if (Math.abs(dx) > 1) {
                        // Invert: place chip at old position with no transition
                        chip.style.transition = 'none';
                        chip.style.transform = `translateX(${dx}px)`;
                        chipsToSlide.push(chip);
                    }
                } else {
                    // New chip — fade in
                    chip.style.animation = 'chip-fade-in 0.25s ease-out';
                }
            }
            // Play: after browser paints the inverted state, animate to final position
            if (chipsToSlide.length > 0) {
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => {
                        for (const chip of chipsToSlide) {
                            chip.style.transition = 'transform 0.25s ease-out';
                            chip.style.transform = '';
                        }
                    });
                });
            }
        }

        FilterProfiler.mark('fp:chipbar:end');
        FilterProfiler.measure('fp:chipbar:flip-apply', 'fp:chipbar:layout', 'fp:chipbar:end');
        FilterProfiler.measure('fp:chipbar:total', 'fp:chipbar:start', 'fp:chipbar:end');
    }

    /**
     * Builds a chip button shared by the chip bar and the descendant dropdown.
     * Chip-bar chips rely on the container's delegated handlers (see
     * _initChipBarChipEvents); dropdown chips attach their own click handler
     * in _createDropdownChip, stopping propagation so the document-level
     * outside-click handler doesn't close the dropdown.
     */
    function _buildChip(tagName, isActive) {
        const btn = document.createElement('button');
        btn.className = isActive ? 'tag-button state-selected' : 'tag-button state-unselected';
        btn.dataset.primaryTag = tagName;
        btn.setAttribute('aria-label', `Filter by ${tagName}`);

        if (isActive && state.colorProvider) {
            const color = state.colorProvider.getTagColor(tagName);
            if (color) {
                btn.style.setProperty('--chip-color', color);
            }
        }

        Utils.appendChipContent(btn, state.tagEmojiMap[tagName], tagName);
        return btn;
    }

    /**
     * Creates a chip bar button element
     */
    function _createChipButton(tagName, isActive) {
        return _buildChip(tagName, isActive);
    }

    /**
     * Binds the chip bar's click, hover, long-press, and right-click handlers
     * once, via delegation on the container — chips are rebuilt on every
     * render, so per-chip listeners would be re-attached constantly.
     * mouseover/mouseout + relatedTarget checks emulate the per-chip
     * mouseenter/mouseleave semantics.
     */
    function _initChipBarChipEvents(container) {
        if (container.dataset.chipEventsBound) return;
        container.dataset.chipEventsBound = '1';

        // Resolves an event to its chip button, or null (gap/padding hits).
        const chipFromEvent = (e) => {
            const target = e.target instanceof Element ? e.target : null;
            const btn = target && target.closest('button[data-primary-tag]');
            return btn && container.contains(btn) ? btn : null;
        };

        container.addEventListener('click', (e) => {
            const btn = chipFromEvent(e);
            if (btn) _handleChipClick(btn.dataset.primaryTag);
        });

        // mouseenter equivalent: skip moves between a chip's own children.
        container.addEventListener('mouseover', (e) => {
            const btn = chipFromEvent(e);
            if (!btn || (e.relatedTarget && btn.contains(e.relatedTarget))) return;
            const tagName = btn.dataset.primaryTag;
            if (!_hasDropdownContent(tagName)) return;
            clearTimeout(_dropdownCloseTimer);
            if (_activeDropdown && _activeDropdown.tagName === tagName) return;
            clearTimeout(_dropdownOpenTimer);
            _dropdownOpenTimer = setTimeout(() => {
                _showDescendantDropdown(btn, tagName);
            }, DESCENDANT_HOVER_OPEN_DELAY);
        });

        // mouseleave equivalent
        container.addEventListener('mouseout', (e) => {
            const btn = chipFromEvent(e);
            if (!btn || (e.relatedTarget && btn.contains(e.relatedTarget))) return;
            if (!_hasDropdownContent(btn.dataset.primaryTag)) return;
            clearTimeout(_dropdownOpenTimer);
            _scheduleDropdownClose();
        });

        container.addEventListener('contextmenu', (e) => {
            const btn = chipFromEvent(e);
            // Chips with no dropdown keep the native context menu.
            if (!btn || !_hasDropdownContent(btn.dataset.primaryTag)) return;
            e.preventDefault();
            clearTimeout(_dropdownOpenTimer);
            _showDescendantDropdown(btn, btn.dataset.primaryTag);
        });

        container.addEventListener('touchstart', (e) => {
            const btn = chipFromEvent(e);
            if (!btn || !_hasDropdownContent(btn.dataset.primaryTag)) return;
            clearTimeout(_longPressTimer);
            _longPressTimer = setTimeout(() => {
                _showDescendantDropdown(btn, btn.dataset.primaryTag);
                _longPressTimer = null;
            }, DESCENDANT_LONG_PRESS_MS);
        }, { passive: true });

        const cancelLongPress = (e) => {
            const btn = chipFromEvent(e);
            if (!btn || !_hasDropdownContent(btn.dataset.primaryTag)) return;
            if (_longPressTimer) {
                clearTimeout(_longPressTimer);
                _longPressTimer = null;
            }
        };
        container.addEventListener('touchend', cancelLongPress);
        container.addEventListener('touchcancel', cancelLongPress);
        container.addEventListener('touchmove', cancelLongPress, { passive: true });
    }

    // ========================================
    // DESCENDANT DROPDOWN
    // ========================================

    /**
     * Scores a tag using the same shape as the chip bar.
     * Returns null if the tag should be dropped (no signal for it).
     */
    function _scoreRelatedTag(tag, visibleFreqs) {
        const score = SearchManager.scoreTagSignal({
            dynamicFreq: state.currentDynamicFrequencies[tag] || 0,
            visibleFreq: visibleFreqs[tag] || 0,
            globalFreq: state.initialGlobalFrequencies[tag] || 0,
            isExactMatch: false
        });
        return score > 0 ? score : null;
    }

    /**
     * Returns related tags for `tagName`, sorted by descending frequency.
     * Layered fallback: descendants first, then siblings (other children of any
     * shared parent), then parents — until the dropdown has enough entries or
     * we run out of related tags. Each tag appears at most once.
     */
    function _getSortedDescendants(tagName) {
        const visibleFreqs = state.getVisibleTagFrequencies ? state.getVisibleTagFrequencies() : {};
        const seen = new Set([tagName]);

        const structural = state.structuralFormatTags;
        const collect = (candidates) => {
            const layer = [];
            candidates.forEach(tag => {
                if (seen.has(tag)) return;
                seen.add(tag);
                // Structural Format nodes (Format root + category tags) are never
                // shown as chips — only their leaf event-type tags are.
                if (structural && structural.has(tag)) return;
                const score = _scoreRelatedTag(tag, visibleFreqs);
                if (score === null) return;
                layer.push({ tag, score });
            });
            layer.sort((a, b) => b.score - a.score);
            return layer;
        };

        const items = [];
        const descendants = state.tagDescendantsOf[tagName];
        if (descendants && descendants.size > 0) {
            items.push(...collect(descendants));
        }

        // If descendants alone don't fill the dropdown, pad with siblings, then parents.
        if (items.length < DESCENDANT_DROPDOWN_LIMIT) {
            const parents = state.tagParentsOf[tagName] || [];
            const siblingSet = new Set();
            parents.forEach(parent => {
                (state.tagChildrenOf[parent] || []).forEach(sib => siblingSet.add(sib));
            });
            items.push(...collect(siblingSet));
        }

        if (items.length < DESCENDANT_DROPDOWN_LIMIT) {
            items.push(...collect(state.tagParentsOf[tagName] || []));
        }

        return items;
    }

    /**
     * True if `tagName` has anything we'd show in a dropdown — descendants,
     * siblings, or parents. Used to gate trigger attachment on chip creation.
     */
    function _hasDropdownContent(tagName) {
        const d = state.tagDescendantsOf[tagName];
        if (d && d.size > 0) return true;
        const parents = state.tagParentsOf[tagName] || [];
        if (parents.length > 0) return true; // parents themselves count, and imply potential siblings
        return false;
    }

    function _scheduleDropdownClose() {
        clearTimeout(_dropdownCloseTimer);
        _dropdownCloseTimer = setTimeout(() => _hideDescendantDropdown(false), DESCENDANT_HOVER_CLOSE_DELAY);
    }

    function _showDescendantDropdown(anchorChip, tagName) {
        if (_activeDropdown && _activeDropdown.tagName === tagName) {
            clearTimeout(_dropdownCloseTimer);
            return;
        }
        _hideDescendantDropdown(true);

        const items = _getSortedDescendants(tagName);
        if (items.length === 0) return;

        const container = document.createElement('div');
        container.className = 'chip-descendant-dropdown';
        container.dataset.parentTag = tagName;

        items.slice(0, DESCENDANT_DROPDOWN_LIMIT).forEach((item, i) => {
            const isActive = TagStateManager.getTagState(item.tag) !== TAG_STATE.UNSELECTED;
            const chipBtn = _createDropdownChip(item.tag, isActive);
            chipBtn.style.animationDelay = `${i * 25}ms`;
            container.appendChild(chipBtn);
        });

        document.body.appendChild(container);
        _positionDropdown(container, anchorChip);

        container.addEventListener('mouseenter', () => clearTimeout(_dropdownCloseTimer));
        container.addEventListener('mouseleave', _scheduleDropdownClose);

        _activeDropdown = { tagName, container, anchorChip };
    }

    function _positionDropdown(container, anchorChip) {
        const cw = container.offsetWidth;
        const chipBar = anchorChip.closest('#chip-bar');

        // If anchored in the chip bar, scroll the bar so the chip moves left
        // enough that the dropdown stays left-aligned with it instead of
        // getting clamped against the viewport's right edge.
        if (chipBar) {
            const r = anchorChip.getBoundingClientRect();
            const overflow = r.left + cw + 4 - window.innerWidth;
            if (overflow > 0) {
                const maxScroll = chipBar.scrollWidth - chipBar.clientWidth;
                chipBar.scrollLeft = Math.min(maxScroll, chipBar.scrollLeft + overflow);
            }
        }

        const rect = anchorChip.getBoundingClientRect();
        // Touch the chip's bottom so hover travel is gap-less
        container.style.left = Math.max(4, rect.left) + 'px';
        container.style.top = rect.bottom + 'px';

        // Fallback clamp if the chip bar couldn't scroll far enough
        if (rect.left + cw + 4 > window.innerWidth) {
            container.style.left = Math.max(4, window.innerWidth - cw - 4) + 'px';
        }
    }

    function _hideDescendantDropdown(immediate) {
        clearTimeout(_dropdownCloseTimer);
        clearTimeout(_dropdownOpenTimer);
        if (!_activeDropdown) return;
        const { container } = _activeDropdown;
        _activeDropdown = null;
        if (!container || !container.parentNode) return;

        if (immediate) {
            container.parentNode.removeChild(container);
            return;
        }
        container.classList.add('closing');
        setTimeout(() => {
            if (container.parentNode) container.parentNode.removeChild(container);
        }, 150);
    }

    function _createDropdownChip(tagName, isActive) {
        const btn = _buildChip(tagName, isActive);
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            _handleChipClick(tagName);
        });
        return btn;
    }

    // Close dropdown on outside click/tap or Escape
    document.addEventListener('click', (e) => {
        if (!_activeDropdown) return;
        const { container, anchorChip } = _activeDropdown;
        if (container.contains(e.target) || (anchorChip && anchorChip.contains(e.target))) return;
        _hideDescendantDropdown(false);
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && _activeDropdown) _hideDescendantDropdown(false);
    });
    window.addEventListener('resize', () => _hideDescendantDropdown(true));
    window.addEventListener('scroll', (e) => {
        // Chip bar scrolls itself when positioning the dropdown; ignore those.
        if (e.target instanceof Element && e.target.id === 'chip-bar') return;
        _hideDescendantDropdown(true);
    }, true);

    // ========================================
    // RENDERING COORDINATION
    // ========================================

    /**
     * Main render function that coordinates SearchManager and SectionRenderer
     * @param {Array} searchResults - Array of search results
     * @param {string} searchTerm - Current search term
     * @param {boolean} [debugMode=false] - Whether debug mode is enabled
     */
    function renderFilters(searchResults = [], searchTerm = '', debugMode = false) {
        state.searchTerm = searchTerm;
        state.lastSearchResults = searchResults;
        state.debugMode = debugMode;

        if (!state.resultsContainerDOM) return;

        const sheet = (typeof Sheet !== 'undefined') ? Sheet : null;

        // A search term (or debug mode) auto-opens the sheet so the results are
        // visible as the user types (mobile: snaps the bottom sheet to peek).
        if (sheet && (searchTerm || debugMode)) {
            sheet.open();
        }

        // No search term: the sheet shows the nearby-events list view instead
        // of search sections. We only render it while the browse content is
        // actually on screen (skip rendering 200 cards off-screen on every map
        // pan); the sheet fires onToggle when it opens, triggering a re-render.
        if (!searchTerm && !debugMode && typeof ListView !== 'undefined') {
            const showList = (!sheet || sheet.isBrowseVisible()) && ListView.hasContent();
            if (showList) {
                ListView.render();
            } else {
                state.resultsContainerDOM.innerHTML = '';
                state.resultsContainerDOM.scrollTop = 0;
            }
            // Mirror SectionRenderer's onAfterRender: keep the chip bar in sync.
            const shouldAnimate = _chipBarAnimateNext;
            _chipBarAnimateNext = false;
            _renderChipBar(shouldAnimate);
            return;
        }

        // A search term (or debug mode) takes over the results container — tear
        // down any list view that was showing.
        if (typeof ListView !== 'undefined') ListView.teardown();

        if (!searchResults || searchResults.length === 0) {
            state.resultsContainerDOM.innerHTML = '';
            state.resultsContainerDOM.scrollTop = 0;
            // Mirror SectionRenderer's onAfterRender so the chip bar resyncs
            // to the current term even when the search has no results.
            const shouldAnimate = _chipBarAnimateNext;
            _chipBarAnimateNext = false;
            _renderChipBar(shouldAnimate);
            return;
        }

        FilterProfiler.mark('fp:panel:group-start');

        // Group and sort results using SearchManager
        const { groupedResults, hiddenResults } = SearchManager.groupAndSortResults(
            searchResults,
            searchTerm,
            providers.getSelectedLocationKey,
            (tag) => TagStateManager.getTagState(tag)
        );

        FilterProfiler.mark('fp:panel:group-end');
        FilterProfiler.measure('fp:panel:groupResults', 'fp:panel:group-start', 'fp:panel:group-end');

        // Render using SectionRenderer
        SectionRenderer.renderFilters(groupedResults, hiddenResults, searchTerm, debugMode);
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the FilterPanelUI module
     * @param {Object} config - Configuration object
     * @param {Array} config.allAvailableTags - All available tags
     * @param {Object} config.initialGlobalFrequencies - Initial tag frequencies
     * @param {HTMLElement} config.resultsContainerDOM - Container for search results
     * @param {Function} config.onFilterChangeCallback - Callback when filters change
     * @param {Function} config.onSearchResultClick - Callback when search result clicked
     * @param {Function} config.performSearch - Function to perform search
     * @param {Function} config.getSearchTerm - Function to get current search term
     * @param {Object} config.colorProvider - Provider for tag color operations
     * @param {Function} config.colorProvider.getTagColor - Get tag color
     * @param {Function} config.colorProvider.assignColorToTag - Assign color to tag
     * @param {Function} config.colorProvider.unassignColorFromTag - Unassign color from tag
     */
    function init(config) {
        // Extract provider and assign rest to state
        state.colorProvider = config.colorProvider || null;
        state.allAvailableTags = config.allAvailableTags || [];
        _rebuildTagCaches();
        state.tagDescendantsOf = config.tagDescendantsOf || {};
        state.tagParentsOf = config.tagParentsOf || {};
        state.tagChildrenOf = config.tagChildrenOf || {};
        // Structural Format nodes (Format root + its category children) are kept in
        // the hierarchy for grouping but never shown as chips. Prefer the value
        // computed in DataManager; fall back to deriving from the hierarchy here so
        // this never depends on init ordering.
        state.structuralFormatTags = config.structuralFormatTags
            || new Set(['Format', ...(((config.tagChildrenOf || {})['Format']) || [])]);
        state.tagEmojiMap = config.tagEmojiMap || {};
        state.getSelectedTagsWithColors = config.getSelectedTagsWithColors || null;
        state.resultsContainerDOM = config.resultsContainerDOM;
        state.onFilterChangeCallback = config.onFilterChangeCallback;
        state.onSearchResultClick = config.onSearchResultClick;
        state.initialGlobalFrequencies = { ...config.initialGlobalFrequencies };
        state.currentDynamicFrequencies = { ...config.initialGlobalFrequencies };

        if (config.getSearchTerm) {
            state.getSearchTerm = config.getSearchTerm;
        }
        if (config.getVisibleTagFrequencies) {
            state.getVisibleTagFrequencies = config.getVisibleTagFrequencies;
        }

        // Initialize section order and view states based on device type (only on first init)
        if (!state.sectionOrder) {
            state.sectionOrder = getDefaultSectionOrder();
        }

        // Initialize tag states
        state.allAvailableTags.forEach(tag => {
            state.tagStates[tag] = TAG_STATE.UNSELECTED;
        });

        if (!state.resultsContainerDOM) {
            console.error("FilterPanelUI: resultsContainerDOM is not provided.");
            return;
        }

        performSearchCallback = config.performSearch || performSearchCallback;

        // Initialize TagStateManager with provider objects
        TagStateManager.init({
            tagStates: state.tagStates,
            colorProvider: state.colorProvider,
            onFilterChangeCallback: state.onFilterChangeCallback,
            tagEmojiMap: state.tagEmojiMap
        });

        // Initialize SectionRenderer
        SectionRenderer.init({
            resultsContainerDOM: state.resultsContainerDOM,
            sectionOrder: state.sectionOrder,
            createSearchResultButton: (result) => TagStateManager.createSearchResultButton(result, state.onSearchResultClick, state.debugMode),
            onSectionReorder: (newOrder) => {
                state.sectionOrder = newOrder;
            },
            onAfterRender: () => {
                const shouldAnimate = _chipBarAnimateNext;
                _chipBarAnimateNext = false;
                _renderChipBar(shouldAnimate);
            }
        });

        _renderChipBar();
        _initChipBarWheelScroll();

        // Initialize GestureHandler (desktop only — conflicts with horizontal tag scroll on mobile)
        if (!isMobileLayout()) {
            GestureHandler.init({
                containerDOM: state.resultsContainerDOM,
                sectionOrder: state.sectionOrder,
                onSectionReorder: (newOrder) => {
                    state.sectionOrder = newOrder;
                },
                performSearchCallback: () => performSearchCallback(state.searchTerm)
            });
        }
    }

    /**
     * Sets application-level providers
     * @param {Object} appProviders - Provider functions
     */
    function setAppProviders(appProviders) {
        Object.assign(providers, appProviders);
    }

    /**
     * Lightweight refresh used after Phase 2 data merge. Updates the available
     * tag list and global frequencies WITHOUT resetting `tagStates` — so any
     * tags the user clicked during Phase 1 stay selected. New tags introduced
     * by the full dataset are added as UNSELECTED. Tags that disappeared keep
     * their state but won't be rendered.
     *
     * Caller should follow this with `filterAndDisplayEvents()` to trigger
     * a normal render cycle that picks up the refreshed frequencies.
     */
    function refreshAvailableTags(updates = {}) {
        if (updates.allAvailableTags) {
            state.allAvailableTags = updates.allAvailableTags;
            for (const tag of state.allAvailableTags) {
                if (!(tag in state.tagStates)) {
                    state.tagStates[tag] = TAG_STATE.UNSELECTED;
                }
            }
            _rebuildTagCaches();
        }
        if (updates.initialGlobalFrequencies) {
            state.initialGlobalFrequencies = { ...updates.initialGlobalFrequencies };
        }
    }

    /**
     * Updates the view with filtered events
     * @param {Array} filteredEvents - Array of filtered events
     */
    function updateView(filteredEvents) {
        FilterProfiler.mark('fp:updateView:start');

        state.currentDynamicFrequencies = {};
        state.allAvailableTags.forEach(tag => state.currentDynamicFrequencies[tag] = 0);

        if (filteredEvents && Array.isArray(filteredEvents)) {
            const tagLocationSets = {};

            filteredEvents.forEach(event => {
                if (event.tags && Array.isArray(event.tags) && event.locationKey) {
                    event.tags.forEach(tag => {
                        if (_availableTagsSet.has(tag)) {
                            if (!tagLocationSets[tag]) {
                                tagLocationSets[tag] = new Set();
                            }
                            tagLocationSets[tag].add(event.locationKey);
                        }
                    });
                }
            });

            for (const tag in tagLocationSets) {
                state.currentDynamicFrequencies[tag] = tagLocationSets[tag].size;
            }
        }

        FilterProfiler.mark('fp:updateView:freq-done');
        FilterProfiler.measure('fp:updateView:freq', 'fp:updateView:start', 'fp:updateView:freq-done');

        performSearchCallback(state.getSearchTerm());

        FilterProfiler.mark('fp:updateView:end');
        FilterProfiler.measure('fp:updateView:performSearch', 'fp:updateView:freq-done', 'fp:updateView:end');
    }

    /**
     * Gets current tag states
     * @returns {Object} Live reference — treat as read-only. All consumers
     *     iterate immediately (HistoryManager copies what it keeps); none
     *     mutate or retain it across tag-state changes.
     */
    function getTagStates() {
        return state.tagStates;
    }

    /**
     * Gets current dynamic frequencies
     * @returns {Object} Live reference — treat as read-only (see getTagStates)
     */
    function getDynamicFrequencies() {
        return state.currentDynamicFrequencies;
    }

    /**
     * Programmatically selects tags (used for URL parameters)
     * @param {Array<string>} tagsToSelect - Array of tag names to select
     * @param {Function} assignColorCallback - Callback to assign colors to selected tags
     */
    function selectTags(tagsToSelect, assignColorCallback) {
        if (!Array.isArray(tagsToSelect)) {
            return;
        }

        tagsToSelect.forEach(tag => {
            // Organizer pseudo-tags are valid filter keys even though they're not
            // in the browsable tag list — select them directly.
            if (Utils.isOrganizerTag(tag)) {
                const oldState = state.tagStates[tag];
                state.tagStates[tag] = TAG_STATE.SELECTED;
                if (oldState !== TAG_STATE.SELECTED && assignColorCallback) {
                    assignColorCallback(tag);
                }
                return;
            }

            // Try exact match first, then case-insensitive match
            let matchedTag = tag;
            if (!state.allAvailableTags.includes(tag)) {
                matchedTag = state.allAvailableTags.find(t => t.toLowerCase() === tag.toLowerCase());
            }

            if (matchedTag && state.allAvailableTags.includes(matchedTag)) {
                const oldState = state.tagStates[matchedTag];
                state.tagStates[matchedTag] = TAG_STATE.SELECTED;

                // Assign color if transitioning from unselected
                if (oldState === TAG_STATE.UNSELECTED && assignColorCallback) {
                    assignColorCallback(matchedTag);
                }
            } else {
                console.warn(`Tag "${tag}" not found in available tags`);
            }
        });
    }

    // ========================================
    // SEARCH INITIALIZATION
    // ========================================

    /**
     * Initialize the search input functionality
     * Delegates to SearchController for input handling
     * @param {Object} config - Configuration object
     * @param {Function} config.onSpecialSearchTerm - Callback for special search terms (debug, noto)
     */
    function initOmniSearch(config) {
        // Delegate to SearchController
        SearchController.init({
            onSpecialSearchTerm: config.onSpecialSearchTerm,
            performSearchCallback: performSearchCallback
        });
    }

    // ========================================
    // EXPORTS
    // ========================================

    /**
     * Re-render the panel with the last search/debug state. Used when the left
     * sheet opens so the (previously skipped) list view populates.
     */
    function rerender() {
        renderFilters(state.lastSearchResults || [], state.searchTerm || '', state.debugMode);
    }

    return {
        init,
        initOmniSearch,
        setAppProviders,
        refreshAvailableTags,
        updateView,
        getTagStates,
        getDynamicFrequencies,
        selectTags,
        setTagState: (tag, state) => TagStateManager.setTagState(tag, state),
        createInteractiveTagButton: (tag) => TagStateManager.createInteractiveTagButton(tag),
        updateAllTagVisuals: () => TagStateManager.updateAllTagVisuals(),
        render: renderFilters,
        renderChipBar: _renderChipBar,
        rerender,
    };
})();
