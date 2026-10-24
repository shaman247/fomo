const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function setup() {
    // Real date helpers (city-timezone day math); the DOM-bound helpers stay stubbed.
    const utilsContext = vm.createContext({});
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../core/utils.js'), 'utf8'), utilsContext);
    const context = vm.createContext({console, performance, setTimeout, Utils: {
        ...vm.runInContext('Utils', utilsContext),
        decodeHtml: s => s,
        eventFilterTags: (e, l) => [...(e.tags || []), ...(l?.tags || [])],
    }});
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../data/dataManager.js'), 'utf8'), context);
    return {manager: vm.runInContext('DataManager', context), state: {},
        config: {START_DATE: new Date(2026, 8, 9), END_DATE: new Date(2026, 11, 9)}};
}
const building = {id: 2163, name: '120 Walker St', lat: 40.7, lng: -74, tags: ['venue:attraction']};
const loft = {id: 7002, name: 'The Walker Loft', lat: 40.7, lng: -74,
    address: '120 Walker St, 5th Floor', tags: ['venue:Event Hall']};
const event = (id, place = loft) => ({id, place_id: place.id, location: place.name,
    name: `Event ${id}`, lat: place.lat, lng: place.lng, tags: [],
    occurrences: [['2026-09-10', '19:00:00', null, '21:00:00']]});
const owner = (state, id) => state.locationsByLatLng[state.eventsById[id].locationKey];

test('an inactive building fallback cannot supply an active tenant name, address or filters', () => {
    const {manager, state, config} = setup();
    manager.processInitialData([event(1)], [building, loft], state, config);
    manager.buildTagIndex(state);
    assert.equal(owner(state, 1).id, loft.id);
    assert.equal(owner(state, 1).address, loft.address);
    assert.equal(state.eventTagIndex['venue:Event Hall'].includes(1), true);
    assert.equal(state.eventTagIndex['venue:attraction'], undefined);
});

test('ID resolves stale event names and independently rounded coordinates', () => {
    const {manager, state, config} = setup();
    manager.processInitialData([{...event(1), location: 'Walker Loft', lat: 40.700001}],
        [building, loft], state, config);
    assert.equal(owner(state, 1).id, loft.id);
    assert.equal(owner(state, 1).lat, state.eventsById[1].latitude);
});

test('same-name tenants retain distinct identities across phased loads', async () => {
    const {manager, state, config} = setup();
    const sibling = {...loft, id: 10801, address: '120 Walker St, 6th Floor', tags: ['venue:Community Space']};
    manager.processInitialData([event(1)], [building, loft], state, config);
    await manager.processFullDataAsync([event(1), event(2, sibling)], [loft, sibling], state, config);
    assert.equal(state.allEvents.length, 2);
    assert.notEqual(state.eventsById[1].locationKey, state.eventsById[2].locationKey);
    assert.equal(owner(state, 1).id, loft.id);
    assert.equal(owner(state, 2).id, sibling.id);
    const firstKey = state.eventsById[1].locationKey;
    await manager.processFullDataAsync([], [building, sibling], state, config);
    assert.equal(state.eventsById[1].locationKey, firstKey);
});

test('missing venue metadata never borrows a sibling and resolves when its chunk arrives', async () => {
    const {manager, state, config} = setup();
    manager.processInitialData([event(1), event(2, building)], [building], state, config);
    assert.equal(owner(state, 1), undefined);
    assert.equal(owner(state, 2).id, building.id);
    await manager.processFullDataAsync([], [loft], state, config);
    assert.equal(owner(state, 1).id, loft.id);
});

test('legacy events require an unambiguous coordinate and name match', () => {
    const {manager, state, config} = setup();
    const legacy = {...event(1), place_id: undefined};
    manager.processInitialData([legacy], [building, loft], state, config);
    assert.equal(owner(state, 1).id, loft.id);
    manager.processInitialData([legacy], [building, loft, {...loft, id: 9999}], state, config);
    assert.equal(owner(state, 1), undefined);
});

test('phase-2 merge stages across yields and publishes events with their lookups at once', async () => {
    const {manager, state, config} = setup();
    // Event 1's coordinate gains a second venue only in phase 2, so it must move.
    manager.processInitialData([event(1)], [building, loft], state, config);
    const before = state.eventsById[1].locationKey;
    const consistent = () => {
        const offsets = state.coordOffsetByVenue;
        return state.allEvents.every(e => {
            const off = offsets.get(e.venueKey);
            return state.eventsById[e.id] === e && e.locationKey === `${off ? off.lat : e.origLat},${off ? off.lng : e.origLng}`;
        }) && Object.keys(state.eventsById).length === state.allEvents.length;
    };
    const seen = [];
    let done = false;
    const watch = () => { seen.push([state.allEvents.length, consistent()]); if (!done) setTimeout(watch, 0); };
    setTimeout(watch, 0);
    const merge = manager.processFullDataAsync([event(2, building), event(3)], [], state, config);
    await merge;
    done = true;
    assert.ok(seen.length >= 1, 'merge yielded to the observer');
    assert.ok(seen.every(([, ok]) => ok), 'every observed state is internally consistent');
    assert.ok(seen.every(([n]) => n === 1), 'new events stay unpublished while staging');
    assert.equal(state.allEvents.length, 3);
    assert.ok(consistent());
    assert.notEqual(state.eventsById[1].locationKey, before);
    assert.equal(state.eventsById[3].locationKey, state.eventsById[1].locationKey);
    assert.equal(owner(state, 1).id, loft.id);
    assert.equal(owner(state, 2).id, building.id);
});

test('staged tag stats publish the same frequencies and available tags as the sync path', async () => {
    const {manager, config} = setup();
    const build = () => {
        const s = {tagConfig: {}, hierarchyTagsSet: new Set(['Music', 'Jazz', 'Format', 'Talk', 'Unlocated', 'venue:Event Hall']),
            tagChildrenOf: {Format: ['Talk']}, formatOnlyTags: new Set()};
        manager.processInitialData([
            {...event(1), tags: ['Music', 'Jazz', 'keyword-only']},
            {...event(2), tags: ['Jazz', 'Talk']},
            {...event(3, building), tags: ['Music']},
        ], [building, loft], s, config);
        // An event without a location key still contributes available tags only.
        s.allEvents.push({id: 4, tags: ['Unlocated']});
        return s;
    };
    const sync = build();
    manager.calculateTagFrequencies(sync);
    manager.processTagHierarchy(sync, config);
    const staged = build();
    await manager.calculateTagStatsAsync(staged, config);
    assert.deepEqual(Object.entries(staged.tagFrequencies), Object.entries(sync.tagFrequencies));
    assert.deepEqual(staged.allAvailableTags, sync.allAvailableTags);
    assert.deepEqual(staged.searchableTagsForEmptyTerm, sync.searchableTagsForEmptyTerm);
    assert.deepEqual([...staged.structuralFormatTags], [...sync.structuralFormatTags]);
    assert.equal(staged.tagFrequencies.Jazz, 1);
    assert.equal(staged.tagFrequencies.Music, 2);
    assert.ok(staged.allAvailableTags.includes('Unlocated'));
    assert.equal(staged.tagFrequencies.Unlocated, undefined);
});
