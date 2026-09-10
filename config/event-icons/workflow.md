# Custom icon workflow

Current runtime contract: [Unified Noto artwork](../../pipeline/icon_artwork.md). Noto and editorial designs share one image renderer; Unicode is retained as source data. New Noto coverage is reviewed offline through `import_noto.py --reviewed`, never approved automatically during extraction. Existing custom place-assignment requirements below still apply to future editorial overrides; current place IDs are exact artwork mappings of their own saved emoji.

Use this process to audit coverage, design a batch, or integrate approved artwork. Start at the requested stage; a small art correction does not require another population audit. Assign icons offline in the database and preserve existing Unicode emoji as fallback. This process does not authorize deployment or changes outside the requested scope.

The [catalog](catalog.json) and [artwork](art/) are shared across cities. Use the active city configuration and publishable population for each audit. [Integration operations](../../pipeline/event_icons.md) documents the implemented commands, schema, rendering, and rollback behavior.

## 1. Find recognition gaps

Take a read-only snapshot of publishable events over an explicit window, normally the next 90 days. Count unique events, not occurrences. Record city, dates, inclusion criteria, input checksum, sample seed, and code/rule revision. The report uses the exporter's publishability gate. Its proposals cover existing rules only: review unassigned events too when discovering new families.

From the repository root, use a fresh task directory and explicit date/seed:

```sh
node config/event-icons/build.cjs --check
./venv/bin/python pipeline/event_icon_report.py --database --start 2026-09-08 --days 90 --output .scratch/icon-batch-20260908/population
./venv/bin/python pipeline/event_icon_audit.py --input .scratch/icon-batch-20260908/population/report.json --seed 20260908 --sample-size 300 --focus '\b(go|dominoes|scrabble|bingo|canasta)\b' --focus-size 75 --output .scratch/icon-batch-20260908/audit
```

Replace the date and focus for the task. Omit `--focus` for a purely random sample. The report's end date is start + `--days`, inclusive. The sampler accepts `report.json` or a JSON event array, never connects to the DB, and refuses to overwrite an existing review directory. Reuse snapshot and seed to reproduce a sample. Record the git revision and a diff snapshot if matching code has uncommitted changes.

`summary.json` counts exact emoji sequences, event types, and tags across the whole population. `review.json` contains full event context and separate random/targeted cohorts. Human or model review fills the initially empty fields:

The report snapshot contains source emoji and independent rule proposals, not effective persisted icon choices. To audit the currently displayed custom icons as well, join valid saved assignments or current exports by event ID and record the displayed ID separately; do not treat a proposal as the current display.

| Field | Meaning |
| --- | --- |
| `fit` | `strong`, `broad`, `weak`, or `uncertain`: does the current emoji communicate the defining activity? |
| `route` | `keep`, `existing-emoji`, `existing-custom`, `new-custom`, or `review` |
| `best_icon` | Exact Unicode sequence, catalog ID, or proposed visual concept |
| `evidence` | Title/tag/description evidence and why the proposed icon improves recognition |
| `uncertainty` | Competing activities, ambiguous abbreviations, or missing context |

Review context, not just emoji/name pairs. Distinguish an activity from a lecture or screening about it, incidental description mentions, and the venue hosting it. Leave mixed-game events broad unless one activity is clearly primary. Targeted supplements expose rare activities and category blind spots; report their results separately. Overall fit percentages come from the random cohort only. Label additional handpicked examples separately.

Count exact Unicode sequences in Python. The DB's `utf8mb4_unicode_ci` collation can compare distinct emoji as equal; avoid SQL string equality for counting/remapping emoji. Update reviewed records by ID.

For tags, inspect actual rows (including precise keyword tags), emoji, `icon_id`, and event usage. For places, inspect location identity, category/tags, emoji, and hosting patterns. Event frequency is not a count of distinct tags or places, and this event sampler does not audit those populations. Save separate tag/place candidate tables with row IDs and evidence when in scope.

**Output:** reproducible snapshot, reviewed sample, distribution summary, and ranked candidates. Keep raw data/previews under `.scratch/<task>/`; version reusable code and compact decisions rather than full event dumps.

## 2. Prioritize a batch and write briefs

Prefer an existing suitable emoji or custom icon before creating art. Using Unicode through the existing emoji system differs from bundling an exact original Noto SVG; the latter requires an explicit catalog/provider decision. A custom font is not required.

Rank candidates by reach (event count, distinct venues/tags, recurrence), recognition gap, clarity at 16–32 px, and reuse versus drawing cost. Frequency × recognition gap × reuse × small-size clarity is a heuristic, not a measured quality score. A rare distinctive game may beat a common activity already served by a clear emoji. Batches of about five worked well; honor the requested size.

Use the initial run-pipeline agent review as a discovery pass too. Its saved `opportunities` surface specific instruments, ensembles, genres/subgenres, styles, techniques, and formats even when an existing icon is acceptable. Generate the aggregated backlog with `pipeline/event_icon_review.py opportunities --output .scratch/<task>/opportunities` and read [the discovery guidance](../../pipeline/event_icon_review.md#discover-more-specific-icon-opportunities). Assess exact concepts and proposed silhouettes rather than stopping at broad “music,” “dance,” or “craft” categories. Reuse suitable existing Noto/Unicode art; separate novel opportunities from simple emoji reassignment.

Use one brief per candidate:

```text
Concept / stable semantic ID:
Evidence: population count, representative event IDs, matching tag/place IDs
Current emoji and why existing alternatives fall short:
Defining visual cue / composition:
Intended meaning and explicit exclusions:
Unicode fallback:
Event eligibility / ambiguity cases:
Exact tag rows / separately justified place rows:
Reference sources, licenses, and brand-specific scope:
Priority rationale:
```

IDs describe meaning, not a style revision: `game-scrabble` stays stable after an art correction. Several precise tags can share an icon; that does not make every tagged event automatically eligible.

## 3. Draw Noto-style SVGs

Use accepted SVGs in [art/](art/) as the working visual reference. For icons with human figures or non-trivial geometry, create and inspect a 3D scene first, then derive the SVG from its projection. This includes articulated poses, people interacting with instruments/tools, intersecting or occluding objects, and solids whose perspective matters. Follow [3D construction and SVG size](geometry-and-size.md); retain the scene as the source for geometry changes. Simple flat pictograms can use direct SVG editing or code generation, and paint-only revisions can reuse established geometry. Bitmap studies or rendered masks may be intermediates, but the finished SVG must contain vector artwork, not a raster wrapper.

- Use `viewBox="0 0 128 128"`, edge breathing room, simple silhouettes, broad colors, restrained outlines, and upper-left lighting with a few shaded planes.
- Match visual weight and perspective. Reference colors include ivory `#F1EDEC`/`#D8CDC9`, charcoal `#2F2F2F`, and wood `#FFCC80`/`#CE8963`/`#AD7156`; they are not a mandatory palette for every subject.
- Prefer one defining object over many tiny objects. A single Scrabble tile reads better than seven tiles; separate its letter and score. Supporting details may disappear at 16 px if the silhouette still reads.
- Keep physical details coherent. The D20 uses triangular faces and small face-aligned numerals, without a giant overlaid label. The MTG card's frame and enlarged lower panel carry its silhouette.
- Outline essential lettering. Avoid runtime fonts, `<text>`, external resources, embedded images, scripts, and filters. Check gaps and edge clipping.
- Scope brand-specific art to its game: the MTG card is not a generic trading-card pictogram. Record provenance. If copying/adapting upstream Noto, pin a commit/release and preserve applicable SVG license/attribution in versioned files. Do not assume its font license covers its image assets.

Render a contact sheet at 16, 24, 32, and a large inspection size beside accepted custom icons and relevant Noto references. Test light/dark backgrounds and site special themes. Inspect rendered output, not just source. Recognition comes before polish: a Rummikub composition resembling a slot machine or a glass bubble resembling a fried egg needs a different silhouette.

Measure raw and gzip sizes against comparable accepted custom and standard Noto SVGs. Reduce large icons using the [size procedure](geometry-and-size.md#reduce-svg-size), including simpler visible detail and compact fitted curves where appropriate. The build copies source SVG bytes unchanged, so source optimization must happen before final review.

Run the automated critical review below on the final optimized source and iterate within existing authorization. Preserve accepted SVGs, reproducible geometry/export sources, and concise decisions in versioned files; ignored design studies and scratch galleries alone are not durable assets.

**Output:** accepted SVGs, contact sheet, and semantic/design decisions. If only prototyping was requested, stop at that deliverable.

## 4. Automated critical visual review

Follow [the critical review protocol](visual-review.md) for every new or materially revised icon. The agent must inspect rendered images, critique recognition, spacing, accuracy, proportions, composition, Noto consistency, and rendering, then fix material defects and re-render. This is an automated agent step; user feedback is additional evidence rather than the only quality check.

Use `render-review.py` to produce unlabeled/labeled sheets and source hashes. Prefer an independent vision reviewer when authorized and available; otherwise record a separate creator critique honestly. Require a per-icon pass tied to the current source hash before integration. Limit unsuccessful revision loops and defer unresolved icons rather than claiming a pass. See the protocol for the rubric, review prompt, and decision record.

The Go regression illustrates proportional review: enlarge a cramped grid and keep stones around or below one grid spacing, while checking that they still read at 16–32 px. Automated SVG validation alone cannot judge this.

## 5. Register art and associate entities offline

Add approved SVGs to `config/event-icons/art/` and catalog entries with stable ID, label, source, provider, and Unicode fallback. The current build supports custom art; inspect/extend its provider contract before adding a bundled Noto subset. Run `node config/event-icons/build.cjs` to generate hashed assets and frontend catalog. Do not edit generated files as source, rename IDs for cosmetic changes, or delete old hashes needed by cached clients.

| Entity | Current source of truth | Policy |
| --- | --- | --- |
| Events | `event_icon_assignments` | Final agent review of full context/catalog; heuristic suggestions are advisory; manual choices protected |
| Tags | `tags.icon_id` | Explicit associations on existing rows, alongside unchanged emoji |
| Places | Not implemented as of this workflow | Implement a location association and export/render support before assigning custom place icons |

### Events

Follow [agent event-icon review](../../pipeline/event_icon_review.md), also run-pipeline Step 5. Prepare the complete incremental queue, read full event context against every available custom icon, and make the final assign/fallback/defer decision. Heuristics in `pipeline/event_icons.py` prefill suggestions but do not filter the queue or constrain the decision. Do not add a regex for every missed name instead of reviewing its meaning. New IDs and changed `use_for`/`avoid_for` catalog guidance reopen prior agent reviews; art-only changes do not.

Use `pipeline/event_icon_review.py` for packet preparation and validated agent batch application, and `pipeline/event_icon_assignments.py --manual` for explicit editorial overrides. The older synchronization command now only maintains saved choices; it does not accept heuristic proposals. Preserve protected fallback/manual decisions, input-hash invalidation, review state, and merge behavior. Do not inject IDs into generated JSON or replace `events.emoji`. Regenerate relevant frontend/public exports and verify them against valid persisted assignments.

### Tags

Inspect exact existing rows and edit with `pipeline/tag_icon_assignments.py --tag NAME --icon ID` (dry run first; `--apply` writes). Precise synonyms may share an icon. Keep broad tags broad: Machine Sewing supports a machine icon while Sewing also includes hand sewing. Do not create/promote tags merely to accommodate artwork.

Save choices in the DB and export the hierarchy's `icon_ids` map. No frontend tag-name rules, fuzzy matching, or ancestor inheritance. `INITIAL` is a one-time seed, not the ongoing taxonomy or a scheduled synchronizer; future batches use explicit edits. Rerunning the seed could refill an intentionally cleared null association.

### Places: implement before first use

Place icons represent lasting venue identity. A games café may merit its own icon; a library hosting Scrabble should retain library identity. Never choose a place icon from its first/next event or automatically inherit an event/tag icon.

When place integration is requested, implement this slice:

1. Add a nullable catalog-validated association such as `locations.icon_id`, migration, and offline edit helper with dry-run, validation, backup, and shared write lock. Preserve `locations.emoji`. If automatic rules are later needed, add origin/review/staleness handling rather than overwriting editorial choices.
2. Export saved IDs in location data and search projections. Preserve missing/unknown-ID fallback and old-client compatibility. Handle location merges/helper edits without losing choices.
3. Use the shared renderer in location headers, search, and Favorites. Extend MapLibre image registration for explicit location IDs: rasterize SVG to RGBA, cache by revision/theme/size, derive accent from rendered pixels, and restore images after style changes. The existing emoji marker path uses RGBA images; this is not an SDF glyph-range task.
4. Verify clusters/markers, selection rings, hover/selected states, theme/style changes, missing assets, and high-DPI/mobile rendering. Keep venue icons stable when their events change.

These are requirements, not existing commands. Do not report places integrated until implemented and exercised. New locations still use the repository's required creation helper.

All DB writes and shared exports use `dblock.write_lock`; serialize with pipeline publishing. Save unique before-images and reviewable diffs. Honor existing authorization; an audit/design request alone does not authorize additional DB or deployment actions.

## 6. Verify and release the requested scope

Use [existing checks](../../pipeline/event_icons.md#verification), scoped to changed contracts, plus tag tests when affected. Include realistic accepted/rejected cases for new families. A dry run after application should be unchanged; exports should contain known, current IDs consistent with DB review/manual state.

Check real surfaces: event search → popup/list; tag search → selected/forbidden chips → popup tags/Favorites; place/map surfaces when implemented. Exercise 16/24/32 px, light/dark and special themes, narrow mobile viewports, mounted-icon theme changes, cold/cached reload, failed assets, unknown IDs, disabled feature, and old exports. Confirm fixed slots do not shift labels and decorative icons do not duplicate accessible text.

Measure raw/gzip bytes, distinct requests/decodes, cache reuse, and raster memory. A 128×128 RGBA image is 64 KiB; fifteen are about 0.94 MiB for one pixel set, before theme/DPR variants, copies, caches, and atlas overhead. Budget actual working sets, not SVG bytes alone. Compare cold/warm interactions on representative mobile hardware/network before claiming performance improvements. Offline matching adds no browser semantic-inference cost; fetch/decode/raster work still costs time and memory. Do not preload every catalog icon by default.

Serve previews from public-only output directories, never the repository root. Run the normal build for integration changes. Publish only when authorized: upload hashed assets before referencing bundles/data, retain old assets, and verify HTTP/service-worker caches. The city `frontend.event_icons` switch disables rendering without erasing DB choices or Unicode fallbacks.

**Completion record:** accepted IDs/art, matching/exclusion decisions, affected event/tag/place counts separately, review/fallback counts, backup paths, verification/performance evidence, and explicit local-versus-deployed status. Save concise batch decisions beside this workflow when a batch ships. Feed observed misrecognitions and assignment errors into future audits; this process does not create an automatic recurring task.
