# Indian instrument icon batch — September 9, 2026

Created **five original instrument SVGs**: Indian sitar, tanpura, harmonium, tabla and sarangi. Reviewed **15 current publishable event records** in a targeted supplement and saved **four new assignments, 11 explicit fallbacks, zero deferred**. This is an artwork supplement, not a random sample or sequential backlog batch; resume sequential reviews after **178553**.

| Icon | Scope | New event assignments |
|---|---|---|
| `instrument-sitar` | Acoustic Indian sitar | 246709 — Sitar Concert: Kalyanjit Das |
| `instrument-tanpura` | Acoustic fretless Indian drone lute | None: no current matching program found |
| `instrument-harmonium` | Hand-pumped Indian harmonium | 224677 — SOUK Harmonium TT; 246710 — Kedar Naphade |
| `instrument-tabla` | Featured tabla pair | 246712 — Tabla Solo: Jorge Ramiro |
| `instrument-sarangi` | Short-necked bowed Indian sarangi | None: the only current mention is an opening solo in a bansuri-led mixed bill |

All five are registered and ready for future eligible assignments. Catalog: **120 custom icons plus 1,710 pinned Noto icons**. **Tag edits: 0. Place edits: 0. Metadata repairs: 0.** Existing Unicode fallbacks remain unchanged; no title rules or browser semantic inference were added.

## Artwork and review

[Final visual passes](20260909-indian-five-visual.json) bind each accepted source hash to a **creator critical pass**, not an independent or blind recognition study. Original vector geometry uses the accepted setar, Hammond organ and conga as family references. Inspected unlabeled native-size panels at 128/32/24/16 CSS pixels, light/dark backgrounds, and ten actual IconManager variants. No copied/traced museum photographs, third-party SVGs, raster wrappers, runtime fonts or logos.

- **Sitar:** large rounded gourd body, upper resonator, long curved-fret neck, seven main strings/pegs and a separate sympathetic-peg bank. Revised the initially oversimplified main string/peg layout. [The Met’s instrument record and photograph](https://www.metmuseum.org/art/collection/search/503529) informed construction. Sympathetic peg/fret counts are abstracted; fine wires merge at 16px. Excludes solid-body electric zitar.
- **Tanpura:** four open strings, four tuning pegs, plain unfretted neck and rounded resonator. [National Music Museum](https://emuseum.nmmusd.org/objects/4716/tambura) and [V&A](https://www.vam.ac.uk/content/exhibitions/display-musical-wonders-of-india/tambura/) support the construction. No added frets or upper resonator. At 16px it shares a lute-family silhouette with the sitar/setar; distinctions are clearer at 24/32px.
- **Harmonium:** wooden case, rear folding bellows, keyboard and front stop knobs. Revised the upright-looking first draft by projecting the keys onto a sloping plane continuous with the case. [BINA’s manufacturer manual and instrument photograph](https://www.binaswar.com/manual-instruction/) informed part placement. Keyboard/stop counts are illustrative rather than model-specific.
- **Tabla:** a larger metal bayan with offset black syahi beside a smaller wooden dayan with centered syahi, leather tension straps and tuning blocks. [The Met’s instrument guide](https://www.metmuseum.org/essays/musical-instruments-of-the-indian-subcontinent) supports these distinctions. No drumsticks; heads and bodies remain different at map size.
- **Sarangi:** short broad unfretted neck, three melody strings/main pegs, abbreviated sympathetic-peg bank, pale skin-covered waisted body, bridge and separate bow. [The Met’s sarangi record and photograph](https://www.metmuseum.org/art/collection/search/503204) informed geometry. This is the Indian classical form, not a violin, sarod or Nepalese sarangi variant.

Two rendered rounds are preserved; the initial packet attempt also caught and fixed a duplicate SVG closing tag before visual review. Five sources total **11,875 bytes raw / 4,238 individually gzipped bytes**. The startup pack remains **181,963 bytes**; all five new icons load on demand. Five 128×128 RGBA rasters occupy 320 KiB for one set before variants, copies and browser/map overhead. No performance improvement claimed.

## Assignment boundaries and metadata

- 217412 explicitly features electric zitar, confirmed by [World Music Institute](https://worldmusicinstitute.org/niladri-kumar-at-adler-hall/). 220849 names the same artist’s tribute program but does not establish acoustic instrumentation; related-tour evidence is not proof of its equipment. Both retain broad music fallbacks. Zakir Hussain is the honoree, not a live performer.
- 246706’s title, precise tag and [official artist heading](https://chhandayan.org/calendar/2026/9/20/santoor-concert-vinay-desai) identify santoor; the source itself repeats the erroneous sitar boilerplate. Retained fallback and preserved a santoor opportunity.
- Vocal concerts 231896, 246707 and 246708 retain broad fallbacks; harmonium/tabla are accompaniment. 225471 retains its flute fallback. 246711 features sarod, a different instrument. 247144 is a mixed-instrument jugalbandi, and 247145 is a broad wellness program with a sitar segment.
- For 247146, [the presenter](https://sneharts.com/event/celebrating-pandit-ramesh-misra/) explicitly distinguishes the main bansuri performance from opening sarangi. The new sarangi remains available without replacing the whole concert’s broader identity.

Saved **13 opportunities across 10 concepts**: electric sitar/zitar, musical tribute format, kirtan, bansuri, ghazal, santoor, Hindustani vocal music, sarod, mridangam and jugalbandi. Genre/format motifs remain exploratory; they are not live icon IDs or approved imagery.

Three grouped findings covering eight unique event IDs are consolidated in the [metadata investigation register](../../.claude/event-metadata-findings.md): the santoor/sitar source contradiction, Chhandayan venue-address conflict (confirmed on two pages; five related records need checking), and a Tribute Band tag on a memorial concert. Source URL date fragments alone were not treated as schedule errors. No metadata was repaired during the icon pass.

## Verification and local state

- **44 Python and 19 JavaScript tests passed**, covering event-icon review/assignment, catalog, rendering, caching and packs.
- All five final source hashes match the visual-pass records. Generator revision: **8599b43bb2f6**.
- All **15 decisions** match fresh persisted rows and leave **zero pending records in this targeted cohort**; repeated planned rows are unchanged.
- Shared-lock export/build verified **31,283 upcoming events** against DB resolution, frontend chunks, built chunks and public NDJSON; no review evidence leaks into browser data.
- Semantic catalog revision: `d279715f4b404eb9ccc0c984cfd0be7e3eeb3a6363453badd1286d31b2985514`. Global pending after expansion: **31,268**; this is separate from the completed 15-record supplement. Sequential checkpoint stays **178553**.
- **Eight real-site checks passed:** all four assigned events in search and event details at desktop 1440×1000 and mobile 390×844. Icons decoded without page errors, failed artwork responses or horizontal overflow. Representative screenshots visually inspected. All five registered standalone assets, including unused tanpura and sarangi, match between source and built output.
- Ten actual IconManager variants (five × light/dark) decoded and reused cached results successfully.
- **Local only: no commit, push, upload or deployment.**

Evidence lives in `.scratch/icon-indian-five-20260909/`: full-context snapshot, draft/final art, render packets, native panels, gallery, decisions, dry-run/apply logs, `icons-before-00.json`, `catalog-before.json`, sizes and validation outputs. The SVGs, catalog, this report and hash-bound visual decisions are durable source artifacts.
