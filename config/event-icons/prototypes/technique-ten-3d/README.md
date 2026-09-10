# Technique and equipment icon geometry

Original construction sources for the September 9 ten-icon supplement. Seven
subjects use explicit mesh geometry; bassoon, crossword and kumiko are flat
vector illustrations. The accepted art is in `../../art/` and the semantic
boundaries are in `../../catalog.json`.

From the repository root, using the existing project environment:

```sh
./venv/bin/python config/event-icons/prototypes/technique-ten-3d/scene.py
./venv/bin/python config/event-icons/prototypes/technique-ten-3d/project.py
./venv/bin/python config/event-icons/prototypes/technique-ten-3d/flat_art.py
```

These commands regenerate the mesh JSON and draft SVGs in
`.scratch/icon-technique-ten-20260909/art/`. They do not register art or modify
the database. Copying changed drafts into the catalog requires fresh visual
review. NumPy and Shapely are already present in the shared project venv.

Serve this directory with a local HTTP server and open `viewer.html` to select
any of the seven subjects. The viewer displays front, rear, left, right, top and
icon-camera views together. It uses pinned Three.js 0.180.0 from jsDelivr; no
external models or textures. `scene.py` records dimensions, camera vectors,
part connections and explicit support/contact choices in metres. Scale is
illustrative; the geometry is not a manufacturer replica.

`project.py` projects planar faces and clips each face against the parts of
other faces that are actually closer at each screen position. It then unites
visible same-color paint and simplifies contours by 0.16 viewBox units (0.30
for the loom). This avoids the occlusion errors of average-depth painter
ordering. Fret markings and ten steel strings use projected centerlines on the
visible top playing surface. They are decorative detail and become visually
merged at 16px. Final artwork remains paths/shapes, with no raster wrapper.

The [geometry review](geometry-review.json) records contact and support findings
and source hashes. Inspected fixes include the brayer crossbar, removed
unsupported loom peg, steamroller seat/steering support, and separated
papermaking water droplets. The step image is deliberately one cropped trouser
leg and shoe planted on a low platform; it makes no claim about a whole-body
pose or paired-limb anatomy. Tests are visual multi-view and selected contact
checks, not exhaustive collision detection.

The [final visual decisions](../../20260909-technique-ten-visual.json) bind each
accepted SVG hash to a creator critical review at 128, 32, 24 and 16px on light
and dark backgrounds, plus actual IconManager rendering. The reviewer was not
independent and no blind-recognition study is claimed. Three rounds are
preserved in the ignored scratch evidence directory. The [batch report](../../20260909-technique-ten.md)
contains event-assignment boundaries, structural source links and verification.
