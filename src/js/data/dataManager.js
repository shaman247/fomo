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

    /**
     * Fetch and parse a JSON file. `prepare(text)` (optional, async) runs on
     * each downloaded body before parsing; its result's fields are merged into
     * the return value, and `skipParse: true` returns without parsing.
     */
    async function _fetchJson(url, timeout, fetchOptions, prepare) {
        // A cached response or an interrupted publish can contain partial JSON.
        // Retry parsing failures once with a full network reload, replacing the
        // HTTP cache entry instead of accepting a 304 for the same broken body.
        for (let attempt = 0; attempt < 2; attempt++) {
            const options = attempt ? { ...fetchOptions, cache: 'reload' } : fetchOptions;
            const text = await _fetchText(url, timeout, options);
            const extra = prepare ? await prepare(text) : null;
            if (extra && extra.skipParse) return { data: undefined, text, ...extra };
            try {
                return { data: JSON.parse(text), text, ...extra };
            } catch (parseError) {
                if (attempt) {
                    throw new Error(`Invalid JSON in ${url} after retrying the download. Please try again shortly.`);
                }
                console.warn(`Invalid JSON in ${url}; retrying without cached data.`);
            }
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
            return (await _fetchJson(url, timeout)).data;
        } catch (error) {
            // Log the error for debugging
            console.error(`Failed to fetch data from ${url}:`, error);

            // Re-throw the error for the caller to handle
            throw error;
        }
    }

    /**
     * Like fetchData, but also returns the UTF-8 body and its content hash so
     * callers (DataCache write-through, background refresh) can store the
     * file cheaply and detect unchanged files without re-comparing payloads.
     *
     * The body is hashed (off the main thread where WebCrypto exists) before
     * it is parsed, so encoding and parsing land in separate tasks. When the
     * hash equals `knownHash` the body is byte-identical to a file that
     * already parsed, so parsing is skipped: `data` is undefined and
     * `unchanged` is true (DataCache.parseBytes(bytes) produces it on demand).
     * @param {string} url - The URL to fetch data from
     * @param {number} timeout - Timeout in milliseconds (default: 10000ms)
     * @param {Object} [fetchOptions] - Extra fetch() options (e.g. {cache: 'no-cache'})
     * @param {string} [knownHash] - hash of a cached copy; skips the parse on a match
     * @returns {Promise<{data: (Object|undefined), bytes: Uint8Array, hash: string, unchanged: boolean}>}
     * @throws {Error} Network, timeout, or parsing errors with user-friendly messages
     */
    async function fetchDataHashed(url, timeout = 10000, fetchOptions, knownHash) {
        try {
            // Distinguish incompatible payloads in the browser HTTP cache as well as IndexedDB.
            const versionedUrl = `${url}${url.includes('?') ? '&' : '?'}schema=${DataCache.schemaVersion}`;
            const { data, bytes, hash, skipParse } = await _fetchJson(versionedUrl, timeout, fetchOptions, async (text) => {
                const bytes = DataCache.encodeText(text);
                const hash = await DataCache.hashBytes(bytes);
                return { bytes, hash, skipParse: !!knownHash && hash === knownHash };
            });
            return { data, bytes, hash, unchanged: skipParse };
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
    // Venues are identified by the exported place_id, with coord+name matching
    // only for legacy events lacking an ID. Offsets derive deterministically
    // from the ORIGINAL coordinate + sorted identities. Only coordinates shared
    // by 2+ venues with events are perturbed. Location metadata always comes from
    // the event's own venue; a building or sibling tenant must never supply it.

    const JITTER_MIN_METERS = 8;          // smallest ring radius (a "very slight" nudge)
    const JITTER_PER_VENUE_METERS = 2.2;  // grow the ring with venue count so points stay separable
    const METERS_PER_DEG_LAT = 111320;
    // ASCII Unit Separator (0x1F): can't occur in coords or venue names. Written as
    // an escape, NOT a raw byte — a literal control char in the source makes the file
    // read as "binary" and silently invisible to grep -I (which once hid a stale call).
    const VENUE_SEP = '\x1f';

    // Profiler span ending at `name`, starting at the previous span mark.
    // No-op unless a FilterProfiler session is active (see filterPanelUI.js).
    let _fpLast = null;
    function _fpSpan(name) {
        const FP = (typeof window !== 'undefined' && window.FilterProfiler) || null;
        if (!FP || !FP._active) return;
        FP.mark(name);
        if (_fpLast && !name.endsWith(':start')) FP.measure(name, _fpLast, name);
        _fpLast = name;
    }

    function venueIdentity(id, name) {
        return id != null ? `id:${id}` : `name:${name || ''}`;
    }

    function venueOffsetKey(lat, lng, identity) {
        return `${lat},${lng}${VENUE_SEP}${identity}`;
    }

    /** Grouping key of an event's venue at its export coordinate. */
    function eventVenueKey(event) {
        return event.venueKey ?? venueOffsetKey(event.origLat, event.origLng,
            venueIdentity(event.place_id, event.location));
    }

    /**
     * Groups events by venue (export coordinate + identity), in first-event
     * order. The final Phase-2 rebuild then formats coordinates and resolves
     * metadata once per venue (~5k) instead of several times per event (~35k);
     * that per-event string work dominated the blocking end-of-load task.
     */
    function collectVenues(events) {
        const venues = new Map();
        for (const event of events) addVenue(venues, event);
        return venues;
    }

    function addVenue(venues, event) {
        const key = eventVenueKey(event);
        if (venues.has(key)) return;
        venues.set(key, { key, origLat: event.origLat, origLng: event.origLng,
            identity: venueIdentity(event.place_id, event.location),
            placeId: event.place_id, name: event.location,
            lat: event.origLat, lng: event.origLng, locationKey: null });
    }

    /** Sets each venue's display point from the offsets (one shared key string per venue). */
    function placeVenues(venues, offsets) {
        for (const venue of venues.values()) {
            const off = offsets.get(venue.key);
            venue.lat = off ? off.lat : venue.origLat;
            venue.lng = off ? off.lng : venue.origLng;
            venue.locationKey = `${venue.lat},${venue.lng}`;
        }
        return venues;
    }

    /**
     * Recomputes per-venue coordinate offsets from the current event set.
     * A coordinate is perturbed only when 2+ distinct venues have events there.
     * Stores venueOffsetKey(origLat, origLng, identity) -> { lat, lng }.
     */
    function computeCoordOffsets(state, venues = collectVenues(state.allEvents || [])) {
        const identitiesByCoord = new Map(); // "lat,lng" -> [venue identity]
        for (const venue of venues.values()) {
            const coordKey = `${venue.origLat},${venue.origLng}`;
            const identities = identitiesByCoord.get(coordKey);
            // Venue keys are unique per (coordinate, identity): no duplicates here.
            if (identities) identities.push(venue.identity);
            else identitiesByCoord.set(coordKey, [venue.identity]);
        }

        const offsets = new Map();
        for (const [coordKey, identityList] of identitiesByCoord) {
            if (identityList.length < 2) continue; // no collision — leave it alone
            const identities = identityList.sort(); // order-independent layout
            const commaIdx = coordKey.indexOf(',');
            const baseLat = Number(coordKey.slice(0, commaIdx));
            const baseLng = Number(coordKey.slice(commaIdx + 1));
            const cosLat = Math.max(0.01, Math.cos(baseLat * Math.PI / 180));
            const radiusM = Math.max(JITTER_MIN_METERS, JITTER_PER_VENUE_METERS * identities.length);
            const n = identities.length;
            identities.forEach((identity, i) => {
                const angle = (2 * Math.PI * i) / n;
                const dLat = (radiusM * Math.sin(angle)) / METERS_PER_DEG_LAT;
                const dLng = (radiusM * Math.cos(angle)) / (METERS_PER_DEG_LAT * cosLat);
                offsets.set(venueOffsetKey(baseLat, baseLng, identity), {
                    lat: Number((baseLat + dLat).toFixed(7)),
                    lng: Number((baseLng + dLng).toFixed(7)),
                });
            });
        }
        state.coordOffsetByVenue = offsets;
    }

    /**
     * Resolve venue metadata by ID, then put it at the event's display point.
     * Coordinate-only joins confuse tenants in the same building. Legacy
     * events without place_id may use an unambiguous coord+name match; an
     * unknown ID never falls back to some other tenant's metadata.
     * @param {Map} [venues] - placed venues from collectVenues/placeVenues;
     *   derived from state.allEvents and the current offsets when omitted
     */
    function buildLocationsIndex(state, venues) {
        if (!venues) {
            venues = placeVenues(collectVenues(state.allEvents || []), state.coordOffsetByVenue || new Map());
        }
        const byKey = {};
        const byId = new Map();
        const legacyByKey = new Map();
        for (const location of (state.rawLocations || [])) {
            if (location.id != null) byId.set(String(location.id), location);
            if (location.lat == null || location.lng == null || !location.name) continue;
            const key = venueOffsetKey(location.lat, location.lng, location.name);
            // Preserve ambiguity: an address/name cannot distinguish these rows.
            legacyByKey.set(key, legacyByKey.has(key) ? null : location);
        }
        // Venues iterate in first-event order, so the first event's venue
        // still wins a shared display point.
        for (const venue of venues.values()) {
            const location = venue.placeId != null
                ? byId.get(String(venue.placeId))
                : legacyByKey.get(venueOffsetKey(venue.origLat, venue.origLng, venue.name));
            if (!location) continue;
            const key = venue.locationKey;
            if (!byKey[key]) byKey[key] = { ...location, lat: venue.lat, lng: venue.lng };
        }
        state.locationsByLatLng = byKey;
    }

    /**
     * Appends locations to the accumulated raw list, de-duped by ID so
     * distinct venues sharing a coordinate are all retained (the legacy
     * first-wins lookup dropped them, which is what hid colliding venues).
     */
    function addRawLocations(locationData, state) {
        if (!state.rawLocations) state.rawLocations = [];
        if (!state._rawLocationSeen) state._rawLocationSeen = new Set();
        for (const location of locationData) {
            if (location.lat == null || location.lng == null) continue;
            const dedupeKey = location.id != null ? `id:${location.id}`
                : venueOffsetKey(location.lat, location.lng, location.name);
            if (state._rawLocationSeen.has(dedupeKey)) continue;
            state._rawLocationSeen.add(dedupeKey);
            // Derive leaf-only display_tags client-side (was shipped inline).
            if (location.tags && !location.display_tags) {
                location.display_tags = filterToLeafTags(location.tags, state);
            }
            state.rawLocations.push(location);
        }
    }

    /**
     * Re-keys events and rebuilds the location index onto perturbed coordinates
     * wherever 2+ venues share an exact coordinate. Idempotent: always
     * derives from each event's ORIGINAL coordinate, so it is safe to re-run
     * after the Phase 2 merge brings in more venues.
     * @param {Object} state - Application state
     */
    function applyCoordPerturbation(state) {
        const venues = collectVenues(state.allEvents);
        computeCoordOffsets(state, venues);
        placeVenues(venues, state.coordOffsetByVenue);
        buildLocationsIndex(state, venues);
        for (const event of state.allEvents) placeEvent(event, venues.get(eventVenueKey(event)));
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
        tags = tags.filter(t => !state.formatOnlyTags?.has(t) && !state.neighborhoodTags?.has(t));
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
     * @returns {Object|null} Processed event or null if invalid
     */
    function transformRawEvent(rawEvent, state, config) {
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

        return {
            id,
            ...restOfEvent,
            section: restOfEvent.section || 'Events',
            emoji: restOfEvent.emoji,
            // origLat/origLng are the unmodified export coordinates; latitude/
            // longitude/locationKey may be re-keyed by applyCoordPerturbation
            // when this venue collides with another at the same coordinate.
            origLat: lat,
            origLng: lng,
            // Immutable venue grouping key, built here in the yielding transform
            // loop so the blocking re-key pass does not format it per event.
            venueKey: venueOffsetKey(lat, lng, venueIdentity(restOfEvent.place_id, restOfEvent.location)),
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
        state.allEvents = eventData
            .map(rawEvent => transformRawEvent(rawEvent, state, config))
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
        const newEvents = await transformNewEventsChunked(fullEventData, state, config, onProgress);
        // One re-key pass after the full merge so cross-chunk venue collisions
        // (a venue whose siblings only appear in a later chunk) are caught.
        await stageAndPublishEvents(state, newEvents);
    }

    /**
     * Merges new events as a staged replacement. Venue grouping, offsets, the
     * locations index, the new events' placement and a complete eventsById
     * are built across yields without touching live state (new events are not
     * reachable from it yet). One synchronous publish then appends them,
     * re-keys the few existing events whose venue moved and swaps every lookup.
     * INVARIANT: never await inside the publish block — input must never
     * observe state.allEvents ahead of eventsById/locationsByLatLng/keys.
     * @param {Object} state - Application state
     * @param {Array} newEvents - transformed events absent from state.allEvents
     */
    async function stageAndPublishEvents(state, newEvents) {
        const oldEvents = state.allEvents;
        const venues = new Map();
        await _forEachYielding(oldEvents, event => addVenue(venues, event));
        await _forEachYielding(newEvents, event => addVenue(venues, event));

        const staged = { rawLocations: state.rawLocations };
        _fpSpan('fp:p2:stage:start');
        computeCoordOffsets(staged, venues);
        placeVenues(venues, staged.coordOffsetByVenue);
        _fpSpan('fp:p2:stage:offsets');
        await _yieldToMain();
        _fpSpan('fp:p2:stage:start');
        buildLocationsIndex(staged, venues);
        _fpSpan('fp:p2:stage:locationsIndex');
        await _yieldToMain();

        const eventsById = {};
        await _forEachYielding(oldEvents, event => { eventsById[event.id] = event; });
        await _forEachYielding(newEvents, event => {
            placeEvent(event, venues.get(eventVenueKey(event)));
            eventsById[event.id] = event;
        });

        // ---- Publish: synchronous from here to the end of the function. ----
        // Phase-2 groups and background refreshes run sequentially, so
        // state.allEvents is still oldEvents here.
        _fpSpan('fp:p2:sync:start');
        for (const event of oldEvents) {
            const venue = venues.get(eventVenueKey(event));
            if (event.locationKey !== venue.locationKey) placeEvent(event, venue);
        }
        state.allEvents.push(...newEvents);
        state.coordOffsetByVenue = staged.coordOffsetByVenue;
        state.locationsByLatLng = staged.locationsByLatLng;
        state.eventsById = eventsById;
        _fpSpan('fp:p2:sync:publish');
    }

    /** Moves an event to its venue's display point. */
    function placeEvent(event, venue) {
        event.latitude = venue.lat;
        event.longitude = venue.lng;
        event.locationKey = venue.locationKey;
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
            // Optional 5th element: exporter's endpoint precision for spans whose
            // start/end the pipeline synthesized ({start:'as_of'} / {end:'open'}).
            const [startDateStr, startTimeStr, endDateStr, endTimeStr, precision] = occ;
            const start = Utils.parseDateInZone(startDateStr, startTimeStr);
            const effectiveEndDateStr = (endDateStr && endDateStr.trim() !== '') ? endDateStr : startDateStr;
            const effectiveEndTimeStr = (endTimeStr && endTimeStr.trim() !== '') ? endTimeStr : startTimeStr;
            const end = Utils.parseDateInZone(effectiveEndDateStr, effectiveEndTimeStr);

            let parsed = null;
            if (start && !end) {
                parsed = { start, end: new Date(start), originalStartTime: startTimeStr, originalEndTime: endTimeStr };
            } else if (start && end) {
                parsed = { start, end, originalStartTime: startTimeStr, originalEndTime: endTimeStr };
            }
            if (parsed && precision && typeof precision === 'object') parsed.precision = precision;
            return parsed;
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
        const startMs = Utils.dayStartMsInZone(Utils.calendarDayIndex(config.START_DATE));
        const endMs = Utils.dayStartMsInZone(Utils.calendarDayIndex(config.END_DATE) + 1) - 1;
        return occurrences.some(occ =>
            occ.start.getTime() <= endMs && occ.end.getTime() >= startMs
        );
    }

    /**
     * Appends new event data to existing events. Processes events in batches
     * of EVENT_PROCESS_CHUNK_SIZE and yields after about 8ms of processing
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

    /** Calls fn on each item, yielding to the main thread after ~8ms slices. */
    async function _forEachYielding(items, fn) {
        let sliceStart = performance.now();
        for (let i = 0; i < items.length; i++) {
            fn(items[i]);
            if ((i & 127) === 127 && performance.now() - sliceStart >= 8) {
                await _yieldToMain();
                sliceStart = performance.now();
            }
        }
    }

    // Check elapsed time every small batch; fixed large batches stalled slower CPUs.
    const EVENT_PROCESS_CHUNK_SIZE = 200;
    async function transformNewEventsChunked(newEventData, state, config, onProgress) {
        const total = newEventData.length;
        const newEvents = [];
        // Track ids seen across chunks (Phase 1's eventsById + this batch).
        // Multi-day events appear in every chunk they touch — dedup on id.
        const seen = new Set(Object.keys(state.eventsById || {}));

        let sliceStart = performance.now();
        for (let i = 0; i < total; i += EVENT_PROCESS_CHUNK_SIZE) {
            const end = Math.min(i + EVENT_PROCESS_CHUNK_SIZE, total);
            for (let j = i; j < end; j++) {
                const raw = newEventData[j];
                if (!raw || raw.id == null) continue;
                const idKey = String(raw.id);
                if (seen.has(idKey)) continue;
                seen.add(idKey);
                const ev = transformRawEvent(raw, state, config);
                if (ev) newEvents.push(ev);
            }
            if (onProgress) onProgress(end, total);
            if (end < total && performance.now() - sliceStart >= 8) {
                await _yieldToMain();
                sliceStart = performance.now();
            }
        }

        // Not appended here: stageAndPublishEvents publishes them together
        // with the lookups that cover them.
        return newEvents;
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
     * Append-only keying of events into eventsById. Phase 1 builds lookups via
     * rebuildEventLookups in applyCoordPerturbation; Phase 2 stages a complete
     * eventsById in stageAndPublishEvents instead.
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
     * after about 8ms, checking every SEARCH_INDEX_CHUNK_SIZE events. The synchronous version is kept
     * for callers that need to block (e.g. a search fired before the async
     * build completes).
     */
    const SEARCH_INDEX_CHUNK_SIZE = 100;
    async function buildSearchIndexAsync(state) {
        // Keep the previous complete index searchable across yields.
        const staging = { ...state };
        _initSearchIndexShell(staging);
        let sliceStart = performance.now();
        for (let i = 0; i < state.allEvents.length; i += SEARCH_INDEX_CHUNK_SIZE) {
            const end = Math.min(i + SEARCH_INDEX_CHUNK_SIZE, state.allEvents.length);
            for (let j = i; j < end; j++) {
                _indexEvent(staging, state.allEvents[j]);
            }
            if (end < state.allEvents.length && performance.now() - sliceStart >= 8) {
                await _yieldToMain();
                sliceStart = performance.now();
            }
        }
        const locationKeys = Object.keys(staging.locationsByLatLng);
        for (const key of locationKeys) {
            _indexLocation(staging, key, staging.locationsByLatLng[key]);
            if (performance.now() - sliceStart >= 8) {
                await _yieldToMain();
                sliceStart = performance.now();
            }
        }
        _indexTagsOrganizers(staging);
        state.searchIndex = staging.searchIndex;
    }

    function _initSearchIndexShell(state) {
        state.searchIndex = {
            events: new Map(),
            eventNames: new Map(),
            normalizedTags: new Map(),
            locations: new Map(),
            tags: new Map(),
            organizers: new Map(),
            eventDisplayNames: new Map()
        };
    }

    function _indexEvent(state, event) {
        const names = [event.name, event.short_name].filter(Boolean).map(Utils.normalizeForSearch);
        const searchableFields = [
            event.description, event.location, event.sublocation
        ].filter(Boolean);
        // Tags repeat across thousands of events; normalize each spelling once per index.
        const tagTerms = [...(event.tags || []), ...(event.keywords || [])].map(tag => {
            let term = state.searchIndex.normalizedTags.get(tag);
            if (term === undefined) {
                term = Utils.normalizeForSearch(tag);
                state.searchIndex.normalizedTags.set(tag, term);
            }
            return term;
        });
        const normalizedText = [...names, ...searchableFields.map(Utils.normalizeForSearch), ...tagTerms].join(' ');
        state.searchIndex.events.set(event.id, normalizedText);
        state.searchIndex.eventNames.set(event.id, names);
        const nameToDisplay = Utils.getDisplayName(event);
        const formatted = Utils.formatAndSanitize(nameToDisplay).replace(/<\/?em>/g, '');
        state.searchIndex.eventDisplayNames.set(event.id, formatted);
    }

    function _indexLocation(state, key, location) {
        const searchableFields = [location.name, location.short_name, ...(location.aliases || []), ...(location.tags || []).map(Utils.getTagDisplayName), ...(location.keywords || [])].filter(Boolean);
        const normalizedText = searchableFields.map(field => Utils.normalizeForSearch(field)).join(' ');
        state.searchIndex.locations.set(key, normalizedText);
    }

    function _indexTagsOrganizers(state) {
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
        for (const key of Object.keys(state.locationsByLatLng)) _indexLocation(state, key, state.locationsByLatLng[key]);
        _indexTagsOrganizers(state);
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
            const location = state.locationsByLatLng[event.locationKey];
            const combinedTags = Utils.eventFilterTags(event, location);

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
     * Staged, yielding equivalent of calculateTagFrequencies followed by
     * processTagHierarchy. The event scan accumulates into locals across
     * yields; tagFrequencies and the available-tag lists are then published
     * together in one synchronous step. Callers must not mutate allEvents or
     * locationsByLatLng meanwhile (Phase-2 groups and refreshes are sequential).
     * @param {Object} state - Application state
     * @param {Object} config - Application configuration
     */
    async function calculateTagStatsAsync(state, config) {
        const tagLocationSets = new Map(); // tag -> Set(locationKey)
        const unlocatedTags = new Set();   // available-tag candidates without a location
        await _yieldToMain();
        await _forEachYielding(state.allEvents, ({ tags, locationKey }) => {
            if (!tags || !Array.isArray(tags)) return;
            for (const tag of tags) {
                if (!locationKey) { unlocatedTags.add(tag); continue; }
                const set = tagLocationSets.get(tag);
                if (set) set.add(locationKey);
                else tagLocationSets.set(tag, new Set([locationKey]));
            }
        });

        // ---- Publish: synchronous from here. ----
        _fpSpan('fp:p2:tags:start');
        for (const locationKey in state.locationsByLatLng) {
            const tags = state.locationsByLatLng[locationKey].tags;
            if (!tags || !Array.isArray(tags)) continue;
            for (const tag of tags) {
                const set = tagLocationSets.get(tag);
                if (set) set.add(locationKey);
                else tagLocationSets.set(tag, new Set([locationKey]));
            }
        }
        const frequencies = {};
        for (const [tag, set] of tagLocationSets) frequencies[tag] = set.size;
        state.tagFrequencies = frequencies;
        const uniqueTags = new Set(tagLocationSets.keys());
        for (const tag of unlocatedTags) uniqueTags.add(tag);
        processTagHierarchy(state, config, uniqueTags);
        _fpSpan('fp:p2:tags:publish');
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
        const tagSearchTerms = {}; // normalized canonical names and aliases
        // Set of all curated tag names (tags NOT in this set are keywords)
        const hierarchyTagsSet = new Set();

        // Build parent/child maps from flat list
        tags.forEach(tag => {
            hierarchyTagsSet.add(tag.name);
            const displayName = tag.display_name || tag.name;
            const venueLabel = globalThis.__CITY__?.venueSelector?.labels?.[displayName];
            tagSearchTerms[tag.name] = [...new Set([tag.name, displayName, venueLabel, ...(tag.aliases || [])]
                .filter(Boolean).map(Utils.normalizeForSearch))];
            const emoji = tag.emoji;
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

        return { childrenOf, parentsOf, descendantsOf, hierarchyTagsSet, tagEmojiMap, tagSearchTerms,
            formats: data.formats || {}, formatOnlyTags: new Set(data.format_only_tags || []),
            tagRedirects: data.tag_redirects || {},
            neighborhoodTags: new Set(['Neighborhood', 'venue:Neighborhood', ...(descendantsOf.Neighborhood || []), ...(descendantsOf['venue:Neighborhood'] || [])]),
            tagIconMap: { ...(data.icon_ids || {}) } };
    }

    /**
     * Processes tag hierarchy and available tags
     * @param {Object} state - Application state
     * @param {Object} config - Application configuration
     * @param {Iterable<string>} [uniqueTags] - every event/location tag, when
     *   the caller already collected them (calculateTagStatsAsync)
     */
    function processTagHierarchy(state, config, uniqueTags) {
        state.tagColors = state.tagConfig.colors || {};
        const allUniqueTagsSet = new Set(uniqueTags);
        if (!uniqueTags) {
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
        }

        // Format-only nodes belong to the independent selector, not topic chips.
        // Retain the legacy structural-node fallback for older example payloads.
        // Refilled IN PLACE when the Set already exists: FilterPanelUI captures a
        // reference to it at init, and this runs again in Phase 2 and on every
        // background data refresh — reassigning would strand that reference.
        const formatChildren = (state.tagChildrenOf && state.tagChildrenOf['Format']) || [];
        if (state.structuralFormatTags instanceof Set) {
            state.structuralFormatTags.clear();
            state.structuralFormatTags.add('Format');
            formatChildren.forEach(tag => state.structuralFormatTags.add(tag));
            state.formatOnlyTags?.forEach(tag => state.structuralFormatTags.add(tag));
        } else {
            state.structuralFormatTags = new Set(['Format', ...formatChildren, ...(state.formatOnlyTags || [])]);
        }

        // Exclude keywords (tags not in the hierarchy) and structural Format nodes
        // from the browsable/selectable tag list.
        const hierarchyTagsSet = state.hierarchyTagsSet || new Set();
        state.allAvailableTags = Array.from(allUniqueTagsSet)
            .filter(tag => (hierarchyTagsSet.size === 0 || hierarchyTagsSet.has(tag))
                && !state.structuralFormatTags.has(tag) && !state.neighborhoodTags?.has(tag))
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
        transformRawEvent,
        parseOccurrences,
        processInitialData,
        processFullDataAsync,
        applyDescriptions,
        buildSearchIndex,
        buildSearchIndexAsync,
        buildTagIndex,
        calculateTagFrequencies,
        calculateTagStatsAsync,
        buildTagHierarchyMaps,
        processTagHierarchy,
        groupEventsByLatLngInDateRange,
        yieldToMain: _yieldToMain
    };
})();
