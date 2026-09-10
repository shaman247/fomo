const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const dir = path.join(__dirname, '../query');
const ctx = vm.createContext({ console, TextEncoder, TextDecoder, URL, btoa, atob });
for (const file of ['querySchema.js', 'queryCore.js']) vm.runInContext(fs.readFileSync(path.join(dir, file), 'utf8'), ctx);
const C = vm.runInContext('FomoQueryCore', ctx);
const examples = JSON.parse(fs.readFileSync(path.join(dir, 'examples.json')));
const clone = v => JSON.parse(JSON.stringify(v));
const base = () => clone(examples.valid[0].query);
test('canonical schema stays synchronized with generated browser schema', () => {
    assert.deepEqual(clone(vm.runInContext('FomoQuerySchema',ctx)), JSON.parse(fs.readFileSync(path.join(dir,'query.schema.json'))));
});
test('all design examples enforce shape and semantic limits', () => {
    for (const c of examples.valid) assert.equal(C.validate(c.query).length, 0, c.id);
    for (const c of examples.invalidShape) assert.ok(C.validate(c.query).length, c.id);
    for (const c of examples.requiresSemanticRejection.filter(c => c.id !== 'wrong-city-for-fixture-context')) assert.ok(C.validate(c.query).length, c.id);
});
test('links preserve full queries and reject ambiguity, unsupported versions and corrupted input', () => {
    for (const {query} of examples.valid) assert.deepEqual(clone(C.decode(C.encode(query,'https://example.test/?old=1'))), query);
    for (const url of ['https://example.test/?qv=2&q=e30','https://example.test/?qv=1&q=!!!']) assert.throws(() => C.decode(url));
});
test('source times retain unknown ends and reject DST gaps/folds', () => {
    const o = C.occurrence(['2026-09-09','7pm',null,null],'America/New_York');
    assert.equal(o.end, null); assert.equal(o.point, false);
    const time = base().time;
    time.windows[0].relation = 'overlaps';
    assert.equal(C.timeMatch(o,time),null);
    assert.equal(C.timeMatch(C.occurrence(['2026-09-09','8pm',null,null],'America/New_York'),time),true);
    time.windows[0].relation = 'contained';
    assert.equal(C.timeMatch(C.occurrence(['2026-09-09','8pm',null,null],'America/New_York'),time),null);
    assert.equal(C.occurrence(['2026-03-08','2:30am',null,null],'America/New_York').start,null);
    assert.equal(C.occurrence(['2026-11-01','1:30am',null,null],'America/New_York').start,null);
});
test('half-open windows, date-only events and exact midnight ends', () => {
    const time = base().time;
    assert.equal(C.timeMatch(C.occurrence(['2026-09-09','8pm',null,null],'America/New_York'),time),true);
    assert.equal(C.timeMatch(C.occurrence(['2026-09-10','5am',null,null],'America/New_York'),time),false);
    assert.equal(C.timeMatch(C.occurrence(['2026-09-09','',null,null],'America/New_York'),time),null);
    const days = {kind:'windows',windows:[{kind:'date_range',startDate:'2026-09-10',endDateExclusive:'2026-09-11',timezone:'America/New_York'}]};
    assert.equal(C.timeMatch(C.occurrence(['2026-09-09','8pm','2026-09-10','12am'],'America/New_York'),days),false);
    assert.equal(C.timeMatch(C.occurrence(['2026-09-10','',null,null],'America/New_York'),days),true);
});
function fixture() {
    const data = {events:[
        {id:1,name:'Jazz outdoors',tags:['Jazz','Outdoor'],lat:40,lng:-74,location:'Hall',occurrences:[['2026-09-09','8pm',null,null]]},
        {id:2,name:'Blues festival',tags:['Blues','Outdoor','Festival'],lat:40,lng:-74,location:'Hall',occurrences:[['2026-09-09','8pm',null,null]]},
        {id:3,name:'Jazz indoors',tags:['Jazz'],lat:40,lng:-74,location:'Hall',occurrences:[['2026-09-09','8pm',null,null]]},
        {id:4,name:'Unknown time',tags:['Jazz','Outdoor'],lat:40,lng:-74,location:'Hall',occurrences:[['2026-09-09','',null,null]]}
    ],locations:[{id:12,name:'Hall',lat:40,lng:-74,tags:['Village','Family']}],organizers:{}, descriptions:{},descriptionsComplete:true,
    hierarchy:{tags:[{name:'Neighborhood',parents:[]},{name:'Borough',parents:['Neighborhood']},{name:'Village',parents:['Borough']}]}};
    const cat = C.catalog(data,{cityId:'nyc',timezone:'America/New_York',neighborhoodSelector:{groups:{'South Borough':['Village']}}});
    return {data,cat};
}
test('AND/OR/exclusion, tag scopes, region membership and unknowns are independent', () => {
    const {data,cat}=fixture(), q=base();
    const tag = name => ({kind:'tag',id:cat.ids.get('tag:'+name),scope:'event',includeDescendants:false});
    q.groups=[{anyOf:[tag('Jazz'),tag('Blues')]},{anyOf:[tag('Outdoor')]},{anyOf:[{kind:'region',id:cat.ids.get('region:South Borough'),includeDescendants:true}]}];
    q.exclude=[tag('Festival')];
    let r=C.evaluate(q,data,cat);
    assert.deepEqual(clone(r.definite.map(x=>x.event.id)),[1]);
    assert.deepEqual(clone(r.possible.map(x=>x.event.id)),[4]);
    q.exclude=[{...tag('Family'),scope:'place'}];
    r=C.evaluate(q,data,cat); assert.equal(r.definite.length,0);
    q.exclude=[tag('Family')]; r=C.evaluate(q,data,cat); assert.equal(r.definite.length,2);
});
test('negative unknowns do not become known matches; sorting uses matching occurrences', () => {
    assert.equal(C.not(null),null); assert.equal(C.and([false,null]),false); assert.equal(C.or([true,null]),true);
    const {data,cat}=fixture(), q=base(); q.groups=[]; q.exclude=[];
    data.events[0].occurrences.unshift(['2025-01-01','7am',null,null]);
    const r=C.evaluate(q,data,cat); assert.equal(r.definite[0].occurrences.length,1);
});
test('circle uses actual numeric coordinates, without acquiring location', () => {
    const {data,cat}=fixture(), q=base(); q.groups=[{anyOf:[{kind:'circle',center:{latitude:40,longitude:-74},radiusMeters:1}]}]; q.exclude=[];
    assert.equal(C.evaluate(q,data,cat).definite.length,3);
    q.groups[0].anyOf[0].center.latitude=41;
    assert.equal(C.evaluate(q,data,cat).definite.length,0);
});
test('known starts use the query calendar even with no published end; date bounds rule out impossible starts', () => {
    const o = C.occurrence(['2026-09-09','11:30pm',null,''],'America/New_York');
    const q = {kind:'windows',windows:[{kind:'date_range',startDate:'2026-09-10',endDateExclusive:'2026-09-11',timezone:'Asia/Tokyo'}]};
    assert.equal(C.timeMatch(o,q),true);
    assert.equal(C.timeMatch(C.occurrence(['2026-08-01','',null,''],'America/New_York'),base().time),false);
});
test('uncertain earlier occurrences never outrank a definite matching start', () => {
    const {data,cat}=fixture(),q=base(); q.groups=[];q.exclude=[];q.time.windows[0].relation='overlaps';
    data.events[0].occurrences=[['2026-09-09','9pm',null,''],['2026-09-09','7pm',null,'']];
    const result=C.evaluate(q,data,cat);
    assert.notEqual(result.definite[0].event.id,1);
    assert.equal(result.definite.find(e=>e.event.id===1).possibleOccurrences.length,1);
});
test('exported database IDs survive label changes; stale legacy IDs are not guessed', () => {
    const {data}=fixture();data.hierarchy.tag_ids={Jazz:42};
    const city={cityId:'nyc',timezone:'America/New_York'};
    const cat=C.catalog(data,city);
    assert.equal(cat.ids.get('tag:Jazz'),'tag:42');
    const q=base();q.groups=[{anyOf:[{kind:'tag',id:'tag:42',scope:'event',includeDescendants:false}]}];q.exclude=[];
    assert.equal(C.evaluate(q,data,cat).definite.length,2);
    q.groups[0].anyOf[0].id=C.namedId('tag','Jazz');
    assert.ok(C.validate(q,cat).some(e=>e.code==='unknown_reference'));
});
