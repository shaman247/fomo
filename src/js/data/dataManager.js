/**
 * DataManager Module
 *
 * Manages data fetching, processing, and indexing for events and locations.
 * Handles initial and full dataset loading, event filtering, and tag management.
 *
 * Features:
 * - Network data fetching with timeout and error handling
 * - Event and location data processing
 * - Tag indexing and frequency calculation
 * - Date range filtering
 * - Occurrence parsing and validation
 *
 * @module DataManager
 */
const DataManager = (() => {
    // ========================================
    // DATA FETCHING
    // ========================================

    /**
     * Fetches the raw response text from the specified URL with comprehensive
     * error handling. Shared by fetchData/fetchDataHashed.
     * @param {string} url - The URL to fetch data from
     * @param {number} timeout - Timeout in milliseconds
     * @param {Object} [fetchOptions] - Extra fetch() options (e.g. {cache: 'no-cache'})
     * @returns {Promise<string>} The raw response body text
     * @throws {Error} Network, timeout, or HTTP errors with user-friendly messages
     */
    async function _fetchText(url, timeout, fetchOptions) {
        // Create an AbortController for timeout handling
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);

        let response;
        try {
            response = await fetch(url, { ...(fetchOptions || {}), signal: controller.signal });
            clearTimeout(timeoutId);
        } catch (fetchError) {
            clearTimeout(timeoutId);

            // Handle different types of fetch errors
            if (fetchError.name === 'AbortError') {
                throw new Error(`Request timed out after ${timeout/1000} seconds. Please check your internet connection and try again.`);
            } else if (fetchError.message.includes('Failed to fetch') || fetchError.message.includes('NetworkError')) {
                throw new Error('Unable to connect to the server. Please check your internet connection and try again.');
            } else {
                throw new Error(`Network error: ${fetchError.message}`);
            }
        }

        // Handle HTTP errors
        if (!response.ok) {
            if (response.status === 404) {
                throw new Error(`Data file not found (404). The requested resource may have been moved or deleted.`);
            } else if (response.status === 500) {
                throw new Error(`Server error (500). Please try again later.`);
            } else if (response.status >= 400 && response.status < 500) {
                throw new Error(`Client error (${response.status}). Please refresh the page and try again.`);
            } else if (response.status >= 500) {
                throw new Error(`Server error (${response.status}). Please try again later.`);
            } else {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
        }

        return response.text();
    }

    function _parseJsonText(text) {
        try {
            return JSON.parse(text);
        } catch (parseError) {
            throw new Error(`Invalid data format received from server. The data may be corrupted.`);
        }
    }

    /**
     * Fetches data from the specified URL with comprehensive error handling
     * @param {string} url - The URL to fetch data from
     * @param {number} timeout - Timeout in milliseconds (default: 10000ms)
     * @returns {Promise<Object>} The parsed JSON data
     * @throws {Error} Network, timeout, or parsing errors with user-friendly messages
     */
    async function fetchData(url, timeout = 10000) {
        try {
            return _parseJsonText(await _fetchText(url, timeout));
        } catch (error) {
            // Log the error for debugging
            console.error(`Failed to fetch data from ${url}:`, error);

            // Re-throw the error for the caller to handle
            throw error;
        }
    }

    /**
     * Like fetchData, but also returns a content hash of the raw response
     * text so callers (DataCache write-through, background refresh) can detect
     * unchanged files without re-comparing payloads.
     * @param {string} url - The URL to fetch data from
     * @param {number} timeout - Timeout in milliseconds (default: 10000ms)
     * @param {Object} [fetchOptions] - Extra fetch() options (e.g. {cache: 'no-cache'})
     * @returns {Promise<{data: Object, hash: string}>}
     * @throws {Error} Network, timeout, or parsing errors with user-friendly messages
     */
    async function fetchDataHashed(url, timeout = 10000, fetchOptions) {
        try {
            const text = await _fetchText(url, timeout, fetchOptions);
            return { data: _parseJsonText(text), hash: DataCache.hashString(text) };
        } catch (error) {
            console.error(`Failed to fetch data from ${url}:`, error);
            throw error;
        }
    }

    // ========================================
    // DATA PROCESSING
    // ========================================

    // ========================================
    // COORDINATE PERTURBATION
    // ========================================
    //
    // Multiple distinct venues can sit at the exact same lat/lng — either real
    // (a multi-tenant building like 120 Walker St) or because several venues
    // geocoded to a shared building centroid. Markers, popups, and event
    // grouping all key on the "lat,lng" string (mapManager.updateMarkerData
    // parses the key straight into the marker geometry), so colliding venues
    // collapse into a single marker/popup and only the first venue's events stay
    // reachable.
    //
    // Fix, purely in the UI: nudge each venue at a shared coordinate onto its own
    // point on a tiny circle (a few meters) so each gets a distinct locationKey.
    // Venues are identified by name (locations carry `name`, events carry
    // `location`); offsets are derived deterministically from the ORIGINAL
    // coordinate + sorted venue names, so the layout is stable and idempotent
    // across Phase 1 / Phase 2 loads. Only coordinates shared by 2+ named venues
    // that actually have events are perturbed — everything else is untouched.

    const JITTER_MIN_METERS = 8;          // smallest ring radius (a "very slight" nudge)
    const JITTER_PER_VENUE_METERS = 2.2;  // grow the ring with venue count so points stay separable
    const METERS_PER_DEG_LAT = 111320;
    // ASCII Unit Separator (0x1F): can't occur in coords or venue names. Written as
    // an escape, NOT a raw byte — a literal control char in the source makes the file
    // read as "binary" and silently invisible to grep -I (which once hid a stale call).
    const VENUE_SEP = '\x1f';

    function venueOffsetKey(lat, lng, name) {
        return `${lat},${lng}${VENUE_SEP}${name || ''}`;
    }

    /**
     * Recomputes per-venue coordinate offsets from the current event set.
     * A coordinate is perturbed only when 2+ distinct named venues have events
     * there. Stores state.coordOffsetByVenue: venueOffsetKey(origLat, origLng,
     * name) -> { lat, lng }.
     */
    function computeCoordOffsets(state) {
        const namesByCoord = new Map(); // "lat,lng" -> Set(name)
        for (const event of state.allEvents) {
            const name = event.location;
            if (!name) continue; // events with no venue name can't be disambiguated
            const coordKey = `${event.origLat},${event.origLng}`;
            let names = namesByCoord.get(coordKey);
            if (!names) { names = new Set(); namesByCoord.set(coordKey, names); }
            names.add(name);
        }

        const offsets = new Map();
        for (const [coordKey, nameSet] of namesByCoord) {
            if (nameSet.size < 2) continue; // no collision — leave it alone
            const names = [...nameSet].sort(); // sort => order-independent, stable layout
            const commaIdx = coordKey.indexOf(',');
            const baseLat = Number(coordKey.slice(0, commaIdx));
            const baseLng = Number(coordKey.slice(commaIdx + 1));
            const cosLat = Math.max(0.01, Math.cos(baseLat * Math.PI / 180));
            const radiusM = Math.max(JITTER_MIN_METERS, JITTER_PER_VENUE_METERS * names.length);
            const n = names.length;
            names.forEach((name, i) => {
                const angle = (2 * Math.PI * i) / n;
                const dLat = (radiusM * Math.sin(angle)) / METERS_PER_DEG_LAT;
                const dLng = (radiusM * Math.cos(angle)) / (METERS_PER_DEG_LAT * cosLat);
                offsets.set(venueOffsetKey(baseLat, baseLng, name), {
                    lat: Number((baseLat + dLat).toFixed(7)),
                    lng: Number((baseLng + dLng).toFixed(7)),
                });
            });
        }
        state.coordOffsetByVenue = offsets;
    }

    /**
     * Rebuilds state.locationsByLatLng from the accumulated raw location list,
     * applying any per-venue offsets so each venue lands on its own key.
     */
    function buildLocationsIndex(state) {
        const byKey = {};
        const offsets = state.coordOffsetByVenue || new Map();
        for (const location of (state.rawLocations || [])) {
            if (location.lat == null || location.lng == null) continue;
            const off = offsets.get(venueOffsetKey(location.lat, location.lng, location.name));
            const lat = off ? off.lat : location.lat;
            const lng = off ? off.lng : location.lng;
            const key = `${lat},${lng}`;
            if (!byKey[key]) {
                byKey[key] = off ? { ...location, lat, lng } : location;
            }
        }
        state.locationsByLatLng = byKey;
    }

    /**
     * Appends locations to the accumulated raw list, de-duped by coord+name so
     * distinct venues sharing a coordinate are all retained (the legacy
     * first-wins lookup dropped them, which is what hid colliding venues).
     */
    function addRawLocations(locationData, state) {
        if (!state.rawLocations) state.rawLocations = [];
        if (!state._rawLocationSeen) state._rawLocationSeen = new Set();
        for (const location of locationData) {
            if (location.lat == null || location.lng == null) continue;
            const dedupeKey = venueOffsetKey(location.lat, location.lng, location.name);
            if (state._rawLocationSeen.has(dedupeKey)) continue;
            state._rawLocationSeen.add(dedupeKey);
            // On Windows, swap an unrenderable country-flag emoji for this
            // location's configured alt_emoji (no-op elsewhere). Done at the
            // source so markers, popup headers, derived marker colors, and
            // flag-event location fallbacks all stay in sync.
            if (location.emoji) location.emoji = Utils.resolveDisplayEmoji(location.emoji, location.alt_emoji);
            // Derive leaf-only display_tags client-side (was shipped inline).
            if (location.tags && !location.display_tags) {
                location.display_tags = filterToLeafTags(location.tags, state);
            }
            state.rawLocations.push(location);
        }
    }

    /**
     * Re-keys events and rebuilds the location index onto perturbed coordinates
     * wherever 2+ named venues share an exact coordinate. Idempotent: always
     * derives from each event's ORIGINAL coordinate, so it is safe to re-run
     * after the Phase 2 merge brings in more venues.
     * @param {Object} state - Application state
     */
    function applyCoordPerturbation(state) {
        computeCoordOffsets(state);
        buildLocationsIndex(state);
        const offsets = state.coordOffsetByVenue;
        for (const event of state.allEvents) {
            const off = offsets.get(venueOffsetKey(event.origLat, event.origLng, event.location));
            const lat = off ? off.lat : event.origLat;
            const lng = off ? off.lng : event.origLng;
            event.latitude = lat;
            event.longitude = lng;
            event.locationKey = `${lat},${lng}`;
        }
        rebuildEventLookups(state);
    }

    /**
     * Processes location data into a lookup map
     * @param {Array} locationData - Array of location objects
     * @param {Object} state - Application state
     */
    function processLocationData(locationData, state) {
        state.rawLocations = [];
        state._rawLocationSeen = new Set();
        addRawLocations(locationData, state);
        buildLocationsIndex(state);
    }

    /**
     * Processes initial dataset (events and locations)
     * @param {Array} eventData - Array of event objects
     * @param {Array} locationData - Array of location objects
     * @param {Object} state - Application state
     * @param {Object} config - Application configuration
     */
    function processInitialData(eventData, locationData, state, config) {
        processLocationData(locationData, state);
        processEventData(eventData, state, config);
        applyCoordPerturbation(state);
    }

    /**
     * Client-side port of the exporter's `_filter_to_leaf_tags`
     * (pipeline/exporter.py — KEEP IN SYNC). Drops curated tags that are
     * ancestors of another curated tag present on the same item, so popups show
     * only the most-specific (leaf) tags. Keywords (not in the hierarchy) are
     * always kept. Replaces the `display_tags` the exporter used to ship inline.
     * @param {string[]} tags
     * @param {Object} state - uses tagDescendantsOf (tag -> Set of descendants)
     *   and hierarchyTagsSet (set of curated tag names)
     * @returns {string[]} leaf-filtered tags (returns the input array unchanged
     *   when there's nothing to strip)
     */
    function filterToLeafTags(tags, state) {
        if (!tags || tags.length === 0) return tags;
        const descendantsOf = state.tagDescendantsOf || {};
        const curatedSet = state.hierarchyTagsSet;
        if (!curatedSet || curatedSet.size === 0) return tags;
        // Only curated tags present on this item count as "strip targets".
        const curatedPresent = tags.filter(t => curatedSet.has(t));
        if (curatedPresent.length === 0) return tags;
        return tags.filter(t => {
            const desc = descendantsOf[t];
            if (!desc) return true;            // leaf (no descendants) → keep
            for (const c of curatedPresent) {  // strip if a present curated tag is below it
                if (desc.has(c)) return false;
            }
            return true;
        });
    }

    /**
     * Transforms a raw event into a structured event object.
     * The id comes from the backend export so the same event in two chunks
     * (recurring events live in every day chunk they touch) collapses to one.
     * @param {Object} rawEvent - Raw event from data source
     * @param {Object} state - Application state (for location lookups)
     * @param {Object} config - Application configuration
     * @param {boolean} isWindows - Whether running on Windows
     * @returns {Object|null} Processed event or null if invalid
     */
    function transformRawEvent(rawEvent, state, config, isWindows) {
        const { id, lat, lng, tags, occurrences: occurrencesJson, ...restOfEvent } = rawEvent;

        // Decode HTML entities in text fields
        ['name', 'location', 'sublocation'].forEach(field => {
            if (restOfEvent[field]) {
                restOfEvent[field] = Utils.decodeHtml(restOfEvent[field]);
            }
        });

        // Validate required fields
        if (!restOfEvent.name || lat == null || lng == null || lat === '' || lng === '') {
            return null;
        }

        // Clear invalid location/sublocation values
        ['location', 'sublocation'].forEach(field => {
            if (restOfEvent[field] && (restOfEvent[field].startsWith('None') || restOfEvent[field].startsWith('N/A'))) {
                restOfEvent[field] = '';
            }
        });

        // Parse occurrences
        let parsedOccurrences;
        try {
            parsedOccurrences = parseOccurrences(occurrencesJson);
        } catch (e) {
            console.warn(`Could not parse occurrences for event "${rawEvent.name}":`, occurrencesJson, e);
            return null;
        }

        // Filter by date range
        if (!isEventInAppDateRange(parsedOccurrences, config)) {
            return null;
        }

        const locationKey = `${lat},${lng}`;

        // On Windows, replace country flag emojis with the venue's emoji,
        // falling back to the globe (via resolveDisplayEmoji) so a flag never
        // reaches the DOM as letter boxes even when the venue lookup misses.
        let emoji = restOfEvent.emoji;
        if (isWindows && Utils.isCountryFlagEmoji(emoji)) {
            const location = state.locationsByLatLng[locationKey];
            emoji = Utils.resolveDisplayEmoji(emoji, location?.emoji);
        }

        // On Windows, country-flag emoji inside the title render as letter-box
        // pairs (e.g. "HT"), so strip them from the display name/short_name at
        // the source — popups, list rows, and search results all read these.
        // (Map labels strip flags on every platform; see mapManager.)
        if (isWindows) {
            if (restOfEvent.name) restOfEvent.name = Utils.stripCountryFlagEmoji(restOfEvent.name);
            if (restOfEvent.short_name) restOfEvent.short_name = Utils.stripCountryFlagEmoji(restOfEvent.short_name);
        }

        return {
            id,
            ...restOfEvent,
            section: restOfEvent.section || 'Events',
            emoji,
            // origLat/origLng are the unmodified export coordinates; latitude/
            // longitude/locationKey may be re-keyed by applyCoordPerturbation
            // when this venue collides with another at the same coordinate.
            origLat: lat,
            origLng: lng,
            latitude: lat,
            longitude: lng,
            locationKey,
            tags,
            // display_tags (leaf-only, for popups) used to be shipped inline;
            // now derived from the tag hierarchy the frontend already loads.
            display_tags: filterToLeafTags(tags, state),
            occurrences: parsedOccurrences
        };
    }

    /**
     * Processes event data into structured format. Leaves eventsById
     * untouched — processInitialData owns the (single) lookup build via
     * applyCoordPerturbation's rebuildEventLookups.
     * @param {Array} eventData - Array of raw event objects
     * @param {Object} state - Application state
     * @param {Object} config - Application configuration
     */
    function processEventData(eventData, state, config) {
        const isWindows = Utils.isWindows();
        state.allEvents = eventData
            .map(rawEvent => transformRawEvent(rawEvent, state, config, isWindows))
            .filter(Boolean);
    }

    /**
     * Processes the full dataset (events and locations), yielding to the main
     * thread between event-processing chunks. Keeps clicks/typing responsive
     * during the heavy Phase 2 merge (~30k events would otherwise block
     * ~150ms uninterrupted).
     */
    async function processFullDataAsync(fullEventData, fullLocationData, state, config, onProgress) {
        addRawLocations(fullLocationData, state);
        // Rebuild the location index BEFORE transforming Phase-2 events:
        // transformRawEvent's Windows flag-emoji fallback looks up the event's
        // venue in locationsByLatLng, and without this rebuild the index still
        // holds only Phase-1 venues (empty in the background-refresh path).
        buildLocationsIndex(state);
        await appendEventDataChunked(fullEventData, state, config, onProgress);
        // One re-key pass after the full merge so cross-chunk venue collisions
        // (a venue whose siblings only appear in a later chunk) are caught.
        // INVARIANT: appendEventDataChunked leaves the event lookups stale
        // (this rebuild owns them), and only a microtask boundary separates
        // the two — user input can't interleave. Never insert a real yield
        // (await _yieldToMain/setTimeout) between these calls.
        applyCoordPerturbation(state);
    }

    /**
     * Parses occurrence data into structured format
     * @param {Array} occurrencesJson - Raw occurrence data
     * @returns {Array} Parsed occurrences with start/end dates
     */
    function parseOccurrences(occurrencesJson) {
        const occurrencesArray = occurrencesJson || [];
        if (!Array.isArray(occurrencesArray)) return []; // Keep this check for safety

        const parsedOccurrences = occurrencesArray.map(occ => {
            const [startDateStr, startTimeStr, endDateStr, endTimeStr] = occ;
            const start = Utils.parseDateInZone(startDateStr, startTimeStr);
            const effectiveEndDateStr = (endDateStr && endDateStr.trim() !== '') ? endDateStr : startDateStr;
            const effectiveEndTimeStr = (endTimeStr && endTimeStr.trim() !== '') ? endTimeStr : startTimeStr;
            const end = Utils.parseDateInZone(effectiveEndDateStr, effectiveEndTimeStr);

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
    }

    /**
     * Checks if event falls within application date range
     * @param {Array} occurrences - Event occurrences
     * @param {Object} config - Application configuration
     * @returns {boolean} True if event is in date range
     */
    function isEventInAppDateRange(occurrences, config) {
        return occurrences.some(occ =>
            occ.start <= config.END_DATE && occ.end >= config.START_DATE
        );
    }

    /**
     * Appends new event data to existing events. Processes events in batches
     * of EVENT_PROCESS_CHUNK_SIZE and yields to the main thread between chunks
     * via _yieldToMain(), so user interactions get frame boundaries to fire on.
     */
    // Use scheduler.yield() when available (yields with input priority on modern Chrome),
    // otherwise MessageChannel.postMessage (sub-ms scheduling, vs setTimeout's 4ms min).
    // Lets chunked loops yield ~10× more cheaply than `setTimeout(0)`.
    let _yieldChannel = null;
    function _yieldToMain() {
        if (typeof scheduler !== 'undefined' && typeof scheduler.yield === 'function') {
            return scheduler.yield();
        }
        if (typeof MessageChannel !== 'undefined') {
            if (!_yieldChannel) {
                _yieldChannel = new MessageChannel();
                _yieldChannel.port1.start?.();
            }
            return new Promise(resolve => {
                const handler = () => {
                    _yieldChannel.port1.removeEventListener('message', handler);
                    resolve();
                };
                _yieldChannel.port1.addEventListener('message', handler);
                _yieldChannel.port2.postMessage(0);
            });
        }
        return new Promise(r => setTimeout(r, 0));
    }

    // Larger chunks = less yield overhead but longer pauses between input handling.
    // 4000 events ≈ ~25ms per chunk on a typical machine — under a 30fps frame budget.
    const EVENT_PROCESS_CHUNK_SIZE = 4000;
    async function appendEventDataChunked(newEventData, state, config, onProgress) {
        const isWindows = Utils.isWindows();
        const total = newEventData.length;
        const newEvents = [];
        // Track ids seen across chunks (Phase 1's eventsById + this batch).
        // Multi-day events appear in every chunk they touch — dedup on id.
        const seen = new Set(Object.keys(state.eventsById || {}));

        for (let i = 0; i < total; i += EVENT_PROCESS_CHUNK_SIZE) {
            const end = Math.min(i + EVENT_PROCESS_CHUNK_SIZE, total);
            for (let j = i; j < end; j++) {
                const raw = newEventData[j];
                if (!raw || raw.id == null) continue;
                const idKey = String(raw.id);
                if (seen.has(idKey)) continue;
                seen.add(idKey);
                const ev = transformRawEvent(raw, state, config, isWindows);
                if (ev) newEvents.push(ev);
            }
            if (onProgress) onProgress(end, total);
            if (end < total) {
                await _yieldToMain();
            }
        }

        state.allEvents.push(...newEvents);
        // No lookup update here: processFullDataAsync (the only caller)
        // immediately rebuilds eventsById inside applyCoordPerturbation —
        // appending first was a wasted O(n) pass on the blocking Phase-2 tail.
    }

    // ========================================
    // INDEXING & LOOKUPS
    // ========================================

    /**
     * Rebuilds event lookup indexes
     * @param {Object} state - Application state
     */
    function rebuildEventLookups(state) {
        state.eventsById = {};
        appendToEventLookups(state, state.allEvents);
    }

    /**
     * Append-only keying of events into eventsById.
     * The live load paths (processInitialData / processFullDataAsync) don't
     * call this directly — each defers to the single rebuildEventLookups pass
     * inside applyCoordPerturbation.
     */
    function appendToEventLookups(state, eventsToAdd) {
        if (!state.eventsById) state.eventsById = {};
        for (const event of eventsToAdd) {
            state.eventsById[event.id] = event;
        }
    }

    /**
     * Builds search index with normalized text for accent/case-insensitive search
     * @param {Object} state - Application state
     */
    /**
     * Async chunked version of buildSearchIndex. Yields to the main thread
     * every SEARCH_INDEX_CHUNK_SIZE events. The synchronous version is kept
     * for callers that need to block (e.g. a search fired before the async
     * build completes).
     */
    const SEARCH_INDEX_CHUNK_SIZE = 5000;
    async function buildSearchIndexAsync(state) {
        _initSearchIndexShell(state);
        for (let i = 0; i < state.allEvents.length; i += SEARCH_INDEX_CHUNK_SIZE) {
            const end = Math.min(i + SEARCH_INDEX_CHUNK_SIZE, state.allEvents.length);
            for (let j = i; j < end; j++) {
                _indexEvent(state, state.allEvents[j]);
            }
            if (end < state.allEvents.length) {
                await _yieldToMain();
            }
        }
        _indexLocationsTagsOrganizers(state);
    }

    function _initSearchIndexShell(state) {
        state.searchIndex = {
            events: new Map(),
            locations: new Map(),
            tags: new Map(),
            organizers: new Map(),
            eventDisplayNames: new Map()
        };
    }

    function _indexEvent(state, event) {
        const searchableFields = [
            event.name, event.short_name, event.description, event.location, event.sublocation
        ].filter(Boolean);
        const normalizedText = searchableFields.map(field => Utils.normalizeForSearch(field)).join(' ');
        state.searchIndex.events.set(event.id, normalizedText);
        const nameToDisplay = Utils.getDisplayName(event);
        const formatted = Utils.formatAndSanitize(nameToDisplay).replace(/<\/?em>/g, '');
        state.searchIndex.eventDisplayNames.set(event.id, formatted);
    }

    function _indexLocationsTagsOrganizers(state) {
        Object.entries(state.locationsByLatLng).forEach(([key, location]) => {
            const searchableFields = [location.name, location.short_name, ...(location.tags || [])].filter(Boolean);
            const normalizedText = searchableFields.map(field => Utils.normalizeForSearch(field)).join(' ');
            state.searchIndex.locations.set(key, normalizedText);
        });
        state.allAvailableTags.forEach(tag => {
            state.searchIndex.tags.set(tag, Utils.normalizeForSearch(tag));
        });
        if (state.organizersById) {
            Object.entries(state.organizersById).forEach(([id, org]) => {
                state.searchIndex.organizers.set(id, Utils.normalizeForSearch(org.name || ''));
            });
        }
    }

    function buildSearchIndex(state) {
        _initSearchIndexShell(state);
        for (const event of state.allEvents) _indexEvent(state, event);
        _indexLocationsTagsOrganizers(state);
    }

    /**
     * Merge a {eventId: description} companion map into already-loaded events.
     * Descriptions are fetched after the markers render (they're the largest,
     * worst-compressing field and aren't needed for the map). When the search
     * index already exists (Phase 1), pass reindex=true to re-index the touched
     * events so description text becomes searchable; in Phase 2 the descriptions
     * are merged before buildSearchIndexAsync, so reindex is unnecessary.
     * @returns {boolean} true if any loaded event was updated
     */
    function applyDescriptions(descMap, state, reindex) {
        if (!descMap) return false;
        const byId = state.eventsById || {};
        let changed = false;
        for (const id in descMap) {
            const ev = byId[id];              // object key access coerces id to string
            if (!ev) continue;
            ev.description = descMap[id];
            changed = true;
            if (reindex && state.searchIndex) _indexEvent(state, ev);
        }
        return changed;
    }

    /**
     * Builds tag index for efficient tag-based lookups
     * @param {Object} state - Application state
     * @param {Array} events - Events to index (optional, defaults to all events)
     */
    function buildTagIndex(state, events) {
        const eventsToIndex = events || state.allEvents;
        state.eventTagIndex = {};
        eventsToIndex.forEach(event => {
            const combinedTags = new Set(event.tags || []);
            const location = state.locationsByLatLng[event.locationKey];
            if (location && location.tags) {
                location.tags.forEach(tag => combinedTags.add(tag));
            }

            // Index each organizer as a pseudo-tag so organizer chips filter
            // through the same selected/required path as ordinary tags. A merged
            // event can have several organizers (organizer_ids).
            for (const orgTag of Utils.organizerTagsForEvent(event)) {
                combinedTags.add(orgTag);
            }

            combinedTags.forEach(tag => {
                if (!state.eventTagIndex[tag]) {
                    state.eventTagIndex[tag] = [];
                }
                state.eventTagIndex[tag].push(event.id);
            });
        });
    }

    /**
     * Calculates tag frequencies across all locations
     * @param {Object} state - Application state
     */
    function calculateTagFrequencies(state) {
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
    }

    /**
     * Builds hierarchy lookup maps from the exported tag_hierarchy.json data.
     * @param {Object} data - { tags: [...], keywords: [...] }
     * @returns {Object} { childrenOf, parentsOf, descendantsOf, hierarchyTagsSet, tagEmojiMap }
     */
    function buildTagHierarchyMaps(data) {
        const tags = data.tags || [];

        const childrenOf = {};   // parent -> [children]
        const parentsOf = {};    // child -> [parents]
        const tagEmojiMap = {};  // tagName -> emoji
        // Set of all curated tag names (tags NOT in this set are keywords)
        const hierarchyTagsSet = new Set();

        // Build parent/child maps from flat list
        tags.forEach(tag => {
            hierarchyTagsSet.add(tag.name);
            // On Windows, swap an unrenderable country-flag emoji for the tag's
            // configured alt_emoji (no-op elsewhere) so tag chips and emoji-
            // derived chip colors stay in sync.
            const emoji = tag.emoji ? Utils.resolveDisplayEmoji(tag.emoji, tag.alt_emoji) : tag.emoji;
            if (emoji) tagEmojiMap[tag.name] = emoji;
            const parents = tag.parents || [];
            if (parents.length > 0) {
                parentsOf[tag.name] = parents;
                parents.forEach(parent => {
                    if (!childrenOf[parent]) childrenOf[parent] = [];
                    childrenOf[parent].push(tag.name);
                });
            }
        });

        // Compute transitive descendants via BFS
        const descendantsOf = {};
        const allParents = Object.keys(childrenOf);
        allParents.forEach(parent => {
            const descendants = new Set();
            const queue = [...(childrenOf[parent] || [])];
            while (queue.length > 0) {
                const child = queue.shift();
                if (descendants.has(child)) continue;
                descendants.add(child);
                (childrenOf[child] || []).forEach(grandchild => {
                    if (!descendants.has(grandchild)) queue.push(grandchild);
                });
            }
            descendantsOf[parent] = descendants;
        });

        return { childrenOf, parentsOf, descendantsOf, hierarchyTagsSet, tagEmojiMap };
    }

    /**
     * Processes tag hierarchy and available tags
     * @param {Object} state - Application state
     * @param {Object} config - Application configuration
     */
    function processTagHierarchy(state, config) {
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

        // Structural Format nodes (the "Format" root + its category children) exist
        // in the hierarchy for grouping/aggregation but are NOT surfaced as
        // selectable chips — only the leaf event-type tags under them are. Derived
        // from the hierarchy so it stays correct if categories change.
        // Refilled IN PLACE when the Set already exists: FilterPanelUI captures a
        // reference to it at init, and this runs again in Phase 2 and on every
        // background data refresh — reassigning would strand that reference.
        const formatChildren = (state.tagChildrenOf && state.tagChildrenOf['Format']) || [];
        if (state.structuralFormatTags instanceof Set) {
            state.structuralFormatTags.clear();
            state.structuralFormatTags.add('Format');
            formatChildren.forEach(tag => state.structuralFormatTags.add(tag));
        } else {
            state.structuralFormatTags = new Set(['Format', ...formatChildren]);
        }

        // Exclude keywords (tags not in the hierarchy) and structural Format nodes
        // from the browsable/selectable tag list.
        const hierarchyTagsSet = state.hierarchyTagsSet || new Set();
        state.allAvailableTags = Array.from(allUniqueTagsSet)
            .filter(tag => (hierarchyTagsSet.size === 0 || hierarchyTagsSet.has(tag))
                && !state.structuralFormatTags.has(tag))
            .sort();

        // Precompute the empty-term tag list (excludes geotags). SearchManager
        // iterates this on every search-clear; doing the geotag filter once
        // saves ~2,100 Set lookups per search.
        const geotagsSet = state.geotagsSet || new Set();
        state.searchableTagsForEmptyTerm = state.allAvailableTags.filter(
            tag => !geotagsSet.has(tag.toLowerCase())
        );
    }

    /**
     * Groups events by location key for events in the current date range
     * Rebuilds the eventsByLatLngInDateRange lookup from filtered events
     * @param {Object} state - Application state (will be modified)
     */
    function groupEventsByLatLngInDateRange(state) {
        state.eventsByLatLngInDateRange =
            FilterManager.groupEventsByLocation(state.allEventsFilteredByDateAndLocation);
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        fetchData,
        fetchDataHashed,
        processInitialData,
        processFullDataAsync,
        applyDescriptions,
        buildSearchIndex,
        buildSearchIndexAsync,
        buildTagIndex,
        calculateTagFrequencies,
        buildTagHierarchyMaps,
        processTagHierarchy,
        groupEventsByLatLngInDateRange
    };
})();
