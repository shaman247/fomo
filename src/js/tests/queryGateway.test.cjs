const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { webcrypto, createHash } = require('node:crypto');
const source = path.join(__dirname, '../query');
const copy = v => JSON.parse(JSON.stringify(v));
async function fixture({ corrupt = false } = {}) {
    const bodies = {
        'manifest.json': { days: ['2026-09-09'], remainderChunks: [] },
        'tag_hierarchy.json': { tags: [] }, 'organizers.json': {},
        'events.day0.json': [{ id: 1, name: 'Example', lat: 40, lng: -74, location: 'Hall', tags: [], occurrences: [['2026-09-09', '8pm', null, '']] }],
        'events.day0.desc.json': {}, 'locations.day0.json': [{ id: 1, name: 'Hall', lat: 40, lng: -74, tags: [] }]
    };
    const files = Object.fromEntries(Object.entries(bodies).map(([n, v]) => [n, createHash('sha256').update(JSON.stringify(v)).digest('hex')]));
    const inventory = { version: 1, cityId: 'fixture', revision: 'snapshot1', generatedAt: '2026-09-09T00:00:00Z', files };
    const elements = [];
    const element = id => { const el = { id, children: [], setAttribute() {}, after() {}, append(...items) { this.children.push(...items); }, replaceChildren() { this.children = []; } }; elements.push(el); return el; };
    element('filter-container'); element('logo-menu');
    let moves, renders = 0, failRender = false, pushes = 0;
    const state = { map: { getBounds: () => null, on: (_, fn) => { moves = fn; } }, eventsById: {}, locationsByLatLng: {}, searchTerm: 'old search' };
    const app = { state, elements: { omniSearchInput: { value: 'old search' } }, updateFilteredEventList() { renders++; if (failRender) { failRender = false; throw Error('render failed'); } } };
    const context = vm.createContext({ console, TextEncoder, TextDecoder, URL, btoa, atob, crypto: webcrypto,
        location: { href: 'https://example.test/' }, CustomEvent: class {},
        window: { __CITY__: { cityId: 'fixture', timezone: 'America/New_York' } },
        document: { getElementById: id => elements.find(e => e.id === id), createElement: () => element(), dispatchEvent() {}, documentElement: { classList: { toggle() {} } } },
        FilterPanelUI: { getTagStates: () => ({}) }, FormatSelector: { selection: () => null }, NeighborhoodSelector: { selection: () => null },
        URLParams: { formatDate: String }, DiscoveryRanking: { score: () => 0, revision: () => 1 },
        FomoWebMCP: { register: async () => {} }, HistoryManager: { push: () => { pushes++; } }, ToastNotifier: { showToast() {} },
        fetch: async url => {
            const name = url.replace('data/', ''); const value = name === 'query-manifest.json' ? inventory : bodies[name];
            const text = JSON.stringify(corrupt && name === 'events.day0.json' ? [] : value);
            return { ok: true, json: async () => JSON.parse(text), arrayBuffer: async () => new TextEncoder().encode(text).buffer };
        }
    });
    for (const file of ['querySchema.js', 'queryCore.js', 'queryGateway.js']) vm.runInContext(fs.readFileSync(path.join(source, file), 'utf8'), context);
    const gateway = vm.runInContext('FomoQueries', context); gateway.init(app); await gateway.load();
    const query = { schemaVersion: 1, cityId: 'fixture', time: { kind: 'all_published' }, groups: [], exclude: [], unknownPolicy: 'separate', sort: { kind: 'earliest' }, view: 'keep' };
    const input = (q = query, id = webcrypto.randomUUID()) => { const c = gateway.getContext(); return { query: q, requestId: id, expectedStateRevision: c.stateRevision, expectedContextRevision: c.contextRevision, catalogRevision: c.catalogRevision, coveragePolicy: 'require_complete' }; };
    return { gateway, query, input, state, app, move: () => moves(), renderFailure: () => { failRender = true; }, stats: () => ({ renders, pushes }) };
}
test('apply is idempotent; conflicting IDs, stale views and cancelled requests do not commit', async () => {
    const { gateway: g, input, move, stats } = await fixture();
    const command = input(); const first = await g.receive({ method: 'apply_query', input: command });
    assert.equal(first.ok, true); assert.equal(first.result.total, 1);
    assert.deepEqual(copy(await g.receive({ method: 'apply_query', input: command })), copy(first));
    assert.equal(stats().pushes, 1);
    assert.equal((await g.receive({ method: 'apply_query', input: { ...command, coveragePolicy: 'allow_partial' } })).error.code, 'request_id_conflict');
    assert.equal((await g.receive({ method: 'apply_query', input: { ...command, requestId: 'stale' } })).error.code, 'stale_state');
    const moved = input(); move();
    assert.equal((await g.receive({ method: 'apply_query', input: moved })).error.code, 'stale_context');
    assert.equal((await g.receive({ method: 'apply_query', input: input() }, { aborted: true })).error.code, 'cancelled');
    assert.equal(stats().pushes, 1);
});
test('invalid, zero-result and incomplete-data queries never silently widen', async () => {
    const f = await fixture(); const { gateway: g, query, input } = f;
    assert.equal((await g.receive({ method: 'apply_query', input: input({ ...query, nearMe: true }) })).error.code, 'invalid_schema');
    assert.equal(g.active(), false);
    const empty = { ...query, groups: [{ anyOf: [{ kind: 'text', fields: ['name'], match: 'phrase', value: 'No such event' }] }] };
    const result = await g.receive({ method: 'apply_query', input: input(empty) });
    assert.equal(result.result.total, 0); assert.deepEqual(copy(g.query()), empty);
    const partial = await fixture({ corrupt: true });
    assert.equal((await partial.gateway.receive({ method: 'apply_query', input: partial.input() })).error.code, 'data_incomplete');
    assert.equal(partial.gateway.active(), false);
});
test('a rendering failure restores the previous search and revision without history', async () => {
    const { gateway: g, input, state, renderFailure, stats } = await fixture();
    const before = g.getContext().stateRevision; renderFailure();
    assert.equal((await g.receive({ method: 'apply_query', input: input() })).ok, false);
    assert.equal(g.active(), false); assert.equal(g.getContext().stateRevision, before);
    assert.equal(state.searchTerm, 'old search'); assert.equal(stats().pushes, 0);
});
test('manual changes while an apply is pending invalidate its commit', async () => {
    const { gateway: g, input } = await fixture();
    const pending = g.receive({ method: 'apply_query', input: input() });
    g.invalidate();
    assert.equal((await pending).error.code, 'stale_state'); assert.equal(g.active(), false);
});
