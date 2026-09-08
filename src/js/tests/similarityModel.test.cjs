const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../data/similarityModel.js'), 'utf8');
const rankingSource = fs.readFileSync(path.join(__dirname, '../data/discoveryRanking.js'), 'utf8');
const generation = '0123456789abcdef';
const block = (ids, values, support) => ({ ids, vectors: Buffer.from(new Int8Array(values.flat()).buffer).toString('base64'), support });
const core = () => ({ schemaVersion: 1, dimensions: 2, domain: 'test', blocks: {
    event: block([], []), place: block(['jazz club|1 main', 'clay studio|2 main'], [[127, 0], [0, 127]], [10, 10]),
    tag: block(['jazz', 'trumpet', 'pottery', 'ceramics'], [[127, 0], [126, 1], [0, 127], [1, 126]], [100, 30, 90, 30])
} });

function setup(overrides = {}) {
    const requests = [];
    const handlers = new Map();
    const fixtures = {
        'manifest.json': { schemaVersion: 1, dimensions: 2, domain: 'test', generation, historyShards: [0], activeShards: [0] },
        [`${generation}/core.json`]: core(),
        [`${generation}/events-0.json`]: block(['1'], [[127, 0]]),
        [`${generation}/active-0.json`]: block(['2', '3'], [[127, 0], [0, 127]]), ...overrides
    };
    const context = vm.createContext({
        window: { __CITY__: { domain: 'test' }, addEventListener() {} }, location: { host: 'test' },
        document: {
            addEventListener(name, callback) { if (!handlers.has(name)) handlers.set(name, []); handlers.get(name).push(callback); },
            dispatchEvent(event) { for (const fn of handlers.get(event.type) || []) fn(event); }
        },
        CustomEvent: class { constructor(type) { this.type = type; } },
        localStorage: { getItem() { return '[]'; }, setItem() {} },
        URL, Float32Array, AbortController, setTimeout, clearTimeout,
        atob: value => Buffer.from(value, 'base64').toString('binary'),
        fetch: async url => { requests.push(url); const data = fixtures[url.replace('data/similarity/', '')];
            return { ok: Boolean(data), status: data ? 200 : 404, json: async () => data }; }
    });
    vm.runInContext(source + '\n' + rankingSource + '\nthis.model=SimilarityModel; this.ranking=DiscoveryRanking;', context);
    return { m: context.model, r: context.ranking, requests };
}
const settle = () => new Promise(resolve => setTimeout(resolve, 15));

test('no-interest page does not request model; opening loads core without full history or active data', async () => {
    const { m, requests } = setup();
    assert.equal(requests.length, 0);
    await m.load();
    assert.equal(requests.length, 2);
    assert.equal(m.score({ id: 2, tags: ['Jazz'] }), 0);
});

test('likes and dislikes transfer across event, place and tag types; exact matches stay stronger', async () => {
    const { r, m } = setup();
    r.set('tag', 'Jazz', 'Jazz', 1);
    await m.load(); await settle();
    const jazz = { id: 2, tags: [] }, pottery = { id: 3, tags: [] };
    assert.ok(r.score(jazz, {}) > r.score(pottery, {}) + 15);
    r.set('event', '3', 'Pottery event', 1);
    assert.ok(r.score(pottery, {}) > r.score(jazz, {}));
    r.remove('event', '3');
    r.set('place', 'clay studio|2 main', 'Clay studio', -1);
    assert.ok(m.score(pottery) < -.9);
    r.remove('place', 'clay studio|2 main');
    assert.equal(m.score(pottery), 0);
});

test('historical saved event fetches its shard and still influences upcoming events', async () => {
    const { r, m, requests } = setup();
    r.set('event', '1', 'An old jazz show', 1);
    await m.load(); await settle();
    assert.ok(requests.some(url => url.endsWith('/events-0.json')));
    assert.ok(m.score({ id: 2 }) > .99);
});

test('new event uses own tags; venue audience does not leak', async () => {
    const { r, m } = setup();
    r.set('tag', 'Jazz', 'Jazz', -1);
    await m.load(); await settle();
    assert.ok(m.score({ id: 9000, tags: ['Jazz'] }) < -.99);
    assert.equal(r.details({ id: 9001, tags: [] }, { tags: ['Jazz'] }).similarity, 0);
});

test('suggestions exclude both stances and prefer related candidates', async () => {
    const { r, m } = setup();
    r.set('tag', 'Jazz', 'Jazz', 1);
    r.set('tag', 'Ceramics', 'Ceramics', -1);
    await m.load(); await settle();
    const suggestions = await m.suggest('tag', ['Jazz', 'Trumpet', 'Pottery', 'Ceramics']);
    assert.equal(suggestions.length, 1);
    assert.equal(suggestions[0].id, 'trumpet');
});

test('model arrival invalidates previously cached exact-only scores', async () => {
    const { r, m } = setup();
    const event = { id: 2, tags: [] };
    r.set('tag', 'Jazz', 'Jazz', 1);
    assert.equal(r.score(event, {}), 0);
    const revision = r.revision();
    await m.load(); await settle();
    assert.ok(r.revision() > revision);
    assert.ok(r.score(event, {}) > 19);
});

test('missing, incompatible and corrupt artifacts fall back to exact ranking', async () => {
    for (const overrides of [
        { 'manifest.json': null },
        { 'manifest.json': { schemaVersion: 10 } },
        { [`${generation}/core.json`]: { ...core(), domain: 'another-city' } },
        { [`${generation}/core.json`]: { ...core(), blocks: { ...core().blocks, tag: block(['jazz'], [[1]]) } } }
    ]) {
        const { r, m } = setup(overrides);
        r.set('event', '2', 'My event', 1);
        assert.equal(await m.load(), false);
        assert.equal(m.ready(), false);
        assert.equal(r.score({ id: 2 }, {}), 100);
    }
});

test('term preferences stay exact and do not request semantic expansion', () => {
    const { r, requests } = setup();
    r.set('term', 'Jazz', 'Jazz', 1);
    assert.equal(requests.length, 0);
    assert.equal(r.score({ name: 'Jazzercise', tags: [] }, {}), 0);
});

test('a missing active chunk retains core suggestions and the new-event fallback', async () => {
    const { r, m } = setup({ [`${generation}/active-0.json`]: null });
    r.set('tag', 'Jazz', 'Jazz', 1);
    await m.load(); await settle();
    assert.equal(m.ready(), true);
    assert.ok(m.score({ id: 2, tags: ['Jazz'] }) > .99);
    assert.equal((await m.suggest('tag', ['Jazz', 'Trumpet']))[0].id, 'trumpet');
});
