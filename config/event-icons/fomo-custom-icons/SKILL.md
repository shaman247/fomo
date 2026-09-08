---
name: fomo-custom-icons
description: Audit icon coverage, create Noto-style SVG pictograms, and integrate explicit database-backed icon assignments for Fomo events, tags, and places. Use for Fomo custom-icon batches or maintenance, not general image generation or Unicode normalization alone.
---

# Fomo custom icons

Work in the Fomo repository and follow its AGENTS.md. Resolve this skill's real filesystem path if installed through a symlink. Read the relevant stages of [the versioned workflow](../workflow.md); its neighboring catalog and art are the accepted visual reference. For implemented commands and contracts, read [event icon operations](../../../pipeline/event_icons.md).

Preserve scope: audits produce candidates, prototypes produce reviewed SVGs, and integration requests add authorized catalog/database/export/render changes. Continue within existing authorization; this skill does not authorize deployment or unrelated taxonomy changes.

- Review a reproducible random sample plus separately labeled targeted supplements. `pipeline/event_icon_audit.py` prepares reviews from a saved snapshot; it does not judge fit or mutate the DB.
- Prefer an existing suitable emoji/icon. Rank new art by reach, recognition gap, reuse, and clarity at 16–32 px. Use exact event/tag/place evidence and explicit exclusions.
- During assignment review, also discover future icon opportunities even when the current icon is acceptable. Go beyond broad categories into specific instruments, ensembles, genres/subgenres, dance styles, techniques, equipment, and formats when supported by event context. Save concrete visual concepts and evidence in each decision's `opportunities`; build the aggregated backlog with `event_icon_review.py opportunities`. Keep prospective concepts separate from live assignments and preserve valuable rare ideas.
- Extend the accepted SVG system with simple Noto-style silhouettes, coherent shading, and outlined lettering. For every new/materially changed icon, run [automated critical visual review](../visual-review.md): render, critique, revise, and re-render without relying on user feedback to catch defects. Require a pass for the current source hash before integration. Use an independent reviewer when authorized/available; otherwise record a distinct creator critique without claiming independence.
- Keep semantic IDs stable, source SVGs/catalog authoritative, generated assets hashed, and Unicode fallbacks intact.
- Associations belong offline in the DB. For event assignment, follow [agent review](../../../pipeline/event_icon_review.md): review complete event context against the full catalog, treating heuristic proposals as advisory, and persist final decisions with the validated batch helper. Explicit fallback is a reviewed decision too. Browser code renders saved IDs without inferring meaning from titles, tag names, or ancestors. Tags have a separate offline helper; places require the schema/export/render slice in the workflow before assigning icons.
- Keep place identity independent of hosted events. Preserve manual choices, review/staleness handling, and shared database locks.

Finish with reviewable artifacts, separate event/tag/place impact counts, validation evidence, and clear local/deployed status. Version reusable decisions; keep snapshots, previews, and backups in `.scratch/<task>/`.
