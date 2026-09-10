# Event and venue tag separation — September 9, 2026

User ruling: events use event tags, locations use venue tags. A shared display
name has independent IDs and hierarchy membership in each scope. A location's
topic (e.g. Jazz) can remain searchable metadata but cannot make its non-Jazz
events match the Jazz filter.

Applied `scripts/separate_tag_scopes.py` under `fomo_write` to local MariaDB.
Backup: `.scratch/tag-scopes/before-separation.json` (tags, location memberships,
DAG, aliases, original table DDL). MariaDB DDL commits implicitly; the script
backs up before DDL, migrates data transactionally and supports resuming.
No IDs or historical event memberships were deleted. The original IDs remain
event-scoped; location memberships point to independent venue rows. Venue-only
original event tags were demoted to keywords. Curated dual meanings are recorded
in city config `tag_scopes.event_parents`; the Ballroom event identity has Dance
as parent, and venue Ballroom has Event Space as parent.

Results: 45,360 location memberships moved; 9,289 became location keywords.
All 57 location Jazz associations are now keywords. Ballroom event ID 574 and
venue ID 80289 are distinct curated tags. Jazz event ID 293 remains curated;
venue ID 80026 is a keyword. No cross-scope event/location/block memberships or
hierarchy edges remain. A direct cross-scope SQL INSERT was rejected with 1644.

Exported 31,270 upcoming events locally. Event and venue `tags` arrays contain
only curated filters. Keywords are separate searchable arrays. Venue browser
keys use `venue:` and render without that prefix. Legacy unambiguous venue
links and favorites redirect; an ambiguous old name retains its event meaning.
Geography uses venue memberships but retains plain area labels and URL values.

Tests cover Jazz include/require/exclude and counts, location keyword search,
duplicate Ballroom identities and menus, scoped aliases/ingestion, geography,
exports and formats. Desktop and 390-pixel mobile venue menus were inspected.
The scoped venue maintenance audit converged with zero pending changes.

Maintenance: always use `scope` in name lookups. `consolidate_tag_aliases.py`
and `tag_icon_assignments.py` accept `--scope`; venue/geographic audits use
venue scope, event keyword repair and format sync use event scope. The old
mixed-owner `populate_tag_hierarchy.py` seed is retired for scoped databases.
The schema migration installs guards for both INSERT and UPDATE of memberships,
aliases and DAG edges, and prevents changing the scope of referenced IDs.
