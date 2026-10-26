const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function load(file, name, globals) {
    const ctx = vm.createContext({ console: { warn() {}, error() {} }, URLSearchParams, ...globals });
    vm.runInContext(fs.readFileSync(path.join(__dirname, file), 'utf8') + `\nthis.mod = ${name};`, ctx);
    return ctx.mod;
}

function shareLink(navigator) {
    const toasts = [];
    const mod = load('../ui/shareLink.js', 'ShareLink', {
        navigator,
        ToastNotifier: { showToast: (message, type) => toasts.push([message, type]) }
    });
    return { mod, toasts };
}

const clipboard = writes => ({ writeText: async url => { writes.push(url); } });

test('opens the native share sheet with the url and title when available', async () => {
    const shared = [], writes = [];
    const { mod, toasts } = shareLink({ share: async data => { shared.push(data); }, clipboard: clipboard(writes) });
    assert.equal(await mod.share({ url: 'https://fomo.nyc/?event=1', title: 'Show' }), 'shared');
    assert.deepEqual(JSON.parse(JSON.stringify(shared)), [{ url: 'https://fomo.nyc/?event=1', title: 'Show' }]);
    assert.deepEqual(writes, []);
    assert.deepEqual(toasts, []);
});

test('dismissing the share sheet neither copies nor toasts', async () => {
    const writes = [];
    const abort = Object.assign(new Error('cancelled'), { name: 'AbortError' });
    const { mod, toasts } = shareLink({ share: async () => { throw abort; }, clipboard: clipboard(writes) });
    assert.equal(await mod.share({ url: 'u' }), 'cancelled');
    assert.deepEqual(writes, []);
    assert.deepEqual(toasts, []);
});

test('copies with a toast when there is no share sheet', async () => {
    const writes = [];
    const { mod, toasts } = shareLink({ clipboard: clipboard(writes) });
    assert.equal(await mod.share({ url: 'https://fomo.nyc/?lat=1', title: 't' }), 'copied');
    assert.deepEqual(writes, ['https://fomo.nyc/?lat=1']);
    assert.deepEqual(toasts, [['Link copied to clipboard!', 'success']]);
});

test('falls back to copying when sharing fails or the data cannot be shared', async () => {
    const writes = [];
    const denied = Object.assign(new Error('no activation'), { name: 'NotAllowedError' });
    let { mod } = shareLink({ share: async () => { throw denied; }, clipboard: clipboard(writes) });
    assert.equal(await mod.share({ url: 'a' }), 'copied');
    ({ mod } = shareLink({ share: async () => assert.fail('should not share'), canShare: () => false, clipboard: clipboard(writes) }));
    assert.equal(await mod.share({ url: 'b' }), 'copied');
    assert.deepEqual(writes, ['a', 'b']);
});

test('shows the url when the clipboard is unavailable', async () => {
    const { mod, toasts } = shareLink({});
    assert.equal(await mod.share({ url: 'https://fomo.nyc/' }), 'failed');
    assert.deepEqual(toasts, [['Could not copy automatically. URL: https://fomo.nyc/', 'info']]);
});

function urlParams(search = '') {
    return load('../core/urlParams.js', 'URLParams', {
        window: { location: { origin: 'https://fomo.nyc', pathname: '/', search } }
    });
}

test('event links center on the venue and name the event', () => {
    const url = new URL(urlParams().generateEventUrl({ id: 294615, lat: 40.75635, lng: -73.92395 }));
    assert.equal(url.origin + url.pathname, 'https://fomo.nyc/');
    assert.deepEqual(Object.fromEntries(url.searchParams), { lat: '40.75635', lng: '-73.92395', zoom: '16.00', event: '294615' });
});

test('an event link parses back into its event id and map view', () => {
    const params = urlParams('?lat=40.75635&lng=-73.92395&zoom=16.00&event=294615').parse();
    assert.equal(params.event, '294615');
    assert.equal(params.lat, 40.75635);
    assert.equal(params.zoom, 16);
    assert.equal(urlParams('?event=<script>').parse().event, undefined);
});
