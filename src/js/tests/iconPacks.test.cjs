const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const { buildPacks, MAX_PACK_BYTES, MAX_STARTUP_BYTES } = require('../../../config/event-icons/packs.cjs');
const source = fs.readFileSync(path.join(__dirname, '../ui/iconManager.js'), 'utf8');
const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><path fill="red" d="M0 0h128v128H0z"/></svg>';

function setup({ status = 200, payload, failImage = () => false, fetchPack,
    pack = 'startup', packBytes = 100, timers = {} } = {}) {
    const fetched = [], images = [];
    const icons = {
        a: { id: 'a', url: 'a.svg', revision: 'a1', pack, gzipBytes: 30 },
        b: { id: 'b', url: 'b.svg', revision: 'b1', pack, gzipBytes: 30 },
        rare: { id: 'rare', url: 'rare.svg', revision: 'r1', pack: null }
    };
    const context = vm.createContext({
        window: { devicePixelRatio: 1 }, AbortController, setTimeout, clearTimeout, queueMicrotask,
        ...timers,
        IconCatalog: { icons, packs: { [pack]: { url: `icons-${pack}.hash.json`, gzipBytes: packBytes } },
            fallbackUrl: 'data:embedded-fallback' },
        async fetch(url, options) {
            fetched.push(url);
            if (fetchPack) return fetchPack(url, options);
            return { ok: status === 200, json: async () => payload || { schemaVersion: 1,
                icons: { a: { revision: 'a1', svg }, b: { revision: 'b1', svg: svg.replace('red', 'blue') } } } };
        },
        Image: class {
            set src(url) { this._src = url; images.push(url); queueMicrotask(() => failImage(url) ? this.onerror() : this.onload()); }
            get src() { return this._src; }
        },
        Utils: { getCurrentTheme: () => 'dark' },
        TagColorManager: { extractColorFromPixels: () => '#123456' },
        document: { createElement: () => ({ getContext: () => ({ drawImage() {}, putImageData() {},
            getImageData: () => ({ data: new Uint8Array(4) }) }) }) }
    });
    vm.runInContext(source, context);
    return { manager: vm.runInContext('IconManager', context), icons, fetched, images };
}

test('concurrent chips share one pack request and decode only requested icons', async () => {
    const { manager, icons, fetched, images } = setup();
    await Promise.all([manager.prepare(icons.a), manager.prepare(icons.b), manager.prepare(icons.a, 'light')]);
    assert.deepEqual(fetched, ['icons-startup.hash.json']);
    assert.equal(images.length, 2);
    assert.ok(images.every(url => url.startsWith('data:image/svg+xml;')));
    assert.equal(decodeURIComponent(images[0].split(',')[1]), svg);
});

test('unassigned artwork remains one standalone request without loading a pack', async () => {
    const { manager, icons, fetched, images } = setup();
    await manager.prepare(icons.rare);
    assert.deepEqual(fetched, []);
    assert.deepEqual(images, ['rare.svg']);
});

test('secondary packs require distinct icons and enough requested bytes', async () => {
    for (const packBytes of [100, 200]) {
        const { manager, icons, fetched, images } = setup({ pack: 'games', packBytes });
        await Promise.all([manager.prepare(icons.a), manager.prepare(icons.b)]);
        assert.equal(fetched.length, packBytes === 100 ? 1 : 0);
        assert.equal(images.filter(url => url.endsWith('.svg')).length, packBytes === 100 ? 0 : 2);
    }
    const { manager, icons, fetched, images } = setup({ pack: 'games' });
    await Promise.all([manager.prepare(icons.a), manager.prepare(icons.a, 'light')]);
    assert.deepEqual(fetched, []);
    assert.deepEqual(images, ['a.svg']);
});

test('an already downloaded secondary pack is reused for later renders', async () => {
    const { manager, icons, fetched } = setup({ pack: 'games' });
    await Promise.all([manager.prepare(icons.a), manager.prepare(icons.b)]);
    await manager.prepare(icons.a, 'light');
    assert.equal(fetched.length, 1);
});

test('already decoded individual icons do not trigger a redundant pack download', async () => {
    const { manager, icons, fetched, images } = setup({ pack: 'games' });
    await manager.prepare(icons.a);
    await Promise.all([manager.prepare(icons.a, 'light'), manager.prepare(icons.b)]);
    assert.deepEqual(fetched, []);
    assert.deepEqual(images, ['a.svg', 'b.svg']);
});

test('a timed-out pack request recovers through individual artwork', async () => {
    const { manager, icons, images } = setup({
        timers: { setTimeout: callback => { queueMicrotask(callback); return 1; }, clearTimeout() {} },
        fetchPack: (url, { signal }) => new Promise((resolve, reject) => {
            if (signal.aborted) reject(new Error('aborted'));
            else signal.addEventListener('abort', () => reject(new Error('aborted')));
        })
    });
    await manager.prepare(icons.a);
    assert.deepEqual(images, ['a.svg']);
});

test('a failed pack falls back per icon and is not retried for every chip', async () => {
    const { manager, icons, fetched, images } = setup({ status: 404 });
    await manager.prepare(icons.a);
    await manager.prepare(icons.b);
    assert.equal(fetched.length, 1);
    assert.deepEqual(images, ['a.svg', 'b.svg']);
});

test('missing entries and mismatched revisions fall back individually', async () => {
    const { manager, icons, images } = setup({ payload: { schemaVersion: 1,
        icons: { a: { revision: 'old', svg } } } });
    await Promise.all([manager.prepare(icons.a), manager.prepare(icons.b)]);
    assert.deepEqual(images, ['a.svg', 'b.svg']);
});

test('invalid pack format and unreadable JSON preserve individual icons', async () => {
    for (const options of [{ payload: { schemaVersion: 2, icons: {} } },
        { fetchPack: async () => ({ ok: true, json: async () => { throw new SyntaxError('partial JSON'); } }) }]) {
        const { manager, icons, images } = setup(options);
        await manager.prepare(icons.a);
        assert.deepEqual(images, ['a.svg']);
    }
});

test('undecodable packed SVG falls back to its individual asset, then embedded fallback', async () => {
    const { manager, icons, images } = setup({ failImage: url => url !== 'data:embedded-fallback' });
    const result = await manager.prepare(icons.a);
    assert.equal(images.length, 3);
    assert.ok(images[0].startsWith('data:image/svg+xml;'));
    assert.equal(images[1], 'a.svg');
    assert.equal(result.url, 'data:embedded-fallback');
});

test('only three different packs download at once', async () => {
    const pending = [], fetched = [];
    // Distinct pack descriptors, using the same renderer in an isolated context.
    const definitions = Array.from({ length: 5 }, (_, i) => `pack${i}`);
    const ctx = vm.createContext({
        window: { devicePixelRatio: 1 }, AbortController, setTimeout, clearTimeout, queueMicrotask,
        IconCatalog: { packs: Object.fromEntries(definitions.map(id => [id, { url: `${id}.json`, gzipBytes: 100 }])) },
        fetch: url => { fetched.push(url); return new Promise(resolve => pending.push(resolve)); },
        Image: class { set src(url) { queueMicrotask(() => this.onload()); } },
        Utils: { getCurrentTheme: () => 'dark' },
        TagColorManager: { extractColorFromPixels: () => '#123456' },
        document: { createElement: () => ({ getContext: () => ({ drawImage() {}, putImageData() {}, getImageData: () => ({}) }) }) }
    });
    vm.runInContext(source, ctx);
    const m = vm.runInContext('IconManager', ctx);
    const requests = definitions.flatMap(pack => [0, 1].map(i => m.prepare({
        id: `${pack}-${i}`, revision: pack, pack, url: `${pack}-${i}.svg`, gzipBytes: 50 })));
    await new Promise(setImmediate);
    assert.equal(fetched.length, 3);
    pending.splice(0).forEach(resolve => resolve({ ok: false }));
    await new Promise(setImmediate);
    assert.equal(fetched.length, 5);
    pending.splice(0).forEach(resolve => resolve({ ok: false }));
    await Promise.all(requests);
});

test('pack hashes stay stable when other artwork changes', () => {
    const artwork = new Map([['a', { revision: '1', svg }], ['b', { revision: '2', svg }]]);
    const config = { schema_version: 1, groups: { startup: ['a'], games: ['b'] } };
    const before = buildPacks(artwork, config);
    artwork.set('b', { revision: '3', svg: svg.replace('red', 'green') });
    const after = buildPacks(artwork, config);
    assert.deepEqual(after.packs.startup, before.packs.startup);
    assert.notEqual(after.packs['games-0'].url, before.packs['games-0'].url);
    assert.equal(JSON.parse(after.files.get(after.packs.startup.url)).icons.a.svg, svg);
});

test('secondary packs are bounded and oversized artwork stays individual', () => {
    const artwork = new Map([['a', { revision: '1', svg }], ['huge', { revision: '2', svg: 'x'.repeat(MAX_PACK_BYTES) }]]);
    for (let i = 0; i < 5; i++) artwork.set(`b${i}`, { revision: '3', svg: 'x'.repeat(50000) });
    const result = buildPacks(artwork, { schema_version: 1,
        groups: { startup: ['a'], games: ['huge', 'b0', 'b1', 'b2', 'b3', 'b4'] } });
    assert.equal(result.membership.huge, undefined);
    assert.equal(Object.keys(result.packs).length, 4);
    for (const bytes of result.files.values()) assert.ok(bytes.length <= MAX_PACK_BYTES);
});

test('invalid membership and oversized startup packs fail the build', () => {
    const artwork = new Map([['a', { revision: '1', svg }], ['huge', { revision: '2', svg: 'x'.repeat(MAX_STARTUP_BYTES) }]]);
    for (const groups of [{ startup: ['missing'] }, { startup: ['a'], games: ['a'] }, { startup: ['huge'] }]) {
        assert.throws(() => buildPacks(artwork, { schema_version: 1, groups }));
    }
});
