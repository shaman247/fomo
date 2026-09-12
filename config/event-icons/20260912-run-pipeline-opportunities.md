# Icon opportunities — /run-pipeline 2026-09-12 (scoped review)

**Coverage:** this is NOT a population-wide audit. The review covered the 594 events created on
2026-09-12 (593 reviewed, 1 deferred: 252984 "T(w)een DLU", no description). The 30,832-event
backlog was deliberately skipped. Raw evidence: `.scratch/run0912/icon-opportunities/opportunities.{json,md}`
and the DB review metadata. 256 raw concept keys; consolidated below.

**Review outcome:** 234 custom icons assigned (108 distinct), 343 reviewed emoji fallbacks, 1 deferral,
~200 heuristic fallbacks overridden on meaning. Top assigned: format-storytime 14, format-book-club 13,
format-author-conversation 10, activity-admissions-counseling 9, activity-benefits-assistance 8.

## Ranked shortlist (recognition gain × breadth × small-size feasibility)

| # | concept | events / venues | visual | why | existing alternative |
|---|---|---|---|---|---|
| 1 | `format-sports-watch-party` | 24 / 3 (one bar's whole NFL+college slate; class is citywide) | wall screen with a ball/score bug, two clinking glasses below | ball emoji says the sport but implies *playing*; TV icon loses the sport | `format-television-watch-party` is scoped to TV programs and its avoid-list points away from sports |
| 2 | `format-history-talk` (merge `format-local-history-talk`) | 13 / 9 | lectern in front of a short timeline bar with ticks | the talk family has art/music/astronomy/math/computing/typography but no general history; libraries run these constantly | `format-art-history-talk` (artworks only); 📚 does not distinguish a lecture from a class |
| 3 | `game-chess` | 5 / 4 | knight silhouette | catalog has Go, canasta, bridge, Rummikub, MTG but no chess; every library/park chess club falls back | ♟️ is a pawn glyph and reads fine — test whether a custom mark adds anything before commissioning |
| 4 | `game-mahjong` | 5 / 5 | one tile face-up with a bamboo/circle motif | same hole as chess; mahjong groups are a dense suburban-library class | 🀄 (red dragon tile) exists in Unicode; evaluate rendering first |
| 5 | `format-street-food-festival` | 11 / 8 | two vendor stalls with striped awnings, head-on | roaming vendor festivals (JAPAN Fes, Smorgasburg-style) rotate between 🍣/🍱/🍙 across one series | `format-food-truck` is vehicle-specific; subsume `format-japanese-cultural-festival` (same 11 events) unless a lantern/noren mark is wanted for that series alone |
| 6 | `format-toddler-playgroup` + `format-story-and-craft` | 6 / 5 and 5 / 5 | (a) two building blocks and a small ball; (b) open book beside a scissors-and-glue pair | `format-storytime` and `format-early-childhood-music` both *avoid* mixed early-learning programs, so these fall through | 🧸 / 🎨 — acceptable, but the avoid rules make this the biggest library-program gap |
| 7 | `format-panel-discussion` | 6 / 6 | three seated silhouettes behind a table with one mic | distinct from a single-speaker talk; broad reuse across cultural orgs | `format-expert-interview` is a two-person format |
| 8 | `format-take-and-make-kit` | 5 / 4 | a flat kit box with a ribbon and a small "to go" arrow | no session happens; these were typed Self-Paced Challenge and share craft emoji with in-room workshops | 🧰; the distinction matters on the map (no time to show up) |
| 9 | `format-day-party` | 6 / 2 | sun over a dance-floor line with raised arms | daytime rooftop parties are a recurring nightlife format | ☀️ + 🎉; low priority until more venues appear |
| 10 | `instrument-piano`, `instrument-trumpet` | 1 / 1 each | grand-piano profile; trumpet bell in profile | genuine catalog holes (cello, tuba, harp, marimba, trombone, French horn exist) — rare here but high value for recitals | 🎹 / 🎺 exist in Unicode and render well; commission only if the custom family needs consistency |
| 11 | `format-documentary-screening`, `format-history-walking-tour`, `ensemble-jazz-combo` | 4 / 4, 4 / 3, 4 / 3 | film reel + "DOC" slate; walking figure + plaque; three small instrument silhouettes | each is a recurring class with only generic art | 🎬 / 🚶 / 🎷 (sax stereotype explicitly discouraged) |

Single-venue series with high counts but low reuse — record, do not prioritize: `format-graduate-info-session`
(9, LIU), `game-poker` (8, FractalU), `activity-buddhist-teaching` (6, one center), `format-demo-night` (5, Fractal).

Rare-but-distinctive, keep on the list: `format-sound-clash`, `genre-drum-and-bass`, `genre-dancehall`,
`genre-soca`, `genre-techno` (all nightlife; recognition of any single genre motif is UNTESTED — every reviewer
flagged this), `format-memory-cafe`, `format-living-history-reenactment`, `craft-papel-picado`, `craft-alebrijes`,
`equipment-immersive-projection-room` (the Igloo history programs — `equipment-vr-headset` explicitly avoids it),
`craft-fuse-beads` (`craft-beading` explicitly avoids it), `activity-group-hike`, `format-cemetery-tour`.

## Consolidations applied here (not in the raw report)
- `format-local-history-talk` → `format-history-talk`.
- `format-association-meeting` → `format-club-meeting` (5+2).
- `format-japanese-cultural-festival` folded under `format-street-food-festival` (identical 11 events).
- `activity-long-distance-hike` / `activity-group-walk` / `activity-group-hike` kept separate (walk ≠ hike).
- Categories: reviewers filed chess/mahjong/manga under `other`; treat as `activity`/`other` per validator.

## Uncertainties
- Genre motifs (techno, D&B, dancehall, soca, R&B, Irish trad, bachata): no reviewer could name a motif with
  confident recognition; needs user testing before any art is commissioned.
- Sports-watch-party count is dominated by one bar (Ainslie Bowery); breadth claim rests on the class being
  common across bar sources, which this scoped review cannot prove.
- The backlog review (30,832 events) will change every count above.
