const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const src = path.join(__dirname, '..', '..');
const read = file => fs.readFileSync(path.join(src, file), 'utf8');

// A <link rel="preload"> is only reused when its URL is byte-identical to the
// fetch. DataManager.fetchDataHashed appends the DataCache schema version, so a
// preload without it downloads the file a second time on every first visit.
test('data preloads use exactly the URLs the app fetches', () => {
    const schema = read('js/data/dataCache.js').match(/const SCHEMA_VERSION = (\d+);/)[1];
    assert.match(read('js/data/dataManager.js'), /\$\{url\}\$\{url\.includes\('\?'\) \? '&' : '\?'\}schema=\$\{DataCache\.schemaVersion\}/,
        'fetchDataHashed versions URLs as <url>?schema=<DataCache.schemaVersion>');

    const script = read('js/script.js');
    const configUrl = key => script.match(new RegExp(`${key}: '([^']+)'`))[1];
    const expected = ['MANIFEST_URL', 'TAG_CONFIG_URL', 'TAG_HIERARCHY_URL'].map(key => `${configUrl(key)}?schema=${schema}`);

    const preloads = [...read('index.html').matchAll(/<link rel="preload" as="fetch" href="([^"]+)"/g)].map(m => m[1]);
    assert.deepEqual(preloads, expected);
});
