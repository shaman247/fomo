const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
function setup(venueTags = [], labels = {}, roots = {}) {
    const ctx = vm.createContext({ console, Set, Map, __CITY__: {venueSelector: {tags: venueTags, labels}, filterRoots: {tag: roots.tag || ["Music", "Art", "Nightlife", "Community", "Dance"], venue: roots.venue || [...venueTags, "Venue", "Event Space"]}} });
    for (const [file, name] of [['core/utils.js', 'Utils'], ['tags/tagStateManager.js', 'TagStateManager'], ['ui/tagSelector.js', 'TagSelector']]) {
        vm.runInContext(fs.readFileSync(path.join(__dirname, '..', file), 'utf8') + `\nthis.${name} = ${name};`, ctx);
    }
    vm.runInContext('this.VenueSelector = VenueSelector;', ctx);
    const states = {};
    // Pure state checks do not require a DOM; button rendering is checked in the browser.
    ctx.TagStateManager.updateAllTagVisuals = () => {};
    ctx.TagStateManager.init({tagStates: states});
    const tree = { Music: ['Jazz', 'Rock'], Jazz: ['Jazz Fusion'], Rock: ['Jazz Fusion'], Art: ['Painting'] };
    const names = ['Music', 'Jazz', 'Rock', 'Jazz Fusion', 'Art', 'Painting'];
    ctx.TagSelector.configure(tree, names);
    return {s: ctx.TagSelector, v: ctx.VenueSelector, t: ctx.TagStateManager, states, tree, names};
}
test('search retains every parent path for tags with multiple parents', () => {
    const {s} = setup();
    s.setSearch('jazz fusion');
    assert.deepEqual([...s.visibleNames()].sort(), ['Jazz', 'Jazz Fusion', 'Music', 'Rock']);
    s.setSearch('does not exist');
    assert.equal(s.visibleNames().length, 0);
});
test('tag choices share existing filter state without overwriting required or excluded filters', () => {
    const {s, t, states} = setup();
    t.setTagState('Art', 'required');
    t.setTagState('Rock', 'forbidden');
    s.setTagSelection('Jazz', true);
    assert.deepEqual(states, {Art: 'required', Rock: 'forbidden', Jazz: 'selected'});
    assert.equal(s.groupState('Music').indeterminate, true);
    assert.equal(s.groupState('Art').checked, true);
    assert.equal(s.groupState('Rock').indeterminate, true);
    s.setTagSelection('Jazz', false);
    assert.equal(states.Jazz, 'unselected');
    assert.equal(states.Art, 'required');
});
test('empty active filters remain reachable and clear also removes organizer filters', () => {
    const {s, t, states} = setup();
    s.setTagSelection('Jazz Fusion', true);
    t.setTagState('organizer:Example', 'forbidden');
    s.updateCounts([]);
    assert.equal(s.visibleNames().includes('Jazz Fusion'), true);
    assert.equal(s.visibleNames().includes('Music'), true);
    assert.equal(s.label(), '2 Tags');
    s.clear();
    assert.equal(Object.values(states).every(state => state === 'unselected'), true);
    assert.equal(s.label(), 'All Tags');
    assert.equal(s.visibleNames().length, 0);
});
test('availability counts deduplicate event and venue membership and refresh keeps selection', () => {
    const {s, tree, names} = setup();
    const e = {id: 1, tags: ['Jazz', 'Music'], locationKey: 'v'};
    s.updateCounts([e, e, {id: 2, tags: [], locationKey: 'v'}], {v: {tags: ['Jazz']}});
    assert.equal(s.count('Jazz'), 2);
    assert.equal(s.count('Music'), 1);
    assert.equal(s.visibleNames().includes('Art'), false);
    s.setTagSelection('Jazz', true);
    s.configure({...tree, Jazz: ['Jazz Fusion', 'New Jazz']}, [...names, 'New Jazz']);
    assert.equal(s.label(), 'Jazz');
    assert.equal(s.groupState('Jazz').checked, true);
    s.setSearch('New Jazz');
    assert.equal(s.visibleNames().includes('New Jazz'), true);
});
test('disconnected cyclic hierarchy components are never promoted to roots', () => {
    const {s} = setup();
    s.configure({A: ['B'], B: ['A']}, ['A', 'B']);
    s.setSearch('B');
    assert.deepEqual([...s.visibleNames()], []);
});


test('venue tags move out of every topic branch without taking activity siblings', () => {
    const {s, v} = setup(['Bar', 'Nightclub', 'Community Center', 'Museum']);
    const tree = {Nightlife: ['Nightclub', 'Clubbing'], Community: ['Community Center'],
        Art: ['Museum', 'Painting'], Venue: ['New Venue Type']};
    const names = ['Venue', 'New Venue Type', 'Nightlife', 'Nightclub', 'Clubbing', 'Bar',
        'Community', 'Community Center', 'Art', 'Museum', 'Painting'];
    s.configure(tree, names); v.configure(tree, names);
    const events = names.map((name, id) => ({id, tags: [name]}));
    s.updateCounts(events); v.updateCounts(events);
    assert.deepEqual([...v.visibleNames()].sort(), ['Bar', 'Community Center', 'Museum', 'New Venue Type', 'Nightclub', 'Venue']);
    assert.deepEqual([...s.visibleNames()].sort(), ['Art', 'Clubbing', 'Community', 'Nightlife', 'Painting']);
    s.setSearch('nightclub'); v.setSearch('nightclub');
    assert.equal(s.visibleNames().length, 0);
    assert.deepEqual([...v.visibleNames()], ['Nightclub']);
});

test('labels and resets are scoped while legacy states and organizer filters survive', () => {
    const {s, v, t, states} = setup(['Bar', 'Museum']);
    v.configure({Museum: ['Art Museum']}, ['Bar', 'Museum', 'Art Museum']);
    t.setTagState('Jazz', 'selected');
    t.setTagState('Bar', 'required');
    t.setTagState('Museum', 'forbidden');
    assert.equal(s.label(), 'Jazz');
    assert.equal(v.label(), '2 Venues');
    s.clear();
    assert.equal(states.Jazz, 'unselected');
    assert.equal(states.Bar, 'required');
    assert.equal(states.Museum, 'forbidden');
    t.setTagState('organizer:Example', 'selected');
    v.clear();
    assert.equal(states.Bar, 'unselected');
    assert.equal(states.Museum, 'unselected');
    assert.equal(states['organizer:Example'], 'selected');
    assert.equal(v.label(), 'All Venues');
});

test('data refresh and zero-match venue filters preserve ownership and removal', () => {
    const {s, v, t} = setup(['Bar', 'Museum']);
    t.setTagState('Bar', 'selected');
    v.configure({}, ['Bar', 'Music']);
    v.updateCounts([]);
    assert.deepEqual([...v.visibleNames()], ['Bar']);
    s.configure({}, ['Bar', 'Music', 'Museum']);
    v.configure({}, ['Bar', 'Music', 'Museum']);
    assert.equal(s.label(), 'All Tags');
    assert.equal(v.label(), 'Bar');
    v.clear();
    assert.equal(v.visibleNames().length, 0);
});

test('venue browsing labels drive search and selections without changing tag identity', () => {
    const {v, t, states} = setup(['Beverage Venue', 'Cultural Venue', 'Restaurant', 'Brewery'],
        {'Beverage Venue': 'Food & Drink', 'Cultural Venue': 'Arts & Culture'});
    const tree = {'Beverage Venue': ['Restaurant', 'Brewery']};
    const names = ['Beverage Venue', 'Cultural Venue', 'Restaurant', 'Brewery'];
    v.configure(tree, names);
    v.setSearch('food & drink');
    assert.deepEqual([...v.visibleNames()], ['Beverage Venue']);
    v.setSearch('brewery');
    assert.deepEqual([...v.visibleNames()].sort(), ['Beverage Venue', 'Brewery']);
    v.setTagSelection('Beverage Venue', true);
    assert.equal(v.label(), 'Food & Drink');
    assert.equal(states['Beverage Venue'], 'selected');
    assert.equal(states['Food & Drink'], undefined);
    t.setTagState('Beverage Venue', 'forbidden');
    assert.equal(v.label(), 'Exclude Food & Drink');
    v.configure(tree, names);
    v.clear();
    assert.equal(v.label(), 'All Venues');
});

test('scoped Ballroom identities belong to separate menus even with legacy venue configuration', () => {
    const {s,v}=setup(['Ballroom']);
    const tree={Dance:['Ballroom'],'venue:Event Space':['venue:Ballroom']};
    const names=['Dance','Ballroom','venue:Event Space','venue:Ballroom'];
    s.configure(tree,names);v.configure(tree,names);
    s.setSearch('Ballroom');v.setSearch('Ballroom');
    assert.deepEqual([...s.visibleNames()],['Ballroom','Dance']);
    assert.deepEqual([...v.visibleNames()],['venue:Ballroom','venue:Event Space']);
    s.setTagSelection('Ballroom',true);
    v.setTagSelection('venue:Ballroom',true);
    assert.equal(s.label(),'Ballroom');assert.equal(v.label(),'Ballroom');
    s.clear();assert.equal(v.label(),'Ballroom');
});

test('unknown roots and their subtrees stay hidden even when they have matches', () => {
    const {s} = setup();
    s.configure({Art: ['Painting'], 'Gallery Reception': ['Special Reception']},
        ['Art', 'Painting', 'Gallery Reception', 'Special Reception']);
    s.updateCounts([{id: 1, tags: ['Gallery Reception', 'Special Reception']}]);
    assert.deepEqual([...s.visibleNames()], []);
    s.setSearch('Reception');
    assert.deepEqual([...s.visibleNames()], []);
});

test('unassigned ancestors remain navigation parents instead of promoting children', () => {
    const {s} = setup();
    s.configure({Art: ['Painting'], Painting: ['Watercolor']}, ['Watercolor']);
    s.updateCounts([{id: 1, tags: ['Watercolor']}]);
    assert.deepEqual([...s.visibleNames()].sort(), ['Art', 'Painting', 'Watercolor']);
});

test('venue orphans need a reviewed parent and roots come only from policy', () => {
    const {v} = setup([], {}, {venue: ['attraction']});
    v.configure({'venue:attraction': ['venue:Observation Deck']},
        ['venue:Observation Deck', 'venue:New Orphan']);
    v.setSearch('Deck');
    assert.deepEqual([...v.visibleNames()].sort(), ['venue:Observation Deck', 'venue:attraction']);
    v.setSearch('Orphan');
    assert.deepEqual([...v.visibleNames()], []);
});
