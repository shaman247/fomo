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

    // Non-matching occurrences shown inline (dimmed) up to this count; beyond it,
    // a "+N other dates" toggle expands them on demand.
    const INLINE_OTHER_DATES_THRESHOLD = 2;

    // Max organizer chips to render per event card. Merged events can have many
    // source websites (incl. over-merge noise); cap keeps the card readable.
    const ORGANIZER_CHIP_CAP = 5;

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
        tagEmojiMap: {},
        getDebugMode: () => false
    };

    // ========================================
    // POPUP HEADER (simplified — no expandable detail)
    // ========================================

    function createPopupHeader(locationInfo) {
        const headerWrapper = document.createElement('div');
        headerWrapper.className = 'popup-header';

        const emojiSpan = document.createElement('span');
        emojiSpan.className = 'popup-header-emoji';
        emojiSpan.textContent = locationInfo.emoji || '';
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
        Utils.appendChipContent(span, state.tagEmojiMap[tag], tag);
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

        // Render any number of website URLs (locations can link to a directory
        // page and the venue's own site, etc.). Falls back to legacy single
        // website_url field for older exports.
        const locationUrls = locationInfo.website_urls
            || (locationInfo.website_url ? [locationInfo.website_url] : []);
        if (locationUrls.length > 0) {
            const linksDiv = document.createElement('div');
            linksDiv.className = 'popup-info-links';
            const seenDomains = new Set();
            for (const url of locationUrls) {
                try {
                    const domain = new URL(url).hostname.replace(/^www\./, '');
                    if (seenDomains.has(domain)) continue;
                    seenDomains.add(domain);
                    const a = document.createElement('a');
                    a.href = url;
                    a.target = '_blank';
                    a.rel = 'noopener noreferrer';
                    a.innerHTML = `${LINK_ICON_SVG} ${Utils.escapeHtml(domain)}`;
                    linksDiv.appendChild(a);
                } catch {
                    // Skip invalid URL
                }
            }
            if (linksDiv.children.length > 0) {
                panel.appendChild(linksDiv);
            }
        }

        if (locationInfo.address) {
            const addressP = document.createElement('p');
            addressP.className = 'popup-info-address';
            addressP.textContent = locationInfo.address;
            panel.appendChild(addressP);
        }

        if (displayTags.length > 0) {
            // Only show curated tags (from tag hierarchy), hide keywords (unless debug mode)
            const curatedTags = state.hierarchyTagsSet.size > 0 && !state.getDebugMode()
                ? displayTags.filter(tag => state.hierarchyTagsSet.has(tag))
                : displayTags;
            if (curatedTags.length > 0) {
                const tagsContainer = document.createElement('div');
                tagsContainer.className = 'tag-tags-container popup-tags-container';
                curatedTags.forEach(tag => {
                    const el = createTagElement(tag);
                    if (el) tagsContainer.appendChild(el);
                });
                panel.appendChild(tagsContainer);
            }
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
    // ACCENT TINTING
    // ========================================

    /**
     * Set the event-title accents on `el` from a base color. Only the base hue
     * is kept; OKLCH lightness + chroma are pinned (via MapManager) so every
     * title reads as equally bright/saturated regardless of emoji hue.
     *   --popup-accent-muted : darker, lower-chroma — collapsed event titles
     *   --popup-accent-vivid : brighter, higher-chroma — expanded titles
     * (Hover variants are re-derived from these in CSS, scoped per card.)
     */
    function setLabelAccentVars(el, baseColor) {
        if (!el || !baseColor || typeof MapManager === 'undefined' || !MapManager.toEventLabelColor) return;
        const isLight = Utils.getCurrentTheme() === 'light';
        el.style.setProperty(
            '--popup-accent-muted',
            MapManager.toEventLabelColor(baseColor, { lightness: isLight ? 42 : 62, chroma: 0.05 })
        );
        el.style.setProperty(
            '--popup-accent-vivid',
            MapManager.toEventLabelColor(baseColor, { lightness: isLight ? 48 : 76, chroma: 0.13 })
        );
    }

    /**
     * Tint a popup/list container with a location's marker color — the ring
     * color derived from its emoji. Links keep the global teal via --accent-color.
     *   --popup-accent : raw hue (used by the tab pill)
     * The muted/vivid event-title accents are set as a fallback for events with
     * no emoji of their own; each card overrides them via applyEventAccentVars.
     */
    function applyAccentVars(el, locationInfo) {
        if (!el || !locationInfo || typeof MapManager === 'undefined' || !MapManager.getMarkerColor) return;
        const markerColor = MapManager.getMarkerColor(locationInfo);
        if (!markerColor) return;
        el.style.setProperty('--popup-accent', markerColor);
        setLabelAccentVars(el, markerColor);
    }

    /**
     * Tint a single event card's title with the EVENT emoji's color. Falls back
     * to the container's location accent (inherited) when the event has no emoji.
     */
    function applyEventAccentVars(card, event) {
        if (!card || !event || !event.emoji ||
            typeof TagColorManager === 'undefined' || !TagColorManager.getColorForEmoji) return;
        setLabelAccentVars(card, TagColorManager.getColorForEmoji(event.emoji));
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

        // Show curated tags (from tag hierarchy), hide keywords (unless debug mode)
        const curatedTags = (tagsToShow && tagsToShow.length > 0)
            ? (state.hierarchyTagsSet.size > 0 && !state.getDebugMode()
                ? tagsToShow.filter(tag => state.hierarchyTagsSet.has(tag))
                : tagsToShow)
            : [];

        // Organizers render as first-class, interactive tag chips (namespaced
        // pseudo-tags) so they filter identically to topic tags. A merged event
        // can have several organizers — show one chip per KNOWN organizer
        // (aggregators/unknowns are dropped), deduped by display name and capped.
        const organizerTags = [];
        if (state.createInteractiveTagButton) {
            const seenOrgNames = new Set();
            for (const t of Utils.organizerTagsForEvent(event)) {
                if (!Utils.isKnownOrganizerTag(t)) continue;
                const label = Utils.getTagDisplayName(t);
                if (seenOrgNames.has(label)) continue;  // collapse duplicate venue website rows
                seenOrgNames.add(label);
                organizerTags.push(t);
                if (organizerTags.length >= ORGANIZER_CHIP_CAP) break;
            }
        }

        if (curatedTags.length > 0 || organizerTags.length > 0) {
            const tagsContainer = document.createElement('div');
            tagsContainer.className = 'tag-tags-container popup-tags-container';

            curatedTags.forEach(tag => {
                const el = createTagElement(tag);
                if (el) tagsContainer.appendChild(el);
            });
            organizerTags.forEach(t => {
                const orgEl = state.createInteractiveTagButton(t);
                if (orgEl) tagsContainer.appendChild(orgEl);
            });

            if (tagsContainer.children.length > 0) {
                eventDetailContainer.appendChild(tagsContainer);
            }
        }

        return eventDetailContainer;
    }

    // ========================================
    // EVENT DATETIME
    // ========================================

    function createEventDatetimeElement(event) {
        const span = document.createElement('span');
        span.className = 'popup-event-card-datetime';

        const { matchingText, otherText, otherCount } = Utils.buildEventDateTime(event);

        const matchingSpan = document.createElement('span');
        matchingSpan.className = 'datetime-matching';
        matchingSpan.textContent = matchingText;
        span.appendChild(matchingSpan);

        if (otherCount === 0) return span;

        if (otherCount <= INLINE_OTHER_DATES_THRESHOLD) {
            const otherSpan = document.createElement('span');
            otherSpan.className = 'datetime-other';
            otherSpan.textContent = matchingText ? `; ${otherText}` : otherText;
            span.appendChild(otherSpan);
            return span;
        }

        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'datetime-toggle';
        toggle.textContent = `+${otherCount} other date${otherCount === 1 ? '' : 's'}`;

        const otherSpan = document.createElement('span');
        otherSpan.className = 'datetime-other';
        otherSpan.hidden = true;
        otherSpan.textContent = matchingText ? `; ${otherText}` : otherText;

        toggle.addEventListener('click', (e) => {
            e.stopPropagation();
            otherSpan.hidden = false;
            toggle.hidden = true;
        });

        span.appendChild(toggle);
        span.appendChild(otherSpan);
        return span;
    }

    // ========================================
    // EVENTS LIST
    // ========================================

    /**
     * Comparator for popup section names: "Events" first, then "Ongoing",
     * then any custom section alphabetically.
     */
    function compareSections(a, b) {
        const orderA = SECTION_ORDER[a] ?? 2;
        const orderB = SECTION_ORDER[b] ?? 2;
        return orderA !== orderB ? orderA - orderB : a.localeCompare(b);
    }

    /**
     * Sorts events at a single location using the same priority order the
     * popup UI shows: tag-matching events first, then by number of matching
     * selected tags, then by date proximity to the reference date. A forced
     * event (typically from a search hit) is pinned to the top.
     *
     * @returns {{ sortedEvents: Array, forcedEvent: Object|null }} Each item
     *   in sortedEvents is { event, isMatchingTags, selectedTagMatchCount,
     *   startTime, distanceFromReference }.
     */
    function sortEventsForLocation(eventsAtLocation, ctx) {
        const { activeFilters, filterFunctions, selectedStartDate = null, forceDisplayEventId = null } = ctx;

        // Tag-state Sets can be expensive to derive when called per-location in a
        // tight loop (e.g. MarkerController's label computation). Callers may
        // precompute and pass them in via ctx.tagSets.
        const { selectedTagsSet, requiredTagsSet, forbiddenTagsSet } =
            ctx.tagSets || Utils.partitionTagStates(activeFilters.tagStates);
        const hasActiveTagFilters = selectedTagsSet.size > 0;

        // No pre-ordering (or array copy) needed for the forced event: sort is
        // stable, and the post-sort pin below moves it to the front anyway.
        const forcedEvent = forceDisplayEventId
            ? (eventsAtLocation.find(e => e.id === forceDisplayEventId) || null)
            : null;

        const referenceDate = selectedStartDate
            ? selectedStartDate.getTime()
            : (activeFilters.sliderStartDate ? activeFilters.sliderStartDate.getTime() : 0);

        const sortedEvents = eventsAtLocation.map(event => {
            const locInfo = event.locationKey ? filterFunctions.getLocationInfo(event.locationKey) : null;
            const combinedTags = event.tags || [];
            const locationTags = locInfo?.tags || [];
            // Organizers participate as pseudo-tags, so a selected/required/
            // forbidden organizer must count toward this event's match — otherwise
            // organizer-selected events wouldn't auto-expand or sort to the top.
            // A merged event can have several organizers.
            const orgTags = Utils.organizerTagsForEvent(event);

            // selectedTagsSet here also contains required tags (it feeds
            // selectedTagMatchCount below), but the predicate's selected tier
            // only runs when requiredTagsSet is empty — where the two
            // conventions coincide — so the boolean is unaffected.
            const isMatchingTags = Utils.matchesTagSets(
                combinedTags, locationTags, orgTags,
                selectedTagsSet, requiredTagsSet, forbiddenTagsSet
            );

            let selectedTagMatchCount = 0;
            if (hasActiveTagFilters && isMatchingTags) {
                for (const tag of combinedTags) if (selectedTagsSet.has(tag)) selectedTagMatchCount++;
                for (const tag of locationTags) if (selectedTagsSet.has(tag)) selectedTagMatchCount++;
                for (const tag of orgTags) if (selectedTagsSet.has(tag)) selectedTagMatchCount++;
            }

            const startTime = event.occurrences?.[0]?.start?.getTime() || 0;
            const endTime = event.occurrences?.[0]?.end?.getTime() || startTime;
            const isOngoingOnReferenceDate = startTime <= referenceDate && endTime >= referenceDate;
            let distanceFromReference = Math.abs(startTime - referenceDate);
            if (isOngoingOnReferenceDate) {
                distanceFromReference = Math.max(0, distanceFromReference - Constants.TIME.FIVE_DAYS_MS);
            }

            return { event, isMatchingTags, selectedTagMatchCount, startTime, distanceFromReference };
        });

        sortedEvents.sort((a, b) => {
            if (a.isMatchingTags !== b.isMatchingTags) return b.isMatchingTags - a.isMatchingTags;
            if (a.selectedTagMatchCount !== b.selectedTagMatchCount) return b.selectedTagMatchCount - a.selectedTagMatchCount;
            return a.distanceFromReference - b.distanceFromReference;
        });

        if (forcedEvent) {
            const idx = sortedEvents.findIndex(d => d.event.id === forcedEvent.id);
            if (idx > 0) {
                const [forcedData] = sortedEvents.splice(idx, 1);
                sortedEvents.unshift(forcedData);
            }
        }

        return { sortedEvents, forcedEvent };
    }

    /**
     * Builds a single `.popup-event-card` with header (emoji + name) and a
     * description preview. When `interactive` (default), it also gets the
     * datetime line and a lazily-rendered detail section toggled on click —
     * this is the location popup's behavior.
     *
     * The desktop list view passes `interactive: false` to get a permanently
     * collapsed, non-expanding card (it wires its own hover/click handlers).
     *
     * @param {Object} event
     * @param {Object} [opts]
     * @param {boolean} [opts.shouldOpen]   Render detail eagerly and start expanded (interactive only)
     * @param {boolean} [opts.interactive]  Add datetime + expand/collapse on click (default true)
     */
    function createEventCard(event, { shouldOpen = false, interactive = true } = {}) {
        const card = document.createElement('div');
        card.className = 'popup-event-card';

        // Title color comes from the event's own emoji (falls back to the
        // container's location accent when the event has no emoji).
        applyEventAccentVars(card, event);

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

        if (interactive) {
            card.appendChild(createEventDatetimeElement(event));
        }

        // Description preview (always visible when collapsed)
        if (event.description) {
            const preview = document.createElement('div');
            preview.className = 'popup-event-card-preview';
            preview.textContent = event.description;
            card.appendChild(preview);
        }

        // Non-interactive cards (list view) stay permanently collapsed.
        if (!interactive) {
            return card;
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

        return card;
    }

    function createEventsList(eventsAtLocation, activeFilters, filterFunctions, forceDisplayEventId = null, selectedStartDate = null) {
        const eventsListWrapper = document.createElement('div');
        eventsListWrapper.className = 'popup-events-list';

        if (eventsAtLocation.length === 0 && !forceDisplayEventId) {
            const noEventsP = document.createElement('p');
            noEventsP.textContent = "No events at this location in the selected date range.";
            eventsListWrapper.appendChild(noEventsP);
            return eventsListWrapper;
        }

        let hasActiveTagFilters = false;
        let hasForbiddenTags = false;
        for (const tag in activeFilters.tagStates) {
            const st = activeFilters.tagStates[tag];
            if (st === 'selected' || st === 'required') hasActiveTagFilters = true;
            else if (st === 'forbidden') hasForbiddenTags = true;
        }
        const hasAnyTagFilter = hasActiveTagFilters || hasForbiddenTags;

        const { sortedEvents: eventsWithSortData, forcedEvent } = sortEventsForLocation(
            eventsAtLocation,
            { activeFilters, filterFunctions, selectedStartDate, forceDisplayEventId }
        );

        const expandAll = !hasAnyTagFilter && eventsWithSortData.length > 0 && eventsWithSortData.length < 4;
        let isFirstEvent = true;

        eventsWithSortData.forEach(({ event, isMatchingTags }) => {
            let shouldOpen = false;
            if (forcedEvent) {
                shouldOpen = (event.id === forcedEvent.id);
            } else if (hasAnyTagFilter) {
                shouldOpen = isMatchingTags;
            } else {
                shouldOpen = expandAll || isFirstEvent;
            }

            eventsListWrapper.appendChild(createEventCard(event, { shouldOpen }));
            isFirstEvent = false;
        });

        return eventsListWrapper;
    }

    // ========================================
    // MAIN BUILDER
    // ========================================

    function createLocationPopupContent(locationInfo, eventsAtLocation, activeFilters, geotagsSet, filterFunctions, forceDisplayEventId = null, selectedStartDate = null, previousActiveTab = null) {
        const popupContainer = document.createElement('div');
        popupContainer.className = 'maplibre-popup-content';

        applyAccentVars(popupContainer, locationInfo);

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
        const sectionNames = [...sectionMap.keys()].sort(compareSections);

        // Info tab shown if there are tags, description, address, or website
        const hasInfo = locationInfo && (displayTags.length > 0 || locationInfo.description || locationInfo.address || locationInfo.website_url || (locationInfo.website_urls && locationInfo.website_urls.length > 0));

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
        } else if (previousActiveTab) {
            const idx = tabNames.indexOf(previousActiveTab);
            if (idx >= 0) defaultTab = idx;
        } else {
            // If filters are active and the default section ("Events") has no
            // matching events but another section does, open to that section
            // instead — otherwise the user lands on a tab full of dimmed,
            // non-matching events.
            const { defaultSection: preferredSection } = getDefaultSectionAndEvents(eventsAtLocation, {
                activeFilters,
                filterFunctions,
                selectedStartDate
            });
            const idx = sectionNames.indexOf(preferredSection);
            if (idx >= 0) defaultTab = idx;
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
                sectionEvents, activeFilters, filterFunctions,
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

        // Lock explicit pixel heights on track/panels after layout, and switch to
        // default tab once viewport has dimensions (offsetWidth is 0 before DOM insertion).
        requestAnimationFrame(() => {
            if (defaultTab > 0) {
                tabs.switchToTab(defaultTab);
            }
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
        state.getDebugMode = config.getDebugMode || (() => false);
    }

    /**
     * Computes the popup's default section ("Events" first, then "Ongoing", then
     * custom alphabetical — preferring the first section with a tag-matching
     * event when ctx has filter state) plus that section's events, in one
     * sortEventsForLocation pass. Used by MarkerController to compute marker
     * label events and by createLocationPopupContent to pick the default tab.
     * Returns { defaultSection, sectionEvents } where sectionEvents is the array
     * of events (not sortData) in popup display order.
     */
    function getDefaultSectionAndEvents(events, ctx) {
        const { sortedEvents } = sortEventsForLocation(events, ctx);

        const sectionsSet = new Set();
        for (const e of events) sectionsSet.add(e.section || 'Events');
        const orderedSections = [...sectionsSet].sort(compareSections);

        let defaultSection = orderedSections[0] || 'Events';
        if (ctx && ctx.activeFilters) {
            const matchingSections = new Set();
            for (const d of sortedEvents) {
                if (d.isMatchingTags) matchingSections.add(d.event.section || 'Events');
            }
            for (const s of orderedSections) {
                if (matchingSections.has(s)) { defaultSection = s; break; }
            }
        }

        const sectionEvents = [];
        for (const d of sortedEvents) {
            if ((d.event.section || 'Events') === defaultSection) {
                sectionEvents.push(d.event);
            }
        }
        return { defaultSection, sectionEvents };
    }

    return {
        init,
        createLocationPopupContent,
        createEventCard,
        getDefaultSectionAndEvents
    };
})();
