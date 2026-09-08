const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const tree = { Neighborhood:['Borough','Region'], Borough:['Village','Heights'], Village:['Quarter'], Region:['Town, East'] };
const names = ['Neighborhood','Borough','Region','Village','Heights','Quarter','Town, East'];
function selector() {
    const ctx = vm.createContext({console, Set, Map});
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/neighborhoodSelector.js'),'utf8')+'\nthis.s=NeighborhoodSelector;',ctx);
    ctx.s.configure(tree,names);
    return ctx.s;
}
test('neighborhoods use event and venue geography with OR matching', () => {
    const s=selector();
    s.setSelection(['Quarter','Town, East']);
    assert.equal(s.matches({tags:['Music','Quarter']}),true);
    assert.equal(s.matches({tags:['Music']},{tags:['Town, East']}),true);
    assert.equal(s.matches({tags:['Heights']}),false);
    assert.equal(s.matches({tags:['Music']}),false);
});
test('deselecting a neighborhood cannot match its inherited selected borough', () => {
    const s=selector();
    s.setGroupSelection('Village',false);
    assert.equal(s.matches({tags:['Neighborhood','Borough','Village','Quarter']}),false);
    assert.equal(s.matches({tags:['Borough','Heights']}),true);
    assert.equal(s.matches({tags:['Borough']}),true);
    assert.equal(s.groupState('Borough').indeterminate,true);
    s.setGroupSelection('Borough',true);
    assert.equal(s.selection(),null);
});
test('clear all remains unchecked and permits selecting one area or a whole branch', () => {
    const s=selector();
    s.setSelection([]);
    assert.equal(s.matches({tags:[]}),true);
    assert.equal(s.label(),'Everywhere');
    assert.equal(s.groupState('Borough').checked,false);
    s.setGroupSelection('Village',true);
    assert.equal(s.label(),'Village');
    assert.deepEqual([...s.selection()].sort(),['Quarter','Village']);
    s.setGroupSelection('Village',false);
    assert.deepEqual([...s.selection()],[]);
    s.setGroupSelection('Quarter',true);
    assert.deepEqual([...s.selection()],['Quarter']);
});
test('legacy region links expand descendants and refresh keeps selection', () => {
    const s=selector();
    assert.deepEqual([...s.fromLegacyTags(['Village'])].sort(),['Quarter','Village']);
    assert.equal(s.fromLegacyTags(['Neighborhood']),null);
    s.setSelection(s.fromLegacyTags(['Borough']));
    s.configure({...tree,Borough:['Village','Heights','New Place']},[...names,'New Place']);
    assert.equal(s.matches({tags:['Borough','New Place']}),false);
    s.setSelection(null);
    assert.equal(s.matches({tags:['Borough','New Place']}),true);
});
test('share links preserve commas in neighborhood names and the empty checkbox state', () => {
    const ctx=vm.createContext({URLSearchParams,console,window:{location:{search:'',origin:'https://example.test',pathname:'/'}}});
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../core/urlParams.js'),'utf8')+'\nthis.u=URLParams;',ctx);
    for(const values of [[],['Town, East','Quarter']]) {
        const url=ctx.u.generateShareUrl({lat:40,lng:-74,zoom:12,neighborhoods:values,formats:['Concert']});
        ctx.window.location.search=new URL(url).search;
        assert.deepEqual([...ctx.u.parse().neighborhoods],values);
        assert.deepEqual([...ctx.u.parse().formats],['Concert']);
    }
});
test('the complete geographic subtree is excluded from topic chips, including deeper nodes', () => {
    const ctx=vm.createContext({console,Set,Map,Utils:{normalizeForSearch:s=>s.toLowerCase()}});
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../data/dataManager.js'),'utf8')+'\nthis.d=DataManager;',ctx);
    const data={tags:[{name:'Neighborhood',parents:[]},{name:'Borough',parents:['Neighborhood']},{name:'Village',parents:['Borough']},{name:'Music',parents:[]}]};
    const maps=ctx.d.buildTagHierarchyMaps(data);
    const state={tagConfig:{},allEvents:[{tags:['Neighborhood','Borough','Village','Music']}],locationsByLatLng:{},hierarchyTagsSet:maps.hierarchyTagsSet,neighborhoodTags:maps.neighborhoodTags};
    ctx.d.processTagHierarchy(state,{});
    assert.deepEqual([...state.allAvailableTags],['Music']);
    assert.equal(maps.neighborhoodTags.has('Village'),true);
});

test('city configuration groups existing areas without changing their memberships', () => {
    const s=selector();
    const options={groups:{Metro:['Borough','Region']},order:['Metro'],expanded:['Metro']};
    s.configure(tree,names,options);
    s.setSelection([]);
    s.setGroupSelection('Metro',true);
    assert.equal(s.selection(),null);
    assert.equal(s.matches({tags:['Quarter']}),true);
    s.setGroupSelection('Region',false);
    assert.equal(s.matches({tags:['Region','Town, East']}),false);
    assert.equal(s.matches({tags:['Borough','Village','Quarter']}),true);
    assert.equal(s.groupState('Metro').indeterminate,true);
    s.setSelection([]);
    s.setGroupSelection('Borough',true);
    assert.equal(s.label(),'Borough');
    s.configure(tree,names,options);
    assert.equal(s.label(),'Borough');
});

test('non-empty searches reveal matching empty areas and their ancestors', () => {
    const s=selector();
    s.updateCounts([{id:1,tags:['Heights']}]);
    assert.equal(s.visibleNames().includes('Quarter'),false);
    assert.equal(s.visibleNames().includes('Region'),false);
    assert.equal(s.visibleNames().includes('Borough'),true);
    s.setSelection(['Quarter']);
    s.setSearch('Quarter');
    assert.deepEqual([...s.visibleNames()].sort(),['Borough','Quarter','Village']);
    assert.equal(s.count('Quarter'),0);
    assert.deepEqual([...s.selection()],['Quarter']);
    s.setSearch('town, east');
    assert.deepEqual([...s.visibleNames()].sort(),['Region','Town, East']);
    s.setSearch('   ');
    assert.equal(s.visibleNames().includes('Quarter'),false);
    s.setSearch('no such area');
    assert.equal(s.visibleNames().length,0);
    s.setSearch('');
    s.updateCounts([{id:2,tags:['Quarter']}]);
    assert.equal(s.visibleNames().includes('Quarter'),true);
    assert.equal(s.matches({tags:['Quarter']}),true);
});
test('area counts deduplicate venue tags, ancestor tags and repeated events', () => {
    const s=selector();
    s.configure(tree,names,{groups:{Metro:['Borough','Region']}});
    const event={id:1,tags:['Quarter','Village','Borough'],locationKey:'v'};
    s.updateCounts([event,event,{id:2,tags:['Heights']},{id:3,tags:[],locationKey:'v'}],
        {v:{tags:['Quarter','Town, East']}});
    assert.equal(s.count('Quarter'),2);
    assert.equal(s.count('Village'),2);
    assert.equal(s.count('Borough'),3);
    assert.equal(s.count('Region'),2);
    assert.equal(s.count('Metro'),3); // Not the sum of overlapping borough/region totals.
    s.updateCounts([]);
    assert.equal(s.visibleNames().length,0);
    assert.equal(s.count('Metro'),0);
});
test('configured subsections retain group selection behavior', () => {
    const s=selector();
    s.configure(tree,names,{groups:{Borough:['Section'],Section:['Village','Heights']}});
    s.updateCounts([{id:1,tags:['Quarter']}]);
    assert.equal(s.count('Section'),1);
    s.setSelection([]);
    s.setGroupSelection('Section',true);
    assert.equal(s.matches({tags:['Quarter']}),true);
    s.setGroupSelection('Village',false);
    assert.equal(s.matches({tags:['Borough','Village','Quarter']}),false);
    assert.equal(s.groupState('Section').indeterminate,true);
});
