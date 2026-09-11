# Per-site extraction settings — rationale

Why specific `websites` rows carry `force_chunked` / `max_records_per_chunk`.
Mechanism, and the measurements behind keeping both knobs opt-in:
`.claude/rules/pipeline.md` → *Per-site extraction settings*. Migrated from
`[[extraction: …]]` lines in `websites.notes` on 2026-09-04; add a row here
when you set either column on a new site.

| website | setting | rationale |
|---|---|---|
| w1 NYC Events | max_records_per_chunk=25 | the js_code appends ~186 API-derived cards as a very dense block (~30 KB) at the END of the page, so the final chunks carry far more records per char than the rendered cards do. Measured 2026-08-18: those chunks silently dropped the street permit parades (Falun Dafa, Pakistan Independence Day, Central American, Mexican Independence) even though they were present in crawled_content at ~91% depth. |
| w50 Film Forum | max_records_per_chunk=25 | measured 2026-07-31: its 50-record/8.4K chunk overruns the response budget; splitting it recovers 3 dated films (63 -> 66 distinct, 4 reps). A GLOBAL cap was measured and rejected (+0.1% events for +83% chunks). |
| w162 Brooklyn Bridge Park | force_chunked=1 | (no rationale recorded) |
| w246 The Green Room 42 | force_chunked=1 | the venuetix listing is ~55-61 KB of `showdetails/` links with `— Feb 28, 2027 9:30 PM` date suffixes that trip NONE of `estimate_event_count`'s signals (measured estimate 0-1 on ~136 real shows), so mode selection fell entirely to the `len(content) > MAX_CHUNK_CHARS*2` size test and the site straddled that 60 KB cliff: 60,722 -> 122, 60,638 -> 122, 56,226 -> 18, 57,174 -> 136, 54,791 -> 18 across five crawls on stable content. Triage 2026-09-10: force_chunked took the same content from 18 -> 133 events. |
| w247 The Met Opera | force_chunked=1 | (no rationale recorded) |
| w386 GrowNYC | max_records_per_chunk=25 | (no rationale recorded) |
| w950 Nook | force_chunked=1 | the Eventbrite API injects ~30 cards at ~43 KB, which is just under LARGE_PAGE_THRESHOLD (est. 32-34) and just under MAX_CHUNK_CHARS*2, so single-call extraction collapsed non-deterministically (30 -> 12 -> 14 events across 07-22/07-25/07-28). |
| w1112 NYC Service | force_chunked=1, max_records_per_chunk=8 | The /calendar js_code emits one record per opportunity with up to 20 dates each; uncapped chunks overrun the response budget (57 records -> 15 extracted on 2026-08-28). |
| w1164 Alvin Ailey | force_chunked=1, max_records_per_chunk=12 | (no rationale recorded) |
| w1577 JCC Manhattan | force_chunked=1 | (no rationale recorded) |
| w4102 Hudson County NJ | force_chunked=1 | (no rationale recorded) |
| w4110 AMC Empire 25 | max_records_per_chunk=20 | 23 date pages x ~14 compact showtime cards; a 50-record chunk drops occurrences off its tail (11 of 88 films undated in crawl 114112 before this). |
| w4653 PlentyofParties | force_chunked=1 | 38 Eventbrite-API cards at ~60 KB sits just under LARGE_PAGE_THRESHOLD=50, so the single-call path's output budget truncates it (33 of 38 extracted 2026-08-18; 7 real future events missing). Same shape as w950 Nook. |
| w4726 Monmouth County Park System | force_chunked=1 | 30-47K calendar, estimate 49 (just under LARGE_PAGE_THRESHOLD); single-call collapsed to 23-24 of 30 distinct titles on 2 of 5 measured runs. |
| w4868 Poetry Brothel NYC | force_chunked=1 | 54K Eventbrite organizer listing, estimate 37 (< LARGE_PAGE_THRESHOLD); single-call reproducibly returned 29 of the 37 event URLs on the page. |
| w5207 The Boat Yard | force_chunked=1 | ~40-90 season events sit just under LARGE_PAGE_THRESHOLD, and single-call mode's 8K output cap truncates the tail. |
| w1813 Weill Cornell Medicine | force_chunked=1 | the Localist-API js_code injects 29 cards at ~38.7 KB — estimate 29-38, just under LARGE_PAGE_THRESHOLD, and under MAX_CHUNK_CHARS*2. Same cliff as w950 Nook. Single-call returned 15 of the 19 policy-eligible events on 2026-09-08; chunked (3 chunks) returned all 19, including the patient wellness series (Hanna Somatic, MBSR, Loving Kindness Meditation). |
