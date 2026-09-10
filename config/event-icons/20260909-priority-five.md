# Five priority icons — September 9, 2026

Created and integrated the five recommended priority designs: block party, pasta making, tarot, button making, and weaving. This is a targeted implementation of the saved opportunity shortlist, not another population-wide audit. All work is local; no commit, push, upload, or deployment.

## Artwork and event impact

| Stable ID | Visual cue and eligibility | Reviewed candidates | Assigned |
| --- | --- | ---: | ---: |
| `activity-block-party` | Buildings, bunting and a street barricade; explicit neighborhood street celebrations | 51 | 51 |
| `activity-pasta-making` | Hands shaping dough above a board with pasta pieces; hands-on pasta classes | 13 | 12 |
| `activity-tarot` | Fanned cards with original sun/moon illustrations; readings, practice and card-focused exhibitions | 9 | 6 |
| `equipment-button-press` | Connected lever press, aligned dies and a finished badge; dedicated pin-button making | 6 | 1 |
| `craft-weaving` | Open loom frame, warp, woven band and shuttle; participatory loom weaving | 6 | 3 |
| **Total distinct events** | **73 custom assignments, 12 explicit fallbacks, no deferrals** | **85** | **73** |

Tag edits: **0**. Place edits: **0**. Existing event emoji values were preserved. All 85 preceding choices were agent fallbacks; no manual choices were replaced.

These are original SVG compositions following the accepted local Noto-style system; no third-party artwork or deck design was copied. Authoritative sources live in `art/`, with eligibility and exclusions in `catalog.json`. New art is roughly 6.1 KB raw / 2.9 KB separately gzipped in total. Assets remain demand-loaded; five 128×128 RGBA buffers are 320 KiB per raster set before browser overhead or theme variants. No performance improvement or physical-device benchmark is claimed.

## Assignment boundaries

Full event descriptions, tags, format, venue, source and URLs were reviewed against the complete custom catalog. Candidates came from the prior saved opportunity inventory, including the exact `equipment-tarot-cards` and `craft-frame-loom-weaving` aliases. All 85 remained publishable in the fresh 31,270-event snapshot. Snapshot SHA-256: `07f42e1f0e9fddb16982bc9138ee1e2717eff43197304f3b4ff9fc99fdff74ca`.

The 12 fallbacks are deliberate:

| Event ID | Reason |
| --- | --- |
| 98052 | Variable pizza-or-pasta cooking party; pasta is not guaranteed. |
| 108639 | Mixed knitting, crochet, embroidery and weaving studio. |
| 117627 | Fiber-art installation inspired by weaving; no established working-loom activity. |
| 150111 | Anime screening and button making share the program. |
| 219137 | Author reading and tea gathering with additional divination activities. |
| 220931 | Book browsing, reflection, conversation and optional tarot readings. |
| 223056 | Combined meditation, tarot, yoga and journaling workshop. |
| 232185 | Rotating DIY series with several crafts. |
| 240418 | Stool construction with a woven seat; the chair fallback represents the project. |
| 242120 | Exhibition closing celebration with several activities. |
| 242340 | Makerspace with several optional tools. |
| 243789 | Buttons, fuse beads and shrink-plastic crafts offered equally. |

Tarot-card exhibition 113685 receives the object-only tarot artwork: it does not depict a reading service. Pasta-and-cheese workshop 91023 receives pasta making because hand-shaping dough is explicitly taught and the tasting accompanies it. Rigid-heddle class 240595 receives the broader weaving icon; the simplified loom does not promise a particular model. Generic named celebrations such as “25 years later” were matched from explicit block-party descriptions and source context, not their titles alone.

Unimplemented opportunity evidence was preserved in review metadata. A specific chair-seat-weaving opportunity replaces the overly broad weaving suggestion for 240418. Twelve opportunity records remain in the 85 decisions; created concepts are no longer treated as missing artwork in these reviews. The browser check exposed a possible weekly-course/continuous-span discrepancy for Weaving 101 (240258), recorded in the [consolidated metadata register](../../.claude/event-metadata-findings.md). No unrelated metadata corrections were made.

## Visual review and validation

The [visual record](20260909-priority-five-visual.json) binds each pass to its exact source SHA-256. Review mode is **creator critical pass**, not an independent or blind recognition study. First-render issues were corrected: the pasta ribbon was simplified and its board darkened for contrast; the loom's opaque backing was removed. Final sources were inspected at 128/32/24/16 px alongside farmers market, knitting and sewing-machine references, and through the actual `IconManager` in light/dark modes. Fine details simplify at 16 px; labels remain necessary.

- 40 Python event-icon tests and 19 JavaScript icon-renderer/pack tests passed.
- Catalog generation/check and normal production build passed. Catalog: 92 custom + 1,710 Noto icons; generated revision `663bb34406f4`.
- All five icons passed real event search → popup checks at 1440 px desktop and 390 px mobile: ten cases, decoded images, no horizontal overflow, no failed icon responses and no browser page errors. Desktop pasta and mobile loom/button surfaces were visually inspected. The test uses exact event IDs; an initial title-only tarot lookup selected a different meetup, so the final tarot example is Tipsy Tarot (98634).
- Official batch helper dry run validated all 85 records, then applied them under the shared advisory lock with a unique before-image.
- Post-application validation is idempotent and the scoped pending count is zero.
- Local frontend chunks and public upcoming NDJSON were regenerated under the shared lock. Every one of the 31,270 exported event icon IDs was verified against current valid DB assignments; the 73 new assignments match in both exports.
- The broader review queue still contains 31,185 records, including 9,411 existing reviews reopened by the expanded semantic catalog. This targeted implementation does not claim to have reviewed that broader backlog.

## Evidence and rollback

Scratch directory: `.scratch/icon-priority-five-20260909/`.

- `candidates.json`, `snapshot.json`: saved concept inventory and fresh full-context snapshot.
- `apply-packet.json`, `decisions.json`: exact reviewed context, catalog, decisions and supporting evidence for all 85 events.
- `assignments-before.json`: official helper before-image for the applied batch.
- `catalog-before.json`: catalog before this five-icon addition, preserving earlier shared-workspace additions.
- `maintenance-before.json`, `export-verification.json`, `build.log`: locked local export and verification evidence.
- `review-v1-rendered/`, `review-v2/`: first and revised visual-review packets and source hashes.
- `gallery/icons.png`, `gallery/themes.png`, `gallery/render-verification.json`: compact previews and ten actual light/dark renderer checks, with successful shared-cache reuse.
- `site-smoke.json`, `site-*-search.png`, `site-*-popup.png`: all ten desktop/mobile event-search and popup checks against the built public-only site copy.

Restore only this batch's IDs from its before-image when rolling back; do not replace shared tables or revert other sessions' catalog work. Old hashed assets are retained for cached clients.
