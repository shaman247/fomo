const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
function harness() {
    const images = new Map(), layouts = new Map(), requests = [];
    let data, theme = 'light';
    const rect = { left: 0, top: 0, right: 1000, bottom: 700 };
    const source = { setData: value => { data = value; } };
    const map = {
        on() {}, isStyleLoaded: () => false, getSource: () => source,
        getLayer: () => true, getCanvas: () => ({ getBoundingClientRect: () => rect }),
        getBounds: () => ({ contains: () => true }), project: () => ({ x: 500, y: 350 }),
        hasImage: id => images.has(id), listImages: () => [...images.keys()],
        addImage: (id, pixels) => images.set(id, pixels), updateImage: (id, pixels) => images.set(id, pixels),
        removeImage: id => images.delete(id), setFeatureState() {}, setFilter() {},
        setLayoutProperty: (id, key, value) => layouts.set(key, value)
    };
    const context = vm.createContext({
        window: { devicePixelRatio: 1 }, innerWidth: 1000, innerHeight: 700,
        requestAnimationFrame: fn => fn(),
        document: { getElementById: id => id === 'map-container' ? { getBoundingClientRect: () => rect } : null },
        Utils: { isMobileLayout: () => false,
            getCurrentTheme: () => theme,
            stripCountryFlagEmoji: value => value,
            parseLocationKey: key => { const [lat, lng] = key.split(',').map(Number); return { lat, lng }; }
        },
        ColorUtils: { oklchHueFromHex: () => 30, oklchToHex: () => '#123456' },
        IconManager: {
            resolve: event => ({ id: event?.icon_id || event?.emoji || 'fallback', revision: '1' }),
            getColor: () => '#123456',
            prepare: (descriptor, theme) => new Promise(done => requests.push({ descriptor, theme, done }))
        },
        DiscoveryRanking: { score: event => event.score || 0,
            topPlaces: (candidates, limit) => new Set(candidates.slice(0, limit).map(c => c.key)) }
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../map/mapManager.js'), 'utf8'), context);
    const manager = vm.runInContext('MapManager', context); manager.init(map);
    const key = '40.7,-74', locations = { [key]: { name: 'Venue', emoji: '🏛️' } };
    return { manager, images, requests, layouts, key, locations, data: () => data,
        setTheme: value => { theme = value; },
        render: events => manager.updateMarkerData({ [key]: events }, locations, new Map()) };
}
test('icon and primary label follow the same ranked event and filter changes', () => {
    const h = harness();
    h.render([{ id: 1, name: 'Painting', icon_id: 'paint' }, { id: 2, name: 'Jazz night', icon_id: 'jazz', score: 10 }]);
    const [icon, label] = h.data().features.map(f => f.properties);
    assert.equal(icon.iconImageId, 'icon-jazz-1');
    assert.equal(label.eventLabel, 'Jazz night'); assert.equal(label.eventLabelExtra, ' +1');
    assert.equal(label.locationName, undefined);
    h.render([{ id: 1, name: 'Painting', icon_id: 'paint' }]);
    assert.equal(h.data().features[0].properties.iconImageId, 'icon-paint-1');
    assert.equal(h.data().features[1].properties.eventLabelExtra, '');
});
test('list hover switches artwork and name together and clears both overrides', () => {
    const h = harness(); h.render([{ id: 1, name: 'Painting', icon_id: 'paint' }]);
    h.manager.highlightLocationByKey(h.key, { labelEvent: { name: 'Jazz night', icon_id: 'jazz' } });
    assert.ok(JSON.stringify(h.layouts.get('icon-image')).includes('icon-jazz-1'));
    assert.ok(JSON.stringify(h.layouts.get('text-field')).includes('Jazz night'));
    h.manager.clearHoverHighlight();
    assert.ok(!JSON.stringify(h.layouts.get('icon-image')).includes('icon-jazz-1'));
    assert.ok(!JSON.stringify(h.layouts.get('text-field')).includes('Jazz night'));
});
test('theme reload discards late sprites from the previous theme', async () => {
    const h = harness(); h.render([{ id: 1, name: 'Go', icon_id: 'game-go' }]);
    const imageId = h.data().features[0].properties.iconImageId;
    const old = h.requests[0];
    h.setTheme('dark'); h.manager.reloadIconImages();
    old.done({ pixels: 'old', accent: '#aaa' }); await Promise.resolve();
    assert.notEqual(h.images.get(imageId), 'old');
    h.requests.at(-1).done({ pixels: 'new', accent: '#bbb' }); await Promise.resolve();
    assert.equal(h.images.get(imageId), 'new');
    assert.equal(h.data().features[0].properties.color, '#bbb');
});
test('offscreen/unpromoted event icons are not eagerly decoded', () => {
    const h = harness(), events = {}, locations = {};
    for (let i = 0; i < 100; i++) {
        const key = `${40 + i / 1000},-74`;
        events[key] = [{ id: i, name: `Event ${i}`, icon_id: `icon${i}` }];
        locations[key] = { name: `Venue ${i}` };
    }
    h.manager.updateMarkerData(events, locations, new Map());
    assert.equal(h.requests.length, 20);
    assert.equal(h.images.size, 20);
});
