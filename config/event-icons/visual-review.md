# Automated critical visual review

Run this agent-driven review for every new or materially revised icon before integration. The coding agent uses rendered-image inspection to critique and revise the artwork without waiting for the user to spot defects. The renderer produces evidence; it does not itself evaluate aesthetics. No background service, model API credential, or recurring job is required.

## Prepare evidence

Use the project venv and existing Playwright/Chromium installation:

```sh
./venv/bin/python config/event-icons/render-review.py --ids game-go --references game-dominoes game-scrabble --output .scratch/icon-review/batch-v1
```

Choose relevant accepted neighbors. Optional `--reference-files PATH ...` adds pinned Noto references or the previous revision for comparison. Use a fresh output directory for each attempt; existing packets are never overwritten. Do not install/modify the shared venv to work around an environment problem. If browser launch is blocked, use an available browser rendering tool or the normal sandbox escalation mechanism. If rendering remains unavailable, mark the visual review blocked, not passed.

The packet includes:

- `blind.png`: candidates numbered without semantic labels, at 128, 32, 24, and 16 CSS px on light/dark backgrounds.
- `labeled.png`: the same sheet with intended concepts revealed.
- `manifest.json`: candidate/reference identity, full source SHA-256, sizes, backgrounds, and device scale.
- `sheet.html`: self-contained review artifact with embedded SVG assets.

Inspect small icons at their actual displayed size, using native-size crops if the viewer scales a tall sheet. Large previews help diagnose geometry; they cannot prove small-size recognition. Include the real site's special-theme/transformed renderings when relevant; this contact sheet covers only normal artwork on two backgrounds. Do not use old screenshots as evidence for a changed SVG.

For figures and complex geometry, include the scene/camera source and multi-view geometry findings from [3D construction](geometry-and-size.md). Inspect the final styled volumes and projected contacts as well as the underlying skeleton. For size reductions, include before/after raw and gzip measurements and compare the optimized rendering with its previous revision; layer-composite checks do not replace reviewing the fitted SVG.

## Critique separately from drawing

Use a separate vision-capable reviewer agent when delegation is authorized and available. Give it the packet and this rubric, not the creator's explanation or expected verdict. Otherwise conduct a distinct critical pass in the working agent and record that it was not independent. This fallback is still automated, but it is not a blind independent evaluation. Avoid claiming blind recognition if the reviewer already knows the design or user feedback.

First inspect the unlabeled image and record what each candidate looks like, confidence, and likely confusions. Then reveal the brief, labeled sheet, and references and assess:

| Dimension | Questions |
| --- | --- |
| Recognition | Is the defining activity/object clear at 24/32 px? At 16 px, does its silhouette remain useful or collapse into another object? |
| Separation | Do letters, scores, stones, pips, outlines, or neighboring objects bleed into one another? Are meaningful gaps visible at normal sizes? |
| Geometry and accuracy | Are faces, intersections, perspective, anatomy, and object construction coherent? Are markings attached to plausible surfaces rather than pasted over the object? |
| Proportions | Are pieces scaled appropriately to boards/grids, handles to tools, and panels to cards? Is the active detail area too small inside the silhouette? |
| Composition | Does the object use its canvas well, with balanced margins, no clipping, and no unnecessary tiny detail? Distinguish intentional breathing room from wasted interior space. |
| Noto consistency | Do visual weight, corner treatment, shading, upper-left lighting, depth, and palette fit the accepted neighbors? Does it feel like the same icon family? |
| Rendering | Are light/dark contrast, transparent edges, highlights, and small-size rasterization clean? Do special-theme variants preserve recognition where used? |
| Size and simplification | Is raw/gzip size in line with comparable custom and standard Noto icons? Did simplification preserve smooth silhouettes, correct occlusion, face features, and defining details? |

Regression examples inform judgment, not hardcoded pixel thresholds for unrelated icons:

- Scrabble: the main letter and small score must remain separate. Do not insist that tiny scores be legible at 16 px if the tile remains clear.
- D20: plausible triangular facets and face-aligned numbers; reject a giant floating “20” that substitutes a label for a recognizable solid.
- Go: stones sit on intersections, with diameter around or below a grid spacing. Reject oversize stones spanning neighboring intersections or an unnecessarily shrunken grid surrounded by a wide board margin.
- MTG: keep enough lower-panel area for the card silhouette to read, without expecting readable rules text.
- Rummikub/glassblowing: check alternate interpretations such as a slot machine or fried egg before polishing details.
- Musical instruments: recognition alone does not establish accurate construction.
  Compare an instrument's silhouette and connected parts with a reliable structural
  reference. For trombone, trace the mouthpiece, two parallel slide tubes and their
  U-bend, bell-section return bow, and flared bell; reject disconnected or trumpet-like
  tubing. For cello/double bass, check smooth, balanced bouts and waist transitions;
  reject exaggerated ripples in the contour or shading even if the instrument is
  recognizable. Record geometry uncertainty explicitly instead of granting a broad
  recognition-based pass.

Use this reviewer prompt, adapted to the batch:

> Critically evaluate these rendered icons using the visual-review rubric. Start with the unlabeled sheet, record likely meanings/confusions, then consult the brief and references. Identify visible defects rather than praising the design. For each issue name the candidate, size/background, location, severity, visual evidence, and a concrete revision. Distinguish observed facts from uncertainty. Do not invent problems to fill a quota or pass an icon merely because the SVG validates. Return pass, revise, or blocked for every candidate. Do not edit files as the reviewer.

## Decide, revise, and re-review

Use per-icon decisions instead of averaging scores:

- **Revise:** any defect materially harming recognition, essential spacing, physical plausibility, proportions, clipping, or consistency. Good color does not compensate for wrong geometry.
- **Pass:** no unresolved material defects at the target sizes. Minor supporting details may soften at 16 px; explain that limitation rather than silently failing or demanding impossible detail.
- **Blocked:** necessary evidence cannot be inspected, the concept cannot be judged reliably, or repeated revisions have not resolved a material defect.

The creator fixes actionable issues, renders a fresh packet, and repeats the critique against the same rubric. Check the whole icon again so one fix does not introduce another issue. Allow up to three revision cycles per batch by default; if a material issue persists, preserve the prototype, report the unresolved issue, and defer that icon while completing acceptable icons. Do not mark it passed just to finish, and do not require routine user approval to make authorized visual fixes. User feedback can override an automated pass and should trigger re-review of the changed art.

Store a compact record for the final reviewed source hash:

```json
{
  "icon_id": "game-go",
  "source_sha256": "<full SHA-256 from manifest>",
  "reviewer_mode": "independent-agent or creator-critical-pass",
  "blind_recognition": "observed result, or not independent / already known",
  "evidence": {"packet": "path", "sizes": [16, 24, 32, 128], "backgrounds": ["light", "dark"]},
  "size_bytes": {"raw": 0, "gzip_level_6": 0},
  "issues": [{"severity": "material or minor", "location": "specific feature", "observation": "visible defect", "revision": "action", "status": "resolved or open"}],
  "decision": "pass or revise or blocked",
  "limitations": []
}
```

Keep large packets in `.scratch/<task>/`; version concise final records under `config/event-icons/reviews/`. A changed source hash invalidates the visual pass and requires fresh rendering/review. Before integration, check each candidate has a pass tied to its current hash. Existing accepted icons are not automatically re-audited unless changed or included in the user's request.

Replace the example byte values with actual measurements. For optimized icons, also record the previous sizes and material simplifications; for 3D-derived icons, link the scene/camera and geometry review evidence.
