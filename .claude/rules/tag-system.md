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

## Two Tag Types

- **Curated tags** (~2,200): in the hierarchy, shown in filter UI, `type = 'tag'`. Always have an emoji.
- **Keywords** (~64,000): search-only, `type = 'keyword'`. No emoji, not in hierarchy.
- Both stored in `tags` table, distinguished by the `type` column.

The invariants `type='tag' ⇒ in hierarchy` and `type='tag' ⇒ has emoji` are intentional. A handful of `type='tag'` tags exist that are intended as future hierarchy roots (e.g. **Hotel** as a venue root) — these have an emoji but no edges yet.

## DAG Structure

Curated tags are organized into a DAG (directed acyclic graph) via the `tag_hierarchy` table. There are 6 independent root families representing orthogonal filtering concerns. Some tags have multiple parents (DAG, not tree). Example: "Live Jazz" is a child of both Jazz and Music.

### Event Types (15 roots)
The "what is the event *about*?" (content/genre) axis. Each root has 2-4 levels of specificity beneath it. Roots, roughly largest-subtree first (exact descendant counts drift constantly — don't treat these as authoritative):
- **Music**, **Community**, **Art**, **Education**, **Wellness**, **Nightlife**, **Theater**, **Film**, **Literature**, **Sports**, **Outdoor**, **Comedy**, **Dance**, **Family**, **Games**

### Format (1 root → 6 categories → 32 types)
The "what is the attendee *doing*?" (structural) axis — mirrors `events.event_type` (see `.claude/rules/database-schema.md` and `pipeline/event_types.py`). One `Format` 🎫 root → six category tags (Performance, Participatory, Browsable, Social, Gathering, **Outings**) → the 32 type leaves (Concert, Workshop, Tour, …). Category tag names match the taxonomy category names exactly, with one unavoidable exception: the `Outing` category would collide with the `Outing` leaf (`tags.name` is UNIQUE), so the category tag is **"Outings"** (plural) while the leaf stays "Outing".

- Membership is driven from `event_type`, not content keywords — `scripts/sync_format_tags.py` rebuilds `event_tags` for the family (run automatically in `/run-pipeline` Step 4). 24 leaves are Format-only and **authoritative** (membership == `event_type` exactly). 8 leaves (**Concert, Sports, Reading, Workshop, Fitness, Volunteer, Party, Festival**) also exist as content-genre nodes with their own subtrees, so they are **multi-parented** (under their genre root AND Format) and their membership is the **union** of content + `event_type` (additive, to keep the genre subtrees' ancestor invariant). `Sports` is the loosest — its content children (Swimming, Esports…) span formats; splitting genre-Sports from format-Sports is a possible future cleanup.
- Search aliases (`tag_aliases`) map natural terms to the leaves (gig→Concert, standup→Comedy Show, gala→Benefit, …).
- **Only the 32 leaf type tags are shown as selectable chips.** The `Format` root + 6 category tags are structural-only (kept for grouping/aggregation, hidden from the chip bar and search). The frontend derives the hidden set as `{'Format'} ∪ childrenOf('Format')` in `DataManager.processTagHierarchy` (`state.structuralFormatTags`), excludes it from `allAvailableTags`, and guards the descendant-dropdown padding in `filterPanelUI._getSortedDescendants`. Event popups already show leaf tags only via the exporter's `display_tags`.

### Venue Types (19 roots, parallel hierarchy)
The "what kind of place is the event at?" axis. These are deliberately separate from event types — a jazz show at a museum is `Jazz` (event) + `Museum` (venue), not nested.

🍺 Bar, 🏢 Community Center, 🎶 Concert Hall, 🏛️ Cultural Center, 🎪 Event Space, 🌿 Garden, 🏛️ Government, 💪 Gym, 🏚️ Historic Site, ⛪ House of Worship, 📚 Library, 🖼️ Museum, 🏢 Office, 🍽️ Restaurant, 🏫 School, 🛍️ Shop, 🎙️ Studio, 🏭 Warehouse, 🧪 Science.

Most venue roots have small subtrees (1–4 children) — venue tags are usually atomic. New venue roots can be added without children if the concept is intended (e.g. **Hotel** 🏨 currently sits as a `type='tag'` root awaiting children).

### Virtual
Delivery method filter. Children: Online, Live Stream, Online Learning, Online Talk, Webinar, Zoom, Virtual Tour, Virtual Yoga.

### Free
Pricing filter. Children: Free Comedy. (Most free-event signal lives in the `Free` keyword/alias layer rather than curated children.)

### Neighborhood (geographic)
Location filter (📍 emoji used uniformly across all descendants — borough, city, neighborhood). Structure: Borough/Region → Neighborhood names.
- **Manhattan**, **Brooklyn**, **Queens**, **Bronx**, **Staten Island**
- **Long Island**, **Westchester**, **Hudson Valley**, **Upstate**, **New Jersey**, **Connecticut**

Geographic tags are also listed in `src/data/tags.json` under `geotags` — the frontend uses this list to hide neighborhood names from event tag displays (popups show event types, not locations).

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
- **Pipeline**: aliases are merged into the rewrite dict during processing, so `process_tags()` handles them transparently
- **Export**: aliases are included in `tag_hierarchy.json` as an `aliases` field on each tag entry
- **Frontend**: aliases are indexed for search — typing "bingo night" surfaces the "Bingo" filter

Examples of alias types:
- Overly specific: "Bingo Night" → Bingo, "DJ Set" → DJ, "Open Mic Night" → Open Mic
- Synonyms: "Live Music" → Music, "RnB" → R&B, "Mahjongg" → Mahjong
- Borough prefixes: "Brooklyn Comedy" → Comedy, "Queens Nightlife" → Nightlife
- Plurals: "Musicals" → Musical, "Paintings" → Painting

Key functions:
- `pipeline/db.py`: `get_tag_aliases(cursor)` — returns `{normalized_alias: canonical_name}` for processing
- `pipeline/db.py`: `get_tag_aliases_for_export(cursor)` — returns `{tag_name: [aliases]}` for export

## How Tags Flow

1. **Pipeline extracts keywords** — AI assigns raw keyword tags to crawled events
2. **`tag_rules` rewrites + `tag_aliases`** — normalizes keywords and maps aliases to canonical tags during processing
3. **`event_tags` stores direct tags** — both curated and keyword types
4. **Backfill propagates ancestors** — `scripts/backfill_category_tags.py` adds all ancestor tags to `event_tags` so an event tagged "Latin Jazz" also gets "Jazz", "Music"
5. **Export** — `pipeline/exporter.py` exports `src/data/tag_hierarchy.json` (with aliases) for the frontend filter panel
6. **Frontend filters** — flat set intersection on `event_tags`, no tree traversal needed

## Key Functions

- `pipeline/db.py`: `build_tag_ancestor_map(cursor)` — BFS transitive closure returning `{tag_id: set(ancestor_ids)}`
- `pipeline/db.py`: `get_tag_hierarchy_for_export(cursor)` — builds the JSON structure for frontend
- `pipeline/db.py`: `get_tag_aliases(cursor)` — alias lookup for processing
- `scripts/populate_tag_hierarchy.py` — manages hierarchy: orphan fixes, intermediate levels, AI classification, geographic hierarchy, emoji assignment, cleanup
- `scripts/backfill_category_tags.py` — propagates ancestor tags to `event_tags`; run after hierarchy changes
- `scripts/export_tag_hierarchy_html.py` — generates `scripts/tag_hierarchy.html` for visual inspection
