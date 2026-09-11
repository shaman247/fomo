# Event icon integration

> Rendering update, September 8, 2026: [Unified Noto artwork](icon_artwork.md) supersedes the historical frontend/font-toggle/Unicode-rendering sections below. All entities now export artwork IDs and use one image renderer. The assignment/manual-review/dedupe commands and policies remain in force.

For the repeatable audit → design → event/tag/place integration process, see [Custom icon workflow](../config/event-icons/workflow.md). This page documents implemented operations; place custom-icon support remains a future implementation slice.

**Current assignment workflow:** [Agent event-icon review](event_icon_review.md), run-pipeline Step 5. Heuristics remain advisory suggestions; the running agent has the final call using complete event context and the full custom catalog. Existing rule assignments are retained until reviewed, but the publish tail no longer automatically accepts new heuristic proposals. The historical rule rollout below explains existing data rather than prescribing new assignments.

Custom event pictograms now flow from persistent assignments through the frontend and public JSON exports into popup/list cards and event search results. Venue map markers, location headers, and organizers retain their own emoji. Tags use explicit associations saved in `tags.icon_id`, with their existing emoji preserved. The shared icon catalog remains city-independent; `frontend.event_icons` in the active city config controls rendering (`true` for this NYC build).

## Data and assignment policy

`event_icon_assignments` stores one optional icon choice per event, its origin, rule version, relevant-input hash, review status, reason, and evidence. The fifteen IDs map to versioned SVGs in `config/event-icons/catalog.json`. Unicode `events.emoji` remains untouched and is exported as before.

The rule classifier uses explicit activity names and reviewed name variants in titles. Narrow context rules can also disambiguate a title term: `Go` plus an exact Go/Baduk/Weiqi tag or explicit board-game description supports the Go icon without hardcoding city/club names. Evidence records both the title and its corroborating tag/description. Broad Games/Board Games tags alone are insufficient; tag associations are not automatically inherited by events. Competing games, non-participation topics, and description-only mentions remain review cases with no exported icon. It does not infer meaning in the browser or call a model. Following approval of the initial local review, the September 8–December 7, 2026 population produced 511 rule assignments and 145 review rows from 30,563 events. The other 29,907 events had no assignment row. These were approved rule-based proposals, not 511 individually audited manual decisions or a measured precision guarantee.

The `event-icons-3` follow-up adds corroborated Go title matching and the Dungeons & Drafts title variant. It assigns three previously missed Go events and fourteen Dungeons & Drafts events, bringing the local population to 528 assigned events and 130 review rows. The existing Dungeons and Drafts keyword also uses `tabletop-rpg` through an explicit offline tag edit. Backups and inspected candidate records are under `.scratch/icon-matching-robustness/`. New tests cover unseen club names, recorded context evidence, broad-tag rejection, unrelated uses of Go/drafts, mixed games, and description-only mentions.

The pipeline refreshes review state after merging/classifying sections and before exporting, under its existing publish lock. Changed relevant inputs invalidate saved choices; maintenance and merging do not silently accept heuristic replacements. Agent decisions (`origin='agent'`) include context/catalog hashes and are reused until review is needed. Agent null IDs explicitly record reviewed emoji fallback. Manual decisions survive recrawls and stay protected; changed content marks them for review and temporarily withholds their icon. A manual null ID explicitly locks the event to its Unicode fallback.

Exports independently validate catalog membership, review state, rule version, and the current input hash. Even a standalone export cannot ship a stale assignment. Unknown/new IDs gracefully fall back in older clients. Only `icon_id` is added to event data; review metadata stays in the database. Both frontend chunks and public NDJSON carry this optional field.

Both the pipeline's dedupe path and `scripts/find_duplicate_events.py` preserve decisions before removing/suppressing a duplicate. Manual choices take precedence over agent choices. Conflicting manual choices become a protected fallback requiring review. A transferred manual choice whose input no longer matches also needs review; deduplication does not silently revalidate it. Agent choices survive but return to review after merging. A valid surviving legacy rule choice can remain; merges do not classify anew. Direct ad-hoc deletion still follows the FK's cascade behavior: callers that merge events must use the merge helpers.

## Commands

Dry-run saved-assignment validation (no new classification or writes):

```sh
./venv/bin/python pipeline/event_icon_assignments.py
```

Install the original table on an existing database, validate saved choices, save a before-image, and regenerate local frontend data (use the agent-review helper for new decisions and its agent-origin migration):

```sh
./venv/bin/python pipeline/event_icon_assignments.py --apply --init-schema --backup .scratch/event-icons/assignments-before.json --export-site
```

The migration is also included in `database/schema.sql` for new installs. Existing deployments must run it before using the new pipeline publish tail. `--init-schema` is idempotent but explicit. The command acquires the shared database write lock; no command in this module uploads files. The local migration and initial assignment pass have been applied in this workspace.

Set an editorial choice (replace the example event ID with the reviewed record):

```sh
./venv/bin/python pipeline/event_icon_assignments.py --apply --manual 149056 --icon game-go --reason 'Reviewed as the board game Go'
./venv/bin/python pipeline/event_icon_assignments.py --apply --manual 149056 --icon fallback --reason 'Keep the Unicode fallback'
```

A later explicit manual decision clears review status using the current content hash. Manual edits need a subsequent export to reach the frontend. Use separate backup filenames for separate operations; do not overwrite a rollback snapshot accidentally.

The independent candidate report remains useful when developing rules:

```sh
node config/event-icons/build.cjs
./venv/bin/python pipeline/event_icon_report.py --database --output .scratch/event-icons-integration/current
./venv/bin/python -m http.server 8874 --bind 127.0.0.1 --directory .scratch/event-icons-integration/current
```

Its JSON includes full source records; its browser view compares bounded, truncated card previews. It proposes rules independently of saved manual overrides, and does not save decisions. Serve only the output directory, not the repository root. For effective persisted assignments, use the synchronization dry-run and exported data.

## Frontend, updates and rollback

`IconManager` resolves only known IDs. SVG decode and themed rasters are shared across instances; fixed-size decorative slots fall back to the catalog emoji on failure. Colors use the same pixel analysis as legacy emoji. Mounted icons refresh on theme changes and completed emoji-font loading, with generation checks preventing stale async paints. The list cache includes the assignment and catalog revision. Search projections preserve `icon_id`; location/organizer rendering is unchanged. Tags render their exported database associations through the same manager (see Offline tag associations below).

The build generates hashed SVG assets and a synchronous catalog manifest. Source SVGs stay in `config/event-icons/art/`; current and older generated assets live in `src/images/event-icons/`. Old hashed assets are retained for cached clients. On deployment, upload assets before the referencing bundle, retain prior asset versions, and verify service-worker/HTTP cache behavior. A disabled or old frontend safely ignores exported IDs. To roll back rendering, set `frontend.event_icons: false` and rebuild/deploy; this preserves assignments and Unicode data. The standalone comparison page's explicit true/false override still takes precedence.

This workspace has been built and verified locally, not uploaded. The full site preview is served from a copy containing only built frontend files and public assets (no API source, credentials, or admin tools).

## Verification

```sh
./venv/bin/python -m unittest discover -s pipeline/tests -p 'test_event_icon*.py'
./venv/bin/python -m unittest discover -s pipeline/tests -p test_public_export.py
./venv/bin/python -m unittest discover -s pipeline/tests -p test_export_chunks.py
./venv/bin/python -m unittest discover -s pipeline/tests -p test_merger.py
node --test src/js/tests/iconManager.test.cjs
node config/event-icons/build.cjs --check
npm run build
```

Checks cover all activity families, semantic false positives, manual fallback, stale content/version/ID rejection, conflicting and stale manual merges, the shared lock requirement, client feature toggles, and cache keys. Full-site Chromium verification covered search → popup, venue identity, mounted-icon theme changes, and 390px layout. The earlier card preview also tested every asset and failed-image fallback. The full-site check also exposed an early-search marker-highlight race; feature-state writes now wait for the marker source, with the existing restore path retaining active selection. The repeated early-search check produced no browser errors. Both the frontend and a scratch public NDJSON export contain exactly 511 unique upcoming events with icon IDs; a second database dry run reports all 30,563 records unchanged.

One local Scrabble search reused one SVG request across multiple results and the popup. That demonstrates resource reuse; it is not a mobile/network performance benchmark. Native Safari/iOS checks, field performance measurement, and a broader pinned Noto SVG subset remain future work. No custom event-dependent map-marker policy is needed for the current integration.


## Offline tag associations

The [September 9 hierarchy audit](../config/event-icons/20260909-tag-hierarchy-review.md)
applies explicit custom and approved Noto overrides, including tanpura for Indian
Classical. `tag_icon_assignments.py --scope event|venue --tag NAME --icon ID`
validates either provider against the approved catalog and preserves `tags.emoji`.
Use scoped exact edits, not the initial seed, for ongoing maintenance.

The September 8 follow-up corrected the missing Mixtape Bingo title synonym in rule version `event-icons-2`: 27 active events changed from `bingo` to `music-bingo`. The existing `Mixtape Bingo` keyword row (30018) also received an explicit offline `music-bingo` association, bringing the local tag map to 26 entries. This was an editorial edit, not an expansion or rerun of the initial seed. Backups are under `.scratch/mixtape-bingo/`. Regression cases cover ordinary bingo, unrelated mixtape events, ambiguous mixed activities, and description-only mentions.

`tags.icon_id` is the source of truth for custom tag artwork, alongside the existing `tags.emoji`. The column and 25 editorial associations have been applied locally, covering all fifteen icon designs. Both curated tags and precise keyword tags can have an icon; assigning artwork does not promote a keyword or alter hierarchy/filter semantics. Broad Games, Tabletop, Magic, Sewing, and Glass Art tags retain their existing emoji.

The tag export includes an `icon_ids` map read directly from the database. The browser performs an exact lookup in that exported map, with no name inference, ancestor inheritance, or hardcoded tag-to-icon rules. The offline seed is never consulted by normal export or rendering. Editing/renaming a tag keeps its association on the database row; the next export carries the current name and ID.

```sh
# Read-only comparison against the one-time seed:
./venv/bin/python pipeline/tag_icon_assignments.py
# Initial setup (already applied in this workspace):
./venv/bin/python pipeline/tag_icon_assignments.py --apply --init-schema --export --backup .scratch/tag-icons/tags-before.json
# Explicit offline edits; preserve tags.emoji in both cases:
./venv/bin/python pipeline/tag_icon_assignments.py --apply --tag MTG --icon game-mtg --export
./venv/bin/python pipeline/tag_icon_assignments.py --apply --tag MTG --icon fallback --export
```

The seed preserves existing non-null choices and only fills empty fields; do not schedule it as recurring maintenance, since intentionally cleared fields are empty too. Ordinary pipeline exports never reseed. Manual `--tag` edits can replace or clear a choice. All database writes and local exports take the shared lock. Nothing is uploaded by these commands.

The shared chip renderer covers filter/search chips, popup tag labels, and tag Favorites. Event/place Favorites labels opt out of tag lookup. Selected tag colors use the custom artwork, while forbidden states and palette-driven themes retain their styling. Existing cached exports without `icon_ids` continue to show emoji.

Tag checks: `./venv/bin/python -m unittest discover -s pipeline/tests -p test_tag_icon_assignments.py` and `node --test src/js/tests/iconManager.test.cjs src/js/tests/tagIconColors.test.cjs`. Browser checks verified MTG, Dungeons and Dragons, Bingo, selected chips, popup tags, forbidden styling, and theme refresh. The seed dry run reports zero remaining changes.
