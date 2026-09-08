const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
function selector() {
    const ctx = vm.createContext({ console, Set, Map });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../ui/formatSelector.js'), 'utf8') + '\nthis.selector = FormatSelector;', ctx);
    const s = ctx.selector;
    s.configure({ Performance: ['Concert', 'Sports'], Participatory: ['Game', 'Fitness'], Outing: ['Tour','Outing'] });
    return s;
}
test('empty selections keep checkboxes clear while matching all events', () => {
    const s = selector();
    const events = [{event_type:'Game',tags:['Concert']}, {event_type:'Concert'}, {event_type:'Fitness',tags:['Sports']}, {event_type:null}];
    assert.equal(events.filter(s.matches).length,4);
    assert.equal(s.label(),'All Events');
    s.setSelection(['Concert','Sports']);
    assert.deepEqual(events.filter(s.matches),[events[1]]);
    s.setSelection([]);
    assert.equal(s.label(),'All Events');
    assert.deepEqual([...s.selection()],[]);
    assert.equal(s.groupState('Performance').checked,false);
    assert.equal(events.filter(s.matches).length,4);
    s.setSelection(['Other']);
    assert.deepEqual(events.filter(s.matches),[events[3]]);
    s.setSelection(null);
    assert.equal(events.filter(s.matches).length,4);
});
test('taxonomy refresh preserves exclusions; all automatically includes new types', () => {
    const s = selector();
    s.setSelection(['Concert']);
    s.configure({Performance:['Concert','Sports','Reading']});
    assert.equal(s.matches({event_type:'Reading'}),false);
    s.setSelection(null);
    s.configure({Performance:['Concert','Reading','Screening']});
    assert.equal(s.matches({event_type:'Screening'}),true);
    s.setSelection(['Gone']);
    assert.deepEqual([...s.selection()],[]);
    s.setSelection(['Screening']);
    s.configure({Performance:['Concert']});
    assert.deepEqual([...s.selection()],[]);
    assert.equal(s.matches({event_type:'Concert'}),true);
});
test('category selection changes every child and preserves other categories', () => {
    const s = selector();
    s.setGroupSelection('Performance', false);
    assert.equal(s.matches({event_type:'Concert'}),false);
    assert.equal(s.matches({event_type:'Sports'}),false);
    assert.equal(s.matches({event_type:'Game'}),true);
    assert.equal(s.matches({event_type:null}),true);
    assert.equal(s.groupState('Performance').checked,false);
    assert.equal(s.groupState('Performance').indeterminate,false);
    s.setGroupSelection('Performance', true);
    assert.equal(s.selection(),null);
    assert.equal(s.groupState('Performance').checked,true);
    s.setSelection(['Concert']);
    s.setGroupSelection('Performance', true);
    assert.deepEqual([...s.selection()],['Concert','Sports']);
    assert.equal(s.groupState('Participatory').checked,false);
    s.setGroupSelection('Performance', false);
    assert.deepEqual([...s.selection()],[]);
    assert.equal(s.groupState('Participatory').checked,false);
    assert.equal(s.matches({event_type:'Game'}),true);
    s.setGroupSelection('Participatory',true);
    assert.deepEqual([...s.selection()],['Game','Fitness']);
    assert.equal(s.matches({event_type:'Concert'}),false);
});
test('partially selected categories show a mixed state and can select all children', () => {
    const s = selector();
    s.setSelection(['Concert','Game']);
    assert.equal(s.groupState('Performance').checked,false);
    assert.equal(s.groupState('Performance').indeterminate,true);
    s.setGroupSelection('Performance', true);
    assert.equal(s.groupState('Performance').checked,true);
    assert.equal(s.groupState('Performance').indeterminate,false);
    assert.deepEqual([...s.selection()],['Concert','Sports','Game']);
    s.configure({Performance:['Concert','Sports','Reading'],Participatory:['Game','Fitness']});
    assert.equal(s.groupState('Performance').indeterminate,true);
    s.setGroupSelection('Performance', false);
    assert.deepEqual([...s.selection()],['Game']);
});
test('legacy category links expand into format leaves without conflating Game and Games', () => {
    const s = selector();
    assert.deepEqual([...s.fromLegacyTags(['Outings'])],['Tour','Outing']);
    assert.deepEqual([...s.fromLegacyTags(['Game'])],['Game']);
    assert.deepEqual([...s.fromLegacyTags(['Games'])],[]);
    assert.equal(s.fromLegacyTags(['Format']),null);
});
test('empty format links preserve unchecked state while displaying all events', () => {
    const ctx = vm.createContext({ URLSearchParams, console, window:{location:{search:'?formats=',origin:'https://example.test',pathname:'/'}} });
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../core/urlParams.js'),'utf8')+'\nthis.URLParams=URLParams;',ctx);
    assert.deepEqual([...ctx.URLParams.parse().formats],[]);
    const s = selector();
    s.setSelection(ctx.URLParams.parse().formats);
    assert.deepEqual([...s.selection()],[]);
    assert.equal(s.label(),'All Events');
    assert.equal(s.matches({event_type:'Concert'}),true);
    const all = ctx.URLParams.generateShareUrl({lat:40,lng:-74,zoom:12,formats:s.selection()});
    assert.equal(new URL(all).searchParams.get('formats'),'');
});
test('format-only nodes stay out of topic chips, including after refresh', () => {
    const ctx=vm.createContext({console,Set,Map,Utils:{normalizeForSearch:s=>s.toLowerCase()}});
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../data/dataManager.js'),'utf8')+'\nthis.DM=DataManager;',ctx);
    const maps=ctx.DM.buildTagHierarchyMaps({tags:[{name:'Sports',parents:['Community']}],format_only_tags:['Format','Game']});
    const state={tagConfig:{},allEvents:[{tags:['Format','Game','Sports']}],locationsByLatLng:{},hierarchyTagsSet:maps.hierarchyTagsSet,formatOnlyTags:maps.formatOnlyTags};
    ctx.DM.processTagHierarchy(state,{});
    assert.deepEqual([...state.allAvailableTags],['Sports']);
    const captured=state.structuralFormatTags;
    ctx.DM.processTagHierarchy(state,{});
    assert.equal(state.structuralFormatTags,captured);
    assert.equal(captured.has('Game'),true);
});
test('format selections intersect date and required topic membership', () => {
    const ctx=vm.createContext({console,Set,Map,Date,Constants:{TIME:{EARLY_MORNING_CUTOFF_HOUR:5}}});
    for (const [file,name] of [['core/utils.js','Utils'],['data/filterManager.js','FM']]) {
        const symbol=name==='FM'?'FilterManager':name;
        vm.runInContext(fs.readFileSync(path.join(__dirname,'..',file),'utf8')+`\nthis.${name}=${symbol};`,ctx);
    }
    const day=new Date(2026,8,8), later=new Date(2026,8,9);
    const e=(id,format,date)=>({id,event_type:format,occurrences:[{start:date,end:date}]});
    const state={allEvents:[e(1,'Game',day),e(2,'Concert',day),e(3,'Game',later),e(4,'Game',day)],eventTagIndex:{Kids:[1,2,3]}};
    ctx.FM.init({appState:state,config:{START_DATE:day,END_DATE:day}});
    const s=selector();s.setSelection(['Game']);
    const result=ctx.FM.filterEventsByTags({Kids:'required'},ctx.FM.filterEventsByDateRange(day,day).filter(s.matches));
    assert.deepEqual([...result].map(e=>e.id),[1]);
    assert.equal(result[0].matching_occurrences.length,1);
});
test('new data schemas get distinct HTTP URLs while preserving revalidation', async () => {
    const requests=[];
    const ctx=vm.createContext({console,AbortController,setTimeout,clearTimeout,
        DataCache:{schemaVersion:4,hashString:s=>String(s.length)},
        fetch:async(url,options)=>{requests.push([url,options.cache]);return {ok:true,text:async()=>'{"formats":{"Social":["Party"]}}'};}});
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../data/dataManager.js'),'utf8')+'\nthis.DM=DataManager;',ctx);
    const result=await ctx.DM.fetchDataHashed('data/tag_hierarchy.json',1000,{cache:'no-cache'});
    assert.deepEqual(requests,[['data/tag_hierarchy.json?schema=4','no-cache']]);
    assert.deepEqual([...result.data.formats.Social],['Party']);
});

test('format counts include Other, hide empty categories, and count events only once', () => {
    const s=selector();
    s.updateCounts([{id:1,event_type:'Concert'},{id:1,event_type:'Concert'},
        {id:2,event_type:'Sports'},{id:3,event_type:null},{id:4,event_type:'Unknown'}]);
    assert.equal(s.count('Concert'),1);
    assert.equal(s.categoryCount('Performance'),2);
    assert.equal(s.count('Other'),2);
    assert.equal(s.categoryCount('Outing'),0);
    assert.deepEqual([...s.visibleTypes()],['Concert','Sports','Other']);
    s.setSelection(['Game']);
    s.updateCounts([]);
    assert.deepEqual([...s.visibleTypes()],[]);
    assert.deepEqual([...s.selection()],['Game']);
    s.updateCounts([{id:5,event_type:'Game'}]);
    assert.deepEqual([...s.visibleTypes()],['Game']);
    assert.equal(s.matches({event_type:'Game'}),true);
});
