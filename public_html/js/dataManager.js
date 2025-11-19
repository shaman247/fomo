const DataManager = {
    fetchData: async function(url) {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    },

    processLocationData: function(locationData, state) {
        state.locationsByLatLng = {};
        locationData.forEach(location => {
            if (location.lat != null && location.lng != null) {
                const locationKey = `${location.lat},${location.lng}`;
                if (!state.locationsByLatLng[locationKey]) {
                    state.locationsByLatLng[locationKey] = location;
                }
            }
        });
    },

    processInitialData: function(eventData, locationData, state, config) {
        this.processLocationData(locationData, state);
        this.processEventData(eventData, state, config);
    },


    processEventData: function(eventData, state, config) {
        let windows = Utils.isWindows();
        state.allEvents = eventData.flatMap((rawEvent, index) => {
            const { lat, lng, tags, occurrences: occurrencesJson, ...restOfEvent } = rawEvent;

            ['name', 'location', 'sublocation'].forEach(field => {
                if (restOfEvent[field]) {
                    restOfEvent[field] = Utils.decodeHtml(restOfEvent[field]);
                }
            });

            if (!restOfEvent.name || lat == null || lng == null || lat === '' || lng === '') {
                return [];
            }

            ['location', 'sublocation'].forEach(field => {
                if (restOfEvent[field] && (restOfEvent[field].startsWith('None') || restOfEvent[field].startsWith('N/A'))) {
                    restOfEvent[field] = '';
                }
            });

            let parsedOccurrences;
            try {
                parsedOccurrences = this.parseOccurrences(occurrencesJson);
            } catch (e) {
                console.warn(`Could not parse occurrences for event "${rawEvent.name}":`, occurrencesJson, e);
                return [];
            }

            if (!this.isEventInAppDateRange(parsedOccurrences, config)) {
                return [];
            }

            const locationKey = `${lat},${lng}`;

            // On Windows, replace country flag emojis with location emoji
            let emoji = restOfEvent.emoji;
            if (windows && Utils.isCountryFlagEmoji(emoji)) {
                const location = state.locationsByLatLng[locationKey];
                if (location?.emoji) {
                    emoji = location.emoji;
                }
            }

            return [{
                id: index,
                ...restOfEvent,
                emoji: emoji,
                latitude: lat,
                longitude: lng,
                locationKey: locationKey,
                tags: tags,
                occurrences: parsedOccurrences
            }];
        });

        this.rebuildEventLookups(state);
        console.log("Total unique events processed:", state.allEvents.length);
    },

    processFullData: function(fullEventData, fullLocationData, state, config) {
        // Add new locations from the full set
        fullLocationData.forEach(location => {
            if (location.lat != null && location.lng != null) {
                const locationKey = `${location.lat},${location.lng}`;
                if (!state.locationsByLatLng[locationKey]) {
                    state.locationsByLatLng[locationKey] = location;
                }
            }
        });

        // Append new events from the full set
        this.appendEventData(fullEventData, state, config);
    },

    parseOccurrences: function(occurrencesJson) {
        const occurrencesArray = occurrencesJson || [];
        if (!Array.isArray(occurrencesArray)) return []; // Keep this check for safety

        const parsedOccurrences = occurrencesArray.map(occ => {
            const [startDateStr, startTimeStr, endDateStr, endTimeStr] = occ;
            const start = Utils.parseDateInNewYork(startDateStr, startTimeStr);
            const effectiveEndDateStr = (endDateStr && endDateStr.trim() !== '') ? endDateStr : startDateStr;
            const effectiveEndTimeStr = (endTimeStr && endTimeStr.trim() !== '') ? endTimeStr : startTimeStr;
            const end = Utils.parseDateInNewYork(effectiveEndDateStr, effectiveEndTimeStr);

            if (start && !end) {
                return { start, end: new Date(start), originalStartTime: startTimeStr, originalEndTime: endTimeStr };
            }
            if (start && end) {
                return { start, end, originalStartTime: startTimeStr, originalEndTime: endTimeStr };
            }
            return null;
        }).filter(Boolean);

        parsedOccurrences.sort((a, b) => a.start - b.start);
        return parsedOccurrences;
    },

    isEventInAppDateRange: function(occurrences, config) {
        return occurrences.some(occ =>
            occ.start <= config.END_DATE && occ.end >= config.START_DATE
        );
    },

    appendEventData: function(newEventData, state, config) {
        const initialEventCount = state.allEvents.length;

        const newEvents = newEventData.flatMap((rawEvent, index) => {
            const { lat, lng, tags, occurrences: occurrencesJson, ...restOfEvent } = rawEvent;

            ['name', 'location', 'sublocation'].forEach(field => {
                if (restOfEvent[field]) {
                    restOfEvent[field] = Utils.decodeHtml(restOfEvent[field]);
                }
            });

            if (!restOfEvent.name || lat == null || lng == null || lat === '' || lng === '') {
                return [];
            }

            ['location', 'sublocation'].forEach(field => {
                if (restOfEvent[field] && (restOfEvent[field].startsWith('None') || restOfEvent[field].startsWith('N/A'))) {
                    restOfEvent[field] = '';
                }
            });

            const parsedOccurrences = this.parseOccurrences(occurrencesJson);
            if (!this.isEventInAppDateRange(parsedOccurrences, config)) {
                return [];
            }

            const locationKey = `${lat},${lng}`;

            // On Windows, replace country flag emojis with location emoji
            let emoji = restOfEvent.emoji;
            if (Utils.isWindows() && Utils.isCountryFlagEmoji(emoji)) {
                const location = state.locationsByLatLng[locationKey];
                if (location?.emoji) {
                    emoji = location.emoji;
                }
            }

            return [{
                id: initialEventCount + index, // Ensure unique IDs
                ...restOfEvent,
                emoji: emoji,
                latitude: lat,
                longitude: lng,
                locationKey: locationKey,
                tags: tags,
                occurrences: parsedOccurrences
            }];
        });

        state.allEvents.push(...newEvents);
        this.rebuildEventLookups(state);
        console.log("Full dataset loaded. Total unique events:", state.allEvents.length);
    },

    rebuildEventLookups: function(state) {
        state.eventsById = {};
        state.eventsByLatLng = {};
        state.allEvents.forEach(event => {
            state.eventsById[event.id] = event;
            if (event.locationKey) {
                if (!state.eventsByLatLng[event.locationKey]) {
                    state.eventsByLatLng[event.locationKey] = [];
                }
                state.eventsByLatLng[event.locationKey].push(event);
            }
        });
    },

    buildTagIndex: function(state, events) {
        const eventsToIndex = events || state.allEvents;
        state.eventTagIndex = {};
        eventsToIndex.forEach(event => {
            const combinedTags = new Set(event.tags || []);
            const location = state.locationsByLatLng[event.locationKey];
            if (location && location.tags) {
                location.tags.forEach(tag => combinedTags.add(tag));
            }

            combinedTags.forEach(tag => {
                if (!state.eventTagIndex[tag]) {
                    state.eventTagIndex[tag] = [];
                }
                state.eventTagIndex[tag].push(event.id);
            });
        });
    },

    calculateTagFrequencies: function(state) {
        const tagLocationSets = {};
        state.allEvents.forEach(event => {
            if (event.tags && Array.isArray(event.tags) && event.locationKey) {
                event.tags.forEach(tag => {
                    if (!tagLocationSets[tag]) {
                        tagLocationSets[tag] = new Set();
                    }
                    tagLocationSets[tag].add(event.locationKey);
                });
            }
        });

        Object.entries(state.locationsByLatLng).forEach(([locationKey, location]) => {
            if (location.tags && Array.isArray(location.tags)) {
                location.tags.forEach(tag => {
                    if (!tagLocationSets[tag]) {
                        tagLocationSets[tag] = new Set();
                    }
                    // Add the locationKey to the set for this tag
                    tagLocationSets[tag].add(locationKey);
                });
            }
        });

        state.tagFrequencies = {};
        for (const tag in tagLocationSets) {
            state.tagFrequencies[tag] = tagLocationSets[tag].size;
        }
    },

    processTagHierarchy: function(state, config) {
        state.tagColors = state.tagConfig.colors || {};
        const allUniqueTagsSet = new Set();
        state.allEvents.forEach(event => {
            if (event.tags && Array.isArray(event.tags)) {
                event.tags.forEach(tag => allUniqueTagsSet.add(tag));
            }
        });

        Object.values(state.locationsByLatLng).forEach(location => {
            if (location.tags && Array.isArray(location.tags)) {
                location.tags.forEach(tag => allUniqueTagsSet.add(tag));
            }
        });

        state.allAvailableTags = Array.from(allUniqueTagsSet).sort();
    }
};
