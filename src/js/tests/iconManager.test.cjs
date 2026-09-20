const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
// Generated assets are not tracked; support running tests on a fresh checkout.
require('../../../config/event-icons/build.cjs').buildIcons();
function setup(extra = {}) {
    const context = vm.createContext({ window: { devicePixelRatio: 1 }, ...extra });
    for (const file of ['core/colorUtils.js', 'core/formatColors.js', 'core/eventIconCatalog.js', 'ui/iconManager.js']) {
        vm.runInContext(fs.readFileSync(path.join(__dirname, '..', file), 'utf8'), context);
    }
    return vm.runInContext('({ manager: IconManager, catalog: IconCatalog })', context);
}
test('Noto and custom assignments resolve to the same artwork contract', () => {
    const { manager } = setup();
    assert.match(manager.resolve({ icon_id: 'game-go', emoji: '🌳' }).url, /game-go\.[a-f0-9]+\.svg$/);
    assert.match(manager.resolve({ emoji: '🌳' }).url, /noto-1f333\.[a-f0-9]+\.svg$/);
    assert.equal(manager.resolve({ name: 'Go Club', emoji: '🌳' }).id, 'noto-1f333');
    assert.deepEqual(Object.keys(manager.resolve({ icon_id: 'game-go' })), Object.keys(manager.resolve({ emoji: '🌳' })));
});
test('unknown or malicious IDs and unknown emoji always use bundled artwork', () => {
    const { manager, catalog } = setup();
    assert.equal(manager.resolve(null).id, catalog.fallbackId);
    for (const icon_id of ['unknown','__proto__','constructor','https://elsewhere/a.svg','../a.svg']) {
        assert.equal(manager.resolve({ icon_id, emoji: '🎉' }).id, 'noto-1f389');
    }
    for (const emoji of [undefined, '', 'constructor', '__proto__', 'not-an-emoji']) {
        assert.equal(manager.resolve({ emoji }).id, catalog.fallbackId);
    }
});
test('presentation selectors and flags resolve identically on every platform', () => {
    const { manager } = setup();
    assert.equal(manager.resolve({ emoji: '🖨️' }).id, manager.resolve({ emoji: '🖨' }).id);
    assert.equal(manager.resolve({ emoji: '🇺🇸' }).id, 'noto-1f1fa-1f1f8');
    assert.equal(manager.resolve({ emoji: '👩🏽‍💻' }).id, 'noto-1f469-1f3fd-200d-1f4bb');
});
test('tag associations are exact and saved assignment edits invalidate caches', () => {
    const { manager } = setup();
    const ids = { MTG: 'game-mtg' };
    manager.setTagIcons(ids, { Games: '🎲' });
    assert.match(manager.tagCacheKey('MTG'), /game-mtg/);
    assert.match(manager.tagCacheKey('Games'), /noto-1f3b2/);
    assert.match(manager.tagCacheKey('mtg'), /noto-1f4c5/);
    const old = manager.tagCacheKey('MTG'); ids.MTG = 'bingo';
    assert.notEqual(manager.tagCacheKey('MTG'), old);
});
test('failed assets use embedded fallback; concurrent requests share one decode', async () => {
    const requests = [];
    const { manager, catalog } = setup({
        Image: class { set src(value) { this._src = value; requests.push(this); } get src() { return this._src; } },
        Utils: { getCurrentTheme: () => 'dark' },
        TagColorManager: { extractColorFromPixels: () => '#123456' },
        document: { createElement: () => ({ getContext: () => ({ drawImage() {}, putImageData() {}, getImageData: () => ({ data: new Uint8Array(4) }) }) }) }
    });
    const descriptor = manager.resolve({ icon_id: 'game-go' });
    const first = manager.prepare(descriptor), second = manager.prepare(descriptor);
    assert.equal(first, second); assert.equal(requests.length, 1);
    requests[0].onerror();
    await Promise.resolve(); await Promise.resolve();
    assert.equal(requests[1].src, catalog.fallbackUrl);
    requests[1].onload();
    const result = await first;
    assert.equal(result.url, catalog.fallbackUrl);
    assert.equal(result.accent, '#123456');
});

function hexChannels(hex) {
    return [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
}
test('disc colors follow format hues, pin per-theme tint, and use neutral for unclassified events', () => {
    const { manager } = setup({ Utils: { getCurrentTheme: () => 'light' } });
    const light = manager.discColors('Social', 'light'), dark = manager.discColors('Social', 'dark');
    const [lr, lg, lb] = hexChannels(light.fill), [dr, dg, db] = hexChannels(dark.fill);
    assert.ok(lr > lg && lr > lb && lr > 220, `light fill is a pale red tint: ${light.fill}`);
    assert.deepEqual([dr, dg, db], [34, 34, 34], 'dark fill matches the neutral UI background');
    assert.notEqual(light.stroke, light.fill);
    assert.ok(hexChannels(light.stroke)[0] < lr, 'the border is darker than the fill in light mode');
    assert.ok(hexChannels(dark.stroke)[0] > dr, 'the border is lighter than the fill in dark mode');
    for (const theme of ['light', 'dark']) {
        const gray = manager.discColors('Other', theme);
        for (const color of [gray.fill, gray.stroke]) {
            const [r, g, b] = hexChannels(color);
            assert.ok(Math.max(r, g, b) - Math.min(r, g, b) <= 2, `${theme} fallback disc is neutral: ${color}`);
        }
    }
    assert.deepEqual(manager.discColors('Social'), light, 'defaults to the current theme');
});
test('map sprites composite a tinted disc under the artwork without polluting the accent', async () => {
    const ops = [], requests = [];
    const ctx = {
        globalCompositeOperation: 'source-over', lineWidth: 1, fillStyle: '', strokeStyle: '',
        drawImage: (...args) => ops.push(['drawImage', ...args.slice(1)]),
        getImageData: (...args) => { ops.push(['getImageData', ctx.globalCompositeOperation, args[2]]); return { data: new Uint8Array(4), args }; },
        beginPath: () => ops.push(['beginPath']),
        arc: (...args) => ops.push(['arc', ...args]),
        stroke() { ops.push(['stroke', ctx.strokeStyle, ctx.lineWidth, ctx.globalCompositeOperation]); },
        fill() { ops.push(['fill', ctx.fillStyle, ctx.globalCompositeOperation]); }
    };
    const extracted = [];
    const { manager } = setup({
        Image: class { set src(value) { this._src = value; requests.push(this); } get src() { return this._src; } },
        Utils: { getCurrentTheme: () => 'dark' },
        TagColorManager: { extractColorFromPixels: pixels => { extracted.push(pixels); return '#d02020'; } },
        document: { createElement: () => ({ getContext: () => ctx }) }
    });
    const descriptor = manager.resolve({ icon_id: 'game-go' });
    const promise = manager.prepare(descriptor, 'dark', true, 'Social');
    assert.equal(manager.prepare(descriptor, 'dark', true, 'Social'), promise);
    requests[0].onload();
    const result = await promise;
    const disc = manager.discColors('Social', 'dark');
    assert.equal(result.accent, '#d02020');
    assert.equal(manager.getColor({ icon_id: 'game-go' }, 'dark'), '#d02020');
    assert.equal(extracted.length, 1);
    assert.deepEqual(ops.map(op => op[0]), ['drawImage', 'getImageData', 'beginPath', 'arc', 'stroke', 'beginPath', 'arc', 'fill', 'getImageData']);
    assert.deepEqual(ops[0].slice(1), [28, 20, 38, 38], 'artwork keeps an 11px margin inside the 60px disc');
    assert.equal(ops[1][1], 'source-over', 'the accent is extracted before the disc is drawn');
    assert.deepEqual(ops[3].slice(1, 4), [47, 39, 29.25], 'border is centered inside the disc edge');
    assert.deepEqual(ops[4].slice(1), [disc.stroke, 1.5, 'destination-over']);
    assert.deepEqual(ops[6].slice(1, 4), [47, 39, 30]);
    assert.deepEqual(ops[7].slice(1), [disc.fill, 'destination-over']);
    assert.equal(result.pixels.args[2], manager.mapSpriteSize(false), 'the sprite matches the slot MapManager allocates');

    const otherFormat = manager.prepare(descriptor, 'dark', true, 'Performance');
    assert.notEqual(otherFormat, promise, 'the same icon in another format has a separate sprite');
    await otherFormat;
    ops.length = 0;
    const plain = manager.prepare(descriptor, 'dark', false);
    assert.notEqual(plain, promise, 'map sprites are cached apart from UI artwork');
    await plain;
    assert.deepEqual(ops.map(op => op[0]), ['drawImage', 'getImageData'], 'UI artwork gets no disc');
    assert.deepEqual(ops[0].slice(1), [4, 4, 56, 56]);
    assert.equal(ops[1][2], 64, 'UI artwork keeps its 64px canvas');

    ops.length = 0;
    const hovered = await manager.prepare(descriptor, 'dark', 'hover', 'Social');
    assert.deepEqual(ops.map(op => op[0]),
        ['drawImage', 'getImageData', 'beginPath', 'arc', 'stroke', 'beginPath', 'arc', 'fill', 'getImageData'],
        'hover draws no glow');
    assert.deepEqual(ops[0].slice(1), [28, 20, 38, 38], 'hover artwork matches the resting sprite');
    assert.deepEqual(ops[3].slice(1, 4), [47, 39, 28.5]);
    assert.deepEqual(ops[4].slice(1), ['#ffffff', 3, 'destination-over'], 'hover border is thicker and white');
    assert.deepEqual(ops[7].slice(1), [disc.fill, 'destination-over']);
    assert.equal(hovered.pixels.args[2], manager.mapSpriteSize(true));
    assert.equal(manager.mapSpriteSize(true), 78); assert.equal(manager.mapSpriteSize(false), 78);
});
