# Six-icon integration and next 100-event review — September 9, 2026

Created and applied six original SVGs to **20 events**. Reviewed the next **100 sequential events, IDs 157875–162302: 33 custom / 67 fallback / 0 deferred**. The separate artwork target review covers 20 previously shortlisted records (16 custom, 4 fallback), plus three dedicated screening/Q&A supplements (3 custom). Total: **123 records, 52 custom / 71 fallback / 0 deferred**. Event counts are unique records, not occurrences.

## New artwork

| Artwork | Semantic ID | Applied events |
|---|---|---:|
| Community food distribution | `activity-food-distribution` | 13 |
| Film screening and Q&A | `format-film-qa` | 3 |
| Welding | `craft-welding` | 1 |
| Laser cutter | `equipment-laser-cutter` | 1 |
| French macarons | `cuisine-macarons` | 1 |
| Stop-motion animation | `activity-stop-motion` | 1 |

The catalog now contains **105 custom icons plus 1,710 pinned Noto icons**. Original geometry uses 128×128 SVG viewboxes and no external fonts, scripts, images or filters. Unicode fallbacks are unchanged. The community distribution icon uses a warm grocery box and one supporting peach hand with a teal sleeve; it is separate from surplus-food rescue's blue basket. Food preparation/meal service and commercial food shopping remain excluded.

[Visual review records](20260909-six-followup-visual.json) bind all six passes to their exact source hashes. This was a distinct **creator critical pass**, not an independent reviewer or blind recognition study. Rendered at 128, 32, 24 and 16 CSS px; native light/dark samples also went through actual IconManager preparation and cache reuse. No material defect remained in the reviewed draft. At 16 px, laser-cutting mechanism details and the stop-motion figure's pose change become less specific; their machine/film-sequence silhouettes survive. Broad pastel macaron shells and filling remain separated. Reference art: accepted food rescue, electronics soldering and video editing.

## Assignment boundaries and metadata findings

The four original film candidates keep their existing fallbacks. Current source/occurrence checks do not support assigning the Q&A icon to their whole screening runs:

- **132999 — Maddie’s Secret:** stored description retains June preview Q&As, while stored upcoming shows are September 9/10 at 11am. The official page advertises a separate September 13, 5:30pm Q&A. [IFC source](https://www.ifccenter.com/films/maddies-secret/).
- **134369 — Mysterious Skin:** upcoming ordinary shows do not inherit past August filmmaker Q&As or the premiere description. [IFC source](https://www.ifccenter.com/films/mysterious-skin/).
- **142583 — Wild Inside:** Q&As and birdwatching walks belong to dated August specials; upcoming September 9/10 shows are ordinary screenings. [IFC source](https://www.ifccenter.com/films/wild-inside/).
- **153757 — A Sad and Beautiful World:** official current page shows September 9/10 screenings with no Q&A announcement, unlike the stored Q&A-only description. [Quad source](https://quadcinema.com/film/a-sad-and-beautiful-world/).

Instead, `format-film-qa` is applied to dedicated records **211366, 212351 and 218537**. Title, full event context and single upcoming occurrence establish a screening followed by discussion for each. **218537 — Soul Patrol** additionally matches the official September 15, 7pm premiere and Q&A. [IFC source](https://www.ifccenter.com/films/soul-patrol/). Live web fetches for the other two dedicated pages were unavailable; their stored explicit titles/descriptions, source URLs and occurrences were reviewed, and no contradictory context was found.

The canonical [metadata findings register](../../.claude/event-metadata-findings.md) has **10 new rows and 2 existing rows updated**. It also retains the already-open food-distribution Farmers Market tag and stop-motion Screening type findings. New observations cover venue identity, missing history classification, mixed evening/lunchtime tours, fashion-show format, captioned/standard screening scope and an apparent multi-artist source merge. Only the four film-scope cases were source-checked here; other metadata observations remain investigations. No event descriptions, emoji, tags, types, places or taxonomy were changed in this task.

## Next opportunities

All 100 events received both a current-display decision and future-opportunity consideration. **25 suggestions across 23 concepts** are saved with event evidence in the DB. The [curated shortlist](20260909-six-followup-shortlist.json) preserves all 23, including rare printmaking techniques and supported musical repertoire. Promising studies: pétanque, Catan, guitar controller, carborundum aquatint, runway fashion show and roast battle. Sound-bath concept aliases are noted for editorial consolidation; uncertain instrument/genre motifs remain exploratory.

The read-only global saved-opportunity report contains **713 concepts from 9,919 eligible saved reviews**, with 2,162 stale reviews excluded. These are report coverage counts, not a claim that the remaining population has been freshly reviewed. Existing art now covers the six implemented concepts; do not manufacture duplicate art from old suggestions.

## Validation and local state

- **48 Python icon tests and 19 JavaScript icon tests passed.**
- All six artwork sources match their accepted review hashes; catalog generation and `--check` passed. Generated revision: `6d9b66c4c26b`.
- All **123** decisions validate against fresh full DB context and are idempotent. Their fresh queue contains **zero pending records**.
- Under the shared advisory write lock, refreshed review state, exported events/public datasets and built the site locally. Verified **31,269** upcoming records in DB, frontend chunks, built chunks and public NDJSON; icon IDs agree and review evidence does not leak into frontend data.
- **12 real-site checks**: every new icon in search and event details at desktop 1440×1000 and mobile 390×844; all assets decoded, no page errors or horizontal overflow. Actual screenshots also inspected for integration with existing UI.
- Event icon impact: **20 new-art assignments**, plus **32 existing custom choices** in the reviewed cohort. **Tag edits: 0. Place edits: 0.**
- Local DB, generated assets, exports and build are ready. **No commit, push, upload or deployment.**

Semantic catalog revision: `7d472d6076bbe75cda416cb165363ca436fe1c727c235b229f2da744f96fa79e`. A catalog expansion reopens earlier semantic reviews, so the global pending count is **31,146** (18,954 unreviewed, 9,796 changed-catalog, 2,258 changed/deferred, 138 legacy-rule). Existing artwork does not become a new unsupported assignment automatically.

Resume the sequential backlog **after event ID 162302**, preparing fresh context under the current catalog. The three Q&A supplements were intentionally outside that sequence and should be skipped while their reviews remain current. This run did not revisit earlier unresolved deferrals outside its cohort.

Evidence directory: `.scratch/icon-six-followup-20260909/`. Full snapshots/decisions: `frozen-00..02.json`, `packet-00..02.json`, `decisions-00..02.json`; rollback backups: `icons-before-00..02.json` and `maintenance-before.json`. Visual packet: `review-v1/`; native previews: `gallery-v1/`; final export comparison: `export-verification.json`; UI results: `site-smoke.json`; global opportunity report: `opportunities/`. These large evidence files are gitignored; compact review and candidate decisions above are durable source artifacts.
