const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function setup() {
    const context = vm.createContext({console, performance, setTimeout, Utils: {
        decodeHtml: s => s,
        parseDateInZone: (d, t) => d ? new Date(`${d}T${t || '00:00:00'}`) : null,
        eventFilterTags: (e, l) => [...(e.tags || []), ...(l?.tags || [])],
    }});
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../data/dataManager.js'), 'utf8'), context);
    return {manager: vm.runInContext('DataManager', context), state: {},
        config: {START_DATE: new Date('2026-09-09'), END_DATE: new Date('2026-12-09')}};
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
