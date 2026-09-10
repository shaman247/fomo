/** Explicit, on-device preferences and a small, inspectable discovery baseline. */
const DiscoveryRanking = (() => {
    const storageKey = `fomo.interests.v1:${window.__CITY__?.domain || location.host}`;
    const types = new Set(['place', 'event', 'tag', 'term']);
    const normalize = value => String(value || '').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
    let entries = [];
    let revision = 0;
    let cache = new WeakMap();
    const baselineCache = new WeakMap();
    const normalizedTags = new Map();
    const appealGroups = [
        ['festival', 'street fair'],
        ['concert', 'live music', 'performance', 'theater', 'comedy', 'screening'],
        ['exhibition', 'art opening'],
        ['free', 'free admission']
    ];
    let storageAvailable = true;
    const indexes = { event: new Map(), place: new Map(), tag: new Map(), term: new Map() };

    function placeKey(place) {
        // Exports currently omit database venue IDs. Use name + street address,
        // never the display coordinates (which change for co-located venues).
        return `${normalize(place?.name)}|${normalize(place?.address)}`;
    }

    function clean(entry) {
        if (!entry || !types.has(entry.type) || ![1, -1].includes(entry.stance)) return null;
        const id = String(entry.id || '').slice(0, 500);
        const label = String(entry.label || '').trim().slice(0, 250);
        if (!id || !label) return null;
        const key = ['tag', 'term'].includes(entry.type) ? normalize(id) : id;
        if (!key) return null;
        return { type: entry.type, id: key,
            label, stance: entry.stance };
    }

    function reindex() {
        Object.values(indexes).forEach(index => index.clear());
        entries.forEach(e => indexes[e.type].set(e.id, e));
        revision++;
        cache = new WeakMap();
        if (typeof SimilarityModel !== 'undefined') SimilarityModel.setPreferences(entries);
    }

    function load() {
        try {
            const stored = JSON.parse(localStorage.getItem(storageKey) || '[]');
            const unique = new Map();
            if (Array.isArray(stored)) stored.slice(0, 200).forEach(raw => {
                const e = clean(raw);
                if (e) unique.set(`${e.type}:${e.id}`, e);
            });
            entries = [...unique.values()];
        } catch (_) { entries = []; }
        reindex();
    }

    function publish() {
        reindex();
        try { localStorage.setItem(storageKey, JSON.stringify(entries)); storageAvailable = true; }
        catch (_) { storageAvailable = false; }
        document.dispatchEvent(new CustomEvent('fomo:preferences-changed'));
    }

    function set(type, id, label, stance) {
        const e = clean({ type, id, label, stance });
        if (!e) return false;
        const index = entries.findIndex(old => old.type === e.type && old.id === e.id);
        if (index < 0 && entries.length >= 200) return false;
        if (index < 0) entries.push(e); else entries[index] = e;
        publish();
        return true;
    }

    function migrateTagAliases(redirects) {
        const mapping = new Map(Object.entries(redirects || {}).map(([a, b]) => [normalize(a), b]));
        const unique = new Map();
        let changed = false;
        // Existing canonical preferences win if old and new names disagree.
        const sorted = [...entries].sort((a, b) => Number(!mapping.has(a.id)) - Number(!mapping.has(b.id)));
        for (const entry of sorted) {
            const target = entry.type === 'tag' && mapping.get(entry.id);
            const next = target ? clean({ ...entry, id: target, label: target }) : entry;
            changed ||= !!target && (next.id !== entry.id || next.label !== entry.label);
            unique.set(`${next.type}:${next.id}`, next);
        }
        if (changed) { entries = [...unique.values()]; publish(); }
    }

    function remove(type, id) {
        entries = entries.filter(e => !(e.type === type && e.id === id));
        publish();
    }

    function renameTerm(id, label) {
        const old = indexes.term.get(id);
        const next = old && clean({ ...old, id: label, label });
        if (!next) return false;
        entries = entries.filter(e => e.type !== 'term' || (e.id !== id && e.id !== next.id));
        entries.push(next); publish(); return true;
    }

    function baseline(event) {
        if (baselineCache.has(event)) return baselineCache.get(event);
        const tags = new Set((event.tags || []).map(tag => {
            if (!normalizedTags.has(tag)) normalizedTags.set(tag, normalize(tag));
            return normalizedTags.get(tag);
        }));
        // These are broad-appeal hypotheses, not measured popularity. Groups
        // cap correlated tags so Music + Concert + Live Music doesn't triple count.
        let appeal = appealGroups.reduce((n, group) => n + Number(group.some(t => tags.has(t))), 0);
        const hosts = new Set();
        for (const url of event.urls || []) {
            try { hosts.add(new URL(url).hostname.replace(/^www\./, '')); } catch (_) {}
        }
        appeal += Math.min(2, Math.max(0, hosts.size - 1));
        baselineCache.set(event, appeal);
        return appeal;
    }

    function details(event, place) {
        const pk = placeKey(place);
        const cached = cache.get(event);
        if (cached && cached.pk === pk && cached.description === event.description) return cached.value;
        const matches = [];
        const add = entry => { if (entry) matches.push(entry); };
        add(indexes.event.get(String(event.id)));
        add(indexes.place.get(pk));
        // Audience/topic tags come from the event. Do not inherit a venue's
        // audience (a library can host both children's and adult programming).
        if (indexes.tag.size) new Set([...(event.tags || []), ...(place?.tags || []).filter(tag => tag.startsWith('venue:'))].map(normalize)).forEach(tag => add(indexes.tag.get(tag)));
        if (indexes.term.size) {
            const fields = [event.name, event.description, event.location, ...(event.tags || []), ...(event.keywords || [])]
                .filter(Boolean).map(s => ` ${normalize(s)} `);
            indexes.term.forEach((entry, term) => {
                if (fields.some(field => field.includes(` ${term} `))) add(entry);
            });
        }
        const personal = matches.reduce((sum, e) => sum + e.stance, 0);
        const appeal = baseline(event);
        const similarity = typeof SimilarityModel !== 'undefined' ? SimilarityModel.score(event) : 0;
        const value = { personal, appeal, similarity, score: personal * 100 + similarity * 20 + appeal, matches };
        cache.set(event, { pk, description: event.description, value });
        return value;
    }

    function score(event, place) { return details(event, place).score; }

    function topPlaces(candidates, limit, pinned = []) {
        const sorted = [...candidates].sort((a, b) => b.score - a.score || (a.distance || 0) - (b.distance || 0) || a.key.localeCompare(b.key));
        const eligible = new Set(sorted.map(c => c.key));
        const chosen = new Set(pinned.filter(key => eligible.has(key)).slice(0, limit));
        for (const c of sorted) { if (chosen.size >= limit) break; chosen.add(c.key); }
        return chosen;
    }

    load();
    document.addEventListener?.('fomo:similarity-changed', () => {
        // Model loads invalidate marker/list ordering without rewriting preferences.
        revision++;
        cache = new WeakMap();
        document.dispatchEvent(new CustomEvent('fomo:preferences-changed'));
    });
    window.addEventListener('storage', e => {
        if (e.key === storageKey || e.key === null) {
            load();
            document.dispatchEvent(new CustomEvent('fomo:preferences-changed'));
        }
    });
    return { normalize, placeKey, set, migrateTagAliases, remove, renameTerm, details, score, baseline, topPlaces,
        entries: () => entries.map(e => ({ ...e })), revision: () => revision,
        canPersist: () => storageAvailable,
        stance: (type, id) => indexes[type]?.get(['tag', 'term'].includes(type) ? normalize(id) : String(id))?.stance || 0 };
})();
