# Instrument artwork corrections — September 8, 2026

User feedback overrode the original automated pass for trombone, cello and double
bass. The three corrected assets now replace those originals locally; semantic IDs
and database associations are unchanged. The other 22 custom assets are byte-for-byte
unchanged. No deployment or commit was performed.

The trombone was rebuilt using the main air path shown in the
[Yamaha structure guide](https://www.yamaha.com/en/musical_instrument_guide/trombone/mechanism/):
mouthpiece, two close parallel slide tubes and their long U-return, rear tuning bow,
then the flared bell. The source diagram's optional F-attachment circuit is omitted
for this straight-tenor depiction. The creator and independent critic both inspected
the supplied structural reference and the rendered draft.

Cello and bass now have controlled, symmetric bouts and simpler highlights instead
of exaggerated waves. The first correction pass failed independent review because
f-hole curls touched the rim at the waist. The final pass narrows the instruments
12% (including the necks), moves and narrows the f-holes inward, and preserves a
visible strip of wood around them. Bow/hand separation remains clear.

One intermediate packet accidentally referenced old production art after a shared
scratch catalog was overwritten. Both coordinator and critic detected the hash and
visual mismatch; that packet was rejected as evidence, not accepted as a new draft.
The final packet verifies scratch source paths and exact hashes before integration.

The [final independent decisions](20260908-instrument-corrections-visual.json) cover
16/24/32/128 px light/dark renders and visual inspection of all nine theme variants.
Subjects were already known, so this review makes no blind-recognition claim.
All three pass, with the usual 16 px limitations for fine strings, braces, mouthpiece,
and cello/bass subtype discrimination. Production-renderer checks prepared all 27
icon/theme combinations without errors, with nonempty rasters and cache reuse.

Catalog generation, production build and generated-output check pass with revision
`e1113f71625c`. Exact accepted SVG bytes are present in both source and built assets.
Old asset hashes remain available for previously cached clients, as designed.
No database/export semantic changes or new matching heuristics were required.

The review rubric now explicitly requires instrument geometry checks rather than
accepting recognizable but physically incorrect silhouettes. Original acceptance
records are marked superseded for these three hashes; their historical batch report
does not establish approval for the old artwork after the user's correction.

Local evidence is under `.scratch/icon-corrections-20260908/`: `before/`,
`corrections-v3/`, `corrections-v3-critique.md`, `trombone-provenance.md`,
`trombone-v1/structural-comparison.png`, `gallery/icons.png`, `gallery/themes.png`,
`gallery/render-verification.json`, and `integration.json`.
