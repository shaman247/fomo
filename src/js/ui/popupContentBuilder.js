/**
 * PopupContentBuilder Module
 *
 * Builds tabbed popup content for location markers with sections:
 * - Event sections (Events, Ongoing, or custom) based on event.section field
 * - Info tab with venue description, website, and address
 *
 * Tabs support horizontal swipe navigation (similar to bottom sheet tabs).
 *
 * @module PopupContentBuilder
 */
const PopupContentBuilder = (() => {
    // ========================================
    // CONSTANTS
    // ========================================

    const TAB_SWIPE_THRESHOLD = 8;       // px to commit to horizontal swipe
    const SWIPE_COMMIT_FRACTION = 0.25;  // fraction of viewport width to snap

    // Section display order: Events first, Ongoing second, custom alphabetical
    const SECTION_ORDER = { 'Events': 0, 'Ongoing': 1 };

    const LINK_ICON_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>';

    const LINK_ICON_SVG_16 = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>';

    // ========================================
    // STATE
    // ========================================

    const state = {
        createInteractiveTagButton: null,
        hierarchyTagsSet: new Set(),
        tagEmojiMap: {}
    };

    // ========================================
    // POPUP HEADER (simplified — no expandable detail)
    // ========================================

    function createPopupHeader(locationInfo) {
        const headerWrapper = document.createElement('div');
        headerWrapper.className = 'popup-header';

        const emojiSpan = document.createElement('span');
        emojiSpan.className = 'popup-header-emoji';
        emojiSpan.textContent = Utils.escapeHtml(locationInfo.emoji);
        headerWrapper.appendChild(emojiSpan);

        const textWrapper = document.createElement('div');
        textWrapper.className = 'popup-header-text';

        const locationP = document.createElement('p');
        locationP.className = 'popup-header-location';
        locationP.innerHTML = Utils.formatAndSanitize(locationInfo.name);
        textWrapper.appendChild(locationP);

        // Tab bar will be inserted here by the main builder

        headerWrapper.appendChild(textWrapper);
        return headerWrapper;
    }

    // ========================================
    // TAG HELPERS
    // ========================================

    /**
     * Creates a display-only keyword tag span (non-clickable)
     */
    function createKeywordTagSpan(tag) {
        const span = document.createElement('span');
        span.className = 'tag-keyword';
        const emoji = state.tagEmojiMap[tag] || '';
        if (emoji) {
            const emojiSpan = document.createElement('span');
            emojiSpan.className = 'chip-emoji';
            emojiSpan.setAttribute('aria-hidden', 'true');
            emojiSpan.textContent = emoji;
            span.appendChild(emojiSpan);
        }
        span.appendChild(document.createTextNode(tag));
        return span;
    }

    /**
     * Creates the appropriate element for a tag: interactive button for curated tags,
     * display-only span for keyword tags
     */
    function createTagElement(tag) {
        const isCurated = state.hierarchyTagsSet.size === 0 || state.hierarchyTagsSet.has(tag);
        if (isCurated && state.createInteractiveTagButton) {
            return state.createInteractiveTagButton(tag);
        }
        return createKeywordTagSpan(tag);
    }

    // ========================================
    // INFO PANEL
    // ========================================

    function createInfoPanel(locationInfo, displayTags = []) {
        const panel = document.createElement('div');
        panel.className = 'popup-info-panel';

        if (locationInfo.description) {
            const descP = document.createElement('p');
            descP.className = 'popup-info-description';
            descP.textContent = locationInfo.description;
            panel.appendChild(descP);
        }

        if (locationInfo.website_url) {
            const linksDiv = document.createElement('div');
            linksDiv.className = 'popup-info-links';
            try {
                const domain = new URL(locationInfo.website_url).hostname.replace(/^www\./, '');
                const a = document.createElement('a');
                a.href = locationInfo.website_url;
                a.target = '_blank';
                a.rel = 'noopener noreferrer';
                a.innerHTML = `${LINK_ICON_SVG} ${Utils.escapeHtml(domain)}`;
                linksDiv.appendChild(a);
            } catch {
                // Skip invalid URL
            }
            panel.appendChild(linksDiv);
        }

        if (locationInfo.address) {
            const addressP = document.createElement('p');
            addressP.className = 'popup-info-address';
            addressP.textContent = locationInfo.address;
            panel.appendChild(addressP);
        }

        if (displayTags.length > 0) {
            const tagsContainer = document.createElement('div');
            tagsContainer.className = 'tag-tags-container popup-tags-container';
            displayTags.forEach(tag => {
                const el = createTagElement(tag);
                if (el) tagsContainer.appendChild(el);
            });
            panel.appendChild(tagsContainer);
        }

        return panel;
    }

    // ========================================
    // TAB SWIPE SYSTEM
    // ========================================

    function setupTabSwipe(viewport, track, tabButtons, tabCount) {
        let activeTab = 0;
        let swipeStartX = 0;
        let swipeStartY = 0;
        let trackStartOffset = 0;
        let isSwiping = false;
        let isScrolling = false;

        function getTrackOffset() {
            const match = track.style.transform.match(/translateX\((.+?)px\)/);
            return match ? parseFloat(match[1]) : 0;
        }

        function switchToTab(index, animate = false) {
            activeTab = Math.max(0, Math.min(tabCount - 1, index));
            const offset = -activeTab * viewport.offsetWidth;
            track.classList.toggle('no-transition', !animate);
            track.style.transform = `translateX(${offset}px)`;
            if (!animate) {
                track.offsetHeight; // force reflow
                track.classList.remove('no-transition');
            }
            tabButtons.forEach((btn, i) => btn.classList.toggle('active', i === activeTab));
        }

        // Tab button clicks
        tabButtons.forEach((btn, i) => {
            btn.addEventListener('click', () => switchToTab(i, true));
        });

        // Touch swipe handlers
        viewport.addEventListener('touchstart', (e) => {
            swipeStartX = e.touches[0].clientX;
            swipeStartY = e.touches[0].clientY;
            trackStartOffset = getTrackOffset();
            isSwiping = false;
            isScrolling = false;
        }, { passive: true });

        viewport.addEventListener('touchmove', (e) => {
            if (isScrolling) return;
            const dx = e.touches[0].clientX - swipeStartX;
            const dy = e.touches[0].clientY - swipeStartY;
            if (!isSwiping) {
                if (Math.abs(dx) < TAB_SWIPE_THRESHOLD && Math.abs(dy) < TAB_SWIPE_THRESHOLD) return;
                // Vertical movement dominates — let the browser handle scrolling
                if (Math.abs(dy) > Math.abs(dx)) {
                    isScrolling = true;
                    return;
                }
                isSwiping = true;
                track.classList.add('no-transition');
            }
            e.preventDefault();

            // Apply rubber-banding at edges
            let offset = trackStartOffset + dx;
            const minOffset = -(tabCount - 1) * viewport.offsetWidth;
            if (offset > 0) {
                offset *= 0.3;
            } else if (offset < minOffset) {
                offset = minOffset + (offset - minOffset) * 0.3;
            }
            track.style.transform = `translateX(${offset}px)`;
        }, { passive: false });

        viewport.addEventListener('touchend', (e) => {
            if (!isSwiping) return;
            isSwiping = false;

            const rawDx = (e.changedTouches?.[0]?.clientX || swipeStartX) - swipeStartX;
            const w = viewport.offsetWidth;
            let target = activeTab;

            if (rawDx < -w * SWIPE_COMMIT_FRACTION) target = activeTab + 1;
            else if (rawDx > w * SWIPE_COMMIT_FRACTION) target = activeTab - 1;

            switchToTab(target, true);
        });

        return { switchToTab };
    }

    // ========================================
    // EVENT DETAIL
    // ========================================

    function createEventDetail(event) {
        const eventDetailContainer = document.createElement('div');
        eventDetailContainer.className = 'popup-event-detail';

        const descriptionP = document.createElement('p');
        descriptionP.innerHTML = Utils.formatAndSanitize(event.description);

        // Handle both new urls array and legacy url field
        // Limit to max 1 URL per distinct domain name
        const urls = event.urls || (event.url ? [event.url] : []);
        if (urls && urls.length > 0) {
            const seenDomains = new Set();
            urls.forEach((url) => {
                if (url && Utils.isValidUrl(url)) {
                    try {
                        const domain = new URL(url).hostname;
                        if (seenDomains.has(domain)) return;
                        seenDomains.add(domain);
                    } catch {
                        // If URL parsing fails, skip domain check and show the link
                    }
                    const urlLink = document.createElement('a');
                    urlLink.href = url;
                    urlLink.target = '_blank';
                    urlLink.rel = 'noopener noreferrer';
                    urlLink.className = 'popup-external-link';
                    urlLink.title = 'More Info (opens in new tab)';
                    urlLink.innerHTML = `  ${LINK_ICON_SVG_16} `;
                    descriptionP.appendChild(urlLink);
                }
            });
        }
        eventDetailContainer.appendChild(descriptionP);

        const tagsToShow = event.display_tags || event.tags;
        if (tagsToShow && tagsToShow.length > 0) {
            const tagsContainer = document.createElement('div');
            tagsContainer.className = 'tag-tags-container popup-tags-container';
            tagsToShow.forEach(tag => {
                const el = createTagElement(tag);
                if (el) tagsContainer.appendChild(el);
            });
            eventDetailContainer.appendChild(tagsContainer);
        }

        return eventDetailContainer;
    }

    // ========================================
    // EVENTS LIST
    // ========================================

    function createEventsList(eventsAtLocation, activeFilters, locationInfo, filterFunctions, forceDisplayEventId = null, selectedStartDate = null) {
        const eventsListWrapper = document.createElement('div');
        eventsListWrapper.className = 'popup-events-list';

        if (eventsAtLocation.length === 0 && !forceDisplayEventId) {
            const noEventsP = document.createElement('p');
            noEventsP.textContent = "No events at this location in the selected date range.";
            eventsListWrapper.appendChild(noEventsP);
            return eventsListWrapper;
        }

        // Get all selected tags
        const selectedTags = Object.entries(activeFilters.tagStates)
            .filter(([, st]) => (st === 'selected' || st === 'required'))
            .map(([tag]) => tag);

        const hasActiveTagFilters = selectedTags.length > 0;
        const hasForbiddenTags = Object.entries(activeFilters.tagStates).some(([, st]) => st === 'forbidden');
        const hasAnyTagFilter = hasActiveTagFilters || hasForbiddenTags;

        let forcedEvent = null;
        let otherEvents = [...eventsAtLocation];

        if (forceDisplayEventId) {
            const forcedEventIndex = otherEvents.findIndex(e => e.id === forceDisplayEventId);
            if (forcedEventIndex > -1) {
                [forcedEvent] = otherEvents.splice(forcedEventIndex, 1);
            }
        }

        const eventsToProcess = forcedEvent ? [forcedEvent, ...otherEvents] : eventsAtLocation;

        // Pre-calculate sort-related properties
        const referenceDate = selectedStartDate ? selectedStartDate.getTime() : (activeFilters.sliderStartDate ? activeFilters.sliderStartDate.getTime() : 0);

        // Pre-compute tag sets once
        const selectedTagsSet = new Set(selectedTags);
        const requiredTagsSet = new Set(
            Object.entries(activeFilters.tagStates)
                .filter(([, s]) => s === 'required')
                .map(([tag]) => tag)
        );
        const forbiddenTagsSet = new Set(
            Object.entries(activeFilters.tagStates)
                .filter(([, s]) => s === 'forbidden')
                .map(([tag]) => tag)
        );

        const eventsWithSortData = eventsToProcess.map(event => {
            const locInfo = event.locationKey ? filterFunctions.getLocationInfo(event.locationKey) : null;
            const combinedTags = event.tags || [];
            const locationTags = locInfo?.tags || [];

            let isMatchingTags = true;
            if (forbiddenTagsSet.size > 0) {
                if (combinedTags.some(t => forbiddenTagsSet.has(t)) || locationTags.some(t => forbiddenTagsSet.has(t))) {
                    isMatchingTags = false;
                }
            }
            if (isMatchingTags && requiredTagsSet.size > 0) {
                for (const tag of requiredTagsSet) {
                    if (!combinedTags.includes(tag) && !locationTags.includes(tag)) {
                        isMatchingTags = false;
                        break;
                    }
                }
            }
            if (isMatchingTags && requiredTagsSet.size === 0 && selectedTagsSet.size > 0) {
                if (!combinedTags.some(t => selectedTagsSet.has(t)) && !locationTags.some(t => selectedTagsSet.has(t))) {
                    isMatchingTags = false;
                }
            }

            let selectedTagMatchCount = 0;
            if (hasActiveTagFilters && isMatchingTags) {
                for (const tag of combinedTags) {
                    if (selectedTagsSet.has(tag)) selectedTagMatchCount++;
                }
                for (const tag of locationTags) {
                    if (selectedTagsSet.has(tag)) selectedTagMatchCount++;
                }
            }
            const startTime = event.occurrences?.[0]?.start?.getTime() || 0;
            const endTime = event.occurrences?.[0]?.end?.getTime() || startTime;

            const isOngoingOnReferenceDate = startTime <= referenceDate && endTime >= referenceDate;
            let distanceFromReference = Math.abs(startTime - referenceDate);
            if (isOngoingOnReferenceDate) {
                distanceFromReference = Math.max(0, distanceFromReference - Constants.TIME.FIVE_DAYS_MS);
            }

            return {
                event,
                isMatchingTags,
                selectedTagMatchCount,
                startTime,
                distanceFromReference
            };
        });

        // Sort: matching first, then by tag count, then by date distance
        eventsWithSortData.sort((a, b) => {
            if (a.isMatchingTags !== b.isMatchingTags) return b.isMatchingTags - a.isMatchingTags;
            if (a.selectedTagMatchCount !== b.selectedTagMatchCount) return b.selectedTagMatchCount - a.selectedTagMatchCount;
            return a.distanceFromReference - b.distanceFromReference;
        });

        // Move forced event to top
        if (forcedEvent) {
            const forcedIdx = eventsWithSortData.findIndex(d => d.event.id === forcedEvent.id);
            if (forcedIdx > 0) {
                const [forcedData] = eventsWithSortData.splice(forcedIdx, 1);
                eventsWithSortData.unshift(forcedData);
            }
        }

        const expandAll = !hasAnyTagFilter && eventsToProcess.length > 0 && eventsToProcess.length < 4;
        let isFirstEvent = true;

        eventsWithSortData.forEach(({ event, isMatchingTags }) => {
            const card = document.createElement('div');
            card.className = 'popup-event-card';

            let shouldOpen = false;
            if (forcedEvent) {
                shouldOpen = (event.id === forcedEvent.id);
            } else if (hasAnyTagFilter) {
                shouldOpen = isMatchingTags;
            } else {
                shouldOpen = expandAll || isFirstEvent;
            }

            // Card header: emoji + name
            const header = document.createElement('div');
            header.className = 'popup-event-card-header';

            if (event.emoji) {
                const emojiSpan = document.createElement('span');
                emojiSpan.className = 'popup-event-emoji';
                emojiSpan.textContent = event.emoji;
                header.appendChild(emojiSpan);
            }

            const info = document.createElement('div');
            info.className = 'popup-event-card-info';

            const nameSpan = document.createElement('span');
            nameSpan.className = 'popup-event-card-name';
            nameSpan.textContent = event.name || '';
            info.appendChild(nameSpan);

            header.appendChild(info);
            card.appendChild(header);

            const datetimeSpan = document.createElement('span');
            datetimeSpan.className = 'popup-event-card-datetime';
            datetimeSpan.textContent = Utils.formatEventDateTimeCompactly(event);
            card.appendChild(datetimeSpan);

            // Description preview (always visible when collapsed)
            if (event.description) {
                const preview = document.createElement('div');
                preview.className = 'popup-event-card-preview';
                preview.textContent = event.description;
                card.appendChild(preview);
            }

            // Detail container (hidden until expanded)
            const detailContainer = document.createElement('div');
            detailContainer.className = 'popup-event-card-detail';
            detailContainer.hidden = true;
            card.appendChild(detailContainer);

            if (shouldOpen) {
                detailContainer.appendChild(createEventDetail(event));
                detailContainer.hidden = false;
                card.dataset.expanded = 'true';
            }

            // Toggle expand/collapse on card click
            card.addEventListener('click', (e) => {
                if (e.target.closest('a, .tag-button, .tag-keyword')) return;
                const isExpanded = card.dataset.expanded === 'true';
                if (isExpanded) {
                    card.dataset.expanded = 'false';
                    detailContainer.hidden = true;
                } else {
                    // Lazy-load detail on first expand
                    if (detailContainer.children.length === 0) {
                        detailContainer.appendChild(createEventDetail(event));
                    }
                    card.dataset.expanded = 'true';
                    detailContainer.hidden = false;
                }
            });

            eventsListWrapper.appendChild(card);
            isFirstEvent = false;
        });

        return eventsListWrapper;
    }

    // ========================================
    // MAIN BUILDER
    // ========================================

    function createLocationPopupContent(locationInfo, eventsAtLocation, activeFilters, geotagsSet, filterFunctions, forceDisplayEventId = null, selectedStartDate = null) {
        const popupContainer = document.createElement('div');
        popupContainer.className = 'maplibre-popup-content';

        // Compute location display tags (leaf tags only, filtered by geotags)
        const displayTags = locationInfo
            ? (locationInfo.display_tags || locationInfo.tags || []).filter(tag => !geotagsSet.has(tag.toLowerCase()))
            : [];

        // Header (emoji + name, tab bar inserted below)
        const header = locationInfo ? createPopupHeader(locationInfo) : null;
        if (header) popupContainer.appendChild(header);

        // Group events by section
        const sectionMap = new Map();
        for (const event of eventsAtLocation) {
            const section = event.section || 'Events';
            if (!sectionMap.has(section)) sectionMap.set(section, []);
            sectionMap.get(section).push(event);
        }

        // Sort sections: Events first, Ongoing second, then custom alphabetical
        const sectionNames = [...sectionMap.keys()].sort((a, b) => {
            const orderA = SECTION_ORDER[a] ?? 2;
            const orderB = SECTION_ORDER[b] ?? 2;
            return orderA !== orderB ? orderA - orderB : a.localeCompare(b);
        });

        // Info tab shown if there are tags, description, address, or website
        const hasInfo = locationInfo && (displayTags.length > 0 || locationInfo.description || locationInfo.address || locationInfo.website_url);

        // Build tab names
        const tabNames = [...sectionNames];
        if (hasInfo) tabNames.push('Info');

        // If no tabs at all (no events, no info), return just the empty container
        if (tabNames.length === 0) {
            return popupContainer;
        }

        // Determine which tab to open by default
        let defaultTab = 0;
        if (forceDisplayEventId) {
            const forcedEvent = eventsAtLocation.find(e => e.id === forceDisplayEventId);
            if (forcedEvent) {
                const idx = sectionNames.indexOf(forcedEvent.section || 'Events');
                if (idx >= 0) defaultTab = idx;
            }
        }

        // Tab bar — placed inside header text wrapper (replacing where tags used to be)
        const tabBar = document.createElement('div');
        tabBar.className = 'popup-tab-bar';
        const tabButtons = tabNames.map((name, i) => {
            const btn = document.createElement('button');
            btn.className = 'popup-tab' + (i === defaultTab ? ' active' : '');
            btn.textContent = name;
            tabBar.appendChild(btn);
            return btn;
        });

        if (header) {
            const textWrapper = header.querySelector('.popup-header-text');
            if (textWrapper) textWrapper.appendChild(tabBar);
        } else {
            popupContainer.appendChild(tabBar);
        }

        // Tab viewport and track
        const viewport = document.createElement('div');
        viewport.className = 'popup-tab-viewport';
        const track = document.createElement('div');
        track.className = 'popup-tab-track';

        // Create event section panels
        for (const sectionName of sectionNames) {
            const panel = document.createElement('div');
            panel.className = 'popup-tab-panel';
            const sectionEvents = sectionMap.get(sectionName);
            // Only pass forceDisplayEventId to the section that contains the forced event
            const forcedInThisSection = forceDisplayEventId && sectionEvents.some(e => e.id === forceDisplayEventId);
            panel.appendChild(createEventsList(
                sectionEvents, activeFilters, locationInfo, filterFunctions,
                forcedInThisSection ? forceDisplayEventId : null,
                selectedStartDate
            ));
            track.appendChild(panel);
        }

        // Info panel (with location tags)
        if (hasInfo) {
            const infoPanel = document.createElement('div');
            infoPanel.className = 'popup-tab-panel';
            infoPanel.appendChild(createInfoPanel(locationInfo, displayTags));
            track.appendChild(infoPanel);
        }

        viewport.appendChild(track);
        popupContainer.appendChild(viewport);

        // Setup tab switching and swipe gestures
        const tabs = setupTabSwipe(viewport, track, tabButtons, tabNames.length);
        if (defaultTab > 0) {
            tabs.switchToTab(defaultTab);
        }

        // Lock explicit pixel heights on track/panels after layout.
        // CSS height:100% doesn't resolve against flex-determined parent heights.
        requestAnimationFrame(() => {
            const h = viewport.offsetHeight;
            if (h > 0) {
                track.style.height = h + 'px';
                track.querySelectorAll('.popup-tab-panel').forEach(p => {
                    p.style.height = h + 'px';
                });
            }
        });

        return popupContainer;
    }

    // ========================================
    // PUBLIC API
    // ========================================

    function init(config) {
        state.createInteractiveTagButton = config.createInteractiveTagButton || null;
        state.hierarchyTagsSet = config.hierarchyTagsSet || new Set();
        state.tagEmojiMap = config.tagEmojiMap || {};
    }

    return {
        init,
        createLocationPopupContent,
        createPopupHeader,
        createEventsList,
        createEventDetail
    };
})();
