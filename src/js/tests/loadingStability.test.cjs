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
        FilterPanelUI: { refreshAvailableTags() { panelRefreshes++; }, selectTags() {} },
        DataManager: {
            async processFullDataAsync() {}, calculateTagFrequencies() {}, processTagHierarchy() {},
            async buildSearchIndexAsync() {}
        }
    });
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

