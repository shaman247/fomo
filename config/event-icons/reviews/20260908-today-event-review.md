# Today’s event-icon review — September 8, 2026

Reviewed **all 2,627 publishable event records listed for September 8**, including ongoing spans, against all 15 custom icons and the existing Noto alternatives. Three agents read 900, 877, and 850 records in 53 bounded packets. The coordinating review checked proposed changes, music examples, semantic duplicates, and evidence limitations. This is complete coverage of the database’s today scope, not an independent verification that every listed occurrence is accurate.

## Saved results

| Result | Records |
| --- | ---: |
| Custom icon | 118 |
| Existing emoji/Noto fallback, explicitly reviewed | 2,509 |
| Deferred | 0 |
| Pending on a fresh second pass | 0 |
| Display changes | 12 |
| Events with future-icon suggestions | 299 |
| Suggestions, before grouping by concept | 319 |
| Distinct concepts after editorial consolidation | 188 |

All 2,627 decisions, reasons, evidence, context hashes, and opportunity lists are persisted in `event_icon_assignments` with agent provenance. No protected manual choices were present in this scope. Twelve decisions differ from the heuristic icon choice: eleven add a custom icon and one changes ordinary bingo to music bingo. The other 106 previously displayed custom choices were confirmed. Existing Unicode emoji were retained. Tag assignments changed: **0**. Place assignments changed: **0**. New artwork: **0**.

| Custom ID | Records |
| --- | ---: |
| trivia | 67 |
| tabletop-rpg | 12 |
| chair-yoga | 7 |
| music-bingo | 6 |
| machine-sewing | 6 |
| 3d-printing | 4 |
| bingo | 3 |
| pole-dance | 3 |
| game-go | 2 |
| game-mtg | 2 |
| game-backgammon | 2 |
| game-scrabble | 2 |
| game-dominoes | 1 |
| game-rummikub | 1 |
| glassblowing | 0 |

## Corrections that required context

| Event IDs | Final icon | Supporting context |
| --- | --- | --- |
| 102566, 116153 | trivia | “JBL Tuesdays” descriptions identify Jeopardy! Bar League. |
| 158551 | music-bingo | Yo! MTV Bingo explicitly says music bingo. |
| 225846 | 3d-printing | Tinkercad class explicitly prints the objects participants design. |
| 227853 | machine-sewing | Longarm quilting names a machine-based quilting process. |
| 231120 | pole-dance | Combined showcase listing explicitly places the pole performance at DROM and aerial show at another venue. |
| 242788, 242789 | pole-dance | Pole conditioning and spin-pole classes; the latter also has a separate weekday inconsistency. |
| 243598, 243665, 245141 | machine-sewing | Descriptions supply sewing machines, including Singer Stylist machines at Open Sewing Lab. |
| 244299 | tabletop-rpg | Monster of the Week is explicitly a participatory tabletop role-playing game. |

Deliberate fallbacks include Friends Tuesday Mtg (a meeting), mixed Scrabble/Mahjong, general makerspaces with incidental 3D printing, hand stitching, and sewing classes whose available text never establishes machine use. Survey Says (238646) remains a survey-game opportunity rather than silently widening trivia’s scope. Cast-glass installations do not imply glassblowing. Film subjects and misleading tags do not turn a screening into a concert, dance class, or sport.

## Recommended next prototype batch

Priority balances recognition gain, reuse across venues, and a plausible silhouette at 16–32 px. Counts are **supporting event records / distinct stored venue-address pairs**, not independent productions, occurrence counts, or guaranteed future assignments. Mixed activities and featured instruments still need final assignment review after art exists.

| Priority | Concept | Records / venues | Visual direction and recognition gap | Example IDs |
| --- | --- | ---: | --- | --- |
| 1 | Pickleball | 14 / 3 | Broad solid paddle and perforated ball; table-tennis and tennis art depict different equipment. | 152932, 240497, 240543 |
| 2 | Interlocking toy bricks | 8 / 8 | One or two bright studded blocks; existing brick is masonry. | 195453, 201616, 203511 |
| 3 | DJ decks | 8 / 7 | Large platter/jog wheel and prominent fader; headphones omit active mixing. Avoid asserting vinyl hardware for an unspecified DJ set. | 97902, 202388, 214595 |
| 4 | Crochet | 8 / 8 | One large hook pulling a loop; yarn alone does not distinguish crochet from knitting. | 116043, 206610, 225829 |
| 5 | Trombone | 2 / 2 | Bell and extended U-shaped slide; existing trumpet has valves and different proportions. | 242792, 248152 |

These are recommendations, not approved artwork. Every prototype must pass the [automated visual review](../visual-review.md), especially small-size recognition and fidelity to the actual object. A subsequent assignment pass must consider the full revised catalog; do not bulk-assign merely because a record contributed an opportunity.

## Specific music opportunities worth preserving

Rare instruments can offer more recognition gain than another broad music symbol. None of these proposals requires guessing instrumentation from an artist’s identity.

| Concept | Records / venues | Evidence and visual direction |
| --- | ---: | --- |
| Steelpan | 1 / 1 | Patrick Davis’s Stomp, Clap and Sing (234865) explicitly features steel pan. Shallow metallic bowl, broad note fields, two mallets; distinct from skin drums. |
| Guzheng | 1 / 1 | Interactive guzheng performance/workshop (222339). Long low zither with a few visible bridges; simplify strings without losing structure. |
| Kalimba | 1 / 1 | Folk Jams in Greeley Square (130290) explicitly mentions a kalimba orchestra. Wooden thumb piano with metal tines. |
| Double bass | 2 / 2 | Port Ross ensemble (219076) names doublebass; Marc Edwards’s program (229254) names contrabass. Sloped shoulders, long neck, upright stance. |
| Cello | 2 / 2 | Don Juan listings (226386, 232262) advertise original live cello music. Upright body, endpin, bow. These are two listings of the same production, so two records overstate independent reuse; theater remains the primary activity. |
| Acoustic/classical guitar | 2 / 2 | SaRon Crenshaw Acoustic (83580) and Classical Guitar Society (243447). Wooden body and sound hole distinguish the bundled electric guitar. |
| Baritone saxophone | 1 / 1 | Explicitly billed in 229254. Long body and looped neck; compare against existing saxophone art before commissioning a near-duplicate. |
| Musical jug | 1 / 1 | Gowanus Jug & String Band Sessions (97177). Handled jug plus restrained sound cue; test that it reads as an instrument. |

The **genre and technique** leads are also saved, separately from instruments: ragtime (123434), stride piano (123434, 237585), early jazz (130203), Balkan brass (81239), Latin American bolero (241917), J-pop (242130, 242131), city pop (242131), neo-soul (242132), free jazz and progressive rock (246714), industrial electronic (223345), breakbeat (223346), house/techno (214595), surf rock (210356), blues, bluegrass, lo-fi, and stadium rock. Concrete exploratory directions range from a syncopated keyboard motif to a broken beat grid or reverb ripple.

**Those genre motifs are not proven recognizable symbols.** Test them against current notes/instrument art and neighboring genres before drawing a production batch. A star does not reliably identify J-pop, a cassette/skyline may convey nostalgia rather than city pop, and abstract rhythm marks may disappear at 16 px. Preserve the evidence without pretending the design problem is solved. Do not use saxophone for all jazz, or demographic/costume cues as substitutes for musical identity.

Other music formats remain distinct: choir (2 records), piano trio (3), big band (2, one associated with a December promotion), chamber music, guitar ensemble, jam session, drum circle, live film score, digital audio production, MIDI sequencing, and vinyl listening. A dense miniature ensemble is unlikely to read well; a shared score/stand or single defining instrument may be clearer.

## Other strong directions and existing-art improvements

Further grounded candidates include binoculars (3 venues), knitting needles (6), figure drawing (6), hand embroidery (2), cyanotype (1), woodturning (1), pottery wheel (1), hand papermaking (1), adaptive handcycle (1), laser cutter (1), vinyl cutter (2), aerial silks/hammock/trapeze, inline skating, ravioli, and the pasta chitarra. Keep cyanotype distinct from unspecified sun printing; keep handbuilding distinct from wheel throwing. Named dance styles are retained individually, including Lindy Hop, Charleston, Chicago Steppin, tango, salsa, Sabar, Kutiro, bélè, Vogue, and Graham technique; accurate movement references and practitioner recognition matter more than decorative dress.

Some improvements need **existing Noto art rather than new drawings**: running clubs using metaphor/brand emoji (150469, 150533, 150580, 150585, 169810); comedy using a portrait, shirt, or skyline (81277, 82725, 191993); Mahjong practice with flower cards (234277); chess lessons with a book (245158). Bluegrass already has banjo, piano has keyboard, and violin/viola often gain little from another near-identical silhouette. Studio controls already cover generic sound mixing. The review did not edit these emoji fields; route editorial changes through the normal emoji workflow.

## Review quality and separate data issues

The pass used full stored descriptions, including records whose source text was already clipped. Heuristics were advisory, every record received an explicit decision, and fresh DB validation rejected no stale inputs or concurrent assignment changes. Semantic consolidation merged equivalent life/figure drawing, toy-brick, stride, choir, DJ-deck, vinyl-listening, DAW, and big-band keys while retaining distinct instruments, styles, techniques, and visual variants.

Coordinating QA removed a Q&A proposal for Maddie’s Secret (132999) because its description specifically dated the Q&A to June 16/17. Other reviewers removed redundant film-frame and generic mixer proposals. Date-specific art-club activities were respected: origami on September 8 is not a 3D-printing session scheduled later in the month (245127).

The full-context pass also exposed **metadata issues requiring a separate cleanup**: December show promotion 184322; September 11 open-hours text 247377; Thursday/Friday pole class text 242789; Turin conference attached to an NYC venue 241300; mismatched library descriptions/venues 242509; generic makerspace prose on finance events 245074/245117. These are evidence conflicts, not independently verified correction instructions. No dates, locations, descriptions, or tags were changed by this review. Repair the source data before treating these candidate counts as attendance or true daily-program statistics.

## Verification and reproducibility

- Added `--date YYYY-MM-DD` scope to review preparation and opportunity reporting; ongoing spans are included. Omit the flag for the full active window.
- Complete 2,627-row packet passed current-state dry-run validation, then applied under the shared write lock with a before-image backup and the agent-origin migration.
- Fresh scoped queue: **0 pending**. Saved opportunity report: **2,627 / 2,627 current reviews, 0 stale**, 188 concepts.
- **40 event-icon tests pass**. Local production build passes. Both `src/data/events.day0.json` and `dist/data/events.day0.json` match all 2,627 persisted decisions, including 118 custom IDs; reasons/evidence/opportunities are absent from public event payloads.
- Local data/build refreshed; **nothing uploaded, deployed, committed, or pushed**. Suggestions add database review metadata, not frontend matching code or speculative asset downloads.

Snapshots, all decisions, before-images, reviewer notes, and raw reports are in `.scratch/today-icon-review/`. Key files: `combined-packet.json`, `combined-decisions.json`, `assignments-before.json`, `editorial-adjustments.json`, `after-review/manifest.json`, `results/opportunities.json`, `results/opportunities.md`, and `export-verification.json`. Suggestions remain durable in database review metadata and can be regenerated with `event_icon_review.py opportunities`; scratch files are not the source of truth.

Machine-readable curated concepts and evidence are in [the companion shortlist](20260908-today-shortlist.json). Next art work should use the [custom-icon workflow](../workflow.md) and create explicit event/tag/place associations only after the relevant artwork and semantic review.
