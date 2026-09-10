# Five new event icons — September 9, 2026

Created and applied **five original SVG icons to 10 events** from the latest shortlist. Reviewed a targeted cohort of 12 complete event records: **10 assigned, two exhibition fallbacks, zero deferred**. This is an artwork integration supplement; the sequential backlog checkpoint remains **after 178553**.

| Artwork | Stable semantic ID | Applied events |
|---|---|---:|
| Woodburning | `craft-pyrography` | 1 |
| Linocut printing | `craft-linocut` | 4 |
| Hammond organ | `instrument-hammond-organ` | 1 |
| Cider pressing | `activity-cider-pressing` | 1 |
| Natural dyeing | `craft-natural-dyeing` | 3 |

The catalog now contains **110 custom icons plus 1,710 pinned Noto icons**. Assignments are stored offline in the DB; existing Unicode emoji, tags, event metadata and place identities remain unchanged. No title rules or client inference were added.

## Design and critical review

The [visual review record](20260909-craft-five-visual.json) binds all five passes to the final source SHA-256 hashes. Original 128×128 vector geometry uses accepted soldering, letterpress and pipe-organ SVGs as family references. No third-party SVGs, raster images, logos or runtime fonts were copied into the artwork.

A **creator critical pass**, not an independent or blind recognition study, inspected unlabeled and labeled renders at 128, 32, 24 and 16 CSS pixels on light/dark backgrounds. Native-size panels avoided scaling away the small examples. The first round prompted two revisions: replace a clip-like dyeing skein with a broad folded cloth, and connect the cider basket to a drain tray with its outlet beyond the frame foot. All five final designs were re-rendered and inspected, including ten actual IconManager light/dark variants with decode and cache reuse checks.

Small-size limits are recorded per icon: woodburning and linocut remain process/tool silhouettes while fine tip detail softens; the Hammond organ keeps two distinct manuals but abstracts drawbar/key counts; the cider press retains its apple/frame/basket while screw threads soften; natural dyeing retains cloth entering a colored bath, with a secondary plant cue. No new human anatomy was introduced.

Structural references informed original drawings: [Hammond B-3 documentation](https://www.hammond.de/downloads/br-b3.pdf) for stacked manuals and controls, [Speedball block-printing tools](https://www.speedballart.com/pop-in-brayers/) for the relief-printing process, [Walnut Hollow woodburning examples](https://walnuthollowcrafts.wordpress.com/tag/cvt/) for heated pen and wood, [Pleasant Hill Grain’s press description](https://pleasanthillgrain.com/maximizer-fruit-apple-cider-press) for screw/plate/basket relationships, and [Maiwa’s dye workshop](https://maiwa.teachable.com/p/natural-dye-workshop-se2025) for fabric/yarn in a dye bath. The organ and press are illustrative equipment families, not claims about exact models at the events.

## Event decisions and metadata

- Woodburning: **172101**. **247902** remains an exhibition fallback and has conflicting stored artist names.
- Linocut: **177311, 225575, 233248, 248262**. Each explicitly teaches linocut/stamp carving and printing; the two-color class remains covered by the general process icon.
- Hammond organ: **178271**, the Hammond-focused Organ Monk trio. Jazz and blues repertoire opportunities remain saved separately.
- Cider making: **172315**, a cider-making demonstration/workshop; no claim that the venue uses the exact illustrated press.
- Natural dyeing: **172104, 177223, 232153**. The thread-dyeing session is separate from later embroidery instruction. Randall’s Island’s [official page](https://randallsisland.org/events/natural-dyeing-workshop-3) confirms participants dye textiles. **126259** remains a finished-installation fallback.

Three observations are consolidated in the [metadata investigation register](../../.claude/event-metadata-findings.md): the conflicting pyrography exhibition artist names, Randall’s Island’s source/stored sublocation difference, and a potential artist-talk/exhibition source merge. These were documented separately; no metadata repairs were made. The Randall’s Island source was checked live; the other observations remain unverified.

## Verification and local state

- **48 Python and 19 JavaScript icon tests passed.**
- All **12 decisions** validate against fresh full context, match persisted rows and leave zero pending records in this targeted cohort.
- Generated revision **39b3b5573427**; source-hash validation and generator check passed.
- Local shared-lock export/build verified **31,283 upcoming events** across DB resolution, frontend chunks, built chunks and public NDJSON. No review evidence leaks into frontend data.
- **10 real-site checks passed**: all five icons in search and event details at desktop 1440×1000 and mobile 390×844. All icon images decoded; no page errors, failed icon responses or horizontal overflow. Representative screenshots were visually inspected.
- New sources total **9,148 bytes raw / 3,081 bytes individually gzipped**. The existing startup pack remains 181,963 bytes; these rare icons remain on demand. Five 128×128 RGBA rasters require 320 KiB for one set; cache variants and browser/map overhead are additional. No performance improvement is claimed.
- Event impact: **10 new assignments. Tag edits: 0. Place edits: 0.**
- **Local only: no commit, push, upload or deployment.**

New semantic revision: `e9b5e1e943db5be692eca28de058a4a7e095051af501a6296d4c0cdefe2bd33f`. Catalog expansion reopens earlier semantic reviews: global pending at verification is **31,271**. Resume the sequential review after **178553** with fresh context; targeted records beyond that boundary should be skipped while current. The five remaining latest-shortlist prototypes—seed paper, broom making, cuatro, setar and Double Dutch—remain future work.

Evidence: `.scratch/icon-craft-five-20260909/` contains the 12-record snapshot, explicit packet/decisions, dry run, `icons-before-00.json`, `maintenance-before.json`, `catalog-before.json`, both visual rounds, native panels, actual renderer/gallery checks, byte report, build/export comparisons and real-site screenshots. This report, the final SVGs, catalog and hash-bound visual review are durable source artifacts.
