/* Assistant-facing data API. No language interpretation and no device sensors. */
const FomoQueries = (() => {
    const C = FomoQueryCore;
    let app, snapshot, catalog, loading, current = null, result = null, viewEvents = null;
    let revision = crypto.getRandomValues(new Uint32Array(1))[0], contextRevision = 0, generation = 0, rendering = false;
    const requests = new Map();
    const initialUrl = typeof location !== 'undefined' ? location.href : '';
    let initialQuery, initialError, lastContextSignature, initialRequestId;
    try { initialQuery = initialUrl ? C.decode(initialUrl) : null; } catch (e) { initialError = e.code; }
    const clone = C.copy;
    const sha = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
    async function load() {
        if (snapshot?.coverage.complete || (snapshot && current)) return snapshot;
        if (loading) return loading;
        loading = (async () => {
            const response = await fetch('data/query-manifest.json', { cache: 'no-cache' });
            if (!response.ok) C.fail('data_incomplete');
            const manifest = await response.json();
            if (manifest.version !== 1 || manifest.cityId !== window.__CITY__.cityId || !manifest.files) C.fail('snapshot_mismatch');
            const files = {}, missing = [];
            const queue = Object.entries(manifest.files);
            await Promise.all(Array.from({ length: 4 }, async () => {
                while (queue.length) {
                    const [name, hash] = queue.shift();
                    if (!/^(manifest|tag_hierarchy|organizers|events\.(day\d+|remainder\d*)|events\.(day\d+|remainder\d*)\.desc|locations\.(day\d+|remainder))\.json$/.test(name)) C.fail('snapshot_mismatch');
                    try {
                        const r = await fetch('data/' + name); if (!r.ok) throw Error();
                        const bytes = await r.arrayBuffer();
                        if (await sha(bytes) !== hash) throw Error('hash');
                        files[name] = JSON.parse(new TextDecoder().decode(bytes));
                    } catch (_) { missing.push(name); }
                }
            }));
            // Never declare a legacy/mixed/unverified snapshot complete.
            const required = ['manifest.json', 'tag_hierarchy.json', 'organizers.json'];
            if (required.some(n => !files[n])) C.fail('data_incomplete', '', { missing });
            const expected = files['manifest.json'];
            const chunks = [...(expected.days || []).map((_, i) => `day${i}`), ...(expected.remainderChunks || ['remainder'])];
            for (const chunk of chunks) for (const name of [`events.${chunk}.json`, `events.${chunk}.desc.json`, `locations.${chunk.startsWith('remainder') ? 'remainder' : chunk}.json`]) {
                if (!Object.hasOwn(manifest.files, name)) C.fail('snapshot_mismatch');
            }
            const events = new Map(), locations = new Map(), descriptions = {};
            for (const [name, records] of Object.entries(files)) {
                if (/^events\..+\.desc\.json$/.test(name)) Object.assign(descriptions, records);
                else if (name.startsWith('events.')) for (const e of records) events.set(String(e.id), e);
                else if (name.startsWith('locations.')) for (const l of records) locations.set(l.id || `${l.lat},${l.lng}|${l.name}`, l);
            }
            const catalogRevision = await sha(new TextEncoder().encode(JSON.stringify([manifest.revision, window.__CITY__.cityId, window.__CITY__.timezone, window.__CITY__.areaIds, window.__CITY__.neighborhoodSelector])));
            const loaded = { events: [...events.values()], locations: [...locations.values()], descriptions,
                descriptionsComplete: !missing.some(n => n.includes('.desc.')), hierarchy: files['tag_hierarchy.json'],
                organizers: files['organizers.json'], coverage: { complete: !missing.length, missing,
                    generatedAt: manifest.generatedAt, sourceExportedAt: manifest.sourceExportedAt || null, revision: catalogRevision, sourceRevision: manifest.revision, dates: expected.days },
                preferenceScore: (e, place) => DiscoveryRanking.score({ ...e, description: descriptions[e.id] }, place) };
            const loadedCatalog = C.catalog(loaded, window.__CITY__);
            snapshot = loaded; catalog = loadedCatalog;
            return snapshot;
        })().finally(() => { loading = null; });
        return loading;
    }
    function getContext() {
        const b = app?.state.map?.getBounds();
        const selectedKey = app?.state.selectedLocationKey;
        const selectedPlace = selectedKey && app.state.locationsByLatLng[selectedKey];
        const manualFilters = {
            dates: (app?.state.datePickerInstance?.selectedDates || []).map(d => URLParams.formatDate(d)),
            tags: Object.fromEntries(Object.entries(FilterPanelUI.getTagStates()).filter(([, s]) => s !== 'unselected')),
            formats: FormatSelector.selection(), regions: NeighborhoodSelector.selection(), text: app?.state.searchTerm || ''
        };
        const signature = JSON.stringify([selectedKey, DiscoveryRanking.revision(), manualFilters]);
        if (lastContextSignature !== undefined && signature !== lastContextSignature) contextRevision++;
        lastContextSignature = signature;
        return { schemaVersion: 1, cityId: window.__CITY__.cityId, eventTimezone: window.__CITY__.timezone,
            stateRevision: revision, contextRevision, catalogRevision: snapshot?.coverage.revision || null,
            query: current ? clone(current) : null,
            selectedPlace: selectedPlace ? { name: selectedPlace.name, id: selectedPlace.id ? String(selectedPlace.id).startsWith('place:') ? selectedPlace.id : `place:${selectedPlace.id}` : null } : null,
            manualFilters: current ? null : manualFilters,
            mapBounds: b ? { south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast() } : null,
            capabilities: { structuredSearch: true, nativeAssistantUI: !!window.webkit?.messageHandlers?.fomoAssistant,
                numericPrice: false, accessibilityEvidence: false, ticketInventory: false, transitRouting: false },
            limits: { pageSize: 50, catalogPageSize: 50, queryBytes: 32768 },
            coverage: snapshot?.coverage || { complete: false, status: 'not_loaded' } };
    }
    function page(items, input = {}, key = '') {
        const limit = input.limit ?? 25;
        if (!Number.isInteger(limit) || limit < 1 || limit > 50) C.fail('query_limit_exceeded');
        let offset = 0;
        if (input.cursor) {
            const [cursorKey, n] = input.cursor.split('~');
            if (cursorKey !== key || !/^\d+$/.test(n || '')) C.fail('stale_cursor');
            offset = Number(n);
        }
        return { items: items.slice(offset, offset + limit), total: items.length,
            cursor: offset + limit < items.length ? `${key}~${offset + limit}` : null };
    }
    function selectFields(record, fields) {
        if (fields === undefined) return record;
        if (!Array.isArray(fields) || fields.length > 20 || fields.some(f => !['id', 'kind', 'name', 'aliases', 'lat', 'lng', 'parents', 'members', 'tags', 'description', 'address', 'url'].includes(f))) C.fail('invalid_schema');
        return Object.fromEntries(Object.entries(record).filter(([k]) => ['id', 'error'].includes(k) || fields.includes(k)));
    }
    function evidence(item) {
        return { id: `event:${item.event.id}`, name: item.event.name, urls: item.event.urls,
            placeId: item.place?.id || null,
            occurrences: item.occurrences.map(o => ({ key: o.key, source: o.raw, start: o.start, end: o.end })),
            possibleOccurrences: item.possibleOccurrences.map(o => ({ key: o.key, source: o.raw, reason: o.invalid ? 'invalid_source_time' : 'missing_evidence' })) };
    }
    function publicResult(r, query, input = {}) {
        return { query: clone(query), ...page(r.definite.map(evidence), input, C.namedId('page', JSON.stringify(query) + snapshot.coverage.revision + r.preferenceRevision)),
            possible: page(r.possible.map(evidence), { limit: 50 }, C.namedId('possible', JSON.stringify(query))).items,
            possibleCount: r.possible.length, unknownCount: r.unknownCount,
            occurrenceCount: r.definite.reduce((n, e) => n + e.occurrences.length, 0), coverage: snapshot.coverage,
            preferenceRevision: r.preferenceRevision ?? DiscoveryRanking.revision(), stateRevision: revision, contextRevision };
    }
    async function evaluate(query, policy) {
        const errors = C.validate(query); if (errors.length) C.fail('invalid_schema', '', { errors });
        if (!['require_complete', 'allow_partial'].includes(policy)) C.fail('invalid_schema', '/coveragePolicy');
        await load();
        if (policy === 'require_complete' && !snapshot.coverage.complete) C.fail('data_incomplete', '', snapshot.coverage);
        const r = C.evaluate(query, snapshot, catalog);
        if (r.errors.length) C.fail('invalid_query', '', { errors: r.errors });
        r.preferenceRevision = DiscoveryRanking.revision();
        return r;
    }
    function currentViewEvents() {
        if (!current || !result) return null;
        if (viewEvents) return viewEvents;
        return viewEvents = result.definite.map((item, rank) => {
            const raw = item.event;
            const existing = app.state.eventsById[raw.id];
            const original = DataManager.transformRawEvent(raw, app.state, {
                ...app.config, START_DATE: new Date('1900-01-01'), END_DATE: new Date('2200-01-01') });
            if (!original) return null;
            if (existing && existing.origLat === raw.lat && existing.origLng === raw.lng) {
                original.latitude = existing.latitude; original.longitude = existing.longitude; original.locationKey = existing.locationKey;
            }
            return { ...original, description: snapshot.descriptions[raw.id] || '',
                matching_occurrences: DataManager.parseOccurrences(item.occurrences.map(o => o.raw)), queryRank: rank };
        }).filter(Boolean);
    }
    function label(p) {
        if (p.id) return (catalog?.records.get(p.id)?.name || p.id) + (p.kind === 'tag' && p.scope !== 'event' ? ` (${p.scope})` : '');
        if (p.kind === 'circle') return `Within ${(p.radiusMeters / 1000).toFixed(2)} km of ${p.center.latitude.toFixed(4)}, ${p.center.longitude.toFixed(4)}`;
        if (p.kind === 'bounds') return `Area ${p.south.toFixed(3)}, ${p.west.toFixed(3)} to ${p.north.toFixed(3)}, ${p.east.toFixed(3)}`;
        return `“${p.value}” (${p.fields.join(', ')})`;
    }
    function render() {
        let panel = document.getElementById('structured-search');
        if (!panel) {
            panel = document.createElement('section'); panel.id = 'structured-search'; panel.setAttribute('aria-label', 'Applied search');
            document.getElementById('filter-container').after(panel);
        }
        document.documentElement.classList.toggle('structured-query-active', !!current);
        panel.hidden = !current; panel.replaceChildren();
        if (!current) return;
        const status = document.createElement('p'); status.setAttribute('role', 'status');
        const count = result?.definite.length || 0;
        status.textContent = `${count} ${count === 1 ? 'event' : 'events'}${snapshot?.coverage.complete ? '' : ' · Partial data'}${result?.unknownCount ? ` · ${result.unknownCount} with unconfirmed details` : ''}`;
        panel.append(status);
        const button = (text, action) => { const b = document.createElement('button'); b.type = 'button'; b.className = 'tag-button'; b.textContent = text; b.onclick = action; panel.append(b); };
        const remove = fn => { const q = clone(current); fn(q); applyFromUI(q); };
        if (current.time.kind === 'windows') button(current.time.windows.map(w => {
            if (w.kind === 'date_range') return `${w.startDate} to before ${w.endDateExclusive}`;
            const f = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short', timeZone: w.timezone });
            return `${{ starts: 'Starting', overlaps: 'Happening', contained: 'Entirely between' }[w.relation]} ${f.format(new Date(w.start))} – ${f.format(new Date(w.endExclusive))}`;
        }).join(' OR ') + ' ×', () => remove(q => { q.time = { kind: 'all_published' }; }));
        current.groups.forEach((g, i) => button(g.anyOf.map(label).join(' OR ') + ' ×', () => remove(q => q.groups.splice(i, 1))));
        current.exclude.forEach((p, i) => button('Exclude ' + label(p) + ' ×', () => remove(q => q.exclude.splice(i, 1))));
        const sort = document.createElement('p'); sort.textContent = `${{ earliest: 'Soonest first', distance: 'Nearest first', personalized: 'Your interests first' }[current.sort.kind]} · Unconfirmed matches ${current.unknownPolicy === 'separate' ? 'listed separately' : 'excluded'}`; panel.append(sort);
        if (result?.possible.length) {
            const details = document.createElement('details'), summary = document.createElement('summary');
            summary.textContent = `${result.possible.length} possible matches — incomplete evidence`; details.append(summary);
            for (const item of result.possible.slice(0, 50)) {
                const a = document.createElement('a'); a.textContent = item.event.name; a.href = /^https?:\/\//i.test(item.event.urls?.[0] || '') ? item.event.urls[0] : '#';
                a.target = '_blank'; a.rel = 'noopener noreferrer'; details.append(a);
            }
            panel.append(details);
        }
        button('Share search', () => app.shareCurrentView());
        button('Use filters', () => { clear(); HistoryManager.push(); });
    }
    function showLinkError(error) {
        const panel = document.createElement('section'); panel.id = 'structured-search-error'; panel.className = 'structured-search-error';
        panel.setAttribute('role', 'alert');
        const text = document.createElement('p'); text.textContent = `This search link could not be opened (${error.code || 'data unavailable'}). The map has not applied it.`;
        const button = document.createElement('button'); button.className = 'tag-button'; button.textContent = 'Use map filters';
        button.onclick = () => { panel.remove(); const url = new URL(location.href); url.searchParams.delete('q'); url.searchParams.delete('qv'); history.replaceState(history.state, '', url); };
        panel.append(text, button); document.getElementById('filter-container').after(panel);
    }
    function showError(error) {
        ToastNotifier.showToast(`Search could not be applied: ${error.code || error.message || 'unavailable'}`, 'error', 6000);
    }
    function commit(query, r, history = true) {
        const before = { current, result, viewEvents, revision, searchTerm: app.state.searchTerm, input: app.elements.omniSearchInput.value };
        current = clone(query); result = r; viewEvents = null; revision++; rendering = true;
        try {
            app.state.searchTerm = ''; app.elements.omniSearchInput.value = '';
            // Include venues outside the app's initial date horizon in its map index.
            for (const item of r.definite) {
                if (!app.state.locationsByLatLng[`${item.event.lat},${item.event.lng}`] && item.place) app.state.locationsByLatLng[`${item.event.lat},${item.event.lng}`] = item.place;
            }
            render(); app.updateFilteredEventList();
            if (query.view === 'fit_matches' && r.definite.length) {
                const coords = r.definite.map(x => [x.event.lng, x.event.lat]).filter(c => c.every(Number.isFinite));
                if (coords.length) {
                    const bounds = new maplibregl.LngLatBounds(coords[0], coords[0]); coords.forEach(c => bounds.extend(c));
                    app.state.map.fitBounds(bounds, { padding: 70, maxZoom: 15, duration: 0 });
                }
            }
            if (history) { if (history === 'replace') HistoryManager.replace(); else HistoryManager.push(); }
            document.dispatchEvent(new CustomEvent('fomo:query-applied', { detail: getContext() }));
        } catch (error) {
            current = before.current; result = before.result; viewEvents = before.viewEvents; revision = before.revision;
            app.state.searchTerm = before.searchTerm; app.elements.omniSearchInput.value = before.input;
            render(); app.updateFilteredEventList();
            throw error;
        } finally { rendering = false; }
    }
    async function applyFromUI(query) {
        try {
            const ctx = getContext();
            await dispatch('apply_query', { query, requestId: crypto.randomUUID(), expectedStateRevision: ctx.stateRevision,
                expectedContextRevision: ctx.contextRevision, catalogRevision: ctx.catalogRevision, coveragePolicy: 'require_complete' });
        } catch (e) { showError(e); }
    }
    function clear() { current = null; result = null; viewEvents = null; revision++; generation++; render(); app.updateFilteredEventList(); }
    async function dispatch(method, input = {}, signal) {
        if (method === 'get_context') return getContext();
        if (method === 'get_current_results') return current ? publicResult(result, current, input) : { items: [], total: 0 };
        if (method === 'get_schema') return clone(FomoQuerySchema);
        if (method === 'get_generation_contract') return clone(FomoGenerationContract);
        if (method === 'validate_query') { await load(); return { errors: C.validate(input.query, catalog) }; }
        if (method === 'lookup_catalog' || method === 'get_catalog_records') {
            await load();
            if (method === 'get_catalog_records') {
                if (!Array.isArray(input.ids) || input.ids.length > 50) C.fail('query_limit_exceeded');
                return { records: input.ids.map(id => selectFields(catalog.records.get(id) || { id, error: 'unknown_reference' }, input.fields)) };
            }
            if (!['exact', 'prefix', 'tokens'].includes(input.match) || typeof input.text !== 'string' || input.text.length > 200
                || !Array.isArray(input.kinds) || !input.kinds.length || input.kinds.some(k => !['tag', 'region', 'place', 'organizer', 'event', 'format'].includes(k))) C.fail('invalid_schema');
            const term = C.normalize(input.text);
            const list = [...catalog.records.values()].filter(r => input.kinds.includes(r.kind)).filter(r => [r.name, ...(r.aliases || [])].some(name => {
                const n = C.normalize(name);
                return input.match === 'exact' ? n === term : input.match === 'prefix' ? n.startsWith(term) : term.split(' ').every(t => n.split(' ').includes(t));
            })).sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
            return { ...page(list.map(r => selectFields(r, input.fields)), input, C.namedId('catalog', JSON.stringify([input.kinds, input.text, input.match, snapshot.coverage.revision]))), catalogRevision: snapshot.coverage.revision };
        }
        if (method === 'get_events') {
            await load(); if (!Array.isArray(input.ids) || input.ids.length > 50) C.fail('query_limit_exceeded');
            return { events: input.ids.map(id => { const e = snapshot.events.find(e => `event:${e.id}` === id); return e ? { ...e, description: snapshot.descriptions[e.id] ?? null } : { id, error: 'unknown_reference' }; }) };
        }
        if (method === 'search_events') return publicResult(await evaluate(input.query, input.coveragePolicy), input.query, input);
        if (method === 'apply_query') {
            if (typeof input.requestId !== 'string' || !input.requestId.length || input.requestId.length > 100 || !Number.isInteger(input.expectedStateRevision)
                || !Number.isInteger(input.expectedContextRevision)) C.fail('invalid_schema');
            const payload = JSON.stringify(input), previous = requests.get(input.requestId);
            if (previous) { if (previous.payload !== payload) C.fail('request_id_conflict'); return previous.promise; }
            const token = ++generation;
            const check = () => {
                getContext();
                if (signal?.aborted) C.fail('cancelled');
                if (input.expectedStateRevision !== revision || token !== generation) C.fail('stale_state');
                if (input.expectedContextRevision !== contextRevision) C.fail('stale_context');
                if (input.catalogRevision !== snapshot?.coverage.revision) C.fail('stale_catalog');
            };
            const promise = (async () => { await load(); check(); const r = await evaluate(input.query, input.coveragePolicy); check(); commit(input.query, r, input.requestId === initialRequestId ? 'replace' : true); return publicResult(r, input.query); })();
            requests.set(input.requestId, { payload, promise });
            if (requests.size > 128) requests.delete(requests.keys().next().value);
            return promise;
        }
        if (method === 'make_link') {
            await load(); const errors = C.validate(input.query, catalog);
            if (errors.length) C.fail('invalid_query', '', { errors });
            return { url: C.encode(input.query, location.href) };
        }
        C.fail('unsupported_capability');
    }
    async function receive(message, signal) {
        try { return { ok: true, result: await dispatch(message.method, message.input, signal) }; }
        catch (e) { return { ok: false, error: { code: e.code || 'unavailable', path: e.path || '', details: e.details || {} } }; }
    }
    function init(application) {
        app = application;
        window.fomo = Object.freeze({ call: receive, schemaVersion: 1 });
        app.state.map.on('moveend', () => { if (!rendering) contextRevision++; });
        document.dispatchEvent(new CustomEvent('fomo:query-ready', { detail: getContext() }));
        FomoWebMCP.register(window.fomo).catch(() => {}); // Optional browser capability.
        // Optional native search entry; a webpage cannot invoke the model itself.
        const host = window.webkit?.messageHandlers?.fomoAssistant;
        if (host) {
            const b = document.createElement('button'); b.type = 'button'; b.textContent = 'Search & saved events'; b.setAttribute('role', 'menuitem');
            b.onclick = () => host.postMessage({ action: 'open' }); document.getElementById('logo-menu').append(b);
        }
        if (initialError) showLinkError({ code: initialError });
        if (initialQuery) load().then(async () => {
            const ctx = getContext();
            const response = await receive({ method: 'apply_query', input: { query: initialQuery, requestId: initialRequestId = crypto.randomUUID(),
                expectedStateRevision: ctx.stateRevision, expectedContextRevision: ctx.contextRevision, catalogRevision: ctx.catalogRevision, coveragePolicy: 'require_complete' } });
            if (!response.ok) showLinkError(response.error);
        }).catch(showLinkError);
    }
    return { init, dispatch, receive, getContext, load, currentViewEvents, active: () => !!current,
        query: () => current ? clone(current) : null, shareUrl: () => current ? C.encode(current, location.href) : null,
        invalidate: () => { if (!rendering) { revision++; generation++; } },
        restore: query => { if (!query) { if (current) clear(); return; } if (snapshot) { const r = C.evaluate(query, snapshot, catalog); if (!r.errors.length) commit(query, r, false); } },
        clear };
})();
