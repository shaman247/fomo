# 3D construction and SVG size

Read this when making icons with human figures or non-trivial geometry, or reducing an oversized SVG. The [jazz study](prototypes/jazz-trio-3d/README.md) demonstrates the approach; its camera, layer order, colors, and numerical tolerances are examples to adapt, not defaults for every icon.

## Build geometry before illustration

Create an inspectable 3D scene before drawing figures or complex spatial relationships. Use suitable scene tooling such as Three.js or Blender. Simple flat pictograms can remain direct SVG work. Reuse an existing scene for revisions; color-only edits need not rebuild geometry.

1. Establish plausible dimensions and construction from reliable structural references. Model instruments, furniture, and tools to a common scale. Record approximations; recognition alone does not establish correct construction.
2. Pose articulated figures with fixed limb lengths and explicit hand, foot, seat, and playing-surface contacts. Group each person with the associated equipment for layout transforms. Enlarged cartoon heads are appropriate, but keep neck attachments, joint connections, and working clearances coherent.
3. Inspect front, side, rear, top, and three-quarter views, isolating figures when occlusion hides defects. Check arms against torsos/instruments, legs against furniture, support points, and grips. Use joint overlays or sampled clearance checks when useful; describe their coverage without claiming exhaustive collision detection.
4. Resolve layout in the scene, then choose an orthographic icon camera. Evaluate both world-space arrangement and projected spacing: equal angular positions do not guarantee balanced head gaps in the image. Move or rotate scene groups to address composition feedback, rather than redrawing disconnected limbs in screen coordinates.
5. Preserve the scene, camera, relevant dimensions, and geometry review with the prototype. If later styling changes body volumes or equipment, check the resulting geometry again.

## Translate the projection into Noto-style art

Use the scene for pose, silhouette, perspective, and occlusion. A mechanically shaded 3D render is only an intermediate: simplify it deliberately into broad paint regions and rounded forms.

- Inspect relevant pinned Noto SVGs alongside accepted custom art. For people, include front and side/profile face references. Use simple eyes, brows, noses, and mouths; larger heads can aid expression at icon scale.
- Give performers distinct hair and clothing silhouettes/colors. Keep neighboring clothing, seats, and equipment visually separate. Use continuous sleeves/trousers around the skeleton instead of exposed rod-and-sphere proxy joints.
- Use a few coherent shading planes. For nighttime scenes, broad warm highlights and cool shadows can suggest spotlights; avoid small jaw/cheek shadows that read as facial hair. Flat skin paint is often clearer at this scale.
- Export real SVG paths/shapes in the standard 128-unit viewBox. Projected vector geometry or fitted contours from rendered color masks are both usable. Raster intermediates must not become embedded images in the SVG.
- Preserve depth-buffer occlusion. If exporting whole groups as painter-ordered layers, composite those layers and compare with the complete depth-buffer render before fitting curves. A group order is valid only for the checked scene and camera. Split interleaved objects or retain masks when a simple order fails; recheck after camera/pose changes.

## Reduce SVG size

Measure source bytes and deterministic per-file gzip bytes (`gzip.compress(data, compresslevel=6, mtime=0)`). Compare unique registered sources in the current custom catalog and bundled Noto manifest; report prototypes separately. Separate standard Noto SVGs from unusually detailed waved flags. Compare relevant peers and median/95th-percentile sizes, not just the largest exception. Gzip estimates are not browser rendering costs or measurements of actual HTTP transfer.

The [September 9, 2026 audit](reviews/svg-size-audit-20260909.md) provides a baseline (decimal KB):

| Group | Median raw / gzip | 95th percentile raw / gzip |
| --- | ---: | ---: |
| 110 cataloged custom icons | 1.30 / 0.62 KB | 4.38 / 1.48 KB |
| 1,589 bundled standard Noto icons | 4.72 / 1.94 KB | 14.91 / 5.25 KB |

Aim for the existing custom range: ordinary pictograms typically need only a few KB; a detailed ensemble should aim around 10 KB raw or less and a few KB gzip. About 15 KB raw or 5 KB gzip is a useful review trigger from this snapshot, not a universal limit or permission to inflate simple icons. Refresh comparisons as the catalog changes. Reduce outliers before finalizing; if a remaining size/quality tradeoff cannot be resolved, report it explicitly and retain the prototype rather than silently accepting an oversized asset.

Optimize the dominant cost, preserving a previous revision for comparison:

1. Inspect path/region counts, coordinate precision, and bytes spent on path data. Metadata removal alone will not fix a dense traced mesh.
2. Remove tiny hardware, fragmented highlights, excessive lighting bands, and details that do not support recognition. Merge close colors where separation and expression survive. Keep defining instrument construction, contact geometry, and distinctive outfits.
3. Simplify hidden geometry. Earlier paint may extend beneath later opaque paint instead of tracing every hidden cutout, provided visible edges, holes, transparency, and occlusion remain correct.
4. Fit smooth Bézier contours instead of storing many short segments. Tune small-region thresholds and fitting tolerance to the 128-unit viewBox, inspecting rendered differences. Use short coordinates, shared paint attributes, and compact path commands when they help; do not sacrifice smooth silhouettes for a byte target.
5. Protect semantic details such as eyes and mouths. Use known projected feature positions when restoring tiny features; color or roundness heuristics alone can turn a smile into an eye dot. Check faces at large size as well as 16–32 px.
6. Re-measure raw/gzip bytes and run a fresh [critical visual review](visual-review.md) at 16, 24, 32, and 128 px on light/dark backgrounds, alongside accepted references. Record the final hash, before/after bytes, material simplifications, and any remaining limitations. A smaller file is not sufficient evidence of a successful revision.

The jazz prototype went from 66,458 to 9,329 bytes raw and 19,928 to 4,416 bytes gzip through fewer paint regions, validated group layers, hidden-edge simplification, and fitted curves. Its final raw size fits the custom range; its gzip size is above the custom maximum of 3,664 bytes but below standard Noto's 95th percentile. This is a useful detailed-ensemble reference, not the target size for every icon.

See the jazz [scene](prototypes/jazz-trio-3d/scene.js), [styled renderer](prototypes/jazz-trio-3d/render-icon.js), [export CLI](prototypes/jazz-trio-3d/trace-icon.py), and [contour fitter](prototypes/jazz-trio-3d/fit_contours.py) for a working implementation. The fitter includes jazz-specific layer and projected-eye assumptions; adapt and verify them for other subjects. Keep sufficient source and export parameters to reproduce accepted artwork.

The build currently copies source SVGs without minifying them. Do not silently replace pinned upstream Noto files or checksums to optimize them; authorized derivatives need their own provenance and visual review.
