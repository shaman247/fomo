# Unified Noto artwork

The frontend renders one kind of icon: a catalog-backed image. The initial approved catalog contains 1,710 Noto entries and the existing 15 custom pictograms. Events, locations, tags and organizers export `icon_id`. Original Unicode emoji remain in the database/public data for provenance and older clients. Existing manual/custom assignments retain precedence and their existing staleness/review rules.

## Catalog and rendering

- `config/event-icons/catalog.json`: existing editorial designs and stable semantic IDs.
- `config/event-icons/noto.json`: approved exact Unicode aliases, source paths, upstream revisions and SHA-256 checksums. Variation selectors are ignored; ZWJ sequences, flags and skin tones are preserved. No title, tag-name or ancestor inference occurs in the renderer.
- `config/event-icons/noto/`: unmodified upstream artwork, pinned to Noto commit `8998f5dd683424a73e2314a8c1f1e359c19e8742`. Waved flag SVGs come from upstream `third_party/region-flags/waved-svg`. The Apache artwork license, attribution and upstream flag provenance accompany the generated assets.
- `node config/event-icons/build.cjs`: validates sources, emits hashed assets and `IconCatalog` in `src/js/core/eventIconCatalog.js`. `--check` verifies generated outputs. Existing hashes are retained for cached clients.

`IconManager` resolves IDs and exact legacy Unicode aliases to the same descriptor, decodes images, applies theme transforms, extracts accent colors, and supplies DOM images and MapLibre pixels. It never draws platform emoji fonts. Unknown values and failed requests use the bundled Noto calendar; an embedded copy covers a missing fallback asset too. There is no font picker, Safari font gate, preview feature switch, or `frontend.event_icons` setting. The historical font file can remain available for older cached clients but is no longer requested by the application.

DOM icon loads are visibility-driven, with at most six simultaneous image requests and bounded decoded/themed caches. Map sprites load only for promoted/hovered markers, cache up to 128 completed sprites, and reject stale async work after theme/style changes. Current markers remain centered event artwork plus primary event labels; additional matching events retain `+N`. Inline UI/title emoji are converted into artwork without modifying source text or editable fields.

The current manifest is about 48 KB gzip. The entire artwork catalog is about 14.6 MB uncompressed on disk; it is **not** precached or eagerly downloaded. These are artifact sizes, not a field-performance benchmark.

## Extraction and review

`pipeline/icon_catalog.py` owns exact resolution and the `icon_review_queue` table. Listing and detail processing flag an unrecognized emoji in the same transaction as the extraction. The locked publish tail also checks tag/place/organizer emoji and reports the pending count. Unknown values do not stop extraction, change its Unicode data, or add artwork automatically.

Queue keys are SHA-256 of normalized UTF-8 sequences, avoiding MariaDB's emoji-equating Unicode collation. Rows retain the original value, first/last seen times, example entity/type/name, observation count, status and review note. The example ID is deliberately not a cascading FK: the evidence survives crawl replacement. Observations count encounters, not distinct events.

The initial historical inventory covered all events (including archived records), crawl events, locations, tags and websites, plus UI fallback artwork. It left 66 unsupported/malformed values affecting 105 historical rows pending review. Detailed snapshots and import reports are in `.scratch/noto-artwork/`.

Install on another database before running the updated processor:

```sh
./venv/bin/python pipeline/icon_catalog.py --init-schema --scan --apply --output .scratch/icon-review/pending.json
```

This command acquires the shared lock. The migration is already applied to this workspace. Read pending findings without writes:

```sh
./venv/bin/python pipeline/icon_catalog.py --output .scratch/icon-review/pending.json
```

Inspect the referenced row and source context. For an existing suitable asset, correct the source emoji using the appropriate entity helper/workflow; do not create a new design simply to accommodate corrupt strings. Dismiss reviewed malformed values with an explanation:

```sh
./venv/bin/python pipeline/icon_catalog.py --dismiss 'VALUE' --note 'Reviewed reason' --apply
```

For legitimate new emoji, save an explicitly reviewed JSON array to a task-specific file and import only those values from a pinned local Noto checkout:

```sh
./venv/bin/python config/event-icons/import_noto.py --upstream PATH_TO_PINNED_NOTO --reviewed .scratch/icon-review/approved.json
node config/event-icons/build.cjs
./venv/bin/python pipeline/icon_catalog.py --scan --apply --output .scratch/icon-review/pending-after.json
```

The importer retains prior approved entries and reports unmatched values. It does not download assets or write the database. `--inventory` is for an explicitly authorized initial historical baseline; do not run it automatically to approve future extractions. The next scan resolves queue entries whose artwork was approved. Dismissed entries retain their status if encountered again. Re-export local event/tag/organizer data under the shared lock after additions or source edits; rebuild before publication. Upload is a separate action.

## Verification

Unit checks cover exact aliases, flags/ZWJ/skin tones, saved assignment precedence, safe unknown IDs, bundled failed-image fallback, shared decoding, hover/filter changes, lazy map loading, stale-theme rejection, and extraction review recording. Existing processor, assignment, public-export and chunk-export checks pass.

The task's local contact sheet is `.scratch/noto-artwork/qa/review.html`: it decodes every catalog asset and shows 56 representative original Noto/custom designs at 16/24/32 px on light/dark backgrounds. Artwork is imported byte-for-byte; no new design or semantic assignment was authored in this change. Visual review checks integration, alignment, legibility and clipping, not a new editorial judgment of all historical associations.

Local verification on 2026-09-08: all 1,725 assets decoded successfully in the in-app browser and native Safari. The full map loaded in both, with centered primary event labels. Desktop event details/list rendering and dark/light theme switching passed without console errors. All 33 frontend tests passed, along with 348 processor tests and the catalog/assignment/export suites. The regenerated public data contained 30,563 distinct events, 4,215 places, 1,965 organizers and 2,731 tag artwork mappings; all referenced catalog IDs were valid, with no unsupported active source emoji. The attempted 390×844 viewport override remained at desktop dimensions, so phone-layout visual verification is still unverified. No deployment was performed.
