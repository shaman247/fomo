# Custom-icon expansion — September 8, 2026

**Artwork correction:** Subsequent user feedback rejected the trombone geometry and
cello/bass contours. Their original visual passes below are historical and superseded
by the [corrected artwork review](20260908-instrument-corrections.md). Assignment
decisions remain unchanged.

Ten original Noto-style SVGs are accepted and integrated locally. The catalog now
contains 25 custom icons plus 1,710 pinned Noto icons (build revision `0f1828d49ea5`).
No upload, commit, or push was performed.

## Accepted artwork and explicit associations

| Icon ID | Subject | Reviewed events assigned |
| --- | --- | ---: |
| `sport-pickleball` | Paddle and perforated ball | 53 |
| `activity-interlocking-bricks` | Interlocking toy brick | 75 |
| `equipment-dj-decks` | Two-deck DJ console | 450 |
| `craft-crochet` | Hook and yarn | 46 |
| `instrument-trombone` | Slide trombone | 14 |
| `instrument-steelpan` | Steelpan bowl and mallets | 1 |
| `instrument-kalimba` | Wooden thumb piano | 0 |
| `instrument-guzheng` | Long bridged zither | 2 |
| `instrument-cello` | Cello and bow | 16 |
| `instrument-double-bass` | Upright double bass | 1 |
| **Total** | | **658** |

The artwork is in `../art/`, with semantic use/avoid guidance in `../catalog.json`.
69 existing tag rows received independently reviewed `icon_id` associations:
7 curated tags and 62 keywords. Exact instrument/activity tags and closely scoped
classes, techniques and formats qualify; mixed topics, artist names and demographic
DJ tags do not. No Kalimba tag exists, so none was invented or promoted. The kalimba
asset remains available for future qualifying events. No places were assigned an
icon: the current custom place override is not implemented, and a hosted event does
not establish a venue's identity.

## Automated visual acceptance

Creators iterated on physical construction and small-size clarity. In particular,
the trombone tubing was corrected, steelpan note fields softened, and the guzheng
changed from a box-like silhouette to an arched, low zither body. A separate critic
recorded blind recognition before reading labels, then assessed 16/24/32/128 px
renders on light and dark backgrounds. All ten final SVGs passed. Acceptance is
bound to each exact source SHA-256 in
[the machine-readable review](20260908-expansion-visual.json).

The coordinator also inspected the production renderer's output through all nine
site themes at 16/24/32 px. All 90 icon/theme preparations were nonempty and error
free; repeated preparation returned cached results. No artwork uses text, fonts,
embedded images, filters, scripts or external resources.

Small-size limits remain explicit: at 16 px the DJ console can resemble a generic
two-dial console, the guzheng reads as a zither without uniquely identifying the
regional subtype, and cello versus double-bass distinctions weaken. Their silhouettes
remain useful at normal 24/32 px sizes. Pixelation and dithering intentionally soften
strings and controls. These are reviewed limitations, not claims of perfect subtype
recognition at every size.

Local evidence:

- `.scratch/icon-expansion-20260908/gallery/icons.png`: labeled contact sheet.
- `.scratch/icon-expansion-20260908/gallery/themes.png`: actual renderer, nine themes.
- `.scratch/icon-expansion-20260908/gallery/render-verification.json`: runtime checks.
- `.scratch/icon-expansion-20260908/{general-v1,music-v2,strings-v2}-critique.md`:
  independent critique and blind guesses.

## Construction and provenance

All paths were drawn for this project. Existing accepted custom artwork and pinned
Noto artwork were style comparisons; no upstream paths were copied and no new asset
license dependency was introduced. Reference products establish physical structure,
not a claim that these simplified icons depict an exact commercial model.

- Trombone: [Yamaha structure guide](https://www.yamaha.com/en/musical_instrument_guide/trombone/mechanism/).
- Steelpan: [Panyard C-20](https://shop.panyard.com/products/new-c-20-lead-pan-high-gloss-silver-package)
  and [note-field diagram](https://shop.panyard.com/cdn/shop/files/C-20_Diagram_V1.png?v=1745712384).
  Nine broad fields simplify the instrument; they do not assert a precise scale.
- Kalimba: [HOKEMA B17](https://www.hokema.de/en/products/hokema-kalimba-b17-440hz-sonderstimmung)
  and [playing instructions](https://www.hokema.de/en/pages/spielanleitung-kalimba-b17).
  A generic nine-tine board, without a specific tuning claim.
- Cello: [Yamaha VC7SG](https://uk.yamaha.com/en/musical-instruments/strings/products/acoustic-strings/vc7sg/).
- Double bass: [Eastman models](https://www.eastmanstrings.com/new-models/)
  and [Mainfranken Theater musician profile](https://www.mainfrankentheater.de/blog/beate-kroehnert/vielsaitig-begabt/).
- Guzheng: [Dunhuang instrument listing](https://www.chinesemusic.com.au/product-page/%E6%95%A6%E7%85%8C%E7%89%8C-%E7%84%A6%E7%AA%97%E5%A4%9C%E9%9B%A8-professional-rosewood-guzheng-694kk).
  Full reference photos were not accessible for every bass/guzheng source; the
  creator used available maker construction information and image-search descriptions.
  This is not a claim that inaccessible photos were visually inspected.

## Full-context assignment review

Candidate retrieval scanned 30,563 publishable events in the active export window.
Two reviewers read all 1,065 retrieved candidates in full context against all 25
available custom icons. Retrieval keywords only selected candidates; they did not
make the final assignment. This was a focused rollout, not another exhaustive
30,563-event semantic audit, and discovery patterns cannot guarantee full recall.

Final outcomes: **662 assign, 402 fallback, 1 defer**. The assignments include the
658 new-icon events above, two trivia events and two music-bingo events. There are
659 display changes relative to the initial saved assignment state. Reviewers also
saved 106 grounded opportunity suggestions across 41 concepts, including knitting,
dance styles, ensembles, additional instruments and exploratory genre treatments.

Featured instruments, lessons and clearly led performances qualify. Supporting
instrumentation in large mixed bills does not. DJ-backed skating, dinners, karaoke
and incidental DJ appearances keep a broader icon. Mixed knitting/crochet groups,
LEGO movies, robotics-focused classes and broadly mixed activity events likewise avoid misleading specificity.
Featured Trombone Shorty events were corroborated against the
[Blue Note artist biography](https://www.bluenote.com/artist/trombone-shorty/), rather
than relying on the stage name alone.

Current-database validation caught 79 tag-only changes made during the review.
The coordinator inspected every delta: equivalent tag normalization/deduplication
(e.g. Crocheting → Crochet, Legos → LEGO, Children → Kids), with unchanged primary
content and assignment rows. Fresh packets and decision hashes were produced after
rechecking the decisions. All 1,065 then passed current-state validation and were
saved under the shared write lock with a rollback backup.

Event **248442, The Nields / Francesca Hoffman**, remains explicitly deferred: its
concert title conflicts with an unrelated Tommi Calamari/eden DJ timetable in the
description. A bounded source lookup did not establish a correction. The metadata
issue is filed in backlog; no event content was changed to guess at a resolution.

A final coordinator comparison found inconsistent LEGO robotics decisions across
the two batches. Five brick assignments were changed to fallback under the lock
with a separate backup. All seven robotics-focused classes/competitions now retain
their source emoji; brick clubs and non-robotic building challenges keep the custom
brick. Final totals above include these corrections.

The new catalog correctly reopens older reviews elsewhere for a future full-catalog
pass. After refresh, the global queue contains 29,499 pending records; within this
1,065-event cohort only the deliberate defer remains pending. A changed catalog does
not justify silently marking unrelated older reviews current.

## Verification and cost

- 40 event-icon tests and 4 tag-assignment tests passed.
- Catalog generation and `build.cjs --check` passed, with hash-bound reviewed assets.
- Production `npm run build` passed.
- All 30,563 exported event icon IDs matched database-backed resolution; all 1,065
  cohort records and all 69 saved tag associations were checked. Review evidence and
  opportunities are not added to public event payloads.
- Source and production export files and generated SVG assets were compared after build.
- Ten SVGs total **17,670 bytes raw / 7,097 bytes per-file gzip**. These are asset
  sizes, not measured network latency. A cached raster is 16 KiB of pixel data at
  DPR 1 or 64 KiB at DPR 2 per icon, before canvas/atlas copies and theme variants.
- No new semantic heuristics or browser matching logic were introduced. The legacy
  heuristic test now covers legacy rules rather than requiring every new catalog
  icon to have a regex rule.

Reversible records and full decisions are under `.scratch/icon-expansion-20260908/`:
`events-before.json`, `tags-before.json`, `current-packet.json`,
`final-decisions.json`, `tag-plan.json`, `final-event-summary.json`,
`robotics-before.json`, `robotics-decisions.json`,
`candidate-opportunities.json`, `export-verification.json`, and `asset-metrics.json`.
The database is the durable source of truth for assignments, rationale and future
icon opportunities. The independent hash-bound artwork acceptance record lives in
this tracked review directory.
