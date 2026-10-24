const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
function harness({ reducedMotion = true } = {}) {
    const images = new Map(), layouts = new Map(), requests = [], hoverRequests = [];
    const layers = new Map(), filters = new Map(), filterCalls = [], featureStates = new Map();
    const dataUpdates = [];
    const handlers = new Map(), timers = new Map();
    let nextTimer = 0;
    const animationFrames = new Map();
    let now = 0, nextFrame = 0;
    let data, theme = 'light', projectX = 500;
    const rect = { left: 0, top: 0, right: 1000, bottom: 700 };
    const source = { setData: value => { data = value; dataUpdates.push(value); } };
    const map = {
        on: (name, fn) => handlers.set(name, [...(handlers.get(name) || []), fn]), isStyleLoaded: () => true, getSource: () => source, addSource() {},
        addLayer: layer => layers.set(layer.id, layer), getLayer: id => layers.get(id),
        setPaintProperty() {}, getCanvas: () => ({ getBoundingClientRect: () => rect }),
        getBounds: () => ({ contains: () => true }), project: () => ({ x: projectX, y: 350 }),
        hasImage: id => images.has(id), listImages: () => [...images.keys()],
        addImage: (id, pixels) => images.set(id, pixels), updateImage: (id, pixels) => images.set(id, pixels),
        removeImage: id => images.delete(id),
        setFeatureState: ({ id }, value) => featureStates.set(id, { ...featureStates.get(id), ...value }),
        setFilter: (id, value) => { filters.set(id, value); filterCalls.push(id); },
        setLayoutProperty: (id, key, value) => layouts.set(key, value)
    };
    const context = vm.createContext({
        window: { devicePixelRatio: 1, matchMedia: () => ({ matches: reducedMotion }) }, innerWidth: 1000, innerHeight: 700,
        performance: { now: () => now },
        setTimeout: (fn, ms) => { timers.set(++nextTimer, fn); return nextTimer; },
        clearTimeout: id => timers.delete(id),
        requestAnimationFrame: fn => { animationFrames.set(++nextFrame, fn); return nextFrame; },
        cancelAnimationFrame: id => animationFrames.delete(id),
        document: { getElementById: id => id === 'map-container' ? { getBoundingClientRect: () => rect } : null,
            createElement: () => ({ getContext: () => ({ measureText: text => ({ width: text.length * 8 }) }) }) },
        Utils: { isMobileLayout: () => false,
            getCurrentTheme: () => theme,
            stripCountryFlagEmoji: value => value,
            parseLocationKey: key => { const [lat, lng] = key.split(',').map(Number); return { lat, lng }; }
        },
        ColorUtils: { oklchHueFromHex: () => 30, oklchToHex: () => '#123456' },
        IconManager: {
            mapSpriteSize: () => 78,
            resolve: event => ({ id: event?.icon_id || event?.emoji || 'fallback', revision: '1' }),
            getColor: () => '#123456',
            prepare: (descriptor, theme, variant, formatCategory) => new Promise(done =>
                (variant === 'hover' ? hoverRequests : requests).push({ descriptor, theme, variant, formatCategory, done }))
        },
        DiscoveryRanking: { score: event => event.score || 0,
            topPlaces: (candidates, limit, pinned = []) => new Set(
                [...new Set([...pinned, ...candidates.map(c => c.key)])].slice(0, limit)) }
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../core/formatColors.js'), 'utf8'), context);
    vm.runInContext("FormatColors.configure({Performance:['Concert'], Participatory:['Workshop']})", context);
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../map/mapManager.js'), 'utf8'), context);
    const manager = vm.runInContext('MapManager', context); manager.init(map);
    const key = '40.7,-74', locations = { [key]: { name: 'Venue', emoji: '🏛️' } };
    return { manager, images, requests, hoverRequests, layouts, layers, filters, filterCalls, featureStates, dataUpdates, key, locations, data: () => data,
        setTheme: value => { theme = value; },
        setProjectX: value => { projectX = value; },
        fire: name => (handlers.get(name) || []).forEach(fn => fn()),
        runTimers: () => { const pending = [...timers.values()]; timers.clear(); pending.forEach(fn => fn()); },
        animationFrames,
        advance: ms => {
            now += ms;
            const callbacks = [...animationFrames.values()];
            animationFrames.clear();
            callbacks.forEach(fn => fn(now));
        },
        render: events => manager.updateMarkerData({ [key]: events }, locations, new Map()) };
}
test('icon and primary label follow the same ranked event and filter changes', () => {
    const h = harness();
    h.render([{ id: 1, name: 'Painting', icon_id: 'paint' }, { id: 2, name: 'Jazz night', icon_id: 'jazz', score: 10 }]);
    const [icon, label] = h.data().features.map(f => f.properties);
    assert.equal(icon.iconImageId, 'icon-jazz-1-format-other');
    assert.equal(label.eventLabel, 'Jazz night'); assert.equal(label.eventLabelExtra, ' +1');
    assert.equal(label.locationName, undefined);
    h.render([{ id: 1, name: 'Painting', icon_id: 'paint' }]);
    assert.equal(h.data().features[0].properties.iconImageId, 'icon-paint-1-format-other');
    assert.equal(h.data().features[1].properties.eventLabelExtra, '');
});
test('hover keeps every promoted icon and label in collision placement without refiltering', () => {
    const h = harness(), second = '40.8,-74';
    h.manager.updateMarkerData({ [h.key]: [{ name: 'Painting' }], [second]: [{ name: 'Music' }] },
        { ...h.locations, [second]: { name: 'Another venue' } }, new Map());
    const initialFilter = JSON.stringify(h.filters.get('marker-symbols'));
    h.filterCalls.length = 0;
    for (const key of [second, h.key]) {
        h.manager.highlightLocationByKey(key);
        assert.equal(JSON.stringify(h.filters.get('marker-symbols')), initialFilter);
        assert.ok(!h.filterCalls.includes('marker-symbols'));
        const ids = h.data().features.flatMap((f, id) => f.properties.locationKey === key ? [id] : []);
        assert.equal(ids.length, 2);
        ids.forEach(id => assert.equal(h.featureStates.get(id).hover, true));
    }
    h.manager.clearHoverHighlight();
    assert.ok(!h.filterCalls.includes('marker-symbols'));
    for (const value of h.featureStates.values()) assert.equal(value.hover, false);
    const normal = h.layers.get('marker-symbols');
    for (const kind of ['icon', 'text']) {
        assert.equal(normal.layout[`${kind}-ignore-placement`], false);
        assert.ok(JSON.stringify(normal.paint[`${kind}-opacity`]).includes('feature-state'));
        assert.equal(h.layers.get('marker-symbols-hover').layout[`${kind}-ignore-placement`], true);
    }
});
test('promoted icons decode a hover sprite variant that the hover layer draws instead of a ring', async () => {
    const h = harness(); h.render([{ id: 1, name: 'Painting', icon_id: 'paint' }]);
    assert.equal(h.layers.get('marker-highlight'), undefined);
    assert.ok(JSON.stringify(h.layers.get('marker-symbols-hover').layout['icon-image']).includes('-hover'));
    assert.ok(!JSON.stringify(h.layers.get('marker-symbols').layout['icon-image']).includes('-hover'));
    assert.equal(h.requests.length, 1); assert.equal(h.hoverRequests.length, 1);
    assert.equal(h.hoverRequests[0].descriptor.id, 'paint');
    assert.equal(h.images.get('icon-paint-1-format-other-hover').width, 78, 'the placeholder slot matches the hover sprite size');
    h.hoverRequests[0].done({ pixels: 'hover pixels', accent: '#123456' });
    await Promise.resolve();
    assert.equal(h.images.get('icon-paint-1-format-other-hover'), 'hover pixels');
    h.manager.highlightLocationByKey(h.key, { labelEvent: { name: 'Jazz night', icon_id: 'jazz' } });
    assert.ok(JSON.stringify(h.layouts.get('icon-image')).includes('icon-jazz-1-format-other-hover'));
    assert.equal(h.hoverRequests.at(-1).descriptor.id, 'jazz');
    assert.equal(h.requests.length, 1, 'a list-row hover only needs the hover variant');
});
test('replacing marker data clears hover on the old sparse label IDs', () => {
    const h = harness(); h.render([{ name: 'Painting' }]);
    h.manager.highlightLocationByKey(h.key);
    h.render([{ name: '' }]);
    assert.equal(h.featureStates.get(0).hover, false);
    assert.equal(h.featureStates.get(1).hover, false);
});
test('list hover switches artwork and name together and clears both overrides', () => {
    const h = harness(); h.render([{ id: 1, name: 'Painting', icon_id: 'paint' }]);
    h.manager.highlightLocationByKey(h.key, { labelEvent: { name: 'Jazz night', icon_id: 'jazz' } });
    assert.ok(JSON.stringify(h.layouts.get('icon-image')).includes('icon-jazz-1-format-other'));
    assert.ok(JSON.stringify(h.layouts.get('text-field')).includes('Jazz night'));
    h.manager.clearHoverHighlight();
    assert.ok(!JSON.stringify(h.layouts.get('icon-image')).includes('icon-jazz-1-format-other'));
    assert.ok(!JSON.stringify(h.layouts.get('text-field')).includes('Jazz night'));
});
test('map and hover labels compose accents before layout and truncation', () => {
    const h = harness();
    const event = { id: 1, name: 'Simo\u0301n Willson Quartet', icon_id: 'jazz' };
    h.render([event]);
    assert.equal(h.data().features[1].properties.eventLabel, 'Simón Willson Quartet');
    h.manager.highlightLocationByKey(h.key, { labelEvent: event });
    const hoverText = JSON.stringify(h.layouts.get('text-field'));
    assert.ok(hoverText.includes('Simón Willson Quartet'));
    assert.ok(!hoverText.includes('\u0301'));
    assert.equal(event.name, 'Simo\u0301n Willson Quartet');

    // This short name fits without an ellipsis once its accents are composed.
    h.render([{ ...event, short_name: 'Cafe\u0301 Cafe\u0301 Cafe\u0301 Cafe\u0301 Cafe\u0301' }]);
    assert.equal(h.data().features[1].properties.eventLabel, 'Café Café Café Café Café');
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
    assert.equal(h.hoverRequests.length, 20, 'each promoted icon also decodes its hover variant');
    assert.equal(h.images.size, 40);
});

test('late artwork updates pixels and accent without replacing data or re-placing labels', async () => {
    const h = harness();
    h.render([{ id: 1, name: 'Painting', icon_id: 'paint' }]);
    const updates = h.dataUpdates.length, filters = h.filterCalls.length;
    h.requests[0].done({ pixels: 'paint pixels', accent: '#123456' });
    await Promise.resolve();
    assert.equal(h.images.get('icon-paint-1-format-other'), 'paint pixels');
    assert.equal(h.featureStates.get(0).accent, '#123456');
    assert.equal(h.dataUpdates.length, updates);
    assert.equal(h.filterCalls.length, filters);

    h.render([{ id: 2, name: 'Music', icon_id: 'music' }]);
    assert.equal(h.featureStates.get(0).accent, null, 'a reused feature ID cannot inherit the previous icon color');
});

test('an old search icon cannot recolor a replacement result', async () => {
    const h = harness();
    h.render([{ id: 1, name: 'Painting', icon_id: 'paint' }]);
    h.render([{ id: 2, name: 'Music', icon_id: 'music' }]);
    const updates = h.dataUpdates.length;
    h.requests[0].done({ pixels: 'paint pixels', accent: '#123456' });
    await Promise.resolve();
    assert.notEqual(h.featureStates.get(0)?.accent, '#123456');
    assert.equal(h.dataUpdates.length, updates);
});

test('applying marker theme paint does not replace the data source', () => {
    const h = harness();
    h.render([{ id: 1, name: 'Painting', icon_id: 'paint' }]);
    const updates = h.dataUpdates.length;
    h.manager.applyThemeToLayers();
    assert.equal(h.dataUpdates.length, updates);
});

test('late artwork fades its pixels over 150ms without touching marker placement', async () => {
    const h = harness({ reducedMotion: false });
    h.render([{ id: 1, name: 'Painting', icon_id: 'paint' }]);
    const pixels = { width: 78, height: 78, data: new Uint8Array(78 * 78 * 4) };
    pixels.data.set([100, 150, 200, 255]);
    const updates = h.dataUpdates.length, filters = h.filterCalls.length;
    h.requests[0].done({ pixels, accent: '#123456' });
    await Promise.resolve();
    assert.equal(h.images.get('icon-paint-1-format-other').data[3], 0);
    h.advance(75);
    assert.deepEqual(Array.from(h.images.get('icon-paint-1-format-other').data.slice(0, 4)), [100, 150, 200, 128]);
    assert.equal(pixels.data[3], 255, 'cached pixels must retain their original alpha');
    h.advance(75);
    assert.equal(h.images.get('icon-paint-1-format-other'), pixels);
    assert.equal(h.animationFrames.size, 0);
    assert.equal(h.dataUpdates.length, updates);
    assert.equal(h.filterCalls.length, filters);
});

test('theme reload cancels an in-flight artwork fade', async () => {
    const h = harness({ reducedMotion: false });
    h.render([{ name: 'Painting', icon_id: 'paint' }]);
    const pixels = { width: 78, height: 78, data: new Uint8Array(78 * 78 * 4).fill(255) };
    h.requests[0].done({ pixels, accent: '#123456' });
    await Promise.resolve();
    h.advance(75);
    h.setTheme('dark');
    h.manager.reloadIconImages();
    h.advance(150);
    assert.equal(h.images.get('icon-paint-1-format-other').data[3], 0);
    assert.equal(h.animationFrames.size, 0);
});

test('a newly promoted marker fades even when another marker already uses its cached sprite', async () => {
    const h = harness({ reducedMotion: false });
    const event = { name: 'Painting', icon_id: 'paint' };
    h.render([event]);
    const pixels = { width: 78, height: 78, data: new Uint8Array(78 * 78 * 4).fill(255) };
    h.requests[0].done({ pixels, accent: '#123456' });
    await Promise.resolve();
    h.advance(150);
    const second = '40.8,-74';
    h.manager.updateMarkerData({ [h.key]: [event], [second]: [event] },
        { ...h.locations, [second]: { name: 'Second venue' } }, new Map());
    assert.notEqual(h.featureStates.get(0)?.iconOpacity, 0, 'existing marker stays visible');
    assert.equal(h.featureStates.get(1).iconOpacity, 0);
    h.advance(75);
    assert.equal(h.featureStates.get(1).iconOpacity, 0.5);
    assert.equal(h.images.get('icon-paint-1-format-other'), pixels, 'the shared sprite must stay fully opaque');
    h.advance(75);
    assert.equal(h.featureStates.get(1).iconOpacity, 1);
    assert.equal(h.requests.length, 1);
});

// A reused icon must not reuse another event format's background or hover sprite.
test('ranked format follows filtering, rekeys shared artwork, and reaches hover rendering', () => {
    const h = harness();
    h.render([{ id: 1, name: 'Music lesson', icon_id: 'music', event_type: 'Workshop', tags: ['Concert'] },
        { id: 2, name: 'Concert', icon_id: 'music', event_type: 'Concert', score: 10 }]);
    assert.equal(h.data().features[0].properties.formatCategory, 'Performance');
    assert.equal(h.data().features[0].properties.iconImageId, 'icon-music-1-format-performance');
    assert.equal(h.requests.at(-1).formatCategory, 'Performance');
    h.manager.highlightLocationByKey(h.key, { labelEvent: { id: 1, name: 'Music lesson', icon_id: 'music', event_type: 'Workshop' } });
    assert.equal(h.hoverRequests.at(-1).formatCategory, 'Participatory');
    h.render([{ id: 1, name: 'Music lesson', icon_id: 'music', event_type: 'Workshop', tags: ['Concert'] }]);
    assert.equal(h.data().features[0].properties.formatCategory, 'Participatory');
    assert.equal(h.data().features[0].properties.iconImageId, 'icon-music-1-format-participatory');
    const dotPaint = JSON.stringify(h.layers.get('marker-dots').paint['circle-color']);
    assert.ok(dotPaint.includes('formatCategory'));
});
test('long names emit full-to-short label tiers that the hover layer narrows to the longest', () => {
    const h = harness(), name = 'Brooklyn Botanic Garden Chili Pepper Fiesta';
    h.render([{ id: 1, name }]);
    const labels = h.data().features.filter(f => f.properties.labelType === 'expanded').map(f => f.properties);
    assert.deepEqual([...labels.map(l => l.eventLabel)],
        [name, 'Brooklyn Botanic Garden Chili Pepper…', 'Brooklyn Botanic Garden Chili…',
            'Brooklyn Botanic Garden…', 'Brooklyn Botanic…']);
    assert.deepEqual([...labels.map(l => l.labelTier)], [0, 1, 2, 3, 4]);
    // Each location tries its tiers longest first, before any further-south location.
    for (let i = 1; i < labels.length; i++) assert.ok(labels[i].sortKey > labels[i - 1].sortKey);
    assert.ok(labels.at(-1).sortKey < -5000 - 40.69);
    h.manager.highlightLocationByKey(h.key);
    assert.ok(JSON.stringify(h.filters.get('marker-symbols-hover')).includes('labelTier'));
    h.data().features.forEach((f, id) => assert.equal(h.featureStates.get(id).hover, true));
});
test('short names keep one label and very long names are capped', () => {
    const h = harness();
    h.render([{ id: 1, name: 'Twenty-five characters ok' }]);
    assert.deepEqual([...h.data().features.slice(1).map(f => f.properties.eventLabel)], ['Twenty-five characters ok']);
    h.render([{ id: 1, name: 'Salsa, Bachata & Kizomba Social Night' }]);
    assert.equal(h.data().features.at(-1).properties.eventLabel, 'Salsa, Bachata…', 'cuts drop trailing punctuation');
    h.render([{ id: 1, name: 'x'.repeat(80) }]);
    const labels = h.data().features.slice(1).map(f => f.properties.eventLabel);
    assert.equal(labels[0], 'x'.repeat(56) + '…');
    assert.equal(labels.at(-1), 'x'.repeat(22) + '…');
});
test('labels near the right edge skip tiers that would run off screen', () => {
    const h = harness();
    h.render([{ id: 1, name: 'Brooklyn Botanic Garden Chili Pepper Fiesta' }]);
    assert.ok(!JSON.stringify(h.filters.get('marker-symbols')).includes('labelTier'), 'centered labels may use every tier');
    // 300px of room minus the 1.8em text offset fits 30 of the stub's 8px characters.
    h.setProjectX(700); h.manager.refreshPromotedMarkers();
    const filter = JSON.stringify(h.filters.get('marker-symbols'));
    assert.ok(filter.includes(`["match",["get","locationKey"],"${h.key}",2,0]`), filter);
    h.setProjectX(500); h.manager.refreshPromotedMarkers();
    assert.ok(!JSON.stringify(h.filters.get('marker-symbols')).includes('labelTier'));
});
test('promotion refreshes once the camera settles, without waiting for moveend', () => {
    const h = harness();
    h.render([{ id: 1, name: 'Brooklyn Botanic Garden Chili Pepper Fiesta' }]);
    h.setProjectX(700);
    h.fire('move'); h.fire('move');
    assert.ok(!JSON.stringify(h.filters.get('marker-symbols')).includes('labelTier'), 'nothing while the camera moves');
    h.runTimers();
    assert.ok(JSON.stringify(h.filters.get('marker-symbols')).includes('labelTier'), 'the settled camera refreshes promotion');
    h.filterCalls.length = 0;
    h.fire('move'); h.fire('moveend'); h.runTimers();
    assert.ok(!h.filterCalls.includes('marker-symbols'), 'moveend cancels the pending settle and refilters nothing new');
});
