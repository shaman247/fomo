const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
// Generated assets are not tracked; support running tests on a fresh checkout.
require('../../../config/event-icons/build.cjs').buildIcons();
function setup(extra = {}) {
    const context = vm.createContext({ window: { devicePixelRatio: 1 }, ...extra });
    for (const file of ['core/eventIconCatalog.js', 'ui/iconManager.js']) {
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
        Utils: { getCurrentTheme: () => 'dark' }, Themes: { resolve: () => ({}) },
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
