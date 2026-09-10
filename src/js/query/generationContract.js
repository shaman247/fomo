/* Compact representation for small local-model context windows. The JSON Schema
 * and semantic validator remain authoritative; this is never an executor. */
const FomoGenerationContract = {
    query: '{schemaVersion:1,cityId:string,time:Time,groups:[{anyOf:[Predicate]}],exclude:[Predicate],unknownPolicy:"exclude"|"separate",sort:Sort,view:"keep"|"fit_matches"}',
    Time: '{kind:"all_published"} OR {kind:"windows",windows:[Window]}',
    Window: '{kind:"instant_range",start:ISO8601,endExclusive:ISO8601,timezone:IANA,relation:"starts"|"overlaps"|"contained"} OR {kind:"date_range",startDate:"YYYY-MM-DD",endDateExclusive:"YYYY-MM-DD",timezone:IANA}',
    Predicate: [
        '{kind:"tag",id:catalogID,scope:"event"|"place"|"organizer",includeDescendants:boolean}',
        '{kind:"region",id:catalogID,includeDescendants:boolean}',
        '{kind:"format"|"place"|"organizer"|"event",id:catalogID}',
        '{kind:"circle",center:{latitude:number,longitude:number},radiusMeters:number}',
        '{kind:"bounds",south:number,west:number,north:number,east:number}',
        '{kind:"text",fields:["name"|"description"|"place_name"|"organizer_name"],value:string,match:"phrase"|"all_tokens"}'
    ],
    Sort: '{kind:"earliest"|"personalized"} OR {kind:"distance",origin:{latitude:number,longitude:number}}',
    rules: 'All fields required. No extra keys. AND between groups, OR within anyOf. Exclusions negate predicates. Windows are OR, start inclusive/end exclusive. Timestamps include seconds and an offset matching timezone. Use catalog IDs verbatim. IDs and tag associations are not guarantees. Text matches literal tokens, not meaning. Unknown source details cannot prove a match. Date-only records match calendar dates; exact time filters require time evidence. All published refers only to the published dataset.',
    limits: { groups: 16, alternativesPerGroup: 8, exclusions: 32, windows: 8, windowDays: 366, textCharacters: 200, radiusMeters: 100000 }
};
