/** Offline-trained content vectors. Explicit interests remain on this device. */
const SimilarityModel = (() => {
    const base = 'data/similarity/';
    let dimensions = 0, manifest = null, loading = null, loaded = false;
    let preferences = [], positive = null, negative = null, positiveCount = 0, negativeCount = 0;
    let version = 0;
    let fallback = new WeakMap();
    const vectors = { event: new Map(), place: new Map(), tag: new Map() };
    const support = { event: new Map(), place: new Map(), tag: new Map() };
    const pendingHistory = new Map();
    let activeLoading = null;
    const completedActive = new Set();
    const normalize = value => String(value || '').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
    const pause = () => new Promise(resolve => setTimeout(resolve, 0));

    function dot(a, b) {
        if (!a || !b) return 0;
        let result = 0;
        for (let i = 0; i < a.length; i++) result += a[i] * b[i];
        return Math.max(-1, Math.min(1, result));
    }

    function unit(v) {
        const norm = Math.hypot(...v);
        if (norm) for (let i = 0; i < v.length; i++) v[i] /= norm;
        return v;
    }

    async function fetchJSON(url, cache = 'default') {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 20000);
        try {
            const response = await fetch(url, { cache, signal: controller.signal });
            if (!response.ok) throw new Error(`Similarity data: ${response.status}`);
            return await response.json();
        } finally { clearTimeout(timer); }
    }

    async function decode(block, size) {
        if (!block || !Array.isArray(block.ids) || typeof block.vectors !== 'string') throw Error('Invalid vectors');
        const bytes = atob(block.vectors);
        if (bytes.length !== block.ids.length * size) throw Error('Invalid vector dimensions');
        const result = new Map();
        for (let row = 0; row < block.ids.length; row++) {
            if (row && row % 1024 === 0) await pause();
            const vector = new Float32Array(size);
            for (let j = 0; j < size; j++) {
                const byte = bytes.charCodeAt(row * size + j);
                vector[j] = (byte > 127 ? byte - 256 : byte) / 127;
            }
            result.set(String(block.ids[row]), unit(vector));
        }
        return result;
    }

    function rebuildProfile() {
        positive = new Float32Array(dimensions); negative = new Float32Array(dimensions);
        positiveCount = 0;
        negativeCount = 0;
        for (const entry of preferences) {
            const vector = vectors[entry.type]?.get(entry.id);
            if (!vector) continue;
            const target = entry.stance === 1 ? positive : negative;
            if (entry.stance === 1) positiveCount++;
            else negativeCount++;
            for (let i = 0; i < dimensions; i++) target[i] += vector[i];
        }
        unit(positive); unit(negative);
        version++;
        fallback = new WeakMap();
    }

    function changed() {
        rebuildProfile();
        document.dispatchEvent(new CustomEvent('fomo:similarity-changed'));
    }

    async function loadHistory() {
        if (!loaded) return;
        const available = new Set(manifest.historyShards || []);
        const shards = new Set(preferences.filter(e => e.type === 'event' && !vectors.event.has(e.id) && /^\d+$/.test(e.id))
            .map(e => Math.floor(Number(e.id) / 2048)).filter(id => available.has(id)));
        await Promise.all([...shards].map(async shard => {
            if (pendingHistory.has(shard)) return pendingHistory.get(shard);
            const promise = (async () => {
                try {
                    const block = await fetchJSON(`${base}${manifest.generation}/events-${shard}.json`);
                    const decoded = await decode(block, dimensions);
                    decoded.forEach((v, id) => vectors.event.set(id, v));
                    changed();
                } catch (_) { pendingHistory.delete(shard); }
            })();
            pendingHistory.set(shard, promise);
            return promise;
        }));
    }

    function loadActive() {
        if (!loaded || activeLoading) return activeLoading;
        const remaining = (manifest.activeShards || []).filter(id => !completedActive.has(id));
        if (!remaining.length) return Promise.resolve();
        activeLoading = (async () => {
            let updated = false;
            // Bound parallel downloads and decode work. This starts after core
            // suggestions and tag-based fallback ranking are already available.
            const worker = async () => {
                while (remaining.length) {
                    const shard = remaining.shift();
                    try {
                        const block = await fetchJSON(`${base}${manifest.generation}/active-${shard}.json`);
                        const decoded = await decode(block, dimensions);
                        decoded.forEach((v, id) => vectors.event.set(id, v));
                        completedActive.add(shard); updated = true;
                    } catch (_) { /* Retry missing chunks on the next profile edit. */ }
                }
            };
            await Promise.all([worker(), worker()]);
            if (updated) changed();
        })().finally(() => { activeLoading = null; });
        return activeLoading;
    }

    async function load() {
        if (loaded) return true;
        if (loading) return loading;
        loading = (async () => {
            try {
                const next = await fetchJSON(`${base}manifest.json`, 'no-cache');
                if (next.schemaVersion !== 1 || !/^[a-f0-9]{16}$/.test(next.generation)
                    || !Number.isInteger(next.dimensions) || next.dimensions < 2 || next.dimensions > 256) return false;
                const core = await fetchJSON(`${base}${next.generation}/core.json`);
                if (core.schemaVersion !== 1 || core.dimensions !== next.dimensions || core.domain !== next.domain) return false;
                if (window.__CITY__?.domain && core.domain !== window.__CITY__.domain) return false;
                // Decode into temporary maps. An incomplete generation never installs.
                const decoded = {};
                for (const type of ['event', 'place', 'tag']) decoded[type] = await decode(core.blocks[type], next.dimensions);
                dimensions = next.dimensions; manifest = next;
                for (const type of ['event', 'place', 'tag']) {
                    vectors[type] = decoded[type];
                    core.blocks[type].ids.forEach((id, i) => support[type].set(String(id), core.blocks[type].support?.[i] ?? 1));
                }
                loaded = true;
                changed();
                void loadHistory();
                if (preferences.some(e => e.type !== 'term')) void loadActive();
                return true;
            } catch (_) { return false; }
            finally { loading = null; }
        })();
        return loading;
    }

    function setPreferences(entries) {
        preferences = entries;
        rebuildProfile();
        if (entries.some(e => e.type !== 'term')) {
            if (loaded) { void loadHistory(); void loadActive(); }
            else void load();
        }
    }

    function eventVector(event) {
        const known = vectors.event.get(String(event.id));
        if (known) return known;
        const cached = fallback.get(event);
        if (cached) return cached;
        const result = new Float32Array(dimensions);
        // A new event uses its own tags. Venue audience never becomes event audience.
        for (const tag of new Set((event.tags || []).map(normalize))) {
            const vector = vectors.tag.get(tag);
            if (!vector) continue;
            const weight = 1 / Math.log2(2 + (support.tag.get(tag) || 1));
            for (let i = 0; i < dimensions; i++) result[i] += vector[i] * weight;
        }
        unit(result); fallback.set(event, result);
        return result;
    }

    function affinity(vector) {
        return Math.max(0, dot(vector, positive)) - Math.max(0, dot(vector, negative));
    }

    function score(event) { return loaded && (positiveCount || negativeCount) ? affinity(eventVector(event)) : 0; }

    async function suggest(type, items, limit = 6) {
        if (!loaded || !vectors[type]) return [];
        const selected = new Set(preferences.filter(e => e.type === type).map(e => e.id));
        const candidates = [];
        const seen = new Set();
        for (let index = 0; index < items.length; index++) {
            if (index && index % 300 === 0) await pause();
            const item = items[index];
            const id = type === 'tag' ? normalize(item) : type === 'place'
                ? `${normalize(item.name)}|${normalize(item.address)}` : String(item.id);
            if (selected.has(id) || seen.has(id)) continue;
            seen.add(id);
            if (type === 'place' && support.place.get(id) === 0) continue;
            const vector = type === 'event' ? eventVector(item) : vectors[type].get(id);
            if (!vector || !vector.some(v => v !== 0)) continue;
            const personal = affinity(vector);
            if ((positiveCount && personal < .12) || (!positiveCount && personal < -.1)) continue;
            const coverage = Math.log1p(support[type].get(id) || 1);
            candidates.push({ id, label: type === 'tag' ? item : item.name,
                context: type === 'place' ? item.address : type === 'event' ? item.location : '',
                emoji: item.emoji, vector, score: positiveCount ? personal : coverage * .025 });
        }
        candidates.sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
        const pool = candidates.slice(0, 120), chosen = [];
        while (chosen.length < limit && pool.length) {
            let best = 0, bestScore = -Infinity;
            pool.forEach((candidate, index) => {
                const redundancy = chosen.reduce((max, old) => Math.max(max, dot(old.vector, candidate.vector)), 0);
                const value = candidate.score - .25 * redundancy;
                if (value > bestScore) { best = index; bestScore = value; }
            });
            chosen.push(pool.splice(best, 1)[0]);
        }
        return chosen.map(({ vector, ...item }) => item);
    }

    return { load, setPreferences, score, suggest, ready: () => loaded, revision: () => version };
})();
