# Pending event icon review — 2026-09-09

**Follow-up completed:** [Five-icon artwork expansion](20260909-artwork-expansion.md) applied all 19 editorial corrections and 22 new-icon assignments locally. The counts and shortlist below describe the preceding review snapshot. Metadata investigations now live in the consolidated register.

Completed the first 100 pending records in ascending event-ID order from a fresh, full-window publishable population of 31,270 events. This is a continuation batch, not a random sample or population-wide quality estimate. Full descriptions, source URLs, venues, tags, prior opportunities and all 60 custom catalog entries were read. No heuristic was accepted without semantic review.

**Saved locally:** 17 custom choices, 83 explicit emoji fallbacks, zero deferrals. Two new choir choices (25850 and 25852); 15 custom choices revalidated. Nine trivia, four DJ decks, two choir, one bingo and one interlocking-brick choice. Seven decisions differ from the title heuristic. The batch contains 25 previously unreviewed records, 64 catalog re-reviews, nine changed-context reviews and two legacy-rule reviews.

All 100 validated before application. The helper saved them in one transaction under the shared advisory lock with an exclusive backup. A second validation reports zero changes; a fresh queue contains none of these 100 IDs. Pending reviews fell from 29,340 to **29,240** with the population unchanged. Tags: zero edits. Places: zero edits. No artwork, taxonomy, source emoji, frontend exports, build or deployment changed. These DB decisions reach the site through a subsequent authorized export/publish.

## Semantic decisions

- **25850 / 25852:** Sacred Harp four-part singing and seven-shape group singing qualify for `format-choir`. Sacred Harp is not an instrument. Keep four-shape and seven-shape future notation concepts distinct.
- **15092 / 16513 / 16515 / 30286:** indirect names conceal DJ programming; DJ context supports decks. Minimal synth in a playlist does not establish a live synthesizer performance.
- **15127:** drag bingo is ordinary `bingo`; no song-identification mechanism supports `music-bingo`.
- **19432:** Duplo building qualifies for interlocking bricks; background music is incidental.
- **23119:** stories, crafts and outdoor play share a nature class; do not force storytime. **12051** rakugo and **33541** personal storytelling/karaoke also do not meet the book-based storytime contract.
- **29265:** garment repair does not establish machine sewing or decorative embroidery. **39918:** couture viewing is not sewing. **37286:** singing within a musical is not a choir event.

## Ranked next artwork studies

These priorities use only this batch’s reviewed evidence. Counts are unique event records and distinct saved venue/address pairs, not forecast assignment totals. The full automatic inventory is available in scratch; it has not received a new population-wide curation in this pass.

| Rank | Concept | Events / venues | Direction and limits |
|---|---|---:|---|
| 1 | `activity-farmers-market` | 13 / 13 | Striped canopy above one produce crate. Thirteen markets at separate venues give broad reuse; compare with existing vegetable artwork and test canopy/crate separation at 16px. |
| 2 | `format-stand-up-comedy` | 5 / 3 | Microphone with one broad laughing mouth. Five events across three venues; compare against the existing microphone before adding complexity. |
| 3 | `craft-mending` | 1 / 1 | Large stitched patch and threaded needle. One distinctive repair event, 29265; avoid implying embroidery or machine use. |
| 4 | `activity-food-rescue` | 2 / 1 | Food crate passed between hands. Two pickup records share one saved venue; simplify the old two-hands-plus-arrow idea before rendering. Do not use DB venue count as pickup-site count. |
| 5 | `format-rakugo` | 1 / 1 | Seated storyteller on a cushion holding a fan. One rare but distinctive format, 12051; verify posture and recognition without relying on costume. |

Garden stewardship is the next practical alternate: hand/plant imagery for 10376 and 43708 at one garden. Existing seedling/potted-plant artwork may already suffice. Drag performance, drum circle and language exchange remain exploratory format studies. Citizenship-exam prep should first compare an existing book/checkmark direction; avoid a document-issuance implication.

Preserve rare genre/style ideas without treating their silhouettes as validated: Latin boogaloo, Northern Soul, shoegaze, surf rock, rockabilly, hot jazz, swing, bluegrass, ska, samba/pagode, and the named dance techniques. The DJ and mixed-band contexts do not justify selecting arbitrary instruments. The genre suggestions often lack a unique 16px motif and require recognition testing before any artwork. Contemporary African dance stays separate from West African dance; the descriptions do not establish a narrower common technique.

## Complete opportunity inventory for this batch

48 evidence-backed suggestions across 28 exact concepts were saved in assignment metadata. Every row below was considered during curation; raw visual directions, exclusions, evidence and URLs are in the saved decision file. No concept below is a newly assignable catalog ID.

| Concept | Events | Representative IDs |
|---|---:|---|
| `activity-citizenship-exam-prep` | 1 | 42235 |
| `activity-farmers-market` | 13 | 17423, 17996, 17997, 17998, 18002 |
| `activity-food-rescue` | 2 | 1989, 8865 |
| `activity-garden-stewardship` | 2 | 10376, 43708 |
| `craft-mending` | 1 | 29265 |
| `dance-bhangra` | 1 | 32332 |
| `dance-contemporary-african` | 1 | 31467 |
| `dance-horton` | 1 | 17788 |
| `dance-samba` | 1 | 34267 |
| `dance-west-african` | 1 | 15480 |
| `format-drag-show` | 2 | 23284, 39029 |
| `format-drum-circle` | 1 | 24049 |
| `format-language-exchange` | 1 | 36793 |
| `format-rakugo` | 1 | 12051 |
| `format-stand-up-comedy` | 5 | 9746, 9747, 9749, 27265, 35324 |
| `genre-bluegrass` | 1 | 24204 |
| `genre-hot-jazz` | 1 | 18453 |
| `genre-latin-boogaloo` | 1 | 16515 |
| `genre-northern-soul` | 1 | 16515 |
| `genre-rockabilly` | 1 | 40630 |
| `genre-samba-pagode` | 1 | 39091 |
| `genre-seven-shape-singing` | 1 | 25852 |
| `genre-shape-note` | 1 | 25850 |
| `genre-shoegaze` | 1 | 16513 |
| `genre-ska` | 1 | 16514 |
| `genre-soul` | 1 | 16515 |
| `genre-surf-rock` | 1 | 16511 |
| `genre-swing` | 2 | 18453, 40630 |

## Existing artwork editorial queue

The review helper deliberately retains source emoji for fallback decisions. These evidence-backed editorial improvements are recorded for a separate emoji pass; they are not new-art requests or applied changes. The pinned Noto catalog already includes open book (`noto-1f4d6`), microphone (`noto-1f3a4`), musical notes (`noto-1f3b6`), climbing person (`noto-1f9d7`), speech bubble (`noto-1f4ac`), dress (`noto-1f457`) and theater masks (`noto-1f3ad`).

- 3244 Broken Dishes: open book instead of plate; 35323 NeuroNautic reading: book/microphone instead of brain.
- 9749 Hot Soup and 27265 Hump Day comedy: microphone instead of bowl/camel. 35324 Party City also needs comedy rather than a generic party cue.
- 3288 and 3290: climbing artwork would clarify the activity; community identity remains in labels.
- 16511 surf rock, 18453 Foxtail, and 40630 Slippery Chickens: musical notes instead of surfer/fox/chicken; avoid inferring a featured instrument.
- 36793 Mandarin practice: speech bubble instead of a national flag. 38603 karaoke: microphone instead of manicure.
- 13820, 38019 and 45202: framed art or palette clarifies exhibition/painting over eye/star/city-night subject imagery. 39918 couture viewing can use dress or framed art instead of coffee.
- 37286 Broadway musical: theater artwork over drinks. 48424/48425 committee meetings: government/discussion imagery over bicycle/tree topic imagery.

## Separate metadata findings

All open metadata findings from this and earlier icon reviews are consolidated in the
[event metadata findings register](../../.claude/event-metadata-findings.md).
That register owns future investigation and resolution status; the original packet
preserves the evidence observed in this review. Artwork edits do not resolve them.

## Reproduction and handoff

Catalog semantic revision: `1e23cc92ed5208b32fd06b513b8a9dc59d494e9128373e70f8f2c4d5f54c8982`. Git revision at review: `33d4a710b2c0d68a5c3517573101b71814e9bfa1`; the shared checkout has unrelated pre-existing edits. Full catalog contents are frozen in the packet.

All task artifacts are in `.scratch/icon-review-20260909-next/`: original `packets/batch-0000.json`, `decisions-0000.json`, `assignments-before-0000.json`, `verification.json` with content checksums, and refreshed `after/` queue. The next pending ID is 49408. Regenerate before applying later batches because the shared DB may change.

`opportunities/opportunities.json` and `.md` contain the automatic whole-window inventory: 580 concepts from 8,894 context-current opportunity reviews, with 2,474 context-stale/deferred reviews excluded. This helper includes older catalog revisions when event context remains current; its coverage count is therefore different from the current-catalog assignment queue. Do not infer that all 8,894 have been re-reviewed against the latest 60 icons.
