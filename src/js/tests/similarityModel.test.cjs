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

function aggregateFixtures() {
    const multi = (ids, parts, support) => ({ ...block(ids, parts.flat(), support),
        offsets: parts.reduce((offsets, group) => [...offsets, offsets.at(-1) + group.length], [0]) });
    const placeIds = ['mixed center|1 main', 'clay studio|2 main'];
    return {
        'manifest.json': { schemaVersion: 2, generation, dimensions: 2, domain: 'test',
            activeShards: [0], historyShards: [0], placeShards: [0] },
        [`${generation}/core.json`]: { ...core(), schemaVersion: 2, blocks: {
            ...core().blocks,
            place: multi(placeIds, [[], []], [10, 10]),
            tag: multi(['jazz', 'pottery', 'creative activities'], [[[127, 0]], [[0, 127]], [[127, 0], [0, 127]]], [100, 90, 190])
        } },
        [`${generation}/places-0.json`]: multi(placeIds, [[[127, 0], [0, 127]], [[0, 127]]], [10, 10])
    };
}

test('mixed venue and parent tag preserve each program instead of a centroid', async () => {
    const { r, m, requests } = setup(aggregateFixtures());
    await m.load();
    assert.equal(requests.some(url => url.includes('/places-')), false);
    r.set('place', 'mixed center|1 main', 'Mixed center', 1);
    await settle();
    assert.ok(m.score({ id: 2 }) > .99);
    assert.ok(m.score({ id: 3 }) > .99);
    assert.equal(requests.filter(url => url.endsWith('/places-0.json')).length, 1);
    r.remove('place', 'mixed center|1 main');
    r.set('tag', 'Creative Activities', 'Creative Activities', 1);
    assert.ok(m.score({ id: 2 }) > .99);
    assert.ok(m.score({ id: 3 }) > .99);
    r.set('tag', 'Pottery', 'Pottery', -1);
    assert.ok(m.score({ id: 2 }) > .99);
    assert.equal(m.score({ id: 3 }), 0);
});

test('candidate venues and new-event fallback also use their closest constituent', async () => {
    const { r, m } = setup(aggregateFixtures());
    r.set('tag', 'Jazz', 'Jazz', 1);
    await m.load(); await settle();
    const suggestions = await m.suggest('place', [
        { name: 'Mixed Center', address: '1 Main' }, { name: 'Clay Studio', address: '2 Main' }
    ]);
    assert.equal(suggestions.length, 1);
    assert.equal(suggestions[0].id, 'mixed center|1 main');
    assert.ok(suggestions[0].score > .99);
    assert.ok(m.score({ id: 9999, tags: ['Jazz', 'Pottery'] }) > .99);
});

test('missing venue constituents preserve exact preference ranking', async () => {
    const { r, m } = setup({ ...aggregateFixtures(), [`${generation}/places-0.json`]: null });
    r.set('place', 'mixed center|1 main', 'Mixed center', 1);
    await m.load(); await settle();
    assert.equal(m.ready(), true);
    assert.equal(m.score({ id: 2 }), 0);
    assert.equal(r.score({ id: 2 }, { name: 'Mixed center', address: '1 Main' }), 100);
});

test('tag examples load lazily and expand a selected topic without losing its anchor', async () => {
    const fixtures = aggregateFixtures();
    fixtures['manifest.json'].tagShards = [0];
    const tag = fixtures[`${generation}/core.json`].blocks.tag;
    fixtures[`${generation}/tags-0.json`] = {
        ...block(tag.ids, [[127, 0], [0, 127], [0, 127], [127, 0], [0, 127]], tag.support),
        offsets: [0, 2, 3, 5]
    };
    const { r, m, requests } = setup(fixtures);
    await m.load();
    assert.equal(requests.some(url => url.includes('/tags-')), false);
    r.set('tag', 'Jazz', 'Jazz', 1);
    await settle();
    assert.equal(requests.filter(url => url.endsWith('/tags-0.json')).length, 1);
    assert.ok(m.score({ id: 2 }) > .99);
    assert.ok(m.score({ id: 3 }) > .99);
});

test('broad-profile scores yield and discard work from an edited profile', async () => {
    const fixtures = aggregateFixtures();
    fixtures[`${generation}/core.json`].blocks.tag = {
        ...block(['wide'], Array.from({ length: 64 }, (_, i) => [127 - i, i]), [64]), offsets: [0, 64]
    };
    const { r, m } = setup(fixtures);
    r.set('tag', 'wide', 'Wide interest', 1);
    await m.load(); await settle();
    const event = { id: 2 };
    assert.equal(m.score(event), 0); // preparation is deferred
    const revision = m.revision();
    r.set('tag', 'wide', 'Wide interest', -1);
    assert.equal(m.score(event), 0);
    await settle();
    assert.ok(m.revision() > revision);
    assert.ok(m.score(event) < -.99);
});

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

test('adding unrelated likes or dislikes never dilutes an existing constituent match', async () => {
    const { r, m } = setup();
    r.set('tag', 'Jazz', 'Jazz', 1);
    await m.load(); await settle();
    const jazz = m.score({ id: 2 });
    r.set('tag', 'Pottery', 'Pottery', 1);
    assert.equal(m.score({ id: 2 }), jazz);
    assert.ok(m.score({ id: 3 }) > .99);
    r.remove('tag', 'Jazz'); r.remove('tag', 'Pottery');
    r.set('tag', 'Jazz', 'Jazz', -1);
    const dislikedJazz = m.score({ id: 2 });
    r.set('tag', 'Pottery', 'Pottery', -1);
    assert.equal(m.score({ id: 2 }), dislikedJazz);
    assert.ok(m.score({ id: 3 }) < -.99);
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
        { 'manifest.json': { schemaVersion: 1, generation, dimensions: 2, activeShards: ['../core'], historyShards: [] } },
        { [`${generation}/core.json`]: { ...core(), domain: 'another-city' } },
        { [`${generation}/core.json`]: { ...core(), blocks: { ...core().blocks, tag: block(['jazz', 'jazz'], [[127, 0], [0, 127]]) } } },
        { [`${generation}/core.json`]: { ...core(), blocks: { ...core().blocks, tag: block(['jazz'], [[127, 0]], [-1]) } } },
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
