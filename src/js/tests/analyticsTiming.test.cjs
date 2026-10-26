const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Runs beacon.js + analytics.js on the production hostname with a fake
// performance timeline, and returns the beacons they send.
function setup({ markBeforeStart = null } = {}) {
    const beacons = [], listeners = {}, marks = [], observers = [];
    if (markBeforeStart) marks.push(markBeforeStart);
    const document = {
        visibilityState: 'visible', readyState: 'complete', referrer: '', currentScript: null,
        addEventListener: (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); },
        querySelector: () => null, getElementById: () => null
    };
    const performance = {
        now: () => 1000,
        getEntriesByName: name => marks.filter(m => m.name === name)
    };
    class PerformanceObserver {
        constructor(callback) { this.callback = callback; observers.push(this); }
        observe() {}
        disconnect() { this.callback = null; }
    }
    const context = vm.createContext({
        window: { __CITY__: { domain: 'fomo.example', timezone: 'America/New_York' }, addEventListener() {}, matchMedia: () => ({ matches: false }), devicePixelRatio: 2, innerWidth: 400, innerHeight: 800 },
        document, performance, PerformanceObserver, MutationObserver: class { observe() {} },
        location: { hostname: 'fomo.example', pathname: '/', search: '' },
        navigator: { userAgent: 'test', language: 'en-US', sendBeacon: (url, body) => { beacons.push(JSON.parse(body)); return true; } },
        screen: { width: 400, height: 800 }, Intl, URL, URLSearchParams, Element: class {}, setTimeout, clearTimeout
    });
    for (const file of ['../core/beacon.js', '../core/analytics.js']) {
        vm.runInContext(fs.readFileSync(path.join(__dirname, file), 'utf8'), context);
    }
    return {
        timings: () => beacons.filter(b => b.type === 'timing'),
        mark: (startTime, source) => {
            const entry = { name: 'fomo:markers-visible', startTime, detail: { source } };
            marks.push(entry);
            for (const o of observers) if (o.callback) o.callback({ getEntriesByName: name => (name === entry.name ? [entry] : []) });
        },
        hide: () => { document.visibilityState = 'hidden'; (listeners.visibilitychange || []).forEach(fn => fn()); }
    };
}

test('time to markers is sent once, as soon as the app marks the markers visible', () => {
    const h = setup();
    assert.equal(h.timings().length, 0);
    h.mark(3456.7, 'network');
    h.hide();
    assert.deepEqual(h.timings().map(t => [t.markersMs, t.source]), [[3457, 'network']]);
});

test('a mark made before Analytics starts is still reported', () => {
    const h = setup({ markBeforeStart: { name: 'fomo:markers-visible', startTime: 900, detail: { source: 'cache' } } });
    assert.deepEqual(h.timings().map(t => [t.markersMs, t.source]), [[900, 'cache']]);
});

test('hiding the page before the markers appear reports "left before markers" once', () => {
    const h = setup();
    h.hide();
    h.mark(9000, 'network');
    h.hide();
    assert.deepEqual(h.timings().map(t => t.markersMs), [null]);
});
