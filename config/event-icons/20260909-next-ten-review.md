# September 9: next ten event-icon batches

Completed ten further batches of 100 unique publishable events, IDs **125000–157847**, following the earlier ten-batch run and priority-five expansion. Final decisions: **304 custom assignments, 695 Unicode fallbacks, one deferred review**. These are a sequential backlog cohort, not a random quality sample.

All 1,000 records were read with full name, description, tags, type, short name, venue, address, source, URLs and prior assignments against the complete custom catalog. Repeated descriptions and URL prefixes were losslessly compressed only for reading. No matching rule or keyword classifier made final decisions. The initial snapshot, notes, packets, exact decisions and DB before-images are in `.scratch/icon-next-ten-20260909/`. Five early batches were reconciled to the final catalog; 25 concurrent tag/type corrections were reread before reconciliation. Their icon verdicts remained supported.

## Accepted artwork

All seven designs use original SVG geometry, with no imported art, fonts, brands or external resources. Each has a current-source hash and creator-critical pass in [visual records](20260909-next-ten-visual.json). Reviews covered 128/32/24/16px, light/dark, accepted references, actual IconManager decode and cache behavior. These were creator critiques, not independent recognition tests. Planetarium seats were revised to equal widths and spacing. Supporting detail simplifies at 16px.

| Design | Events assigned in cohort | Representative event | Scope and exclusions |
|---|---:|---|---|
| [Photo editing](art/photo-editing.svg) | 2 | 125000 | Still-image editing, photo enhancement, retouching and Photoshop or Lightroom image-editing instruction. Excludes: Taking photographs, film/video editing, ordinary drawing, or graphic design without image editing. |
| [Still-life drawing](art/still-life-drawing.svg) | 1 | 126045 | Participatory still-life drawing classes and drawing studies explicitly centered on arranged inanimate objects. Excludes: Figure or portrait drawing, general sketching, painting without drawing, or exhibitions without participation. |
| [Croquet](art/croquet.svg) | 1 | 130581 | Croquet play, lessons and dedicated croquet gatherings. Excludes: Cricket, golf, lawn bowls, tennis, or generic lawn games without primary croquet. |
| [Lighthouse](art/lighthouse.svg) | 2 | 137543 | Tours, visits or programs explicitly centered on a lighthouse and its history. Excludes: Unrelated towers, skyscrapers, navigation software or coastal events without a lighthouse focus. |
| [Litter cleanup](art/litter-cleanup.svg) | 5 | 129254 | Volunteer litter collection, trash cleanup and community cleanups where collecting discarded waste is a primary task. Excludes: Composting, food rescue, indoor housecleaning, invasive-plant removal or gardening without an explicit litter-cleanup component. |
| [Planetarium show](art/planetarium.svg) | 3 | 139411 | Shows and immersive screenings explicitly presented inside a planetarium dome, including astronomy, fractal and music-laser programs. Excludes: Outdoor telescope observing, ordinary cinemas, live concerts, observatory tours without a dome show or generic space topics. |
| [Track running](art/track-running.svg) | 27 | 150401 | Running workouts, interval training and running events explicitly conducted on an athletics track. Excludes: Road or trail running, off-track tempo or hill sessions, walking, railway tracks, motor racing, or a club named Track Club whose event is not on a track. |

The new designs cover **41 events**. Photo editing uses a landscape and adjustment sliders; still-life drawing uses arranged objects on paper with a pencil; croquet uses a connected mallet, ball and open wicket. Lighthouse art uses a striped tower, lamp and beams. Litter cleanup uses a grabber holding a bottle above an open bag. Planetarium uses a dome, projected planet and seats. Track running uses continuous oval lanes, an infield and finish marks.

Selection favored distinct reusable activities over club identities, music-name puns or already adequate Noto objects. Track-club names alone do not establish a track session; road intervals and hills remain broad. Pantry work does not imply surplus food rescue. Generic park maintenance does not imply litter collection. Chair exercise does not imply chair yoga. Playing vinyl can use the existing turntable. Participatory watercolor, cross-stitch, clay sculpting, Canasta, karaoke, book clubs, language exchange and storytime use existing precise artwork when supported.

## Batch results

| Batch | ID boundary | Custom | Fallback | Deferred |
|---|---|---:|---:|---:|
| 1 | 125000–130747 | 22 | 77 | 1 |
| 2 | 130756–137535 | 27 | 73 | 0 |
| 3 | 137536–142025 | 19 | 81 | 0 |
| 4 | 142035–146408 | 16 | 84 | 0 |
| 5 | 146423–148863 | 72 | 28 | 0 |
| 6 | 148864–149927 | 83 | 17 | 0 |
| 7 | 149931–150494 | 19 | 81 | 0 |
| 8 | 150495–150596 | 10 | 90 | 0 |
| 9 | 150597–153762 | 11 | 89 | 0 |
| 10 | 153899–157847 | 25 | 75 | 0 |

Event **126714, Pizza Mermaid's Aquarium of Friendship**, remains explicitly deferred because its missing description does not establish the unusual performance format. It retains its fallback pending source investigation; it is not falsely marked resolved.

## Metadata and future art

**280 event-level observations** were appended to the [consolidated metadata register](../../.claude/event-metadata-findings.md). They cover source/occurrence mixtures, title and format errors, incorrect venue prose, ambiguous starting points and inappropriate subject-derived tags. These are observations at review time, not 280 proven or still-open defects: a concurrent task corrected tags/types on 25 cohort records, and its resolution records remain authoritative. This run changed icon assignments only, with no tag, place or event-metadata edits.

The running-source cohort particularly warrants investigation for copied neighboring descriptions and meeting-point conflicts. Examples: 150449 says Engineers Gate but is pinned to East River Park; 150476 says McCarren Track but is pinned to Luna Park Annex; 150493 says Eisenhower Park but is pinned to Mansfield Park. Several club-identity emoji also communicate names rather than activity. Preserve original metadata until investigated.

The [shortlist](20260909-next-ten-shortlist.json) preserves **180 suggestions across 115 concepts**, including rare ideas. Promising next studies are welding, laser cutting, foraging, food distribution, stop-motion animation and macaron morphology. Forest bathing, qigong and seated exercise need careful distinction and physical/anatomical review. Slime-specific sessions are mixed into general playground series and need metadata resolution before narrower assignment. Genre and ensemble sketches remain prospective, especially where the proposed objects could imply unlisted instruments.

## Validation and handoff

48 Python icon tests and 19 JavaScript renderer/catalog tests passed. Hash-bound visual passes and actual light/dark renderer checks passed for all seven new icons. Local export/build and desktop/mobile results are recorded below after verification. No commit, push, upload or deployment was performed.

Frontend and public NDJSON exports matched all **31,269** publishable DB icon choices. All 1,000 cohort decisions validated idempotently; one declared defer remains. Local build and generator freshness check passed. Global pending queue at export: **30,270**; new semantic IDs reopen older reviews, so prepare a fresh queue and use this cohort boundary to avoid repeating work.

All seven designs passed real event search → details checks at 1440px desktop and 390px mobile (14 cases): correct IDs, decoded images, no page errors, no horizontal overflow. Screenshots and network evidence are in the task scratch directory.
