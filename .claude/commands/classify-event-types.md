# Classify Event Types Command

Populate the `events.event_type` column by classifying events against a fixed
taxonomy. The classifier runs as Claude (no Gemini call), reading event name +
description + venue + tags + occurrence shape and assigning one type per event.

## Taxonomy (33 types + Other catch-all, 6 categories)

> The exact storable label strings are also defined in `pipeline/event_types.py`
> (`VALID_EVENT_TYPES`) — the machine-readable single source of truth. When you
> add or rename a type, update **both** this doc and that module.

The organizing question is **"what is the attendee doing?"** — orthogonal to
content tags. A "Jazz Concert" is `Performance > Concert` + content tag `Jazz`;
a "Jazz Workshop" is `Participatory > Workshop` + content tag `Jazz`. Same
content, different *type*. **Do not introduce types that duplicate content
tags** (e.g. no `Dance` type — a dance show is `Theater Show` + `Dance` tag).

### Performance — audience watches a billed showing
- **Concert** — billed musical act(s); attendee watches/listens
- **Theater Show** — any billed stage performance: scripted play, dance, opera, drag, burlesque, magic, musical theater. (Genre lives in content tags.)
- **Comedy Show** — stand-up, sketch, improv lineup billed as comedy
- **Screening** — film/video with a fixed start time
- **Sports** — physical, in-person game/match watched as spectator (esports is NOT Sports — see `Game`)
- **Reading** — single-author or panel reading, book talk, poetry reading

### Participatory — attendee is the active subject
- **Class** — instructor-led skill-building with a **curriculum or level**: language course, ceramics 101, dance level 2. Multi-session implied.
- **Workshop** — **single-session** hands-on making (cocktails, bookbinding, mosaic). One-off making event with an instructor.
- **Camp** — multi-day immersive program, usually kids/teens
- **Fitness** — yoga, run club, dance fitness, group exercise where the point is the body workout
- **Game** — structured play with a win condition: trivia, MTG, bingo, scrabble, tournaments, **esports/LAN parties**
- **Open Practice** — **recurring drop-in participatory with no curriculum or level**: figure drawing, jam session, open mic, social dance practica, meditation sits without religious framing, affinity-group swim/climb/skate sessions
- **Volunteer** — labor-donation event (food pantry, park cleanup, tax prep, mentoring)
- **Drop-In Service** — show up to receive **individualized free service**: legal clinic, mock citizenship interview, drop-in resume help, library tech help, 1:1 consultations (career, design, HR), mobile health van, period pantry, community acupuncture by donation, free haircuts. Different from `Volunteer` (you receive, not give labor) and `Workshop` (no group instruction).

### Browsable — self-paced consumption of a curated environment
- **Exhibition** — gallery/museum show with a defined open run. Static single-piece installations you view at your own pace live here too. (A *scripted, sensory, time-slotted* environment you move through is `Immersive Experience`, not Exhibition.)
- **Open House** — venue opens normally-gated space (museum free Fridays, school open house, open studios, artist-residency open hours)
- **Market** — vendor-driven commerce: flea market, greenmarket, craft bazaar, vendor fair. Attendee browses to buy.
- **Fair** — booth/table-walking convening where the attendee circulates among many exhibitors to gather information, meet representatives, or sign up: career/job fair, college or grad-school fair, resource or benefits fair, volunteer fair, health fair. Different from `Market` (vendors selling goods — a fair's tables recruit and inform rather than transact), `Exhibition` (curated works on view, not staffed booths), `Open House` (one venue opening its own doors, not many organizations convening in a hall), and `Festival` (multi-act programming sprawl — a "street fair" or "renaissance faire" is `Festival`/`Community Celebration` despite the name).
- **Pop-Up** — venue hosts a one-off guest artist/vendor that doesn't fit the Market pattern: tattoo day at a bar, food pop-up at a brewery, plant giveaway, pet portrait session at a café. Different from `Market` (single guest, not vendor sprawl) and `Workshop` (no instruction).
- **Immersive Experience** — a ticketed, time-slotted, multi-sensory environment or scenario the attendee is enveloped in: museum overnights, dining-in-the-dark, scent/sensory journeys, interactive narrative installations, immersive wellness retreats. Different from `Exhibition` (self-paced viewing of works on a run), `Theater Show` (no billed stage performance), and `Tour` (not place-learning). The event is sold as an "experience."

### Social — open-ended gathering; being among others is the point
- **Club Night** — DJ-driven late-night dancing. **Weekly recurring DJ + dancing → Club Night** regardless of "Party" in the name.
- **Party** — themed social gathering, networking mixer, brunch, holiday party. Default Social bucket when nothing else fits.
- **Benefit** — fundraiser / gala / awards ceremony with a **mixed program** (cocktails + auction + performance + dinner). Different from `Concert` (single billed perf) and `Party` (mixer, no program).
- **Watch Party** — group viewing of a broadcast (World Cup, album listening)
- **Festival** — multi-act, multi-day curated programming sprawl (film fest, multi-stage music fest, citywide arts week). NOT markets/bazaars (those are `Market`).
- **Community Celebration** — a public, festive gathering marking a civic, seasonal, or milestone occasion with light mixed programming, open to all ages: anniversary celebrations, "X Day" community/neighborhood days, park/plaza celebrations, holiday family days, seasonal kickoffs ("Summer Celebration", "School's Out"). Different from `Festival` (multi-act/multi-day sprawl — Celebration is typically single-day and occasion-anchored), `Ceremony` (formal ritual observance — Celebration is festive, not ritual), `Party` (adult mixer/nightlife — Celebration is civic/family/public-occasion), and `Benefit` (no fundraising program).

### Gathering — facilitated convening around topic/faith/function
- **Talk** — lecture, panel, single-topic informational session; audience listens. Industry panels (Tech Week) live here.
- **Service** — **religious** ritual requiring liturgy/ritual/clergy/consecrated space. Worship, Mass, vespers, sermon, zazen with a teacher, secular humanist Sunday platform.
- **Ceremony** — **secular/civic** *formal/ritual* observance: flag raising, civic memorial, dedication, naming, swearing-in, awards ceremony without performance program. The defining mark is a ritual/formal moment, not festivity. A festive public occasion (anniversary party, "X Day" celebration, holiday family day) is `Community Celebration`, not Ceremony. Different from `Service` (religious), `Festival` (multi-act).
- **Civic Meeting** — community board hearing, town hall, advocacy group meeting, governance session
- **Discussion Group** — book club, support group, study circle, peer-led topical discussion. Repeating convening around shared interest, no liturgy and no governance agenda.

### Outing — bounded group experience anchored to a place
- **Tour** — docent-led or self-guided exploration of place: walking tour, garden tour, birding, factory tour
- **Outing** — group outdoor activity not framed as instruction or place-learning: social bike ride, group skate, casual group walk

### Catch-all
- **Other** — Use ONLY when an event is genuinely a real event but none of the 33 types above describe its structure. Prefer the closest-fitting real type over `Other` whenever defensible. If `Other` accumulates a recurring pattern (3+ events of the same shape), the taxonomy probably needs a new type — flag it for review. Do NOT use `Other` for junk rows (closures, submission calls, marketing) — those go to `UNKNOWN`.

## Decision rules

1. **Type the event, not the occurrence.** A multi-week theater run is one
   `Theater Show`, not 14 of them. Span carries duration, not type.
2. **Festivals contain performances.** Type the container as `Festival`; if
   individual lineup slots are separate event rows, each gets its own
   performance type. Markets are `Market`, not `Festival`.
3. **Trivia/bingo/MTG/esports/LAN → `Game`** — structure is "show up, play,
   see who wins." Sports = physical, in-person spectator events.
4. **Outdoor movie series** → `Screening`. Outdoor concert series → `Concert`.
   The "social/picnic" framing is context, not structure.
5. **Workshop vs Class vs Open Practice triangle:**
   - **Workshop** = single-session hands-on with instructor
   - **Class** = multi-session with curriculum or level number
   - **Open Practice** = recurring drop-in, no curriculum, no level. Open mic,
     jam, figure drawing, meditation circle, climb/skate/swim affinity night.
6. **Walking tours vs walking classes vs group walks** — Tour learns about
   place; Class learns a skill; Outing is casual recurring walks/rides.
7. **Service requires liturgy or ritual.** Mass, worship, zazen-with-teacher,
   formal religious ceremony, civic memorial. Wellness meditations without
   religious framing → `Open Practice`. Religious classes (Bible/Torah/sutra
   study with curriculum) → `Class`.
8. **Open House** is for normally-gated venues throwing open the doors (museum
   free hours, school open house, artist-residency open studios). `Exhibition`
   is when there's a curated show on view. `Market` is when vendors are selling.
   `Fair` is when many organizations staff tables to recruit/inform.
   **Fair vs Market vs Festival — go by what the tables are for, not the word
   "fair" in the name.** Tables recruiting, advising, or signing people up
   (career, college, grad school, volunteer, health, benefits, resource,
   housing, camp) → `Fair`. Tables selling goods (craft fair, vendor fair,
   holiday market, book fair with a sales floor) → `Market`. Street
   fairs/festivals, renaissance faires, county fairs with rides and stages →
   `Festival` or `Community Celebration`.
9. **Benefit/Gala vs Party vs Concert:**
   - If billed as fundraiser **with mixed program** (cocktail hour + auction +
     speeches + performance) → `Benefit`
   - If single billed performance with "benefit" framing → `Concert` or `Theater Show`
   - If pure mixer/networking/party → `Party`
10. **Civic Meeting vs Discussion Group vs Talk:**
    - Governmental/advocacy agenda → `Civic Meeting`
    - Peer-led topical convening (book club, support group) → `Discussion Group`
    - Single billed speaker/panel → `Talk`
11. **Theater Show is the umbrella for any billed stage performance.** Drama,
    dance, ballet, opera, drag, burlesque, magic, musical theater all live here.
    Genre lives in content tags (e.g. `Drag Show`, `Ballet`, `Musical`).
12. **Immersive Experience vs Exhibition vs Theater Show.** If the attendee
    moves through a scripted, sensory, time-slotted *environment* (museum
    overnight, dining-in-the-dark, scent journey, interactive narrative) →
    `Immersive Experience`. If they view works at their own pace on an open run
    → `Exhibition`. If they watch a billed stage performance → `Theater Show`.
13. **Community Celebration vs Festival vs Ceremony vs Party.** Festive public
    occasion (anniversary, "X Day", park/holiday/seasonal celebration, family
    fun day) → `Community Celebration`. Multi-act/multi-day curated sprawl →
    `Festival`. Formal/ritual civic observance → `Ceremony`. Adult
    mixer/nightlife → `Party`.
14. **When two types are plausible**, choose the one that describes the
    *primary attendee experience*.

## Pre-classification junk filter

Reject these patterns before classifying — they're not events:
- Title is a closure / holiday observance ("Memorial Day Observation", "Closed for Holiday", "Building Closed")
- Title is a call for submissions / applications ("Submissions: …", "Open Call")
- Title is venue marketing ("Private Events", "Dinner Service", "Available for Booking")
- Title is a placeholder ("TBD", "No Name", "Untitled") with empty description
- Description equals "No description available" AND name is generic AND single occurrence at single venue

For these, output `UNKNOWN` and flag for upstream extractor cleanup.

## Workflow

### Mode A: Backfill existing events

1. Pull a batch of un-classified events (LIMIT 500-1000) with their `name`,
   `short_name`, `description`, `location_name`, `sublocation`, `tags`,
   `section`, `occ_count`, `span_days`. Write to a JSON file.
2. Spawn a sub-agent: hand it the JSON file path and **this entire command
   prompt**, ask for `[{"id": N, "type": "Label"}, ...]` output written to
   a result file.
3. Bulk-update: `UPDATE events SET event_type=%s WHERE id=%s` for each row.
4. Repeat until `event_type IS NULL` count is 0.

### Mode B: Pipeline integration

`/run-pipeline` Step 4 runs Mode A scoped to `event_type IS NULL` active events
after each pipeline run (post dedupe/hide/merge), so new events get typed
automatically without a manual full backfill. This is the current integration.

A future tighter option: classify each event at insert time inside
`pipeline/merger.py` using a single-event prompt that embeds this taxonomy,
storing on the `events` row directly. Not yet implemented — the post-run
sweep in Mode B above is the sustaining mechanism for now.

## Valid type labels (exact strings for storage)

`Concert`, `Theater Show`, `Comedy Show`, `Screening`, `Sports`, `Reading`,
`Class`, `Workshop`, `Camp`, `Fitness`, `Game`, `Open Practice`, `Volunteer`, `Drop-In Service`,
`Exhibition`, `Open House`, `Market`, `Fair`, `Pop-Up`, `Immersive Experience`,
`Club Night`, `Party`, `Benefit`, `Watch Party`, `Festival`, `Community Celebration`,
`Talk`, `Service`, `Ceremony`, `Civic Meeting`, `Discussion Group`,
`Tour`, `Outing`,
`Other` (genuine event, no taxonomy fit — flag for review),
`UNKNOWN` (not an event — closures, submissions, marketing).

## Validating

```sql
SELECT event_type, COUNT(*) c
FROM events WHERE archived=0 AND suppressed=0 AND event_type IS NOT NULL
GROUP BY event_type ORDER BY c DESC;
```

Spot-check 20 random rows per type. Look for cases where the type leaked from
a content tag (e.g. a `Jazz` tag forcing `Concert` when the event is actually
a `Workshop`).

## Notes on relation to `section`

`section` (Events/Ongoing) is a **duration signal, not a type signal** and
remains an independent column. Exhibitions tend to be Ongoing; one-off
screenings tend to be Events; but recurring classes and weekly trivia split
across both. Filter on type and cadence independently.
