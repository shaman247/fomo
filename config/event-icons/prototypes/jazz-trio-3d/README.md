# Jazz trio: 3D geometry study

This replaces screen-coordinate guessing with a scene built in metres. It is a
geometry prototype and the source of a first Noto-inspired vector projection.

Open `index.html` in a browser. Drag to orbit, scroll to zoom, choose any of seven
orthographic views, isolate a musician, or enable the translucent joint overlay.
The placement bearings retain 120° intervals. The drummer remains on the 1.55 m
reference circle; the bassist is moved 0.40 m inward to a 1.15 m radius and turned
left 90° with the bass. Both the keyboardist and bassist then turn 20° right.
The keyboardist and keyboard move 0.471278 m inward to a 1.078722 m radius,
equalizing the horizontal head-center gaps in the default drummer-centered view.
Their final yaws are 100° (keyboard), 360° (drums), and 310° (bass).
The default view shows the front of the bass. The optional layout guide shows the reference circle and
spokes ending at the actual musician positions. Heads default to 1.35× scale;
the 1.0–1.6× control raises each head as it grows to preserve the neck attachment.
The page loads pinned Three.js 0.180.0 modules from jsDelivr. No application data,
database access, package installation, or deployment is involved.

## Source and dimensions

- `scene.js` is the authoritative procedural scene, including articulated poses,
  instruments, dimensions, material setup, and camera controls.
- `controls.html` supplies the inspection controls. `index.html` contains the
  standalone assembled preview.
- Keyboard dimensions are 1.298 × 0.364 × 0.141 m, taken from
  [Yamaha's CP88 specifications](https://usa.yamaha.com/products/music_production/stagekeyboards/cp88_73/specs.html).
  The simplified geometry has no Yamaha branding or downloaded product mesh.
- White-key tops are at 0.817 m; the keyboardist's seat top is at 0.50 m. The
  drummer's seat top is at 0.52 m. These are scene setup choices.
- Each arm uses 0.31 m and 0.28 m segments. Seated legs use two 0.43 m segments;
  standing legs use two 0.435 m segments. Elbow and knee positions are solved
  from those lengths and explicit wrist/ankle targets.
- The bass is an original approximate 3/4-size shape, about 1.98 m tall including
  its endpin and scroll. It is a spatial proxy, not a manufacturer replica.
- The drum kit uses a 22-inch kick, 14-inch snare and 10-inch rack tom.

## Geometry review

`geometry-review.json` records source hash, joint positions, limb lengths,
sampled clearances, contact targets, visual findings, and browser checks.
`geometry-checks.js` is the browser-evaluated function used for clearance tests.
The scene exposes `window.__jazz3d` for those inspections.

The initial bass forearm intersection was detected numerically and corrected.
Final sampled minimum clearance is approximately 80 mm for keyboardist legs
against the keyboard case, 18 mm for arms against the case, and 10 mm for the
bassist's right arm against the bass body. These are conservative capsule sample
checks against selected obstacles, not exhaustive collision detection.

The geometry was inspected from front, left, right, rear, above and three-quarter
views, including isolated keyboardist and bassist views. Interaction checks cover
orbiting, zoom, all presets, isolation, joint overlay, and light/dark layouts at
736 and 360 px widths, including the head-size control, layout guide, and adaptive
mobile camera framing. Render packets are in `.scratch/jazz-trio-3d/`.

## Vector projection

`render-icon.js` clones the musician groups and dresses the articulated skeleton
with continuous rounded sleeves and trousers, smooth torsos, rounded shoes, and
original Noto-inspired faces. The illustration uses 1.60× heads with broader
cheeks; the inspection study retains its adjustable 1.35× default. The three
head-center horizontal positions remain symmetric.

The keyboardist wears a charcoal waistcoat, rolled mustard sleeves, plum-purple
trousers, and a curly crop. The drummer has swept brown hair and a coral shirt
with cream collar. The bassist has auburn waves, a teal sleeveless top, dark
trousers, and gold jewelry. Three warm overhead spotlights, cool shadow colors,
and a midnight-blue stage establish the nighttime setting. Light pools are
clipped to the stage surface. Fabrics use broad two-tone shading. Faces, ears,
noses, and necks use a single warm skin color so jaw shadows do not resemble
facial hair; stage lighting remains on hair, clothing, and instruments.

The depth buffer preserves occlusion. Keyboard markings are simplified to two
grouped octaves with reduced black-key relief for the shallow icon camera;
the keyboard footprint and original playing plane stay fixed. A single central
X stand and rounded stool cushion replace mechanical proxy details.
The compact export omits tuning pegs and tiny shirt buttons, consolidates
highlight bands, and strengthens strings so they do not fragment during tracing.
`render-icon.js` returns the complete depth-buffer render plus four transparent
layers: stage, drummer, keyboardist, and bassist. Compositing those layers in
that order was verified pixel-for-pixel against the complete render.

`trace-icon.py` and `fit_contours.py` fit genuine SVG curves to those layers.
Earlier paint can extend beneath later paint, avoiding redundant hidden cutouts.
The fitter merges nearby colors, removes regions below 0.3 square viewBox units,
uses a 0.45-unit curve tolerance, and stores quarter-unit coordinates as integers
under a scale transform. Small eye dots remain round. Colors are specified once
per path and shared by fill and stroke through `currentColor`.

Run `./venv/bin/python config/event-icons/prototypes/jazz-trio-3d/trace-icon.py
.scratch/jazz-trio-3d/icon config/event-icons/prototypes/jazz-trio-projected.svg`
after saving the four `layer-*.png` images returned by `render-icon.js` in that
input directory, together with the returned `projection.json` eye-center metadata.
Output is deterministic for those inputs and parameters.
The SVG is now 9,329 bytes, reduced from 66,458 bytes at the size audit (and
314,791 bytes before the first optimization). No raster is embedded. The result
is `../jazz-trio-projected.svg`, with `../jazz-trio-projected.png` as its preview.
The result is local and outside the live catalog. The small-size review records
the final source hash and remaining detail limits at 16 px.

The camera stays horizontally centered on the drummer. The three head centers
project from world X coordinates approximately −0.867234, 0, and +0.867234 m.
Changing the camera or head scale may change that visual symmetry. Do not
reintroduce independent 2D pose edits; resolve layout feedback in `scene.js`.

The earlier `../jazz-trio-circle.svg` remains a rejected 2D prototype, outside the
live catalog. This study has no event, tag, place, export, or deployment impact.
