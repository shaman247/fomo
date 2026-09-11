# Cycle 004 icon construction

Five original vector designs represent screenwriting, quiet reading, peer support discussions, seed-ball making and worm composting. [scene.py](scene.py) defines the two 3D studies; [project.py](project.py) clips vector mesh faces by relative depth and unites their paint; [flat_art.py](flat_art.py) constructs the three planar diagrams. No external artwork, logos, runtime text or embedded raster images are used.

Regenerate from the repository root with the existing project venv:

```sh
./venv/bin/python config/event-icons/prototypes/autonomous-cycle-004/scene.py
./venv/bin/python config/event-icons/prototypes/autonomous-cycle-004/project.py
./venv/bin/python config/event-icons/prototypes/autonomous-cycle-004/flat_art.py
./venv/bin/python config/event-icons/prototypes/autonomous-cycle-004/views.py
```

Outputs live under `.scratch/icon-cycles-20260909/cycle-004/`. [Geometry review](geometry-review.json) records front, rear, side, top and icon-view inspection. The two earth balls touch a common support plane; visible seed shapes partly enter their surfaces, and the stem joins the larger ball. The worm bin rests on its base, with the joined worm’s underside contacting the bedding. The lid is omitted for this demonstration view. The zero-area line projection case encountered in a side view is explicitly discarded from filled geometry, and the final six views were regenerated and inspected.

The initial earth-ball shading was too angular, so roundness was increased and each ball’s paint simplified. Source size decreased **4,841 / 1,814 → 3,969 / 1,526 raw / gzip-level-6 bytes**. Removing the distracting lid and enlarging the worm reduced that icon **2,991 / 1,110 → 2,529 / 1,012** while improving its main cue. Three separate conversation bubbles replaced a two-person/private-chat composition. [Final visual records](../../20260909-autonomous-cycle-004-visual.json) bind acceptance to each SVG hash and record native 128/32/24/16px review, light/dark backgrounds and ten actual IconManager variants. This is a distinct creator critical pass, not independent recognition testing.

## Structural and semantic evidence

[US EPA’s worm-composting overview](https://www.epa.gov/recycle/composting-home#vermicomposting) establishes a bin, bedding, worms and organic scraps as the essential equipment. The image is an open illustrative demonstration, not a complete construction or care guide; a lid would be used outside the pictured inspection. Vent marks are emblematic rather than an engineered airflow design.

[Snug Harbor’s seed-ball workshop](https://snug-harbor.org/class/compost-seed-ball-workshop/?slot_id=19843) explicitly forms compost seed balls for habitat restoration. Its search-indexed primary listing was readable; a direct fetch failed. The current database’s complete event context was also reviewed. The sprout represents a planting outcome, not pre-germinated supplies or guaranteed growth. The exact clay/compost recipe and seed species are not depicted.

Current full event context explicitly supports screenplay structure/formatting (190837), an independent quiet reading hour (190999/191000), and an eight-week bereavement support discussion (190804). Screenwriting uses a movie-slate stripe, indented script lines and pencil; quiet reading uses an open book and sound-off emblem. This emblem does not impose an accessibility restriction. Three conversation bubbles and a care heart represent a support group without a clinical treatment or outcome claim.

Small details soften at16px: seeds, script indentation, bin vents and the quiet badge are more distinct at24/32px. A general sprouting-soil interpretation remains possible for seed balls. These limitations are retained in the visual record; no measured recognition or performance gain is claimed.
