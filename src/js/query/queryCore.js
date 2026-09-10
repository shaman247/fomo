/* Structured predicates only. This module has no clock, location sensor or model. */
const FomoQueryCore = (() => {
    const copy = value => JSON.parse(JSON.stringify(value));
    const normalize = value => String(value || '').normalize('NFKC').toLowerCase()
        .replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
    const and = values => values.includes(false) ? false : values.includes(null) ? null : true;
    const or = values => values.includes(true) ? true : values.includes(null) ? null : false;
    const not = value => value === null ? null : !value;
    const problem = (code, path = '', details = {}) => ({ code, path, details });
    const fail = (code, path, details) => { throw Object.assign(new Error(code), problem(code, path, details)); };
    // Legacy name-derived identities are explicit and deterministic. New exports
    // supply DB identities; a stale legacy reference is rejected, never remapped.
    function namedId(kind, name) {
        let a = 2166136261, b = 5381;
        for (const ch of String(name)) {
            a = Math.imul(a ^ ch.codePointAt(0), 16777619);
            b = Math.imul(b, 33) ^ ch.codePointAt(0);
        }
        return `${kind}:n${(a >>> 0).toString(16)}${(b >>> 0).toString(16)}`;
    }
    function validDate(s) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
        const d = new Date(s + 'T00:00:00Z');
        return Number.isFinite(+d) && d.toISOString().slice(0, 10) === s;
    }
    const formatters = new Map();
    function parts(ms, zone) {
        if (!formatters.has(zone)) formatters.set(zone, new Intl.DateTimeFormat('en-CA', {
            timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
        }));
        const p = Object.fromEntries(formatters.get(zone).formatToParts(ms).map(p => [p.type, p.value]));
        return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
    }
    function validInstant(s, zone) {
        if (!validDate(s.slice(0, 10)) || !Number.isFinite(Date.parse(s))) return false;
        // Compare wall-clock components, not just Date.parse (which rolls invalid dates).
        return parts(Date.parse(s), zone) === s.slice(0, 19);
    }
    function shape(value, schema, path = '') {
        if (schema.$ref) schema = FomoQuerySchema.$defs[schema.$ref.split('/').pop()];
        if (schema.oneOf) return schema.oneOf.filter(s => shape(value, s, path).length === 0).length === 1
            ? [] : [problem('invalid_schema', path, { expected: 'one supported variant' })];
        if (Object.hasOwn(schema, 'const') && value !== schema.const) return [problem('invalid_schema', path)];
        if (schema.enum && !schema.enum.includes(value)) return [problem('invalid_schema', path)];
        const type = schema.type;
        if (type && (type === 'object' ? value === null || typeof value !== 'object' || Array.isArray(value)
            : type === 'array' ? !Array.isArray(value)
                : typeof value !== type || (type === 'number' && !Number.isFinite(value)))) return [problem('invalid_schema', path)];
        const errors = [];
        if (type === 'object') {
            for (const k of schema.required || []) if (!Object.hasOwn(value, k)) errors.push(problem('invalid_schema', path + '/' + k));
            for (const k of Object.keys(value)) {
                if (!Object.hasOwn(schema.properties, k)) errors.push(problem('invalid_schema', path + '/' + k));
                else errors.push(...shape(value[k], schema.properties[k], path + '/' + k));
            }
        }
        if (type === 'array') {
            if (value.length < schema.minItems || value.length > schema.maxItems) errors.push(problem('query_limit_exceeded', path));
            if (schema.uniqueItems && new Set(value.map(JSON.stringify)).size !== value.length) errors.push(problem('invalid_schema', path));
            value.slice(0, 128).forEach((v, i) => errors.push(...shape(v, schema.items, path + '/' + i)));
        }
        if (type === 'string' && (value.length < schema.minLength || value.length > schema.maxLength
            || (schema.pattern && !new RegExp(schema.pattern).test(value))
            || (schema.format === 'date' && !validDate(value))
            || (schema.format === 'date-time' && (!validDate(value.slice(0, 10)) || !Number.isFinite(Date.parse(value)))))) errors.push(problem('invalid_schema', path));
        if (type === 'number' && (value < schema.minimum || value > schema.maximum || value <= schema.exclusiveMinimum)) errors.push(problem('invalid_schema', path));
        return errors;
    }
    function validate(query, catalog) {
        try {
            if (new TextEncoder().encode(JSON.stringify(query)).length > 32768) return [problem('query_limit_exceeded')];
            const errors = shape(query, FomoQuerySchema);
            if (errors.length) return errors;
            if (catalog && query.cityId !== catalog.cityId) errors.push(problem('city_mismatch', '/cityId'));
            (query.time.windows || []).forEach((w, i) => {
                const p = `/time/windows/${i}`;
                try {
                    parts(0, w.timezone);
                    const a = w.kind === 'date_range' ? Date.parse(w.startDate) : Date.parse(w.start);
                    const b = w.kind === 'date_range' ? Date.parse(w.endDateExclusive) : Date.parse(w.endExclusive);
                    if (!(a < b)) errors.push(problem('invalid_date', p));
                    if (b - a > 366 * 86400000 + 3600000) errors.push(problem('query_limit_exceeded', p));
                    if (w.kind === 'instant_range' && (!validInstant(w.start, w.timezone) || !validInstant(w.endExclusive, w.timezone))) errors.push(problem('invalid_timezone_offset', p));
                } catch (_) { errors.push(problem('invalid_timezone_offset', p + '/timezone')); }
            });
            const check = (p, path) => {
                if (p.id && catalog && !catalog.records.has(p.id)) errors.push(problem('unknown_reference', path + '/id', { id: p.id }));
                if (p.kind === 'bounds' && p.south > p.north) errors.push(problem('invalid_bounds', path));
                if (p.kind === 'text' && !normalize(p.value)) errors.push(problem('invalid_schema', path + '/value'));
            };
            query.groups.forEach((g, i) => g.anyOf.forEach((p, j) => check(p, `/groups/${i}/anyOf/${j}`)));
            query.exclude.forEach((p, i) => check(p, `/exclude/${i}`));
            return errors;
        } catch (_) { return [problem('invalid_schema')]; }
    }
    function catalog(data, city) {
        const records = new Map(), ids = new Map(), children = new Map();
        const add = (kind, name, extra = {}, explicitId) => {
            const id = explicitId || namedId(kind, name);
            if (records.has(id) && records.get(id).name !== name) fail('identity_collision');
            records.set(id, { id, kind, name, ...extra });
            ids.set(`${kind}:${name}`, id);
            return id;
        };
        const hierarchy = data.hierarchy || {};
        const tagNames = new Set((hierarchy.tags || []).map(t => t.name));
        data.events.forEach(e => (e.tags || []).forEach(t => tagNames.add(t)));
        data.locations.forEach(e => (e.tags || []).forEach(t => tagNames.add(t)));
        for (const name of tagNames) add('tag', name, {}, hierarchy.tag_ids?.[name] ? `tag:${hierarchy.tag_ids[name]}` : undefined);
        for (const t of hierarchy.tags || []) {
            Object.assign(records.get(ids.get('tag:' + t.name)), { scope: t.scope || 'event', displayName: t.display_name || t.name, aliases: [t.display_name || t.name, ...(t.aliases || []), ...Object.entries(hierarchy.tag_redirects || {}).filter(([, target]) => target === t.name).map(([alias]) => alias)],
                parents: (t.parents || []).map(n => ids.get('tag:' + n)).filter(Boolean) });
            for (const parent of t.parents || []) {
                const list = children.get(parent) || new Set(); list.add(t.name); children.set(parent, list);
            }
        }
        const areaName = n => n.startsWith('venue:') ? n.slice(6) : n;
        const geographicChildren = new Map([...children].map(([p, c]) => [areaName(p), new Set([...c].map(areaName))]));
        const configured = city.neighborhoodSelector?.groups || {};
        const areaNames = new Set();
        const visit = (n, seen) => { if (seen.has(n)) return; seen.add(n); for (const c of geographicChildren.get(n) || []) visit(c, seen); };
        visit('Neighborhood', areaNames); // Structural taxonomy root, not city-specific geography.
        areaNames.delete('Neighborhood');
        for (const [parent, members] of Object.entries(configured)) {
            areaNames.add(parent); members.forEach(n => areaNames.add(n));
        }
        for (const name of areaNames) add('region', name, {}, city.areaIds?.[name] || (hierarchy.tag_ids?.[name] ? `area:${hierarchy.tag_ids[name]}` : namedId('area', name)));
        const areaChildren = new Map([...geographicChildren].map(([p, c]) => [p, new Set(c)]));
        const parents = new Map();
        for (const [p, members] of Object.entries(configured)) for (const c of members) parents.set(c, p);
        for (const [p, set] of areaChildren) for (const c of set) if (parents.has(c) && parents.get(c) !== p) set.delete(c);
        for (const [p, members] of Object.entries(configured)) {
            const set = areaChildren.get(p) || new Set(); members.forEach(c => set.add(c)); areaChildren.set(p, set);
        }
        const descendants = (name, kind) => {
            const seen = new Set();
            const walk = n => { if (seen.has(n)) return; seen.add(n); for (const c of (kind === 'region' ? areaChildren : children).get(n) || []) walk(c); };
            walk(name); return seen;
        };
        for (const name of areaNames) {
            const record = records.get(ids.get('region:' + name));
            record.members = [...(areaChildren.get(name) || [])].map(n => ids.get('region:' + n)).filter(Boolean);
            record.parents = [...areaChildren].filter(([, children]) => children.has(name)).map(([n]) => ids.get('region:' + n)).filter(Boolean);
            record.aliases = records.get(ids.get('tag:' + name))?.aliases || [];
        }
        const places = new Map();
        for (const l of data.locations) {
            const identity = l.id ? `place:${l.id}` : namedId('place', l.name + '|' + (l.address || ''));
            add('place', l.name, { ...l, id: identity, aliases: l.aliases || [], identitySource: l.id ? 'database' : 'legacy_name_address' }, identity);
            places.set(`${l.lat},${l.lng}|${l.name}`, records.get(identity));
        }
        for (const [id, o] of Object.entries(data.organizers || {})) add('organizer', o.name, o, `organizer:${id}`);
        for (const name of new Set([...Object.values(hierarchy.formats || {}).flat(), ...data.events.map(e => e.event_type || 'Other')])) add('format', name);
        for (const e of data.events) add('event', e.name, {}, `event:${e.id}`);
        return { cityId: city.cityId, timezone: city.timezone, records, ids, descendants, areaNames, places };
    }
    const timeCache = new Map();
    function localInstant(date, time, zone) {
        const key = `${date}|${time}|${zone}`;
        if (timeCache.has(key)) return timeCache.get(key);
        let result = null;
        const m = typeof time === 'string' && time.trim().match(/^(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*(am|pm)?$/i);
        if (validDate(date) && m) {
            let h = +m[1]; const min = +(m[2] || 0), sec = +(m[3] || 0);
            const meridiem = m[4]?.toLowerCase();
            if (min < 60 && sec < 60 && (meridiem ? h >= 1 && h <= 12 : h < 24)) {
                if (meridiem) h = h % 12 + (meridiem === 'pm' ? 12 : 0);
                const local = `${date}T${String(h).padStart(2, '0')}:${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
                const naive = Date.parse(local + 'Z'), candidates = new Set();
                for (const delta of [-36, 0, 36]) {
                    const probe = naive + delta * 3600000;
                    const offset = Date.parse(parts(probe, zone) + 'Z') - probe;
                    const ms = naive - offset;
                    if (parts(ms, zone) === local) candidates.add(ms);
                }
                if (candidates.size === 1) result = [...candidates][0]; // A source DST fold is unknown, not guessed.
            }
        }
        if (timeCache.size > 100000) timeCache.clear();
        timeCache.set(key, result); return result;
    }
    function occurrence(raw, zone) {
        const [date, time, endDate, endTime] = raw;
        const start = localInstant(date, time, zone);
        const end = localInstant(endDate || date, endTime, zone);
        return { raw, start, end, zone, invalid: !validDate(date) || (!!endDate && !validDate(endDate)) || (endDate && endDate < date) || (start !== null && end !== null && end < start), point: start !== null && start === end };
    }
    function timeMatch(o, time) {
        if (time.kind === 'all_published') return true;
        if (o.invalid) return null;
        return or(time.windows.map(w => {
            const [date, , endDate] = o.raw;
            if (w.kind === 'date_range') {
                // Exact intervals use query timezone, date-only source records use their documented source dates.
                const first = o.start === null ? date : parts(o.start, w.timezone).slice(0, 10);
                const last = o.end === null ? (endDate || first) : parts(o.point ? o.end : o.end - 1, w.timezone).slice(0, 10);
                return first < w.endDateExclusive && last >= w.startDate;
            }
            const a = Date.parse(w.start), b = Date.parse(w.endExclusive), s = o.start, e = o.end;
            // A known source date can rule out an exact start even when its clock time is absent.
            if (s === null && w.relation === 'starts' && o.zone) {
                const lo = localInstant(date, '00:00', o.zone);
                const next = new Date(Date.parse(date + 'T00:00:00Z') + 86400000).toISOString().slice(0, 10);
                const hi = localInstant(next, '00:00', o.zone);
                if (lo !== null && hi !== null && (hi <= a || lo >= b)) return false;
            }
            if (w.relation === 'starts') return s === null ? null : a <= s && s < b;
            if (o.point) return a <= s && s < b;
            if (w.relation === 'contained') {
                if ((s !== null && (s < a || s >= b)) || (e !== null && e > b)) return false;
                return s === null || e === null ? null : true;
            }
            if ((s !== null && s >= b) || (e !== null && e <= a)) return false;
            if (s !== null && s >= a && s < b) return true;
            return s === null || e === null ? null : s < b && e > a;
        }));
    }
    function distance(a, b) {
        const rad = x => x * Math.PI / 180;
        const h = Math.sin(rad(b.latitude - a.latitude) / 2) ** 2
            + Math.cos(rad(a.latitude)) * Math.cos(rad(b.latitude)) * Math.sin(rad(b.longitude - a.longitude) / 2) ** 2;
        return 6371008.8 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(Math.max(0, 1 - h)));
    }
    function evaluate(query, data, cat) {
        const errors = validate(query, cat); if (errors.length) return { errors };
        const definite = [], possible = []; let unknownCount = 0;
        const regionSets = new Map();
        function predicate(p, e, loc) {
            const record = p.id ? cat.records.get(p.id) : null;
            const orgs = (e.organizer_ids || []).map(id => data.organizers?.[id]).filter(Boolean);
            if (p.kind === 'event') return p.id === `event:${e.id}`;
            if (p.kind === 'place') return loc ? p.id === loc.id : null;
            if (p.kind === 'organizer') return (e.organizer_ids || []).some(id => p.id === `organizer:${id}`);
            if (p.kind === 'format') return (e.event_type || 'Other') === record.name;
            if (p.kind === 'tag') {
                const tags = p.scope === 'event' ? e.tags : p.scope === 'place' ? loc?.tags
                    : orgs.every(o => Array.isArray(o.tags)) ? orgs.flatMap(o => o.tags) : undefined;
                if (!Array.isArray(tags)) return null;
                const names = p.includeDescendants ? cat.descendants(record.name, 'tag') : new Set([record.name]);
                return tags.some(t => names.has(t));
            }
            if (p.kind === 'region') {
                if (!regionSets.has(p.id + p.includeDescendants)) regionSets.set(p.id + p.includeDescendants,
                    p.includeDescendants ? cat.descendants(record.name, 'region') : new Set([record.name]));
                const names = regionSets.get(p.id + p.includeDescendants);
                const geography = [...new Set([...(e.tags || []), ...(loc?.tags || [])].map(n => n.startsWith('venue:') ? n.slice(6) : n))].filter(n => cat.areaNames.has(n));
                const leaves = geography.filter(n => !geography.some(other => other !== n && cat.descendants(n, 'region').has(other)));
                return leaves.length ? leaves.some(n => names.has(n)) : null;
            }
            if (p.kind === 'circle' || p.kind === 'bounds') {
                if (!Number.isFinite(e.lat) || !Number.isFinite(e.lng)) return null;
                if (p.kind === 'circle') return distance(p.center, { latitude: e.lat, longitude: e.lng }) <= p.radiusMeters;
                return e.lat >= p.south && e.lat <= p.north && (p.west <= p.east ? e.lng >= p.west && e.lng <= p.east : e.lng >= p.west || e.lng <= p.east);
            }
            const values = { name: e.name, description: Object.hasOwn(data.descriptions, String(e.id)) ? data.descriptions[e.id] : data.descriptionsComplete ? '' : null,
                place_name: loc?.name || e.location, organizer_name: orgs.map(o => o.name).join(' ') };
            const texts = p.fields.map(f => values[f] == null ? null : ` ${normalize(values[f])} `);
            const needle = normalize(p.value);
            if (p.match === 'phrase') return or(texts.map(t => t === null ? null : t.includes(` ${needle} `)));
            return and(needle.split(' ').map(token => or(texts.map(t => t === null ? null : t.includes(` ${token} `)))));
        }
        for (const e of data.events) {
            const loc = (e.place_id && cat.records.get(`place:${e.place_id}`)) || cat.places.get(`${e.lat},${e.lng}|${e.location}`);
            const checks = query.groups.map(g => or(g.anyOf.map(p => predicate(p, e, loc))));
            checks.push(...query.exclude.map(p => not(predicate(p, e, loc))));
            const eligible = and(checks);
            if (eligible === false) continue;
            const matched = [], uncertain = [];
            const seen = new Set();
            for (const raw of e.occurrences || []) {
                const key = namedId('occurrence', e.id + '|' + JSON.stringify(raw) + '|' + cat.timezone);
                if (seen.has(key)) continue; seen.add(key);
                const o = occurrence(raw, cat.timezone);
                const result = and([eligible, timeMatch(o, query.time)]);
                if (result !== false) (result === true ? matched : uncertain).push({ key, ...o });
            }
            const chronological = (a, b) => ((a.start ?? Infinity) - (b.start ?? Infinity)) || a.key.localeCompare(b.key);
            matched.sort(chronological); uncertain.sort(chronological);
            if (uncertain.length) unknownCount++;
            const item = { event: e, place: loc, occurrences: matched, possibleOccurrences: uncertain };
            if (matched.length) definite.push(item);
            else if (uncertain.length && query.unknownPolicy === 'separate') possible.push(item);
        }
        const score = item => query.sort.kind === 'distance' ? (Number.isFinite(item.event.lat) && Number.isFinite(item.event.lng)
            ? distance(query.sort.origin, { latitude: item.event.lat, longitude: item.event.lng }) : Infinity)
            : query.sort.kind === 'personalized' ? -(data.preferenceScore?.(item.event, item.place) || 0)
                : Math.min(...(item.occurrences.length ? item.occurrences : item.possibleOccurrences).map(o => o.start ?? Infinity));
        const sort = (a, b) => (score(a) - score(b) || String(a.event.id).localeCompare(String(b.event.id)));
        definite.sort(sort); possible.sort(sort);
        return { definite, possible, unknownCount, errors: [] };
    }
    function encode(query, base) {
        if (validate(query).length) fail('invalid_schema');
        const bytes = new TextEncoder().encode(JSON.stringify(query));
        const value = btoa(Array.from(bytes, b => String.fromCharCode(b)).join('')).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
        const url = new URL(base); url.search = ''; url.hash = ''; url.searchParams.set('qv', '1'); url.searchParams.set('q', value);
        if (url.href.length > 8192) fail('link_too_large'); return url.href;
    }
    function decode(url) {
        const u = new URL(url); if (!u.searchParams.has('qv') && !u.searchParams.has('q')) return null;
        if (u.href.length > 8192 || u.searchParams.getAll('qv').length !== 1 || u.searchParams.get('qv') !== '1' || u.searchParams.getAll('q').length !== 1) fail('invalid_schema');
        try {
            const raw = u.searchParams.get('q'); if (!/^[A-Za-z0-9_-]+$/.test(raw)) fail('invalid_schema');
            const text = atob(raw.replace(/-/g, '+').replace(/_/g, '/'));
            const query = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Uint8Array.from(text, c => c.charCodeAt(0))));
            const errors = validate(query); if (errors.length) fail('invalid_schema', '', { errors }); return query;
        } catch (_) { fail('invalid_schema'); }
    }
    return { copy, normalize, and, or, not, namedId, validDate, parts, validate, catalog, occurrence, timeMatch, distance, evaluate, encode, decode, problem, fail };
})();
