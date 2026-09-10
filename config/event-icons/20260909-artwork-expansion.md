# Reviewed artwork expansion — 2026-09-09

Created and accepted the five designs shortlisted in the [100-event review](20260909-event-review.md), applied its 19 existing-artwork corrections, and consolidated open metadata findings in the [investigation register](../../.claude/event-metadata-findings.md). All final data and build changes are local; nothing was uploaded or deployed.

## Artwork and explicit event assignments

The catalog now contains 65 custom SVGs. The new assignment scope is the previously reviewed 100-event cohort, with unchanged full event context except the 19 requested source-emoji corrections. There was no global keyword reassignment.

| Icon | Source | Event assignments | Reviewed meaning and exclusions |
|---|---|---:|---|
| `activity-farmers-market` | [Farmers market](art/farmers-market.svg) | 13 | Markets primarily selling local farm produce and farm-made food directly to shoppers. Excludes: Generic flea/craft markets, food festivals, grocery shopping, cooking classes, or incidental produce stalls. |
| `format-stand-up-comedy` | [Stand-up comedy](art/stand-up-comedy.svg) | 5 | Stand-up comedy shows, spoken comic sets and participatory stand-up open mics. Excludes: Sketch/improv theater without stand-up, films, generic theater comedy, singing, or comedy only incidental to another activity. |
| `craft-mending` | [Garment mending](art/mending.svg) | 1 | Repairing, patching or darning worn clothing and fabric; dedicated garment-mending instruction or circles. Excludes: Decorative embroidery without repair, new garment construction, machine-sewing classes without a repair focus, or generic textile arts. |
| `activity-food-rescue` | [Food rescue](art/food-rescue.svg) | 2 | Volunteer collection and redistribution of surplus food for community food programs. Excludes: Shopping, food tastings, general food service/cooking, recycling nonfood materials, or food drives without surplus-food recovery context. |
| `format-rakugo` | [Rakugo storytelling](art/rakugo.svg) | 1 | Performances or instruction explicitly centered on the Japanese seated comic storytelling form rakugo. Excludes: Generic storytelling, book storytime, stand-up, theater with incidental rakugo, or Japanese culture without this performance form. |

**Impact:** 22 events received new custom IDs. Nineteen events received existing Noto emoji corrections, with three overlaps (stand-up events); 38 distinct events therefore have changed display/source-art choices. All 100 cohort reviews were refreshed against the 65-icon catalog: 39 custom choices, 61 explicit fallbacks, zero deferrals. The 22 now-covered opportunity mentions were removed from prospective metadata, leaving 26 suggestions for future work. Tags: zero edits. Places: zero edits. Event titles, descriptions, dates, source links and taxonomy were not corrected by this artwork pass.

## Visual review and provenance

All artwork is original SVG geometry extending the accepted local system. No external image bytes were copied. Designs use the existing 128px viewBox, shaded planes, restrained outlines and Noto-family palette. No embedded raster, runtime text, external resource, or new frontend semantic inference was introduced. The new assets use the renderer’s supported individual, on-demand downloads.

The creator inspected unlabeled/labeled renders at native 16/24/32px and 128px on white and dark backgrounds, alongside embroidery, storytime, trivia, and pinned Noto microphone/carrot references. This was a distinct **creator critical pass, not an independent or blind evaluation**. One material revision moved the stand-up microphone cable to the rotated handle base. All five final SHA-256 values have a pass in [the visual record](20260909-artwork-visual.json).

Final artwork was also inspected through the real IconManager in all nine site themes (45 icon/theme variants). Repeated rendering returned the same cached object; every variant decoded with nonempty pixels. Monochrome/pixel themes lose small detail and color. Food rescue can also suggest donation or mutual aid without its label; rakugo may read as a seated fan performer to an unfamiliar viewer. Assignment rules retain the narrow meanings rather than treating visual resemblance as evidence.

Rakugo posture/props were checked against the Japan Foundation’s [Rakugo teaching resource](https://classroomresources.sydney.jpf.go.jp/jpfmedia/katsura.sunshine.tasksheet%28rakugo%20quiz%EF%BC%89.pdf): one storyteller kneels on a cushion with a fan and hand towel. The new pictogram represents the form, not a portrait of a named performer.

## Existing-artwork corrections

Each source emoji was compared exactly in Python and updated by explicit event ID under the shared DB lock. Current full context and manual-choice protections were checked before writing. The final custom icon takes precedence for the three comedy rows that also received new custom art; the corrected microphone remains their Unicode fallback.

| Event ID | Event | Before | Corrected fallback | Noto ID |
|---|---|---|---|---|
| 3244 | Broken Dishes Book Club with Swati | 🍽️ | 📖 | `noto-1f4d6` |
| 35323 | NeuroNautic Institute Presents | 🧠 | 📖 | `noto-1f4d6` |
| 9749 | Hot Soup Comedy | 🥣 | 🎤 | `noto-1f3a4` |
| 27265 | The Hump Day Soiree Comedy open mic | 🐪 | 🎤 | `noto-1f3a4` |
| 35324 | Party City | 🎉 | 🎤 | `noto-1f3a4` |
| 3288 | Bipoc Meetup | ✊🏾 | 🧗 | `noto-1f9d7` |
| 3290 | Queer Climb Night | 🏳️‍🌈 | 🧗 | `noto-1f9d7` |
| 16511 | Unsteady Freddie's Surf-Rock Shindig | 🏄🏽 | 🎶 | `noto-1f3b6` |
| 18453 | Foxtail at Arlo SoHo | 🦊 | 🎶 | `noto-1f3b6` |
| 40630 | The Slippery Chickens | 🐔 | 🎶 | `noto-1f3b6` |
| 36793 | Mandarin Meet-up | 🇨🇳 | 💬 | `noto-1f4ac` |
| 38603 | Yas Kween Karaoke with Leslie | 💅 | 🎤 | `noto-1f3a4` |
| 13820 | Hortensia Mi Kafchin: Through Different Eyes | 👁️ | 🖼️ | `noto-1f5bc` |
| 38019 | Whitney Biennial 2026 | 🌟 | 🖼️ | `noto-1f5bc` |
| 45202 | Starry Night Over Empire State Building | 🌃 | 🎨 | `noto-1f3a8` |
| 39918 | Member Mornings: Iris van Herpen | ☕ | 👗 | `noto-1f457` |
| 37286 | The Great Gatsby | 🥂 | 🎭 | `noto-1f3ad` |
| 48424 | Transportation Committee Meeting | 🚲 | 🏛️ | `noto-1f3db` |
| 48425 | Parks, Landmarks & Cultural Affairs Committee Meeting | 🌳 | 🏛️ | `noto-1f3db` |

## Metadata investigation handoff

The single [metadata findings register](../../.claude/event-metadata-findings.md) contains 32 open investigation rows covering daily, weekly and expansion reviews through September 9. Each includes event/tag IDs, the observed conflict, a next investigation step and status, plus links to original evidence. The normal backlog links to it, and the September 9 report now points there. Historical reports remain evidence; future status belongs in the register. Consolidation does not mark any data issue fixed.

## Validation and operating status

- 40 existing Python event-icon tests and 19 relevant frontend resolver/pack tests pass. No new test mirrors static SVG geometry.
- The validated batch helper saved all 100 cohort reviews with a before-image backup under the shared lock. Revalidation during export matched every saved row exactly, and the cohort has zero pending reviews.
- All 31,270 local frontend event IDs match DB-resolved artwork; public upcoming NDJSON agrees with those chunks. Source/dist event chunks match and contain no private review metadata.
- Asset generator safety/freshness checks and the local production build pass. Five current source hashes match the accepted visual record.
- Real-site search → event details passed at 1440×1000 desktop and 390×844 mobile. Rakugo artwork decoded in search and details, with no horizontal overflow or page errors; the desktop screenshot also verifies its map sprite. The detail-sheet layout was checked alongside existing venue/tag artwork. `site-smoke.json` and screenshots preserve the evidence.
- Initial smoke attempts had an incomplete public preview (vendor/CSS omissions) and an outdated floating-popup selector. Correcting the test setup resolved both; no production-code change was necessary.
- Five SVGs total 7499 bytes, or 3436 bytes individually gzipped. This is an artifact-size result, not a field-performance benchmark.

Adding semantic catalog IDs intentionally reopens prior catalog reviews outside this cohort: **31,170** records are now pending against the expanded catalog. The normal pre-export maintenance also invalidated 387 previously stale saved reviews; it did not choose replacement artwork for them. Their before-images are preserved in `maintenance-before.json`. The cohort of 100 remains current. No broad opportunity audit is claimed by this integration.

Artifacts/backups: `.scratch/icon-artwork-20260909/` contains `current-events.json`, `context-changes.json` (empty), `editorial-plan.json`, `emoji-before.json`, `assignment-packet.json`, `assignment-decisions.json`, `assignments-before.json`, `maintenance-before.json`, `catalog-before.json`, visual packets `review-v1/` and `review-v2/`, the final gallery and theme renders, `export-verification.json`, `asset-verification.json`, and `build.log`. The public upcoming/past NDJSON exports were regenerated locally.
