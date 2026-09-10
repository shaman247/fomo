# Five new event icons — VR, seed paper, wind turbine, setar and Double Dutch

Created five original SVGs and applied them to **12 events**. A targeted full-context review of **27 current publishable event records** produced **15 custom choices (12 new, three retained), 12 explicit fallbacks, zero deferred**. This is a targeted artwork supplement, not a random sample or another sequential 100-event batch. The sequential backlog checkpoint remains **after 178553**.

| Artwork / stable ID | New assignments |
|---|---|
| Virtual reality headset — `equipment-vr-headset` | 163551, 226803, 228581, 228665, 231459, 240104, 244618 |
| Seed paper making — `craft-seed-paper` | 172094 |
| Wind turbine — `equipment-wind-turbine` | 176654 |
| Persian setar — `instrument-setar` | 246741 |
| Double Dutch — `sport-double-dutch` | 174824, 232808 |

The catalog contains **115 custom icons and 1,710 pinned Noto icons**. Event emoji are unchanged. **Tag edits: zero. Place edits: zero. Metadata repairs: zero.** No new title-matching rules or frontend semantic inference.

## Design and critical review

[Final visual passes](20260909-discovery-five-visual.json) bind each source SHA-256 to a creator critical pass. This was an automated creator critique, **not an independent reviewer or blind user-recognition study**. Rendered all candidates beside accepted ukulele, Pilates and natural-dyeing art at 128, 32, 24 and 16 CSS pixels on light/dark backgrounds; inspected native-size panels and actual IconManager variants.

- VR: opaque broad visor, padded housing, overhead strap and two tracking cameras. Brand-neutral equipment; no specific model is promised.
- Seed paper: deckled sheet with embedded seeds and a sprout. Replaced warm cream/brown paper with neutral ivory/gray to reduce the initial flatbread-like appearance. The sprout symbolizes plantability, not a promise of already-sprouted workshop material.
- Turbine: three blades around a hub, continuous tapered tower and base. Strengthened blade contrast after the first render. Represents wind-energy equipment without implying a full-scale turbine is built at the workshop.
- Setar: small pear-shaped soundbox, long slender neck, four strings/pegs, bridge and soundboard perforations. Connected string runs above the nut during critique. [Center for World Music’s instrument educator](https://centerforworldmusic.org/2015/06/world-music-instruments-the-setar/) and [Smithsonian’s setar description](https://asia-archive.si.edu/podcast/persian-classical-music-bahman-panahi-tar-and-setar-ali-mojallal-tombak/) informed construction; fret counts are abstracted for small-size illustration.
- Double Dutch: replaced the first hoop-like lone-jumper composition with two turners holding both ropes and a central jumper. Checked equal limb lengths, arms thinner than legs, short neck, consistent skin tone, coherent lighting, connected grips and space below the airborne jumper. Two colored rope paths distinguish the activity; exact grip detail softens at 16px. [National Double Dutch League](https://nationaldoubledutchleague.com/) describes the two-rope technique.

All art is original vector geometry; no copied SVGs, traced reference photographs, raster wrappers, logos or runtime fonts. Three rendered rounds are preserved. Five final sources total **8,295 raw bytes / 3,437 individually gzipped bytes**. Startup pack remains **181,963 bytes**; the new rare icons load on demand. Five 128×128 RGBA rasters use 320 KiB for one set before variants, copies and browser/map overhead. No performance improvement is claimed.

## Assignment boundaries and discoveries

- VR headsets apply to the seven explicit immersive/headset experiences above. [Prado’s host](https://powerhousearts.org/prado) confirms wearable headsets. [MoMI](https://movingimage.org/event/sense-of-nowhere/) and [the artist](https://www.hsinhsuanyeh.com/vr-son) corroborate the interactive hand-tracking VR work.
- White Plains Igloo animal-search games remain fallbacks: stored descriptions specify projected walls. For 243951, a [related official series occurrence](https://calendar.whiteplainslibrary.org/event/15773752) explicitly says the room operates without headsets; the exact current occurrence did not load. Do not infer headset use from the word VR or the existing goggles emoji.
- 82723 retains `format-improv-comedy`: “VR” is part of the event name. 221802 and 244006 retain `format-storytime`: turbine/VR topics do not change the read-aloud format.
- 177217 retains its microphone fallback. The saved Mohsen Namjoo listing describes him as a setar virtuoso but does not establish this concert’s instrumentation; its source URL returned 404 during review. New art instead applies to 246741, whose program explicitly features Nima Janmohammadi on setar with Pejman Hadadi on percussion.
- Mixed arcade socials, broad makerspace access, the mixed African Film Festival family day, and mixed animation screenings retain fallbacks. 245550 teaches 3D modeling, with VR and printing as downstream uses.

Saved **eight opportunities across six concepts**: immersive projection rooms (three events), Persian fusion, tombak, daf, Persian classical music, and the existing 3D-modeling opportunity. Genre imagery remains exploratory and must not overpromise program instrumentation. Removed now-covered proposed concepts from the new reviews; incidental mentions do not become assignments.

Six grouped observations covering 12 event IDs are consolidated in the [metadata investigation register](../../.claude/event-metadata-findings.md): truncated snippets, Igloo equipment/sublocations, artist spelling, Prado sublocation, ANNY identity/virtual-location questions, and the unavailable Namjoo source. The ANNY bowling-emoji issue links back to its existing register entry. No unrelated metadata repair was performed.

## Validation and local state

- **44 Python and 19 JavaScript tests passed** across event-icon review/assignment, catalog, renderer and pack behavior.
- All **27 decisions** validate against fresh complete context, match persisted assignments, and leave **zero pending records in this targeted cohort**. Repeated planned rows are unchanged.
- Generator/source-hash check passed; artwork revision **b7c38e9b43e4**.
- Shared-lock local export/build verified **31,283 upcoming events** against DB resolution, frontend chunks, built chunks and public NDJSON. No review evidence leaks into frontend data.
- **10 real-site checks passed:** five icons in search and event details at desktop 1440×1000 and mobile 390×844. Every icon decoded; no page errors, failed icon responses or horizontal overflow. Representative desktop/mobile screenshots were inspected.
- Ten actual IconManager variants (five icons × light/dark) decoded and reused the cache successfully.
- Semantic catalog revision: `e0622d6a8834c6353d35573557c0dc8be5f69a22b7d3810003d4484d402391be`. Global pending review count after catalog expansion: **31,256** (10,453 changed-catalog, 2,200 changed/deferred, 18,465 unreviewed, 138 legacy). This is global review work, separate from the completed 27-record supplement.
- **Local only: no commit, push, upload or deployment.**

Evidence directory: `.scratch/icon-discovery-five-20260909/`. It contains the current full-context snapshot, explicit packet and decisions, dry-run/apply logs, `icons-before-00.json`, `maintenance-before.json`, `catalog-before.json`, three artwork rounds, source-hash manifests, native panels, actual renderer results, byte report, and build/export verification. Final SVGs, catalog, this report and visual decisions are durable source artifacts.
