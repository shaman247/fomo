const TagFilterUI = (() => {
    const TAG_STATE = {
        UNSELECTED: 'unselected',
        SELECTED: 'selected',
        REQUIRED: 'required',
        FORBIDDEN: 'forbidden'
    };

    const SECTION_VIEW_STATE = {
        COLLAPSED: 'collapsed',   // Show limited results based on thresholds
        DEFAULT: 'default',       // Hide isVisible=false items
        EXPANDED: 'expanded'      // Show all items including isVisible=false
    };

    // Target number of lines when collapsed
    const TARGET_COLLAPSED_LINES = {
        small: 2,  // Mobile/small windows
        large: 5   // Desktop/large windows
    };

    // Function to determine if window is small (mobile-like)
    function isSmallWindow() {
        return window.innerWidth < 768; // Standard mobile breakpoint
    }

    // Calculate how many items fit in target number of lines
    // This is called during rendering with actual DOM elements
    function calculateCollapseThreshold(sectionWrapper, items) {
        if (items.length === 0) return 3; // Fallback

        const targetLines = isSmallWindow() ? TARGET_COLLAPSED_LINES.small : TARGET_COLLAPSED_LINES.large;

        // Temporarily add items to measure their height
        const tempContainer = document.createElement('div');
        tempContainer.style.cssText = 'position: absolute; visibility: hidden; width: ' + sectionWrapper.offsetWidth + 'px;';
        tempContainer.className = sectionWrapper.className;

        document.body.appendChild(tempContainer);

        // Clone and add the icon button (it takes up horizontal space in the flexbox)
        const iconButton = sectionWrapper.querySelector('.section-icon-button');
        if (iconButton) {
            const tempIconButton = iconButton.cloneNode(true);
            tempContainer.appendChild(tempIconButton);
        }

        let count = 0;
        const lineHeight = 32; // Approximate line height for tag buttons with padding/margin
        const maxHeight = lineHeight * targetLines;

        // Create a temporary show more button to account for its space
        const tempShowMoreButton = document.createElement('button');
        tempShowMoreButton.className = 'tag-button state-cycle-button';
        tempShowMoreButton.textContent = '+';

        // Add items one by one until we exceed the target height
        for (let i = 0; i < items.length; i++) {
            const testElement = items[i].cloneNode(true);
            tempContainer.appendChild(testElement);

            // Add the show more button to simulate the actual layout with the button
            tempContainer.appendChild(tempShowMoreButton);

            const heightWithButton = tempContainer.offsetHeight;

            // Remove the button for the next iteration
            tempContainer.removeChild(tempShowMoreButton);

            // Check if adding this item plus the button would exceed our target
            if (heightWithButton > maxHeight && count > 0) {
                // Remove the last item we just added since it causes overflow
                tempContainer.removeChild(testElement);
                break;
            }

            currentHeight = heightWithButton;
            count++;
        }

        document.body.removeChild(tempContainer);

        // Return at least 1, and cap at items.length
        return Math.max(1, Math.min(count, items.length));
    }

    // Get initial collapse threshold estimate (used before rendering)
    function getEstimatedCollapseThreshold(sectionKey) {
        // Rough estimates based on typical item sizes
        const targetLines = isSmallWindow() ? TARGET_COLLAPSED_LINES.small : TARGET_COLLAPSED_LINES.large;

        // Estimate items per line based on section type
        const estimatedItemsPerLine = {
            locations: isSmallWindow() ? 1.5 : 3,  // Locations tend to be longer
            events: isSmallWindow() ? 1.2 : 2.5,   // Events can be long
            tags: isSmallWindow() ? 2.5 : 5        // Tags are typically shorter
        };

        const itemsPerLine = estimatedItemsPerLine[sectionKey] || 2;
        return Math.max(1, Math.floor(targetLines * itemsPerLine));
    }

    const state = {
        allAvailableTags: [],
        tagConfigBgColors: [],
        resultsContainerDOM: null,
        onFilterChangeCallback: null,
        defaultMarkerColor: null,
        initialGlobalFrequencies: {},
        currentDynamicFrequencies: {},
        tagStates: {},
        tagPositions: new Map(),
        searchInputDOM: null,
        searchTerm: '',
        onSearchResultClick: null,
        getTagColor: null,
        assignColorToTag: null,
        unassignColorFromTag: null,
        sectionOrder: ['locations', 'events', 'tags'], // Track section display order
        sectionViewStates: { // Track view state for each section
            locations: SECTION_VIEW_STATE.DEFAULT,
            events: SECTION_VIEW_STATE.DEFAULT,
            tags: SECTION_VIEW_STATE.DEFAULT
        },
        lastSearchResults: [], // Cache last search results for re-rendering
        lastSearchTerm: ''
    };
    const providers = {
        getSelectedLocationKey: () => null,
    };
    let performSearchCallback = () => {};

    // Helper function to re-render while keeping a reference element in the same visual position
    // Takes the element to track (button or section wrapper) as a reference point
    function reRenderWithElementPositionPreserved(referenceElement) {
        if (!state.resultsContainerDOM || !referenceElement) return;

        // Get the section key to find the corresponding element after re-render
        const sectionWrapper = referenceElement.closest('[data-section-key]');
        const sectionKey = sectionWrapper?.dataset.sectionKey;
        if (!sectionKey) return;

        // Determine what type of element to track
        let isSection = referenceElement.classList.contains('search-results-section');
        let buttonClass = null;
        if (!isSection) {
            if (referenceElement.classList.contains('section-icon-button')) {
                buttonClass = 'section-icon-button';
            } else if (referenceElement.classList.contains('show-more-button')) {
                buttonClass = 'show-more-button';
            } else if (referenceElement.classList.contains('show-fewer-button')) {
                buttonClass = 'show-fewer-button';
            }
        }

        // Save the current scroll position and viewport position of element
        const scrollTopBefore = state.resultsContainerDOM.scrollTop;
        const containerRect = state.resultsContainerDOM.getBoundingClientRect();
        const elementRect = referenceElement.getBoundingClientRect();
        const elementOffsetFromContainerTop = elementRect.top - containerRect.top;

        // Re-render with cached results (this will reset scrollTop to 0)
        renderFilters(state.lastSearchResults, state.lastSearchTerm);

        // Find the corresponding element in the newly rendered DOM
        let newElement;
        if (isSection) {
            newElement = state.resultsContainerDOM.querySelector(
                `[data-section-key="${sectionKey}"]`
            );
        } else if (buttonClass) {
            newElement = state.resultsContainerDOM.querySelector(
                `[data-section-key="${sectionKey}"] .${buttonClass}`
            );
        }

        if (newElement) {
            // Calculate where we need to scroll to keep the element in the same position
            // Element's position in the container (relative to container's scrollable content)
            const newElementRect = newElement.getBoundingClientRect();
            const newContainerRect = state.resultsContainerDOM.getBoundingClientRect();
            const newElementOffsetFromContainerTop = newElementRect.top - newContainerRect.top;

            // Adjust scroll so the element appears at the same offset from container top
            state.resultsContainerDOM.scrollTop = newElementOffsetFromContainerTop - elementOffsetFromContainerTop;
        }
    }

    function init(config) {
        Object.assign(state, config);
        state.initialGlobalFrequencies = { ...config.initialGlobalFrequencies };
        state.currentDynamicFrequencies = { ...config.initialGlobalFrequencies };
        if (config.getSearchTerm) {
            state.getSearchTerm = config.getSearchTerm;
        }

        state.allAvailableTags.forEach(tag => {
            state.tagStates[tag] = TAG_STATE.UNSELECTED;
        });

        if (!state.resultsContainerDOM) {
            console.error("tagFilterUI: resultsContainerDOM is not provided.");
            return;
        }

        performSearchCallback = config.performSearch || performSearchCallback;
        state.searchInputDOM = document.getElementById('omni-search-input');
        if (state.searchInputDOM) {
            // The main App controller in script.js will handle the input events
            // and call TagFilterUI.render() with the results.
            state.searchInputDOM.addEventListener('keydown', handleSearchKeydown);
        }

        // Initialize swipe gestures for section reordering
        initSwipeGestures();
    }

    function setAppProviders(appProviders) {
        Object.assign(providers, appProviders);
    }

    function handleSearchKeydown(e) {
        if (e.key === 'Escape') {
            clearSearch(state.searchInputDOM.value);
        }
    }

    function clearSearch(currentTerm) {
        if (state.searchInputDOM) {
            state.searchInputDOM.value = '';
        }
        state.searchTerm = currentTerm || '';
        // Re-render with no search term and no search results,
        // which will cause it to display the normal tag cloud.
        renderFilters([]);
        state.searchInputDOM.blur();
    }

    function updateTagVisuals(buttonElement, tagValue) {
        const tagState = state.tagStates[tagValue];
        const tagColor = state.getTagColor ? state.getTagColor(tagValue) : null;
        const colorToUse = tagColor || state.defaultMarkerColor;

        buttonElement.className = 'tag-button';

        switch (tagState) {
            case TAG_STATE.SELECTED:
                buttonElement.classList.add('state-selected');
                buttonElement.setAttribute('aria-pressed', 'true');
                buttonElement.setAttribute('aria-label', `${tagValue}, selected tag filter`);
                if (Array.isArray(colorToUse)) {
                    buttonElement.style.background = `linear-gradient(to bottom, color-mix(in srgb, ${colorToUse[0]} 80%, transparent), color-mix(in srgb, ${colorToUse[1]} 80%, transparent))`;
                } else {
                    buttonElement.style.backgroundColor = `color-mix(in srgb, ${colorToUse} 80%, transparent)`;
                }
                break;
            case TAG_STATE.REQUIRED:
                buttonElement.classList.add('state-required');
                buttonElement.setAttribute('aria-pressed', 'true');
                buttonElement.setAttribute('aria-label', `${tagValue}, required tag filter`);
                if (Array.isArray(colorToUse)) {
                    buttonElement.style.background = `linear-gradient(to bottom, color-mix(in srgb, ${colorToUse[0]} 80%, transparent), color-mix(in srgb, ${colorToUse[1]} 80%, transparent))`;
                } else {
                    buttonElement.style.backgroundColor = `color-mix(in srgb, ${colorToUse} 80%, transparent)`;
                }
                break;
            case TAG_STATE.FORBIDDEN:
                buttonElement.classList.add('state-forbidden');
                buttonElement.setAttribute('aria-pressed', 'mixed');
                buttonElement.setAttribute('aria-label', `${tagValue}, forbidden tag filter`);
                break;
            case TAG_STATE.UNSELECTED:
            default:
                buttonElement.classList.add('state-unselected');
                buttonElement.setAttribute('aria-pressed', 'false');
                buttonElement.setAttribute('aria-label', `${tagValue}, unselected tag filter`);
                break;
        }
        buttonElement.textContent = tagValue;
    }

    function getRightClickNextState(currentState) {
        switch (currentState) {
            case TAG_STATE.UNSELECTED:
                return TAG_STATE.SELECTED;
            case TAG_STATE.SELECTED:
                return TAG_STATE.REQUIRED;
            case TAG_STATE.REQUIRED:
                return TAG_STATE.FORBIDDEN;
            case TAG_STATE.FORBIDDEN:
            default:
                return TAG_STATE.UNSELECTED;
        }
    }

    function getNextState(currentState) {
        switch (currentState) {
            case TAG_STATE.SELECTED:
            case TAG_STATE.REQUIRED:
            case TAG_STATE.FORBIDDEN:
                return TAG_STATE.UNSELECTED;
            case TAG_STATE.UNSELECTED:
                return TAG_STATE.SELECTED;
            default:
                return TAG_STATE.SELECTED;
        }
    }

    function createTagElement(tag) {
        const button = document.createElement('button');
        button.dataset.tag = tag;

        updateTagVisuals(button, tag);

        button.addEventListener('click', (e) => {
            const oldState = state.tagStates[tag];
            state.tagStates[tag] = getNextState(state.tagStates[tag]);
            const newState = state.tagStates[tag];

            // Assign or unassign color based on state change
            if (oldState === TAG_STATE.UNSELECTED && (newState === TAG_STATE.SELECTED || newState === TAG_STATE.REQUIRED)) {
                if (state.assignColorToTag) {
                    state.assignColorToTag(tag);
                }
            } else if ((oldState === TAG_STATE.SELECTED || oldState === TAG_STATE.REQUIRED) && newState === TAG_STATE.UNSELECTED) {
                if (state.unassignColorFromTag) {
                    state.unassignColorFromTag(tag);
                }
            }

            // Always update visuals after state change
            updateTagVisuals(button, tag);

            if (state.onFilterChangeCallback) {
                state.onFilterChangeCallback();
            }
        });

        button.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            const oldState = state.tagStates[tag];
            state.tagStates[tag] = getRightClickNextState(state.tagStates[tag]);
            const newState = state.tagStates[tag];

            // Assign or unassign color based on state change
            if (oldState === TAG_STATE.UNSELECTED && (newState === TAG_STATE.SELECTED || newState === TAG_STATE.REQUIRED)) {
                if (state.assignColorToTag) {
                    state.assignColorToTag(tag);
                }
            } else if ((oldState === TAG_STATE.SELECTED || oldState === TAG_STATE.REQUIRED || oldState === TAG_STATE.FORBIDDEN) && newState === TAG_STATE.UNSELECTED) {
                if (state.unassignColorFromTag) {
                    state.unassignColorFromTag(tag);
                }
            }

            // Always update visuals after state change
            updateTagVisuals(button, tag);

            if (state.onFilterChangeCallback) {
                state.onFilterChangeCallback();
            }
        });
        return button;
    }

    function createInteractiveTagButton(tag) {
        const button = document.createElement('button');
        button.dataset.tag = tag;

        updateTagVisuals(button, tag);

        button.addEventListener('click', (e) => {
            e.stopPropagation();
            const oldState = state.tagStates[tag];
            state.tagStates[tag] = getNextState(state.tagStates[tag]);
            const newState = state.tagStates[tag];

            // Assign or unassign color based on state change
            if (oldState === TAG_STATE.UNSELECTED && (newState === TAG_STATE.SELECTED || newState === TAG_STATE.REQUIRED)) {
                if (state.assignColorToTag) {
                    state.assignColorToTag(tag);
                }
            } else if ((oldState === TAG_STATE.SELECTED || oldState === TAG_STATE.REQUIRED) && newState === TAG_STATE.UNSELECTED) {
                if (state.unassignColorFromTag) {
                    state.unassignColorFromTag(tag);
                }
            }

            updateTagVisuals(button, tag);
            // When a tag is clicked in the search results, we need to re-run the filter logic
            // and then re-run the search to update the displayed results.
            state.onFilterChangeCallback();
        });

        button.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const oldState = state.tagStates[tag];
            state.tagStates[tag] = getRightClickNextState(state.tagStates[tag]);
            const newState = state.tagStates[tag];

            // Assign or unassign color based on state change
            if (oldState === TAG_STATE.UNSELECTED && (newState === TAG_STATE.SELECTED || newState === TAG_STATE.REQUIRED)) {
                if (state.assignColorToTag) {
                    state.assignColorToTag(tag);
                }
            } else if ((oldState === TAG_STATE.SELECTED || oldState === TAG_STATE.REQUIRED || oldState === TAG_STATE.FORBIDDEN) && newState === TAG_STATE.UNSELECTED) {
                if (state.unassignColorFromTag) {
                    state.unassignColorFromTag(tag);
                }
            }

            updateTagVisuals(button, tag);
            state.onFilterChangeCallback();
        });

        return button;
    }

    function createSearchResultButton(result) {
        if (result.type === 'tag') {
            // For tags, create the interactive button and apply non-visible styling if needed
            const button = createInteractiveTagButton(result.ref);
            if (result.isVisible === false) {
                button.classList.add('non-visible-tag');
            }
            return button;
        }

        const button = document.createElement('button');
        button.className = 'tag-button state-unselected';

        // Add non-visible class based on result type if not visible
        if (result.isVisible === false) {
            if (result.type === 'location') {
                button.classList.add('non-visible-location');
            } else if (result.type === 'event') {
                button.classList.add('non-visible-event');
            }
        }

        button.dataset.resultType = result.type;
        button.dataset.resultRef = result.ref;
        button.setAttribute('role', 'listitem');
        const emoji = result.emoji ? `<span class="popup-event-emoji" aria-hidden="true">${result.emoji}</span>` : '';
        const displayName = result.displayName || result.ref;
        button.innerHTML = `${emoji} ${displayName.replace(/<\/?strong>/g, '')}`;
        button.setAttribute('aria-label', `${result.type}: ${displayName.replace(/<\/?[^>]+(>|$)/g, '')}`);

        button.addEventListener('click', (e) => {
            if (state.onSearchResultClick && result.type) {
                state.onSearchResultClick(result);
            }
        });
        return button;
    }

    function initSwipeGestures() {
        if (!state.resultsContainerDOM) return;

        let startX = 0;
        let startY = 0;
        let isDragging = false;
        let isHorizontalSwipe = false;
        let hasTriggeredReorder = false;
        let targetSectionKey = null;
        let targetHeader = null;
        let targetContainer = null;

        const handleStart = (x, y, target) => {
            // Find which section was touched/clicked
            const container = target.closest('.search-results-section');

            if (container) {
                targetContainer = container;
                targetSectionKey = container.dataset.sectionKey;
                targetHeader = container.querySelector('.result-group-title');
            } else {
                // Not on a section, ignore
                return;
            }

            startX = x;
            startY = y;
            isDragging = true;
            isHorizontalSwipe = false;
            hasTriggeredReorder = false;
        };

        const handleMove = (x, y) => {
            if (!isDragging || !targetSectionKey) return;

            const deltaX = x - startX;
            const deltaY = y - startY;

            // Determine if this is a horizontal swipe (once determined, stick with it)
            if (!isHorizontalSwipe && (Math.abs(deltaX) > 10 || Math.abs(deltaY) > 10)) {
                isHorizontalSwipe = Math.abs(deltaX) > Math.abs(deltaY);

                // If we started on a button and movement is horizontal, prevent the click
                if (isHorizontalSwipe && targetHeader && targetHeader.querySelector('.tag-button')) {
                    // Prevent click on buttons when swiping
                    const buttons = targetContainer ? targetContainer.querySelectorAll('.tag-button') : [];
                    buttons.forEach(btn => {
                        btn.style.pointerEvents = 'none';
                    });
                }
            }

            // Apply visual feedback for horizontal swipes
            if (isHorizontalSwipe) {
                const maxDisplacement = 100;
                const displacement = Math.max(-maxDisplacement, Math.min(maxDisplacement, deltaX));
                const opacity = 1 - (Math.abs(displacement) / maxDisplacement) * 0.5;

                if (targetContainer) {
                    targetContainer.style.transition = 'none';
                    targetContainer.style.transform = `translateX(${displacement}px)`;
                    targetContainer.style.opacity = opacity;
                }

                // Trigger reorder when threshold is reached
                if (!hasTriggeredReorder && Math.abs(deltaX) > 50) {
                    hasTriggeredReorder = true;

                    // Capture elements before reordering
                    const oldContainer = targetContainer;
                    const dismissedIndex = state.sectionOrder.indexOf(targetSectionKey);

                    // Move the swiped section to the bottom
                    state.sectionOrder.splice(dismissedIndex, 1);
                    state.sectionOrder.push(targetSectionKey);

                    // Reset drag state
                    isDragging = false;
                    isHorizontalSwipe = false;

                    // Animate out the swiped section
                    const slideDistance = 30;
                    const slideOutX = deltaX > 0 ? slideDistance : -slideDistance;

                    if (oldContainer) {
                        oldContainer.style.transition = 'transform 0.15s ease-out, opacity 0.15s ease-out';
                        oldContainer.style.transform = `translateX(${slideOutX}px)`;
                        oldContainer.style.opacity = '0';
                    }

                    // Re-render after animation
                    performSearchCallback(state.searchTerm);
                }
            }
        };

        const handleEnd = (x, y) => {
            if (!isDragging) return;

            // Reset visual feedback if reorder wasn't triggered
            if (!hasTriggeredReorder && isHorizontalSwipe) {
                if (targetContainer) {
                    targetContainer.style.transition = 'transform 0.3s ease, opacity 0.3s ease';
                    targetContainer.style.transform = 'translateX(0)';
                    targetContainer.style.opacity = '1';
                }
            }

            // Re-enable pointer events on buttons
            if (targetContainer) {
                const buttons = targetContainer.querySelectorAll('.tag-button');
                buttons.forEach(btn => {
                    btn.style.pointerEvents = '';
                });
            }

            isDragging = false;
            isHorizontalSwipe = false;
            hasTriggeredReorder = false;
            targetSectionKey = null;
            targetHeader = null;
            targetContainer = null;
        };

        // Touch events
        state.resultsContainerDOM.addEventListener('touchstart', (e) => {
            const touch = e.touches[0];
            handleStart(touch.clientX, touch.clientY, e.target);
        }, { passive: true });

        state.resultsContainerDOM.addEventListener('touchmove', (e) => {
            if (e.touches.length > 0) {
                const touch = e.touches[0];
                handleMove(touch.clientX, touch.clientY);
            }
        }, { passive: true });

        state.resultsContainerDOM.addEventListener('touchend', (e) => {
            if (e.changedTouches.length > 0) {
                const touch = e.changedTouches[0];
                handleEnd(touch.clientX, touch.clientY);
            }
        }, { passive: true });

        // Mouse events
        state.resultsContainerDOM.addEventListener('mousedown', (e) => {
            handleStart(e.clientX, e.clientY, e.target);
        });

        state.resultsContainerDOM.addEventListener('mousemove', (e) => {
            handleMove(e.clientX, e.clientY);
        });

        state.resultsContainerDOM.addEventListener('mouseup', (e) => {
            handleEnd(e.clientX, e.clientY);
        });

        state.resultsContainerDOM.addEventListener('mouseleave', () => {
            if (isDragging && isHorizontalSwipe) {
                if (targetContainer) {
                    targetContainer.style.transition = 'transform 0.3s ease, opacity 0.3s ease';
                    targetContainer.style.transform = 'translateX(0)';
                    targetContainer.style.opacity = '1';

                    // Re-enable pointer events on buttons
                    const buttons = targetContainer.querySelectorAll('.tag-button');
                    buttons.forEach(btn => {
                        btn.style.pointerEvents = '';
                    });
                }

                isDragging = false;
                isHorizontalSwipe = false;
            }
        });
    }

    function renderFilters(searchResults = [], searchTerm = '') {
        state.searchTerm = searchTerm;

        // Cache the search results for re-rendering
        state.lastSearchResults = searchResults;
        state.lastSearchTerm = searchTerm;

        if (!state.resultsContainerDOM) return;

        // Clear the single results container
        state.resultsContainerDOM.innerHTML = '';
        state.resultsContainerDOM.scrollTop = 0;

        if (searchResults) {
            // If searching, group results and display them in sections.
            const groupedResults = {
                locations: [],
                events: [],
                tags: []
            };

            // Track hidden items separately for each section
            const hiddenResults = {
                locations: [],
                events: [],
                tags: []
            };

            // Filter results: only show isVisible=false items if there's a non-empty search term or toggle is on
            const hasSearchTerm = searchTerm && searchTerm.trim().length > 0;

            searchResults.forEach(result => {
                const type = result.type;

                // Separate visible and hidden items
                if (result.isVisible === false && !hasSearchTerm) {
                    // Hidden items go to separate array
                    if (type === 'location') hiddenResults.locations.push(result);
                    else if (type === 'event') hiddenResults.events.push(result);
                    else if (type === 'tag') hiddenResults.tags.push(result);
                } else {
                    // Visible items go to main array
                    if (type === 'location') groupedResults.locations.push(result);
                    else if (type === 'event') groupedResults.events.push(result);
                    else if (type === 'tag') groupedResults.tags.push(result);
                }
            });

            // Sort locations, prioritizing the selected one, then by score
            const selectedLocationKey = providers.getSelectedLocationKey();
            groupedResults.locations.sort((a, b) => {
                const isASelected = a.ref === selectedLocationKey;
                const isBSelected = b.ref === selectedLocationKey;
                if (isASelected !== isBSelected) return isASelected ? -1 : 1;
                return (b.score || 0) - (a.score || 0);
            });
            hiddenResults.locations.sort((a, b) => (b.score || 0) - (a.score || 0));

            groupedResults.events.sort((a, b) => (b.score || 0) - (a.score || 0));
            hiddenResults.events.sort((a, b) => (b.score || 0) - (a.score || 0));

            // Filter out selected/required/forbidden tags from search results, then sort
            groupedResults.tags = groupedResults.tags.filter(result => {
                const tagState = state.tagStates[result.ref] || TAG_STATE.UNSELECTED;
                return tagState === TAG_STATE.UNSELECTED;
            });
            hiddenResults.tags = hiddenResults.tags.filter(result => {
                const tagState = state.tagStates[result.ref] || TAG_STATE.UNSELECTED;
                return tagState === TAG_STATE.UNSELECTED;
            });

            groupedResults.tags.sort((a, b) => (b.score || 0) - (a.score || 0));
            hiddenResults.tags.sort((a, b) => (b.score || 0) - (a.score || 0));

            const renderSection = (results, hiddenItems, sectionTitle, sectionIcon, sectionKey) => {
                const hasHiddenItems = hiddenItems && hiddenItems.length > 0;
                const viewState = state.sectionViewStates[sectionKey];

                // Start with estimated threshold
                let collapseThreshold = getEstimatedCollapseThreshold(sectionKey);

                // Skip section if there are no visible results and no hidden items
                if (results.length === 0 && !hasHiddenItems) return;

                // Create wrapper for section (contains results inline)
                const sectionWrapper = document.createElement('div');
                sectionWrapper.className = 'search-results-section';
                sectionWrapper.dataset.sectionKey = sectionKey;

                // Add toggle button at the beginning (always shown)
                const toggleButton = document.createElement('button');
                toggleButton.className = 'tag-button state-unselected toggle-hidden-button section-icon-button';

                // Add state indicator symbol (same for all sections)
                const stateSymbol = (viewState === SECTION_VIEW_STATE.COLLAPSED) ? '▶' : '▼';

                toggleButton.innerHTML = `${sectionIcon}<span class="state-indicator">${stateSymbol}</span>`;

                // Set simple aria-label and title
                toggleButton.setAttribute('aria-label', sectionTitle);
                toggleButton.setAttribute('title', sectionTitle);

                // Add visual indicator class for state
                toggleButton.classList.add(`view-state-${viewState}`);

                toggleButton.addEventListener('click', (e) => {
                    e.stopPropagation();

                    // Toggle between DEFAULT and COLLAPSED
                    const currentState = state.sectionViewStates[sectionKey];
                    if (currentState === SECTION_VIEW_STATE.COLLAPSED) {
                        state.sectionViewStates[sectionKey] = SECTION_VIEW_STATE.DEFAULT;
                    } else { // DEFAULT or EXPANDED -> go to COLLAPSED
                        state.sectionViewStates[sectionKey] = SECTION_VIEW_STATE.COLLAPSED;
                    }

                    // Re-render while keeping this button in the same position
                    reRenderWithElementPositionPreserved(toggleButton);
                });

                toggleButton.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                    e.stopPropagation();

                    // Dismiss section - move to bottom
                    const currentIndex = state.sectionOrder.indexOf(sectionKey);
                    if (currentIndex === -1) return; // Safety check

                    state.sectionOrder.splice(currentIndex, 1);
                    state.sectionOrder.push(sectionKey);

                    // Re-render immediately
                    renderFilters(state.lastSearchResults, state.lastSearchTerm);
                });

                sectionWrapper.appendChild(toggleButton);

                // For collapsed state, we need to measure actual items to determine threshold
                // Create visible result elements
                const visibleItemElements = results.map(result => createSearchResultButton(result));

                // Create all items (visible + hidden) for measurement purposes
                const allItems = [...results, ...(hiddenItems || [])];
                const allItemElements = allItems.map(result => createSearchResultButton(result));

                // Determine which results to show based on view state
                let resultsToShow = [];

                if (viewState === SECTION_VIEW_STATE.COLLAPSED) {
                    // Calculate actual threshold based on rendered size using visible items
                    // Temporarily append section to measure (if not already in DOM)
                    const wasInDOM = sectionWrapper.parentNode !== null;
                    if (!wasInDOM) {
                        state.resultsContainerDOM.appendChild(sectionWrapper);
                    }

                    // Calculate threshold based on actual measurements of visible items only
                    const measuredThreshold = calculateCollapseThreshold(sectionWrapper, visibleItemElements);
                    collapseThreshold = measuredThreshold;

                    // Show only visible items up to the threshold
                    resultsToShow = visibleItemElements.slice(0, collapseThreshold);
                } else if (viewState === SECTION_VIEW_STATE.DEFAULT) {
                    // Show only visible results
                    resultsToShow = visibleItemElements;
                } else { // EXPANDED
                    // Show all results including hidden
                    resultsToShow = allItemElements;
                }

                // Add result buttons
                resultsToShow.forEach(resultElement => {
                    sectionWrapper.appendChild(resultElement);
                });

                // Add show more button (+)
                // Only show if there are more items to display
                let showMoreButton = false;

                if (viewState === SECTION_VIEW_STATE.COLLAPSED) {
                    // Show button if there are more visible results beyond the threshold OR if there are hidden items
                    showMoreButton = results.length > collapseThreshold || hasHiddenItems;
                } else if (viewState === SECTION_VIEW_STATE.DEFAULT) {
                    // Show button if there are hidden items
                    showMoreButton = hasHiddenItems;
                }

                if (showMoreButton) {
                    const btn = document.createElement('button');
                    btn.className = 'tag-button state-unselected state-cycle-button show-more-button';
                    btn.textContent = '+';

                    const label = `Show more ${sectionTitle.toLowerCase()}`;
                    btn.setAttribute('title', label);
                    btn.setAttribute('aria-label', label);

                    btn.classList.add(`view-state-${viewState}`);

                    btn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        const currentState = state.sectionViewStates[sectionKey];
                        if (currentState === SECTION_VIEW_STATE.COLLAPSED) {
                            // Check if all visible items are already shown
                            if (results.length <= collapseThreshold && hasHiddenItems) {
                                // Skip DEFAULT and go directly to EXPANDED
                                state.sectionViewStates[sectionKey] = SECTION_VIEW_STATE.EXPANDED;
                            } else {
                                // Go to DEFAULT to show remaining visible items
                                state.sectionViewStates[sectionKey] = SECTION_VIEW_STATE.DEFAULT;
                            }
                        } else if (currentState === SECTION_VIEW_STATE.DEFAULT) {
                            state.sectionViewStates[sectionKey] = SECTION_VIEW_STATE.EXPANDED;
                        }
                        // Re-render while keeping the section top in the same position
                        reRenderWithElementPositionPreserved(sectionWrapper);
                    });

                    sectionWrapper.appendChild(btn);
                }

                // Add show fewer button (-)
                // Only show if clicking it would result in fewer items
                let showFewerButton = false;

                if (viewState === SECTION_VIEW_STATE.DEFAULT) {
                    // Show button if there are more visible results than threshold
                    showFewerButton = results.length > collapseThreshold;
                } else if (viewState === SECTION_VIEW_STATE.EXPANDED) {
                    // Show button if there are hidden items (collapsing would hide them)
                    showFewerButton = hasHiddenItems;
                }

                if (showFewerButton) {
                    const btn = document.createElement('button');
                    btn.className = 'tag-button state-unselected state-cycle-button show-fewer-button';
                    btn.textContent = '−';

                    const label = `Show fewer ${sectionTitle.toLowerCase()}`;
                    btn.setAttribute('title', label);
                    btn.setAttribute('aria-label', label);

                    btn.classList.add(`view-state-${viewState}`);

                    btn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        const currentState = state.sectionViewStates[sectionKey];
                        if (currentState === SECTION_VIEW_STATE.DEFAULT) {
                            state.sectionViewStates[sectionKey] = SECTION_VIEW_STATE.COLLAPSED;
                        } else if (currentState === SECTION_VIEW_STATE.EXPANDED) {
                            state.sectionViewStates[sectionKey] = SECTION_VIEW_STATE.DEFAULT;
                        }
                        // Re-render while keeping this button in the same position
                        reRenderWithElementPositionPreserved(btn);
                    });

                    sectionWrapper.appendChild(btn);
                }

                state.resultsContainerDOM.appendChild(sectionWrapper);
            };

            // Define section metadata
            const sections = {
                locations: {
                    title: 'Places',
                    icon: '<svg xmlns="http://www.w3.org/2000/svg" height="18px" viewBox="0 0 24 24" width="18px" fill="currentColor" aria-hidden="true"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>',
                    results: groupedResults.locations.slice(0, 100),
                    hidden: hiddenResults.locations.slice(0, 100)
                },
                events: {
                    title: 'Events',
                    icon: '<svg xmlns="http://www.w3.org/2000/svg" height="18px" viewBox="0 0 24 24" width="18px" fill="currentColor" aria-hidden="true"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM7 10h5v5H7v-5z"/></svg>',
                    results: groupedResults.events.slice(0, 100),
                    hidden: hiddenResults.events.slice(0, 100)
                },
                tags: {
                    title: 'Tags',
                    icon: '<svg xmlns="http://www.w3.org/2000/svg" height="18px" viewBox="0 0 24 24" width="18px" fill="currentColor" aria-hidden="true"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M21.41 11.58l-9-9C12.05 2.22 11.55 2 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l9 9c.36.36.86.58 1.41.58s1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41s-.23-1.06-.59-1.42zM5.5 7C4.67 7 4 6.33 4 5.5S4.67 4 5.5 4 7 4.67 7 5.5 6.33 7 5.5 7z"/></svg>',
                    results: groupedResults.tags.slice(0, 100),
                    hidden: hiddenResults.tags.slice(0, 100)
                }
            };

            // Render sections in the specified order
            state.sectionOrder.forEach(sectionKey => {
                const section = sections[sectionKey];
                if (section) {
                    renderSection(section.results, section.hidden, section.title, section.icon, sectionKey);
                }
            });

        }

    }

    function populateInitialFilters() {
        state.currentDynamicFrequencies = { ...state.initialGlobalFrequencies };
        state.allAvailableTags.forEach(tag => {
            state.tagStates[tag] = TAG_STATE.UNSELECTED;
        });
        renderFilters();
    }

    function updateView(filteredEvents) {
        state.currentDynamicFrequencies = {};
        state.allAvailableTags.forEach(tag => state.currentDynamicFrequencies[tag] = 0);

        if (filteredEvents && Array.isArray(filteredEvents)) {
            const tagLocationSets = {};
            filteredEvents.forEach(event => {
                if (event.tags && Array.isArray(event.tags) && event.locationKey) {
                    event.tags.forEach(tag => {
                        if (state.allAvailableTags.includes(tag)) {
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

        // Re-run the search with the current term to update the view
        performSearchCallback(state.getSearchTerm());
    }

    function getTagStates() {
        return { ...state.tagStates };
    }

    function getDynamicFrequencies() {
        return { ...state.currentDynamicFrequencies };
    }

    function resetSelections() {
        state.allAvailableTags.forEach(tag => {
            state.tagStates[tag] = TAG_STATE.UNSELECTED;
        });
        clearSearch('');
    }

    /**
     * Programmatically select tags (used for URL parameters)
     * @param {Array<string>} tagsToSelect - Array of tag names to select
     * @param {Function} assignColorCallback - Callback to assign colors to selected tags
     */
    function selectTags(tagsToSelect, assignColorCallback) {
        if (!Array.isArray(tagsToSelect)) {
            return;
        }

        tagsToSelect.forEach(tag => {
            // Only select if the tag exists in available tags
            // Try exact match first, then case-insensitive match
            let matchedTag = tag;
            if (!state.allAvailableTags.includes(tag)) {
                // Try case-insensitive match
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

    return {
        init,
        setAppProviders,
        populateInitialFilters,
        updateView,
        getTagStates,
        getDynamicFrequencies,
        resetSelections,
        selectTags,
        createInteractiveTagButton,
        render: renderFilters,
        clearSearch,
    };
})();