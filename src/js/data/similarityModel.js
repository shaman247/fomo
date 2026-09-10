/** Offline-trained content vectors. Explicit interests remain on this device. */
const SimilarityModel = (() => {
    const base = 'data/similarity/';
    let dimensions = 0, manifest = null, loading = null, loaded = false;
    let preferences = [], positive = null, negative = null, positiveCount = 0, negativeCount = 0;
    let version = 0;
    let fallback = new WeakMap();
    let preparedScores = new WeakMap(), scoreQueue = new Map(), scoring = false;
    let profileEpoch = 0;
    let thresholds = { positive: .35, negative: .55 };
    const vectorPool = new Map(), constituentSets = new WeakMap();
    const vectors = { event: new Map(), place: new Map(), tag: new Map() };
    const support = { event: new Map(), place: new Map(), tag: new Map() };
    const pendingHistory = new Map();
    let activeLoading = null;
    const completedActive = new Set();
    const aggregateShards = { place: new Map(), tag: new Map() };
    const pendingAggregates = new Map(), completedAggregates = new Set();
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
        if (block.ids.some(id => typeof id !== 'string') || new Set(block.ids).size !== block.ids.length)
            throw Error('Invalid vector IDs');
        if (block.support !== undefined && (!Array.isArray(block.support) || block.support.length !== block.ids.length
            || block.support.some(n => !Number.isInteger(n) || n < 0))) throw Error('Invalid support counts');
        const bytes = atob(block.vectors);
        const offsets = block.offsets ?? block.ids.map((_, i) => i).concat(block.ids.length);
        if (!Array.isArray(offsets) || offsets.length !== block.ids.length + 1 || offsets[0] !== 0
            || offsets.some((n, i) => !Number.isSafeInteger(n) || n < 0 || (i && n < offsets[i - 1]))
            || bytes.length !== offsets[offsets.length - 1] * size) throw Error('Invalid vector dimensions');
        const result = new Map();
        for (let row = 0; row < block.ids.length; row++) {
            const parts = [];
            for (let part = offsets[row]; part < offsets[row + 1]; part++) {
                if (part && part % 1024 === 0) await pause();
                const signature = bytes.slice(part * size, (part + 1) * size);
                let vector = vectorPool.get(signature);
                if (!vector) {
                    vector = new Float32Array(size);
                    for (let j = 0; j < size; j++) {
                        const byte = signature.charCodeAt(j);
                        vector[j] = (byte > 127 ? byte - 256 : byte) / 127;
                    }
                    unit(vector); vectorPool.set(signature, vector);
                }
                if (vector.some(v => v !== 0)) parts.push(vector);
            }
            result.set(String(block.ids[row]), parts);
        }
        return result;
    }

    function rebuildProfile() {
        positive = []; negative = [];
        positiveCount = 0;
        negativeCount = 0;
        for (const entry of preferences) {
            const vector = vectors[entry.type]?.get(entry.id);
            if (!vector?.length) continue;
            const target = entry.stance === 1 ? positive : negative;
            if (entry.stance === 1) positiveCount++;
            else negativeCount++;
            target.push(...vector);
        }
        // Parent and child preferences can share many exact constituents.
        const unique = parts => [...new Set(parts)];
        positive = unique(positive); negative = unique(negative);
        version++;
        fallback = new WeakMap();
        preparedScores = new WeakMap(); scoreQueue.clear();
        profileEpoch++;
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

    async function loadAggregates(type, ids) {
        const shardMap = aggregateShards[type];
        if (!loaded || manifest.schemaVersion < 2) return;
        const shards = [...new Set(ids.map(id => shardMap.get(id)).filter(id => id !== undefined))];
        const key = id => `${type}:${id}`;
        const todo = shards.filter(id => !completedAggregates.has(key(id)) && !pendingAggregates.has(key(id)));
        let updated = false;
        const worker = async () => {
            while (todo.length) {
                const shard = todo.shift();
                const promise = (async () => {
                    try {
                        const block = await fetchJSON(`${base}${manifest.generation}/${type === 'place' ? 'places' : 'tags'}-${shard}.json`);
                        const decoded = await decode(block, dimensions);
                        if ([...decoded.keys()].some(id => shardMap.get(id) !== shard)
                            || decoded.size !== [...shardMap.values()].filter(id => id === shard).length)
                            throw Error('Invalid aggregate shard membership');
                        decoded.forEach((parts, id) => vectors[type].set(id, parts));
                        completedAggregates.add(key(shard)); updated = true;
                    } catch (_) { /* Missing programming retries on the next edit/open. */ }
                    finally { pendingAggregates.delete(key(shard)); }
                })();
                pendingAggregates.set(key(shard), promise);
                await promise;
            }
        };
        await Promise.all([worker(), worker(), ...shards.map(id => pendingAggregates.get(key(id)))]);
        if (updated) changed();
    }

    async function load() {
        if (loaded) return true;
        if (loading) return loading;
        loading = (async () => {
            try {
                const next = await fetchJSON(`${base}manifest.json`, 'no-cache');
                if (![1, 2].includes(next.schemaVersion) || !/^[a-f0-9]{16}$/.test(next.generation)
                    || !Number.isInteger(next.dimensions) || next.dimensions < 2 || next.dimensions > 256) return false;
                for (const key of ['activeShards', 'historyShards']) {
                    if (!Array.isArray(next[key]) || next[key].some(id => !Number.isSafeInteger(id) || id < 0)
                        || new Set(next[key]).size !== next[key].length) return false;
                }
                if (next.schemaVersion === 2 && (!Array.isArray(next.placeShards)
                    || next.placeShards.some((id, index) => id !== index))) return false;
                const core = await fetchJSON(`${base}${next.generation}/core.json`);
                if (core.schemaVersion !== next.schemaVersion || core.dimensions !== next.dimensions || core.domain !== next.domain) return false;
                if (window.__CITY__?.domain && core.domain !== window.__CITY__.domain) return false;
                const nextThresholds = core.affinityThresholds ?? { positive: next.schemaVersion === 1 ? 0 : .35,
                    negative: next.schemaVersion === 1 ? 0 : .55 };
                if (['positive', 'negative'].some(key => !Number.isFinite(nextThresholds[key])
                    || nextThresholds[key] < 0 || nextThresholds[key] >= 1)) return false;
                if (next.affinityThresholds && ['positive', 'negative'].some(key =>
                    next.affinityThresholds[key] !== nextThresholds[key])) return false;
                // Decode into temporary maps. An incomplete generation never installs.
                const decoded = {};
                for (const type of ['event', 'place', 'tag']) decoded[type] = await decode(core.blocks[type], next.dimensions);
                if (next.schemaVersion === 2 && (Math.ceil(core.blocks.place.ids.length / 128) !== next.placeShards.length
                    || (next.tagShards && (!Array.isArray(next.tagShards)
                        || next.tagShards.some((id, index) => id !== index)
                        || Math.ceil(core.blocks.tag.ids.length / 64) !== next.tagShards.length)))) return false;
                dimensions = next.dimensions; manifest = next;
                thresholds = nextThresholds;
                for (const type of ['event', 'place', 'tag']) {
                    vectors[type] = decoded[type];
                    core.blocks[type].ids.forEach((id, i) => support[type].set(String(id), core.blocks[type].support?.[i] ?? 1));
                }
                if (next.schemaVersion === 2) {
                    core.blocks.place.ids.forEach((id, i) => aggregateShards.place.set(id, Math.floor(i / 128)));
                    if (next.tagShards) core.blocks.tag.ids.forEach((id, i) => aggregateShards.tag.set(id, Math.floor(i / 64)));
                }
                loaded = true;
                changed();
                void loadHistory();
                for (const type of ['place', 'tag']) void loadAggregates(type, preferences.filter(e => e.type === type).map(e => e.id));
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
            if (loaded) {
                void loadHistory(); void loadActive();
                for (const type of ['place', 'tag']) void loadAggregates(type, entries.filter(e => e.type === type).map(e => e.id));
            }
            else void load();
        }
    }

    function eventVector(event) {
        const known = vectors.event.get(String(event.id));
        if (known) return known;
        const cached = fallback.get(event);
        if (cached) return cached;
        const result = [];
        // A new event uses its own tags. Venue audience never becomes event audience.
        for (const tag of new Set((event.tags || []).map(normalize))) {
            const vector = vectors.tag.get(tag);
            if (!vector) continue;
            result.push(...vector);
        }
        fallback.set(event, result);
        return result;
    }

    function closest(left, right) {
        if ((left?.length || 0) * (right?.length || 0) > 32) {
            if (!constituentSets.has(left)) constituentSets.set(left, new Set(left));
            if (right.some(part => constituentSets.get(left).has(part))) return 1;
        }
        let best = 0;
        for (const a of left || []) for (const b of right || []) {
            best = Math.max(best, dot(a, b));
            if (best >= .999999) return 1;
        }
        return best;
    }

    async function closestAsync(left, right) {
        let best = 0, start = Date.now(), count = 0;
        if (!left?.length || !right?.length) return 0;
        if (!constituentSets.has(left)) constituentSets.set(left, new Set(left));
        if (right.some(part => constituentSets.get(left).has(part))) return 1;
        for (const a of left) for (const b of right) {
            best = Math.max(best, dot(a, b));
            if (best >= .999999) return 1;
            if (++count % 128 === 0 && Date.now() - start >= 8) { await pause(); start = Date.now(); }
        }
        return best;
    }

    const strength = (value, threshold) => Math.max(0, (value - threshold) / (1 - threshold));

    async function affinityAsync(parts) {
        const liked = positive, disliked = negative;
        return strength(await closestAsync(parts, liked), thresholds.positive)
            - strength(await closestAsync(parts, disliked), thresholds.negative);
    }

    function affinity(parts) {
        // Separate interests are alternatives, not coordinates to average. A
        // pottery preference must not dilute an existing strong jazz match.
        // Conservative semantic propagation; exact preferences remain separate.
        // Generic thematic overlap is weaker evidence for a negative inference.
        return strength(closest(parts, positive), thresholds.positive) - strength(closest(parts, negative), thresholds.negative);
    }

    async function prepareScores() {
        let lastNotification = Date.now();
        try {
            while (scoreQueue.size) {
                const start = Date.now();
                for (const [event, parts] of scoreQueue) {
                    scoreQueue.delete(event);
                    const epoch = profileEpoch;
                    const value = await affinityAsync(parts);
                    if (epoch === profileEpoch) preparedScores.set(event, value);
                    if (Date.now() - start >= 8) break;
                }
                if (!scoreQueue.size || Date.now() - lastNotification >= 100) {
                    version++;
                    document.dispatchEvent(new CustomEvent('fomo:similarity-changed'));
                    lastNotification = Date.now();
                }
                if (scoreQueue.size) await pause();
            }
        } finally { scoring = false; }
    }

    function score(event) {
        if (!loaded || !(positiveCount || negativeCount)) return 0;
        const parts = eventVector(event);
        if (parts.length * (positive.length + negative.length) <= 32) return affinity(parts);
        if (preparedScores.has(event)) return preparedScores.get(event);
        scoreQueue.set(event, parts);
        if (!scoring) { scoring = true; void pause().then(prepareScores); }
        // Exact ranking is already usable while broad-profile work yields in
        // small slices. Arrival invalidates the outer map/list ranking cache.
        return 0;
    }

    async function suggest(type, items, limit = 6) {
        if (!loaded || !vectors[type]) return [];
        if (type === 'place') await loadAggregates(type, items.map(item => `${normalize(item.name)}|${normalize(item.address)}`));
        if (type === 'tag') await loadAggregates(type, items.map(normalize));
        const epoch = profileEpoch;
        const selected = new Set(preferences.filter(e => e.type === type).map(e => e.id));
        const candidates = [];
        const seen = new Set();
        for (let index = 0; index < items.length; index++) {
            if (index && index % 20 === 0) await pause();
            const item = items[index];
            const id = type === 'tag' ? normalize(item) : type === 'place'
                ? `${normalize(item.name)}|${normalize(item.address)}` : String(item.id);
            if (selected.has(id) || seen.has(id)) continue;
            seen.add(id);
            if (type === 'place' && support.place.get(id) === 0) continue;
            const vector = type === 'event' ? eventVector(item) : vectors[type].get(id);
            if (!vector?.length) continue;
            const personal = await affinityAsync(vector);
            if (epoch !== profileEpoch) return [];
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
            for (const [index, candidate] of pool.entries()) {
                let redundancy = 0;
                for (const old of chosen) redundancy = Math.max(redundancy, await closestAsync(old.vector, candidate.vector));
                const value = candidate.score - .25 * redundancy;
                if (value > bestScore) { best = index; bestScore = value; }
            }
            if (epoch !== profileEpoch) return [];
            chosen.push(pool.splice(best, 1)[0]);
        }
        return chosen.map(({ vector, ...item }) => item);
    }

    return { load, setPreferences, score, suggest, ready: () => loaded, revision: () => version };
})();
