const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../data/discoveryRanking.js'), 'utf8');

function setup(saved = '[]', failWrites = false) {
    const storage = new Map([['fomo.interests.v1:test', saved]]);
    const context = vm.createContext({
        window: { addEventListener() {} }, location: { host: 'test' }, URL,
        document: { dispatchEvent() {} }, CustomEvent: class {},
        localStorage: {
            getItem: key => storage.get(key),
            setItem: (key, value) => { if (failWrites) throw Error('quota'); storage.set(key, value); }
        }
    });
    vm.runInContext(source + '\nthis.ranking = DiscoveryRanking;', context);
    return { r: context.ranking, storage };
}

const place = { name: 'A Library', address: '10 Main Street', lat: 40, lng: -74, tags: ['Children'] };
const event = { id: 1, name: 'An evening of jazz', description: 'Live jazz quartet',
    tags: ['Jazz', 'Concert'], location: 'A Library', urls: ['https://example.org/event'] };

test('all four exact signal types count once, and negatives subtract', () => {
    const { r } = setup();
    r.set('event', '1', event.name, 1);
    r.set('place', r.placeKey(place), place.name, 1);
    r.set('tag', 'Jazz', 'Jazz', 1);
    r.set('term', 'jazz quartet', 'jazz quartet', -1);
    const result = r.details(event, place);
    assert.equal(result.personal, 2);
    assert.equal(result.matches.length, 4);
    assert.equal(r.details({ ...event, tags: ['Jazz', 'Jazz'] }, place).personal, 2);
});

test('changing/removing a preference invalidates cached scores and survives reload', () => {
    const { r, storage } = setup();
    r.set('event', '1', event.name, 1);
    assert.equal(r.details(event, place).personal, 1);
    r.set('event', '1', event.name, -1);
    assert.equal(r.details(event, place).personal, -1);
    const restored = setup(storage.get('fomo.interests.v1:test')).r;
    assert.equal(restored.details(event, place).personal, -1);
    r.remove('event', '1');
    assert.equal(r.details(event, place).personal, 0);
});

test('venue audience does not spill into events; event dislikes do not penalize neighbors', () => {
    const { r } = setup();
    r.set('tag', 'Children', 'Children', -1);
    r.set('event', '2', 'Camp', -1);
    assert.equal(r.details(event, place).personal, 0);
    assert.equal(r.details({ ...event, id: 2, tags: ['Children'] }, place).personal, -2);
});

test('place preference survives display-coordinate changes and distinguishes addresses', () => {
    const { r } = setup();
    r.set('place', r.placeKey(place), place.name, 1);
    assert.equal(r.details(event, { ...place, lat: 40.000001 }).personal, 1);
    assert.equal(r.details(event, { ...place, address: '12 Main Street' }).personal, 0);
});

test('terms use exact whole phrases, not substrings or semantic expansion', () => {
    const { r } = setup(); r.set('term', 'jazz', 'Jazz', 1);
    assert.equal(r.details(event, place).personal, 1);
    assert.equal(r.details({ ...event, name: 'Jazzercise', description: '', tags: [] }, place).personal, 0);
    const late = { ...event, name: 'Music night', description: '', tags: [] };
    assert.equal(r.details(late, place).personal, 0);
    late.description = 'Jazz tonight';
    assert.equal(r.details(late, place).personal, 1);
});

test('editing a term removes its old influence', () => {
    const { r } = setup(); r.set('term', 'jazz', 'jazz', 1);
    r.renameTerm('jazz', 'theater');
    assert.equal(r.details(event, place).personal, 0);
    assert.equal(r.entries().length, 1);
    assert.equal(r.entries()[0].id, 'theater');
});

test('new-user baseline is bounded, avoids duplicate-host votes, and cannot outweigh an exact match', () => {
    const { r } = setup();
    assert.equal(r.baseline(event), 1);
    assert.equal(r.baseline({ ...event, tags: ['Concert', 'Performance', 'Live Music'],
        urls: ['https://example.org/a', 'https://www.example.org/b'] }), 1);
    const popular = { ...event, tags: ['Festival', 'Concert', 'Exhibition', 'Free'],
        urls: ['https://one.org', 'https://two.org', 'https://three.org', 'https://four.org'] };
    assert.equal(r.baseline(popular), 6);
    r.set('event', '2', 'A quiet event', 1);
    assert.ok(r.score({ id: 2 }, place) > r.score(popular, place));
});

test('top N is viewport-local, bounded with pins, deterministic, and promotes remaining places after zoom', () => {
    const { r } = setup();
    const points = [{ key: 'a', score: 4 }, { key: 'b', score: 3 }, { key: 'c', score: 1 }];
    assert.equal([...r.topPlaces(points, 2)].join(','), 'a,b');
    assert.equal([...r.topPlaces(points, 2, ['c'])].join(','), 'c,a');
    assert.equal([...r.topPlaces(points.slice(2), 2)].join(','), 'c');
    assert.equal(r.topPlaces(points, 2, ['missing', 'c', 'b', 'a']).size, 2);
    assert.equal([...r.topPlaces([{ key: 'z', score: 1 }, { key: 'a', score: 1 }], 1)][0], 'a');
});

test('malformed stored data and unavailable storage leave a usable session', () => {
    assert.equal(setup('{broken').r.entries().length, 0);
    const { r } = setup('[]', true);
    assert.equal(r.set('tag', 'Jazz', 'Jazz', 1), true);
    assert.equal(r.canPersist(), false);
    assert.equal(r.details(event, place).personal, 1);
    assert.equal(r.set('term', '!!!', '!!!', 1), false);
});

test('retired tag favorites migrate once; an explicit canonical stance wins collisions', () => {
    const { r, storage } = setup();
    r.set('tag', 'Children', 'Children', 1);
    r.set('tag', 'Kids', 'Kids', -1);
    r.set('tag', 'AI', 'AI', 1);
    r.migrateTagAliases({Children:'Kids', AI:'Artificial Intelligence'});
    assert.equal(r.entries().length,2);
    assert.equal(r.stance('tag','Kids'),-1);
    assert.equal(r.stance('tag','Artificial Intelligence'),1);
    const version = r.revision();
    r.migrateTagAliases({Children:'Kids', AI:'Artificial Intelligence'});
    assert.equal(r.revision(),version);
    const restored = setup(storage.get('fomo.interests.v1:test')).r;
    assert.equal(restored.details({id:9,tags:['Artificial Intelligence']},{}).personal,1);
});
