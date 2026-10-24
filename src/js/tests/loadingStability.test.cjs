const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function harness() {
    let renders = 0, panelRefreshes = 0;
    const context = vm.createContext({
        navigator: { userAgent: '' }, window: {}, Constants: {}, console, setTimeout,
        document: { addEventListener: (_, fn) => fn(), getElementById: () => null },
        URLParams: { formatDate: date => date.toISOString().slice(0, 10) },
        FomoQueries: { invalidate() {} },
        DiscoveryRanking: { migratePlaces() {} },
        FilterPanelUI: { refreshAvailableTags() { panelRefreshes++; }, selectTags() {} },
        DataManager: {
            async processFullDataAsync() {}, async calculateTagStatsAsync() {},
            async buildSearchIndexAsync() {}
        }
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../core/utils.js'), 'utf8'), context);
    const source = fs.readFileSync(path.join(__dirname, '../script.js'), 'utf8');
    vm.runInContext(source.replace('    App.init();', '    globalThis.App = App;'), context);
    const app = context.App;
    Object.assign(app.state, {
        manifest: { days: ['2026-09-11', '2026-09-12'], remainderChunks: ['remainder0', 'remainder1'] },
        loadedChunks: new Set(['day0']),
        datePickerInstance: { selectedDates: [new Date('2026-09-11T12:00:00Z')] },
        allAvailableTags: []
    });
    app._loadDataFile = async () => [];
    app._applyChunkDescriptions = () => {};
    app._markSnapshotComplete = () => {};
    app.filterAndDisplayEvents = () => { renders++; app._waitingForDateChunks = false; };
    return { app, stats: () => ({ renders, panelRefreshes }) };
}

test('initial ranges select every required day and all necessary tail partitions', () => {
    const { app } = harness();
    const chunks = (...dates) => Array.from(app._chunksForDates(...dates));
    assert.deepEqual(chunks('2026-09-11'), ['day0']);
    assert.deepEqual(chunks('2026-09-11', '2026-09-12'), ['day0', 'day1']);
    assert.deepEqual(chunks('2026-09-12', '2026-09-15'), ['day1', 'remainder0', 'remainder1']);
    assert.deepEqual(chunks('2026-09-20'), ['remainder0', 'remainder1']);
    app.state.manifest = { days: [] };
    assert.deepEqual(chunks('2026-09-11'), ['remainder']);
});

test('background date batches become available without replacing the current map or list', async () => {
    const { app, stats } = harness();
    await app._loadFullData({});
    assert.deepEqual(stats(), { renders: 0, panelRefreshes: 0 });
    assert.equal(app._dataViewPending, true);
    assert.equal(app.state.loadedChunks.size, 4);
});

test('a requested date range finishes once after all of its chunks arrive', async () => {
    const { app, stats } = harness();
    app.state.datePickerInstance.selectedDates = [new Date('2026-09-12'), new Date('2026-09-20')];
    app._waitingForDateChunks = true;
    assert.equal(app._selectedDateChunksReady(), false);
    let publications = [];
    app.filterAndDisplayEvents = () => {
        publications.push([...app.state.loadedChunks]);
        app._waitingForDateChunks = false;
    };
    await app._loadFullData({});
    assert.equal(publications.length, 1);
    assert.deepEqual(publications[0], ['day0', 'day1', 'remainder0', 'remainder1']);
    assert.equal(app._selectedDateChunksReady(), true);
    assert.equal(stats().panelRefreshes, 0);
});

test('the next search consumes pending data using the latest input', () => {
    const { app, stats } = harness();
    app._dataViewPending = true;
    app.performSearch('jazz');
    assert.equal(app.state.searchTerm, 'jazz');
    assert.equal(stats().renders, 1);
});

test('the yielding first render runs the same steps in the same order, scoring matches before markers', async () => {
    const run = async (yielding) => {
        const log = [];
        let yields = 0;
        const events = [{ id: 1, locationKey: 'a' }, { id: 2, locationKey: 'b' }];
        const counter = name => ({ updateCounts: () => log.push(`${name}.counts`), matches: () => true });
        const context = vm.createContext({
            navigator: { userAgent: '' }, window: {}, Constants: {}, console, setTimeout, performance,
            document: { addEventListener: (_, fn) => fn(), getElementById: () => null },
            URLParams: { formatDate: date => date.toISOString().slice(0, 10) },
            TagSelector: counter('tag'), VenueSelector: counter('venue'),
            FormatSelector: counter('format'), NeighborhoodSelector: counter('area'),
            FomoQueries: { currentViewEvents: () => null },
            FilterManager: {
                filterEventsByTags: (_, list) => { log.push('filter'); return list; },
                groupEventsByLocation: list => { log.push('group'); return Object.fromEntries(list.map(e => [e.locationKey, [e]])); }
            },
            FilterPanelUI: { getTagStates: () => ({}), updateView: () => log.push('panel') },
            MarkerController: { findOpenPopup: () => null, displayEventsOnMap: () => log.push('markers') },
            DiscoveryRanking: { details: (e, place) => log.push(`score${e.id}:${place.id}`) },
            DataManager: { yieldToMain: async () => { yields++; } }
        });
        vm.runInContext(fs.readFileSync(path.join(__dirname, '../core/utils.js'), 'utf8'), context);
        const source = fs.readFileSync(path.join(__dirname, '../script.js'), 'utf8');
        vm.runInContext(source.replace('    App.init();', '    globalThis.App = App;'), context);
        const app = context.App;
        Object.assign(app.state, {
            manifest: { days: [] }, loadedChunks: new Set(['remainder']), allEventsFilteredByDate: events,
            locationsByLatLng: { a: { id: 'A' }, b: { id: 'B' } },
            datePickerInstance: { selectedDates: [new Date('2026-10-12T12:00:00Z')] }
        });
        app.updateVisibleItems = () => log.push('visible');
        app._applySearchTermFilter = locations => locations;
        if (yielding) await app._filterAndDisplayEventsYielding();
        else app.filterAndDisplayEvents();
        return { log, yields, matching: app.state.currentlyMatchingEvents };
    };
    const sync = await run(false), split = await run(true);
    // Tags and Venues counts each filter by the other selector first.
    const steps = ['filter', 'filter', 'tag.counts', 'filter', 'venue.counts', 'format.counts', 'area.counts',
        'group', 'visible', 'markers', 'panel'];
    assert.deepEqual(sync.log, steps);
    assert.deepEqual(split.log, [...steps.slice(0, 9), 'score1:A', 'score2:B', ...steps.slice(9)]);
    assert.equal(sync.yields, 0);
    assert.equal(split.yields, 3);
    assert.equal(split.matching.length, 2);
});
