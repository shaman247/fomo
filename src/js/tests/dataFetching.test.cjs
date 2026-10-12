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
        DataCache: {
            schemaVersion: 4,
            encodeText: text => new TextEncoder().encode(text),
            async hashBytes(bytes) { const text = new TextDecoder().decode(bytes); hashed.push(text); return `h:${text}`; }
        },
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

test('hashed loads return the recovered body and its hash and preserve schema and options', async () => {
    const body = '{"123":"Description"}';
    const { manager, calls } = setup([{ body: '<html>Unavailable</html>' }, { body }]);
    const result = await manager.fetchDataHashed('data/events.remainder0.desc.json?v=1', 1000,
        { cache: 'no-cache', credentials: 'same-origin' });
    assert.equal(result.data['123'], 'Description');
    assert.equal(result.hash, `h:${body}`);
    assert.equal(new TextDecoder().decode(result.bytes), body);
    assert.equal(result.unchanged, false);
    assert.equal(calls[0].url, 'data/events.remainder0.desc.json?v=1&schema=4');
    assert.equal(calls[1].url, calls[0].url);
    assert.equal(calls[0].options.cache, 'no-cache');
    assert.equal(calls[1].options.cache, 'reload');
    assert.equal(calls[1].options.credentials, 'same-origin');
});

test('persistent malformed JSON reports the file and stops after two requests', async () => {
    const { manager, calls } = setup([{ body: '' }, { body: 'broken' }]);
    await assert.rejects(manager.fetchDataHashed('data/events.remainder2.json'),
        /Invalid JSON in data\/events.remainder2.json\?schema=4 after retrying/);
    assert.equal(calls.length, 2);
});

test('a body matching the cached hash is not parsed; any other body is', async () => {
    const body = '[{"id":1}]';
    const { manager } = setup([{ body }, { body: '[{"id":2}]' }]);
    const same = await manager.fetchDataHashed('data/events.day0.json', 1000, {}, `h:${body}`);
    assert.equal(same.unchanged, true);
    assert.equal(same.data, undefined);
    assert.equal(new TextDecoder().decode(same.bytes), body);
    const other = await manager.fetchDataHashed('data/events.day0.json', 1000, {}, `h:${body}`);
    assert.equal(other.unchanged, false);
    assert.equal(other.data[0].id, 2);
});

test('a broken body never matches the cached hash and still reloads once', async () => {
    const body = '[{"id":1}]';
    const { manager, calls } = setup([{ body: '[{"id":' }, { body }]);
    const result = await manager.fetchDataHashed('data/events.day0.json', 1000, {}, `h:${body}`);
    assert.equal(calls.length, 2);
    assert.equal(calls[1].options.cache, 'reload');
    assert.equal(result.unchanged, true);
});

test('HTTP failures keep their specific error without a JSON retry', async () => {
    const { manager, calls } = setup([{ status: 404 }]);
    await assert.rejects(manager.fetchData('data/missing.json'), /404/);
    assert.equal(calls.length, 1);
});
