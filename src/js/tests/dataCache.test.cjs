const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Minimal in-memory IndexedDB: one database per instance, structured-clone
// semantics on put/get (like the real store), async requests and
// transactions that complete once their requests have settled.
function fakeIndexedDB() {
    const stores = new Map();
    let exists = false;
    let pending = 0;
    let txWaiters = [];
    const settle = () => { if (!pending) { const w = txWaiters; txWaiters = []; w.forEach(fn => fn()); } };
    const request = (fn) => {
        const req = {};
        pending++;
        setTimeout(() => {
            try { req.result = fn(); req.onsuccess && req.onsuccess(); }
            catch (error) { req.error = error; req.onerror && req.onerror(); }
            pending--;
            setTimeout(settle, 0);
        }, 0);
        return req;
    };
    const objectStore = (name) => {
        const s = stores.get(name);
        const key = (value, k) => (s.keyPath ? value[s.keyPath] : k);
        return {
            get: k => request(() => (s.data.has(k) ? structuredClone(s.data.get(k)) : undefined)),
            getKey: k => request(() => (s.data.has(k) ? k : undefined)),
            put: (value, k) => request(() => { s.data.set(key(value, k), structuredClone(value)); }),
            clear: () => request(() => s.data.clear())
        };
    };
    const db = {
        objectStoreNames: { contains: name => stores.has(name) },
        createObjectStore(name, opts) { stores.set(name, { keyPath: opts && opts.keyPath, data: new Map() }); },
        transaction() {
            const tx = { objectStore };
            setTimeout(() => txWaiters.push(() => tx.oncomplete && tx.oncomplete()), 0);
            return tx;
        },
        close() {}
    };
    return {
        stores,
        open() {
            const req = {};
            setTimeout(() => {
                req.result = db;
                if (!exists) { exists = true; req.onupgradeneeded && req.onupgradeneeded(); }
                req.onsuccess && req.onsuccess();
            }, 0);
            return req;
        }
    };
}

const CONFIG = { DATA_DIR: 'data/', MANIFEST_URL: 'data/manifest.json', TAG_CONFIG_URL: 'data/tags.json',
    TAG_HIERARCHY_URL: 'data/tag_hierarchy.json', ORGANIZERS_URL: 'data/organizers.json', REMAINDER_CHUNK: 'remainder' };
const FILES = {
    'data/manifest.json': { days: ['2026-10-12'] },
    'data/tags.json': { geotags: [] },
    'data/tag_hierarchy.json': { tags: [], keywords: [] },
    'data/organizers.json': {},
    'data/events.day0.json': [{ id: 1, name: 'Café Jazz 🎷' }],
    'data/locations.day0.json': [{ id: 7, name: 'Bar' }],
    'data/events.day0.desc.json': { 1: 'Late set' },
    'data/events.remainder.json': [{ id: 2, name: 'Later' }],
    'data/locations.remainder.json': [],
    'data/events.remainder.desc.json': {}
};

// One "page load": fresh module instances over a shared fake IndexedDB.
function load(idb, { files = FILES, online = true, subtle = true } = {}) {
    const requests = [];
    const context = vm.createContext({
        console: { warn() {}, error() {}, log() {} }, setTimeout, clearTimeout, AbortController,
        TextEncoder, TextDecoder, structuredClone, performance,
        crypto: subtle ? globalThis.crypto : {},
        indexedDB: idb, navigator: { userAgent: '', onLine: online },
        window: {}, Constants: {}, document: { addEventListener: (_, fn) => fn(), getElementById: () => null },
        async fetch(url) {
            requests.push(url);
            if (!online) throw new Error('Failed to fetch');
            const name = url.split('?')[0];
            if (!(name in files)) return { ok: false, status: 404 };
            return { ok: true, status: 200, text: async () => JSON.stringify(files[name]) };
        }
    });
    for (const file of ['data/dataCache.js', 'data/dataManager.js']) {
        vm.runInContext(fs.readFileSync(path.join(__dirname, '..', file), 'utf8'), context);
    }
    const source = fs.readFileSync(path.join(__dirname, '../script.js'), 'utf8');
    vm.runInContext(source.replace('    App.init();', '    globalThis.App = App;'), context);
    const app = context.App;
    app._sessionHashes = new Map();
    app._cachePutPromises = [];
    Object.assign(app.config, CONFIG);
    return { app, cache: vm.runInContext('DataCache', context), manager: vm.runInContext('DataManager', context), requests };
}

async function networkSession(idb, options) {
    const { app, cache, requests } = load(idb, options);
    await cache.init();
    app.state.dataFromCache = cache.isUsable();
    app.state.manifest = await app._loadDataFile(CONFIG.MANIFEST_URL);
    app.state.loadedChunks = new Set(['day0', 'remainder']);
    for (const url of Object.keys(FILES).slice(1)) await app._loadDataFile(url);
    await app._markSnapshotComplete();
    return { app, cache, requests };
}

// What a pre-2026-10-12 bundle left behind: parsed-data records, FNV hashes.
function seedLegacySnapshot(idb) {
    const files = idb.stores.get('files').data, meta = idb.stores.get('meta').data;
    const hashes = {};
    for (const [url, data] of Object.entries(FILES)) {
        files.set(url, { url, data: structuredClone(data), hash: 'a1b2c3d4', savedAt: Date.now() });
        hashes[url] = 'a1b2c3d4';
    }
    meta.set('snapshot', { complete: true, manifestDays: ['2026-10-12'], savedAt: Date.now(), hashes, schemaVersion: 4 });
}

test('network loads store UTF-8 bytes, not parsed data, and stamp a version-5 snapshot', async () => {
    const idb = fakeIndexedDB();
    const { cache } = await networkSession(idb);
    const record = idb.stores.get('files').data.get('data/events.day0.json');
    assert.equal('data' in record, false);
    assert.ok(record.bytes instanceof Uint8Array);
    assert.equal(new TextDecoder().decode(record.bytes), JSON.stringify(FILES['data/events.day0.json']));
    const meta = idb.stores.get('meta').data.get('snapshot');
    assert.equal(meta.complete, true);
    assert.equal(meta.schemaVersion, 5);
    assert.deepEqual(Object.keys(meta.hashes).sort(), Object.keys(FILES).sort());
    assert.match(meta.hashes['data/events.day0.json'], /^sha256:[0-9a-f]{64}$/);
    assert.equal(meta.hashes['data/events.day0.json'], await cache.hashBytes(record.bytes));
});

test('a version-5 snapshot reloads offline with identical data', async () => {
    const idb = fakeIndexedDB();
    await networkSession(idb);
    const { app, cache, requests } = load(idb, { online: false });
    await cache.init();
    assert.equal(cache.isUsable(), true);
    app.state.dataFromCache = cache.isUsable();
    for (const [url, data] of Object.entries(FILES)) {
        assert.deepEqual(JSON.parse(JSON.stringify(await app._loadDataFile(url))), data);
    }
    assert.deepEqual(requests, []);
});

test('an incomplete snapshot is never used offline', async () => {
    const idb = fakeIndexedDB();
    const files = { ...FILES };
    delete files['data/events.remainder.desc.json'];
    const first = load(idb, { files });
    await first.cache.init();
    first.app.state.manifest = FILES['data/manifest.json'];
    first.app.state.loadedChunks = new Set(['day0', 'remainder']);
    for (const url of Object.keys(files)) await first.app._loadDataFile(url);
    await first.app._markSnapshotComplete();
    assert.equal(idb.stores.get('meta').data.has('snapshot'), false);
    const next = load(idb, { online: false });
    await next.cache.init();
    assert.equal(next.cache.isUsable(), false);
});

test('a version-4 snapshot of parsed records survives the upgrade and loads offline', async () => {
    const idb = fakeIndexedDB();
    await load(idb).cache.init(); // creates the stores
    seedLegacySnapshot(idb);
    const { app, cache, requests } = load(idb, { online: false });
    await cache.init();
    assert.equal(cache.isUsable(), true);
    assert.equal(idb.stores.get('files').data.size, Object.keys(FILES).length);
    app.state.dataFromCache = true;
    for (const [url, data] of Object.entries(FILES)) {
        assert.deepEqual(JSON.parse(JSON.stringify(await app._loadDataFile(url))), data);
    }
    assert.deepEqual(requests, []);
});

test('snapshots of unknown versions are wiped, and unreadable records count as misses', async () => {
    const idb = fakeIndexedDB();
    await load(idb).cache.init();
    seedLegacySnapshot(idb);
    idb.stores.get('meta').data.get('snapshot').schemaVersion = 3;
    const { cache } = load(idb);
    await cache.init();
    assert.equal(cache.isUsable(), false);
    assert.equal(idb.stores.get('files').data.size, 0);
    idb.stores.get('files').data.set('data/x.json', { url: 'data/x.json', bytes: new TextEncoder().encode('{"a":'), hash: 'h' });
    assert.equal(await cache.read('data/x.json'), null);
    assert.equal(await cache.read('data/missing.json'), null);
});

test('the legacy snapshot migrates to byte records on its first background refresh', async () => {
    const idb = fakeIndexedDB();
    await load(idb).cache.init();
    seedLegacySnapshot(idb);
    const { app, cache } = load(idb);
    await cache.init();
    app.state.dataFromCache = true;
    app.state.isInitialLoad = false;
    let applied = 0;
    app._applyFreshSnapshot = async (fresh) => {
        applied++;
        for (const file of fresh.files.values()) assert.ok(file.data !== undefined);
    };
    await app._backgroundRefresh();
    assert.equal(applied, 1); // FNV-era hashes never equal SHA-256 ones
    for (const record of idb.stores.get('files').data.values()) {
        assert.ok(record.bytes instanceof Uint8Array);
        assert.equal('data' in record, false);
    }
    assert.equal(idb.stores.get('meta').data.get('snapshot').schemaVersion, 5);
});

test('an unchanged refresh compares hashes without parsing; a changed file parses the rest on demand', async () => {
    const idb = fakeIndexedDB();
    await networkSession(idb);
    const parsed = [];
    const session = (files) => {
        const s = load(idb, { files });
        const realParse = s.cache.parseBytes;
        s.cache.parseBytes = (bytes) => { parsed.push(bytes.length); return realParse(bytes); };
        return s;
    };
    let { app, cache, manager } = session(FILES);
    await cache.init();
    app.state.dataFromCache = true;
    let fresh = await app._fetchFreshSnapshot();
    const unparsed = [...fresh.files].filter(([, f]) => f.data === undefined).map(([u]) => u);
    assert.deepEqual(unparsed.sort(), Object.keys(FILES).filter(u => u !== CONFIG.MANIFEST_URL).sort());
    let applied = 0;
    app.state.isInitialLoad = false;
    app._applyFreshSnapshot = async () => { applied++; };
    await app._backgroundRefresh();
    assert.equal(applied, 0);
    assert.deepEqual(parsed, []);

    const changed = { ...FILES, 'data/events.day0.json': [{ id: 1, name: 'Café Jazz 🎷 (moved)' }] };
    ({ app, cache, manager } = session(changed));
    await cache.init();
    app.state.dataFromCache = true;
    fresh = await app._fetchFreshSnapshot();
    const plain = value => JSON.parse(JSON.stringify(value));
    assert.deepEqual(plain(fresh.files.get('data/events.day0.json').data), changed['data/events.day0.json']);
    assert.equal(fresh.files.get('data/events.day0.json').unchanged, false);
    assert.equal(fresh.files.get('data/events.remainder.json').unchanged, true);
    // _applyFreshSnapshot parses the unchanged files and builds from all of them.
    const built = {};
    Object.assign(manager, {
        buildTagHierarchyMaps: () => ({ hierarchyTagsSet: new Set(), descendantsOf: {}, parentsOf: {}, childrenOf: {},
            tagEmojiMap: {}, tagIconMap: {}, tagSearchTerms: {}, formats: {}, formatOnlyTags: new Set(),
            neighborhoodTags: new Set(), tagRedirects: {} }),
        processInitialData() {},
        async processFullDataAsync(events, locations) { built.events = events; built.locations = locations; },
        applyDescriptions(map) { (built.descriptions ||= []).push(map); },
        async calculateTagStatsAsync() {},
        async buildSearchIndexAsync() {}
    });
    app._swapRefreshedState = () => { built.swapped = true; };
    parsed.length = 0;
    await app._applyFreshSnapshot(fresh);
    assert.equal(parsed.length, Object.keys(FILES).length - 2); // all but the manifest and the changed chunk
    assert.deepEqual(JSON.parse(JSON.stringify(built.events)),
        [...changed['data/events.day0.json'], ...FILES['data/events.remainder.json']]);
    assert.deepEqual(JSON.parse(JSON.stringify(built.descriptions)), [{ 1: 'Late set' }, {}]);
    assert.equal(built.swapped, true);
});

test('without WebCrypto the hash falls back to a sliced FNV-1a that never matches SHA-256', async () => {
    const { cache: native } = load(fakeIndexedDB());
    const { cache: fallback } = load(fakeIndexedDB(), { subtle: false });
    const big = new Uint8Array(3 * (1 << 20) + 5).fill(7);
    const a = await fallback.hashBytes(big);
    assert.match(a, /^fnv1a:3145733:[0-9a-f]{8}$/);
    assert.equal(a, await fallback.hashBytes(big.slice()));
    big[big.length - 1] = 8;
    assert.notEqual(a, await fallback.hashBytes(big));
    assert.notEqual(await native.hashBytes(big), await fallback.hashBytes(big));
    assert.equal(await native.hashBytes(new TextEncoder().encode('{"a":1}')),
        await native.hashBytes(new TextEncoder().encode('{"a":1}')));
});
