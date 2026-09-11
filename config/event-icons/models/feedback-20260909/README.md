# Feedback-driven geometry study — September 9, 2026

This study supplies 34 geometry-based replacements for the custom-icon feedback batch. The remaining 13 edits use direct vector changes or the previously reviewed jazz-trio projection. These are stylized pictograms, not manufacturing models.

## Reproduce

From the repository root, using the existing project venv:

```sh
./venv/bin/python config/event-icons/models/feedback-20260909/fetch_dependencies.py
./venv/bin/python config/event-icons/models/feedback-20260909/render.py
```

The dependency manifest pins Three.js 0.180.0 modules and SHA-256 hashes. The loader and core stay in scratch. The small selected character meshes are retained in `assets/`; no shared Python dependencies are installed. Chromium needs local rendering permission in sandboxed sessions.

The renderer writes five views, a baked scene, projection metadata, and candidate SVGs to `.scratch/icon-corrections-20260909/`. Use `--ids` to select models; `--render-only` and `--fit-only` separate the stages. It does not overwrite accepted art. Final source hashes and feedback resolutions are in `../../reviews/feedback-corrections-20260909.json`.

## Human source and posing

The original tube-and-sphere human drafts were rejected. `people.js` instead imports Quaternius **Universal Base Characters — Standard**, downloaded from the official [pack page](https://quaternius.com/packs/universalbasecharacters.html) / [itch.io distribution](https://quaternius.itch.io/universal-base-characters). The free edition actually contains the male and female superhero bodies; the broader advertised set is not all in this free archive.

The included `assets/License_Standard.txt` grants **CC0 1.0**. `assets/provenance.json` records the archive checksum, retained-file checksums, and modifications. Binary geometry/skin weights are unchanged; the glTF files omit unused texture dependencies. Two of the included hair meshes are retained. No paid models or source `.blend` files are used.

Poses use the imported skeleton and skin weights, with two-bone reach checks and fixed limb lengths. Heads are enlarged 1.45×. Hair and simple face marks attach to the head bone; facial marks are placed on the mesh surface. The body remains skinned through posing, then is baked for the vector projection. Smooth fragment-level clothing boundaries avoid jagged triangle-based color patches. Faces use flat skin paint; trousers use two broad tones. Chair, mat and pole are separate scene geometry. Posed bounds, rather than the glTF rest-pose bounding box, establish mat contact.

Front, side, rear, top and icon views were inspected. The geometry review covers visible joint connections, reach, support and obvious intersections; it is not an exhaustive collision solver or a validated exercise/biomechanics model. Figure drawing flattens a posed rig into a graphite study on paper. The pole icon depicts a grounded supported pose, not an unsupported aerial hold.

## Other geometry and sources

`scene.js` supplies shared primitives, strings and keyboard/machine construction. `objects.js` builds the remaining scenes. Controls and markings lie on their supporting planes. The trombone slide and bell-return bow occupy different planes. The paper icon uses a classic folded boat after the crane study failed silhouette review. Some models deliberately omit hidden markings and internal mechanisms.

Primary structural references consulted:

- [Yamaha trombone structure](https://www.yamaha.com/en/musical_instrument_guide/trombone/mechanism/mechanism002.html)
- [Yamaha classical-guitar dimensions](https://au.yamaha.com/en/musical-instruments/guitars-basses-amps/products/classical-nylon-guitars/cg-cgx/specs.html)
- [Kala soprano ukulele dimensions](https://kalabrand.com/products/uk-monstera)
- [Met sitar](https://www.metmuseum.org/art/collection/search/502149), [sarangi](https://www.metmuseum.org/art/collection/search/503204), and [tabla](https://www.metmuseum.org/art/collection/search/500712)

`glyphs.js` contains outlined Inter SemiBold numeral/letter shapes derived from the repository's Inter font. The SIL Open Font License is retained in `INTER-LICENSE.txt`. The shader/geometry code is local; no raster art is embedded in SVGs.

## Projection, style and review

All objects share an orthographic depth-buffer projection. Color masks are fitted into compact Bézier paths, with small-region filtering and nearby-color merging. Projected eye centers preserve small circular eyes. The pottery silhouette supplies a matching underpaint beneath independently fitted paint regions, preventing transparent seams. Fitting tolerances and stroke widths are explicit in `render.py`.

Style references are pinned Noto yoga, person, walking-woman profile, running-man, guitar and drum SVGs under `../../noto/`, alongside accepted custom artwork. Small-size review covers 16, 24, 32 and 128 px on light/dark backgrounds. The review is a creator critical pass, not an independent or blind review. Narrow instruments and detailed ensembles remain family-level silhouettes at 16 px; the full concept is clearer at 24–32 px.
