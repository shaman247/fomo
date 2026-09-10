const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function setup(responses) {
    const calls = [], hashed = [];
    const context = vm.createContext({
        AbortController, setTimeout, clearTimeout,
        console: { error() {}, warn() {} },
        DataCache: { schemaVersion: 4, hashString(text) { hashed.push(text); return 'hash'; } },
        async fetch(url, options) {
            calls.push({ url, options });
            assert.ok(responses.length, 'unexpected extra request');
            const next = responses.shift();
            return { ok: !next.status, status: next.status || 200, text: async () => next.body };
        }
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../data/dataManager.js'), 'utf8'), context);
    return { manager: vm.runInContext('DataManager', context), calls, hashed };
}

test('valid JSON loads once without forcing a cache reload', async () => {
    const { manager, calls } = setup([{ body: '[{"id":1}]' }]);
    assert.equal((await manager.fetchData('data/events.day0.json'))[0].id, 1);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].options.cache, undefined);
});

test('a partial JSON response recovers with one network reload', async () => {
    const { manager, calls } = setup([{ body: '[{"id":' }, { body: '[{"id":1}]' }]);
    assert.equal((await manager.fetchData('data/events.day0.json'))[0].id, 1);
    assert.equal(calls.length, 2);
    assert.equal(calls[1].url, calls[0].url);
    assert.equal(calls[1].options.cache, 'reload');
});

test('hashed loads hash only the recovered body and preserve schema and options', async () => {
    const body = '{"123":"Description"}';
    const { manager, calls, hashed } = setup([{ body: '<html>Unavailable</html>' }, { body }]);
    const result = await manager.fetchDataHashed('data/events.remainder0.desc.json?v=1', 1000,
        { cache: 'no-cache', credentials: 'same-origin' });
    assert.equal(result.data['123'], 'Description');
    assert.equal(result.hash, 'hash');
    assert.deepEqual(hashed, [body]);
    assert.equal(calls[0].url, 'data/events.remainder0.desc.json?v=1&schema=4');
    assert.equal(calls[1].url, calls[0].url);
    assert.equal(calls[0].options.cache, 'no-cache');
    assert.equal(calls[1].options.cache, 'reload');
    assert.equal(calls[1].options.credentials, 'same-origin');
});

test('persistent malformed JSON reports the file and stops after two requests', async () => {
    const { manager, calls, hashed } = setup([{ body: '' }, { body: 'broken' }]);
    await assert.rejects(manager.fetchDataHashed('data/events.remainder2.json'),
        /Invalid JSON in data\/events.remainder2.json\?schema=4 after retrying/);
    assert.equal(calls.length, 2);
    assert.deepEqual(hashed, []);
});

test('HTTP failures keep their specific error without a JSON retry', async () => {
    const { manager, calls } = setup([{ status: 404 }]);
    await assert.rejects(manager.fetchData('data/missing.json'), /404/);
    assert.equal(calls.length, 1);
});
