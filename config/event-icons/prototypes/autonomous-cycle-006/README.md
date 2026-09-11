# Autonomous cycle 006 artwork — September 10, 2026

Five original SVG pictograms selected from the 100 full-context events 191948–193224. Existing catalog and Unicode choices were considered first; exact assignments remain offline in the database.

| Stable meaning | Evidence | Visual cue and exclusions |
| --- | --- | --- |
| `equipment-cocktail-shaker` | 192169 Botanical Mixology | Closed cobbler shaker beside a cocktail glass: preparation rather than drinking alone. No exact recipe, brand or venue serviceware is promised. |
| `format-poetry-reading` | 192027 David Mills; 192246 curated series | Verse-like short lines and a quotation bubble indicate performed writing. Poetry specificity is supplied by the event; excludes workshops and participatory open mics. |
| `activity-conversation-practice` | 192763, 192804, 192807, 192817, 192972, 192976 | Two matching A speech bubbles indicate a shared target language. Distinct from reciprocal language exchange with different writing systems; ordinary conversation and peer support are excluded. |
| `format-literary-open-mic` | 192235 Most Hated Poets | Open book with connected microphone indicates participatory written-word performance. Excludes singing, comedy-only microphones and curated readings without open participation. |
| `activity-weeding` | 192013 Tunnel Gardens | Uprooted plant specimen with exposed roots beside a hand fork. Represents unwanted-plant removal; excludes planting, transplanting, food harvesting and litter cleanup. |

This is a cohort-based selection, not a population-wide reach ranking. The six conversation groups establish reuse within the reviewed sample. Other designs address narrow gaps supported by specific event context. Unicode fallbacks are retained: cocktail glass, scroll, speaking head, microphone and seedling.

`scene.py` holds three authoritative equipment scenes. `project.py` clips faces by projected depth, unions paint, and simplifies paths at 0.16 viewBox units. `views.py` renders front, rear, left, right, top and icon views. `flat_art.py` supplies two planar emblem designs. Run these with the project venv from the repository root; generated studies go to `.scratch/icon-cycles-20260909/cycle-006/art/`.

The shaker uses three joined parts—cup, fitted strainer shoulder and cap—at illustrative approximately 25 cm height and 10.7 cm width. It and the cocktail glass sit on y=0; glass bowl, stem and base join, with liquid below the rim. Construction was checked against the [Cocktail Kingdom catalog](https://magento.cocktailkingdom.com/media/wysiwyg/CK-Catalog_Version4.pdf). No product drawing, logo or third-party geometry was copied.

The weeding scene is a specimen diagram, not an unsupported figure performing an extraction. Four curved leaves and branching roots connect continuously. Grip, ferrule, shaft, crossbar and four tines connect. The [RHS weeding guidance](https://www.rhs.org.uk/garden-jobs/how-to-weed-a-bed) supports a hand fork and exposed root system as relevant cues; the icon is not a procedural recommendation for every species.

The literary lectern has connected base, pole and tray. The open book is represented by planar page/cover emblems on the tray, with matched page paint and a central gutter. A connected side-mounted gooseneck clears the page and joins its microphone grille. No exact venue lectern is promised. Both A glyphs and quotation marks are outlined paths, with no runtime fonts.

Initial review found a disconnected microphone mount, uneven book shading, diamond-shaped leaves, fine roots and a thermos-like shaker. A final structural check narrowed the initially squat shaker to a plausible width/height ratio. The revised mount begins inside the tray, pages share broad paint, leaves use curved contours, roots are thicker, and a separate cocktail glass disambiguates the shaker. The poetry page's initial speaker-control glyph looked like audio playback; quotation marks replaced it. Unnecessary conversation sparkles were removed.

See `geometry-review.json` and the [hash-bound review](../../reviews/20260909-autonomous-cycle-006.json). This was a distinct creator critical pass, not independent/blind evaluation. Final native 128/32/24/16 px cards were inspected on light/dark beside accepted language-exchange, book-club and litter-cleanup art; ten actual IconManager variants decoded and reused cached results. Fine lines and roots soften at 16 px. The icons are most informative at 24/32 px; exact format remains contextual.

The five assets total 15,530 raw / 5,878 deterministic gzip-level-6 bytes. Recognition revisions added necessary glass/leaf geometry; literary art reduced from 4,885/1,669 to 4,312/1,536 bytes through coherent broad paint. All three projected sources reproduce their registered bytes. File-size comparisons do not establish transfer or runtime improvements.
