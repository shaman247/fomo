# Tag-gap icon scenes

Fourteen original icon compositions derived from inspectable Three.js scenes. `objects.js` is authoritative for object geometry; `people.js` poses the existing CC0 rigged characters. `primitives.js`, `glyphs.js` and `fit_contours.py` are local snapshots of the September 9 scene/export helpers, isolated from concurrent revisions. No raster data is embedded in the accepted SVGs.

Reproduce from the repository root with the existing project venv:

```sh
./venv/bin/python config/event-icons/models/feedback-20260909/fetch_dependencies.py
./venv/bin/python config/event-icons/models/tag-gaps-20260910/render.py
```

The renderer uses the pinned Three.js 0.180.0 modules cached in `.scratch/jazz-trio-3d/` and `.scratch/icon-corrections-20260909/assets/three/`. Shared character assets remain under `../feedback-20260909/assets/`; their CC0 license and provenance travel with that folder. `dependencies.json` records the exact runtime and asset hashes used. The glyph outlines derive from Inter, with its OFL text retained here; this batch uses musical note shapes rather than text labels.

Output goes to `.scratch/tag-gaps-20260910/`: five 1024px views, serialized scene and camera metadata for each model, then fitted SVG candidates. `--render-only`, `--fit-only`, and `--ids ID ...` support targeted revisions. `geometry-review.json` preserves the final cameras and construction checks. The full serialized scenes and screenshots stay in scratch because the JavaScript is authoritative.

## Construction references and limits

- [The Met: Egyptian oud](https://www.metmuseum.org/art/collection/search/503203): pear-shaped soundboard, vaulted back, short unfretted neck, three roses and bent pegbox. The icon uses a bowl whose rings share the soundboard perimeter. Strings, peg count and rosette lattices are abbreviated; it is not a replica of this instrument.
- [Yamaha: anatomy of a vibraphone](https://hub.yamaha.com/drums/percussion/anatomy-of-a-vibraphone/): metal tone bars, resonator tubes of differing lengths and damper pedal. The model abbreviates the pitch range/bar count and hides the internal fan/motor mechanism. Mallets are arranged above the instrument as display objects.
- [Bloch: tap plates](https://us.blochworld.com/collections/taps): separate toe and heel taps. The icon uses a low heel with metal plates on both sole contact areas; tiny fasteners are supporting detail.
- [RISO: duplicator comparison](https://www.riso.co.uk/compare-duplicators/): generic duplicator identity. The offset two-color impression is the process cue; this simplified casing does not claim a particular model or internal configuration.
- [Quaternius Universal Base Characters](https://quaternius.com/packs/universalbasecharacters.html): CC0 anatomy/skin weights and hair meshes; local fixed-length inverse kinematics, facial details, colors and poses. Partner palms meet at a two-hand open hold. Reach checks cover articulated chains; visual review covers projected contact and clothing volumes, not exhaustive collision detection.

Front, side, rear, top and icon views were inspected. Revisions closed the oud body/soundboard gap, grounded all chamber stands, connected/thickened stand supports, and changed the contemporary dancer from a squat to an asymmetric lifted-leg pose. A hand-puppet glove, open singing-bowl interior, brayer/yoke, duplicator tray, metal bar/resonator array, and stage opening retain plausible component placement. Paired film frames and music stands are intentionally symbolic compositions.

Final SVG fitting: 0.28-unit curve tolerance, 0.12 square-unit minimum region, RGB palette distance 14, quarter-unit coordinate storage, projected eye preservation, and a 0.05-unit final outline. Sizes and source-hash-specific creator critiques are in `../../reviews/tag-gaps-20260910*.json`. This was a distinct creator critical pass, not an independent review.
