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
        defaultMarkerColor: null,
        debugMode: false,

        // Frequencies (tag usage counts)
        initialGlobalFrequencies: {},
        currentDynamicFrequencies: {},

        // Tag states (managed by TagStateManager)
        tagStates: {},

        // Search state (SearchController handles input events)
        searchTerm: '',
        lastSearchResults: [],
        lastSearchTerm: '',
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

    /**
     * Determines if the current window is mobile-sized
     * @returns {boolean} True if window width is at or below mobile breakpoint
     */
    function isMobileLayout() {
        const breakpoint = (typeof Constants !== 'undefined' && Constants.UI && Constants.UI.MOBILE_BREAKPOINT)
            ? Constants.UI.MOBILE_BREAKPOINT
            : 768;
        return window.innerWidth <= breakpoint;
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
     * Gets the default section view states based on device type
     * Desktop: tags expanded, others collapsed
     * Mobile: all sections collapsed
     * @returns {Object} Section view states
     */
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
    // SEARCH HANDLING (delegated to SearchController)
    // ========================================

    /**
     * Clears the search input and results
     * Delegates to SearchController for input clearing
     */
    function clearSearch() {
        SearchController.clearSearch();
        state.searchTerm = '';
        renderFilters([]);
    }

    // ========================================
    // CHIP BAR
    // ========================================

    const CHIP_BAR_MAX_LINES = 3;
    const CHIP_BAR_RENDER_LIMIT = 100; // render up to this many, then trim to fit lines
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
        const TAG_STATE = TagStateManager.getTagStateConstants();
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

        FilterProfiler.mark('fp:chipbar:start');

        // Anchored chip elements are about to be discarded; close any open dropdown.
        _hideDescendantDropdown(true);

        const TAG_STATE = TagStateManager.getTagStateConstants();

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

            const normalizedTag = Utils.normalizeForSearch(tag);

            // When searching, only include tags whose name matches the term
            if (hasSearch && !normalizedTag.includes(normalizedSearchTerm)) continue;

            const freq = state.currentDynamicFrequencies[tag] || 0;
            if (!hasSearch && freq <= 0) continue;

            // Base score: dynamic frequency (same as SearchManager)
            let score = freq;

            if (hasSearch) {
                // Exact match boost
                if (normalizedTag === normalizedSearchTerm) {
                    score += 1000;
                }
            }

            // Viewport visibility boost
            const visFreq = visibleFreqs[tag] || 0;
            if (visFreq > 0) {
                score += visFreq * 5;
                score += 5;
            }

            // Global frequency tiebreaker
            const globalFreq = state.initialGlobalFrequencies[tag] || 0;
            score += globalFreq * 0.01;

            // Descendant aggregation: parent tags get credit for children's scores
            const descendants = state.tagDescendantsOf[tag];
            if (descendants) {
                descendants.forEach(d => {
                    const dFreq = state.currentDynamicFrequencies[d] || 0;
                    const dVisFreq = visibleFreqs[d] || 0;
                    score += dFreq;
                    if (dVisFreq > 0) {
                        score += dVisFreq * 5 + 5;
                    }
                    score += (state.initialGlobalFrequencies[d] || 0) * 0.01;
                });
            }

            if (score <= 0) continue;

            unselectedTags.push({ tag, score });
        }

        // Sort unselected by descending score
        unselectedTags.sort((a, b) => b.score - a.score);

        FilterProfiler.mark('fp:chipbar:scored');
        FilterProfiler.measure('fp:chipbar:score', 'fp:chipbar:start', 'fp:chipbar:scored');

        // 4. Build DOM with generous limit, then trim to fit max lines
        const unselectedToRender = unselectedTags.slice(0, CHIP_BAR_RENDER_LIMIT);

        // FLIP: capture old chip positions before rebuilding
        const oldPositions = new Map();
        for (const chip of container.children) {
            const tag = chip.dataset.primaryTag;
            if (tag) {
                const rect = chip.getBoundingClientRect();
                oldPositions.set(tag, { left: rect.left, top: rect.top });
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

        const hasChips = selectedTagNames.size > 0 || unselectedToRender.length > 0;
        container.style.display = hasChips ? 'flex' : 'none';

        FilterProfiler.mark('fp:chipbar:dom-built');
        FilterProfiler.measure('fp:chipbar:dom-build', 'fp:chipbar:flip-capture', 'fp:chipbar:dom-built');

        // Trim to max lines on desktop (mobile is single-row horizontal scroll)
        if (hasChips && !isMobileLayout()) {
            _trimChipBarToMaxLines(container);
            _updateChipBarLayout(container);
        }

        FilterProfiler.mark('fp:chipbar:trimmed');
        FilterProfiler.measure('fp:chipbar:trim+layout', 'fp:chipbar:dom-built', 'fp:chipbar:trimmed');

        // FLIP: animate chips from old positions to new positions
        if (animate && oldPositions.size > 0) {
            const chipsToSlide = [];
            for (const chip of container.children) {
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
        FilterProfiler.measure('fp:chipbar:flip-apply', 'fp:chipbar:trimmed', 'fp:chipbar:end');
        FilterProfiler.measure('fp:chipbar:total', 'fp:chipbar:start', 'fp:chipbar:end');
    }

    /**
     * If fewer than 6 chips are visible inline, move chip bar to its own row.
     */
    function _updateChipBarLayout(container) {
        const filterContainer = document.getElementById('filter-container');
        if (!filterContainer) return;

        // Count chips visible within the container bounds
        const containerRect = container.getBoundingClientRect();
        let visibleCount = 0;
        for (const chip of container.children) {
            const chipRect = chip.getBoundingClientRect();
            if (chipRect.top < containerRect.bottom && chipRect.right <= containerRect.right + 1) {
                visibleCount++;
            }
        }

        const needsOwnRow = visibleCount < 6 && container.children.length >= 6;
        filterContainer.classList.toggle('chips-below', needsOwnRow);

        if (needsOwnRow) {
            // Align chip bar left edge with search bar (skip past logo)
            const logo = document.getElementById('logo-menu-wrapper');
            if (logo) {
                const gap = 10; // matches #filter-container > div:first-child gap
                container.style.marginLeft = (logo.offsetWidth + gap) + 'px';
            }
            // Re-trim after layout change since more chips may now fit
            _trimChipBarToMaxLines(container);
        } else {
            container.style.marginLeft = '';
        }
    }

    /**
     * Removes unselected chips that overflow past CHIP_BAR_MAX_LINES rows.
     * Measures actual rendered positions to account for variable chip widths.
     */
    function _trimChipBarToMaxLines(container) {
        const chips = container.children;
        if (chips.length === 0) return;

        // Find the top of the first chip to establish the baseline
        const firstTop = chips[0].offsetTop;
        let lineCount = 1;
        let prevTop = firstTop;

        for (let i = 1; i < chips.length; i++) {
            const chipTop = chips[i].offsetTop;
            if (chipTop > prevTop) {
                lineCount++;
                prevTop = chipTop;
            }
            if (lineCount > CHIP_BAR_MAX_LINES && !chips[i].classList.contains('active')) {
                // Remove this and all subsequent unselected chips
                while (container.children.length > i) {
                    container.removeChild(container.lastChild);
                }
                return;
            }
        }
    }

    /**
     * Creates a chip bar button element
     */
    function _createChipButton(tagName, isActive) {
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

        const emoji = state.tagEmojiMap[tagName] || '';
        if (emoji) {
            const emojiSpan = document.createElement('span');
            emojiSpan.className = 'chip-emoji';
            emojiSpan.setAttribute('aria-hidden', 'true');
            emojiSpan.textContent = emoji;
            btn.appendChild(emojiSpan);
        }
        btn.appendChild(document.createTextNode(Utils.getTagDisplayName(tagName)));

        btn.addEventListener('click', () => _handleChipClick(tagName));
        _attachDescendantDropdownTriggers(btn, tagName);
        return btn;
    }

    // ========================================
    // DESCENDANT DROPDOWN
    // ========================================

    /**
     * Scores a tag using the same shape as the chip bar.
     * Returns null if the tag should be dropped (no signal for it).
     */
    function _scoreRelatedTag(tag, visibleFreqs) {
        const freq = state.currentDynamicFrequencies[tag] || 0;
        const visFreq = visibleFreqs[tag] || 0;
        let score = freq;
        if (visFreq > 0) score += visFreq * 5 + 5;
        score += (state.initialGlobalFrequencies[tag] || 0) * 0.01;
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

    /**
     * Attaches hover, long-press, and right-click handlers that open a dropdown
     * of descendant chips below the given chip button.
     */
    function _attachDescendantDropdownTriggers(btn, tagName) {
        if (!_hasDropdownContent(tagName)) return;

        btn.addEventListener('mouseenter', () => {
            clearTimeout(_dropdownCloseTimer);
            if (_activeDropdown && _activeDropdown.tagName === tagName) return;
            clearTimeout(_dropdownOpenTimer);
            _dropdownOpenTimer = setTimeout(() => {
                _showDescendantDropdown(btn, tagName);
            }, DESCENDANT_HOVER_OPEN_DELAY);
        });

        btn.addEventListener('mouseleave', () => {
            clearTimeout(_dropdownOpenTimer);
            _scheduleDropdownClose();
        });

        btn.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            clearTimeout(_dropdownOpenTimer);
            _showDescendantDropdown(btn, tagName);
        });

        btn.addEventListener('touchstart', () => {
            clearTimeout(_longPressTimer);
            _longPressTimer = setTimeout(() => {
                _showDescendantDropdown(btn, tagName);
                _longPressTimer = null;
            }, DESCENDANT_LONG_PRESS_MS);
        }, { passive: true });

        const cancelLongPress = () => {
            if (_longPressTimer) {
                clearTimeout(_longPressTimer);
                _longPressTimer = null;
            }
        };
        btn.addEventListener('touchend', cancelLongPress);
        btn.addEventListener('touchcancel', cancelLongPress);
        btn.addEventListener('touchmove', cancelLongPress, { passive: true });
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

        const TAG_STATE = TagStateManager.getTagStateConstants();
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
        const btn = document.createElement('button');
        btn.className = isActive ? 'tag-button state-selected' : 'tag-button state-unselected';
        btn.dataset.primaryTag = tagName;
        btn.setAttribute('aria-label', `Filter by ${tagName}`);

        if (isActive && state.colorProvider) {
            const color = state.colorProvider.getTagColor(tagName);
            if (color) btn.style.setProperty('--chip-color', color);
        }

        const emoji = state.tagEmojiMap[tagName] || '';
        if (emoji) {
            const emojiSpan = document.createElement('span');
            emojiSpan.className = 'chip-emoji';
            emojiSpan.setAttribute('aria-hidden', 'true');
            emojiSpan.textContent = emoji;
            btn.appendChild(emojiSpan);
        }
        btn.appendChild(document.createTextNode(Utils.getTagDisplayName(tagName)));

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
        state.lastSearchTerm = searchTerm;
        state.debugMode = debugMode;

        if (!state.resultsContainerDOM) return;

        const filterPanel = !isMobileLayout()
            ? state.resultsContainerDOM.closest('#filter-panel')
            : null;

        // Desktop, no search term: show the event list view in place of search
        // sections. Keep the panel full-height when the list has content (so it
        // can scroll); collapse it when there are no matching events.
        if (filterPanel && !searchTerm && !debugMode && typeof ListView !== 'undefined') {
            const showList = ListView.isVisible() && ListView.hasContent();
            filterPanel.classList.toggle('sections-hidden', !showList);
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

        // Toggle panel height based on whether sections will be shown (desktop only)
        if (filterPanel) {
            const showSections = !!searchTerm || debugMode;
            filterPanel.classList.toggle('sections-hidden', !showSections);
        }

        // A search term (or debug mode) takes over the results container — tear
        // down any list view that was showing.
        if (typeof ListView !== 'undefined') ListView.teardown();

        if (!searchResults || searchResults.length === 0) {
            state.resultsContainerDOM.innerHTML = '';
            state.resultsContainerDOM.scrollTop = 0;
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

        // Render using SectionRenderer (onAfterRender distributes to bottom sheet on mobile)
        SectionRenderer.renderFilters(groupedResults, hiddenResults, searchTerm, debugMode);
    }

    /**
     * On mobile, distributes each section into its own tab in the bottom sheet.
     * The top bar keeps only search + date.
     */
    function _distributeContentMobile() {
        if (!isMobileLayout() || typeof BottomSheet === 'undefined') return;
        const container = state.resultsContainerDOM;
        if (!container) return;

        // Extract each section and pass to the bottom sheet's tab panels
        const sections = {};
        const locationSection = container.querySelector('[data-section-key="locations"]');
        const eventSection = container.querySelector('[data-section-key="events"]');
        const tagSection = container.querySelector('[data-section-key="tags"]');
        const organizerSection = container.querySelector('[data-section-key="organizers"]');

        if (locationSection) sections.locations = locationSection;
        if (eventSection) sections.events = eventSection;
        if (tagSection) sections.tags = tagSection;
        if (organizerSection) sections.organizers = organizerSection;

        BottomSheet.updateBrowseTabs(sections);
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
     * @param {string} config.defaultMarkerColor - Default marker color
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
        state.defaultMarkerColor = config.defaultMarkerColor;
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
        const TAG_STATE = TagStateManager.getTagStateConstants();
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
            defaultMarkerColor: state.defaultMarkerColor,
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
                _distributeContentMobile();
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
        const TAG_STATE = TagStateManager.getTagStateConstants();
        if (updates.allAvailableTags) {
            state.allAvailableTags = updates.allAvailableTags;
            for (const tag of state.allAvailableTags) {
                if (!(tag in state.tagStates)) {
                    state.tagStates[tag] = TAG_STATE.UNSELECTED;
                }
            }
        }
        if (updates.initialGlobalFrequencies) {
            state.initialGlobalFrequencies = { ...updates.initialGlobalFrequencies };
        }
    }

    /**
     * Populates initial filters
     */
    function populateInitialFilters() {
        const TAG_STATE = TagStateManager.getTagStateConstants();
        state.currentDynamicFrequencies = { ...state.initialGlobalFrequencies };
        state.allAvailableTags.forEach(tag => {
            state.tagStates[tag] = TAG_STATE.UNSELECTED;
        });
        renderFilters();
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
            const availableTagsSet = new Set(state.allAvailableTags);

            filteredEvents.forEach(event => {
                if (event.tags && Array.isArray(event.tags) && event.locationKey) {
                    event.tags.forEach(tag => {
                        if (availableTagsSet.has(tag)) {
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
     * @returns {Object} Copy of tag states
     */
    function getTagStates() {
        return { ...state.tagStates };
    }

    /**
     * Gets current dynamic frequencies
     * @returns {Object} Copy of dynamic frequencies
     */
    function getDynamicFrequencies() {
        return { ...state.currentDynamicFrequencies };
    }

    /**
     * Resets all tag selections
     */
    function resetSelections() {
        const TAG_STATE = TagStateManager.getTagStateConstants();
        state.allAvailableTags.forEach(tag => {
            state.tagStates[tag] = TAG_STATE.UNSELECTED;
        });
        clearSearch('');
        _renderChipBar();
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

        const TAG_STATE = TagStateManager.getTagStateConstants();

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
     * @param {HTMLElement} config.filterPanelDOM - Filter panel element (for mobile auto-expand)
     * @param {HTMLElement} config.expandFilterPanelButtonDOM - Expand button element (for mobile)
     * @param {Function} config.onSpecialSearchTerm - Callback for special search terms (debug, noto)
     */
    function initOmniSearch(config) {
        // Delegate to SearchController
        SearchController.init({
            filterPanelDOM: config.filterPanelDOM,
            expandFilterPanelButtonDOM: config.expandFilterPanelButtonDOM,
            onSpecialSearchTerm: config.onSpecialSearchTerm,
            performSearchCallback: performSearchCallback
        });
    }

    // ========================================
    // EXPORTS
    // ========================================

    /**
     * Flip the desktop event list view on/off and re-render the panel with the
     * last search state. Returns the new visibility (true = list shown).
     */
    function toggleListView() {
        if (typeof ListView === 'undefined') return false;
        const nowVisible = !ListView.isVisible();
        ListView.setVisible(nowVisible);
        renderFilters(state.lastSearchResults || [], state.lastSearchTerm || '', state.debugMode);
        return nowVisible;
    }

    return {
        init,
        initOmniSearch,
        setAppProviders,
        refreshAvailableTags,
        populateInitialFilters,
        updateView,
        getTagStates,
        getDynamicFrequencies,
        resetSelections,
        selectTags,
        setTagState: (tag, state) => TagStateManager.setTagState(tag, state),
        createInteractiveTagButton: (tag) => TagStateManager.createInteractiveTagButton(tag),
        updateAllTagVisuals: () => TagStateManager.updateAllTagVisuals(),
        render: renderFilters,
        renderChipBar: _renderChipBar,
        toggleListView,
        clearSearch,
    };
})();
