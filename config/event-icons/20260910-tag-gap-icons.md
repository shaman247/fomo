# Tag-gap custom icons — September 10, 2026

Created and registered **14 SVG icons**, with **41 explicit local tag assignments: 28 event-scope and 13 venue-scope**. **0 event assignments / 0 location assignments.** Original Unicode fallbacks are preserved. The preceding [hierarchy audit](20260909-tag-hierarchy-review.md) and user-approved tanpura guidance remain applicable.

| New icon | Tags receiving it | Raw / gzip bytes |
| --- | --- | --- |
| Tap dance shoe | Tap Dance | 2029 / 1060 |
| Singing bowl | Sound Bath | 4492 / 2123 |
| Animation | Animation, Anime | 4515 / 2009 |
| Hand puppetry | Puppetry, Puppet Show | 3142 / 1613 |
| Risograph printing | Risograph | 2907 / 1436 |
| Vibraphone | Vibraphone | 8074 / 3762 |
| Chamber ensemble | Chamber Ensemble, Chamber Music | 2681 / 1240 |
| Musical duo | Duo, Acoustic Duo, Jazz Duo | 2304 / 1120 |
| Oud | Available for explicit oud programs; no assignment yet | 6455 / 2976 |
| Printmaking | Printmaking, Block Printing | 2772 / 1375 |
| Performance stage | Performance Space, Performing Arts | 1689 / 878 |
| Historic site | Historic Site | 1925 / 936 |
| Partner dance | Partner Dance, Social Dance, Ballroom, Ballroom Dance, Salsa, Bachata, Swing Dance, Lindy Hop | 3880 / 2023 |
| Contemporary dance | Contemporary Dance, Modern Dance | 2351 / 1269 |

The oud is available for instrument-specific programs; it does not represent all Arabic, Levantine or Middle Eastern music. Tango/Argentine Tango remain unchanged because their tag evidence includes music-only programs. Venue Ballroom remains a room category. Broad Puppetry, Sound Bath, Printmaking, Chamber Music and Historic Site use representative category emblems, with event-level exclusions in the catalog; these tag choices never automatically propagate to events or places.

## Review and validation

All fourteen scenes were inspected from front, side, rear, top and icon views. The final SVGs were reviewed at **16/24/32/128 px on light and dark backgrounds**, beside accepted custom art and pinned Noto dancer, front-face and profile references. This was a distinct **creator critical pass**, not an independent review. Geometry revisions fixed the oud body/soundboard join, stand support gaps/grounding and contemporary dancer pose. Small details and process-specific distinctions can soften at 16px; per-icon limitations and final source SHA-256 passes are in [the visual review](reviews/tag-gaps-20260910.json).

The fourteen SVGs total **49,216 raw bytes**, ranging from 1,689 to 8,074 bytes. Smooth fitted contours, small-region filtering and palette merging keep the batch compact. Music-stand revisions reduced the chamber icon from 3,329 to 2,681 bytes and the duo from 2,855 to 2,304 bytes while improving support continuity. The refreshed 149-source custom catalog has raw/gzip medians of 1,853/713 bytes and 95th percentiles of 7,614/3,131 bytes; standard Noto remains 4,724/1,943 median and 14,908/5,252 at the 95th percentile. The vibraphone is the batch's raw-size high point because it preserves bars, resonators, frame and pedal. Full measurements: [size comparison](reviews/tag-gaps-20260910-size.json).

Production build and asset validation passed. Five tag-assignment, four catalog and six frontend artwork/chip tests passed. The production chip renderer decoded all 13 assigned custom assets with no failures, browser errors or horizontal overflow at 1280px dark and 390px light; selected/forbidden chips and mounted theme switching were checked. The fourteen-art gallery also decoded successfully. All 41 exported scope-qualified mappings and fourteen final source hashes match. This is a component harness check, not a new full-map or physical-device audit.

## Remaining concepts

Five groups from the original audit remain exploratory: **blues, house, broader genre-specific emblems, cultural community, and ritual**. A blue microphone cannot uniquely identify blues; speakers/pulses duplicate general electronic-music imagery; a universal cultural or ritual emblem risks replacing flags with another misleading generalization. Keep the current reviewed interim artwork while developing context-specific briefs. A separate marionette mechanism is also a future extension of the hand-puppet design.

## Reproduction and release state

- [Scene sources, licenses and structural references](models/tag-gaps-20260910/README.md)
- [Exact before/after tag assignments](20260910-tag-gap-assignments.json)
- Scratch backup: `.scratch/tag-gaps-20260910/assignments-before.json`; source tag evidence: `tag-evidence.json` in the same folder.
- Scratch previews: `new-icons.png`, `review-final/`, `desktop-dark.png`, `mobile-light.png` and `ui-check.json` in that folder.

**Local database, export and build only. Not deployed or committed.** Other sessions' existing-art revisions were preserved and are outside this batch's visual pass.
