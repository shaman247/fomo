---
paths:
  - "pipeline/**"
  - "scripts/populate_tag_hierarchy.py"
  - "scripts/backfill_category_tags.py"
  - "scripts/export_tag_hierarchy_html.py"
  - "scripts/apply_keyword_mappings.py"
  - "src/js/tags/**"
  - "src/data/tag_hierarchy.json"
  - "src/data/tags.json"
---

# Tag System

## Owner scopes (2026-09-09)

`tags.scope` is `event` or `venue`, independent of `type`. Names are unique
**within a scope**; event Ballroom and venue Ballroom have separate IDs. All
name-based queries must include scope. `event_tags` and `event_tag_blocks`
accept event IDs only, `location_tags` accepts venue IDs only. Hierarchy edges
and aliases stay within scope; database triggers enforce these boundaries.

Location topic associations (Jazz, Music, etc.) are venue **keywords**. They are
searchable but excluded from filter membership, counts, and topic inheritance.
Venue-only names stored on events are event keywords. Geographic tags belong
to venues. The frontend export publishes curated event names as `tags`, event
keywords as `keywords`, venue filter keys as `venue:<name>`, and plain location
keywords separately. Display labels omit the namespace. Same-name filters remain
independent in Tags and Venues, including required/excluded states. Legacy
unambiguous venue links redirect to scoped keys; ambiguous names keep the event
meaning. Area URLs keep their plain names.

Migration and backup: `scripts/separate_tag_scopes.py`; detailed record in
[the scope migration note](../../database/migrations/20260909_tag_scopes.md). Consolidation and
icon assignment CLIs accept `--scope event|venue` (default event). Geographic and
venue audits use venue scope; event ingestion, Format sync, keyword repair and
ancestor backfill use event scope. The historical `populate_tag_hierarchy.py`
mixed-scope seed refuses to run on the migrated schema.

## Two Tag Types

- **Curated tags** (~2,200): in the hierarchy, shown in filter UI, `type = 'tag'`. Always have an emoji.
- **Keywords** (~64,000): search-only, `type = 'keyword'`. No emoji, not in hierarchy.
- Both stored in `tags` table, distinguished by the `type` column.

Curated tags must reach an explicitly reviewed root in `frontend.filter_roots`
(or `tag_hierarchy.structural_roots` for Format/Neighborhood). Parentlessness
never grants root status, regardless of frequency or emoji. Hotel is a reviewed
standalone root. Keywords may have inference edges to curated ancestors without
becoming browse nodes; never promote them merely because an edge exists.

**Promotion:** use `scripts/promote_tag.py --scope event|venue --name NAME
--parent PARENT --emoji EMOJI` (repeat `--parent` for a DAG). Default mode validates
and rolls back; `--apply` commits under the shared write lock. Missing parents,
cycles, and orphaned results roll back the entire promotion. Do not use raw
`UPDATE tags SET type='tag'` for ad hoc promotions. Deliberate new roots require
reviewing the city config first. Automated ingestion must continue creating
keywords. Format/geographic maintenance retains its explicitly configured roots.

**Audit/publication:** `scripts/audit_tag_hierarchy.py --output <new-report.json>`
checks stored and Format-stripped graphs. Both event and hierarchy exports refuse
invalid graphs before writing. Frontend selectors use only the explicit roots,
keep unassigned parents in navigation, and never promote disconnected components.
Read the [maintenance runbook](../../pipeline/tag_hierarchy.md).

## DAG Structure

Curated tags are organized into a DAG (directed acyclic graph) via the `tag_hierarchy` table. There are 6 independent root families representing orthogonal filtering concerns. Some tags have multiple parents (DAG, not tree). Example: "Live Jazz" is a child of both Jazz and Music.

### Event Types (15 roots)
The "what is the event *about*?" (content/genre) axis. Each root has 2-4 levels of specificity beneath it. Roots, roughly largest-subtree first (exact descendant counts drift constantly — don't treat these as authoritative):
- **Music**, **Community**, **Art**, **Education**, **Wellness**, **Nightlife**, **Theater**, **Film**, **Literature**, **Sports**, **Outdoor**, **Comedy**, **Dance**, **Family**, **Games**

### Format (1 root → 6 categories → 38 types)
The "what is the attendee *doing*?" (structural) axis — mirrors `events.event_type` (see `.claude/rules/database-schema.md` and `pipeline/event_types.py`). One `Format` 🎫 root → six category tags (Performance, Participatory, Browsable, Social, Gathering, **Outings**) → the 38 type leaves (Concert, Workshop, Tour, …). Category tag names match the taxonomy category names exactly, with one unavoidable exception: the `Outing` category would collide with the `Outing` leaf (`(tags.name, tags.scope)` is UNIQUE), so the category tag is **"Outings"** (plural) while the leaf stays "Outing".

- Membership is driven from `event_type`, not content keywords — `scripts/sync_format_tags.py` rebuilds `event_tags` for the family (run automatically in `/run-pipeline` Step 4). 30 leaves are Format-only and **authoritative** (membership == `event_type` exactly). 8 leaves (**Concert, Sports, Reading, Workshop, Fitness, Volunteer, Party, Festival**) also exist as content-genre nodes with their own subtrees, so they are **multi-parented** (under their genre root AND Format) and their membership is the **union** of content + `event_type` (additive, to keep the genre subtrees' ancestor invariant). `Sports` is the loosest — its content children (Swimming, Esports…) span formats; splitting genre-Sports from format-Sports is a possible future cleanup.
- Search aliases (`tag_aliases`) map natural terms to the leaves (gig→Concert, standup→Comedy Show, gala→Benefit, career fair→Fair, …).
- **Public UI separation (2026-09-08):** the date row has a dedicated FormatSelector, default **All Events**. Its 38 type checkboxes plus Other match exported `event_type` directly, OR within formats and AND with dates/topics. `export_tag_hierarchy` publishes `formats`, `format_only_tags`, and a topic graph with all format-only nodes/parent links removed. The 8 shared topic identities above remain in the topic graph with content parents only (Sports remains a root). `event_types.FORMAT_TOPIC_NAMES` is shared by the exporter and legacy sync; do not infer this set from non-Format parents, because Sports has none. Popups label the format separately. The DB mirror remains for pipeline compatibility; browser filtering no longer relies on that mirror.

### Venue Types (parallel hierarchy)
The "what kind of place is the event at?" axis. These are deliberately separate from event types — a jazz show at a museum is `Jazz` (event) + `Museum` (venue), not nested.

**User ruling (2026-09-09): categories must reflect how people browse.** The user rejected "Beverage Venue" and chose familiar groups: **Food & Drink**, **Arts & Culture**, and **Outdoor**. Reducing root count alone is not a reason to invent a category. Public labels live in `frontend.venue_selector.labels`; the older database names remain stable identifiers only.

Use specific venue identities beneath those browsing groups: Food & Drink → Bar → Cocktail Bar / Dive Bar / Sports Bar; Arts & Culture → Performance Space → Music Venue → Concert Hall / Jazz Club; School → Music School / Art School. Food & Drink also groups Restaurant (including Cafe and Bakery), Brewery, Winery, Distillery, and Lounge. Outdoor groups Park, Garden, Farm, Plaza, Rooftop, and Observation Deck. Arts & Culture also groups Museum, Library, Cultural Center, Historic Site, Arts Venue, and Microcinema. Multi-parenting is appropriate for venue identities such as Community Garden (Garden + Park) and Fitness Studio (Gym + Studio). A venue type must not imply an event topic: Music School does not make every event Music, and Sports Bar does not make every event Sports. Independent roots such as Hotel remain valid when no useful broader category exists. Avoid collecting every venue below the generic Venue tag: that would add a click without improving navigation.

**Other venue policy (user ruling, 2026-09-09):** the former Attraction category
is labeled **Other** (stable key `attraction`). It is a catch-all only for reviewed
rare venue types that fit no existing category. Indoor Skydiving and Skatepark
now belong under Fitness & Recreation.
Prefer a suitable existing parent; rarity alone is not grounds to move an
established category. Use `scripts/promote_tag.py --scope venue --parent attraction`
for reviewed additions. Unreviewed terms stay keywords; never automatically put
all untagged venues into Other. Observation Deck is under Outdoor, and its three
venues must not retain the former Other membership solely from that old parent.

**Fitness & Recreation** groups Gym, Pool / Swimming, Recreation Center, Skatepark, and Indoor Skydiving. Recreation Center also remains under Community Center. Outdoor skatepark locations retain their own Park/Outdoor memberships; Skatepark itself must not imply Outdoor because it includes indoor facilities. Backfill the new parent for every existing descendant location, not just locations in the original venue review.

**Event Hall** is the user's chosen category for dedicated rental venues for receptions, galas, conferences, and private parties, with Ballroom and Convention Center beneath it. Occasional private bookings do not make a gallery, bar, or hotel an Event Hall. Nightclub is an independent root. Venue, Event Space, Warehouse, and Nightlife Venue are search-only keywords; retain their IDs and memberships, but never promote them or blanket-map them to Event Hall. Classify a warehouse by its actual use. Choose a specific venue type for new locations; Other requires individual review.

The public venue selector uses venue-scoped curated identities and the explicit `frontend.filter_roots.venue` allowlist. Do not automatically classify mixed topic/activity subtrees as venues. Reviewed canonicalization and parent corrections live in the city config's `venue_taxonomy` policy. `scripts/audit_venue_taxonomy.py --output <new-report-path>` previews drift; applying requires `--apply --expect-config <reviewed-hash>`, creates a backup, takes the shared write lock, and validates convergence. It remaps synonym references and adds missing ancestors while respecting event tag blocks. Venue membership backfill is location-only; event topics never inherit venue parents. `scripts/audit_venue_memberships.py` separately audits `venue_taxonomy.membership_review`, including generic-only locations needing review and sourced description/name corrections. See [the hierarchy runbook](../../pipeline/tag_hierarchy.md) and [the September 9 audit](../notes/venue-taxonomy-2026-09-09.md).

### Virtual
Delivery method filter. Children: Online, Live Stream, Online Learning, Online Talk, Webinar, Zoom, Virtual Tour, Virtual Yoga.

**Product policy (user ruling, 2026-08-16) — virtual events are mapped, not hidden:**

> "If a virtual event is associated with an organizer with a physical location, it should be mapped to that location. It is common for organizations to do a mix of in-person and virtual events; these should all be listed together, with a 'Virtual' tag on the virtual events for easy filtering if needed."

Consequences:
- A Zoom/online event pinned to its organizer's venue is **correct and intended**, not a geography bug. Do **not** suppress virtual events, and do **not** invent a shared "Virtual" location row — organizations' online and in-person programming belongs on the same pin.
- Every virtual-only event must carry the `Virtual` root (plus the most specific fitting child), because that tag is the *only* thing that lets a user filter them out.
- **`events.location_name` is the ground truth** for delivery method — it is the raw string from the source page. `locations.name` says where the organizer is, not how you attend. Never infer "in person" from a physical `location_id`; see the matching warning in `.claude/commands/audit-event-tags.md`.
- Genuine **hybrid** rows ("Online & In-Person", "Mary Chapel (IN PERSON) / Zoom") happen in person *and* stream — they are not virtual-only and must not be swept up by virtual-only passes.

### Free
Pricing filter. Children: Free Comedy. (Most free-event signal lives in the `Free` keyword/alias layer rather than curated children.)

### Neighborhood (geographic)
Location filter (📍 emoji used uniformly across all descendants — borough, city, neighborhood). Structure: Borough/Region → Neighborhood names.
- **Manhattan**, **Brooklyn**, **Queens**, **Bronx**, **Staten Island**
- **Long Island**, **Westchester**, **Hudson Valley**, **Upstate**, **New Jersey**, **Connecticut**

The geographic place names live in `config/<FOMO_CITY>.yaml` under `geotags` (the single, city-agnostic source of truth, also read by the backend via `city_config.geotags()`). `build.js` writes them into the generated `src/data/tags.json` (gitignored), which the frontend fetches to hide neighborhood names from event tag displays (popups show event types, not locations).

## Tag Disambiguation (homonyms)

Some tag names have genuinely distinct meanings depending on context (e.g. "Pool" = swimming or billiards; "Drama" = stage or film). Rather than forcing one meaning or multi-parenting (which causes filter pollution since events get *all* parent ancestors), these are split into named variants like `Drama / Theater` and `Drama / Film`. The pipeline picks the right variant by inspecting an event's other tags.

- **Storage**: variants are sibling rows in `tags` with names of the form `Foo / Bar`. The frontend strips the ` / Bar` suffix for display via `Utils.getTagDisplayName()` — only the filter tree's parent path conveys which variant a user clicked.
- **Disambiguation rules** live in the `tag_disambiguations` table:
  - `ambiguous_alias` — normalized form of the AI-emitted tag (e.g. `drama`)
  - `context_tag_id` — the rule fires if this tag (or any of its descendants) is among the event's co-tags. NULL means unconditional fallback.
  - `target_tag_id` — which variant to use
  - `priority` — rules are evaluated highest-first; first match wins
- **Pipeline integration**: `process_tags()` in `pipeline/processor.py` defers ambiguous aliases during the main loop and resolves them in a second pass once co-tags are known. Rules are loaded via `db.get_tag_disambiguations()`.
- **Default fallback**: every alias should have one rule with `context_tag_id=NULL` and `priority=0` — this is the variant chosen when no co-tag matches.

Currently split: Avant Garde (Art / Music), Pool (Swimming / Billiards), Open Mic (Music / Comedy / Poetry), Biography (Film / Literature), Musical (Theater / Film), Drama (Theater / Film), Storytelling (Theater / Literature / Community).

## Tag Aliases

The `tag_aliases` table maps variant keyword names to canonical curated tags. Unlike `tag_rules` rewrites (which handle formatting like `18plus` → `18+`), aliases handle semantic equivalence (different names for the same concept).

- **Database**: `tag_aliases(tag_id, alias)` — alias is PK, tag_id FK to `tags.id`
- **Pipeline**: `tag_canonicalization.py` resolves alias chains to their terminal target and rejects cycles or conflicting normalized destinations. `process_tags()` resolves rewrite chains, canonicalizes known spellings after CamelCase/region formatting, and defers context-dependent homonyms. Website default tags use the same resolution.
- **Export**: aliases are included in `tag_hierarchy.json` as an `aliases` field on each tag entry
- **Frontend**: aliases are indexed for search — typing "bingo night" surfaces the "Bingo" filter

**Alias writes**: use `db.upsert_tag_alias(cursor, alias, tag_id)` under the shared
`write_lock`. It validates normalized destinations and cycles before writing while
preserving human-readable alias spelling for phrase search. Do not recreate the
retired `Benefit → Fundraiser` back-edge: `fundraiser → Benefit` is the current
Format alias. Existing curated tag identities remain distinct.

**Historical repairs**: `scripts/reconcile_tag_aliases.py` previews alias flattening
and keyword spelling/alias repairs. Application requires a reviewed config hash,
new backup/output paths, and the write lock. It reconciles active event tags and
all crawl history, honors/copies tag blocks, and verifies convergence before
commit. Curated source tags and contextual homonyms are protected; this is not
a hierarchy or Format migration. Keep old tag rows so existing names/references
are not silently deleted.

**Reviewed curated consolidation**: `scripts/consolidate_tag_aliases.py` accepts an
explicit source→canonical JSON map and requires a preview config hash plus new backup
for `--apply`. Under `write_lock`, it migrates all event memberships (including archived),
venue memberships, crawl/website names, incoming aliases, rewrite destinations,
disambiguation references, and DAG edges. Source IDs remain as keyword rows; blocks
are retained/copied. Format identities and alias chains in the supplied mapping are
rejected. The public export includes `tag_redirects` for retired name compatibility;
Favorites and old tag links migrate to canonical names. See
[the format/alias implementation](../notes/format-selector-2026-09-08.md).

**Search/filter contract** (2026-09-08): event text search includes event tags,
including keywords; aliases match canonical tag suggestions and the chip bar.
Keywords remain excluded from the browsable chip list. Exact event names rank
ahead of incidental text matches. Inclusion/exclusion share the scoped event + venue +
organizer curated tag index; dynamic/viewport counts use the same membership. Preference
ranking's deliberate avoidance of inherited venue audience tags is separate.

Examples of alias types:
- Overly specific: "Bingo Night" → Bingo, "DJ Set" → DJ, "Open Mic Night" → Open Mic
- Synonyms: "Live Music" → Music, "RnB" → R&B, "Mahjongg" → Mahjong
- Borough prefixes: "Brooklyn Comedy" → Comedy, "Queens Nightlife" → Nightlife
- Plurals: "Musicals" → Musical, "Paintings" → Painting

## How Tags Flow

1. **Pipeline extracts keywords** — AI assigns raw keyword tags to crawled events
2. **`tag_rules` rewrites + `tag_aliases`** — normalizes keywords and maps aliases to canonical tags during processing
3. **`event_tags` stores direct tags** — both curated and keyword types
4. **Backfill propagates ancestors** — `scripts/backfill_category_tags.py` adds all ancestor tags to `event_tags` so an event tagged "Latin Jazz" also gets "Jazz", "Music"
5. **Export** — `pipeline/exporter.py` exports `src/data/tag_hierarchy.json` (with aliases) for the frontend filter panel
6. **Frontend filters** — flat set intersection on `event_tags`, no tree traversal needed

## Key Functions

- `scripts/backfill_category_tags.py` — propagates ancestor tags to `event_tags`; run after hierarchy changes
