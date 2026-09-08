# Event icon catalog

For repeatable discovery, design, review, and database-backed integration, follow the [custom icon workflow](workflow.md). The [Fomo custom-icons skill](fomo-custom-icons/SKILL.md) routes future batches through that process.

Every new or materially changed icon runs through [automated critical visual review](visual-review.md). `render-review.py` produces reproducible browser-rendered evidence; the agent critiques it and revises defects before integration. Final review records live in `reviews/` and refer to exact source hashes.

`catalog.json` defines semantic IDs, accessible labels, Unicode fallbacks, and artwork sources. `art/` contains original custom Noto-style SVGs; these paths were drawn separately and are not official Google or Wizards artwork. Pinned upstream Noto assets live separately in `noto/` and `noto.json`; both providers use the shared renderer. Batch provenance and acceptance records live in `reviews/`.

The palette and shading were guided by Google Noto dice, Mahjong, flower cards, wood, yoga, and cartwheel references. References and their original Apache 2.0 license are preserved in the local design study at `design/event-icons/noto-prototype/reference/`. Upstream: https://github.com/googlefonts/noto-emoji/tree/main/svg. The MTG-inspired card uses a redrawn Planeswalker-inspired emblem and is scoped to Magic: The Gathering; it must not be used as a generic trading-card pictogram. The symbol reference is https://magic.wizards.com/en/news/announcements/venturing-outward-new-magic-logo-2018-03-27.

The second batch and d20 numeral outlines were generated using the existing Inter font in `src/fonts/inter/`; the upstream font project is https://github.com/rsms/inter. The SVGs have no font dependency at runtime. All sources use a 128×128 viewBox, outlined lettering, and no scripts, remote resources, embedded images, or filters.

Run `node config/event-icons/build.cjs` after editing art or metadata. The normal site build also calls this generator. It emits content-hashed SVGs into `src/images/event-icons/` and `src/js/core/eventIconCatalog.js`. These outputs are gitignored; commit the source artwork, catalogs, and licenses under `config/event-icons/` instead. A fresh checkout needs `npm run build` (or the icon generator alone for direct source previews) before serving icons. Run the generator with `--check` after generation to verify outputs are current.

Keep older hashed assets available while cached clients may still reference them. The generator retains existing hashes locally, and the FTP uploader adds or updates files without deleting older remote assets. A fresh checkout regenerates only current hashes, so deployments must preserve existing remote icon files rather than mirror-delete them.

`preview.html` is a template, rendered by `pipeline/event_icon_report.py`; it is not a production page. It uses the actual shared popup/list event card and theme/color code. See `pipeline/event_icons.md` for assignment, export, rollback, report, and test commands. The active city config controls production rendering.
