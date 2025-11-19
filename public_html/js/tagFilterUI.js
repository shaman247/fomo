const TagFilterUI = (() => {
    const TAG_STATE = {
        UNSELECTED: 'unselected',
        SELECTED: 'selected',
        REQUIRED: 'required',
        FORBIDDEN: 'forbidden'
    };

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
    };
    const providers = {
        getSelectedLocationKey: () => null,
    };
    let performSearchCallback = () => {};

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
        const selectedLocationKey = providers.getSelectedLocationKey();

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

            searchResults.forEach(result => {
                const type = result.type;
                if (type === 'location') groupedResults.locations.push(result);
                else if (type === 'event') groupedResults.events.push(result);
                else if (type === 'tag') groupedResults.tags.push(result);
            });

            // Sort locations, prioritizing the selected one, then by score
            const selectedLocationKey = providers.getSelectedLocationKey();
            groupedResults.locations.sort((a, b) => {
                const isASelected = a.ref === selectedLocationKey;
                const isBSelected = b.ref === selectedLocationKey;
                if (isASelected !== isBSelected) return isASelected ? -1 : 1;
                return (b.score || 0) - (a.score || 0);
            });
            groupedResults.events.sort((a, b) => (b.score || 0) - (a.score || 0));

            // Filter out selected/required/forbidden tags from search results, then sort
            groupedResults.tags = groupedResults.tags.filter(result => {
                const tagState = state.tagStates[result.ref] || TAG_STATE.UNSELECTED;
                return tagState === TAG_STATE.UNSELECTED;
            });

            groupedResults.tags.sort((a, b) => (b.score || 0) - (a.score || 0));

            const renderSection = (results, sectionTitle, sectionIcon, sectionKey) => {
                if (results.length === 0) return;

                // Create wrapper for section (contains header and results inline)
                const sectionWrapper = document.createElement('div');
                sectionWrapper.className = 'search-results-section';
                sectionWrapper.dataset.sectionKey = sectionKey;

                // Create section header (icon only)
                const header = document.createElement('h4');
                header.className = 'result-group-title';
                header.innerHTML = `<span class="angle-quotes">&laquo;</span> ${sectionIcon} <span class="angle-quotes">&raquo;</span>`;
                header.dataset.sectionKey = sectionKey;
                header.setAttribute('aria-label', sectionTitle);
                header.setAttribute('title', sectionTitle);

                // Add click handler to reorder sections
                header.addEventListener('click', () => {
                    const currentIndex = state.sectionOrder.indexOf(sectionKey);

                    if (currentIndex === 0) {
                        // If already at the top, move to the bottom
                        state.sectionOrder.splice(currentIndex, 1);
                        state.sectionOrder.push(sectionKey);
                    } else {
                        // Otherwise, move to the top
                        state.sectionOrder.splice(currentIndex, 1);
                        state.sectionOrder.unshift(sectionKey);
                    }

                    // Re-render with current search term
                    performSearchCallback(state.searchTerm);
                });

                sectionWrapper.appendChild(header);

                // Add result buttons inline
                results.forEach(result => {
                    const resultElement = createSearchResultButton(result);
                    sectionWrapper.appendChild(resultElement);
                });

                state.resultsContainerDOM.appendChild(sectionWrapper);
            };

            function addDragToScroll(element) {
                let isDown = false;
                let startX;
                let scrollLeft;

                element.addEventListener('mousedown', (e) => {
                    isDown = true;
                    element.style.cursor = 'grabbing';
                    startX = e.pageX - element.offsetLeft;
                    scrollLeft = element.scrollLeft;
                });

                element.addEventListener('mouseleave', () => {
                    isDown = false;
                    element.style.cursor = 'grab';
                });

                element.addEventListener('mouseup', () => {
                    isDown = false;
                    element.style.cursor = 'grab';
                });

                element.addEventListener('mousemove', (e) => {
                    if (!isDown) return;
                    e.preventDefault();
                    const x = e.pageX - element.offsetLeft;
                    const walk = (x - startX) * 2; // Scroll speed multiplier
                    element.scrollLeft = scrollLeft - walk;
                });
            }

            // Define section metadata
            const sections = {
                locations: {
                    title: 'Places',
                    icon: '<svg xmlns="http://www.w3.org/2000/svg" height="18px" viewBox="0 0 24 24" width="18px" fill="currentColor" aria-hidden="true"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>',
                    results: groupedResults.locations.slice(0, 100)
                },
                events: {
                    title: 'Events',
                    icon: '<svg xmlns="http://www.w3.org/2000/svg" height="18px" viewBox="0 0 24 24" width="18px" fill="currentColor" aria-hidden="true"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM7 10h5v5H7v-5z"/></svg>',
                    results: groupedResults.events.slice(0, 100)
                },
                tags: {
                    title: 'Tags',
                    icon: '<svg xmlns="http://www.w3.org/2000/svg" height="18px" viewBox="0 0 24 24" width="18px" fill="currentColor" aria-hidden="true"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M21.41 11.58l-9-9C12.05 2.22 11.55 2 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l9 9c.36.36.86.58 1.41.58s1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41s-.23-1.06-.59-1.42zM5.5 7C4.67 7 4 6.33 4 5.5S4.67 4 5.5 4 7 4.67 7 5.5 6.33 7 5.5 7z"/></svg>',
                    results: groupedResults.tags.slice(0, 100)
                }
            };

            // Render sections in the specified order
            state.sectionOrder.forEach(sectionKey => {
                const section = sections[sectionKey];
                if (section) {
                    renderSection(section.results, section.title, section.icon, sectionKey);
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