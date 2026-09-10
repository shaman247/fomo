# September 9: ten further event-icon batches

Completed ten distinct 100-event cohorts, continuing after event 81277. Every full stored context was read and individually judged against the catalog; every decision stores its rationale and supporting evidence. Final catalog reconciliation added 21 matches to earlier cohorts. All 1,000 forward reviews and five earlier artwork applications are current, with no deferred decisions or pending reviews in this scope. Local database, frontend chunks, public NDJSON and build are updated. No upload, deployment, commit or push.

| Batch | IDs | Custom | Fallback | Opportunity records |
|---|---|---:|---:|---:|
| 1 | 81280–88335 | 37 | 63 | 21 |
| 2 | 88336–93433 | 25 | 75 | 27 |
| 3 | 93435–98572 | 28 | 72 | 33 |
| 4 | 98576–101181 | 26 | 74 | 22 |
| 5 | 101182–104799 | 35 | 65 | 29 |
| 6 | 104827–107632 | 32 | 68 | 16 |
| 7 | 107643–110666 | 32 | 68 | 34 |
| 8 | 110672–114949 | 23 | 77 | 42 |
| 9 | 114950–120208 | 22 | 78 | 32 |
| 10 | 120209–124869 | 12 | 88 | 38 |
| **Total** | **1,000 distinct events** | **272** | **728** | **294** |

Seventeen new SVGs were created and applied: collage, audio editing, video editing, tai chi, Pilates, composting, book discussion, watercolor, improv comedy, language exchange, bicycle repair, scavenger hunt, stroller walk, vinyl turntable, audio mixing console, karaoke and pastel drawing. The catalog now contains 87 custom icons and 1,710 Noto icons. Generated asset revision: `83d0eb7d8f26`.

The earlier explicit targets were also completed: 74219 Pilates Fusion, 78311 Collage Night, 79404 How to Edit Your Podcast, 79412 The Art of Video Editing, and 80421 Sunrise Tai Chi. These five are additional applications, not counted as forward-batch progress.

Pilates was redrawn after feedback about neck length, arm thickness, unequal limbs, contradictory shading and levitation. The current figure uses a side view with aligned limbs, thinner arms, uniform limb color, a shorter neck and seated contact with the mat. Food rescue retains the approved arrow-free design and blue basket contrasting with the hands.

Every current new SVG hash has a [recorded visual pass](20260909-ten-batches-visual.json), inspected at 128, 32, 24 and 16 pixels on light/dark backgrounds. These were distinct creator critiques, not independent reviews. Turntable cartridge placement was corrected after the first render. Small details simplify at 16px; ambiguous concepts such as improv, language exchange and pastel retain labels and strict semantic exclusions.

The [consolidated metadata register](../../.claude/event-metadata-findings.md) contains 140 new stored-context flags from these ten cohorts. Findings cover mismatched formats, mixed event URLs, audience conflicts, venue ambiguity and title-driven emoji choices. They remain investigation leads; this run did not alter event metadata. Existing investigation statuses from other work were preserved.

The [future-artwork shortlist](20260909-ten-batches-shortlist.json) preserves 294 opportunity records spanning 185 distinct saved concepts, including rare styles, instruments, craft techniques and equipment. The largest remaining gaps in this cohort are support groups (17), jazz (15), blues (12), oral storytelling (8) and reggaeton (7). Genre motifs are exploratory and require recognition testing; artist names or musical genres never establish instrumentation by themselves. The full database opportunity inventory contains 686 concepts; it is saved in the scratch output.

Validation: 32 Python tests and 19 JavaScript tests passed. The actual IconManager rendered all 18 assets (17 new plus food rescue) in both themes, including image decoding and cache identity checks. The actual Pilates Fusion search result and event detail were checked at 1440px desktop and 390px mobile widths: icons decoded, no horizontal overflow, no JavaScript errors, and no failed icon requests. Screenshots were inspected alongside the existing UI. The local build and generator consistency check passed. All 31,270 upcoming events have identical expected icon IDs in frontend chunks, built chunks and public NDJSON; review evidence remains outside frontend data. Public past export contains 27,687 events. The standard maintenance helper invalidated three unrelated stale assignments. Tag and place assignment edits: zero.

The broader queue remains open: 30,265 events require review under current catalog/context rules, including previously reviewed events reopened by catalog expansion. This is separate from the completed ten-cohort scope.

Reproduction and rollback: `.scratch/icon-ten-batches-20260909/` holds frozen full contexts, explicit notes, original iteration packets, final reconciled packets and decisions, per-application database backups, visual sheets, build logs, export verification and the global opportunity inventory. `progress.json` tracks the ten distinct cohorts. Generated contact sheets are in `gallery/`.
