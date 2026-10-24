const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { performance } = require('node:perf_hooks');

function app(venueLabels = {}) {
    const ctx = vm.createContext({ console, performance, setTimeout, Set, Map,
        __CITY__: {venueSelector: {labels: venueLabels}},
        Constants: { DISTANCE: { MAX_PROXIMITY_METERS: 50000 } },
        DiscoveryRanking: { score: e => e.preferenceScore || 0, stance: () => 0, placeKey: () => '' }
    });
    for (const [file, name] of [['core/utils.js','Utils'], ['data/dataManager.js','DataManager'],
        ['data/searchManager.js','SearchManager'], ['data/filterManager.js','FilterManager']]) {
        vm.runInContext(fs.readFileSync(path.join(__dirname, '..', file), 'utf8') + `\nthis.${name}=${name};`, ctx);
    }
    const maps = ctx.DataManager.buildTagHierarchyMaps({tags:[
        {name:'Concert',parents:[],aliases:['gig','GIG']},
        {name:'R&B',parents:[],aliases:['RnB']},
        {name:'Museum',parents:[]}, {name:'Brooklyn',parents:[]}
    ]});
    const state = {allEvents:[], locationsByLatLng:{'40,-74':{name:'Museum venue',tags:['Museum','Brooklyn']}},
        tagConfig:{}, hierarchyTagsSet:maps.hierarchyTagsSet, tagSearchTerms:maps.tagSearchTerms,
        tagChildrenOf:maps.childrenOf, tagDescendantsOf:maps.descendantsOf,
        currentlyMatchingEvents:[], currentlyVisibleMatchingEvents:[], locationDistances:{},
        currentlyMatchingLocationKeys:new Set(), currentlyVisibleMatchingLocationKeys:new Set(),
        visibleTagFrequencies:{}, tagFrequencies:{}, allAvailableTags:[]};
    ctx.SearchManager.init({appState:state});
    ctx.FilterManager.init({appState:state,config:{}});
    function load(events) {
        state.allEvents = events;
        state.eventsById = Object.fromEntries(events.map(e => [e.id,e]));
        state.currentlyMatchingEvents = events;
        state.currentlyVisibleMatchingEvents = events;
        ctx.DataManager.processTagHierarchy(state,{});
        ctx.DataManager.buildSearchIndex(state);
        ctx.DataManager.buildTagIndex(state);
    }
    return {...ctx,state,load};
}

test('keyword-only matches are searchable without creating browsable keyword chips', () => {
    const a=app();
    a.load([{id:1,name:'Autumn party',tags:['Halloween'],locationKey:'40,-74'}]);
    assert.equal(a.SearchManager.search('halloween',{},[]).some(r => r.type==='event' && r.ref===1),true);
    assert.equal(a.state.allAvailableTags.includes('Halloween'),false);
    a.DataManager.applyDescriptions({1:'An evening celebration'},a.state,true);
    assert.equal(a.SearchManager.search('halloween',{},[]).some(r => r.type==='event'),true);
    assert.equal(a.SearchManager.search('evening',{},[]).some(r => r.type==='event'),true);
});

test('canonical and alias searches yield one chip with exact-match relevance', async () => {
    const a=app();
    a.load([{id:1,name:'Live set',tags:['Concert','R&B']}]);
    for(const [term,tag] of [['gig','Concert'],['RnB','R&B'],['concert','Concert']]){
        const results=a.SearchManager.search(term,{},[]).filter(r=>r.type==='tag');
        assert.equal(results.length,1);
        assert.equal(results[0].ref,tag);
        assert.equal(results[0].textMatch,1);
    }
    assert.equal(a.SearchManager.matchTag('Concert','gig').exact,true);
    const refreshed=a.DataManager.buildTagHierarchyMaps({tags:[{name:'Concert',aliases:['live gig']}]});
    a.state.tagSearchTerms=refreshed.tagSearchTerms;
    await a.DataManager.buildSearchIndexAsync(a.state);
    assert.equal(a.SearchManager.search('live gig',{},[]).some(r=>r.type==='tag'&&r.ref==='Concert'),true);
});

test('venue browsing labels are searchable and rendered while topic aliases keep their identities', () => {
    const a = app({'Beverage Venue': 'Food & Drink', 'Cultural Venue': 'Arts & Culture'});
    const maps = a.DataManager.buildTagHierarchyMaps({tags: [
        {name: 'Beverage Venue'}, {name: 'Cultural Venue'}, {name: 'Art', aliases: ['Arts & Culture']}
    ]});
    a.state.tagSearchTerms = maps.tagSearchTerms;
    assert.equal(a.SearchManager.matchTag('Beverage Venue', 'food & drink').exact, true);
    assert.equal(a.SearchManager.matchTag('Cultural Venue', 'arts & culture').exact, true);
    assert.equal(a.SearchManager.matchTag('Art', 'arts & culture').exact, true);
    assert.equal(a.Utils.getTagDisplayName('Beverage Venue'), 'Food & Drink');
    assert.equal(a.Utils.getTagDisplayName('Cultural Venue'), 'Arts & Culture');
    assert.equal(a.Utils.getTagDisplayName('Art'), 'Art');
});

test('an exact event name outranks a highly preferred incidental text match', () => {
    const a=app();
    a.load([{id:1,name:'Unrelated',description:'Try bingo tonight',tags:[],preferenceScore:1000},
        {id:2,name:'Bingo',tags:[]}]);
    const results=a.SearchManager.search('bingo',{},[]);
    const grouped=a.SearchManager.groupAndSortResults(results,'bingo',()=>null,()=> 'unselected');
    assert.equal(grouped.groupedResults.events[0].ref,2);
});

test('selected, required, forbidden, popup and counts agree on venue membership', () => {
    const a=app();
    const e={id:1,name:'Show',tags:['Concert','Museum'],locationKey:'40,-74'};
    const outside={id:2,name:'Elsewhere',tags:['Concert']};
    a.load([e,outside]);
    const dateCopy={...e,matching_occurrences:[{start:'selected-day'}]};
    for(const tag of ['Museum','Brooklyn']){
        for(const mode of ['selected','required']){
            const results=a.FilterManager.filterEventsByTags({[tag]:mode},[dateCopy,outside]);
            assert.equal(results.length,1);assert.equal(results[0],dateCopy);
        }
        const results=a.FilterManager.filterEventsByTags({[tag]:'forbidden'},[dateCopy,outside]);
        assert.deepEqual(Array.from(results,r=>r.id),[2]);
        assert.equal(a.Utils.matchesTagSets(e.tags,a.state.locationsByLatLng[e.locationKey].tags,[],
            new Set(),new Set(),new Set([tag])),false);
    }
    const viewport=a.FilterManager.filterEventsByViewport([e],{contains:()=>true},null,{'40,-74':0});
    assert.equal(viewport.visibleTagFrequencies.Museum,2); // event + venue count once
    assert.equal(viewport.visibleTagFrequencies.Brooklyn,2);
});

test('organizer exclusions and required/forbidden combinations share the index', () => {
    const a=app();
    const e={id:1,name:'Show',tags:['Concert'],organizer_ids:[7],locationKey:'40,-74'};
    a.load([e]);
    const org=a.Utils.organizerTagsForEvent(e)[0];
    assert.ok(org);
    assert.equal(a.FilterManager.filterEventsByTags({[org]:'required'},[e]).length,1);
    assert.equal(a.FilterManager.filterEventsByTags({Concert:'required',[org]:'forbidden'},[e]).length,0);
});

test('location Jazz keywords are searchable but never count, include, require or exclude non-Jazz events', () => {
    const a = app();
    a.state.locationsByLatLng['40,-74'] = {name:'Music room', tags:['venue:Music Venue'], keywords:['Jazz']};
    const jazz = {id:1,name:'Jazz trio',tags:['Jazz'],locationKey:'40,-74'};
    const comedy = {id:2,name:'Stand-up',tags:['Comedy'],keywords:['Improvisation'],locationKey:'40,-74'};
    a.load([jazz,comedy]);
    assert.deepEqual(Array.from(a.state.eventTagIndex.Jazz),[1]);
    for (const mode of ['selected','required']) {
        assert.deepEqual(Array.from(a.FilterManager.filterEventsByTags({Jazz:mode},[jazz,comedy]), e=>e.id),[1]);
    }
    assert.deepEqual(Array.from(a.FilterManager.filterEventsByTags({Jazz:'forbidden'},[jazz,comedy]),e=>e.id),[2]);
    assert.equal(a.state.searchIndex.locations.get('40,-74').includes('jazz'),true);
    assert.equal(a.SearchManager.search('improvisation',{},[]).some(r=>r.type==='event'&&r.ref===2),true);
    assert.equal(a.Utils.eventFilterTags(comedy,a.state.locationsByLatLng['40,-74']).has('Improvisation'),false);
});

test('same-name Ballroom topic and venue identities filter independently and share their display name', () => {
    const a=app();
    a.state.locationsByLatLng['40,-74']={name:'Ballroom',tags:['venue:Ballroom']};
    const dance={id:1,name:'Dance',tags:['Ballroom']};
    const concert={id:2,name:'Concert',tags:['Concert'],locationKey:'40,-74'};
    a.load([dance,concert]);
    assert.deepEqual(Array.from(a.FilterManager.filterEventsByTags({Ballroom:'selected'},[dance,concert]),e=>e.id),[1]);
    assert.deepEqual(Array.from(a.FilterManager.filterEventsByTags({'venue:Ballroom':'selected'},[dance,concert]),e=>e.id),[2]);
    assert.equal(a.Utils.getTagDisplayName('venue:Ballroom'),a.Utils.getTagDisplayName('Ballroom'));
});

test('Tags and Venues selections OR within a selector and AND across them', () => {
    const a=app();
    a.state.locationsByLatLng['40,-74']={name:'Park',tags:['venue:Outdoor']};
    a.state.locationsByLatLng['41,-74']={name:'Cinema',tags:['venue:Cinema']};
    const parkFilm={id:1,name:'Movie night',tags:['Film'],locationKey:'40,-74'};
    const parkJazz={id:2,name:'Jazz picnic',tags:['Jazz'],locationKey:'40,-74'};
    const cinemaFilm={id:3,name:'Premiere',tags:['Film'],locationKey:'41,-74'};
    const parkYoga={id:4,name:'Yoga',tags:['Wellness'],locationKey:'40,-74'};
    const all=[parkFilm,parkJazz,cinemaFilm,parkYoga];
    a.load(all);
    const ids=states=>Array.from(a.FilterManager.filterEventsByTags(states,all),e=>e.id).sort();
    const popup=(states,e)=>{
        const s=a.Utils.partitionTagStates(states);
        return a.Utils.matchesTagSets(e.tags,a.state.locationsByLatLng[e.locationKey].tags,[],
            s.selectedTagsSet,s.requiredTagsSet,s.forbiddenTagsSet,s.selectedGroups);
    };
    const cases=[
        [{Film:'selected','venue:Outdoor':'selected'},[1]],
        [{Film:'selected',Jazz:'selected','venue:Outdoor':'selected'},[1,2]],
        [{Film:'selected','venue:Outdoor':'selected','venue:Cinema':'selected'},[1,3]],
        [{Film:'required','venue:Outdoor':'selected'},[1]],
        [{Film:'selected','venue:Outdoor':'required'},[1]],
        [{Film:'selected',Jazz:'required'},[2]], // required still supersedes selected within a selector
        [{Jazz:'required',Film:'selected','venue:Outdoor':'selected'},[2]],
    ];
    for(const [states,expected] of cases){
        assert.deepEqual(ids(states),expected,JSON.stringify(states));
        assert.deepEqual(all.filter(e=>popup(states,e)).map(e=>e.id),expected,JSON.stringify(states));
        // matchesTagSets without explicit groups derives the same answer.
        const s=a.Utils.partitionTagStates(states);
        assert.deepEqual(all.filter(e=>a.Utils.matchesTagSets(e.tags,a.state.locationsByLatLng[e.locationKey].tags,[],
            s.selectedTagsSet,s.requiredTagsSet,s.forbiddenTagsSet)).map(e=>e.id),expected);
    }
});

test('location aliases are searchable but never displayed', () => {
    const a = app();
    a.state.locationsByLatLng['40,-74'] = {name:'KGB Bar', tags:['venue:Bar'], aliases:['The Red Room at KGB']};
    a.load([{id:1,name:'Jazz trio',tags:['Jazz'],locationKey:'40,-74'}]);
    assert.equal(a.state.searchIndex.locations.get('40,-74').includes('red room'),true);
    const hit = a.SearchManager.search('red room',{},[]).find(r=>r.type==='location'&&r.ref==='40,-74');
    assert.ok(hit);
    assert.equal(hit.displayName,'KGB Bar');
});
