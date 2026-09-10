# Topic and venue hierarchy maintenance

Only `config/<FOMO_CITY>.yaml` → `frontend.filter_roots.tag` and `.venue`
authorize public roots. Names are unprefixed in config and scoped at export.
`tag_hierarchy.structural_roots` authorizes the separate Format and geographic
families. Root status is a browsing decision, never inferred from counts,
parentlessness, or a cycle. Independent categories such as Hotel remain valid.

New extracted tags remain keywords. Promote an existing keyword with:

```sh
./venv/bin/python scripts/promote_tag.py --scope event --name 'Example' --parent Art --emoji 🎨
# Repeat the reviewed command with --apply to commit. Repeat --parent for multiple parents.
```

The preview executes the promotion under the shared lock, validates the entire
result, and rolls back. Apply commits only after validation. Every requested
parent must already be curated in the same scope. Missing parents, cycles,
disconnected graphs, and missing root config fail closed. New roots require an
explicit config review. Do not promote with ad hoc SQL; the historical mixed-scope
seed script is retired. Keyword-to-parent inference edges do not make a keyword
a browsable filter.

Run the audit after any hierarchy edit and weekly via `.claude/recurring-checks.md`:

```sh
./venv/bin/python scripts/audit_tag_hierarchy.py --output .scratch/tag-orphans/NEW/audit.json
```

Exit 0 is clean; exit 1 reports findings. Unexpected failures must also be handled.
The report checks curated reachability, cycles, explicit roots, invalid scope
edges, and the public projection after Format-only nodes are removed. A tag can
be connected in the stored graph yet become an orphan after that projection.
Do not add a root merely to silence the audit. Prefer a semantically accurate
parent; demote non-filter concepts to keywords, retaining IDs and memberships.

Reviewed repairs live in `tag_hierarchy.parents` (exact parent sets per scope)
and `.demote`. Keep overlapping `venue_taxonomy.parents` and
`tag_scopes.event_parents` policies consistent. Preview first, then apply with
`--apply --expect-config HASH --output <new-path>`. The script checks for drift,
backs up changed tags/edges and added memberships, takes the shared write lock,
and verifies convergence before committing. Ancestor backfill uses the owner's
scope and respects event tag blocks. Existing memberships are retained; a future
repair removing incorrect parents also needs a reviewed membership cleanup.

Ancestor backfill creates its Other fallback as a keyword, never as a curated
root, and now takes the shared write lock. Format, venue, and geographic
maintenance validate the full hierarchy before committing.

Both event and hierarchy exports validate before writing. After a repair,
regenerate event/location data and hierarchy together under the shared lock,
then build and use the normal authorized release process. Selectors independently
use explicit roots and the complete graph, so absent or zero-count parents do
not promote children. Disconnected components never become fallback roots;
active legacy filters still have removal controls.

## September 9, 2026 audit

- Event Gallery Reception → Art (76 active event memberships).
- Event Flea Market → Community; event Indoor Skydiving → Sports (both unused).
- Venue Observation Deck and Indoor Skydiving → existing `attraction` identity,
  publicly labeled **Attraction**. Observation Deck covers SUMMIT, Edge, and
  One World Observatory; the skydiving venue is iFLY Westchester.
- Event Parks and Rec → keyword. Its one active event is a High Line walk.
- Kept reviewed standalone categories, including Hotel and Pool. Warehouse was
  subsequently retired in the venue-use review below.

Applied five edges and one demotion, adding five missing event ancestors and
three venue ancestors. No tag IDs, memberships, or URLs were deleted. Both
browse graphs validated clean. Preview, application report, and rollback data:
`.scratch/tag-orphans/preview-reviewed.json`, `applied.json`,
`applied.backup.json`. No bulk promotion of the 1,615 existing keyword inference
edges: those are intentionally outside the curated browse graph.

### Other and Outdoor venue policy

**Other** is the public label for the existing `attraction` identity, keeping
stable IDs and saved filter links. Use it only for a reviewed rare venue type
that fits no existing category; low frequency alone does not justify moving a
well-defined category into Other. Newly extracted terms remain keywords until
reviewed. For an appropriate new rare venue type, use `scripts/promote_tag.py`
with `--scope venue --parent attraction`; never create a new top-level root as
a fallback, and never classify every untagged location as Other automatically.

Observation Deck belongs under **Outdoor** (`Outdoor Venue`). SUMMIT, Edge,
and One World Observatory inherit Outdoor and no longer carry Other. Indoor
Skydiving subsequently moved to Fitness & Recreation, along with Skatepark. Membership
cleanup must accompany reparenting so former ancestors do not linger in filters.

The Other/Outdoor reparenting backup and verification report are in
`.scratch/tag-orphans/other-outdoor/backup.json` and `applied.json`.

### Venue-use review: Event Hall and specific categories

**Event Hall** means a dedicated rental venue for receptions, galas, conferences,
and private parties. Ballroom and Convention Center belong beneath it. A bar,
gallery, hotel, or performance space does not become an Event Hall merely because
it accepts private bookings. Retain multiple types when distinct uses are real.
**Nightclub** is an independent root, outside the rental-venue hierarchy.

**Venue**, **Event Space**, **Warehouse**, and **Nightlife Venue** are search-only
keywords. Their IDs and memberships survive; do not alias them all to Event Hall
or automatically assign their locations to Other. Warehouse describes a building,
not its present use: review whether it is a music venue, rental hall, office, etc.
New locations need a specific venue type; use Other only after review.

The review covered 949 locations and recorded 367 explicit assignments, adding
652 memberships (including ancestors) and removing three incorrect memberships.
The exact city-specific decisions and sourced content corrections live in
`venue_taxonomy.membership_review` in the city config. Preview recurring drift:

```sh
./venv/bin/python scripts/audit_venue_memberships.py --output .scratch/venue-taxonomy-clarity/NEW/audit.json
```

Exit 0 means the policy is satisfied. Exit 1 means pending changes or locations
with retired generic terms but no curated venue type; review these individually.
An identity or description mismatch requires fresh review, not overwriting newer
content. Apply only a reviewed preview with `--apply --expect-config HASH` and a
new output path. The transaction takes the shared lock, backs up affected data,
checks the full hierarchy, and verifies convergence. It never expands geography
or copies event topics into venue types. Application and rollback data are in
`.scratch/venue-taxonomy-clarity/applied.json` and `applied.backup.json`.

Content corrections made alongside this review:

- Cloud City is an artist-run arts and performance space, not a board-game café
  ([official about page](https://www.cloudcity.nyc/about.html)).
- Peoples’ Voice Cafe was founded in 1979 and moved to Judson in 2021
  ([organization history](https://peoplesvoicecafe.org/2021fall.html)).
- The location named iBoatNYC is now 327 Stagg St: the former name identifies
  the organizer, not the physical venue
  ([organizer’s event listing](https://www.eventbrite.com/e/juany-bravo-afters-brooklyn-nyc-tickets-1991707934046)).

### Follow-up: reviewed Other memberships

The [Other venue review](other_venue_review.md) moved 24 of 44 locations into
existing categories and created a dedicated Hit Me Up location with scoped
source aliases. Remaining Other memberships have explicit reasons in
`venue_taxonomy.membership_review.other_review.retain`. The membership audit
flags new unreviewed Other assignments and Other retained alongside an unrelated
precise venue type. Legitimate children of Other and geography do not trigger
the redundancy check. Revisit retained active locations when better source
information becomes available; do not infer an operating venue from a party
address alone.

### Fitness & Recreation follow-up

The user suggested grouping indoor skating and skydiving with physical activity
venues. The approved **Fitness & Recreation** root now contains Gym, Pool /
Swimming, Recreation Center, Skatepark, and Indoor Skydiving. Gym and Pool /
Swimming are no longer separate roots. Recreation Center keeps its Community
Center parent as well. The three existing Skatepark keyword memberships were
reviewed before promotion: Substance is indoor; Pier 62 and London Planetree
Playground retain their independent Park/Outdoor memberships.

Removed Other from Substance Skatepark and iFLY Westchester, leaving 18 reviewed
Other locations. Added 60 ancestor memberships across the affected subtrees.
The membership audit now supports child promotions and includes every existing
subtree member when backfilling a reviewed parent. Event-topic identities are
unchanged. Backup and reports: `.scratch/fitness-recreation/applied.backup.json`,
`applied.json`, `verified.json`, and `hierarchy-verified.json`.
