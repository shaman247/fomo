# Structured search and local assistants

The implementation accepts complete structured queries, evaluates published event
occurrences, and updates Fomo's map/list. All natural-language interpretation,
clarification, relative dates and origins belong to the calling assistant.
There are no hosted model calls, GPS permission requests, or location sensors in
this feature. An embedded native model has no inherited Siri/Gemini location:
it must ask for an origin when the user has not supplied one.

## Integration

Wait for `window.fomo` or the `fomo:query-ready` document event. Call
`window.fomo.call({method, input})`. Replies are `{ok:true,result}` or
`{ok:false,error:{code,path,details}}`. No provider credentials are required.

```js
// Literal retrieval; the assistant chooses among candidates.
const tags = await fomo.call({method: 'lookup_catalog', input: {
  kinds: ['tag'], text: 'Karaoke', match: 'exact', limit: 3
}});
const areas = await fomo.call({method: 'lookup_catalog', input: {
  kinds: ['region'], text: 'South Brooklyn', match: 'exact', limit: 3
}});
const {result: context} = await fomo.call({method: 'get_context'});
// The caller supplies all boundaries and chooses IDs from the returned records.
const query = {
  schemaVersion: 1, cityId: context.cityId,
  time: {kind: 'windows', windows: [{
    kind: 'instant_range', start: '2026-09-09T18:00:00-04:00',
    endExclusive: '2026-09-10T05:00:00-04:00',
    timezone: 'America/New_York', relation: 'starts'
  }]},
  groups: [
    {anyOf: [{kind: 'tag', id: tags.result.items[0].id,
      scope: 'event', includeDescendants: true}]},
    {anyOf: [{kind: 'region', id: areas.result.items[0].id,
      includeDescendants: true}]}
  ],
  exclude: [], unknownPolicy: 'separate',
  sort: {kind: 'earliest'}, view: 'fit_matches'
};
const reply = await fomo.call({method: 'apply_query', input: {
  query, requestId: crypto.randomUUID(),
  expectedStateRevision: context.stateRevision,
  expectedContextRevision: context.contextRevision,
  catalogRevision: context.catalogRevision, coveragePolicy: 'require_complete'
}});
```

Check every reply and candidate list before using it; the example assumes both
lookups succeed and that the caller selected those candidates. Dates above are
fixed examples, not a “tonight” preset. For proximity use
`{kind:'circle',center:{latitude,longitude},radiusMeters}` with caller-supplied
numbers. A map bound is never asserted to be the user's location.

| Method | Input and behavior |
| --- | --- |
| `get_context` | Current query, ordinary filter state, map bounds, selected place, dataset timezone, capabilities and revisions. Does not load data or provide device context. |
| `get_schema` | Authoritative JSON Schema; semantic validation is also mandatory. |
| `get_generation_contract` | Compact grammar for small local-model contexts. Does not replace validation. |
| `lookup_catalog` | `kinds`, literal `text`, `match` exact/prefix/tokens; optional `limit`, `cursor`, `fields`. Returns candidates, not a resolved winner. |
| `get_catalog_records` | `ids` (at most 50), optional `fields`. Calling with `ids:[]` loads the catalog before capturing revisions. |
| `get_events` | Event `ids` (at most 50); source records and descriptions. |
| `validate_query` | `query`; returns structural/semantic `errors`. |
| `search_events` | `query`, `coveragePolicy`, optional `limit`, `cursor`; read-only evaluation. |
| `apply_query` | Full replacement plus revision preconditions and request ID, as above. |
| `get_current_results` | Optional `limit`, `cursor`; current applied results without reinterpreting or reranking. |
| `make_link` | Validated `query`; creates `?qv=1&q=…` URL, maximum 8 KiB. |

Read-only pages contain at most 50 definite results. `possible`, `possibleCount`
and `unknownCount` distinguish incomplete evidence from definite matches. The UI
lists the first 50 possible events separately. Occurrences retain source tuples,
exact instants when known, and deterministic keys. Missing ends, malformed dates,
and source DST gaps/folds are not converted to invented exact times.

AND combines groups; OR combines each group's alternatives and each time window.
Exclusions use three-valued negation. Exact intervals are half-open. `starts`,
`overlaps` and `contained` have distinct meanings. Date-only windows support
source calendar dates. Unknown evidence is excluded or shown separately according
to `unknownPolicy`. Earliest ranking uses definite matching occurrences, distance
needs an explicit origin, and personalization only changes order.

Queries replace the active structured view. Filter chips expose their actual
constraints; removing one edits the structured query. “Use filters” restores the
ordinary manual filter mode. Empty results do not relax constraints. Browser
history and share links retain the structured view. Large queries can execute
within 32 KiB but cannot be shared if their encoded URL exceeds 8 KiB.

## Data and identity

The pipeline exports database place IDs, event place references and tag IDs.
Configured geographic group IDs live in `frontend.area_ids` in the city YAML;
retain those IDs when renaming labels. Other geographic IDs use database tag IDs.
Legacy exports use explicit name-derived fallback identities. They are not
silently remapped after a database-ID export: a stale reference fails visibly.
Regenerate the dataset before publishing durable links for the first release.

`build.js` and `pipeline/query_snapshot.py` create `data/query-manifest.json` with
SHA-256 hashes for the expected event, description, venue, hierarchy and organizer
files. The data uploader sends every required file and publishes the inventory
last, only on success. Hash mismatches/missing files prevent a complete-data apply.
The active search pins its snapshot for consistent results and pagination; reload
to use newly published data. A failed initial load can be retried. In-flight
publication can temporarily report incomplete data instead of mixing versions.

`generatedAt` is inventory creation time. `sourceExportedAt` is source export time
(or null for older exports), not a promise of individual event freshness. Coverage
means completeness of this published export, not all events in the city.

The engine is `queryCore.js`; the browser gateway is `queryGateway.js`.
`query.schema.json` and generated `querySchema.js` must stay identical (tested).
No query execution code calls a model or interprets natural-language operators.

## Native adapters

**iOS:** `AssistantSearch.swift` uses Foundation Models with runtime availability
checks, a guided action envelope, catalog retrieval and canonical validation.
The JSON payload is still validated independently. Bounded lookup rounds and one
semantic repair are allowed. Unsupported hardware or model errors preserve the
ordinary map and manual native search. Conversations remain in memory; cancelled
requests are not added to conversation history. The adapter supplies its own clock
and timezone, not a Fomo context API endpoint.

The native sheet also supports explicit manual time/title search, fixed saved
searches, named saved-search App Entities, an `Open saved search` intent, and a
`Show structured event search` intent accepting resolved query JSON. Calendar
editing requires an explicitly selected occurrence with known start/end times;
Apple's editor performs the user-reviewed save. Local reminders require an
explicit time and notification permission, retain the occurrence key/revision,
warn that cached details may change, and can be cancelled. No search creates
calendar entries or reminders automatically. These utilities work without a model.

The existing deployment target remains iOS 26.2. `FOMO_WEB_DOMAIN` in the Xcode
build settings supplies both the trusted WebView domain and associated-domain
entitlement. Choose the project's signing team. To finish Universal Links, run:

```sh
./venv/bin/python mobile/ios/generate_apple_association.py --team-id YOUR_TEAM_ID
```

Supply the real ten-character Team ID (not the placeholder above); the script
writes the local `.well-known/apple-app-site-association` artifact. Publish it
with the site and verify association on a signed device. No Team ID was available
in this checkout, so that site association has not been generated or deployed.

**Android:** `AssistantSearch.kt` uses the ML Kit Prompt API with explicit model
availability/download handling, bounded JSON generation and the same canonical
validator. No cloud fallback or GPS permissions. Incoming HTTPS links work for
initial and warm intents. The existing Android App Links association is retained.
The transport serializes messages into the trusted WebView; no unrestricted
JavaScript interface is exposed to frames. The alpha structured-output API and
AppFunctions are not dependencies of this implementation.

Both adapters reject oversized contexts instead of silently dropping constraints.
They still need physical-device model quality, latency, cancellation and
availability evaluation against `design/structured-search/evaluation.md`.
Compilation and deterministic query tests do not establish model interpretation
quality or App Store acceptance.

## Browser assistants and release verification

When `document.modelContext.registerTool` exists, `webMCP.js` registers the same
structured lookup/search/apply/link tools. It is optional and feature-detected;
normal browsers retain the JavaScript API and links. Browser/assistant support is
not universal. There is no hosted MCP endpoint or Fomo-hosted language model.

Verified locally: frontend unit suite, query concurrency/failure tests, inventory
and mocked uploader tests, desktop/mobile map rendering, zero results, idempotent
apply, stale revision rejection, Back navigation and structured-link replay;
iOS simulator build and Android Kotlin compilation. Nothing was committed,
uploaded, or submitted for review during implementation.

Relevant platform references:
[Foundation Models](https://developer.apple.com/documentation/foundationmodels),
[App Intents](https://developer.apple.com/documentation/appintents),
[Calendar editor](https://developer.apple.com/documentation/eventkit/accessing-calendar-using-eventkit-and-eventkitui),
[ML Kit Prompt API](https://developers.google.com/ml-kit/genai/prompt/android/get-started),
[WebMCP](https://developer.chrome.com/docs/ai/webmcp/imperative-api).
